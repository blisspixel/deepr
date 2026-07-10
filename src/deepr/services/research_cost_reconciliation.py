"""Repair durable research cost holds from terminal queue evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from deepr.experts.cost_safety import get_cost_safety_manager
from deepr.experts.research_cost_gate import (
    ResearchCostReservation,
    refund_research_cost,
    settle_research_cost,
)
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.queue.base import JobStatus


async def reconcile_research_cost_reservations(queue: Any, *, default_provider: str) -> int:
    """Close orphaned holds only from terminal or missing queue evidence."""
    reconciled = 0
    store = ResearchReservationStore()
    for record in store.active_reservations():
        job = await queue.get_job(record.job_id)
        age = datetime.now(UTC) - record.created_at
        if job is None and age < timedelta(minutes=15):
            continue
        if job is not None and job.status == JobStatus.QUEUED:
            if age < timedelta(minutes=15) or not await queue.cancel_job(job.id):
                continue
            reservation = ResearchCostReservation(
                job_id=record.job_id,
                provider=str(job.provider or default_provider),
                model=job.model,
                estimated_cost=record.reserved_cost,
                reservation_id=record.reservation_id,
                manager=get_cost_safety_manager(),
            )
            refund_research_cost(reservation)
            reconciled += 1
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
        reservation = ResearchCostReservation(
            job_id=record.job_id,
            provider=str(getattr(job, "provider", "") or default_provider),
            model=str(getattr(job, "model", "") or ""),
            estimated_cost=record.reserved_cost,
            reservation_id=record.reservation_id,
            manager=get_cost_safety_manager(),
        )
        provider_job_id = str(getattr(job, "provider_job_id", "") or "")
        if (
            job is None
            or job.status in {JobStatus.COMPLETED, JobStatus.FAILED}
            or provider_job_id
            or unresolved_submission
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
