"""Value-of-spend gate wiring for metered gap-fill routes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.spend_decisions import record_spend_decision
from deepr.experts.spend_policy import SpendDecision, evaluate_spend


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _priority_factor(route: Any) -> float:
    priority = float(getattr(route, "priority", 3) or 3)
    return _clamp01(priority / 5.0)


def _expected_value(route: Any) -> float:
    explicit_value = getattr(route, "expected_value", None)
    if explicit_value is not None:
        return _clamp01(float(explicit_value or 0.0))

    estimated_cost = max(float(getattr(route, "estimated_cost", 0.0) or 0.0), 0.001)
    ev_cost_ratio = max(float(getattr(route, "ev_cost_ratio", 0.0) or 0.0), 0.0)
    if ev_cost_ratio > 0.0:
        return _clamp01(ev_cost_ratio * estimated_cost)

    return _priority_factor(route)


def gap_route_benefit_factors(route: Any) -> dict[str, float]:
    """Estimate value-gate factors from route scoring metadata only.

    The gate uses numeric gap-ranking fields already produced upstream. It does
    not inspect topic words or decide whether the gap is semantically important.
    """
    priority = _priority_factor(route)
    return {
        "gap_closure": 1.0,
        "value": _expected_value(route),
        "urgency": priority,
        "volatility": 0.50,
    }


def build_gap_fill_spend_decider(
    *,
    expert_name: str,
    capacity_source: str,
    manager: Any | None = None,
    decision_log_path: Path | None = None,
    now: datetime | None = None,
) -> Any:
    """Build a callback for ``GapFillEngine`` to gate automatic metered spend."""
    if manager is None:
        from deepr.experts.cost_safety import get_cost_safety_manager

        manager = get_cost_safety_manager()

    def decide(route: Any, estimated_cost: float) -> SpendDecision:
        factors = gap_route_benefit_factors(route)
        decision = evaluate_spend(
            spent=float(getattr(manager, "monthly_cost", 0.0) or 0.0),
            cap=float(getattr(manager, "max_monthly", 0.0) or 0.0),
            est_cost=estimated_cost,
            **factors,
        )
        record_spend_decision(
            expert_name=expert_name,
            operation="expert_gap_fill",
            topic=str(getattr(route, "topic", "") or ""),
            capacity_source=capacity_source,
            estimated_cost=estimated_cost,
            factors=factors,
            decision=decision.to_dict(),
            path=decision_log_path,
            now=now or datetime.now(UTC),
        )
        return decision

    return decide
