"""Value-of-spend gate wiring for expert sync."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.spend_decisions import record_spend_decision
from deepr.experts.spend_policy import SpendDecision, evaluate_spend


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _volatility_from_cadence(cadence_days: float) -> float:
    if cadence_days <= 1:
        return 1.0
    if cadence_days <= 3:
        return 0.85
    if cadence_days <= 7:
        return 0.70
    if cadence_days <= 30:
        return 0.50
    return 0.30


def sync_subscription_benefit_factors(subscription: Any, *, now: datetime | None = None) -> dict[str, float]:
    """Estimate value-gate factors from schedule metadata only.

    These are workflow estimates, not semantic judgments: first syncs close more
    missing context, shorter cadences indicate more volatile topics, and overdue
    subscriptions become more urgent. The topic meaning is intentionally ignored.
    """
    current = now or datetime.now(UTC)
    cadence_days = max(float(getattr(subscription, "cadence_days", 7.0) or 7.0), 0.001)
    last_synced = getattr(subscription, "last_synced", None)
    if last_synced is None:
        urgency = 0.70
        gap_closure = 1.0
    else:
        elapsed_days = max(0.0, (_aware_utc(current) - _aware_utc(last_synced)).total_seconds() / 86_400.0)
        overdue_ratio = elapsed_days / cadence_days
        urgency = _clamp01(max(0.50, overdue_ratio / 2.0))
        gap_closure = 0.60

    return {
        "gap_closure": gap_closure,
        "value": 0.50,
        "urgency": urgency,
        "volatility": _volatility_from_cadence(cadence_days),
    }


def build_sync_spend_decider(
    *,
    expert_name: str,
    capacity_source: str,
    manager: Any | None = None,
    decision_log_path: Path | None = None,
    now: datetime | None = None,
) -> Any:
    """Build a callback for ``ExpertSyncEngine`` to gate metered sync spend."""
    if manager is None:
        from deepr.experts.cost_safety import get_cost_safety_manager

        manager = get_cost_safety_manager()

    def decide(subscription: Any, estimated_cost: float) -> SpendDecision:
        factors = sync_subscription_benefit_factors(subscription, now=now)
        decision = evaluate_spend(
            spent=float(getattr(manager, "monthly_cost", 0.0) or 0.0),
            cap=float(getattr(manager, "max_monthly", 0.0) or 0.0),
            est_cost=estimated_cost,
            **factors,
        )
        record_spend_decision(
            expert_name=expert_name,
            operation="expert_sync",
            topic=str(getattr(subscription, "topic", "") or ""),
            capacity_source=capacity_source,
            estimated_cost=estimated_cost,
            factors=factors,
            decision=decision.to_dict(),
            path=decision_log_path,
            now=now,
        )
        return decision

    return decide
