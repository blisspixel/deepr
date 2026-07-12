"""Shared reserved dispatch for provider-backed research jobs."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from deepr.experts.research_cost_gate import (
    ResearchCostReservation,
    refund_research_cost,
    settle_research_cost,
)
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.providers.base import ResearchRequest
from deepr.queue.base import JobStatus, ResearchJob

logger = logging.getLogger(__name__)


class ResearchDispatchReservationError(RuntimeError):
    """A queued job cannot prove an active, job-owned cost reservation."""

    def __init__(self, message: str, *, code: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _refund_after_dispatch_failure(reservation: ResearchCostReservation, job_id: str) -> None:
    try:
        refund_research_cost(reservation)
    except Exception:
        logger.exception("Could not refund failed research dispatch %s", job_id)


def _settle_uncertain_dispatch(
    reservation: ResearchCostReservation,
    *,
    request_id: str,
    source: str,
) -> None:
    try:
        settle_research_cost(
            reservation,
            actual_cost=None,
            request_id=request_id,
            source=source,
        )
    except Exception:
        logger.exception("Could not settle uncertain research dispatch %s", reservation.job_id)


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


async def _mark_dispatch_failed(queue: Any, job_id: str, error: Exception) -> None:
    """Best-effort terminal state for a job already persisted in the queue."""
    try:
        await queue.update_status(job_id=job_id, status=JobStatus.FAILED, error=str(error))
    except Exception:
        logger.exception("Could not persist dispatch failure for research job %s", job_id)


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


async def _submit_reserved_provider_job(
    *,
    queue: Any,
    provider: Any,
    request: Any,
    reservation: ResearchCostReservation,
    job: ResearchJob,
) -> str:
    stable_request = (
        replace(request, idempotency_key=request.idempotency_key or f"deepr-research-{job.id}")
        if isinstance(request, ResearchRequest)
        else request
    )
    try:
        return str(await provider.submit_research(stable_request))
    except Exception as exc:
        if submission_outcome_is_ambiguous(exc):
            _settle_uncertain_dispatch(
                reservation,
                request_id=f"deepr-research-{job.id}",
                source="services.dispatch_reserved_research.ambiguous_submission",
            )
        else:
            _refund_after_dispatch_failure(reservation, job.id)
        await _mark_dispatch_failed(queue, job.id, exc)
        raise


async def dispatch_reserved_research(
    *,
    queue: Any,
    provider: Any,
    job: ResearchJob,
    request: Any,
    reservation: ResearchCostReservation,
) -> str:
    """Enqueue and dispatch a reserved job without releasing accepted spend."""
    try:
        await queue.enqueue(job)
    except Exception as exc:
        _refund_after_dispatch_failure(reservation, job.id)
        await _mark_dispatch_failed(queue, job.id, exc)
        raise

    try:
        _, reservation = await restore_active_queued_reservation(
            queue=queue,
            job_id=job.id,
            expected=reservation,
            queued_job=job,
        )
    except ResearchDispatchReservationError as error:
        if error.retryable:
            raise
        _refund_after_dispatch_failure(reservation, job.id)
        raise error

    if not await queue.claim_submission(job.id):
        claim_error = RuntimeError("research job was cancelled before provider submission")
        _refund_after_dispatch_failure(reservation, job.id)
        raise claim_error

    provider_job_id = await _submit_reserved_provider_job(
        queue=queue,
        provider=provider,
        request=request,
        reservation=reservation,
        job=job,
    )

    try:
        updated = await queue.update_status(
            job_id=job.id,
            status=JobStatus.PROCESSING,
            provider_job_id=provider_job_id,
        )
        if updated is False:
            raise RuntimeError("queue rejected provider job status update")
    except Exception as exc:
        try:
            cancelled = await provider.cancel_job(provider_job_id)
        except Exception:
            cancelled = False
            logger.exception("Could not cancel accepted provider job %s after queue update failure", provider_job_id)
        if cancelled:
            _refund_after_dispatch_failure(reservation, job.id)
        else:
            _settle_uncertain_dispatch(
                reservation,
                request_id=provider_job_id,
                source="services.dispatch_reserved_research.tracking_failure",
            )
        await _mark_dispatch_failed(queue, job.id, exc)
        raise
    return provider_job_id


__all__ = [
    "ResearchDispatchReservationError",
    "dispatch_reserved_research",
    "restore_active_queued_reservation",
    "submission_outcome_is_ambiguous",
]
