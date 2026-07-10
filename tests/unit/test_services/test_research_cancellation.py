"""Cost-safety contracts for research cancellation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.queue.base import JobStatus, ResearchJob
from deepr.services.research_cancellation import cancel_reserved_research


@pytest.mark.asyncio
async def test_queued_job_refunds_only_after_queue_cancellation():
    queue = MagicMock(cancel_queued_submission=AsyncMock(return_value=True))
    reservation = MagicMock()

    with patch(
        "deepr.cli.commands.run_submission.rollback_persisted_submission",
        new_callable=AsyncMock,
        return_value=True,
    ) as rollback:
        outcome = await cancel_reserved_research(
            queue=queue,
            provider=None,
            job=ResearchJob(id="queued", prompt="prompt"),
            default_provider="openai",
            source="test",
            reservation=reservation,
        )

    assert outcome.queue_cancelled is True
    assert outcome.cost_closed is True
    assert outcome.confirmed is True
    rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_queued_cleanup_is_cleared_before_confirmation():
    queue = MagicMock(
        cancel_queued_submission=AsyncMock(return_value=True),
        clear_cleanup_metadata=AsyncMock(return_value=True),
    )
    job = ResearchJob(
        id="queued",
        prompt="prompt",
        metadata={"provider_file_ids": ["file-1"]},
    )

    with patch(
        "deepr.cli.commands.run_submission.rollback_persisted_submission",
        new=AsyncMock(return_value=True),
    ):
        outcome = await cancel_reserved_research(
            queue=queue,
            provider=MagicMock(),
            job=job,
            default_provider="openai",
            source="test",
            reservation=MagicMock(),
        )

    assert outcome.confirmed is True
    queue.clear_cleanup_metadata.assert_awaited_once_with("queued")


@pytest.mark.asyncio
async def test_queued_cleanup_failure_is_not_reported_as_confirmed():
    queue = MagicMock(cancel_queued_submission=AsyncMock(return_value=True))
    job = ResearchJob(
        id="queued",
        prompt="prompt",
        metadata={"provider_file_ids": ["file-1"]},
    )

    with patch(
        "deepr.cli.commands.run_submission.rollback_persisted_submission",
        new=AsyncMock(return_value=False),
    ):
        outcome = await cancel_reserved_research(
            queue=queue,
            provider=MagicMock(),
            job=job,
            default_provider="openai",
            source="test",
            reservation=MagicMock(),
        )

    assert outcome.queue_cancelled is True
    assert outcome.cost_closed is True
    assert outcome.cleanup_closed is False
    assert outcome.confirmed is False


@pytest.mark.asyncio
async def test_stale_queued_snapshot_cannot_refund_claimed_submission():
    claimed = ResearchJob(id="claimed", prompt="prompt", status=JobStatus.PROCESSING)
    queue = MagicMock(
        cancel_queued_submission=AsyncMock(return_value=False),
        get_job=AsyncMock(return_value=claimed),
    )

    with patch("deepr.services.research_cancellation.settle_research_cost") as settle:
        outcome = await cancel_reserved_research(
            queue=queue,
            provider=None,
            job=ResearchJob(id="claimed", prompt="prompt", status=JobStatus.QUEUED),
            default_provider="openai",
            source="test.cancel",
        )

    assert outcome.queue_cancelled is False
    assert outcome.cost_closed is False
    assert outcome.confirmed is False
    settle.assert_not_called()


@pytest.mark.asyncio
async def test_provider_cancellation_failure_keeps_queue_and_reservation_open():
    queue = MagicMock(cancel_active_job=AsyncMock(return_value=True))
    provider = MagicMock(cancel_job=AsyncMock(return_value=False))
    job = ResearchJob(id="accepted", prompt="prompt", provider_job_id="provider-job")

    with patch("deepr.services.research_cancellation.settle_research_cost") as settle:
        outcome = await cancel_reserved_research(
            queue=queue,
            provider=provider,
            job=job,
            default_provider="openai",
            source="test",
            reservation=MagicMock(),
        )

    assert outcome.queue_cancelled is False
    assert outcome.cost_closed is False
    assert outcome.confirmed is False
    queue.cancel_active_job.assert_not_awaited()
    settle.assert_not_called()


@pytest.mark.asyncio
async def test_provider_cancellation_exception_logs_type_without_content(caplog):
    queue = MagicMock(cancel_active_job=AsyncMock(return_value=True))
    provider = MagicMock(cancel_job=AsyncMock(side_effect=RuntimeError("secret\nforged")))
    job = ResearchJob(id="accepted", prompt="prompt", provider_job_id="secret\nforged-provider-job")

    outcome = await cancel_reserved_research(
        queue=queue,
        provider=provider,
        job=job,
        default_provider="openai",
        source="test",
        reservation=MagicMock(),
    )

    assert outcome.confirmed is False
    assert "RuntimeError" in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.asyncio
async def test_terminal_snapshot_cannot_cancel_provider_or_rewrite_history():
    queue = MagicMock(cancel_active_job=AsyncMock(return_value=True))
    provider = MagicMock(cancel_job=AsyncMock(return_value=True))
    job = ResearchJob(id="completed", prompt="prompt", status=JobStatus.COMPLETED)

    outcome = await cancel_reserved_research(
        queue=queue,
        provider=provider,
        job=job,
        default_provider="openai",
        source="test",
        reservation=MagicMock(),
    )

    assert outcome.confirmed is False
    provider.cancel_job.assert_not_awaited()
    queue.cancel_active_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_snapshot_retries_queued_cost_closure() -> None:
    reservation = MagicMock()
    job = ResearchJob(id="cancelled", prompt="prompt", status=JobStatus.CANCELLED)

    with (
        patch(
            "deepr.services.research_cancellation.restore_research_cost_reservation",
            return_value=reservation,
        ),
        patch("deepr.services.research_cancellation.refund_research_cost") as refund,
    ):
        outcome = await cancel_reserved_research(
            queue=MagicMock(),
            provider=None,
            job=job,
            default_provider="openai",
            source="test.retry",
        )

    assert outcome.confirmed is True
    refund.assert_called_once_with(reservation)


@pytest.mark.asyncio
async def test_cancelled_snapshot_reports_unclosed_accepted_cost() -> None:
    job = ResearchJob(
        id="cancelled",
        prompt="prompt",
        status=JobStatus.CANCELLED,
        provider_job_id="provider-job",
    )

    with (
        patch(
            "deepr.services.research_cancellation.restore_research_cost_reservation",
            return_value=MagicMock(),
        ),
        patch(
            "deepr.services.research_cancellation.settle_research_cost",
            side_effect=RuntimeError("ledger unavailable"),
        ),
    ):
        outcome = await cancel_reserved_research(
            queue=MagicMock(),
            provider=MagicMock(),
            job=job,
            default_provider="openai",
            source="test.retry",
        )

    assert outcome.queue_cancelled is True
    assert outcome.cost_closed is False
    assert outcome.confirmed is False


@pytest.mark.asyncio
async def test_accepted_job_cancellation_settles_estimate_instead_of_refunding():
    queue = MagicMock(cancel_active_job=AsyncMock(return_value=True))
    provider = MagicMock(cancel_job=AsyncMock(return_value=True))
    reservation = MagicMock()
    job = ResearchJob(id="accepted", prompt="prompt", provider_job_id="provider-job")

    with patch("deepr.services.research_cancellation.settle_research_cost") as settle:
        outcome = await cancel_reserved_research(
            queue=queue,
            provider=provider,
            job=job,
            default_provider="openai",
            source="test.cancel",
            reservation=reservation,
        )

    assert outcome.queue_cancelled is True
    assert outcome.cost_closed is True
    settle.assert_called_once_with(
        reservation,
        actual_cost=None,
        request_id="provider-job",
        source="test.cancel",
    )


@pytest.mark.asyncio
async def test_provider_cancellation_does_not_settle_after_losing_terminal_state_race():
    queue = MagicMock(cancel_active_job=AsyncMock(return_value=False))
    provider = MagicMock(cancel_job=AsyncMock(return_value=True))
    reservation = MagicMock()
    job = ResearchJob(id="accepted", prompt="prompt", provider_job_id="provider-job")

    with patch("deepr.services.research_cancellation.settle_research_cost") as settle:
        outcome = await cancel_reserved_research(
            queue=queue,
            provider=provider,
            job=job,
            default_provider="openai",
            source="test.cancel",
            reservation=reservation,
        )

    assert outcome.confirmed is False
    settle.assert_not_called()


@pytest.mark.asyncio
async def test_accepted_job_without_cost_reservation_preserves_active_state():
    queue = MagicMock(cancel_active_job=AsyncMock(return_value=True))
    provider = MagicMock(cancel_job=AsyncMock(return_value=True))
    job = ResearchJob(id="accepted", prompt="prompt", provider_job_id="provider-job")

    with patch(
        "deepr.services.research_cancellation.restore_research_cost_reservation",
        return_value=None,
    ):
        outcome = await cancel_reserved_research(
            queue=queue,
            provider=provider,
            job=job,
            default_provider="openai",
            source="test.cancel",
        )

    assert outcome.confirmed is False
    provider.cancel_job.assert_not_awaited()
    queue.cancel_active_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_inflight_submission_cannot_release_cost_without_provider_id():
    queue = MagicMock(cancel_active_job=AsyncMock(return_value=True))
    job = ResearchJob(id="inflight", prompt="prompt", status=JobStatus.PROCESSING)

    with patch("deepr.services.research_cancellation.settle_research_cost") as settle:
        outcome = await cancel_reserved_research(
            queue=queue,
            provider=None,
            job=job,
            default_provider="openai",
            source="test.cancel",
        )

    assert outcome.queue_cancelled is False
    assert outcome.cost_closed is False
    queue.cancel_active_job.assert_not_awaited()
    settle.assert_not_called()
