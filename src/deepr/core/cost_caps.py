"""Authoritative fail-closed spend-cap resolution for metered work.

Every paid entry point must ultimately use these caps inside the durable
reservation transaction. Environment limits and the persisted operator budget
are all ceilings. The tightest applicable value wins, zero disables paid work,
and malformed policy is an error rather than an excuse to use a larger default.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from dotenv import dotenv_values
from filelock import FileLock

_DEFAULTS: dict[str, float] = {"per_job": 1.0, "daily": 2.0}
_ABSOLUTE_CEILINGS: dict[str, float] = {
    "per_job": 5.0,
    "daily": 5.0,
    "weekly": 5.0,
    "monthly": 5.0,
}
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
_FREEZE_KINDS = frozenset(
    {
        "account_control_expired",
        "account_control_unknown",
        "account_identity_mismatch",
        "billing_divergence",
        "billing_evidence_storage_failure",
        "cost_ceiling_divergence",
        "legacy",
        "manual",
        "unconfigured",
        "zero_ceiling",
    }
)
_EVIDENCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROVIDER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_PAID_API_PROVIDER: ContextVar[str | None] = ContextVar("deepr_paid_api_provider", default=None)
_VERIFIED_AUTHORITY_MARKER = object()


class SpendCapConfigurationError(ValueError):
    """A spend policy cannot be proven safe enough to admit paid work."""


class MutableSpendLimits(Protocol):
    """Budget-shaped settings that can be narrowed by operator authority."""

    max_cost_per_job: float
    daily_limit: float
    monthly_limit: float


class VerifiedSpendAuthority(Protocol):
    """Shape returned by immutable account-evidence verification."""

    @property
    def evidence_ids(self) -> tuple[str, ...]: ...

    @property
    def recovered_freeze_id(self) -> str: ...

    @property
    def valid_until(self) -> datetime: ...

    @property
    def providers(self) -> tuple[str, ...]: ...

    @property
    def hard_monthly_limit_usd(self) -> float: ...


@dataclass(frozen=True)
class OperatorBudget:
    """The spend-authority fields read from the operator budget document."""

    configured: bool
    monthly_limit: float
    frozen: bool
    freeze_reason: str = ""
    freeze_id: str = ""
    freeze_kind: str = ""
    frozen_at: datetime | None = None
    authorization_evidence_ids: tuple[str, ...] = ()
    authorized_until: datetime | None = None
    authorization_valid: bool = False
    authorization_providers: tuple[str, ...] = ()
    authorization_hard_monthly_limit: float = 0.0
    authorization_recovered_freeze_id: str = ""
    authorization_recovered_frozen_at: datetime | None = None
    authorization_cost_state_id: str = ""
    _verified_marker: object | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class _AuthorizationReference:
    evidence_ids: tuple[str, ...]
    valid_until: datetime
    recovered_freeze_id: str
    recovered_frozen_at: datetime | None
    cost_state_id: str


def budget_file_path() -> Path:
    """Return the single persisted operator-budget path."""
    configured = os.getenv(BUDGET_FILE_ENV, "").strip()
    if configured:
        target = Path(configured)
        if not target.is_absolute():
            raise SpendCapConfigurationError(f"{BUDGET_FILE_ENV} must be an absolute path")
        return target
    try:
        target = Path.home() / ".deepr" / "budget.json"
    except (OSError, RuntimeError) as exc:
        raise SpendCapConfigurationError("operator budget home path is unavailable") from exc
    if not target.is_absolute():
        raise SpendCapConfigurationError("operator budget home path must be absolute")
    return target


def _normalized_provider(provider: str) -> str:
    normalized = provider.strip().casefold()
    if _PROVIDER_PATTERN.fullmatch(normalized) is None:
        raise SpendCapConfigurationError("paid API provider must be a bounded identifier")
    return normalized


@contextmanager
def paid_api_provider_scope(provider: str) -> Iterator[None]:
    """Bind legacy nested cap reads to one already identified provider."""
    token = _PAID_API_PROVIDER.set(_normalized_provider(provider))
    try:
        yield
    finally:
        _PAID_API_PROVIDER.reset(token)


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


def _reject_budget_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r} is not allowed")


def _reject_budget_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON key {key!r} is not allowed")
        document[key] = value
    return document


def _loads_operator_budget(text: str) -> dict[str, object]:
    document = json.loads(
        text,
        parse_constant=_reject_budget_json_constant,
        object_pairs_hook=_reject_budget_duplicate_keys,
    )
    if not isinstance(document, dict):
        raise ValueError("operator budget must be a JSON object")
    return document


def _active_cost_state_id() -> str:
    try:
        from deepr.observability.cost_ledger import (
            CostLedgerDurabilityError,
            CostLedgerLockTimeout,
            CostLedgerReadError,
            current_cost_state_id,
        )

        return current_cost_state_id()
    except (CostLedgerDurabilityError, CostLedgerLockTimeout, CostLedgerReadError, ValueError) as exc:
        raise SpendCapConfigurationError("cost-state identity is unavailable") from exc


def read_operator_budget(path: Path | None = None, *, provider: str | None = None) -> OperatorBudget:
    """Strictly read the operator's persisted monthly authority.

    A missing file means paid capacity has not been authorized. Existing legacy
    files remain readable, but the old ``-1`` unlimited value is rejected.
    """
    target = path or budget_file_path()
    if not target.exists():
        return OperatorBudget(
            configured=False,
            monthly_limit=0.0,
            frozen=True,
            freeze_reason="paid API account controls are not configured",
            freeze_kind="unconfigured",
        )
    try:
        document = _loads_operator_budget(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SpendCapConfigurationError(f"operator budget is unreadable: {target}") from exc
    operator = parse_operator_budget(document)
    if document.get("paid_api_frozen", False) is True or operator.monthly_limit <= 0:
        return operator
    reference = _authorization_fields(document)
    requested_provider = provider or _PAID_API_PROVIDER.get()
    if requested_provider is None:
        return replace(
            operator,
            frozen=True,
            freeze_reason="paid API provider binding is required",
            freeze_kind="account_identity_mismatch",
        )
    requested_provider = _normalized_provider(requested_provider)
    if reference is None or not reference.recovered_freeze_id or reference.recovered_frozen_at is None:
        return operator
    if reference.cost_state_id != _active_cost_state_id():
        return replace(
            operator,
            frozen=True,
            freeze_reason="paid API authorization belongs to another cost state",
            freeze_kind="account_identity_mismatch",
        )
    try:
        from deepr.observability.provider_account_controls import (
            ProviderAccountControlError,
            verify_paid_api_authorization,
        )

        try:
            authorization = verify_paid_api_authorization(
                reference.evidence_ids,
                expected_freeze_id=reference.recovered_freeze_id,
                expected_frozen_at=reference.recovered_frozen_at,
                monthly_limit_usd=operator.monthly_limit,
                requested_provider=requested_provider,
            )
        except ProviderAccountControlError as exc:
            kind = "account_control_expired" if "expired" in str(exc).casefold() else "account_identity_mismatch"
            return replace(
                operator,
                frozen=True,
                freeze_reason=f"paid API account-control evidence is invalid: {exc}",
                freeze_kind=kind,
            )
    except ImportError as exc:  # pragma: no cover - installed package invariant
        raise SpendCapConfigurationError("paid API evidence verifier is unavailable") from exc
    if reference.valid_until != authorization.valid_until:
        return replace(
            operator,
            frozen=True,
            freeze_reason="paid API authorization expiration does not match immutable evidence",
            freeze_kind="account_identity_mismatch",
        )
    return _with_verified_authorization(operator, authorization)


def _aware_datetime(value: object, *, source: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise SpendCapConfigurationError(f"{source} must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise SpendCapConfigurationError(f"{source} must be a timezone-aware timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpendCapConfigurationError(f"{source} must be a timezone-aware timestamp")
    return parsed.astimezone(UTC)


def _authorization_cost_state_id(value: object) -> str:
    if not isinstance(value, str) or len(value) != 32:
        raise SpendCapConfigurationError("operator authorization cost_state_id is invalid")
    try:
        int(value, 16)
    except ValueError as exc:
        raise SpendCapConfigurationError("operator authorization cost_state_id is invalid") from exc
    return value


def _authorization_fields(document: dict[str, object]) -> _AuthorizationReference | None:
    raw = document.get("paid_api_authorization")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SpendCapConfigurationError("operator paid_api_authorization must be a JSON object")
    allowed = {
        "authority",
        "evidence_ids",
        "valid_until",
        "recovered_freeze_id",
        "recovered_frozen_at",
        "cost_state_id",
    }
    if set(raw).difference(allowed):
        raise SpendCapConfigurationError("operator paid_api_authorization contains unknown fields")
    if raw.get("authority") != "verified_by_deepr":
        raise SpendCapConfigurationError("operator paid_api_authorization authority is not verified")
    evidence = raw.get("evidence_ids")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 32:
        raise SpendCapConfigurationError("operator paid_api_authorization evidence_ids must be a non-empty list")
    evidence_ids: list[str] = []
    for value in evidence:
        if not isinstance(value, str) or _EVIDENCE_ID_PATTERN.fullmatch(value) is None:
            raise SpendCapConfigurationError("operator paid_api_authorization contains an invalid evidence ID")
        evidence_ids.append(value)
    if len(set(evidence_ids)) != len(evidence_ids):
        raise SpendCapConfigurationError("operator paid_api_authorization evidence IDs must be unique")
    valid_until = _aware_datetime(raw.get("valid_until"), source="operator paid_api_authorization valid_until")
    recovered_freeze_id = raw.get("recovered_freeze_id", "")
    if not isinstance(recovered_freeze_id, str) or (
        recovered_freeze_id and _EVIDENCE_ID_PATTERN.fullmatch(recovered_freeze_id) is None
    ):
        raise SpendCapConfigurationError("operator authorization recovered_freeze_id must be a bounded identifier")
    raw_recovered_frozen_at = raw.get("recovered_frozen_at")
    recovered_frozen_at = (
        None
        if raw_recovered_frozen_at is None
        else _aware_datetime(
            raw_recovered_frozen_at,
            source="operator paid_api_authorization recovered_frozen_at",
        )
    )
    cost_state_id = _authorization_cost_state_id(raw.get("cost_state_id"))
    return _AuthorizationReference(
        evidence_ids=tuple(evidence_ids),
        valid_until=valid_until,
        recovered_freeze_id=recovered_freeze_id,
        recovered_frozen_at=recovered_frozen_at,
        cost_state_id=cost_state_id,
    )


def _with_verified_authorization(
    operator: OperatorBudget,
    authorization: VerifiedSpendAuthority,
) -> OperatorBudget:
    """Create an operator budget carrying evidence-derived authority."""
    from deepr.observability.cost_ledger import current_cost_state_id

    return replace(
        operator,
        frozen=False,
        freeze_reason="",
        freeze_id="",
        freeze_kind="",
        frozen_at=None,
        authorization_evidence_ids=authorization.evidence_ids,
        authorized_until=authorization.valid_until,
        authorization_valid=True,
        authorization_providers=authorization.providers,
        authorization_hard_monthly_limit=authorization.hard_monthly_limit_usd,
        authorization_recovered_freeze_id=authorization.recovered_freeze_id,
        authorization_cost_state_id=current_cost_state_id(),
        _verified_marker=_VERIFIED_AUTHORITY_MARKER,
    )


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
    freeze_id = document.get("freeze_id", "")
    if not isinstance(freeze_id, str) or (freeze_id and _EVIDENCE_ID_PATTERN.fullmatch(freeze_id) is None):
        raise SpendCapConfigurationError("operator freeze_id must be a bounded identifier")
    freeze_kind = document.get("freeze_kind", "legacy" if frozen else "")
    if not isinstance(freeze_kind, str) or (freeze_kind and freeze_kind not in _FREEZE_KINDS):
        raise SpendCapConfigurationError("operator freeze_kind is not recognized")
    raw_frozen_at = document.get("frozen_at")
    frozen_at = None if raw_frozen_at is None else _aware_datetime(raw_frozen_at, source="operator frozen_at")
    authorization = _authorization_fields(document)
    evidence_ids = authorization.evidence_ids if authorization is not None else ()
    authorized_until = authorization.valid_until if authorization is not None else None
    effective_frozen = frozen
    effective_reason = reason.strip()
    effective_kind = freeze_kind
    if not effective_frozen and monthly_limit == 0:
        effective_frozen = True
        effective_reason = "paid API monthly ceiling is zero"
        effective_kind = "zero_ceiling"
    elif not effective_frozen:
        effective_frozen = True
        if authorized_until is not None and authorized_until <= datetime.now(UTC):
            effective_reason = "paid API account-control authorization expired"
            effective_kind = "account_control_expired"
        else:
            effective_reason = "paid API account-control authorization is missing or unverified"
            effective_kind = "account_control_unknown"
    return OperatorBudget(
        configured=True,
        monthly_limit=monthly_limit,
        frozen=effective_frozen,
        freeze_reason=effective_reason,
        freeze_id=freeze_id,
        freeze_kind=effective_kind,
        frozen_at=frozen_at,
        authorization_evidence_ids=evidence_ids,
        authorized_until=authorized_until,
        authorization_valid=False,
        authorization_recovered_freeze_id=(authorization.recovered_freeze_id if authorization is not None else ""),
        authorization_recovered_frozen_at=(authorization.recovered_frozen_at if authorization is not None else None),
        authorization_cost_state_id=(authorization.cost_state_id if authorization is not None else ""),
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


def _checkout_policy_value(path: Path, env_name: str, raw: object) -> float:
    if not isinstance(raw, str) or not raw.strip():
        raise SpendCapConfigurationError(f"{path}:{env_name} must be a finite non-negative number")
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise SpendCapConfigurationError(f"{path}:{env_name} must be a finite non-negative number") from exc
    if not isfinite(value) or value < 0:
        raise SpendCapConfigurationError(f"{path}:{env_name} must be a finite non-negative number")
    return value


def _read_checkout_policy(path: Path) -> dict[str, float]:
    try:
        document = dotenv_values(dotenv_path=path, interpolate=False)
    except (OSError, UnicodeError) as exc:
        raise SpendCapConfigurationError(f"spend-cap source is unreadable: {path}") from exc
    if not path.is_file():
        raise SpendCapConfigurationError(f"spend-cap source disappeared while being read: {path}")
    current: dict[str, list[float]] = {key: [] for key in _PRIMARY}
    for key in _PRIMARY:
        for env_name in (_PRIMARY[key], _LEGACY[key]):
            if env_name in document:
                current[key].append(_checkout_policy_value(path, env_name, document[env_name]))
    normalized = {key: min(values) for key, values in current.items() if values}
    for key in normalized:
        runtime_values = [
            value for value in (_parse_env_limit(_PRIMARY[key]), _parse_env_limit(_LEGACY[key])) if value is not None
        ]
        if runtime_values:
            normalized[key] = min(normalized[key], *runtime_values)
    return normalized


def _trusted_checkout_limits() -> dict[str, tuple[float, ...]]:
    """Load caps from validated checkout env files persisted by cost authority.

    ``load_dotenv`` makes a checkout-local cap look like a process variable but
    loses its provenance. A wheel launched elsewhere must retain that tighter
    bound, so only validated checkout files discovered through the canonical
    cost-source registry are consulted here.
    """
    from deepr.observability.cost_ledger import (
        CostLedgerReadError,
        register_spend_cap_env_source,
        well_known_spend_cap_env_paths,
    )

    limits: dict[str, list[float]] = {key: [] for key in _PRIMARY}
    try:
        paths = well_known_spend_cap_env_paths()
        for path in paths:
            effective = register_spend_cap_env_source(path, _read_checkout_policy(path))
            for key, value in effective.items():
                limits[key].append(value)
    except CostLedgerReadError as exc:
        raise SpendCapConfigurationError(f"spend-cap provenance is incomplete: {exc}") from exc
    return {key: tuple(values) for key, values in limits.items()}


def _environment_limit(key: str, trusted_values: tuple[float, ...] = ()) -> float | None:
    values = [
        value
        for value in (_parse_env_limit(_PRIMARY[key]), _parse_env_limit(_LEGACY[key]), *trusted_values)
        if value is not None
    ]
    return min(values) if values else None


def resolve_spend_caps(
    *,
    budget_path: Path | None = None,
    operator_budget: OperatorBudget | None = None,
    provider: str | None = None,
) -> dict[str, float]:
    """Resolve per-job, UTC day/week/month caps in USD.

    Paid work is default-off until either an operator budget file or an explicit
    monthly environment ceiling exists. A persisted freeze or any zero window
    makes the dependent narrower windows zero too.
    """
    if budget_path is not None and operator_budget is not None:
        raise ValueError("budget_path and operator_budget are mutually exclusive")
    requested_provider = provider or _PAID_API_PROVIDER.get()
    if requested_provider is not None:
        requested_provider = _normalized_provider(requested_provider)
    operator = operator_budget or read_operator_budget(budget_path, provider=requested_provider)
    if operator_budget is not None and (
        requested_provider is None
        or operator._verified_marker is not _VERIFIED_AUTHORITY_MARKER
        or not operator.authorization_valid
        or requested_provider not in operator.authorization_providers
    ):
        operator = replace(
            operator,
            frozen=True,
            freeze_reason="paid API provider authority is not verified",
            freeze_kind="account_identity_mismatch",
        )
    trusted_limits = _trusted_checkout_limits()
    per_job = _environment_limit("per_job", trusted_limits["per_job"])
    daily = _environment_limit("daily", trusted_limits["daily"])
    weekly = _environment_limit("weekly", trusted_limits["weekly"])
    monthly = _environment_limit("monthly", trusted_limits["monthly"])

    per_job = _DEFAULTS["per_job"] if per_job is None else per_job
    daily = _DEFAULTS["daily"] if daily is None else daily

    monthly_candidates: list[float] = []
    if monthly is not None:
        monthly_candidates.append(monthly)
    if operator.configured:
        monthly_candidates.append(operator.monthly_limit)
    monthly = min(monthly_candidates) if monthly_candidates else 0.0
    monthly = min(monthly, _ABSOLUTE_CEILINGS["monthly"])
    if operator.frozen:
        monthly = 0.0

    weekly = monthly if weekly is None else min(weekly, monthly)
    weekly = min(weekly, _ABSOLUTE_CEILINGS["weekly"])
    daily = min(daily, weekly, _ABSOLUTE_CEILINGS["daily"])
    per_job = min(per_job, daily, _ABSOLUTE_CEILINGS["per_job"])
    return {
        "per_job": per_job,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
    }


def clamp_spend_authority(settings: MutableSpendLimits) -> None:
    """Narrow settings, collapsing every paid limit to zero on policy errors."""
    try:
        caps = resolve_spend_caps()
    except SpendCapConfigurationError:
        caps = {"per_job": 0.0, "daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    settings.max_cost_per_job = min(settings.max_cost_per_job, caps["per_job"])
    settings.daily_limit = min(settings.daily_limit, caps["daily"])
    settings.monthly_limit = min(settings.monthly_limit, caps["monthly"])


def apply_paid_api_freeze(
    document: dict[str, object],
    *,
    reason: str,
    kind: str = "manual",
    freeze_id: str | None = None,
    now: datetime | None = None,
) -> None:
    """Apply a fresh typed freeze to an in-memory budget document."""
    if kind not in _FREEZE_KINDS:
        raise SpendCapConfigurationError("paid API freeze kind is not recognized")
    identifier = freeze_id or f"freeze_{uuid4().hex}"
    if _EVIDENCE_ID_PATTERN.fullmatch(identifier) is None:
        raise SpendCapConfigurationError("paid API freeze ID must be a bounded identifier")
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    document["paid_api_frozen"] = True
    document["freeze_reason"] = reason.strip() or "paid cost safety invariant failed"
    document["freeze_id"] = identifier
    document["freeze_kind"] = kind
    document["frozen_at"] = timestamp.isoformat()
    document.pop("paid_api_authorization", None)


def freeze_paid_api(
    reason: str,
    *,
    path: Path | None = None,
    kind: str = "manual",
    freeze_id: str | None = None,
) -> OperatorBudget:
    """Persist a cross-process paid freeze after a safety invariant breaks."""
    target = path or budget_file_path()
    with spend_policy_lock(target):
        return _freeze_paid_api_unlocked(reason, target=target, kind=kind, freeze_id=freeze_id)


def _freeze_paid_api_unlocked(
    reason: str,
    *,
    target: Path,
    kind: str = "manual",
    freeze_id: str | None = None,
) -> OperatorBudget:
    """Write a paid freeze while the caller holds ``spend_policy_lock``."""
    from deepr.utils.atomic_io import atomic_write_json

    if target.exists():
        try:
            document = _loads_operator_budget(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise SpendCapConfigurationError(f"operator budget is unreadable: {target}") from exc
    else:
        document = {"monthly_limit": 0.0}
    parse_operator_budget(document)
    apply_paid_api_freeze(document, reason=reason, kind=kind, freeze_id=freeze_id)
    parse_operator_budget(document)
    atomic_write_json(target, document, fsync=True)
    return parse_operator_budget(document)


__all__ = [
    "BUDGET_FILE_ENV",
    "OperatorBudget",
    "SpendCapConfigurationError",
    "apply_paid_api_freeze",
    "budget_file_path",
    "clamp_spend_authority",
    "freeze_paid_api",
    "paid_api_provider_scope",
    "parse_operator_budget",
    "read_operator_budget",
    "resolve_spend_caps",
    "spend_policy_lock",
]
