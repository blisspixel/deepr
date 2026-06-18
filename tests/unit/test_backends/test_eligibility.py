"""Tests for backend eligibility decisions."""

from __future__ import annotations

from datetime import UTC, datetime

from deepr.backends.capacity import BackendKind, CostModel
from deepr.backends.eligibility import BackendEligibilityStatus, evaluate_backend_eligibility
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedgerEvent,
    QuotaState,
    QuotaWindowKind,
)
from deepr.backends.research_backend import ResearchBackend

T0 = datetime(2026, 6, 18, tzinfo=UTC)


def _backend(
    backend_id: str = "codex",
    *,
    kind: BackendKind = BackendKind.PLAN_QUOTA,
    cost_model: CostModel = CostModel.ROLLING_WINDOW,
    available: bool = True,
    detail: str = "",
    task_classes: tuple[str, ...] = (),
    requires_quota_ledger: bool = True,
) -> ResearchBackend:
    return ResearchBackend(
        backend_id=backend_id,
        name=backend_id,
        kind=kind,
        cost_model=cost_model,
        available=available,
        detail=detail,
        task_classes=task_classes,
        requires_quota_ledger=requires_quota_ledger,
    )


def _event(
    backend_id: str = "codex",
    event_type: QuotaEventType = QuotaEventType.USAGE_OBSERVED,
    *,
    account_id: str = "",
    remaining: float | None = 5.0,
    confidence: QuotaConfidence = QuotaConfidence.OBSERVED,
    overage_enabled: bool | None = None,
    reserve_floor_fraction: float | None = None,
    metadata: dict[str, object] | None = None,
) -> QuotaLedgerEvent:
    return QuotaLedgerEvent(
        backend_id=backend_id,
        account_id=account_id,
        event_type=event_type,
        timestamp=T0,
        cost_model=CostModel.ROLLING_WINDOW,
        window_kind=QuotaWindowKind.ROLLING_5H,
        units_remaining=remaining,
        unit_name="compute_units",
        remaining_confidence=confidence,
        overage_enabled=overage_enabled,
        reserve_floor_fraction=reserve_floor_fraction,
        metadata=metadata or {},
    )


def _state(event: QuotaLedgerEvent) -> QuotaState:
    return QuotaState(
        backend_id=event.backend_id,
        account_id=event.account_id,
        latest_event=event,
        exhausted=event.event_type == QuotaEventType.EXHAUSTED,
        quarantined=event.event_type == QuotaEventType.QUARANTINED,
    )


class TestBackendEligibility:
    def test_local_backend_needs_no_quota_state(self):
        backend = _backend(
            "ollama",
            kind=BackendKind.LOCAL,
            cost_model=CostModel.OWNED_HARDWARE,
            requires_quota_ledger=False,
        )

        decision = evaluate_backend_eligibility(backend)

        assert decision.eligible
        assert decision.status == BackendEligibilityStatus.ELIGIBLE
        assert decision.to_dict()["quota_state"] is None

    def test_unavailable_backend_is_blocked(self):
        decision = evaluate_backend_eligibility(_backend(available=False, detail="not installed"))

        assert not decision.eligible
        assert decision.status == BackendEligibilityStatus.UNAVAILABLE
        assert "not installed" in decision.reason

    def test_task_class_restriction_blocks_backend(self):
        decision = evaluate_backend_eligibility(_backend(task_classes=("sync",)), task_class="absorb")

        assert not decision.eligible
        assert decision.status == BackendEligibilityStatus.TASK_UNSUPPORTED

    def test_metered_backend_requires_explicit_budget_gate(self):
        backend = _backend(
            "openai",
            kind=BackendKind.API_METERED,
            cost_model=CostModel.METERED,
            requires_quota_ledger=False,
        )

        blocked = evaluate_backend_eligibility(backend)
        allowed = evaluate_backend_eligibility(backend, allow_metered=True)

        assert blocked.status == BackendEligibilityStatus.METERED_REQUIRES_BUDGET
        assert allowed.eligible

    def test_plan_quota_without_observation_is_unknown(self):
        decision = evaluate_backend_eligibility(_backend())

        assert not decision.eligible
        assert decision.status == BackendEligibilityStatus.QUOTA_UNKNOWN

    def test_plan_quota_with_observed_remaining_units_is_eligible(self):
        state = _state(_event())

        decision = evaluate_backend_eligibility(_backend(), quota_states=[state])

        assert decision.eligible
        assert decision.account_id == ""
        assert decision.quota_state == state

    def test_exhausted_quota_is_blocked(self):
        state = _state(_event(event_type=QuotaEventType.EXHAUSTED, remaining=0))

        decision = evaluate_backend_eligibility(_backend(), quota_states=[state])

        assert not decision.eligible
        assert decision.status == BackendEligibilityStatus.QUOTA_EXHAUSTED

    def test_quarantined_quota_is_blocked(self):
        state = _state(_event(event_type=QuotaEventType.QUARANTINED, remaining=None))

        decision = evaluate_backend_eligibility(_backend(), quota_states=[state])

        assert not decision.eligible
        assert decision.status == BackendEligibilityStatus.QUOTA_QUARANTINED

    def test_overage_enabled_is_blocked_before_quota_use(self):
        state = _state(_event(overage_enabled=True))

        decision = evaluate_backend_eligibility(_backend(), quota_states=[state])

        assert not decision.eligible
        assert decision.status == BackendEligibilityStatus.QUOTA_OVERAGE_ENABLED

    def test_unknown_remaining_quota_is_blocked(self):
        state = _state(_event(remaining=3, confidence=QuotaConfidence.UNKNOWN))

        decision = evaluate_backend_eligibility(_backend(), quota_states=[state])

        assert not decision.eligible
        assert decision.status == BackendEligibilityStatus.QUOTA_UNKNOWN

    def test_reserve_floor_is_blocked_from_total_units(self):
        state = _state(_event(remaining=10, reserve_floor_fraction=0.10, metadata={"units_total": 100}))

        decision = evaluate_backend_eligibility(_backend(), quota_states=[state])

        assert not decision.eligible
        assert decision.status == BackendEligibilityStatus.RESERVE_FLOOR_REACHED

    def test_reserve_floor_is_blocked_from_explicit_floor_units(self):
        state = _state(_event(remaining=2, metadata={"reserve_floor_units": 3}))

        decision = evaluate_backend_eligibility(_backend(), quota_states=[state])

        assert not decision.eligible
        assert decision.status == BackendEligibilityStatus.RESERVE_FLOOR_REACHED

    def test_multi_account_pool_prefers_an_eligible_account(self):
        exhausted = _state(_event(event_type=QuotaEventType.EXHAUSTED, account_id="personal", remaining=0))
        available = _state(_event(account_id="work", remaining=4))

        decision = evaluate_backend_eligibility(_backend(), quota_states=[exhausted, available])

        assert decision.eligible
        assert decision.account_id == "work"
