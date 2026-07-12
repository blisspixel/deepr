"""Tests for reserved provider dispatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.experts.research_cost_gate import ResearchCostReservation
from deepr.providers.base import ResearchRequest
from deepr.queue.base import JobStatus, ResearchJob
from deepr.services.research_submission import (
    ResearchDispatchReservationError,
    dispatch_reserved_research,
)


@pytest.fixture(autouse=True)
def _durable_reservation_is_active(monkeypatch):
    monkeypatch.setattr(
        "deepr.services.research_submission.ResearchReservationStore.is_active_for_job",
        lambda _self, **_kwargs: True,
    )


def _job() -> ResearchJob:
    return ResearchJob(
        id="job-1",
        prompt="Research",
        model="test-model",
        status=JobStatus.QUEUED,
        metadata={
            "cost_reservation_id": "reservation-1",
            "cost_reservation_estimated_usd": 0.4,
            "cost_reservation_provider": "openai",
            "cost_reservation_model": "test-model",
        },
    )


def _reservation() -> ResearchCostReservation:
    return ResearchCostReservation(
        job_id="job-1",
        provider="openai",
        model="test-model",
        estimated_cost=0.4,
        reservation_id="reservation-1",
        manager=MagicMock(),
    )


def _queue(**overrides) -> MagicMock:
    values = {
        "enqueue": AsyncMock(),
        "get_job": AsyncMock(return_value=_job()),
        "claim_submission": AsyncMock(return_value=True),
        "update_status": AsyncMock(return_value=True),
    }
    values.update(overrides)
    return MagicMock(**values)


@pytest.mark.asyncio
async def test_dispatch_enqueues_submits_and_persists_provider_id() -> None:
    queue = _queue()
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
    queue = _queue()
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
    queue = _queue(update_status=AsyncMock(side_effect=[False, True]))
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
    queue = _queue(update_status=AsyncMock(side_effect=OSError("queue unavailable")))
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
    queue = _queue()
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
        "deepr.services.research_submission.ResearchReservationStore.is_active_for_job",
        lambda _self, **_kwargs: False,
    )
    queue = _queue()
    provider = MagicMock(submit_research=AsyncMock())

    with pytest.raises(ResearchDispatchReservationError, match="missing or closed") as raised:
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=MagicMock(),
            reservation=_reservation(),
        )

    assert raised.value.code == "reservation_not_active"
    assert raised.value.retryable is False
    provider.submit_research.assert_not_awaited()
    queue.update_status.assert_awaited_once_with(
        job_id="job-1",
        status=JobStatus.FAILED,
        error=str(raised.value),
    )


@pytest.mark.asyncio
async def test_dispatch_checks_exact_reservation_ownership(monkeypatch) -> None:
    observed = {}

    def active_for_job(_self, **values):
        observed.update(values)
        return False

    monkeypatch.setattr(
        "deepr.services.research_submission.ResearchReservationStore.is_active_for_job",
        active_for_job,
    )
    queue = _queue()
    provider = MagicMock(submit_research=AsyncMock())

    with pytest.raises(ResearchDispatchReservationError) as raised:
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=MagicMock(),
            reservation=_reservation(),
        )

    assert observed == {
        "reservation_id": "reservation-1",
        "job_id": "job-1",
        "reserved_cost": 0.4,
    }
    assert raised.value.code == "reservation_not_active"
    provider.submit_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_waits_when_reservation_store_is_unavailable(monkeypatch) -> None:
    def unavailable(_self, **_kwargs):
        raise OSError("database busy")

    monkeypatch.setattr(
        "deepr.services.research_submission.ResearchReservationStore.is_active_for_job",
        unavailable,
    )
    queue = _queue()
    provider = MagicMock(submit_research=AsyncMock())
    reservation = _reservation()

    with pytest.raises(ResearchDispatchReservationError) as raised:
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=MagicMock(),
            reservation=reservation,
        )

    assert raised.value.code == "reservation_store_unavailable"
    assert raised.value.retryable is True
    queue.claim_submission.assert_not_awaited()
    queue.update_status.assert_not_awaited()
    provider.submit_research.assert_not_awaited()
    reservation.manager.refund_reservation.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_fails_when_persisted_reservation_metadata_does_not_match() -> None:
    persisted = _job()
    persisted.metadata["cost_reservation_id"] = "stale-reservation"
    queue = _queue(get_job=AsyncMock(return_value=persisted))
    provider = MagicMock(submit_research=AsyncMock())

    with pytest.raises(ResearchDispatchReservationError) as raised:
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=persisted,
            request=MagicMock(),
            reservation=_reservation(),
        )

    assert raised.value.code == "reservation_mismatch"
    queue.claim_submission.assert_not_awaited()
    provider.submit_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_refuses_provider_work_when_queue_claim_lost() -> None:
    queue = _queue(claim_submission=AsyncMock(return_value=False))
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
