"""Repair durable research cost holds from terminal queue evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from deepr.experts.cost_safety import get_cost_safety_manager
from deepr.experts.research_cost_gate import (
    ResearchCostReservation,
    refund_research_cost,
    restore_research_cost_reservation,
    settle_research_cost,
)
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.queue.base import JobStatus


def _requires_conservative_settlement(
    job: Any | None,
    *,
    provider_job_id: str,
    unresolved_submission: bool,
    provider_work_may_have_run: bool,
) -> bool:
    """Return whether terminal evidence cannot prove a safe refund."""
    return (
        job is None
        or job.status in {JobStatus.COMPLETED, JobStatus.FAILED}
        or bool(provider_job_id)
        or unresolved_submission
        or provider_work_may_have_run
    )


async def _refund_stale_queued_reservation(
    queue: Any,
    job: Any,
    record: Any,
    *,
    age: timedelta,
    default_provider: str,
) -> int:
    """Cancel and refund one stale job that provably never reached a provider."""
    if age < timedelta(minutes=15) or not await queue.cancel_queued_submission(job.id):
        return 0
    refund_research_cost(
        ResearchCostReservation(
            job_id=record.job_id,
            provider=str(job.provider or default_provider),
            model=job.model,
            estimated_cost=record.reserved_cost,
            reservation_id=record.reservation_id,
            manager=get_cost_safety_manager(),
        )
    )
    return 1


async def reconcile_research_cost_reservations(queue: Any, *, default_provider: str) -> int:
    """Close orphaned holds only from terminal or missing queue evidence."""
    reconciled = 0
    store = ResearchReservationStore()
    for record in store.active_reservations():
        job = await queue.get_job(record.job_id)
        age = datetime.now(UTC) - record.created_at
        if job is None and age < timedelta(minutes=15):
            continue
        if job is not None and job.status == JobStatus.QUEUED and not record.provider_work_may_have_run:
            reconciled += await _refund_stale_queued_reservation(
                queue,
                job,
                record,
                age=age,
                default_provider=default_provider,
            )
            continue
        if job is not None and job.status == JobStatus.PROCESSING and job.provider_job_id:
            continue
        if job is not None and job.status == JobStatus.PROCESSING and age < timedelta(minutes=15):
            continue
        unresolved_submission = job is not None and job.status == JobStatus.PROCESSING
        if job is not None and job.status == JobStatus.PROCESSING:
            await queue.update_status(
                job_id=job.id,
                status=JobStatus.FAILED,
                error="Provider submission outcome unresolved after reservation grace period",
            )
        reservation = (
            restore_research_cost_reservation(
                job_id=record.job_id,
                metadata=getattr(job, "metadata", None),
                provider=str(getattr(job, "provider", "") or default_provider),
                model=str(getattr(job, "model", "") or ""),
                manager=get_cost_safety_manager(),
            )
            if job is not None
            else None
        )
        if reservation is None:
            # An unbound or missing queue record cannot authorize settlement.
            # Keep any possibly dispatched hold active for operator recovery;
            # only definitively pre-dispatch work may be refunded.
            definitively_predispatch_cancel = (
                job is not None
                and job.status == JobStatus.CANCELLED
                and not getattr(job, "provider_job_id", "")
                and not record.provider_work_may_have_run
            )
            if definitively_predispatch_cancel:
                refund_research_cost(
                    ResearchCostReservation(
                        job_id=record.job_id,
                        provider=default_provider,
                        model=str(getattr(job, "model", "") or "unknown"),
                        estimated_cost=record.reserved_cost,
                        reservation_id=record.reservation_id,
                        manager=get_cost_safety_manager(),
                    )
                )
                reconciled += 1
            continue
        provider_job_id = str(getattr(job, "provider_job_id", "") or "")
        if _requires_conservative_settlement(
            job,
            provider_job_id=provider_job_id,
            unresolved_submission=unresolved_submission,
            provider_work_may_have_run=record.provider_work_may_have_run,
        ):
            settle_research_cost(
                reservation,
                actual_cost=getattr(job, "cost", None) if job is not None else None,
                request_id=provider_job_id,
                source="services.reconcile_research_cost_reservations",
            )
        else:
            refund_research_cost(reservation)
        reconciled += 1
    return reconciled


__all__ = ["reconcile_research_cost_reservations"]
