"""Durable compatibility adapter for legacy estimated-cost helper calls."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class SoftCostPathDisabled(RuntimeError):
    """A legacy caller could not obtain durable paid-call accounting."""


@dataclass(frozen=True)
class SoftCostReservation:
    """A marked durable hold settled by the legacy record helper."""

    reservation: Any
    operation_type: str

    def record_cost(self, **kwargs: Any) -> None:
        """Settle reported usage without permitting best-effort ledger loss."""
        from deepr.experts.research_cost_gate import ResearchCostReservation, settle_research_cost

        provider = str(kwargs.get("provider", self.reservation.provider))
        model = str(kwargs.get("model", self.reservation.model))
        attributed = ResearchCostReservation(
            job_id=self.reservation.job_id,
            provider=provider,
            model=model,
            estimated_cost=self.reservation.estimated_cost,
            reservation_id=self.reservation.reservation_id,
            manager=self.reservation.manager,
        )
        settle_research_cost(
            attributed,
            actual_cost=kwargs.get("actual_cost"),
            tokens=int(kwargs.get("tokens_output", 0) or 0),
            request_id=str(kwargs.get("request_id", "") or ""),
            source=str(kwargs.get("source", "experts.cost_admission") or "experts.cost_admission"),
            settlement_metadata={"legacy_operation_type": self.operation_type},
        )


def admit_soft_cost_operation(
    *,
    session_id: str,
    operation_type: str,
    estimated_cost: float,
    require_confirmation: bool = False,
) -> tuple[Any | None, float, str | None]:
    """Durably reserve and mark a legacy paid operation before dispatch."""
    estimate = float(estimated_cost)
    if require_confirmation:
        return None, estimate, "legacy paid helper cannot satisfy interactive confirmation"
    try:
        from deepr.experts.research_cost_gate import (
            mark_research_provider_work,
            refund_research_cost,
            reserve_configured_cost_ceiling,
        )

        reservation = reserve_configured_cost_ceiling(
            job_id=f"legacy-{operation_type}-{uuid.uuid4().hex}",
            provider="pending",
            model="pending",
            max_cost_per_job=estimate,
        )
        try:
            mark_research_provider_work(reservation)
        except BaseException:
            refund_research_cost(reservation, provider_work_did_not_run=True)
            raise
        return SoftCostReservation(reservation, operation_type), estimate, None
    except Exception as exc:
        logger.warning("Cost admission failed closed for %s/%s: %s", session_id, operation_type, exc)
        return None, estimate, f"cost admission unavailable: {exc}"


def record_soft_cost(manager: Any | None, **kwargs: Any) -> None:
    """Settle a legacy durable hold or fail visibly."""
    if not isinstance(manager, SoftCostReservation):
        raise SoftCostPathDisabled("Legacy paid operation has no durable reservation")
    manager.record_cost(**kwargs)


__all__ = [
    "SoftCostPathDisabled",
    "SoftCostReservation",
    "admit_soft_cost_operation",
    "record_soft_cost",
]
