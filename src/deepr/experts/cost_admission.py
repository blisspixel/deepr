"""Fail-closed soft cost admission for legacy paid helper paths.

Some expert helpers still use ``CostSafetyManager.check_operation`` without the
full durable reserve/mark/settle wrapper. Those preflights must never fail open:
if cost bookkeeping cannot run, paid provider work must not run either.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def admit_soft_cost_operation(
    *,
    session_id: str,
    operation_type: str,
    estimated_cost: float,
    require_confirmation: bool = False,
) -> tuple[Any | None, float, str | None]:
    """Admit one soft-gated paid operation or return a block reason.

    Returns:
        ``(manager, estimate, block_reason)``. ``block_reason`` is non-``None``
        when the caller must not dispatch provider work. Infrastructure
        failures fail closed with a block reason rather than clearing the gate.
    """
    try:
        from deepr.experts.cost_safety import get_cost_safety_manager

        manager = get_cost_safety_manager()
        allowed, reason, _needs_confirm = manager.check_operation(
            session_id=session_id,
            operation_type=operation_type,
            estimated_cost=estimated_cost,
            require_confirmation=require_confirmation,
        )
        if not allowed:
            return manager, float(estimated_cost), reason or "cost operation denied"
        return manager, float(estimated_cost), None
    except Exception as exc:
        logger.warning(
            "Cost admission failed closed for %s/%s: %s",
            session_id,
            operation_type,
            exc,
        )
        return None, float(estimated_cost), f"cost admission unavailable: {exc}"


def record_soft_cost(manager: Any | None, **kwargs: Any) -> None:
    """Best-effort ledger write that never raises into the paid workflow."""
    if manager is None:
        return
    try:
        manager.record_cost(**kwargs)
    except Exception as exc:
        logger.warning(
            "Soft cost recording failed for %s/%s: %s",
            kwargs.get("session_id", ""),
            kwargs.get("operation_type", ""),
            exc,
        )


__all__ = ["admit_soft_cost_operation", "record_soft_cost"]
