"""Cost-safety helpers for expert portrait generation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class PortraitCostBlocked(ValueError):
    """Raised when portrait generation is denied before provider spend."""


@dataclass(frozen=True)
class PortraitCostReservation:
    effective_provider: str | None
    estimated_cost: float
    manager: Any | None = None
    reservation_id: str = ""


def reserve_portrait_cost(
    *,
    expert_name: str,
    provider: str | None,
    detect_provider: Callable[[], str | None],
    portrait_cost: Callable[[str | None], float],
) -> PortraitCostReservation:
    """Reserve budget for a metered portrait provider before generation."""
    effective_provider = provider or detect_provider()
    estimated_cost = portrait_cost(effective_provider) if effective_provider else 0.0
    if estimated_cost <= 0:
        return PortraitCostReservation(effective_provider=effective_provider, estimated_cost=estimated_cost)

    from deepr.experts.cost_safety import get_cost_safety_manager

    manager = get_cost_safety_manager()
    allowed, reason, needs_confirmation, reservation_id = manager.check_and_reserve(
        session_id=f"portrait_{expert_name}",
        operation_type="portrait_generation",
        estimated_cost=estimated_cost,
        require_confirmation=False,
    )
    if not allowed or needs_confirmation:
        raise PortraitCostBlocked(f"Portrait generation blocked by cost safety: {reason}")
    return PortraitCostReservation(
        effective_provider=effective_provider,
        estimated_cost=estimated_cost,
        manager=manager,
        reservation_id=reservation_id,
    )


def refund_portrait_cost(reservation: PortraitCostReservation) -> None:
    if reservation.manager is not None:
        reservation.manager.refund_reservation(reservation.reservation_id)


def record_portrait_cost(
    *,
    expert_name: str,
    reservation: PortraitCostReservation,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if reservation.manager is None:
        return
    event_metadata = {"expert": expert_name}
    if metadata:
        event_metadata.update(metadata)
    reservation.manager.record_cost(
        session_id=f"portrait_{expert_name}",
        operation_type="portrait_generation",
        actual_cost=reservation.estimated_cost,
        provider=reservation.effective_provider or "auto",
        source=source,
        metadata=event_metadata,
        reservation_id=reservation.reservation_id,
    )
