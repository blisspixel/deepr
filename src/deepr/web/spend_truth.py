"""Spend-truth helpers for the dashboard: budget breach and artifact audit.

A 30-job campaign once billed $37.79 while the dashboard showed nothing and
zero report artifacts survived. These helpers give the web API the same
reconciled numbers the CLI approval gate and `deepr costs doctor` use, so
over-budget state and orphaned spend are first-class facts the UI renders
loudly instead of surprises found on a bill.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def verified_cost_estimate(
    estimator: Any,
    prompt: str,
    model: str,
) -> tuple[dict[str, float], float | None, Exception | None]:
    """Build a display estimate and return its conservative admission amount.

    The admission amount is absent unless every estimator bound is finite,
    non-negative, and ordered. Static fallback values remain display-only.
    """
    minimum, maximum, expected = 1.0, 5.0, 2.0
    error: Exception | None = None
    if estimator is None:
        if "o3" in model:
            minimum, maximum, expected = 2.0, 15.0, 5.0
    else:
        try:
            estimate = estimator.estimate_cost(prompt, model)
            minimum = float(estimate.min_cost)
            maximum = float(estimate.max_cost)
            expected = float(estimate.expected_cost)
        except Exception as exc:
            error = exc

    payload = {
        "min_cost": round(minimum, 2),
        "max_cost": round(maximum, 2),
        "expected_cost": round(expected, 2),
    }
    values_valid = all(math.isfinite(value) and value >= 0 for value in (minimum, maximum, expected))
    bounds_valid = minimum <= expected <= maximum
    admission = (
        max(expected, maximum) if estimator is not None and error is None and values_valid and bounds_valid else None
    )
    return payload, admission, error


def _nonnegative_money(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite non-negative number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return number


def paid_estimate_admission(admission_estimate: float, caps: dict[str, float], snapshot: Any) -> dict[str, Any]:
    """Evaluate one estimate against a validated atomic accounting snapshot."""
    estimate = _nonnegative_money(admission_estimate, field="admission estimate")
    checked_caps = {key: _nonnegative_money(caps[key], field=f"{key} cap") for key in caps}
    active_holds = _nonnegative_money(snapshot.active_cost, field="active holds")
    current_exposure = {
        "daily": _nonnegative_money(snapshot.daily_settled_cost, field="daily settled cost") + active_holds,
        "weekly": _nonnegative_money(snapshot.weekly_settled_cost, field="weekly settled cost") + active_holds,
        "monthly": _nonnegative_money(snapshot.monthly_settled_cost, field="monthly settled cost") + active_holds,
    }
    unresolved_holds = snapshot.unresolved_count
    if isinstance(unresolved_holds, bool) or not isinstance(unresolved_holds, int) or unresolved_holds < 0:
        raise ValueError("unresolved hold count must be a non-negative integer")

    reason = None
    if unresolved_holds:
        reason = "Unresolved post-dispatch holds require reconciliation; paid API dispatch is blocked."
    elif checked_caps["monthly"] <= 0:
        reason = "Paid API authority is frozen or unconfigured."
    elif estimate > checked_caps["per_job"]:
        reason = f"Estimated ceiling exceeds per-job limit of ${checked_caps['per_job']:.2f}"
    elif current_exposure["daily"] + estimate > checked_caps["daily"]:
        reason = f"Estimated ceiling would exceed daily limit of ${checked_caps['daily']:.2f}"
    elif current_exposure["weekly"] + estimate > checked_caps["weekly"]:
        reason = f"Estimated ceiling would exceed weekly limit of ${checked_caps['weekly']:.2f}"
    elif current_exposure["monthly"] + estimate > checked_caps["monthly"]:
        reason = f"Estimated ceiling would exceed monthly limit of ${checked_caps['monthly']:.2f}"

    return {
        "allowed": reason is None,
        "reason": reason,
        "active_holds": active_holds,
        "exposure": current_exposure,
        "effective_caps": checked_caps,
        "unresolved_holds": unresolved_holds,
    }


def cost_exposure_snapshot(*, now: datetime | None = None) -> dict[str, Any]:
    """Return one fail-closed read model for dashboard money state.

    Settled cost comes from one strict ledger snapshot. Active durable holds
    are included in exposure so accepted work cannot disappear until its bill
    settles. Policy and holds are read fresh on every request, which keeps CLI,
    MCP, worker, and dashboard changes visible without restarting the web app.
    """
    from deepr.core.cost_caps import read_operator_budget, resolve_spend_caps
    from deepr.experts.research_reservation_store import ResearchReservationStore

    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("cost exposure timestamp must include a UTC offset")
    current = current.astimezone(UTC)
    operator = read_operator_budget()
    caps = resolve_spend_caps(operator_budget=operator)
    snapshot = ResearchReservationStore().exposure_snapshot(now=current)
    settled = {
        "daily": snapshot.daily_settled_cost,
        "weekly": snapshot.weekly_settled_cost,
        "monthly": snapshot.monthly_settled_cost,
        "total": snapshot.total_settled_cost,
    }
    active_holds = snapshot.active_cost
    exposure = {
        "daily": settled["daily"] + active_holds,
        "weekly": settled["weekly"] + active_holds,
        "monthly": settled["monthly"] + active_holds,
    }
    remaining = {period: max(0.0, caps[period] - exposure[period]) for period in ("daily", "weekly", "monthly")}
    paid_api_frozen = operator.frozen or caps["monthly"] <= 0
    freeze_reason = operator.freeze_reason
    if paid_api_frozen and not freeze_reason:
        freeze_reason = (
            "paid API budget is not configured"
            if not operator.configured
            else "effective monthly paid API ceiling is $0"
        )

    return {
        "settled": settled,
        "active_holds": active_holds,
        "unresolved_holds": snapshot.unresolved_count,
        "unresolved_exposure": snapshot.unresolved_cost,
        "exposure": exposure,
        "effective_caps": caps,
        "remaining": remaining,
        "budget_monthly_limit": operator.monthly_limit if operator.configured else 0.0,
        "paid_api_frozen": paid_api_frozen,
        "freeze_reason": freeze_reason,
        "over_budget": exposure["monthly"] > caps["monthly"],
        "authority_exhausted": caps["monthly"] <= 0 or exposure["monthly"] >= caps["monthly"],
        # Flat aliases preserve the existing REST contract while all web
        # consumers migrate to the explicit settled/exposure/caps sections.
        "daily": settled["daily"],
        "weekly": settled["weekly"],
        "monthly": settled["monthly"],
        "total": settled["total"],
        "daily_exposure": exposure["daily"],
        "weekly_exposure": exposure["weekly"],
        "monthly_exposure": exposure["monthly"],
        "per_job_limit": caps["per_job"],
        "daily_limit": caps["daily"],
        "weekly_limit": caps["weekly"],
        "monthly_limit": caps["monthly"],
        "effective_per_job_limit": caps["per_job"],
        "effective_daily_limit": caps["daily"],
        "effective_weekly_limit": caps["weekly"],
        "effective_monthly_limit": caps["monthly"],
    }


def audit_spend_integrity(days: int, reports_root: Path) -> dict:
    """Classify paid ledger events as matched, disposed, or unexplained.

    Same classifier as `deepr costs doctor`. ``orphaned_spend`` is the still-
    unexplained residual (no report artifact and no durable disposition).
    """
    from deepr.cli.commands.costs import _doctor_classify
    from deepr.observability.cost_ledger import CostLedger
    from deepr.observability.spend_dispositions import latest_dispositions_by_event_key

    cutoff = datetime.now(UTC) - timedelta(days=days)
    dir_names = [d.name for d in reports_root.iterdir() if d.is_dir()] if reports_root.exists() else []
    events = CostLedger().with_locked_accounting_events(list)
    matched, disposed, unexplained = _doctor_classify(
        events,
        dir_names,
        cutoff,
        dispositions_by_key=latest_dispositions_by_event_key(),
    )
    return {
        "days": days,
        "matched_spend": round(sum(e["cost_usd"] for e in matched), 2),
        "disposed_spend": round(sum(e["cost_usd"] for e in disposed), 2),
        "orphaned_spend": round(sum(e["cost_usd"] for e in unexplained), 2),
        "unexplained_spend": round(sum(e["cost_usd"] for e in unexplained), 2),
        "matched_events": len(matched),
        "disposed_events": len(disposed),
        "orphaned_events": len(unexplained),
        "unexplained_events": len(unexplained),
    }
