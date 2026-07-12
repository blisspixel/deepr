"""Tests for cost safety and circuit breaker utilities.

Tests the CostCircuitBreaker class and related cost control functions.
Includes property-based tests for circuit breaker behavior.

Requirements: 8.2 - Cost circuit breaker
"""

import os
import threading
import time
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from deepr.experts.cost_safety import (
    CircuitBreakerState,
    CostCircuitBreaker,
    CostEvent,
    CostLimitExceeded,
    create_default_circuit_breaker,
)


class TestCostCircuitBreaker:
    """Tests for CostCircuitBreaker class."""

    def test_init_defaults(self):
        """Test default initialization."""
        breaker = CostCircuitBreaker()

        assert breaker.cost_threshold == 10.0
        assert breaker.window_seconds == 300.0
        assert breaker.event_threshold == 50
        assert breaker.cooldown_seconds == 60.0
        assert breaker.max_single_cost == 5.0

    def test_init_custom_values(self):
        """Test custom initialization."""
        breaker = CostCircuitBreaker(
            cost_threshold=5.0, window_seconds=60.0, event_threshold=10, cooldown_seconds=30.0, max_single_cost=2.0
        )

        assert breaker.cost_threshold == 5.0
        assert breaker.window_seconds == 60.0
        assert breaker.event_threshold == 10
        assert breaker.cooldown_seconds == 30.0
        assert breaker.max_single_cost == 2.0

    def test_allow_request_initially(self):
        """Test that requests are allowed initially."""
        breaker = CostCircuitBreaker()

        allowed, reason = breaker.allow_request()
        assert allowed
        assert reason is None

    def test_allow_request_with_estimated_cost(self):
        """Test allow_request with estimated cost."""
        breaker = CostCircuitBreaker(cost_threshold=1.0)

        # Should allow small cost
        allowed, reason = breaker.allow_request(estimated_cost=0.5)
        assert allowed

        # Should deny if would exceed threshold
        breaker.record_cost(0.6, "test")
        allowed, reason = breaker.allow_request(estimated_cost=0.5)
        assert not allowed
        assert "exceed cost threshold" in reason.lower()

    def test_record_cost_under_threshold(self):
        """Test recording cost under threshold."""
        breaker = CostCircuitBreaker(cost_threshold=10.0)

        result = breaker.record_cost(1.0, "test_operation")
        assert result is True  # Circuit still closed

        state = breaker.get_state()
        assert state.is_closed
        assert state.total_cost_window == 1.0

    def test_record_cost_exceeds_threshold(self):
        """Test that exceeding cost threshold trips breaker."""
        breaker = CostCircuitBreaker(cost_threshold=1.0)

        # Record costs that exceed threshold
        breaker.record_cost(0.5, "op1")
        breaker.record_cost(0.5, "op2")
        result = breaker.record_cost(0.5, "op3")  # This exceeds $1.0

        assert result is False  # Circuit tripped

        state = breaker.get_state()
        assert state.is_open
        assert "Cost threshold exceeded" in state.reason

    def test_record_cost_exceeds_event_threshold(self):
        """Test that exceeding event threshold trips breaker."""
        breaker = CostCircuitBreaker(event_threshold=3)

        breaker.record_cost(0.01, "op1")
        breaker.record_cost(0.01, "op2")
        breaker.record_cost(0.01, "op3")
        result = breaker.record_cost(0.01, "op4")  # Exceeds 3 events

        assert result is False

        state = breaker.get_state()
        assert state.is_open
        assert "Event threshold exceeded" in state.reason

    def test_single_operation_limit(self):
        """Test that single operation limit is enforced."""
        breaker = CostCircuitBreaker(max_single_cost=1.0)

        # Should deny expensive single operation
        allowed, reason = breaker.allow_request(estimated_cost=2.0)
        assert not allowed
        assert "Single operation cost" in reason

    def test_circuit_open_denies_requests(self):
        """Test that open circuit denies all requests."""
        breaker = CostCircuitBreaker(cost_threshold=0.5)

        # Trip the breaker
        breaker.record_cost(0.6, "expensive_op")

        # Should deny new requests
        allowed, reason = breaker.allow_request()
        assert not allowed
        assert "Circuit breaker open" in reason

    def test_manual_reset(self):
        """Test manual reset of circuit breaker."""
        breaker = CostCircuitBreaker(cost_threshold=0.5)

        # Trip the breaker
        breaker.record_cost(0.6, "expensive_op")
        assert breaker.get_state().is_open

        # Reset
        breaker.reset()

        state = breaker.get_state()
        assert state.is_closed
        assert state.reason is None

    def test_force_open(self):
        """Test forcing circuit breaker open."""
        breaker = CostCircuitBreaker()

        breaker.force_open("Manual override for testing")

        state = breaker.get_state()
        assert state.is_open
        assert "Manual override" in state.reason

    def test_auto_reset_after_cooldown(self):
        """Test automatic reset after cooldown period."""
        breaker = CostCircuitBreaker(
            cost_threshold=0.5,
            cooldown_seconds=0.1,  # Very short for testing
        )

        # Trip the breaker
        breaker.record_cost(0.6, "expensive_op")
        assert breaker.get_state().is_open

        # Wait for cooldown
        time.sleep(0.15)

        # Should auto-reset
        state = breaker.get_state()
        assert state.is_closed

    def test_get_recent_events(self):
        """Test getting recent cost events."""
        breaker = CostCircuitBreaker()

        breaker.record_cost(0.1, "op1", job_id="job-1")
        breaker.record_cost(0.2, "op2", job_id="job-2")
        breaker.record_cost(0.3, "op3", job_id="job-3")

        events = breaker.get_recent_events(limit=2)

        assert len(events) == 2
        assert events[0].cost == 0.2
        assert events[1].cost == 0.3

    def test_events_pruned_outside_window(self):
        """Test that old events are pruned."""
        breaker = CostCircuitBreaker(window_seconds=0.1)

        breaker.record_cost(0.5, "old_op")

        # Wait for event to age out
        time.sleep(0.15)

        # New state should show 0 cost
        state = breaker.get_state()
        assert state.total_cost_window == 0.0
        assert state.event_count_window == 0


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState dataclass."""

    def test_is_closed_when_not_open(self):
        """Test is_closed property."""
        state = CircuitBreakerState(
            is_open=False,
            reason=None,
            opened_at=None,
            total_cost_window=0.0,
            event_count_window=0,
            cooldown_remaining=0.0,
        )
        assert state.is_closed

    def test_is_closed_when_open(self):
        """Test is_closed when circuit is open."""
        state = CircuitBreakerState(
            is_open=True,
            reason="Test",
            opened_at=time.time(),
            total_cost_window=10.0,
            event_count_window=5,
            cooldown_remaining=30.0,
        )
        assert not state.is_closed


class TestCostEvent:
    """Tests for CostEvent dataclass."""

    def test_cost_event_creation(self):
        """Test creating a cost event."""
        event = CostEvent(timestamp=time.time(), cost=0.15, operation="research_job", job_id="job-123")

        assert event.cost == 0.15
        assert event.operation == "research_job"
        assert event.job_id == "job-123"

    def test_cost_event_optional_job_id(self):
        """Test cost event without job_id."""
        event = CostEvent(timestamp=time.time(), cost=0.10, operation="test")

        assert event.job_id is None


class TestCostLimitExceeded:
    """Tests for CostLimitExceeded exception."""

    def test_exception_message(self):
        """Test exception message."""
        exc = CostLimitExceeded("Cost limit exceeded")
        assert str(exc) == "Cost limit exceeded"

    def test_exception_with_state(self):
        """Test exception with state."""
        state = CircuitBreakerState(
            is_open=True,
            reason="Test",
            opened_at=time.time(),
            total_cost_window=10.0,
            event_count_window=5,
            cooldown_remaining=30.0,
        )
        exc = CostLimitExceeded("Cost limit exceeded", state=state)

        assert exc.state is not None
        assert exc.state.is_open


class TestCreateDefaultCircuitBreaker:
    """Tests for create_default_circuit_breaker function."""

    def test_creates_breaker_with_defaults(self):
        """Test that default breaker has sensible values."""
        breaker = create_default_circuit_breaker()

        assert breaker.cost_threshold == 10.0
        assert breaker.window_seconds == 300.0
        assert breaker.event_threshold == 50
        assert breaker.cooldown_seconds == 60.0
        assert breaker.max_single_cost == 5.0


class TestPropertyBasedCircuitBreaker:
    """Property-based tests for circuit breaker."""

    @given(st.floats(min_value=0.01, max_value=100.0))
    @settings(max_examples=50)
    def test_cost_threshold_respected(self, threshold: float):
        """Property: Circuit trips when cost exceeds threshold."""
        breaker = CostCircuitBreaker(cost_threshold=threshold)

        # Record cost just over threshold
        breaker.record_cost(threshold + 0.01, "test")

        state = breaker.get_state()
        assert state.is_open

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_event_threshold_respected(self, threshold: int):
        """Property: Circuit trips when events exceed threshold."""
        breaker = CostCircuitBreaker(
            event_threshold=threshold,
            cost_threshold=1000.0,  # High to not interfere
        )

        # Record events up to and over threshold
        for i in range(threshold + 1):
            breaker.record_cost(0.001, f"op{i}")

        state = breaker.get_state()
        assert state.is_open

    @given(st.floats(min_value=0.01, max_value=10.0))
    @settings(max_examples=50)
    def test_single_cost_limit_enforced(self, max_single: float):
        """Property: Single operation limit is enforced."""
        breaker = CostCircuitBreaker(max_single_cost=max_single)

        # Should deny operation over limit
        allowed, reason = breaker.allow_request(estimated_cost=max_single + 0.01)
        assert not allowed
        assert "Single operation" in reason

    @given(st.lists(st.floats(min_value=0.01, max_value=1.0), min_size=1, max_size=20))
    @settings(max_examples=50)
    def test_total_cost_tracked_correctly(self, costs: list):
        """Property: Total cost in window is sum of recorded costs."""
        breaker = CostCircuitBreaker(
            cost_threshold=1000.0,  # High to not trip
            event_threshold=1000,  # High to not trip
        )

        for i, cost in enumerate(costs):
            breaker.record_cost(cost, f"op{i}")

        state = breaker.get_state()
        expected_total = sum(costs)

        # Allow small floating point tolerance
        assert abs(state.total_cost_window - expected_total) < 0.001

    @given(st.floats(min_value=0.01, max_value=1.0))
    @settings(max_examples=50)
    def test_reset_clears_state(self, cost: float):
        """Property: Reset clears circuit breaker state."""
        breaker = CostCircuitBreaker(cost_threshold=0.001)

        # Trip the breaker
        breaker.record_cost(cost, "test")
        assert breaker.get_state().is_open

        # Reset
        breaker.reset()

        state = breaker.get_state()
        assert state.is_closed
        assert state.reason is None


# Import new classes for testing
from deepr.experts.cost_safety import CostSafetyManager, get_cost_safety_manager, reset_cost_safety_manager
from deepr.experts.cost_safety_ledger import DurableCostReservationError


class TestCostSafetyManager:
    """Tests for CostSafetyManager class."""

    def test_init_default_circuit_breaker(self):
        """Test initialization with default circuit breaker."""
        manager = CostSafetyManager()

        assert manager.circuit_breaker is not None
        assert manager.circuit_breaker.cost_threshold == 10.0

    def test_init_custom_circuit_breaker(self):
        """Test initialization with custom circuit breaker."""
        custom_breaker = CostCircuitBreaker(cost_threshold=5.0)
        manager = CostSafetyManager(circuit_breaker=custom_breaker)

        assert manager.circuit_breaker.cost_threshold == 5.0

    def test_check_operation_allowed(self):
        """Test check_operation when operation is allowed."""
        manager = CostSafetyManager()

        allowed, reason, needs_confirm = manager.check_operation(
            session_id="test-session", operation_type="research_submit", estimated_cost=0.50
        )

        assert allowed
        assert reason == "OK"
        assert not needs_confirm

    def test_check_operation_blocked_by_circuit_breaker(self):
        """Test check_operation when circuit breaker blocks."""
        breaker = CostCircuitBreaker(cost_threshold=0.1)
        manager = CostSafetyManager(circuit_breaker=breaker)

        # Trip the breaker
        breaker.record_cost(0.2, "expensive_op")

        allowed, reason, needs_confirm = manager.check_operation(
            session_id="test-session", operation_type="research_submit", estimated_cost=0.50
        )

        assert not allowed
        assert "Circuit breaker open" in reason
        assert not needs_confirm

    def test_check_operation_high_cost_confirmation(self):
        """Test that high-cost operations request confirmation."""
        manager = CostSafetyManager()

        allowed, reason, needs_confirm = manager.check_operation(
            session_id="test-session", operation_type="research_submit", estimated_cost=2.0, require_confirmation=True
        )

        assert allowed
        assert "High cost" in reason
        assert needs_confirm

    def test_record_cost_tracks_session(self):
        """Test that record_cost tracks session costs."""
        manager = CostSafetyManager()

        manager.record_cost(session_id="session-1", operation_type="research_submit", actual_cost=0.50)
        manager.record_cost(session_id="session-1", operation_type="research_submit", actual_cost=0.30)

        assert manager.get_session_cost("session-1") == 0.80

    def test_record_cost_separate_sessions(self):
        """Test that sessions are tracked separately."""
        manager = CostSafetyManager()

        manager.record_cost("session-1", "op", 0.50)
        manager.record_cost("session-2", "op", 0.30)

        assert manager.get_session_cost("session-1") == 0.50
        assert manager.get_session_cost("session-2") == 0.30

    @pytest.mark.parametrize(
        "invalid_cost",
        [True, False, "0.1", None, float("nan"), float("inf"), float("-inf"), -0.01],
    )
    def test_check_and_reserve_rejects_invalid_money(self, invalid_cost):
        manager = CostSafetyManager()

        with pytest.raises(ValueError, match="finite non-negative"):
            manager.check_and_reserve("session-1", "research", invalid_cost)

        assert manager._reservations == {}
        assert manager._reserved_daily == 0.0

    @pytest.mark.parametrize(
        "invalid_cost",
        [True, False, "0.1", None, float("nan"), float("inf"), float("-inf"), -0.01],
    )
    def test_record_cost_rejects_invalid_money_before_accounting(self, invalid_cost):
        manager = CostSafetyManager()
        _allowed, _reason, _confirm, reservation_id = manager.check_and_reserve(
            "session-1",
            "research",
            1.0,
        )

        with pytest.raises(ValueError, match="finite non-negative"):
            manager.record_cost(
                "session-1",
                "research",
                invalid_cost,
                reservation_id=reservation_id,
            )

        assert manager.daily_cost == 0.0
        assert manager.get_session_cost("session-1") == 0.0
        assert manager._reserved_daily == 1.0
        assert manager._ledger.get_events() == []
        manager.refund_reservation(reservation_id)

    def test_required_fsync_replay_settles_process_counters_once(self, monkeypatch, tmp_path):
        from deepr.experts.cost_safety_ledger import CostLedgerCommitError

        manager = CostSafetyManager()
        _allowed, _reason, _confirm, reservation_id = manager.check_and_reserve(
            "session-1",
            "research",
            1.0,
        )
        real_fsync = os.fsync
        calls = 0

        def fail_once(fd):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError(5, "durability unavailable", str(tmp_path / "private"))
            real_fsync(fd)

        monkeypatch.setattr(os, "fsync", fail_once)
        kwargs = {
            "session_id": "session-1",
            "operation_type": "research",
            "actual_cost": 0.1,
            "idempotency_key": "required-replay",
            "reservation_id": reservation_id,
            "require_ledger": True,
        }

        with pytest.raises(CostLedgerCommitError):
            manager.record_cost(**kwargs)

        assert manager.daily_cost == 0.0
        assert manager._reserved_daily == 1.0

        manager.record_cost(**kwargs)
        manager.record_cost(**{**kwargs, "reservation_id": ""})

        assert calls == 3
        assert manager.daily_cost == pytest.approx(0.1)
        assert manager.monthly_cost == pytest.approx(0.1)
        assert manager.get_session_cost("session-1") == pytest.approx(0.1)
        assert manager._reserved_daily == 0.0
        assert len(manager._ledger.get_events()) == 1

    def test_durable_duplicate_from_another_manager_does_not_increment_local_totals(self):
        first = CostSafetyManager()
        first.record_cost(
            session_id="shared-session",
            operation_type="research",
            actual_cost=0.1,
            idempotency_key="shared-durable-event",
        )
        second = CostSafetyManager()
        _allowed, _reason, _confirm, reservation_id = second.check_and_reserve(
            "shared-session",
            "research",
            1.0,
        )

        second.record_cost(
            session_id="shared-session",
            operation_type="research",
            actual_cost=0.1,
            idempotency_key="shared-durable-event",
            reservation_id=reservation_id,
        )

        assert second.daily_cost == 0.0
        assert second.monthly_cost == 0.0
        assert second.get_session_cost("shared-session") == 0.0
        assert second._reserved_daily == 0.0
        assert second.circuit_breaker.get_recent_events() == []

    def test_durable_reservations_serialize_budget_across_managers(self):
        first = CostSafetyManager()
        second = CostSafetyManager()
        first.max_daily = second.max_daily = 1.0
        first.max_monthly = second.max_monthly = 1.0

        allowed, _, _, first_id = first.check_and_reserve(
            "first-session",
            "council_consult",
            0.8,
            durable_reservation=True,
            reservation_job_id="council_first",
        )
        denied, reason, _, second_id = second.check_and_reserve(
            "second-session",
            "council_consult",
            0.3,
            durable_reservation=True,
            reservation_job_id="council_second",
        )

        assert allowed is True
        assert denied is False
        assert "Daily limit $1.00 would be exceeded" in reason
        assert second_id == ""
        assert first._get_reservation_store().active_cost() == pytest.approx(0.8)
        first.refund_reservation(first_id, provider_work_did_not_run=True)

    def test_durable_reserve_includes_existing_canonical_ledger_spend(self):
        first = CostSafetyManager()
        first.record_cost(
            session_id="prior-session",
            operation_type="research",
            actual_cost=0.8,
            idempotency_key="prior-canonical-spend",
            require_ledger=True,
        )
        second = CostSafetyManager()
        second.max_daily = 1.0
        second.max_monthly = 1.0

        allowed, reason, _, reservation_id = second.check_and_reserve(
            "new-session",
            "council_consult",
            0.3,
            durable_reservation=True,
            reservation_job_id="council_after_spend",
        )

        assert allowed is False
        assert "spent $0.80" in reason
        assert reservation_id == ""
        assert second._get_reservation_store().active_cost() == 0.0

    def test_malformed_canonical_ledger_fails_durable_reserve_closed(self):
        manager = CostSafetyManager()
        manager._ledger.ledger_path.write_text('{"broken":', encoding="utf-8")

        with pytest.raises(DurableCostReservationError, match="durable cost reservation failed"):
            manager.check_and_reserve(
                "malformed-session",
                "council_consult",
                0.2,
                durable_reservation=True,
                reservation_job_id="council_malformed",
            )

        assert manager._reservations == {}
        assert manager._reserved_daily == 0.0

    def test_concurrent_durable_reserve_and_settle_have_no_lock_order_cycle(self, monkeypatch):
        manager = CostSafetyManager()
        allowed, _, _, first_id = manager.check_and_reserve(
            "first-session",
            "council_consult",
            0.2,
            durable_reservation=True,
            reservation_job_id="council_lock_order_first",
        )
        assert allowed
        manager.mark_provider_work_may_have_run(first_id)
        store = manager._get_reservation_store()
        settlement_holds_sqlite = threading.Event()
        release_settlement = threading.Event()
        reserve_entered = threading.Event()
        errors: list[BaseException] = []
        second_reservation: list[str] = []
        real_record_event = manager._ledger.record_event
        real_reserve = store.reserve

        def blocked_record_event(*args, **kwargs):
            settlement_holds_sqlite.set()
            assert release_settlement.wait(timeout=2.0)
            return real_record_event(*args, **kwargs)

        def observed_reserve(**kwargs):
            reserve_entered.set()
            return real_reserve(**kwargs)

        monkeypatch.setattr(manager._ledger, "record_event", blocked_record_event)
        monkeypatch.setattr(store, "reserve", observed_reserve)

        def settle() -> None:
            try:
                manager.record_cost(
                    session_id="first-session",
                    operation_type="council_synthesis",
                    actual_cost=0.1,
                    idempotency_key="lock-order-settlement",
                    reservation_id=first_id,
                    require_ledger=True,
                )
            except BaseException as error:
                errors.append(error)

        def reserve() -> None:
            try:
                result = manager.check_and_reserve(
                    "second-session",
                    "council_consult",
                    0.2,
                    durable_reservation=True,
                    reservation_job_id="council_lock_order_second",
                )
                second_reservation.append(result[3])
            except BaseException as error:
                errors.append(error)

        settle_thread = threading.Thread(target=settle)
        reserve_thread = threading.Thread(target=reserve)
        settle_thread.start()
        assert settlement_holds_sqlite.wait(timeout=2.0)
        reserve_thread.start()
        assert reserve_entered.wait(timeout=2.0)
        release_settlement.set()
        settle_thread.join(timeout=2.0)
        reserve_thread.join(timeout=2.0)

        assert not settle_thread.is_alive()
        assert not reserve_thread.is_alive()
        assert errors == []
        assert second_reservation and second_reservation[0]
        manager.refund_reservation(second_reservation[0], provider_work_did_not_run=True)

    def test_get_session_cost_unknown_session(self):
        """Test get_session_cost for unknown session."""
        manager = CostSafetyManager()

        assert manager.get_session_cost("unknown") == 0.0

    def test_record_cost_writes_ledger_event(self):
        """record_cost should write canonical ledger event metadata."""
        with patch("deepr.experts.cost_safety.CostLedger") as mock_ledger_cls:
            manager = CostSafetyManager()
            mock_ledger = mock_ledger_cls.return_value

            manager.record_cost(
                session_id="session-1",
                operation_type="research_submit",
                actual_cost=0.42,
                details="test details",
                provider="openai",
                model="gpt-5.4",
                tokens_input=100,
                tokens_output=200,
                request_id="resp_123",
                source="unit.test",
                idempotency_key="k1",
            )

            mock_ledger.record_event.assert_called_once()
            kwargs = mock_ledger.record_event.call_args.kwargs
            assert kwargs["operation"] == "research_submit"
            assert kwargs["provider"] == "openai"
            assert kwargs["model"] == "gpt-5.4"
            assert kwargs["cost_usd"] == 0.42
            assert kwargs["session_id"] == "session-1"
            assert kwargs["request_id"] == "resp_123"
            assert kwargs["source"] == "unit.test"
            assert kwargs["idempotency_key"] == "k1"
            assert kwargs["metadata"]["details"] == "test details"

    def test_record_cost_strict_mode_raises_path_safe_ledger_error(self, monkeypatch, tmp_path):
        """Strict mode should fail fast when ledger write fails."""
        monkeypatch.setenv("DEEPR_COST_TRACKING_STRICT", "1")
        sensitive_path = tmp_path / "private" / "cost_ledger.jsonl"
        ledger_error = OSError(28, "No space left on device", str(sensitive_path))
        with patch("deepr.experts.cost_safety.CostLedger") as mock_ledger_cls:
            manager = CostSafetyManager()
            mock_ledger_cls.return_value.record_event.side_effect = ledger_error

            with pytest.raises(RuntimeError) as exc_info:
                manager.record_cost(
                    session_id="session-1",
                    operation_type="research_submit",
                    actual_cost=0.10,
                )

        public_error = exc_info.value
        assert str(public_error) == "Cost ledger write failed in strict mode."
        assert str(sensitive_path) not in str(public_error)
        assert public_error.__cause__ is ledger_error
        assert public_error.ledger_error is ledger_error
        assert public_error.metadata == {"error_type": "OSError", "errno": 28, "mode": "strict"}

    def test_record_cost_nonstrict_ledger_error_log_is_path_safe(self, monkeypatch, tmp_path, caplog):
        """Best-effort ledger failures must not place local paths in logs."""
        monkeypatch.delenv("DEEPR_COST_TRACKING_STRICT", raising=False)
        sensitive_path = tmp_path / "private" / "cost_ledger.jsonl"
        ledger_error = OSError(28, "No space left on device", str(sensitive_path))
        with patch("deepr.experts.cost_safety.CostLedger") as mock_ledger_cls:
            manager = CostSafetyManager()
            mock_ledger_cls.return_value.record_event.side_effect = ledger_error

            with caplog.at_level("WARNING", logger="deepr.experts.cost_safety_ledger"):
                manager.record_cost(
                    session_id="session-1",
                    operation_type="research_submit",
                    actual_cost=0.10,
                )

        assert str(sensitive_path) not in caplog.text
        assert "error_type=OSError, errno=28" in caplog.text

    def test_reset_clears_all_state(self):
        """Test that reset clears all tracking state."""
        manager = CostSafetyManager()

        manager.record_cost("session-1", "op", 0.50)
        manager.circuit_breaker.force_open("test")

        manager.reset()

        assert manager.get_session_cost("session-1") == 0.0
        assert manager.circuit_breaker.get_state().is_closed


class TestGetCostSafetyManager:
    """Tests for get_cost_safety_manager singleton function."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_cost_safety_manager()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_cost_safety_manager()

    def test_returns_manager_instance(self):
        """Test that function returns a CostSafetyManager."""
        manager = get_cost_safety_manager()

        assert isinstance(manager, CostSafetyManager)

    def test_returns_same_instance(self):
        """Test that function returns singleton instance."""
        manager1 = get_cost_safety_manager()
        manager2 = get_cost_safety_manager()

        assert manager1 is manager2

    def test_reset_creates_new_instance(self):
        """Test that reset allows new instance creation."""
        manager1 = get_cost_safety_manager()
        manager1.record_cost("test", "op", 1.0)

        reset_cost_safety_manager()

        manager2 = get_cost_safety_manager()

        # Should be different instance with fresh state
        assert manager2.get_session_cost("test") == 0.0


class TestResetCostSafetyManager:
    """Tests for reset_cost_safety_manager function."""

    def test_reset_clears_singleton(self):
        """Test that reset clears the singleton."""
        manager = get_cost_safety_manager()
        manager.record_cost("test", "op", 1.0)

        reset_cost_safety_manager()

        # New manager should have fresh state
        new_manager = get_cost_safety_manager()
        assert new_manager.get_session_cost("test") == 0.0

    def test_reset_safe_when_no_manager(self):
        """Test that reset is safe when no manager exists."""
        reset_cost_safety_manager()  # First reset
        reset_cost_safety_manager()  # Should not raise


class TestCostSessionHardCeiling:
    """CostSession.can_proceed must enforce the absolute per-op ceiling.

    Previously only CostSafetyManager.check_and_reserve enforced the $10
    ceiling; legacy callers using CostSession directly could approve a
    single operation above it as long as the session budget allowed.
    """

    def test_rejects_above_absolute_ceiling(self):
        from deepr.experts.cost_safety import CostSafetyManager, CostSession

        session = CostSession(
            session_id="test_ceiling",
            session_type="chat",
            budget_limit=100.0,  # plenty of session budget
        )
        over = CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION + 0.50
        ok, reason = session.can_proceed(over)
        assert ok is False
        assert "ceiling" in reason.lower()

    def test_allows_below_ceiling_within_budget(self):
        from deepr.experts.cost_safety import CostSession

        session = CostSession(
            session_id="test_ceiling_ok",
            session_type="chat",
            budget_limit=100.0,
        )
        ok, reason = session.can_proceed(5.0)
        assert ok is True
        assert reason == "OK"


class TestSpendingSummaryContract:
    """get_spending_summary is the contract `deepr budget safety` renders.

    The command crashed with KeyError('percent_used') because the summary
    lacked the fields the renderer reads - found live, 2026-06-12. These
    tests pin the full rendered contract.
    """

    def test_summary_carries_rendered_fields(self):
        from deepr.experts.cost_safety import CostSafetyManager

        manager = CostSafetyManager()
        manager.daily_cost = 2.0
        manager.monthly_cost = 20.0
        summary = manager.get_spending_summary()

        for bucket in ("daily", "monthly"):
            for key in ("spent", "limit", "remaining", "percent_used"):
                assert key in summary[bucket], f"{bucket}.{key} missing"
        assert summary["limits"]["per_operation"] == CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION
        assert summary["limits"]["daily"] == manager.max_daily
        assert summary["limits"]["monthly"] == manager.max_monthly
        assert summary["daily"]["percent_used"] == pytest.approx(2.0 / manager.max_daily * 100)

    def test_percent_used_zero_limit_is_safe(self):
        from deepr.experts.cost_safety import CostSafetyManager

        manager = CostSafetyManager()
        manager.max_daily = 0.0
        assert manager.get_spending_summary()["daily"]["percent_used"] == 0.0

    def test_env_caps_apply_to_safety_manager(self, monkeypatch):
        from deepr.experts.cost_safety import CostSafetyManager

        monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "1.00")
        monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "25.00")
        manager = CostSafetyManager()
        assert manager.max_daily == 1.0
        assert manager.max_monthly == 25.0

    def test_env_caps_invalid_or_oversized_fall_back(self, monkeypatch):
        from deepr.experts.cost_safety import CostSafetyManager

        monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "not-a-number")
        monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "999999")
        manager = CostSafetyManager()
        assert manager.max_daily == 50.0
        assert manager.max_monthly == CostSafetyManager.ABSOLUTE_MAX_MONTHLY

    @pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
    def test_env_caps_nonfinite_values_fall_back(self, monkeypatch, value):
        from deepr.experts.cost_safety import CostSafetyManager

        monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", value)
        monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", value)
        manager = CostSafetyManager()

        assert manager.max_daily == 50.0
        assert manager.max_monthly == 500.0
