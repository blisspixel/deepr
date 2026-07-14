"""Durable admission for metered model calls."""

from __future__ import annotations

import asyncio
import inspect
import math
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from types import SimpleNamespace
from typing import NoReturn, TypeVar

from deepr.core.costs import CostEstimator
from deepr.experts.research_cost_gate import (
    ResearchCostReservation,
    refund_research_cost,
    reserve_configured_cost_ceiling,
    settle_research_cost,
)
from deepr.experts.research_reservation_store import ResearchReservationStore

T = TypeVar("T")


class MeteredCallAccountingError(RuntimeError):
    """Raised when durable admission or settlement state cannot be updated."""


def _optional_declared_attribute(value: object, name: str) -> object | None:
    try:
        inspect.getattr_static(value, name)
    except AttributeError:
        return None
    return getattr(value, name, None)


def _usage_tokens(usage: object, primary: str, fallback: str) -> int:
    value = _optional_declared_attribute(usage, primary)
    if value is None:
        value = _optional_declared_attribute(usage, fallback)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Provider usage field {primary} must be a non-negative integer")
    return value


def _response_cost(response: object, model: str) -> tuple[float | None, int]:
    usage = _optional_declared_attribute(response, "usage")
    if usage is None:
        return None, 0
    input_tokens = _usage_tokens(usage, "input_tokens", "prompt_tokens")
    output_tokens = _usage_tokens(usage, "output_tokens", "completion_tokens")
    if input_tokens <= 0 and output_tokens <= 0:
        return None, 0
    actual_cost = CostEstimator.calculate_actual_cost(model, input_tokens, output_tokens)
    if not math.isfinite(actual_cost) or actual_cost < 0:
        raise ValueError("Calculated provider usage cost must be finite and non-negative")
    return actual_cost, output_tokens


def _mark_provider_dispatch(reservation: ResearchCostReservation) -> None:
    ResearchReservationStore().mark_provider_work_may_have_run(reservation.reservation_id)


def _refund_before_dispatch(reservation: ResearchCostReservation) -> None:
    refund_research_cost(reservation)


def _settle_conservative(
    reservation: ResearchCostReservation,
    *,
    source: str,
    reason: str,
    on_settled: Callable[[float], None] | None,
) -> None:
    settle_research_cost(
        reservation,
        actual_cost=None,
        source=f"{source}.conservative",
        actual_cost_reported=False,
        settlement_metadata={"metered_call_settlement_reason": reason},
    )
    if on_settled is not None:
        on_settled(reservation.estimated_cost)


def _settle_response(
    reservation: ResearchCostReservation,
    *,
    actual_cost: float | None,
    output_tokens: int,
    source: str,
    on_settled: Callable[[float], None] | None,
) -> None:
    settle_research_cost(
        reservation,
        actual_cost=actual_cost,
        tokens=output_tokens,
        source=source,
    )
    if on_settled is not None:
        on_settled(actual_cost if actual_cost is not None else reservation.estimated_cost)


def _accounting_error(message: str, cause: BaseException) -> MeteredCallAccountingError:
    error = MeteredCallAccountingError(message)
    error.__cause__ = cause
    return error


def _settle_sync_failure(
    reservation: ResearchCostReservation,
    *,
    source: str,
    reason: str,
    on_settled: Callable[[float], None] | None,
) -> None:
    try:
        _settle_conservative(
            reservation,
            source=source,
            reason=reason,
            on_settled=on_settled,
        )
    except BaseException as accounting_error:
        raise _accounting_error("Post-dispatch metered call cost settlement failed", accounting_error)


def execute_reserved_sync_call(
    *,
    operation_prefix: str,
    provider: str,
    model: str,
    source: str,
    call: Callable[[], T],
    max_cost_per_job: float | None = None,
    on_settled: Callable[[float], None] | None = None,
) -> T:
    """Run one metered call under a cross-process ceiling and settle its usage."""
    job_id = f"{operation_prefix}-{uuid.uuid4().hex}"
    try:
        reservation = reserve_configured_cost_ceiling(
            job_id=job_id,
            provider=provider,
            model=model,
            max_cost_per_job=max_cost_per_job,
        )
    except ValueError:
        raise
    except Exception as exc:
        raise MeteredCallAccountingError("Metered call cost reservation failed") from exc

    try:
        _mark_provider_dispatch(reservation)
    except BaseException as mark_error:
        try:
            _refund_before_dispatch(reservation)
        except BaseException as refund_error:
            raise _accounting_error("Metered call dispatch mark and refund failed", refund_error)
        raise _accounting_error("Metered call dispatch mark failed", mark_error)

    try:
        response = call()
    except BaseException:
        _settle_sync_failure(
            reservation,
            source=source,
            reason="provider_call_failed",
            on_settled=on_settled,
        )
        raise

    try:
        actual_cost, output_tokens = _response_cost(response, model)
    except BaseException:
        _settle_sync_failure(
            reservation,
            source=source,
            reason="malformed_or_unpriceable_usage",
            on_settled=on_settled,
        )
        raise

    try:
        _settle_response(
            reservation,
            actual_cost=actual_cost,
            output_tokens=output_tokens,
            source=source,
            on_settled=on_settled,
        )
    except BaseException as exc:
        raise _accounting_error("Metered call cost settlement failed", exc)
    return response


async def _finish_thread_task(task: asyncio.Task[T], cancellation: asyncio.CancelledError) -> T:
    repeated_cancellations = 0
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            repeated_cancellations += 1
    if repeated_cancellations:
        cancellation.__dict__["metered_call_repeated_cancellations"] = repeated_cancellations
    return task.result()


def _attach_accounting_failure(
    cancellation: asyncio.CancelledError,
    *,
    stage: str,
    error: BaseException,
) -> None:
    accounting_error = _accounting_error(f"Metered call {stage} failed during cancellation", error)
    cancellation.__dict__["metered_call_accounting_error"] = accounting_error
    cancellation.__dict__["metered_call_accounting_stage"] = stage
    cancellation.add_note(f"Metered call {stage} failed while cancellation was pending.")


async def _refund_after_cancellation(
    reservation: ResearchCostReservation,
    cancellation: asyncio.CancelledError,
) -> bool:
    task = asyncio.create_task(
        asyncio.to_thread(_refund_before_dispatch, reservation),
        name=f"metered-call-refund-{reservation.job_id}",
    )
    try:
        await _finish_thread_task(task, cancellation)
    except BaseException as error:
        _attach_accounting_failure(cancellation, stage="predispatch refund", error=error)
        return False
    return True


async def _reserve_async(
    *,
    job_id: str,
    provider: str,
    model: str,
    max_cost_per_job: float | None,
) -> ResearchCostReservation:
    task = asyncio.create_task(
        asyncio.to_thread(
            reserve_configured_cost_ceiling,
            job_id=job_id,
            provider=provider,
            model=model,
            max_cost_per_job=max_cost_per_job,
        ),
        name=f"metered-call-reserve-{job_id}",
    )
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            reservation = await _finish_thread_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage="reservation", error=error)
        else:
            cleaned = await _refund_after_cancellation(
                reservation,
                cancellation,
            )
            cancellation.__dict__["metered_call_predispatch_reservation_cleaned"] = cleaned
        raise


async def _mark_dispatch_async(reservation: ResearchCostReservation) -> None:
    task = asyncio.create_task(
        asyncio.to_thread(_mark_provider_dispatch, reservation),
        name=f"metered-call-dispatch-mark-{reservation.job_id}",
    )
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_thread_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage="dispatch mark", error=error)
        cleaned = await _refund_after_cancellation(
            reservation,
            cancellation,
        )
        cancellation.__dict__["metered_call_predispatch_reservation_cleaned"] = cleaned
        raise


async def _refund_async(reservation: ResearchCostReservation) -> None:
    task = asyncio.create_task(
        asyncio.to_thread(_refund_before_dispatch, reservation),
        name=f"metered-call-refund-{reservation.job_id}",
    )
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_thread_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage="predispatch refund", error=error)
        raise


async def _settle_after_async_error(
    reservation: ResearchCostReservation,
    *,
    source: str,
    reason: str,
    on_settled: Callable[[float], None] | None,
    operation_error: BaseException,
) -> NoReturn:
    task = asyncio.create_task(
        asyncio.to_thread(
            _settle_conservative,
            reservation,
            source=source,
            reason=reason,
            on_settled=on_settled,
        ),
        name=f"metered-call-conservative-settle-{reservation.job_id}",
    )
    if isinstance(operation_error, asyncio.CancelledError):
        try:
            await _finish_thread_task(task, operation_error)
        except BaseException as error:
            _attach_accounting_failure(operation_error, stage="conservative settlement", error=error)
        raise operation_error
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_thread_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage="conservative settlement", error=error)
        cancellation.__dict__["metered_call_interrupted_error_type"] = type(operation_error).__name__
        cancellation.add_note("Cancellation replaced a metered call error after conservative settlement started.")
        raise
    except BaseException as error:
        raise _accounting_error("Post-dispatch metered call cost settlement failed", error)
    raise operation_error


async def _settle_response_async(
    reservation: ResearchCostReservation,
    *,
    actual_cost: float | None,
    output_tokens: int,
    source: str,
    on_settled: Callable[[float], None] | None,
) -> None:
    task = asyncio.create_task(
        asyncio.to_thread(
            _settle_response,
            reservation,
            actual_cost=actual_cost,
            output_tokens=output_tokens,
            source=source,
            on_settled=on_settled,
        ),
        name=f"metered-call-settle-{reservation.job_id}",
    )
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_thread_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage="settlement", error=error)
        raise
    except BaseException as error:
        raise _accounting_error("Metered call cost settlement failed", error)


async def execute_reserved_async_call(
    *,
    operation_prefix: str,
    provider: str,
    model: str,
    source: str,
    call: Callable[[], Awaitable[T]],
    max_cost_per_job: float | None = None,
    on_settled: Callable[[float], None] | None = None,
) -> T:
    """Run one async metered call under a durable ceiling and settle usage."""
    job_id = f"{operation_prefix}-{uuid.uuid4().hex}"
    try:
        reservation = await _reserve_async(
            job_id=job_id,
            provider=provider,
            model=model,
            max_cost_per_job=max_cost_per_job,
        )
    except asyncio.CancelledError:
        raise
    except ValueError:
        raise
    except Exception as exc:
        raise MeteredCallAccountingError("Metered call cost reservation failed") from exc

    try:
        await _mark_dispatch_async(reservation)
    except asyncio.CancelledError:
        raise
    except BaseException as mark_error:
        try:
            await _refund_async(reservation)
        except asyncio.CancelledError:
            raise
        except BaseException as refund_error:
            raise _accounting_error("Metered call dispatch mark and refund failed", refund_error)
        raise _accounting_error("Metered call dispatch mark failed", mark_error)

    try:
        response = await call()
    except BaseException as operation_error:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason="provider_call_cancelled"
            if isinstance(operation_error, asyncio.CancelledError)
            else "provider_call_failed",
            on_settled=on_settled,
            operation_error=operation_error,
        )

    try:
        actual_cost, output_tokens = _response_cost(response, model)
    except BaseException as usage_error:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason="malformed_or_unpriceable_usage",
            on_settled=on_settled,
            operation_error=usage_error,
        )

    await _settle_response_async(
        reservation,
        actual_cost=actual_cost,
        output_tokens=output_tokens,
        source=source,
        on_settled=on_settled,
    )
    return response


async def _reserve_and_mark_async(
    *,
    job_id: str,
    provider: str,
    model: str,
    max_cost_per_job: float | None,
) -> ResearchCostReservation:
    try:
        reservation = await _reserve_async(
            job_id=job_id,
            provider=provider,
            model=model,
            max_cost_per_job=max_cost_per_job,
        )
    except asyncio.CancelledError:
        raise
    except ValueError:
        raise
    except Exception as exc:
        raise MeteredCallAccountingError("Metered call cost reservation failed") from exc
    try:
        await _mark_dispatch_async(reservation)
    except asyncio.CancelledError:
        raise
    except BaseException as mark_error:
        try:
            await _refund_async(reservation)
        except asyncio.CancelledError:
            raise
        except BaseException as refund_error:
            raise _accounting_error("Metered call dispatch mark and refund failed", refund_error)
        raise _accounting_error("Metered call dispatch mark failed", mark_error)
    return reservation


async def _settle_stream_usage_async(
    reservation: ResearchCostReservation,
    *,
    model: str,
    source: str,
    final_usage: object | None,
    on_settled: Callable[[float], None] | None,
) -> None:
    if final_usage is None:
        await asyncio.to_thread(
            _settle_conservative,
            reservation,
            source=source,
            reason="stream_missing_usage",
            on_settled=on_settled,
        )
        return
    try:
        actual_cost, output_tokens = _response_cost(SimpleNamespace(usage=final_usage), model)
    except BaseException:
        await asyncio.to_thread(
            _settle_conservative,
            reservation,
            source=source,
            reason="malformed_or_unpriceable_usage",
            on_settled=on_settled,
        )
        return
    if actual_cost is None and output_tokens <= 0:
        await asyncio.to_thread(
            _settle_conservative,
            reservation,
            source=source,
            reason="stream_missing_usage",
            on_settled=on_settled,
        )
        return
    await _settle_response_async(
        reservation,
        actual_cost=actual_cost,
        output_tokens=output_tokens,
        source=source,
        on_settled=on_settled,
    )


async def execute_reserved_async_stream(
    *,
    operation_prefix: str,
    provider: str,
    model: str,
    source: str,
    events: Callable[[], AsyncIterator[tuple[T, object | None]]],
    max_cost_per_job: float | None = None,
    on_settled: Callable[[float], None] | None = None,
) -> AsyncIterator[T]:
    """Stream one metered call under durable admission and settle final usage.

    ``events`` yields ``(item, usage)`` pairs. The last non-``None`` usage wins
    for settlement. If the stream ends without usable usage, the held ceiling is
    consumed conservatively after dispatch was marked.
    """
    reservation = await _reserve_and_mark_async(
        job_id=f"{operation_prefix}-{uuid.uuid4().hex}",
        provider=provider,
        model=model,
        max_cost_per_job=max_cost_per_job,
    )

    final_usage: object | None = None
    try:
        async for item, usage in events():
            if usage is not None:
                final_usage = usage
            yield item
    except BaseException as operation_error:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason="provider_call_cancelled"
            if isinstance(operation_error, asyncio.CancelledError)
            else "provider_call_failed",
            on_settled=on_settled,
            operation_error=operation_error,
        )

    await _settle_stream_usage_async(
        reservation,
        model=model,
        source=source,
        final_usage=final_usage,
        on_settled=on_settled,
    )


async def execute_reserved_fixed_cost_async_call(
    *,
    operation_prefix: str,
    provider: str,
    model: str,
    source: str,
    max_cost_per_job: float,
    call: Callable[[], Awaitable[T]],
    cost_from_result: Callable[[T], float],
    on_settled: Callable[[float], None] | None = None,
) -> T:
    """Run one non-token-priced work unit under durable reserve/mark/settle.

    Skill tools and similar side effects have tier or fixed estimates rather
    than provider token usage. ``cost_from_result`` returns the amount to
    settle after success (clamped to ``[0, hold]``). Exceptions after dispatch
    still consume the full hold conservatively.
    """
    if isinstance(max_cost_per_job, bool) or not isinstance(max_cost_per_job, (int, float)):
        raise ValueError("max_cost_per_job must be a positive finite number")
    ceiling = float(max_cost_per_job)
    if not math.isfinite(ceiling) or ceiling <= 0:
        raise ValueError("max_cost_per_job must be a positive finite number")

    reservation = await _reserve_and_mark_async(
        job_id=f"{operation_prefix}-{uuid.uuid4().hex}",
        provider=provider,
        model=model,
        max_cost_per_job=ceiling,
    )

    try:
        result = await call()
    except BaseException as operation_error:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason="provider_call_cancelled"
            if isinstance(operation_error, asyncio.CancelledError)
            else "provider_call_failed",
            on_settled=on_settled,
            operation_error=operation_error,
        )

    try:
        raw_cost = float(cost_from_result(result))
    except BaseException as cost_error:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason="malformed_or_unpriceable_usage",
            on_settled=on_settled,
            operation_error=cost_error,
        )

    if not math.isfinite(raw_cost) or raw_cost < 0:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason="malformed_or_unpriceable_usage",
            on_settled=on_settled,
            operation_error=ValueError("cost_from_result must return a finite non-negative number"),
        )

    settled = min(float(reservation.estimated_cost), raw_cost)
    await _settle_response_async(
        reservation,
        actual_cost=settled,
        output_tokens=0,
        source=source,
        on_settled=on_settled,
    )
    return result


__all__ = [
    "MeteredCallAccountingError",
    "execute_reserved_async_call",
    "execute_reserved_async_stream",
    "execute_reserved_fixed_cost_async_call",
    "execute_reserved_sync_call",
]
