"""Worker recovery for a claim that died before provider handoff."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.core.costs import CostEstimate
from deepr.experts.cost_safety import CostSafetyManager
from deepr.experts.research_cost_gate import reserve_research_cost
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.observability.cost_ledger import CostLedger
from deepr.queue.base import JobStatus, ResearchJob
from deepr.queue.local_queue import SQLiteQueue
from deepr.worker.poller import JobPoller

_UNRESOLVED = "Provider submission outcome unresolved after reservation grace period"


class _SyntheticProvider:
    """Records provider traffic. Recovery must not submit or cancel."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_status(self, provider_job_id: str) -> MagicMock:
        self.calls.append(f"status:{provider_job_id}")
        response = MagicMock()
        response.status = "in_progress"
        return response

    async def cancel_job(self, provider_job_id: str) -> bool:
        self.calls.append(f"cancel:{provider_job_id}")
        return False

    async def submit_research(self, request: object) -> str:
        self.calls.append("submit")
        raise AssertionError(f"recovery submitted work: {request!r}")


def _reserve(job_id: str):
    return reserve_research_cost(
        job_id=job_id,
        provider="openai",
        model="test-model",
        estimate=CostEstimate(0.1, 0.3, 0.2, "test-model", "test"),
        max_cost_per_job=1.0,
        max_daily_cost=2.0,
        max_monthly_cost=5.0,
        manager=CostSafetyManager(),
    )


def _age(reservation_id: str, *, minutes: int) -> None:
    created = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
    with sqlite3.connect(ResearchReservationStore().path) as connection:
        connection.execute(
            "UPDATE research_cost_reservations SET created_at = ? WHERE reservation_id = ?",
            (created, reservation_id),
        )


def _poller(queue: SQLiteQueue, provider: _SyntheticProvider) -> JobPoller:
    with patch("deepr.worker.poller.load_config", return_value={"provider": "openai"}):
        return JobPoller(queue=queue, provider=provider, storage=MagicMock())


async def _claim(queue: SQLiteQueue, reservation, *, provider_job_id: str | None = None) -> None:
    job = ResearchJob(
        id=reservation.job_id,
        prompt="interrupted claim",
        model="test-model",
        provider="openai",
        status=JobStatus.QUEUED,
        metadata=reservation.metadata(),
        provider_job_id=provider_job_id,
    )
    await queue.enqueue(job)
    assert await queue.claim_submission(job.id)


@pytest.mark.asyncio
async def test_restarted_worker_preserves_then_resolves_an_interrupted_claim(tmp_path) -> None:
    """In-grace claims stay put. A later cycle reaches the unresolved outcome."""
    queue = SQLiteQueue(tmp_path / "queue.db")
    provider = _SyntheticProvider()
    reservation = _reserve("interrupted-claim")
    await _claim(queue, reservation)
    _age(reservation.reservation_id, minutes=1)
    poller = _poller(queue, provider)

    await poller._poll_cycle()

    preserved = await queue.get_job(reservation.job_id)
    assert preserved is not None
    assert preserved.status is JobStatus.PROCESSING
    assert preserved.provider_job_id is None
    assert ResearchReservationStore().state(reservation.reservation_id) == "active"
    assert provider.calls == []

    _age(reservation.reservation_id, minutes=20)
    await poller._poll_cycle()
    await poller._poll_cycle()

    resolved = await queue.get_job(reservation.job_id)
    assert resolved is not None
    assert resolved.status is JobStatus.FAILED
    assert resolved.last_error == _UNRESOLVED
    assert resolved.provider_job_id is None
    assert provider.calls == []
    store = ResearchReservationStore()
    assert store.state(reservation.reservation_id) == "settled"
    assert store.active_cost() == 0.0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(0.3)
    assert events[0].idempotency_key == "job:interrupted-claim:completion"


@pytest.mark.asyncio
async def test_worker_does_not_refund_an_untracked_dispatch_after_grace(tmp_path) -> None:
    """A missing provider id does not prove that no remote work happened."""
    queue = SQLiteQueue(tmp_path / "queue.db")
    provider = _SyntheticProvider()
    reservation = _reserve("untracked-dispatch")
    ResearchReservationStore().mark_provider_work_may_have_run(reservation.reservation_id)
    await _claim(queue, reservation)
    _age(reservation.reservation_id, minutes=20)
    poller = _poller(queue, provider)

    await poller._poll_cycle()

    job = await queue.get_job(reservation.job_id)
    assert job is not None
    assert job.status is JobStatus.FAILED
    assert job.last_error == _UNRESOLVED
    assert provider.calls == []
    assert ResearchReservationStore().state(reservation.reservation_id) == "settled"
    assert CostLedger().get_events()[0].cost_usd == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_worker_keeps_polling_a_live_provider_job(tmp_path) -> None:
    queue = SQLiteQueue(tmp_path / "queue.db")
    provider = _SyntheticProvider()
    reservation = _reserve("live-provider-job")
    await _claim(queue, reservation, provider_job_id="provider-1")
    _age(reservation.reservation_id, minutes=20)
    poller = _poller(queue, provider)

    await poller._poll_cycle()

    job = await queue.get_job(reservation.job_id)
    assert job is not None
    assert job.status is JobStatus.PROCESSING
    assert job.provider_job_id == "provider-1"
    assert provider.calls == ["status:provider-1"]
    assert ResearchReservationStore().state(reservation.reservation_id) == "active"


@pytest.mark.asyncio
async def test_worker_settles_a_terminal_job_without_reopening_it(tmp_path) -> None:
    queue = SQLiteQueue(tmp_path / "queue.db")
    provider = _SyntheticProvider()
    reservation = _reserve("already-terminal")
    job = ResearchJob(
        id=reservation.job_id,
        prompt="done",
        model="test-model",
        provider="openai",
        status=JobStatus.COMPLETED,
        cost=0.2,
        metadata=reservation.metadata(),
        provider_job_id="provider-done",
    )
    await queue.enqueue(job)
    poller = _poller(queue, provider)

    await poller._poll_cycle()
    await poller._poll_cycle()

    stored = await queue.get_job(reservation.job_id)
    assert stored is not None
    assert stored.status is JobStatus.COMPLETED
    assert provider.calls == []
    assert ResearchReservationStore().state(reservation.reservation_id) == "settled"
    assert len(CostLedger().get_events()) == 1


@pytest.mark.asyncio
async def test_reconciliation_failure_still_polls_live_jobs() -> None:
    provider = _SyntheticProvider()
    job = ResearchJob(
        id="live-after-reconcile-error",
        prompt="live",
        model="test-model",
        status=JobStatus.PROCESSING,
        provider_job_id="provider-live",
        submitted_at=datetime.now(UTC),
    )
    queue = MagicMock()
    queue.list_jobs = AsyncMock(return_value=[job])
    with (
        patch("deepr.worker.poller.load_config", return_value={"provider": "openai"}),
        patch(
            "deepr.services.research_cost_reconciliation.reconcile_research_cost_reservations",
            new=AsyncMock(side_effect=RuntimeError("store unavailable")),
        ),
    ):
        poller = JobPoller(queue=queue, provider=provider, storage=MagicMock())
        await poller._poll_cycle()

    assert provider.calls == ["status:provider-live"]
