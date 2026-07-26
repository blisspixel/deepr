"""Authoritative fail-closed spend-cap resolution for metered work.

Every paid entry point must ultimately use these caps inside the durable
reservation transaction. Environment limits and the persisted operator budget
are all ceilings. The tightest applicable value wins, zero disables paid work,
and malformed policy is an error rather than an excuse to use a larger default.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Protocol

from filelock import FileLock

_DEFAULTS: dict[str, float] = {"per_job": 5.0, "daily": 10.0}
_PRIMARY: dict[str, str] = {
    "per_job": "DEEPR_MAX_COST_PER_JOB",
    "daily": "DEEPR_MAX_COST_PER_DAY",
    "weekly": "DEEPR_MAX_COST_PER_WEEK",
    "monthly": "DEEPR_MAX_COST_PER_MONTH",
}
_LEGACY: dict[str, str] = {
    "per_job": "DEEPR_PER_JOB_LIMIT",
    "daily": "DEEPR_DAILY_LIMIT",
    "weekly": "DEEPR_WEEKLY_LIMIT",
    "monthly": "DEEPR_MONTHLY_LIMIT",
}
BUDGET_FILE_ENV = "DEEPR_BUDGET_FILE"


class SpendCapConfigurationError(ValueError):
    """A spend policy cannot be proven safe enough to admit paid work."""


class MutableSpendLimits(Protocol):
    """Budget-shaped settings that can be narrowed by operator authority."""

    max_cost_per_job: float
    daily_limit: float
    monthly_limit: float


@dataclass(frozen=True)
class OperatorBudget:
    """The spend-authority fields read from the operator budget document."""

    configured: bool
    monthly_limit: float
    frozen: bool
    freeze_reason: str = ""


def budget_file_path() -> Path:
    """Return the single persisted operator-budget path."""
    configured = os.getenv(BUDGET_FILE_ENV, "").strip()
    if configured:
        return Path(configured)
    try:
        return Path.home() / ".deepr" / "budget.json"
    except (OSError, RuntimeError):
        return Path(".deepr") / "budget.json"


@contextmanager
def spend_policy_lock(path: Path | None = None, *, timeout_seconds: float = 10.0) -> Iterator[None]:
    """Serialize policy mutations and reservation authority reads."""
    target = path or budget_file_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(f"{target.name}.lock")
    with FileLock(str(lock_path), timeout=timeout_seconds, thread_local=False):
        yield


def _money(value: object, *, source: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpendCapConfigurationError(f"{source} must be a finite non-negative number")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise SpendCapConfigurationError(f"{source} must be a finite non-negative number")
    return number


def read_operator_budget(path: Path | None = None) -> OperatorBudget:
    """Strictly read the operator's persisted monthly authority.

    A missing file means paid capacity has not been authorized. Existing legacy
    files remain readable, but the old ``-1`` unlimited value is rejected.
    """
    target = path or budget_file_path()
    if not target.exists():
        return OperatorBudget(configured=False, monthly_limit=0.0, frozen=False)
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SpendCapConfigurationError(f"operator budget is unreadable: {target}") from exc
    return parse_operator_budget(document)


def parse_operator_budget(document: object) -> OperatorBudget:
    """Validate spend-authority fields in an already loaded document."""
    if not isinstance(document, dict):
        raise SpendCapConfigurationError("operator budget must be a JSON object")
    monthly_limit = _money(document.get("monthly_limit", 0.0), source="operator monthly_limit")
    frozen = document.get("paid_api_frozen", False)
    if not isinstance(frozen, bool):
        raise SpendCapConfigurationError("operator paid_api_frozen must be true or false")
    reason = document.get("freeze_reason", "")
    if not isinstance(reason, str):
        raise SpendCapConfigurationError("operator freeze_reason must be a string")
    return OperatorBudget(
        configured=True,
        monthly_limit=monthly_limit,
        frozen=frozen,
        freeze_reason=reason.strip(),
    )


def _parse_env_limit(env_name: str) -> float | None:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise SpendCapConfigurationError(f"{env_name} must be a finite non-negative number") from exc
    if not isfinite(value) or value < 0:
        raise SpendCapConfigurationError(f"{env_name} must be a finite non-negative number")
    return value


def _environment_limit(key: str) -> float | None:
    values = [value for value in (_parse_env_limit(_PRIMARY[key]), _parse_env_limit(_LEGACY[key])) if value is not None]
    return min(values) if values else None


def resolve_spend_caps(
    *,
    budget_path: Path | None = None,
    operator_budget: OperatorBudget | None = None,
) -> dict[str, float]:
    """Resolve per-job, UTC day/week/month caps in USD.

    Paid work is default-off until either an operator budget file or an explicit
    monthly environment ceiling exists. A persisted freeze or any zero window
    makes the dependent narrower windows zero too.
    """
    if budget_path is not None and operator_budget is not None:
        raise ValueError("budget_path and operator_budget are mutually exclusive")
    operator = operator_budget or read_operator_budget(budget_path)
    per_job = _environment_limit("per_job")
    daily = _environment_limit("daily")
    weekly = _environment_limit("weekly")
    monthly = _environment_limit("monthly")

    per_job = _DEFAULTS["per_job"] if per_job is None else per_job
    daily = _DEFAULTS["daily"] if daily is None else daily

    monthly_candidates: list[float] = []
    if monthly is not None:
        monthly_candidates.append(monthly)
    if operator.configured:
        monthly_candidates.append(operator.monthly_limit)
    monthly = min(monthly_candidates) if monthly_candidates else 0.0
    if operator.frozen:
        monthly = 0.0

    weekly = monthly if weekly is None else min(weekly, monthly)
    daily = min(daily, weekly)
    per_job = min(per_job, daily)
    return {
        "per_job": per_job,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
    }


def clamp_spend_authority(settings: MutableSpendLimits) -> None:
    """Narrow budget-shaped settings without allowing a policy increase."""
    caps = resolve_spend_caps()
    settings.max_cost_per_job = min(settings.max_cost_per_job, caps["per_job"])
    settings.daily_limit = min(settings.daily_limit, caps["daily"])
    settings.monthly_limit = min(settings.monthly_limit, caps["monthly"])


def freeze_paid_api(reason: str, *, path: Path | None = None) -> OperatorBudget:
    """Persist a cross-process paid freeze after a safety invariant breaks."""
    target = path or budget_file_path()
    with spend_policy_lock(target):
        return _freeze_paid_api_unlocked(reason, target=target)


def _freeze_paid_api_unlocked(reason: str, *, target: Path) -> OperatorBudget:
    """Write a paid freeze while the caller holds ``spend_policy_lock``."""
    from deepr.utils.atomic_io import atomic_write_json

    if target.exists():
        try:
            document = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SpendCapConfigurationError(f"operator budget is unreadable: {target}") from exc
    else:
        document = {"monthly_limit": 0.0}
    parse_operator_budget(document)
    document["paid_api_frozen"] = True
    document["freeze_reason"] = reason.strip() or "paid cost safety invariant failed"
    document["frozen_at"] = datetime.now(UTC).isoformat()
    parse_operator_budget(document)
    atomic_write_json(target, document, fsync=True)
    return parse_operator_budget(document)


__all__ = [
    "BUDGET_FILE_ENV",
    "OperatorBudget",
    "SpendCapConfigurationError",
    "budget_file_path",
    "clamp_spend_authority",
    "freeze_paid_api",
    "parse_operator_budget",
    "read_operator_budget",
    "resolve_spend_caps",
    "spend_policy_lock",
]
