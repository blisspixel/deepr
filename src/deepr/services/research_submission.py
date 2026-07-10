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

    if not ResearchReservationStore().is_active(reservation.reservation_id):
        error = RuntimeError("research cost reservation closed before provider submission")
        _refund_after_dispatch_failure(reservation, job.id)
        await _mark_dispatch_failed(queue, job.id, error)
        raise error

    if not await queue.claim_submission(job.id):
        error = RuntimeError("research job was cancelled before provider submission")
        _refund_after_dispatch_failure(reservation, job.id)
        raise error

    try:
        stable_request = (
            replace(request, idempotency_key=request.idempotency_key or f"deepr-research-{job.id}")
            if isinstance(request, ResearchRequest)
            else request
        )
        provider_job_id = str(await provider.submit_research(stable_request))
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


__all__ = ["dispatch_reserved_research", "submission_outcome_is_ambiguous"]
