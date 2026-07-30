"""Durable provider-completion finalization contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.providers.base import UsageStats
from deepr.queue.base import JobStatus, ResearchJob
from deepr.queue.local_queue import SQLiteQueue
from deepr.services.provider_completion import (
    authoritative_completion_usage,
    conservative_completion_cost,
    finalize_provider_completion,
    finalize_provider_failure,
)


def _response():
    return SimpleNamespace(
        output=[{"type": "message", "content": [{"type": "output_text", "text": "result"}]}],
        usage=SimpleNamespace(cost=0.25, total_tokens=42),
    )


def test_missing_immediate_usage_consumes_reserved_ceiling() -> None:
    response = SimpleNamespace(usage=None)
    reservation = SimpleNamespace(estimated_cost=0.75)

    reported, accounted, tokens = conservative_completion_cost(response, reservation)

    assert reported is None
    assert accounted == pytest.approx(0.75)
    assert tokens == 0


def test_completion_pricing_uses_canonical_queued_model() -> None:
    job = ResearchJob(
        id="canonical-model",
        prompt="priced",
        provider="openai",
        model="o3-deep-research",
        enable_web_search=False,
        enable_code_interpreter=False,
        metadata={"cost_reservation_model": "o3-deep-research"},
    )
    response = SimpleNamespace(
        model="o3-deep-research-2025-06-26",
        output=[{"type": "message", "content": []}],
        usage=SimpleNamespace(
            input_tokens=100,
            cached_input_tokens=10,
            output_tokens=20,
            total_tokens=120,
            cost=0.01,
        ),
    )

    with patch.object(UsageStats, "calculate_cost_with_cached_input", return_value=0.25) as calculate:
        cost, tokens = authoritative_completion_usage(job, response)

    assert cost == pytest.approx(0.25)
    assert tokens == 120
    calculate.assert_called_once_with(
        100,
        20,
        "o3-deep-research",
        cached_input_tokens=10,
    )


def test_completion_adds_provable_web_search_charges() -> None:
    job = ResearchJob(
        id="tool-cost",
        prompt="research",
        provider="openai",
        model="o4-mini-deep-research",
        enable_web_search=True,
        enable_code_interpreter=False,
        metadata={
            "cost_reservation_model": "o4-mini-deep-research",
            "research_max_tool_calls": 4,
        },
    )
    response = SimpleNamespace(
        model="o4-mini-deep-research-2025-06-26",
        output=[
            {"type": "web_search_call", "content": []},
            {"type": "web_search_call", "content": []},
            {"type": "message", "content": []},
        ],
        usage=SimpleNamespace(
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=20,
            total_tokens=120,
            cost=0.20,
        ),
    )

    with patch.object(UsageStats, "calculate_cost_with_cached_input", return_value=0.20):
        cost, tokens = authoritative_completion_usage(job, response)

    assert cost == pytest.approx(0.20 + (2 * 0.025))
    assert tokens == 120


def test_code_interpreter_completion_consumes_reserved_ceiling() -> None:
    job = ResearchJob(
        id="unbounded-container-cost",
        prompt="research",
        provider="openai",
        model="o4-mini-deep-research",
        enable_web_search=False,
        enable_code_interpreter=True,
        metadata={
            "cost_reservation_model": "o4-mini-deep-research",
            "research_max_tool_calls": 1,
        },
    )
    response = SimpleNamespace(
        model="o4-mini-deep-research-2025-06-26",
        output=[
            {"type": "code_interpreter_call", "content": []},
            {"type": "message", "content": []},
        ],
        usage=SimpleNamespace(
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=20,
            total_tokens=120,
            cost=0.20,
        ),
    )

    cost, tokens = authoritative_completion_usage(job, response)

    assert cost is None
    assert tokens == 120


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(
            model=None,
            output=[{"type": "message", "content": []}],
            usage=SimpleNamespace(
                input_tokens=100,
                cached_input_tokens=0,
                output_tokens=20,
                total_tokens=120,
                cost=0.01,
            ),
        ),
        SimpleNamespace(
            model="o4-mini-deep-research",
            output=[{"type": "message", "content": []}],
            usage=SimpleNamespace(
                input_tokens=100,
                cached_input_tokens=0,
                output_tokens=20,
                total_tokens=120,
                cost=0.01,
            ),
        ),
        SimpleNamespace(
            model="o3-deep-research",
            output=None,
            usage=SimpleNamespace(
                input_tokens=100,
                cached_input_tokens=0,
                output_tokens=20,
                total_tokens=120,
                cost=0.01,
            ),
        ),
        SimpleNamespace(
            model="o3-deep-research",
            output=[
                {"type": "web_search_call", "content": []},
                {"type": "web_search_call", "content": []},
            ],
            usage=SimpleNamespace(
                input_tokens=100,
                cached_input_tokens=0,
                output_tokens=20,
                total_tokens=120,
                cost=0.01,
            ),
        ),
    ],
)
def test_ambiguous_completion_model_or_tool_usage_consumes_reserved_ceiling(response) -> None:
    job = ResearchJob(
        id="ambiguous-completion",
        prompt="research",
        provider="openai",
        model="o3-deep-research",
        enable_web_search=True,
        enable_code_interpreter=False,
        metadata={
            "cost_reservation_model": "o3-deep-research",
            "research_max_tool_calls": 1,
        },
    )

    cost, tokens = authoritative_completion_usage(job, response)

    assert cost is None
    assert tokens == 120


def test_immediate_completion_with_missing_model_consumes_reserved_ceiling() -> None:
    response = SimpleNamespace(
        model=None,
        usage=SimpleNamespace(cost=0.10, total_tokens=42),
    )
    reservation = SimpleNamespace(
        provider="openai",
        model="o3-deep-research",
        estimated_cost=0.75,
    )

    reported, accounted, tokens = conservative_completion_cost(response, reservation)

    assert reported is None
    assert accounted == pytest.approx(0.75)
    assert tokens == 42


@pytest.mark.asyncio
async def test_failure_settles_missing_usage_before_terminal_state() -> None:
    job = ResearchJob(
        id="job-failed",
        prompt="failed",
        status=JobStatus.PROCESSING,
        provider_job_id="provider-job",
        metadata={},
    )
    updated = ResearchJob(id=job.id, prompt=job.prompt, status=JobStatus.FAILED)
    queue = MagicMock(
        update_results=AsyncMock(return_value=True),
        update_status=AsyncMock(return_value=True),
        get_job=AsyncMock(return_value=updated),
    )
    reservation = MagicMock(estimated_cost=0.80)
    response = SimpleNamespace(usage=None, error="provider failed")

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
    ):
        result = await finalize_provider_failure(
            queue=queue,
            provider=MagicMock(),
            job=job,
            response=response,
            source="test.failure",
        )

    assert result is updated
    assert settle.call_args.kwargs["actual_cost"] is None
    queue.update_results.assert_awaited_once_with(
        job.id,
        report_paths={},
        cost=0.80,
        tokens_used=0,
    )
    queue.update_status.assert_awaited_once_with(job.id, JobStatus.FAILED, error="provider failed")


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
async def test_completion_persists_reserved_ceiling_when_usage_is_missing() -> None:
    job = ResearchJob(
        id="job-missing-usage",
        prompt="complete",
        status=JobStatus.PROCESSING,
        provider_job_id="provider-job",
    )
    updated = ResearchJob(id=job.id, prompt=job.prompt, status=JobStatus.COMPLETED)
    queue = MagicMock(
        update_results=AsyncMock(return_value=True),
        update_status=AsyncMock(return_value=True),
        get_job=AsyncMock(return_value=updated),
    )
    storage = MagicMock(save_report=AsyncMock(return_value=SimpleNamespace(url="report.md")))
    reservation = MagicMock(estimated_cost=0.75)
    response = SimpleNamespace(output=[], usage=None)

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
        ),
    ):
        result = await finalize_provider_completion(
            queue=queue,
            storage=storage,
            provider=MagicMock(),
            job=job,
            response=response,
            source="test.missing_usage",
        )

    assert result is updated
    assert settle.call_args.kwargs["actual_cost"] is None
    queue.update_results.assert_awaited_once_with(
        job.id,
        report_paths={"markdown": "report.md"},
        cost=0.75,
        tokens_used=0,
    )


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
            return_value=MagicMock(estimated_cost=0.25),
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
            return_value=MagicMock(estimated_cost=0.25),
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
