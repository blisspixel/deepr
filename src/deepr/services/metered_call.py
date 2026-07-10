"""Durable admission for synchronous metered model calls."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TypeVar

from deepr.core.costs import CostEstimator
from deepr.experts.research_cost_gate import (
    refund_research_cost,
    reserve_configured_cost_ceiling,
    settle_research_cost,
)
from deepr.services.research_submission import submission_outcome_is_ambiguous

T = TypeVar("T")


def _response_cost(response: object, model: str) -> tuple[float | None, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, 0
    input_tokens = int(getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", 0) or 0)
    if input_tokens <= 0 and output_tokens <= 0:
        return None, 0
    return CostEstimator.calculate_actual_cost(model, input_tokens, output_tokens), output_tokens


def execute_reserved_sync_call(
    *,
    operation_prefix: str,
    provider: str,
    model: str,
    source: str,
    call: Callable[[], T],
) -> T:
    """Run one metered call under a cross-process ceiling and settle its usage."""
    job_id = f"{operation_prefix}-{uuid.uuid4().hex}"
    reservation = reserve_configured_cost_ceiling(
        job_id=job_id,
        provider=provider,
        model=model,
    )
    try:
        response = call()
    except Exception as exc:
        if submission_outcome_is_ambiguous(exc):
            settle_research_cost(reservation, actual_cost=None, source=f"{source}.ambiguous")
        else:
            refund_research_cost(reservation)
        raise
    actual_cost, output_tokens = _response_cost(response, model)
    settle_research_cost(
        reservation,
        actual_cost=actual_cost,
        tokens=output_tokens,
        source=source,
    )
    return response


async def execute_reserved_async_call(
    *,
    operation_prefix: str,
    provider: str,
    model: str,
    source: str,
    call: Callable[[], Awaitable[T]],
) -> T:
    """Run one async metered call under a durable ceiling and settle usage."""
    job_id = f"{operation_prefix}-{uuid.uuid4().hex}"
    reservation = reserve_configured_cost_ceiling(
        job_id=job_id,
        provider=provider,
        model=model,
    )
    try:
        response = await call()
    except Exception as exc:
        if submission_outcome_is_ambiguous(exc):
            settle_research_cost(reservation, actual_cost=None, source=f"{source}.ambiguous")
        else:
            refund_research_cost(reservation)
        raise
    actual_cost, output_tokens = _response_cost(response, model)
    settle_research_cost(
        reservation,
        actual_cost=actual_cost,
        tokens=output_tokens,
        source=source,
    )
    return response


__all__ = ["execute_reserved_async_call", "execute_reserved_sync_call"]
