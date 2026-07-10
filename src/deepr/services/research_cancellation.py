"""Cost-safe cancellation for queued and provider-accepted research jobs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from deepr.experts.research_cost_gate import (
    ResearchCostReservation,
    refund_research_cost,
    restore_research_cost_reservation,
    settle_research_cost,
)
from deepr.queue.base import JobStatus, ResearchJob
from deepr.services.provider_status import provider_exception_name

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResearchCancellationOutcome:
    """Describe whether queue state and cost state were safely closed."""

    queue_cancelled: bool
    cost_closed: bool
    cleanup_closed: bool = True

    @property
    def confirmed(self) -> bool:
        """Return whether provider, queue, and cost state closed safely."""
        return self.queue_cancelled and self.cost_closed and self.cleanup_closed


async def _cancel_accepted_provider_job(provider: Any, provider_job_id: str, job_id: str) -> bool:
    """Cancel accepted provider work without exposing provider-controlled data."""
    if not provider_job_id:
        return True
    if provider is None:
        return False
    try:
        return bool(await provider.cancel_job(provider_job_id))
    except Exception as exc:
        logger.warning(
            "Could not cancel provider job for %s (%s)",
            job_id,
            provider_exception_name(exc),
        )
        return False


async def _close_cancelled_snapshot(
    *,
    queue: Any,
    job: ResearchJob,
    provider: Any,
    default_provider: str,
    reservation: ResearchCostReservation | None,
    source: str,
) -> ResearchCancellationOutcome:
    """Finish cost and cleanup work after a durable cancellation transition."""
    active_reservation = reservation or restore_research_cost_reservation(
        job_id=job.id,
        metadata=job.metadata,
        provider=default_provider,
        model=job.model,
    )
    try:
        provider_prepared = bool(
            job.provider_job_id or job.metadata.get("provider_file_ids") or job.metadata.get("vector_store_id")
        )
        if active_reservation is not None:
            if provider_prepared:
                settle_research_cost(
                    active_reservation,
                    actual_cost=None,
                    request_id=str(job.provider_job_id or ""),
                    source=source,
                )
            else:
                refund_research_cost(active_reservation)
    except Exception as exc:
        logger.warning("Could not close cancellation cost for %s (%s)", job.id, provider_exception_name(exc))
        return ResearchCancellationOutcome(queue_cancelled=True, cost_closed=False)

    from deepr.cli.commands.run_submission import cleanup_persisted_uploads

    cleanup_closed = True
    has_cleanup_metadata = bool(job.metadata.get("provider_file_ids") or job.metadata.get("vector_store_id"))
    if has_cleanup_metadata:
        if provider is None or not await cleanup_persisted_uploads(provider, job):
            logger.error("Provider upload cleanup incomplete for cancelled job %s", job.id)
            cleanup_closed = False
        elif not await queue.clear_cleanup_metadata(job.id):
            logger.error("Provider cleanup state was not persisted for cancelled job %s", job.id)
            cleanup_closed = False
    return ResearchCancellationOutcome(
        queue_cancelled=True,
        cost_closed=True,
        cleanup_closed=cleanup_closed,
    )


async def _cancel_unclaimed_submission(
    *,
    queue: Any,
    job: ResearchJob,
    default_provider: str,
    provider: Any,
    reservation: ResearchCostReservation | None,
) -> tuple[ResearchCancellationOutcome | None, ResearchJob]:
    """Cancel a queued snapshot atomically or refresh it after losing the claim."""
    if job.status != JobStatus.QUEUED or job.provider_job_id:
        return None, job
    if await queue.cancel_queued_submission(job.id):
        active_reservation = reservation or restore_research_cost_reservation(
            job_id=job.id,
            metadata=job.metadata,
            provider=default_provider,
            model=job.model,
        )
        if active_reservation is None:
            return ResearchCancellationOutcome(queue_cancelled=True, cost_closed=False), job
        from deepr.cli.commands.run_submission import rollback_persisted_submission

        cleanup_closed = await rollback_persisted_submission(
            provider,
            job,
            active_reservation,
            source=f"services.research_cancellation.queued.{job.id}",
        )
        has_cleanup_metadata = bool(job.metadata.get("provider_file_ids") or job.metadata.get("vector_store_id"))
        if cleanup_closed and has_cleanup_metadata:
            cleanup_closed = bool(await queue.clear_cleanup_metadata(job.id))
        return ResearchCancellationOutcome(
            queue_cancelled=True,
            cost_closed=True,
            cleanup_closed=cleanup_closed,
        ), job
    current_job = await queue.get_job(job.id)
    if current_job is None:
        return ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False), job
    return None, current_job


async def cancel_reserved_research(
    *,
    queue: Any,
    provider: Any,
    job: ResearchJob,
    default_provider: str,
    source: str,
    reservation: ResearchCostReservation | None = None,
) -> ResearchCancellationOutcome:
    """Cancel provider work before queue work and conservatively close cost."""
    if job.status == JobStatus.CANCELLED:
        return await _close_cancelled_snapshot(
            queue=queue,
            job=job,
            provider=provider,
            default_provider=default_provider,
            reservation=reservation,
            source=f"{source}.retry",
        )
    if job.status not in {JobStatus.QUEUED, JobStatus.PROCESSING}:
        return ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False)
    queued_outcome, job = await _cancel_unclaimed_submission(
        queue=queue,
        job=job,
        default_provider=default_provider,
        provider=provider,
        reservation=reservation,
    )
    if queued_outcome is not None:
        return queued_outcome

    provider_job_id = str(job.provider_job_id or "")
    accepted_by_provider = bool(provider_job_id)
    if job.status == JobStatus.PROCESSING and not accepted_by_provider:
        return ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False)
    active_reservation = reservation or restore_research_cost_reservation(
        job_id=job.id,
        metadata=job.metadata,
        provider=default_provider,
        model=job.model,
    )
    if active_reservation is None:
        return ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False)
    if not await _cancel_accepted_provider_job(provider, provider_job_id, job.id):
        return ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False)

    if not await queue.cancel_active_job(job.id):
        return ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False)
    settle_research_cost(
        active_reservation,
        actual_cost=None,
        request_id=provider_job_id,
        source=source,
    )

    from deepr.cli.commands.run_submission import cleanup_persisted_uploads

    has_cleanup_metadata = bool(job.metadata.get("provider_file_ids") or job.metadata.get("vector_store_id"))
    cleanup_closed = await cleanup_persisted_uploads(provider, job)
    if not cleanup_closed:
        logger.error("Provider upload cleanup incomplete for cancelled job %s", job.id)
    elif has_cleanup_metadata and not await queue.clear_cleanup_metadata(job.id):
        logger.error("Provider cleanup state was not persisted for cancelled job %s", job.id)
        cleanup_closed = False

    return ResearchCancellationOutcome(
        queue_cancelled=True,
        cost_closed=True,
        cleanup_closed=cleanup_closed,
    )


__all__ = ["ResearchCancellationOutcome", "cancel_reserved_research"]
