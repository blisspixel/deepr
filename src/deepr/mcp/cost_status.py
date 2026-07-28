"""Fail-closed cost status projection for the MCP health tool."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def current_cost_status() -> tuple[str, dict[str, Any]]:
    """Return health and canonical spend exposure without guessing on failure."""
    try:
        from deepr.core.cost_caps import read_operator_budget, resolve_spend_caps
        from deepr.experts.research_reservation_store import ResearchReservationStore

        exposure = ResearchReservationStore().exposure_snapshot()
        operator = read_operator_budget()
        caps = resolve_spend_caps(operator_budget=operator)
        summary: dict[str, Any] = {
            "accounting_status": "known",
            "daily_settled": exposure.daily_settled_cost,
            "monthly_settled": exposure.monthly_settled_cost,
            "active_holds": exposure.active_cost,
            "unresolved_holds": exposure.unresolved_count,
            "daily_exposure": exposure.daily_settled_cost + exposure.active_cost,
            "monthly_exposure": exposure.monthly_settled_cost + exposure.active_cost,
            "daily_remaining": max(0.0, caps["daily"] - exposure.daily_settled_cost - exposure.active_cost),
            "monthly_remaining": max(0.0, caps["monthly"] - exposure.monthly_settled_cost - exposure.active_cost),
            "paid_api_blocked": operator.frozen or caps["monthly"] <= 0,
            "freeze_reason": operator.freeze_reason,
        }
        return "healthy", summary
    except Exception:
        logger.error("MCP cost accounting state is unreadable")
        return "degraded", {
            "accounting_status": "unknown",
            "daily_settled": "UNKNOWN",
            "monthly_settled": "UNKNOWN",
            "active_holds": "UNKNOWN",
            "unresolved_holds": "UNKNOWN",
            "daily_exposure": "UNKNOWN",
            "monthly_exposure": "UNKNOWN",
            "daily_remaining": 0.0,
            "monthly_remaining": 0.0,
            "paid_api_blocked": True,
            "freeze_reason": "canonical money state is unreadable",
        }


__all__ = ["current_cost_status"]
