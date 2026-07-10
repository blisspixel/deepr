"""Real SQLite concurrency contracts for dispatch and cancellation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.core.costs import CostEstimate
from deepr.experts.cost_safety import CostSafetyManager
from deepr.experts.research_cost_gate import refund_research_cost, reserve_research_cost
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.providers.base import ResearchRequest
from deepr.queue.base import JobStatus, ResearchJob
from deepr.queue.local_queue import SQLiteQueue
from deepr.services.research_cancellation import cancel_reserved_research
from deepr.services.research_submission import dispatch_reserved_research


@pytest.mark.asyncio
async def test_inflight_submit_cannot_be_cancelled_or_resurrected(tmp_path) -> None:
    queue = SQLiteQueue(str(tmp_path / "queue.db"))
    reservation = reserve_research_cost(
        job_id="racing-job",
        provider="openai",
        model="test-model",
        estimate=CostEstimate(0.1, 0.3, 0.2, "test-model", "test"),
        max_cost_per_job=1.0,
        max_daily_cost=2.0,
        max_monthly_cost=5.0,
        manager=CostSafetyManager(),
    )
    job = ResearchJob(
        id=reservation.job_id,
        prompt="test",
        model="test-model",
        status=JobStatus.QUEUED,
        metadata=reservation.metadata(),
    )
    provider_entered = asyncio.Event()
    release_provider = asyncio.Event()

    async def submit(_request):
        provider_entered.set()
        await release_provider.wait()
        return "provider-job"

    provider = MagicMock(
        submit_research=AsyncMock(side_effect=submit),
        cancel_job=AsyncMock(return_value=True),
    )
    dispatch = asyncio.create_task(
        dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=job,
            request=ResearchRequest(prompt="test", model="test-model", system_message="test"),
            reservation=reservation,
        )
    )
    stale_queued_snapshot = job
    await asyncio.wait_for(provider_entered.wait(), timeout=2)

    claimed = await queue.get_job(job.id)
    assert claimed is not None
    assert claimed.status == JobStatus.PROCESSING
    assert claimed.provider_job_id is None
    cancellation = await cancel_reserved_research(
        queue=queue,
        provider=provider,
        job=claimed,
        default_provider="openai",
        source="test.cancel",
    )
    assert cancellation.queue_cancelled is False
    assert cancellation.cost_closed is False

    stale_cancellation = await cancel_reserved_research(
        queue=queue,
        provider=provider,
        job=stale_queued_snapshot,
        default_provider="openai",
        source="test.cancel-stale",
    )
    assert stale_cancellation.queue_cancelled is False
    assert stale_cancellation.cost_closed is False

    release_provider.set()
    assert await dispatch == "provider-job"
    persisted = await queue.get_job(job.id)
    assert persisted is not None
    assert persisted.status == JobStatus.PROCESSING
    assert persisted.provider_job_id == "provider-job"
    assert ResearchReservationStore().active_cost() == pytest.approx(0.3)
    refund_research_cost(reservation)
