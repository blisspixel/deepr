"""Regression tests for atomic research cost reservations."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import MagicMock, patch

import pytest

from deepr.core.costs import CostEstimate
from deepr.experts.cost_safety import CostSafetyManager
from deepr.experts.research_cost_gate import (
    ResearchCostBlocked,
    refund_research_cost,
    reserve_configured_research_cost,
    reserve_research_cost,
    restore_research_cost_reservation,
    settle_research_cost,
)
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.observability.cost_ledger import CostLedger


def _estimate(expected: float, *, maximum: float | None = None) -> CostEstimate:
    return CostEstimate(
        min_cost=expected / 2,
        max_cost=maximum if maximum is not None else expected,
        expected_cost=expected,
        model="test-model",
        reasoning="test estimate",
    )


def _reserve(manager: CostSafetyManager, job_id: str, expected: float):
    return reserve_research_cost(
        job_id=job_id,
        provider="openai",
        model="test-model",
        estimate=_estimate(expected),
        max_cost_per_job=2.0,
        max_daily_cost=1.0,
        max_monthly_cost=5.0,
        manager=manager,
    )


def test_manager_hydrates_cumulative_spend_from_canonical_ledger() -> None:
    CostLedger().record_event("prior_research", "openai", 0.7, idempotency_key="prior")
    manager = CostSafetyManager()

    with pytest.raises(ResearchCostBlocked, match="Daily limit"):
        _reserve(manager, "next-job", 0.4)


def test_settlement_releases_reservation_and_records_actual_cost() -> None:
    manager = CostSafetyManager()
    reservation = _reserve(manager, "job-1", 0.8)

    settle_research_cost(
        reservation,
        actual_cost=0.6,
        tokens=120,
        request_id="provider-1",
        source="test.research",
    )

    assert manager._reserved_daily == 0.0
    assert manager.daily_cost == pytest.approx(0.6)
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(0.6)
    assert events[0].idempotency_key == "job:job-1:completion"


def test_refund_releases_reservation_without_ledger_spend() -> None:
    manager = CostSafetyManager()
    reservation = _reserve(manager, "job-refund", 0.8)

    refund_research_cost(reservation)

    assert manager._reserved_daily == 0.0
    assert manager.daily_cost == 0.0
    assert CostLedger().get_events() == []


def test_parallel_reservations_cannot_overcommit_daily_limit() -> None:
    manager = CostSafetyManager()
    barrier = Barrier(2)

    def attempt(job_id: str) -> bool:
        barrier.wait()
        try:
            _reserve(manager, job_id, 0.75)
        except ResearchCostBlocked:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, ("job-a", "job-b")))

    assert sorted(results) == [False, True]
    assert manager._reserved_daily == pytest.approx(0.75)


def test_independent_managers_cannot_overcommit_durable_daily_limit() -> None:
    managers = (CostSafetyManager(), CostSafetyManager())
    barrier = Barrier(2)

    def attempt(item: tuple[str, CostSafetyManager]) -> bool:
        job_id, manager = item
        barrier.wait()
        try:
            _reserve(manager, job_id, 0.75)
        except ResearchCostBlocked:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, (("job-a", managers[0]), ("job-b", managers[1]))))

    assert sorted(results) == [False, True]
    assert ResearchReservationStore().active_cost() == pytest.approx(0.75)


def test_daily_ceiling_reserves_maximum_estimated_cost() -> None:
    manager = CostSafetyManager()
    first = reserve_research_cost(
        job_id="max-a",
        provider="openai",
        model="test-model",
        estimate=_estimate(0.5, maximum=1.0),
        max_cost_per_job=2.0,
        max_daily_cost=1.0,
        max_monthly_cost=5.0,
        manager=manager,
    )

    with pytest.raises(ResearchCostBlocked, match="Daily limit"):
        reserve_research_cost(
            job_id="max-b",
            provider="openai",
            model="test-model",
            estimate=_estimate(0.5, maximum=1.0),
            max_cost_per_job=2.0,
            max_daily_cost=1.0,
            max_monthly_cost=5.0,
            manager=CostSafetyManager(),
        )

    assert first.estimated_cost == 1.0


def test_worker_settlement_does_not_leave_future_submissions_locally_blocked() -> None:
    first = reserve_research_cost(
        job_id="worker-job",
        provider="openai",
        model="test-model",
        estimate=_estimate(0.5, maximum=0.75),
        max_cost_per_job=2.0,
        max_daily_cost=1.0,
        max_monthly_cost=5.0,
    )
    restored = restore_research_cost_reservation(
        job_id=first.job_id,
        metadata=first.metadata(),
        provider="openai",
        model="test-model",
        manager=CostSafetyManager(),
    )
    assert restored is not None
    settle_research_cost(restored, actual_cost=0.1, source="test.worker")

    second = reserve_research_cost(
        job_id="api-next-job",
        provider="openai",
        model="test-model",
        estimate=_estimate(0.2, maximum=0.3),
        max_cost_per_job=2.0,
        max_daily_cost=1.0,
        max_monthly_cost=5.0,
    )

    assert second.estimated_cost == 0.3


def test_per_job_maximum_is_checked_before_reservation() -> None:
    manager = CostSafetyManager()

    with pytest.raises(ResearchCostBlocked, match="exceeds limit"):
        reserve_research_cost(
            job_id="expensive",
            provider="openai",
            model="test-model",
            estimate=_estimate(0.5, maximum=3.0),
            max_cost_per_job=2.0,
            max_daily_cost=5.0,
            max_monthly_cost=10.0,
            manager=manager,
        )

    assert manager._reserved_daily == 0.0


def test_configured_reservation_only_tightens_per_job_limit() -> None:
    expected_reservation = MagicMock()
    with (
        patch(
            "deepr.config.load_config",
            return_value={
                "max_cost_per_job": 5.0,
                "max_daily_cost": 25.0,
                "max_monthly_cost": 200.0,
            },
        ),
        patch(
            "deepr.experts.research_cost_gate.CostEstimator.estimate_cost",
            return_value=_estimate(0.5, maximum=1.0),
        ),
        patch(
            "deepr.experts.research_cost_gate.reserve_research_cost",
            return_value=expected_reservation,
        ) as reserve,
    ):
        _, reservation = reserve_configured_research_cost(
            job_id="configured",
            provider="openai",
            prompt="prompt",
            model="test-model",
            enable_web_search=True,
            max_cost_per_job=10.0,
        )

    assert reservation is expected_reservation
    assert reserve.call_args.kwargs["max_cost_per_job"] == 5.0
