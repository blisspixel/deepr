"""Durable research reservation reconciliation tests."""

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.core.costs import CostEstimate
from deepr.experts.cost_safety import CostSafetyManager
from deepr.experts.research_cost_gate import reserve_research_cost
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.observability.cost_ledger import CostLedger
from deepr.queue.base import JobStatus, ResearchJob
from deepr.services.research_cost_reconciliation import reconcile_research_cost_reservations


@pytest.mark.asyncio
async def test_completed_queue_job_closes_orphaned_durable_hold() -> None:
    reservation = reserve_research_cost(
        job_id="completed-job",
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
        status=JobStatus.COMPLETED,
        cost=0.2,
        metadata=reservation.metadata(),
    )
    queue = MagicMock(get_job=AsyncMock(return_value=job))

    count = await reconcile_research_cost_reservations(queue, default_provider="openai")

    assert count == 1
    assert ResearchReservationStore().active_cost() == 0.0


@pytest.mark.asyncio
async def test_stale_queued_job_is_cancelled_and_refunded() -> None:
    reservation = reserve_research_cost(
        job_id="queued-orphan",
        provider="openai",
        model="test-model",
        estimate=CostEstimate(0.1, 0.3, 0.2, "test-model", "test"),
        max_cost_per_job=1.0,
        max_daily_cost=2.0,
        max_monthly_cost=5.0,
        manager=CostSafetyManager(),
    )
    store = ResearchReservationStore()
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE research_cost_reservations SET created_at = ? WHERE reservation_id = ?",
            ((datetime.now(UTC) - timedelta(minutes=20)).isoformat(), reservation.reservation_id),
        )
    job = ResearchJob(
        id=reservation.job_id,
        prompt="test",
        model="test-model",
        status=JobStatus.QUEUED,
        metadata=reservation.metadata(),
    )
    queue = MagicMock(
        get_job=AsyncMock(return_value=job),
        cancel_job=AsyncMock(return_value=True),
    )

    count = await reconcile_research_cost_reservations(queue, default_provider="openai")

    assert count == 1
    queue.cancel_job.assert_awaited_once_with("queued-orphan")
    assert store.active_cost() == 0.0


@pytest.mark.asyncio
async def test_cancelled_dispatched_job_settles_conservatively_without_provider_id() -> None:
    reservation = reserve_research_cost(
        job_id="cancelled-dispatched",
        provider="openai",
        model="test-model",
        estimate=CostEstimate(0.1, 0.3, 0.2, "test-model", "test"),
        max_cost_per_job=1.0,
        max_daily_cost=2.0,
        max_monthly_cost=5.0,
        manager=CostSafetyManager(),
    )
    store = ResearchReservationStore()
    store.mark_provider_work_may_have_run(reservation.reservation_id)
    job = ResearchJob(
        id=reservation.job_id,
        prompt="test",
        model="test-model",
        status=JobStatus.CANCELLED,
        metadata=reservation.metadata(),
    )
    queue = MagicMock(get_job=AsyncMock(return_value=job))

    count = await reconcile_research_cost_reservations(queue, default_provider="openai")

    assert count == 1
    assert store.state(reservation.reservation_id) == "settled"
    event = CostLedger().get_events()[0]
    assert event.idempotency_key == "job:cancelled-dispatched:completion"
    assert event.cost_usd == pytest.approx(0.3)
    assert event.metadata["actual_cost_reported"] is False
