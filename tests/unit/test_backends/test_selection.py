"""Tests for deterministic backend selection."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deepr.backends.capacity import BackendKind, CostModel
from deepr.backends.eligibility import BackendEligibilityStatus
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedgerEvent,
    QuotaState,
    QuotaWindowKind,
)
from deepr.backends.research_backend import ResearchBackend
from deepr.backends.selection import (
    BackendQualityStatus,
    BackendSelectionStatus,
    select_capacity_backend,
)

T0 = datetime(2026, 6, 18, tzinfo=UTC)


def _local(backend_id: str = "local-a", *, available: bool = True) -> ResearchBackend:
    return ResearchBackend(
        backend_id=backend_id,
        name=backend_id,
        kind=BackendKind.LOCAL,
        cost_model=CostModel.OWNED_HARDWARE,
        available=available,
        requires_quota_ledger=False,
    )


def _plan(
    backend_id: str = "plan-a",
    *,
    cost_model: CostModel = CostModel.CREDIT_POOL,
    available: bool = True,
) -> ResearchBackend:
    return ResearchBackend(
        backend_id=backend_id,
        name=backend_id,
        kind=BackendKind.PLAN_QUOTA,
        cost_model=cost_model,
        available=available,
        requires_quota_ledger=True,
    )


def _metered(backend_id: str = "metered-a", *, available: bool = True) -> ResearchBackend:
    return ResearchBackend(
        backend_id=backend_id,
        name=backend_id,
        kind=BackendKind.API_METERED,
        cost_model=CostModel.METERED,
        available=available,
        requires_quota_ledger=False,
    )


def _quota_state(
    backend_id: str,
    *,
    remaining: float | None = 5,
    event_type: QuotaEventType = QuotaEventType.USAGE_OBSERVED,
    confidence: QuotaConfidence = QuotaConfidence.OBSERVED,
) -> QuotaState:
    event = QuotaLedgerEvent(
        backend_id=backend_id,
        account_id="account-a",
        event_type=event_type,
        timestamp=T0,
        cost_model=CostModel.CREDIT_POOL,
        window_kind=QuotaWindowKind.MONTHLY_CREDIT_POOL,
        units_remaining=remaining,
        unit_name="credits",
        remaining_confidence=confidence,
    )
    return QuotaState(
        backend_id=event.backend_id,
        account_id=event.account_id,
        latest_event=event,
        exhausted=event.event_type == QuotaEventType.EXHAUSTED,
        quarantined=event.event_type == QuotaEventType.QUARANTINED,
    )


class TestSelectCapacityBackend:
    def test_owned_capacity_wins_over_plan_and_metered(self):
        selection = select_capacity_backend(
            [_metered(), _plan(), _local()],
            quota_states=[_quota_state("plan-a")],
            allow_metered=True,
        )

        assert selection.status == BackendSelectionStatus.SELECTED
        assert selection.backend_id == "local-a"
        assert [candidate.backend.backend_id for candidate in selection.candidates] == [
            "local-a",
            "plan-a",
            "metered-a",
        ]

    def test_plan_quota_wins_when_local_is_unavailable(self):
        selection = select_capacity_backend(
            [_metered(), _plan(), _local(available=False)],
            quota_states=[_quota_state("plan-a")],
            allow_metered=True,
        )

        assert selection.backend_id == "plan-a"
        assert selection.selected is not None
        assert selection.selected.eligibility.account_id == "account-a"

    def test_metered_backend_requires_explicit_budget_gate(self):
        selection = select_capacity_backend([_metered()])

        assert selection.status == BackendSelectionStatus.NO_ELIGIBLE_BACKEND
        assert selection.backend_id == ""
        assert selection.candidates[0].eligibility.status == BackendEligibilityStatus.METERED_REQUIRES_BUDGET

    def test_metered_backend_can_be_selected_after_budget_gate(self):
        selection = select_capacity_backend([_metered()], allow_metered=True)

        assert selection.status == BackendSelectionStatus.SELECTED
        assert selection.backend_id == "metered-a"

    def test_plan_quota_requires_observed_state_by_default(self):
        selection = select_capacity_backend([_plan()])

        assert selection.status == BackendSelectionStatus.NO_ELIGIBLE_BACKEND
        assert selection.candidates[0].eligibility.status == BackendEligibilityStatus.QUOTA_UNKNOWN

    def test_quality_floor_skips_lower_quality_owned_capacity(self):
        selection = select_capacity_backend(
            [_local(), _plan()],
            quota_states=[_quota_state("plan-a")],
            quality_floor=0.8,
            quality_scores={"local-a": 0.7, "plan-a": 0.86},
        )

        assert selection.backend_id == "plan-a"
        assert selection.candidates[0].quality_gate.status == BackendQualityStatus.BELOW_FLOOR
        assert selection.candidates[1].quality_gate.status == BackendQualityStatus.PASSED

    def test_quality_floor_requires_measured_score(self):
        selection = select_capacity_backend([_local()], quality_floor=0.8)

        assert selection.status == BackendSelectionStatus.NO_ELIGIBLE_BACKEND
        assert selection.candidates[0].quality_gate.status == BackendQualityStatus.UNKNOWN

    def test_metered_is_last_resort_when_free_sources_fail_quality(self):
        selection = select_capacity_backend(
            [_metered(), _plan(), _local()],
            quota_states=[_quota_state("plan-a", event_type=QuotaEventType.EXHAUSTED, remaining=0)],
            allow_metered=True,
            quality_floor=0.75,
            quality_scores={"local-a": 0.5, "plan-a": 0.95, "metered-a": 0.9},
        )

        assert selection.backend_id == "metered-a"
        assert selection.candidates[0].quality_gate.status == BackendQualityStatus.BELOW_FLOOR
        assert selection.candidates[1].eligibility.status == BackendEligibilityStatus.QUOTA_EXHAUSTED

    def test_selection_reason_explains_no_routable_backend(self):
        selection = select_capacity_backend([_local()], quality_floor=0.9, quality_scores={"local-a": 0.4})

        assert selection.status == BackendSelectionStatus.NO_ELIGIBLE_BACKEND
        assert "local-a: eligible, below_floor" in selection.reason

    def test_dict_shape_includes_gate_details(self):
        selection = select_capacity_backend([_local()], quality_floor=0.6, quality_scores={"local-a": 0.7})

        data = selection.to_dict()

        assert data["status"] == "selected"
        assert data["backend_id"] == "local-a"
        assert data["selected"]["quality_gate"]["status"] == "passed"
        assert data["candidates"][0]["routable"] is True

    def test_backend_id_breaks_ties_inside_same_rung(self):
        selection = select_capacity_backend([_local("local-z"), _local("local-a")])

        assert selection.backend_id == "local-a"

    def test_plan_cost_model_orders_credit_pool_before_rolling_window(self):
        selection = select_capacity_backend(
            [
                _plan("rolling-a", cost_model=CostModel.ROLLING_WINDOW),
                _plan("credit-a", cost_model=CostModel.CREDIT_POOL),
            ],
            quota_states=[_quota_state("rolling-a"), _quota_state("credit-a")],
        )

        assert selection.backend_id == "credit-a"

    @pytest.mark.parametrize(
        ("floor", "scores"),
        [
            (-0.1, {}),
            (1.1, {}),
            (None, {"local-a": -0.1}),
            (None, {"local-a": 1.1}),
        ],
    )
    def test_quality_scores_must_be_probability_values(self, floor, scores):
        with pytest.raises(ValueError, match="between 0 and 1"):
            select_capacity_backend([_local()], quality_floor=floor, quality_scores=scores)
