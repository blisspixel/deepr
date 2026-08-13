"""Regression tests for atomic research cost reservations."""

from __future__ import annotations

import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import MagicMock, patch

import pytest

from deepr.core.costs import CostEstimate
from deepr.experts.cost_safety import CostSafetyManager
from deepr.experts.research_cost_gate import (
    PaidCostCeilingDivergence,
    ResearchCostBlocked,
    ResearchCostReservation,
    ResearchCostSettlementError,
    record_unreserved_research_cost,
    refund_research_cost,
    reserve_configured_cost_ceiling,
    reserve_configured_research_cost,
    reserve_research_cost,
    restore_research_cost_reservation,
    settle_research_cost,
)
from deepr.experts.research_reservation_store import (
    ResearchReservationLimitExceeded,
    ResearchReservationStore,
    ResearchReservationStoreError,
    _settled_spend_windows,
    _wallet_consumed,
)
from deepr.observability.cost_ledger import CostLedger, CostLedgerEvent
from deepr.providers.base import ResearchRequest


def _estimate(expected: float, *, maximum: float | None = None) -> CostEstimate:
    return CostEstimate(
        min_cost=expected / 2,
        max_cost=maximum if maximum is not None else expected,
        expected_cost=expected,
        model="test-model",
        reasoning="test estimate",
    )


def _current_paid_authorization() -> dict[str, object]:
    document = json.loads(Path(os.environ["DEEPR_BUDGET_FILE"]).read_text(encoding="utf-8"))
    return document["paid_api_authorization"]


def _reserve(
    manager: CostSafetyManager,
    job_id: str,
    expected: float,
    *,
    request: ResearchRequest | None = None,
):
    return reserve_research_cost(
        job_id=job_id,
        provider="openai",
        model="test-model",
        estimate=_estimate(expected),
        max_cost_per_job=2.0,
        max_daily_cost=1.0,
        max_monthly_cost=5.0,
        manager=manager,
        request=request,
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
    assert ResearchReservationStore().state(reservation.reservation_id) == "settled"


def test_settlement_of_refunded_reservation_records_truth_freezes_and_fails() -> None:
    from deepr.core.cost_caps import read_operator_budget

    manager = CostSafetyManager()
    reservation = _reserve(manager, "job-refunded-before-settlement", 0.8)
    refund_research_cost(reservation)

    with pytest.raises(ResearchCostSettlementError, match="refunded"):
        settle_research_cost(
            reservation,
            actual_cost=0.6,
            source="test.refunded_settlement",
        )

    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(0.6)
    assert events[0].metadata["durable_settlement_outcome"] == "refunded"
    assert events[0].metadata["accounting_integrity_failure"] is True
    operator = read_operator_budget()
    assert operator.frozen is True
    assert operator.freeze_kind == "legacy"


def test_settlement_of_missing_reservation_records_truth_freezes_and_fails() -> None:
    from deepr.core.cost_caps import read_operator_budget

    reservation = ResearchCostReservation(
        job_id="job-missing-at-settlement",
        provider="openai",
        model="test-model",
        estimated_cost=0.8,
        reservation_id="missing-reservation",
        manager=CostSafetyManager(),
        dispatch_binding_id="a" * 64,
    )

    with pytest.raises(ResearchCostSettlementError, match="missing"):
        settle_research_cost(
            reservation,
            actual_cost=0.6,
            source="test.missing_settlement",
        )

    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(0.6)
    assert events[0].metadata["durable_settlement_outcome"] == "missing"
    assert events[0].metadata["accounting_integrity_failure"] is True
    operator = read_operator_budget()
    assert operator.frozen is True
    assert operator.freeze_kind == "legacy"


def test_active_cost_reconciles_existing_canonical_completion_without_duplicate_spend() -> None:
    reservation = _reserve(CostSafetyManager(), "job-existing-completion", 0.8)
    store = ResearchReservationStore()
    store.mark_provider_work_may_have_run(reservation.reservation_id)
    CostLedger().record_event(
        operation="research_job",
        provider="openai",
        model="test-model",
        cost_usd=0.25,
        task_id=reservation.job_id,
        source="test.existing_completion",
        idempotency_key=f"job:{reservation.job_id}:completion",
    )

    assert store.active_cost() == 0.0
    assert store.state(reservation.reservation_id) == "settled"
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(0.25)


def test_conservative_settlement_is_not_labeled_as_reported_actual_cost() -> None:
    manager = CostSafetyManager()
    reservation = _reserve(manager, "job-conservative", 0.8)

    settle_research_cost(
        reservation,
        actual_cost=0.55,
        actual_cost_reported=False,
        settlement_metadata={
            "settlement_basis": "conservative_unaccounted_ceiling",
            "known_cost_usd": 0.25,
            "unaccounted_ceiling_usd": 0.55,
        },
        source="test.conservative",
    )

    event = CostLedger().get_events()[0]
    assert event.cost_usd == pytest.approx(0.55)
    assert event.metadata == {
        "settlement_basis": "conservative_unaccounted_ceiling",
        "known_cost_usd": 0.25,
        "unaccounted_ceiling_usd": 0.55,
        "cost_reservation_id": reservation.reservation_id,
        "cost_reservation_job_id": reservation.job_id,
        "estimated_cost_usd": 0.8,
        "actual_cost_reported": False,
    }


def test_reported_cost_above_reservation_records_truth_then_freezes_paid_api() -> None:
    from deepr.core.cost_caps import read_operator_budget

    reservation = _reserve(CostSafetyManager(), "job-divergence", 0.5)

    with pytest.raises(PaidCostCeilingDivergence, match="Paid API frozen"):
        settle_research_cost(
            reservation,
            actual_cost=0.6,
            source="test.divergence",
        )

    event = CostLedger().get_events()[0]
    assert event.cost_usd == pytest.approx(0.6)
    assert event.metadata["cost_ceiling_diverged"] is True
    operator = read_operator_budget()
    assert operator.frozen is True
    assert operator.freeze_kind == "cost_ceiling_divergence"
    assert "exceeded authorized ceiling" in operator.freeze_reason


def test_refund_releases_reservation_without_ledger_spend() -> None:
    manager = CostSafetyManager()
    reservation = _reserve(manager, "job-refund", 0.8)

    refund_research_cost(reservation)

    assert manager._reserved_daily == 0.0
    assert manager.daily_cost == 0.0
    assert CostLedger().get_events() == []
    assert ResearchReservationStore().state(reservation.reservation_id) == "refunded"
    assert ResearchReservationStore().state("missing") is None


def test_exact_call_ceiling_is_not_silently_narrowed_to_configured_limit(monkeypatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "0.10")

    with pytest.raises(ResearchCostBlocked, match="exceeds limit"):
        reserve_configured_cost_ceiling(
            job_id="too-wide-envelope",
            provider="openai",
            model="gpt-5-mini",
            max_cost_per_job=0.20,
        )

    assert ResearchReservationStore().active_cost() == pytest.approx(0.0)


def test_exact_call_ceiling_is_fully_held_when_authorized(monkeypatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "0.50")

    reservation = reserve_configured_cost_ceiling(
        job_id="bounded-envelope",
        provider="openai",
        model="gpt-5-mini",
        max_cost_per_job=0.20,
    )

    assert reservation.estimated_cost == pytest.approx(0.20)
    assert ResearchReservationStore().active_cost() == pytest.approx(0.20)
    refund_research_cost(reservation, provider_work_did_not_run=True)


def test_refund_cannot_release_hold_after_provider_dispatch_mark() -> None:
    manager = CostSafetyManager()
    reservation = _reserve(manager, "job-dispatched", 0.8)
    store = ResearchReservationStore()
    store.mark_provider_work_may_have_run(reservation.reservation_id)

    refund_research_cost(reservation)

    assert store.state(reservation.reservation_id) == "active"
    assert store.active_reservations()[0].provider_work_may_have_run is True
    assert manager._reserved_daily == pytest.approx(0.8)


def test_unreserved_missing_usage_records_configured_ceiling(monkeypatch) -> None:
    from deepr.core.cost_caps import read_operator_budget

    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "0.75")
    manager = CostSafetyManager()

    settled = record_unreserved_research_cost(
        job_id="legacy-missing-usage",
        provider="openai",
        model="o3-deep-research",
        actual_cost=None,
        manager=manager,
        source="test.legacy",
    )

    assert settled == pytest.approx(0.75)
    event = CostLedger().get_events()[0]
    assert event.cost_usd == pytest.approx(0.75)
    assert event.metadata["actual_cost_reported"] is False
    assert event.metadata["settlement_basis"] == "configured_ceiling"
    operator = read_operator_budget()
    assert operator.frozen is True
    assert operator.freeze_kind == "legacy"
    assert "legacy unreserved paid API completion" in operator.freeze_reason
    assert "pending accounting review" in operator.freeze_reason


def test_unreserved_reported_cost_records_truth_then_freezes_paid_api() -> None:
    from deepr.core.cost_caps import read_operator_budget

    settled = record_unreserved_research_cost(
        job_id="legacy-reported-usage",
        provider="openai",
        model="o3-deep-research",
        actual_cost=3.75,
        tokens=1_200,
        request_id="provider-unreserved",
        manager=CostSafetyManager(),
        source="test.legacy.reported",
    )

    assert settled == pytest.approx(3.75)
    event = CostLedger().get_events()[0]
    assert event.cost_usd == pytest.approx(3.75)
    assert event.request_id == "provider-unreserved"
    assert event.tokens_output == 1_200
    assert event.metadata["legacy_unreserved_job"] is True
    assert event.metadata["actual_cost_reported"] is True
    assert event.metadata["settlement_basis"] == "provider_reported_cost"
    operator = read_operator_budget()
    assert operator.frozen is True
    assert operator.freeze_kind == "legacy"
    assert "legacy-reported-usage" in operator.freeze_reason


def test_unreserved_low_reported_cost_uses_configured_ceiling_floor(monkeypatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "0.75")

    settled = record_unreserved_research_cost(
        job_id="legacy-low-reported-usage",
        provider="openai",
        model="o3-deep-research",
        actual_cost=0.01,
        tokens=1_200,
        manager=CostSafetyManager(),
        source="test.legacy.low-reported",
    )

    assert settled == pytest.approx(0.75)
    event = CostLedger().get_events()[0]
    assert event.cost_usd == pytest.approx(0.75)
    assert event.metadata["actual_cost_reported"] is True
    assert event.metadata["settlement_basis"] == "configured_ceiling_floor"


def test_unreserved_ledger_failure_still_leaves_paid_api_frozen() -> None:
    from deepr.core.cost_caps import read_operator_budget

    manager = MagicMock(spec=CostSafetyManager)
    manager.record_cost.side_effect = RuntimeError("ledger unavailable")

    with pytest.raises(RuntimeError, match="ledger unavailable"):
        record_unreserved_research_cost(
            job_id="legacy-ledger-failure",
            provider="openai",
            model="o3-deep-research",
            actual_cost=0.25,
            manager=manager,
            source="test.legacy.failure",
        )

    manager.record_cost.assert_called_once()
    operator = read_operator_budget()
    assert operator.frozen is True
    assert operator.freeze_kind == "legacy"
    assert "legacy-ledger-failure" in operator.freeze_reason


def test_active_reservation_check_binds_job_and_reserved_cost() -> None:
    reservation = _reserve(CostSafetyManager(), "owned-job", 0.8)
    store = ResearchReservationStore()

    assert store.is_active_for_job(
        reservation_id=reservation.reservation_id,
        job_id="owned-job",
        reserved_cost=0.8,
    )
    assert not store.is_active_for_job(
        reservation_id=reservation.reservation_id,
        job_id="different-job",
        reserved_cost=0.8,
    )
    assert not store.is_active_for_job(
        reservation_id=reservation.reservation_id,
        job_id="owned-job",
        reserved_cost=0.7,
    )


@pytest.mark.parametrize("field_name", ["reserved_cost", "max_daily_cost", "max_monthly_cost"])
@pytest.mark.parametrize("value", [True, -0.01, float("nan"), float("inf"), "1.0"])
def test_durable_store_rejects_invalid_reservation_money(field_name, value, tmp_path) -> None:
    store = ResearchReservationStore(tmp_path / "reservations.db")
    values = {"reserved_cost": 0.5, "max_daily_cost": 1.0, "max_monthly_cost": 5.0}
    values[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        store.reserve(reservation_id="reservation", job_id="job", **values)

    assert store.active_reservations() == []


@pytest.mark.parametrize("value", [True, -0.01, float("nan"), float("inf"), "1.0"])
def test_durable_store_rejects_invalid_settlement_before_callback(value, tmp_path) -> None:
    store = ResearchReservationStore(tmp_path / "reservations.db")
    binding_id = "a" * 64
    store.reserve(
        reservation_id="reservation",
        job_id="job",
        reserved_cost=0.5,
        max_daily_cost=1.0,
        max_monthly_cost=5.0,
        provider="openai",
        model="model",
        dispatch_binding_id=binding_id,
    )
    record = MagicMock()

    with pytest.raises(ValueError, match="actual_cost"):
        store.settle(
            "reservation",
            value,
            record,
            job_id="job",
            reserved_cost=0.5,
            provider="openai",
            model="model",
            dispatch_binding_id=binding_id,
            request_envelope_sha256=None,
        )

    record.assert_not_called()
    assert store.state("reservation") == "active"


@pytest.mark.parametrize(
    ("forged_field", "forged_value"),
    [
        ("job_id", "other-job"),
        ("provider", "anthropic"),
        ("model", "other-model"),
        ("estimated_cost", 0.01),
        ("estimated_cost", float("nan")),
        ("dispatch_binding_id", "f" * 64),
        ("request_envelope_sha256", "e" * 64),
    ],
)
def test_forged_settlement_handle_cannot_close_or_reconcile_real_hold(
    forged_field: str,
    forged_value: object,
) -> None:
    from deepr.core.cost_caps import read_operator_budget

    manager = CostSafetyManager()
    request = ResearchRequest(prompt="bounded request", model="test-model", system_message="system")
    reservation = _reserve(manager, "settlement-owned-job", 0.8, request=request)
    forged = replace(reservation, **{forged_field: forged_value})

    with pytest.raises(ResearchCostSettlementError, match="identity_mismatch"):
        settle_research_cost(forged, actual_cost=0.1, source="test.forged_settlement")

    store = ResearchReservationStore()
    assert store.state(reservation.reservation_id) == "active"
    assert store.active_cost() == pytest.approx(0.8)
    assert manager._reserved_daily == pytest.approx(0.8)
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].operation == "research_settlement_integrity"
    assert "cost_reservation_id" not in events[0].metadata
    assert events[0].metadata["attempted_cost_reservation_id"] == reservation.reservation_id
    assert read_operator_budget().frozen is True


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


def test_operator_ceiling_below_provider_hard_limit_blocks_direct_store_callers() -> None:
    authorization = _current_paid_authorization()
    Path(os.environ["DEEPR_BUDGET_FILE"]).write_text(
        json.dumps(
            {
                "monthly_limit": 1.0,
                "paid_api_frozen": False,
                "paid_api_authorization": authorization,
            }
        ),
        encoding="utf-8",
    )
    store = ResearchReservationStore()
    barrier = Barrier(2)

    def attempt(index: int) -> bool:
        from deepr.core.cost_caps import paid_api_provider_scope

        with paid_api_provider_scope("openai"):
            barrier.wait()
            try:
                store.reserve(
                    reservation_id=f"operator-{index}",
                    job_id=f"job-{index}",
                    reserved_cost=0.75,
                    max_daily_cost=100.0,
                    max_weekly_cost=100.0,
                    max_monthly_cost=100.0,
                )
            except ResearchReservationLimitExceeded:
                return False
            return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, range(2)))

    assert results == [False, False]
    assert ResearchReservationStore().active_cost() == pytest.approx(0.0)


def test_long_lived_manager_observes_operator_freeze_before_next_reservation() -> None:
    manager = CostSafetyManager()
    Path(os.environ["DEEPR_BUDGET_FILE"]).write_text(
        json.dumps(
            {
                "monthly_limit": 200.0,
                "paid_api_frozen": True,
                "freeze_reason": "operator stop",
            }
        ),
        encoding="utf-8",
    )

    allowed, reason, _, reservation_id = manager.check_and_reserve(
        session_id="frozen",
        operation_type="research",
        estimated_cost=0.01,
    )

    assert allowed is False
    assert "ceiling $0.00" in reason
    assert reservation_id == ""


def test_positive_budget_reduction_blocks_previously_reserved_aggregate() -> None:
    store = ResearchReservationStore()
    for index in range(2):
        store.reserve(
            reservation_id=f"reduced-{index}",
            job_id=f"reduced-job-{index}",
            reserved_cost=1.0,
            max_daily_cost=200.0,
            max_weekly_cost=200.0,
            max_monthly_cost=200.0,
        )
    Path(os.environ["DEEPR_BUDGET_FILE"]).write_text(
        json.dumps({"monthly_limit": 1.5, "paid_api_frozen": False}),
        encoding="utf-8",
    )

    with pytest.raises(ResearchReservationLimitExceeded, match="aggregate authority changed"):
        store.mark_provider_work_may_have_run("reduced-0")

    assert all(not row.provider_work_may_have_run for row in store.active_reservations())


def test_new_ledger_spend_blocks_old_hold_at_dispatch() -> None:
    store = ResearchReservationStore()
    authorization = _current_paid_authorization()
    Path(os.environ["DEEPR_BUDGET_FILE"]).write_text(
        json.dumps(
            {
                "monthly_limit": 5.0,
                "paid_api_frozen": False,
                "paid_api_authorization": authorization,
            }
        ),
        encoding="utf-8",
    )
    store.reserve(
        reservation_id="old-hold",
        job_id="old-hold-job",
        reserved_cost=0.75,
        max_daily_cost=200.0,
        max_weekly_cost=200.0,
        max_monthly_cost=200.0,
    )
    CostLedger().record_event(
        operation="unreserved_completion",
        provider="openai",
        cost_usd=4.50,
        source="test",
    )

    with pytest.raises(ResearchReservationLimitExceeded, match="aggregate authority changed"):
        store.mark_provider_work_may_have_run("old-hold")


def test_exposure_snapshot_returns_settled_active_and_unresolved_together() -> None:
    store = ResearchReservationStore()
    store.reserve(
        reservation_id="snapshot-unresolved",
        job_id="snapshot-unresolved-job",
        reserved_cost=0.40,
        max_daily_cost=10.0,
        max_weekly_cost=200.0,
        max_monthly_cost=200.0,
    )
    store.mark_provider_work_may_have_run("snapshot-unresolved")
    store.reserve(
        reservation_id="snapshot-predispatch",
        job_id="snapshot-predispatch-job",
        reserved_cost=0.60,
        max_daily_cost=10.0,
        max_weekly_cost=200.0,
        max_monthly_cost=200.0,
    )
    CostLedger().record_event(
        operation="prior_research",
        provider="openai",
        cost_usd=0.50,
        idempotency_key="snapshot-prior",
    )

    exposure = store.exposure_snapshot()

    assert exposure.daily_settled_cost == pytest.approx(0.50)
    assert exposure.weekly_settled_cost == pytest.approx(0.50)
    assert exposure.monthly_settled_cost == pytest.approx(0.50)
    assert exposure.total_settled_cost == pytest.approx(0.50)
    assert exposure.active_cost == pytest.approx(1.0)
    assert exposure.unresolved_cost == pytest.approx(0.40)
    assert exposure.unresolved_count == 1


def _activate_spend_wallet(amount_usd: float, *, baseline_usd: float) -> str:
    from deepr.core.spend_wallet import create_wallet, save_wallet
    from deepr.observability.cost_ledger import current_cost_state_id

    wallet = create_wallet(
        amount_usd=amount_usd,
        cost_state_id=current_cost_state_id(),
        settled_cost_baseline_usd=baseline_usd,
    )
    save_wallet(wallet)
    return wallet.wallet_id


def test_wallet_caps_total_drawdown_beside_provider_boundary() -> None:
    _activate_spend_wallet(5.0, baseline_usd=0.0)
    store = ResearchReservationStore()

    store.reserve(
        reservation_id="wallet-first",
        job_id="wallet-first-job",
        reserved_cost=2.0,
        max_daily_cost=100.0,
        max_weekly_cost=100.0,
        max_monthly_cost=100.0,
    )
    with pytest.raises(ResearchReservationLimitExceeded, match="limit"):
        store.reserve(
            reservation_id="wallet-over",
            job_id="wallet-over-job",
            reserved_cost=3.01,
            max_daily_cost=100.0,
            max_weekly_cost=100.0,
            max_monthly_cost=100.0,
        )


def test_calendar_windows_reset_independently_of_cumulative_wallet() -> None:
    now = datetime.now(UTC)
    old = CostLedgerEvent(
        operation="old_paid_work",
        provider="openai",
        cost_usd=4.0,
        timestamp=now - timedelta(days=40),
    )
    current = CostLedgerEvent(
        operation="current_paid_work",
        provider="openai",
        cost_usd=1.0,
        timestamp=now,
    )

    assert _settled_spend_windows([old, current], now=now) == pytest.approx((1.0, 1.0, 1.0))
    # The wallet check remains cumulative even though the monthly window reset.
    assert _wallet_consumed([old, current], baseline_usd=0.0) == pytest.approx(5.0)


def test_wallet_refuses_canonical_ledger_rollback() -> None:
    event = CostLedgerEvent(operation="settled", provider="openai", cost_usd=1.0)

    with pytest.raises(ResearchReservationStoreError, match="below the spend wallet baseline"):
        _wallet_consumed([event], baseline_usd=2.0)


def test_explicit_monthly_cap_still_counts_pre_wallet_month_spend(monkeypatch) -> None:
    from deepr.observability import cost_ledger

    monkeypatch.setattr(cost_ledger, "well_known_spend_cap_env_paths", lambda: ())
    CostLedger().record_event(
        operation="current_month_before_wallet",
        provider="openai",
        cost_usd=4.50,
        idempotency_key="pre-wallet-current-month",
    )
    _activate_spend_wallet(200.0, baseline_usd=4.50)
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "5.00")

    with pytest.raises(ResearchReservationLimitExceeded, match=r"limit \$5\.00"):
        ResearchReservationStore().reserve(
            reservation_id="monthly-window-independent",
            job_id="monthly-window-independent-job",
            reserved_cost=0.51,
            max_daily_cost=200.0,
            max_weekly_cost=200.0,
            max_monthly_cost=200.0,
        )


def test_every_later_metered_ledger_dollar_draws_down_wallet() -> None:
    _activate_spend_wallet(4.0, baseline_usd=0.0)
    CostLedger().record_event(
        operation="other_api_usage",
        provider="xai",
        cost_usd=3.25,
        idempotency_key="wallet-cross-provider-spend",
    )

    with pytest.raises(ResearchReservationLimitExceeded, match="limit"):
        ResearchReservationStore().reserve(
            reservation_id="wallet-after-ledger-spend",
            job_id="wallet-after-ledger-spend-job",
            reserved_cost=0.76,
            max_daily_cost=100.0,
            max_weekly_cost=100.0,
            max_monthly_cost=100.0,
        )


def test_zero_dollar_plan_records_do_not_draw_down_wallet() -> None:
    _activate_spend_wallet(50.0, baseline_usd=0.0)
    CostLedger().record_event(
        operation="plan_quota_completion",
        provider="claude",
        cost_usd=0.0,
        idempotency_key="wallet-plan-zero",
    )

    ResearchReservationStore().reserve(
        reservation_id="wallet-after-plan",
        job_id="wallet-after-plan-job",
        reserved_cost=2.0,
        max_daily_cost=100.0,
        max_weekly_cost=100.0,
        max_monthly_cost=100.0,
    )


def test_dispatch_mark_refuses_a_reservation_from_another_wallet() -> None:
    first_id = _activate_spend_wallet(50.0, baseline_usd=0.0)
    store = ResearchReservationStore()
    store.reserve(
        reservation_id="first-wallet-hold",
        job_id="first-wallet-job",
        reserved_cost=0.5,
        max_daily_cost=100.0,
        max_weekly_cost=100.0,
        max_monthly_cost=100.0,
    )
    second_id = _activate_spend_wallet(50.0, baseline_usd=0.0)
    assert first_id != second_id

    with pytest.raises(ResearchReservationLimitExceeded, match="authority changed"):
        store.mark_provider_work_may_have_run("first-wallet-hold")


def test_freeze_cannot_finish_between_authority_read_and_reservation_commit(monkeypatch) -> None:
    from deepr.cli.commands.budget import mutate_budget_config
    from deepr.core import cost_caps

    store = ResearchReservationStore()
    authority_read = Event()
    release_reservation = Event()
    freeze_started = Event()
    freeze_finished = Event()
    original_resolve = cost_caps.resolve_spend_policy

    def paused_resolve(*args, **kwargs):
        policy = original_resolve(*args, **kwargs)
        authority_read.set()
        assert release_reservation.wait(timeout=2)
        return policy

    monkeypatch.setattr(cost_caps, "resolve_spend_policy", paused_resolve)

    def reserve() -> None:
        from deepr.core.cost_caps import paid_api_provider_scope

        with paid_api_provider_scope("openai"):
            store.reserve(
                reservation_id="linearized-reservation",
                job_id="linearized-job",
                reserved_cost=0.25,
                max_daily_cost=10.0,
                max_weekly_cost=200.0,
                max_monthly_cost=200.0,
            )

    def freeze() -> None:
        freeze_started.set()

        def update(config):
            config["paid_api_frozen"] = True
            config["freeze_reason"] = "race test"

        mutate_budget_config(update)
        freeze_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        reserve_future = executor.submit(reserve)
        assert authority_read.wait(timeout=2)
        freeze_future = executor.submit(freeze)
        assert freeze_started.wait(timeout=2)
        assert freeze_finished.wait(timeout=0.05) is False
        release_reservation.set()
        reserve_future.result(timeout=2)
        freeze_future.result(timeout=2)

    assert freeze_finished.is_set()
    with pytest.raises(ResearchReservationLimitExceeded):
        store.reserve(
            reservation_id="post-freeze",
            job_id="post-freeze-job",
            reserved_cost=0.01,
            max_daily_cost=10.0,
            max_weekly_cost=200.0,
            max_monthly_cost=200.0,
        )


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


def test_legacy_reservation_metadata_without_provider_bound_version_is_not_restored() -> None:
    restored = restore_research_cost_reservation(
        job_id="legacy-job",
        metadata={
            "cost_reservation_id": "legacy-reservation",
            "cost_reservation_estimated_usd": 1.0,
            "cost_reservation_provider": "openai",
            "cost_reservation_model": "test-model",
        },
        provider="openai",
        model="test-model",
    )

    assert restored is None


@pytest.mark.parametrize("estimated_cost", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_reservation_metadata_is_not_restored(estimated_cost: float) -> None:
    restored = restore_research_cost_reservation(
        job_id="corrupted-job",
        metadata={
            "cost_reservation_authority_version": "provider-request-bound-v2",
            "cost_reservation_id": "corrupted-reservation",
            "cost_reservation_estimated_usd": estimated_cost,
            "cost_reservation_provider": "openai",
            "cost_reservation_model": "test-model",
            "cost_reservation_dispatch_binding_id": "a" * 64,
            "cost_reservation_request_envelope_sha256": "b" * 64,
        },
        provider="openai",
        model="test-model",
    )

    assert restored is None


def test_legacy_reservation_schema_migrates_but_cannot_mint_bound_dispatch(tmp_path: Path) -> None:
    database = tmp_path / "legacy-reservations.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE research_cost_reservations (
                reservation_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL UNIQUE,
                reserved_cost REAL NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                actual_cost REAL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO research_cost_reservations
                (reservation_id, job_id, reserved_cost, state, created_at)
            VALUES ('legacy-id', 'legacy-job', 0.20, 'active', '2026-07-29T00:00:00+00:00')
            """
        )

    store = ResearchReservationStore(database)
    with sqlite3.connect(database) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(research_cost_reservations)")}
    assert {
        "provider_work_may_have_run",
        "provider",
        "model",
        "dispatch_binding_id",
        "request_envelope_sha256",
    } <= columns

    with pytest.raises(ResearchReservationStoreError, match="does not match"):
        store.mark_provider_work_may_have_run(
            "legacy-id",
            provider="openai",
            model="model",
            job_id="legacy-job",
            reserved_cost=0.20,
            dispatch_binding_id="a" * 64,
            request_envelope_sha256="b" * 64,
        )

    active = store.active_reservations()
    assert len(active) == 1
    assert active[0].provider_work_may_have_run is False


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
            "deepr.experts.research_cost_gate.bounded_research_cost_estimate",
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
