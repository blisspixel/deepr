"""Cost-safe cancellation for queued and provider-accepted research jobs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from deepr.experts.research_cost_gate import (
    ResearchCostReservation,
    restore_research_cost_reservation,
    settle_research_cost,
)
from deepr.queue.base import JobStatus, ResearchJob

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResearchCancellationOutcome:
    """Describe whether queue state and cost state were safely closed."""

    queue_cancelled: bool
    cost_closed: bool


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

        await rollback_persisted_submission(
            provider,
            job,
            active_reservation,
            source=f"services.research_cancellation.queued.{job.id}",
        )
        return ResearchCancellationOutcome(queue_cancelled=True, cost_closed=True), job
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
    if accepted_by_provider:
        if provider is None:
            return ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False)
        try:
            if not await provider.cancel_job(provider_job_id):
                return ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False)
        except Exception:
            logger.exception("Could not cancel provider job %s", provider_job_id)
            return ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False)

    active_reservation = reservation or restore_research_cost_reservation(
        job_id=job.id,
        metadata=job.metadata,
        provider=default_provider,
        model=job.model,
    )
    if accepted_by_provider and active_reservation is not None:
        settle_research_cost(
            active_reservation,
            actual_cost=None,
            request_id=provider_job_id,
            source=source,
        )
    else:
        return ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False)

    from deepr.cli.commands.run_submission import cleanup_persisted_uploads

    if not await cleanup_persisted_uploads(provider, job):
        logger.error("Provider upload cleanup incomplete for cancelled job %s", job.id)

    queue_cancelled = bool(await queue.cancel_job(job.id))
    if not queue_cancelled:
        queue_cancelled = bool(
            await queue.update_status(
                job_id=job.id,
                status=JobStatus.CANCELLED,
                error="Provider cancellation confirmed" if accepted_by_provider else "Cost reservation cancelled",
            )
        )
    return ResearchCancellationOutcome(queue_cancelled=queue_cancelled, cost_closed=True)


__all__ = ["ResearchCancellationOutcome", "cancel_reserved_research"]
