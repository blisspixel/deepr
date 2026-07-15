"""Tests for durable benchmark spend ceilings and ledger settlement."""

from __future__ import annotations

import pytest

from deepr.evals.benchmark_budget import BenchmarkBudgetExceeded, BenchmarkSpendGuard
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.observability.cost_ledger import CostLedger


@pytest.fixture
def isolated_costs(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "costs"))
    return tmp_path


def test_guard_blocks_before_reserving_beyond_run_ceiling(isolated_costs):
    guard = BenchmarkSpendGuard(0.5, run_id="run-cap")
    first = guard.reserve(
        provider="openai",
        model="openai/test",
        cost_ceiling=0.3,
        operation="benchmark_evaluation",
    )

    with pytest.raises(BenchmarkBudgetExceeded, match="would be exceeded"):
        guard.reserve(
            provider="openai",
            model="openai/test",
            cost_ceiling=0.21,
            operation="benchmark_evaluation",
        )

    assert guard.scheduled_cost == pytest.approx(0.3)
    assert ResearchReservationStore().active_cost() == pytest.approx(0.3)
    guard.settle(first, status="completed")


def test_settlement_writes_one_auditable_event_and_closes_hold(isolated_costs):
    guard = BenchmarkSpendGuard(1.0, run_id="run-ledger")
    reservation = guard.reserve(
        provider="gemini",
        model="gemini/test",
        cost_ceiling=0.25,
        operation="benchmark_judge",
        metadata={"tier": "chat", "evaluated_model": "openai/test"},
    )

    guard.settle(reservation, status="failed")

    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].operation == "benchmark_judge"
    assert events[0].cost_usd == pytest.approx(0.25)
    assert events[0].source == "benchmark_models.benchmark_judge"
    assert events[0].metadata["status"] == "failed"
    assert events[0].metadata["cost_basis"] == "conservative_call_ceiling"
    assert ResearchReservationStore().active_cost() == 0


def test_refund_releases_unsubmitted_call_without_ledger_event(isolated_costs):
    guard = BenchmarkSpendGuard(0.5, run_id="run-refund")
    reservation = guard.reserve(
        provider="xai",
        model="xai/test",
        cost_ceiling=0.2,
        operation="benchmark_validation",
    )

    guard.refund(reservation)

    assert guard.scheduled_cost == 0
    assert CostLedger().get_events() == []
    assert ResearchReservationStore().active_cost() == 0


def test_invalid_or_unbounded_runtime_budget_is_rejected(isolated_costs):
    for budget in (True, 0, -1, float("inf"), float("nan")):
        with pytest.raises(BenchmarkBudgetExceeded, match="finite and greater than zero"):
            BenchmarkSpendGuard(budget)


def test_guard_rejects_invalid_call_ceiling(isolated_costs):
    guard = BenchmarkSpendGuard(1.0)

    with pytest.raises(BenchmarkBudgetExceeded, match="finite and non-negative"):
        guard.reserve(provider="openai", model="openai/test", cost_ceiling=True, operation="benchmark")


def test_guard_blocks_writable_but_corrupt_canonical_ledger(isolated_costs):
    path = isolated_costs / "costs" / "cost_ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    ledger = CostLedger(ledger_path=path)

    with pytest.raises(BenchmarkBudgetExceeded, match="not accounting-ready"):
        BenchmarkSpendGuard(1.0, ledger=ledger)

    assert not (path.parent / "research_reservations.db").exists()
