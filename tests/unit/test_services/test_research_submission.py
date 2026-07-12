"""Tests for reserved provider dispatch."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.experts.research_cost_gate import ResearchCostReservation
from deepr.providers.base import ResearchRequest
from deepr.queue.base import JobStatus, ResearchJob
from deepr.services.research_bounds import ResearchRequestBoundsError
from deepr.services.research_submission import (
    ResearchDispatchReservationError,
    dispatch_reserved_research,
)


@pytest.fixture(autouse=True)
def _durable_reservation_is_active(monkeypatch):
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "deepr.services.research_submission.ResearchReservationStore.is_active_for_job",
        lambda _self, **_kwargs: True,
    )
    monkeypatch.setattr("deepr.services.research_submission.mark_research_provider_work", lambda _reservation: None)


_MODEL = "o4-mini-deep-research"


def _job() -> ResearchJob:
    return ResearchJob(
        id="job-1",
        prompt="Research",
        model=_MODEL,
        status=JobStatus.QUEUED,
        metadata={
            "cost_reservation_id": "reservation-1",
            "cost_reservation_estimated_usd": 0.6,
            "cost_reservation_provider": "openai",
            "cost_reservation_model": _MODEL,
        },
    )


def _reservation() -> ResearchCostReservation:
    return ResearchCostReservation(
        job_id="job-1",
        provider="openai",
        model=_MODEL,
        estimated_cost=0.6,
        reservation_id="reservation-1",
        manager=MagicMock(),
    )


def _queue(**overrides) -> MagicMock:
    values = {
        "enqueue": AsyncMock(),
        "get_job": AsyncMock(),
        "claim_submission": AsyncMock(return_value=True),
        "update_status": AsyncMock(return_value=True),
    }
    values.update(overrides)
    queue = MagicMock(**values)
    if "get_job" not in overrides and "enqueue" not in overrides:

        async def persist(job: ResearchJob) -> str:
            queue.get_job.return_value = job
            return job.id

        queue.enqueue = AsyncMock(side_effect=persist)
    return queue


@pytest.mark.asyncio
async def test_dispatch_enqueues_submits_and_persists_provider_id() -> None:
    queue = _queue()
    provider = MagicMock(submit_research=AsyncMock(return_value="provider-1"), cancel_job=AsyncMock())
    reservation = _reservation()

    provider_job_id = await dispatch_reserved_research(
        queue=queue,
        provider=provider,
        job=_job(),
        request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
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
async def test_dispatch_settles_maximum_when_provider_rejects_after_mark() -> None:
    queue = _queue()
    provider = MagicMock(submit_research=AsyncMock(side_effect=RuntimeError("rejected")))
    reservation = _reservation()

    with (
        patch("deepr.services.research_submission.settle_research_cost") as settle,
        pytest.raises(RuntimeError, match="rejected"),
    ):
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
            reservation=reservation,
        )

    settle.assert_called_once_with(
        reservation,
        actual_cost=None,
        request_id="deepr-research-job-1",
        source="services.dispatch_reserved_research.provider_failure",
        actual_cost_reported=False,
        settlement_metadata={"research_dispatch_settlement_reason": "provider_call_failed"},
    )
    reservation.manager.refund_reservation.assert_not_called()
    queue.update_status.assert_awaited_once_with(
        job_id="job-1",
        status=JobStatus.FAILED,
        error="rejected",
    )


@pytest.mark.asyncio
async def test_dispatch_settles_when_tracking_failure_provider_cancelled() -> None:
    queue = _queue(update_status=AsyncMock(side_effect=[False, True]))
    provider = MagicMock(
        submit_research=AsyncMock(return_value="provider-1"),
        cancel_job=AsyncMock(return_value=True),
    )
    reservation = _reservation()

    with (
        patch("deepr.services.research_submission.settle_research_cost") as settle,
        pytest.raises(RuntimeError, match="queue rejected"),
    ):
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
            reservation=reservation,
        )

    provider.cancel_job.assert_awaited_once_with("provider-1")
    settle.assert_called_once_with(
        reservation,
        actual_cost=None,
        request_id="provider-1",
        source="services.dispatch_reserved_research.tracking_failure",
        actual_cost_reported=False,
        settlement_metadata={"research_dispatch_settlement_reason": "provider_accepted_queue_handoff_failed"},
    )
    reservation.manager.refund_reservation.assert_not_called()


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
            request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
            reservation=reservation,
        )

    settle.assert_called_once_with(
        reservation,
        actual_cost=None,
        request_id="provider-1",
        source="services.dispatch_reserved_research.tracking_failure",
        actual_cost_reported=False,
        settlement_metadata={"research_dispatch_settlement_reason": "provider_accepted_queue_handoff_failed"},
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
            request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
            reservation=reservation,
        )

    settle.assert_called_once_with(
        reservation,
        actual_cost=None,
        request_id="deepr-research-job-1",
        source="services.dispatch_reserved_research.provider_failure",
        actual_cost_reported=False,
        settlement_metadata={"research_dispatch_settlement_reason": "provider_call_failed"},
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
            request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
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
            request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
            reservation=_reservation(),
        )

    assert observed == {
        "reservation_id": "reservation-1",
        "job_id": "job-1",
        "reserved_cost": 0.6,
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
            request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
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
            request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
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
            request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
            reservation=_reservation(),
        )

    provider.submit_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_during_provider_call_conservatively_settles() -> None:
    queue = _queue()
    entered = asyncio.Event()

    async def submit(_request: ResearchRequest) -> str:
        entered.set()
        await asyncio.Event().wait()
        return "unreachable"

    provider = MagicMock(submit_research=AsyncMock(side_effect=submit))
    reservation = _reservation()
    with patch("deepr.services.research_submission.settle_research_cost") as settle:
        task = asyncio.create_task(
            dispatch_reserved_research(
                queue=queue,
                provider=provider,
                job=_job(),
                request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
                reservation=reservation,
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError) as raised:
            await task

    settle.assert_called_once_with(
        reservation,
        actual_cost=None,
        request_id="deepr-research-job-1",
        source="services.dispatch_reserved_research.provider_failure",
        actual_cost_reported=False,
        settlement_metadata={"research_dispatch_settlement_reason": "provider_call_cancelled"},
    )
    assert raised.value.__dict__.get("research_dispatch_accounting_error") is None
    reservation.manager.refund_reservation.assert_not_called()


@pytest.mark.asyncio
async def test_cancellation_waits_for_provider_id_handoff() -> None:
    handoff_entered = asyncio.Event()
    release_handoff = asyncio.Event()

    async def persist_handoff(**_kwargs) -> bool:
        handoff_entered.set()
        await release_handoff.wait()
        return True

    queue = _queue(update_status=AsyncMock(side_effect=persist_handoff))
    provider = MagicMock(submit_research=AsyncMock(return_value="provider-1"))
    reservation = _reservation()
    with patch("deepr.services.research_submission.settle_research_cost") as settle:
        task = asyncio.create_task(
            dispatch_reserved_research(
                queue=queue,
                provider=provider,
                job=_job(),
                request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
                reservation=reservation,
            )
        )
        await asyncio.wait_for(handoff_entered.wait(), timeout=2)
        task.cancel()
        release_handoff.set()
        with pytest.raises(asyncio.CancelledError) as raised:
            await task

    assert raised.value.__dict__["research_dispatch_handoff_persisted"] is True
    assert raised.value.__dict__["research_dispatch_provider_job_id"] == "provider-1"
    settle.assert_not_called()
    reservation.manager.refund_reservation.assert_not_called()


@pytest.mark.asyncio
async def test_cancellation_during_dispatch_mark_refunds_before_provider(monkeypatch) -> None:
    entered = threading.Event()
    release = threading.Event()

    def mark(_reservation: ResearchCostReservation) -> None:
        entered.set()
        release.wait(timeout=2)

    monkeypatch.setattr("deepr.services.research_submission.mark_research_provider_work", mark)
    queue = _queue()
    provider = MagicMock(submit_research=AsyncMock())
    reservation = _reservation()
    with patch("deepr.services.research_submission.refund_research_cost") as refund:
        task = asyncio.create_task(
            dispatch_reserved_research(
                queue=queue,
                provider=provider,
                job=_job(),
                request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
                reservation=reservation,
            )
        )
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError) as raised:
            await task

    refund.assert_called_once_with(reservation)
    assert raised.value.__dict__["research_dispatch_predispatch_reservation_cleaned"] is True
    provider.submit_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_during_enqueue_cancels_snapshot_before_refund() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def enqueue(_job: ResearchJob) -> str:
        entered.set()
        await release.wait()
        return "job-1"

    queue = _queue(enqueue=AsyncMock(side_effect=enqueue))
    queue.cancel_queued_submission = AsyncMock(return_value=True)
    provider = MagicMock(submit_research=AsyncMock())
    reservation = _reservation()
    with patch("deepr.services.research_submission.refund_research_cost") as refund:
        task = asyncio.create_task(
            dispatch_reserved_research(
                queue=queue,
                provider=provider,
                job=_job(),
                request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
                reservation=reservation,
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    queue.cancel_queued_submission.assert_awaited_once_with("job-1")
    refund.assert_called_once_with(reservation)
    provider.submit_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_refuses_reservation_smaller_than_full_envelope() -> None:
    reservation = _reservation()
    reservation = ResearchCostReservation(
        job_id=reservation.job_id,
        provider=reservation.provider,
        model=reservation.model,
        estimated_cost=0.01,
        reservation_id=reservation.reservation_id,
        manager=reservation.manager,
    )
    queue = _queue()
    provider = MagicMock(submit_research=AsyncMock())
    with (
        patch("deepr.services.research_submission.refund_research_cost") as refund,
        pytest.raises(ResearchRequestBoundsError) as raised,
    ):
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=_job(),
            request=ResearchRequest(prompt="Research", model=_MODEL, system_message="Test"),
            reservation=reservation,
        )

    assert raised.value.code == "research_reservation_envelope_too_small"
    refund.assert_called_once_with(reservation)
    queue.enqueue.assert_not_awaited()
    provider.submit_research.assert_not_awaited()


@pytest.mark.asyncio
async def test_gemini_deep_research_fails_closed_before_dispatch() -> None:
    model = "deep-research-pro-preview-12-2025"
    reservation = ResearchCostReservation(
        job_id="job-1",
        provider="gemini",
        model=model,
        estimated_cost=5.0,
        reservation_id="reservation-1",
        manager=MagicMock(),
    )
    job = _job()
    job.model = model
    queue = _queue()
    provider = MagicMock(submit_research=AsyncMock())
    with (
        patch("deepr.services.research_submission.refund_research_cost") as refund,
        pytest.raises(ResearchRequestBoundsError) as raised,
    ):
        await dispatch_reserved_research(
            queue=queue,
            provider=provider,
            job=job,
            request=ResearchRequest(prompt="Research", model=model, system_message="Test"),
            reservation=reservation,
        )

    assert raised.value.code == "gemini_deep_research_budget_unbounded"
    refund.assert_called_once_with(reservation)
    provider.submit_research.assert_not_awaited()
