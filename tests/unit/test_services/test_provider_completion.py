"""Durable provider-completion finalization contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.queue.base import JobStatus, ResearchJob
from deepr.queue.local_queue import SQLiteQueue
from deepr.services.provider_completion import finalize_provider_completion


def _response():
    return SimpleNamespace(
        output=[{"type": "message", "content": [{"type": "output_text", "text": "result"}]}],
        usage=SimpleNamespace(cost=0.25, total_tokens=42),
    )


@pytest.mark.asyncio
async def test_completion_closes_cost_and_cleanup_before_terminal_state() -> None:
    job = ResearchJob(
        id="job-1",
        prompt="complete",
        status=JobStatus.PROCESSING,
        provider_job_id="provider-job",
    )
    updated = ResearchJob(id="job-1", prompt="complete", status=JobStatus.COMPLETED)
    queue = MagicMock(
        update_results=AsyncMock(return_value=True),
        update_status=AsyncMock(return_value=True),
        get_job=AsyncMock(return_value=updated),
    )
    storage = MagicMock(save_report=AsyncMock(return_value=SimpleNamespace(url="report.md")))
    reservation = MagicMock()

    with (
        patch(
            "deepr.services.provider_completion.restore_research_cost_reservation",
            return_value=reservation,
        ),
        patch("deepr.services.provider_completion.settle_research_cost") as settle,
        patch(
            "deepr.services.provider_completion.reconcile_research_cost_from_ledger",
            return_value=True,
        ),
        patch(
            "deepr.cli.commands.run_submission.cleanup_persisted_uploads",
            new=AsyncMock(return_value=True),
        ) as cleanup,
    ):
        result = await finalize_provider_completion(
            queue=queue,
            storage=storage,
            provider=MagicMock(),
            job=job,
            response=_response(),
            source="test",
        )

    assert result is updated
    settle.assert_called_once()
    cleanup.assert_awaited_once()
    queue.update_status.assert_awaited_once_with("job-1", JobStatus.COMPLETED)


@pytest.mark.asyncio
async def test_completion_does_not_claim_terminal_state_when_cost_settlement_fails() -> None:
    job = ResearchJob(
        id="job-1",
        prompt="complete",
        status=JobStatus.PROCESSING,
        provider_job_id="provider-job",
    )
    queue = MagicMock(update_status=AsyncMock())
    storage = MagicMock(save_report=AsyncMock(return_value=SimpleNamespace(url="report.md")))

    with (
        patch(
            "deepr.services.provider_completion.restore_research_cost_reservation",
            return_value=MagicMock(),
        ),
        patch(
            "deepr.services.provider_completion.settle_research_cost",
            side_effect=RuntimeError("ledger unavailable"),
        ),
    ):
        with pytest.raises(RuntimeError, match="ledger unavailable"):
            await finalize_provider_completion(
                queue=queue,
                storage=storage,
                provider=MagicMock(),
                job=job,
                response=_response(),
                source="test",
            )

    queue.update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_retry_does_not_repeat_confirmed_provider_cleanup(tmp_path) -> None:
    queue = SQLiteQueue(str(tmp_path / "queue.db"))
    job = ResearchJob(
        id="job-1",
        prompt="complete",
        status=JobStatus.PROCESSING,
        provider_job_id="provider-job",
        metadata={
            "provider_file_ids": ["file-1"],
            "vector_store_id": "vs-1",
        },
    )
    await queue.enqueue(job)
    storage = MagicMock(save_report=AsyncMock(return_value=SimpleNamespace(url="report.md")))
    provider = MagicMock(
        delete_document=AsyncMock(return_value=True),
        delete_vector_store=AsyncMock(return_value=True),
    )
    original_update_status = queue.update_status
    queue.update_status = AsyncMock(return_value=False)

    with (
        patch(
            "deepr.services.provider_completion.restore_research_cost_reservation",
            return_value=MagicMock(),
        ),
        patch("deepr.services.provider_completion.settle_research_cost"),
        patch(
            "deepr.services.provider_completion.reconcile_research_cost_from_ledger",
            return_value=True,
        ),
    ):
        with pytest.raises(RuntimeError, match="completion status"):
            await finalize_provider_completion(
                queue=queue,
                storage=storage,
                provider=provider,
                job=job,
                response=_response(),
                source="test",
            )

        retry_job = await queue.get_job(job.id)
        assert retry_job is not None
        assert retry_job.metadata == {}
        queue.update_status = original_update_status
        completed = await finalize_provider_completion(
            queue=queue,
            storage=storage,
            provider=provider,
            job=retry_job,
            response=_response(),
            source="test.retry",
        )

    assert completed.status == JobStatus.COMPLETED
    provider.delete_document.assert_awaited_once_with("file-1")
    provider.delete_vector_store.assert_awaited_once_with("vs-1")
