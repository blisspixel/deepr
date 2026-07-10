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
    rollback.assert_awaited_once()


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
    settle.assert_not_called()


@pytest.mark.asyncio
async def test_provider_cancellation_failure_keeps_queue_and_reservation_open():
    queue = MagicMock(cancel_job=AsyncMock(return_value=True))
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
    queue.cancel_job.assert_not_awaited()
    settle.assert_not_called()


@pytest.mark.asyncio
async def test_accepted_job_cancellation_settles_estimate_instead_of_refunding():
    queue = MagicMock(cancel_job=AsyncMock(return_value=True))
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
async def test_provider_cancellation_repairs_queue_when_cancel_transition_is_rejected():
    queue = MagicMock(
        cancel_job=AsyncMock(return_value=False),
        update_status=AsyncMock(return_value=True),
    )
    provider = MagicMock(cancel_job=AsyncMock(return_value=True))
    reservation = MagicMock()
    job = ResearchJob(id="accepted", prompt="prompt", provider_job_id="provider-job")

    with patch("deepr.services.research_cancellation.settle_research_cost"):
        outcome = await cancel_reserved_research(
            queue=queue,
            provider=provider,
            job=job,
            default_provider="openai",
            source="test.cancel",
            reservation=reservation,
        )

    assert outcome.queue_cancelled is True
    queue.update_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_inflight_submission_cannot_release_cost_without_provider_id():
    queue = MagicMock(cancel_job=AsyncMock(return_value=True))
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
    queue.cancel_job.assert_not_awaited()
    settle.assert_not_called()
