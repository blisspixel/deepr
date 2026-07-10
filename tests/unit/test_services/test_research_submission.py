"""Tests for reserved provider dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.experts.research_cost_gate import ResearchCostReservation
from deepr.providers.base import ResearchRequest
from deepr.queue.base import JobStatus, ResearchJob
from deepr.services.research_submission import dispatch_reserved_research


@pytest.fixture(autouse=True)
def _durable_reservation_is_active(monkeypatch):
    monkeypatch.setattr(
        "deepr.services.research_submission.ResearchReservationStore.is_active",
        lambda _self, _reservation_id: True,
    )


def _job() -> ResearchJob:
    return ResearchJob(id="job-1", prompt="Research", model="test-model", status=JobStatus.QUEUED)


def _reservation() -> ResearchCostReservation:
    return ResearchCostReservation(
        job_id="job-1",
        provider="openai",
        model="test-model",
        estimated_cost=0.4,
        reservation_id="reservation-1",
        manager=MagicMock(),
    )


@pytest.mark.asyncio
async def test_dispatch_enqueues_submits_and_persists_provider_id() -> None:
    queue = MagicMock(
        enqueue=AsyncMock(),
        claim_submission=AsyncMock(return_value=True),
        update_status=AsyncMock(return_value=True),
    )
    provider = MagicMock(submit_research=AsyncMock(return_value="provider-1"), cancel_job=AsyncMock())
    reservation = _reservation()

    provider_job_id = await dispatch_reserved_research(
        queue=queue,
        provider=provider,
        job=_job(),
        request=ResearchRequest(prompt="Research", model="test-model", system_message="Test"),
        reservation=reservation,
    )

    assert provider_job_id == "provider-1"
    submitted_request = provider.submit_research.await_args.args[0]
    assert submitted_request.idempotency_key == "deepr-research-job-1"
    queue.enqueue.assert_awaited_once()
    queue.update_status.assert_awaited_once_with(
        job_id="job-1",
        status=JobStatus.PROCESSING,
        provider_job_id="provider-1",
    )
    reservation.manager.refund_reservation.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_refunds_when_provider_rejects_submission() -> None:
    queue = MagicMock(
        enqueue=AsyncMock(),
        claim_submission=AsyncMock(return_value=True),
        update_status=AsyncMock(return_value=True),
    )
    provider = MagicMock(submit_research=AsyncMock(side_effect=RuntimeError("rejected")))
    reservation = _reservation()

    with pytest.raises(RuntimeError, match="rejected"):
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=MagicMock(),
            reservation=reservation,
        )

    reservation.manager.refund_reservation.assert_called_once_with("reservation-1")
    queue.update_status.assert_awaited_once_with(
        job_id="job-1",
        status=JobStatus.FAILED,
        error="rejected",
    )


@pytest.mark.asyncio
async def test_dispatch_refunds_when_tracking_failure_is_cancelled() -> None:
    queue = MagicMock(
        enqueue=AsyncMock(),
        claim_submission=AsyncMock(return_value=True),
        update_status=AsyncMock(side_effect=[False, True]),
    )
    provider = MagicMock(
        submit_research=AsyncMock(return_value="provider-1"),
        cancel_job=AsyncMock(return_value=True),
    )
    reservation = _reservation()

    with pytest.raises(RuntimeError, match="queue rejected"):
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=MagicMock(),
            reservation=reservation,
        )

    provider.cancel_job.assert_awaited_once_with("provider-1")
    reservation.manager.refund_reservation.assert_called_once_with("reservation-1")


@pytest.mark.asyncio
async def test_dispatch_settles_estimate_when_accepted_job_cannot_be_cancelled() -> None:
    queue = MagicMock(
        enqueue=AsyncMock(),
        claim_submission=AsyncMock(return_value=True),
        update_status=AsyncMock(side_effect=OSError("queue unavailable")),
    )
    provider = MagicMock(
        submit_research=AsyncMock(return_value="provider-1"),
        cancel_job=AsyncMock(return_value=False),
    )
    reservation = _reservation()

    with (
        patch("deepr.services.research_submission.settle_research_cost") as settle,
        pytest.raises(OSError, match="queue unavailable"),
    ):
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=MagicMock(),
            reservation=reservation,
        )

    settle.assert_called_once_with(
        reservation,
        actual_cost=None,
        request_id="provider-1",
        source="services.dispatch_reserved_research.tracking_failure",
    )


@pytest.mark.asyncio
async def test_dispatch_settles_maximum_when_submission_outcome_is_ambiguous() -> None:
    queue = MagicMock(
        enqueue=AsyncMock(),
        claim_submission=AsyncMock(return_value=True),
        update_status=AsyncMock(return_value=True),
    )
    provider = MagicMock(submit_research=AsyncMock(side_effect=TimeoutError("response lost")))
    reservation = _reservation()

    with (
        patch("deepr.services.research_submission.refund_research_cost") as refund,
        patch("deepr.services.research_submission.settle_research_cost") as settle,
        pytest.raises(TimeoutError, match="response lost"),
    ):
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=MagicMock(),
            reservation=reservation,
        )

    settle.assert_called_once_with(
        reservation,
        actual_cost=None,
        request_id="deepr-research-job-1",
        source="services.dispatch_reserved_research.ambiguous_submission",
    )
    refund.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_refuses_provider_work_after_reservation_was_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "deepr.services.research_submission.ResearchReservationStore.is_active",
        lambda _self, _reservation_id: False,
    )
    queue = MagicMock(
        enqueue=AsyncMock(),
        claim_submission=AsyncMock(return_value=True),
        update_status=AsyncMock(return_value=True),
    )
    provider = MagicMock(submit_research=AsyncMock())

    with pytest.raises(RuntimeError, match="reservation closed"):
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=MagicMock(),
            reservation=_reservation(),
        )

    provider.submit_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_refuses_provider_work_when_queue_claim_lost() -> None:
    queue = MagicMock(
        enqueue=AsyncMock(),
        claim_submission=AsyncMock(return_value=False),
        update_status=AsyncMock(return_value=True),
    )
    provider = MagicMock(submit_research=AsyncMock())

    with pytest.raises(RuntimeError, match="cancelled before provider"):
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=MagicMock(),
            reservation=_reservation(),
        )

    provider.submit_research.assert_not_awaited()
