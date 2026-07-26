"""Fail-closed API research cost reservation."""

from __future__ import annotations

from deepr.core.cost_caps import resolve_spend_caps
from deepr.core.costs import CostEstimate
from deepr.experts.cost_safety import CostSafetyManager
from deepr.experts.research_cost_gate import ResearchCostReservation, reserve_research_cost
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.observability.cost_ledger import CostLedger
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.services.research_bounds import bounded_research_cost_estimate


def reserve_api_research_cost(
    *,
    job_id: str,
    provider: str,
    prompt: str,
    model: str,
    enable_web_search: bool,
) -> tuple[CostEstimate, ResearchCostReservation]:
    """Estimate and atomically reserve one REST API research job."""
    # Documented DEEPR_MAX_COST_PER_* caps and the legacy DEEPR_*_LIMIT names
    # are both honored; the tighter bound wins and malformed values never
    # fall open (see core/cost_caps.py).
    limits = resolve_spend_caps()
    bounded_request = ResearchRequest(
        prompt=prompt,
        model=model,
        system_message="You are a research assistant. Provide comprehensive, citation-backed analysis.",
        tools=[ToolConfig(type="web_search_preview")] if enable_web_search else [],
    )
    estimate = bounded_research_cost_estimate(request=bounded_request, provider=provider)
    reservation = reserve_research_cost(
        job_id=job_id,
        provider=provider,
        model=model,
        estimate=estimate,
        max_cost_per_job=limits["per_job"],
        max_daily_cost=limits["daily"],
        max_weekly_cost=limits["weekly"],
        max_monthly_cost=limits["monthly"],
    )
    return estimate, reservation


def build_api_cost_summary(
    *,
    queue_reported_cost: float,
    total_jobs: int,
    completed_jobs: int,
) -> dict[str, float | int | str]:
    """Build a REST cost summary from canonical spend and reservation state."""
    spending = CostSafetyManager().get_spending_summary()
    active_reserved = ResearchReservationStore().active_cost()
    monthly = spending["monthly"]
    return {
        "daily": spending["daily"]["spent"],
        "weekly": spending["weekly"]["spent"],
        "monthly": monthly["spent"],
        "total": CostLedger().get_total_cost(),
        "daily_limit": spending["daily"]["limit"],
        "weekly_limit": spending["weekly"]["limit"],
        "monthly_limit": monthly["limit"],
        "active_reserved": active_reserved,
        "monthly_headroom": max(0.0, monthly["limit"] - monthly["spent"] - active_reserved),
        "queue_reported_cost": queue_reported_cost,
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "avg_cost_per_job": queue_reported_cost / completed_jobs if completed_jobs else 0,
        "currency": "USD",
    }


__all__ = ["build_api_cost_summary", "reserve_api_research_cost"]
