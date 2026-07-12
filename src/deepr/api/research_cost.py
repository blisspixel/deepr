"""Fail-closed API research cost reservation."""

from __future__ import annotations

import os

from deepr.core.costs import CostEstimate
from deepr.experts.research_cost_gate import ResearchCostReservation, reserve_research_cost
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
    limits = {
        "per_job": float(os.getenv("DEEPR_PER_JOB_LIMIT", "5") or "5"),
        "daily": float(os.getenv("DEEPR_DAILY_LIMIT", "10") or "10"),
        "monthly": float(os.getenv("DEEPR_MONTHLY_LIMIT", "20") or "20"),
    }
    if any(limit <= 0 for limit in limits.values()):
        raise ValueError("research cost limits must be positive")
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
        max_monthly_cost=limits["monthly"],
    )
    return estimate, reservation


__all__ = ["reserve_api_research_cost"]
