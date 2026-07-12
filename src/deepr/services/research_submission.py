"""Shared reserved dispatch for provider-backed research jobs."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any, NoReturn, TypeVar

from deepr.experts.research_cost_gate import (
    ResearchCostReservation,
    mark_research_provider_work,
    refund_research_cost,
    settle_research_cost,
)
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.providers.base import ResearchRequest
from deepr.queue.base import JobStatus, ResearchJob
from deepr.services.research_bounds import (
    ResearchRequestBoundsError,
    bounded_research_cost_estimate,
    request_bound_metadata,
    validate_persisted_request_bounds,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class ResearchDispatchReservationError(RuntimeError):
    """A queued job cannot prove an active, job-owned cost reservation."""

    def __init__(self, message: str, *, code: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ResearchDispatchAccountingError(RuntimeError):
    """Durable research accounting could not be completed safely."""


async def _finish_task(task: asyncio.Task[T], cancellation: asyncio.CancelledError) -> T:
    repeated = 0
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            repeated += 1
    if repeated:
        cancellation.__dict__["research_dispatch_repeated_cancellations"] = repeated
    return task.result()


def _attach_accounting_failure(
    cancellation: asyncio.CancelledError,
    *,
    stage: str,
    error: BaseException,
) -> None:
    accounting_error = ResearchDispatchAccountingError(
        f"Research dispatch {stage} failed while cancellation was pending"
    )
    accounting_error.__cause__ = error
    cancellation.__dict__["research_dispatch_accounting_error"] = accounting_error
    cancellation.__dict__["research_dispatch_accounting_stage"] = stage
    cancellation.add_note(f"Research dispatch {stage} failed while cancellation was pending.")


async def _cost_call(
    function: Any,
    reservation: ResearchCostReservation,
    *,
    stage: str,
) -> None:
    task = asyncio.create_task(
        asyncio.to_thread(function, reservation),
        name=f"research-{stage}-{reservation.job_id}",
    )
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage=stage, error=error)
        raise
    except BaseException as error:
        raise ResearchDispatchAccountingError(f"Research dispatch {stage} failed") from error


async def _cost_call_during_cancellation(
    function: Any,
    reservation: ResearchCostReservation,
    cancellation: asyncio.CancelledError,
    *,
    stage: str,
) -> bool:
    task = asyncio.create_task(
        asyncio.to_thread(function, reservation),
        name=f"research-{stage}-{reservation.job_id}",
    )
    try:
        await _finish_task(task, cancellation)
    except BaseException as error:
        _attach_accounting_failure(cancellation, stage=stage, error=error)
        return False
    return True


def _settle_conservative_sync(
    reservation: ResearchCostReservation,
    *,
    request_id: str,
    source: str,
    reason: str,
) -> None:
    settle_research_cost(
        reservation,
        actual_cost=None,
        request_id=request_id,
        source=source,
        actual_cost_reported=False,
        settlement_metadata={"research_dispatch_settlement_reason": reason},
    )


async def _settle_after_provider_error(
    reservation: ResearchCostReservation,
    *,
    request_id: str,
    source: str,
    reason: str,
    operation_error: BaseException,
) -> NoReturn:
    task = asyncio.create_task(
        asyncio.to_thread(
            _settle_conservative_sync,
            reservation,
            request_id=request_id,
            source=source,
            reason=reason,
        ),
        name=f"research-conservative-settle-{reservation.job_id}",
    )
    if isinstance(operation_error, asyncio.CancelledError):
        try:
            await _finish_task(task, operation_error)
        except BaseException as error:
            _attach_accounting_failure(operation_error, stage="conservative settlement", error=error)
        raise operation_error
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage="conservative settlement", error=error)
        cancellation.__dict__["research_dispatch_interrupted_error_type"] = type(operation_error).__name__
        raise
    except BaseException as error:
        raise ResearchDispatchAccountingError("Post-dispatch research settlement failed") from error
    raise operation_error


def submission_outcome_is_ambiguous(error: Exception) -> bool:
    """Return whether a provider may have accepted work before the error."""
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = type(current).__name__.lower()
        if "timeout" in name or "connection" in name:
            return True
        original = getattr(current, "original_error", None)
        current = original if isinstance(original, BaseException) else current.__cause__
    return False


async def _mark_dispatch_failed(queue: Any, job_id: str, error: BaseException) -> None:
    """Best-effort terminal state for a job already persisted in the queue."""
    try:
        await queue.update_status(job_id=job_id, status=JobStatus.FAILED, error=str(error))
    except Exception:
        logger.exception("Could not persist dispatch failure for research job %s", job_id)


async def _mark_dispatch_failed_during_cancellation(
    queue: Any,
    job_id: str,
    error: BaseException,
    cancellation: asyncio.CancelledError,
) -> None:
    task = asyncio.create_task(
        queue.update_status(job_id=job_id, status=JobStatus.FAILED, error=str(error) or type(error).__name__),
        name=f"research-queue-failure-{job_id}",
    )
    try:
        await _finish_task(task, cancellation)
    except BaseException as queue_error:
        cancellation.__dict__["research_dispatch_queue_error"] = queue_error
        cancellation.add_note("Research queue terminal-state write failed while cancellation was pending.")


def _stable_request(request: Any, job_id: str) -> ResearchRequest:
    if not isinstance(request, ResearchRequest):
        raise ResearchRequestBoundsError(
            "Provider-backed research requires a typed ResearchRequest with explicit ceilings",
            code="research_request_bounds_missing",
        )
    return replace(request, idempotency_key=request.idempotency_key or f"deepr-research-{job_id}")


def _validate_reservation_envelope(
    request: ResearchRequest,
    reservation: ResearchCostReservation,
) -> None:
    if request.model != reservation.model:
        raise ResearchRequestBoundsError(
            "Research request model does not match its durable reservation",
            code="research_reservation_model_mismatch",
        )
    envelope = bounded_research_cost_estimate(request=request, provider=reservation.provider)
    if reservation.estimated_cost + 1e-12 < envelope.max_cost:
        raise ResearchRequestBoundsError(
            f"Research reservation ${reservation.estimated_cost:.6f} does not cover the "
            f"${envelope.max_cost:.6f} request envelope",
            code="research_reservation_envelope_too_small",
        )


async def _mark_provider_dispatch(reservation: ResearchCostReservation) -> None:
    try:
        await _cost_call(mark_research_provider_work, reservation, stage="provider dispatch mark")
    except asyncio.CancelledError as cancellation:
        cleaned = await _cost_call_during_cancellation(
            refund_research_cost,
            reservation,
            cancellation,
            stage="predispatch refund",
        )
        cancellation.__dict__["research_dispatch_predispatch_reservation_cleaned"] = cleaned
        raise
    except BaseException as mark_error:
        try:
            await _cost_call(refund_research_cost, reservation, stage="predispatch refund")
        except BaseException as refund_error:
            raise ResearchDispatchAccountingError("Research dispatch mark and refund failed") from refund_error
        raise ResearchDispatchAccountingError("Research provider dispatch mark failed") from mark_error


async def _refund_predispatch(reservation: ResearchCostReservation) -> None:
    await _cost_call(refund_research_cost, reservation, stage="predispatch refund")


async def _cancel_queued_predispatch(
    *,
    queue: Any,
    job_id: str,
    reservation: ResearchCostReservation,
    cancellation: asyncio.CancelledError,
) -> None:
    task = asyncio.create_task(queue.cancel_queued_submission(job_id), name=f"research-cancel-queued-{job_id}")
    try:
        cancelled = bool(await _finish_task(task, cancellation))
    except BaseException as error:
        cancellation.__dict__["research_dispatch_queue_error"] = error
        cancellation.add_note("Could not determine whether the queued research job was cancelled.")
        return
    if not cancelled:
        cancellation.add_note("Queued research cancellation lost its claim; the durable cost hold remains active.")
        return
    cleaned = await _cost_call_during_cancellation(
        refund_research_cost,
        reservation,
        cancellation,
        stage="queued cancellation refund",
    )
    cancellation.__dict__["research_dispatch_predispatch_reservation_cleaned"] = cleaned


def _reservation_identity(reservation: ResearchCostReservation) -> tuple[str, str, str, float]:
    return (
        reservation.reservation_id,
        reservation.job_id,
        reservation.model,
        reservation.estimated_cost,
    )


async def restore_active_queued_reservation(
    *,
    queue: Any,
    job_id: str,
    expected: ResearchCostReservation,
    store: ResearchReservationStore | None = None,
    queued_job: ResearchJob | None = None,
) -> tuple[ResearchJob, ResearchCostReservation]:
    """Restore and verify the exact persisted hold before a provider POST.

    Deterministic metadata or ownership failures are terminal and persisted.
    A reservation-store read failure is retryable, so the job stays queued and
    its possible active hold remains intact.
    """
    job = queued_job or await queue.get_job(job_id)
    if job is None:
        raise ResearchDispatchReservationError(
            "research queue snapshot missing before provider submission",
            code="queue_snapshot_missing",
            retryable=False,
        )
    if job.status != JobStatus.QUEUED:
        raise ResearchDispatchReservationError(
            "research job is not queued for provider submission",
            code="queue_state_invalid",
            retryable=False,
        )

    from deepr.experts.research_cost_gate import restore_research_cost_reservation

    restored = restore_research_cost_reservation(
        job_id=job.id,
        metadata=job.metadata,
        provider=job.provider,
        model=job.model,
        manager=expected.manager,
    )
    if restored is None:
        error = ResearchDispatchReservationError(
            "research cost reservation metadata missing before provider submission",
            code="reservation_metadata_missing",
            retryable=False,
        )
        await _mark_dispatch_failed(queue, job.id, error)
        raise error

    expected_identity = _reservation_identity(expected)
    restored_identity = _reservation_identity(restored)
    if (
        restored_identity != expected_identity
        or restored.provider != expected.provider
        or job.provider != restored.provider
        or job.model != restored.model
    ):
        error = ResearchDispatchReservationError(
            "research cost reservation does not match the queued job",
            code="reservation_mismatch",
            retryable=False,
        )
        await _mark_dispatch_failed(queue, job.id, error)
        raise error

    try:
        is_active = (store or ResearchReservationStore()).is_active_for_job(
            reservation_id=restored.reservation_id,
            job_id=job.id,
            reserved_cost=restored.estimated_cost,
        )
    except Exception as exc:
        raise ResearchDispatchReservationError(
            "research reservation state is temporarily unavailable; job remains queued",
            code="reservation_store_unavailable",
            retryable=True,
        ) from exc
    if not is_active:
        error = ResearchDispatchReservationError(
            "research cost reservation is missing or closed before provider submission",
            code="reservation_not_active",
            retryable=False,
        )
        await _mark_dispatch_failed(queue, job.id, error)
        raise error
    return job, restored


async def submit_reserved_provider_research(
    *,
    provider: Any,
    request: ResearchRequest,
    reservation: ResearchCostReservation,
    source: str,
) -> str:
    """Cross one provider boundary under a durable mark and full ceiling."""
    try:
        _validate_reservation_envelope(request, reservation)
    except BaseException:
        await _refund_predispatch(reservation)
        raise
    await _mark_provider_dispatch(reservation)
    try:
        provider_job_id = str(await provider.submit_research(request))
        if not provider_job_id:
            raise RuntimeError("provider returned an empty research job ID")
        return provider_job_id
    except BaseException as error:
        await _settle_after_provider_error(
            reservation,
            request_id=request.idempotency_key,
            source=f"{source}.provider_failure",
            reason=("provider_call_cancelled" if isinstance(error, asyncio.CancelledError) else "provider_call_failed"),
            operation_error=error,
        )


async def _persist_provider_handoff(
    *,
    queue: Any,
    provider: Any,
    job: ResearchJob,
    provider_job_id: str,
    reservation: ResearchCostReservation,
) -> None:
    update_task = asyncio.create_task(
        queue.update_status(
            job_id=job.id,
            status=JobStatus.PROCESSING,
            provider_job_id=provider_job_id,
        ),
        name=f"research-provider-handoff-{job.id}",
    )
    operation_error: BaseException | None = None
    try:
        updated = await asyncio.shield(update_task)
        if updated is False:
            operation_error = RuntimeError("queue rejected provider job status update")
    except asyncio.CancelledError as cancellation:
        try:
            updated = await _finish_task(update_task, cancellation)
        except BaseException as error:
            operation_error = error
        else:
            if updated is not False:
                cancellation.__dict__["research_dispatch_provider_job_id"] = provider_job_id
                cancellation.__dict__["research_dispatch_handoff_persisted"] = True
                raise
            operation_error = RuntimeError("queue rejected provider job status update")
        try:
            cancel_task = asyncio.create_task(
                provider.cancel_job(provider_job_id),
                name=f"research-provider-cancel-{job.id}",
            )
            await _finish_task(cancel_task, cancellation)
        except BaseException as cancel_error:
            cancellation.__dict__["research_dispatch_provider_cancel_error"] = cancel_error
        await _settle_after_provider_error(
            reservation,
            request_id=provider_job_id,
            source="services.dispatch_reserved_research.handoff_cancellation",
            reason="provider_accepted_queue_handoff_cancelled",
            operation_error=cancellation,
        )
    except BaseException as error:
        operation_error = error

    if operation_error is None:
        return
    try:
        await provider.cancel_job(provider_job_id)
    except BaseException:
        logger.exception("Could not cancel accepted provider job %s after queue handoff failure", provider_job_id)
    await _settle_after_provider_error(
        reservation,
        request_id=provider_job_id,
        source="services.dispatch_reserved_research.tracking_failure",
        reason="provider_accepted_queue_handoff_failed",
        operation_error=operation_error,
    )


async def _prepare_queued_dispatch(
    request: Any,
    job: ResearchJob,
    reservation: ResearchCostReservation,
) -> ResearchRequest:
    stable_request = _stable_request(request, job.id)
    try:
        _validate_reservation_envelope(stable_request, reservation)
        job.metadata.update(request_bound_metadata(stable_request))
    except BaseException:
        await _refund_predispatch(reservation)
        raise
    return stable_request


async def _enqueue_reserved_job(
    queue: Any,
    job: ResearchJob,
    reservation: ResearchCostReservation,
) -> None:
    task = asyncio.create_task(queue.enqueue(job), name=f"research-enqueue-{job.id}")
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_task(task, cancellation)
        except BaseException as enqueue_error:
            cancellation.__dict__["research_dispatch_enqueue_error"] = enqueue_error
        await _cancel_queued_predispatch(
            queue=queue,
            job_id=job.id,
            reservation=reservation,
            cancellation=cancellation,
        )
        raise
    except BaseException as error:
        await _refund_predispatch(reservation)
        await _mark_dispatch_failed(queue, job.id, error)
        raise


async def _restore_reserved_job(
    queue: Any,
    job: ResearchJob,
    request: ResearchRequest,
    reservation: ResearchCostReservation,
) -> ResearchCostReservation:
    task = asyncio.create_task(
        restore_active_queued_reservation(
            queue=queue,
            job_id=job.id,
            expected=reservation,
        ),
        name=f"research-restore-reservation-{job.id}",
    )
    try:
        queued_job, restored = await asyncio.shield(task)
        validate_persisted_request_bounds(queued_job.metadata, request)
        return restored
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_task(task, cancellation)
        except BaseException as restore_error:
            cancellation.__dict__["research_dispatch_restore_error"] = restore_error
        await _cancel_queued_predispatch(
            queue=queue,
            job_id=job.id,
            reservation=reservation,
            cancellation=cancellation,
        )
        raise
    except ResearchDispatchReservationError as error:
        if error.retryable:
            raise
        await _refund_predispatch(reservation)
        raise
    except BaseException as error:
        await _refund_predispatch(reservation)
        await _mark_dispatch_failed(queue, job.id, error)
        raise


async def _claim_reserved_job(
    queue: Any,
    job: ResearchJob,
    reservation: ResearchCostReservation,
) -> None:
    task = asyncio.create_task(queue.claim_submission(job.id), name=f"research-claim-{job.id}")
    try:
        claimed = bool(await asyncio.shield(task))
    except asyncio.CancelledError as cancellation:
        try:
            claimed = bool(await _finish_task(task, cancellation))
        except BaseException as claim_error:
            cancellation.__dict__["research_dispatch_claim_error"] = claim_error
            raise
        if claimed:
            await _mark_dispatch_failed_during_cancellation(queue, job.id, cancellation, cancellation)
        cleaned = await _cost_call_during_cancellation(
            refund_research_cost,
            reservation,
            cancellation,
            stage="claimed predispatch refund" if claimed else "lost claim refund",
        )
        cancellation.__dict__["research_dispatch_predispatch_reservation_cleaned"] = cleaned
        raise
    if not claimed:
        await _refund_predispatch(reservation)
        raise RuntimeError("research job was cancelled before provider submission")


async def dispatch_reserved_research(
    *,
    queue: Any,
    provider: Any,
    job: ResearchJob,
    request: Any,
    reservation: ResearchCostReservation,
) -> str:
    """Enqueue and dispatch a reserved job without releasing accepted spend."""
    stable_request = await _prepare_queued_dispatch(request, job, reservation)
    await _enqueue_reserved_job(queue, job, reservation)
    reservation = await _restore_reserved_job(queue, job, stable_request, reservation)
    await _claim_reserved_job(queue, job, reservation)

    try:
        provider_job_id = await submit_reserved_provider_research(
            provider=provider,
            request=stable_request,
            reservation=reservation,
            source="services.dispatch_reserved_research",
        )
    except asyncio.CancelledError as cancellation:
        await _mark_dispatch_failed_during_cancellation(queue, job.id, cancellation, cancellation)
        raise
    except BaseException as exc:
        await _mark_dispatch_failed(queue, job.id, exc)
        raise

    await _persist_provider_handoff(
        queue=queue,
        provider=provider,
        job=job,
        provider_job_id=provider_job_id,
        reservation=reservation,
    )
    return provider_job_id


__all__ = [
    "ResearchDispatchAccountingError",
    "ResearchDispatchReservationError",
    "dispatch_reserved_research",
    "restore_active_queued_reservation",
    "submission_outcome_is_ambiguous",
    "submit_reserved_provider_research",
]
