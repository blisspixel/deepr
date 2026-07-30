"""Real SQLite concurrency contracts for dispatch and cancellation."""

import asyncio

import pytest

from deepr.core.costs import CostEstimate
from deepr.experts.cost_safety import CostSafetyManager
from deepr.experts.research_cost_gate import refund_research_cost, reserve_research_cost
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.providers.base import DeepResearchProvider, ResearchRequest, ResearchResponse, VectorStore
from deepr.providers.dispatch_authority import default_paid_endpoint
from deepr.queue.base import JobStatus, ResearchJob
from deepr.queue.local_queue import SQLiteQueue
from deepr.services.research_cancellation import cancel_reserved_research
from deepr.services.research_submission import dispatch_reserved_research


class _RaceProvider(DeepResearchProvider):
    provider_key = "openai"
    _paid_endpoint = default_paid_endpoint("openai")

    def __init__(self, entered: asyncio.Event, release: asyncio.Event) -> None:
        self._entered = entered
        self._release = release

    async def _submit_research_impl(self, request: ResearchRequest) -> str:
        del request
        self._entered.set()
        await self._release.wait()
        return "provider-job"

    async def get_status(self, job_id: str) -> ResearchResponse:
        return ResearchResponse(id=job_id, status="in_progress")

    async def cancel_job(self, job_id: str) -> bool:
        del job_id
        return True

    async def _upload_document_accounted(self, file_path: str, purpose: str = "assistants") -> str:
        del file_path, purpose
        return "file-id"

    async def delete_document(self, file_id: str) -> bool:
        del file_id
        return True

    async def _create_vector_store_accounted(self, name: str, file_ids: list[str]) -> VectorStore:
        return VectorStore(id="store-id", name=name, file_ids=file_ids)

    async def wait_for_vector_store(
        self,
        vector_store_id: str,
        timeout: int = 900,
        poll_interval: float = 2.0,
    ) -> bool:
        del vector_store_id, timeout, poll_interval
        return True

    async def list_vector_stores(self, limit: int = 100) -> list[VectorStore]:
        del limit
        return []

    async def delete_vector_store(self, vector_store_id: str) -> bool:
        del vector_store_id
        return True

    def get_model_name(self, model_key: str) -> str:
        return model_key


@pytest.mark.asyncio
async def test_inflight_submit_cannot_be_cancelled_or_resurrected(tmp_path) -> None:
    queue = SQLiteQueue(str(tmp_path / "queue.db"))
    reservation = reserve_research_cost(
        job_id="racing-job",
        provider="openai",
        model="gpt-4o-mini",
        estimate=CostEstimate(0.1, 0.3, 0.2, "gpt-4o-mini", "test"),
        max_cost_per_job=1.0,
        max_daily_cost=2.0,
        max_monthly_cost=5.0,
        manager=CostSafetyManager(),
    )
    job = ResearchJob(
        id=reservation.job_id,
        prompt="test",
        model="gpt-4o-mini",
        status=JobStatus.QUEUED,
        metadata=reservation.metadata(),
    )
    provider_entered = asyncio.Event()
    release_provider = asyncio.Event()

    provider = _RaceProvider(provider_entered, release_provider)
    dispatch = asyncio.create_task(
        dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=job,
            request=ResearchRequest(prompt="test", model="gpt-4o-mini", system_message="test"),
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
