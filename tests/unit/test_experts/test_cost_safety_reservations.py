"""Tests for the cost-safety reservation pattern and absolute ceilings.

Covers the changes from the bug-hunt pass:
- ``ABSOLUTE_MAX_*`` class constants (used by mcp/server.py and cli/budget.py).
- Atomic ``check_and_reserve`` + ``record_cost(reservation_id=...)`` settling.
- ``refund_reservation`` releases the in-flight pool without billing.
- Reservation pool is consulted in subsequent ``check_operation`` calls so
  N parallel callers cannot over-commit against the daily cap.
"""

from __future__ import annotations

import time

import pytest

from deepr.experts.cost_circuit_breaker import CostCircuitBreaker
from deepr.experts.cost_safety import CostSafetyManager


@pytest.fixture
def manager():
    m = CostSafetyManager()
    # Keep tests deterministic: tight daily cap with circuit breaker
    # large enough not to interfere.
    m.max_daily = 10.0
    m.max_monthly = 100.0
    return m


class TestAbsoluteCeilings:
    def test_class_attributes_exist(self):
        # The MCP server / CLI both reference these without instantiation.
        assert CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION > 0
        assert CostSafetyManager.ABSOLUTE_MAX_DAILY > 0
        assert CostSafetyManager.ABSOLUTE_MAX_MONTHLY > 0

    def test_per_operation_ceiling_blocks_above_threshold(self, manager):
        too_big = CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION + 1.0
        allowed, reason, _, _ = manager.check_and_reserve(
            session_id="s1",
            operation_type="research",
            estimated_cost=too_big,
            reserve=False,
        )
        assert allowed is False
        assert "absolute per-op ceiling" in reason


class TestReservationFlow:
    def test_reserve_returns_reservation_id(self, manager):
        allowed, _, _, rid = manager.check_and_reserve(
            session_id="s1",
            operation_type="research",
            estimated_cost=1.0,
        )
        assert allowed is True
        assert rid  # non-empty

    def test_record_cost_settles_reservation(self, manager):
        allowed, _, _, rid = manager.check_and_reserve(
            session_id="s1",
            operation_type="research",
            estimated_cost=2.0,
        )
        assert allowed
        # Reservation should hold the projected daily spend
        assert manager._reserved_daily == 2.0

        manager.record_cost(
            session_id="s1",
            operation_type="research",
            actual_cost=1.75,
            reservation_id=rid,
        )
        # Reservation released; actual spend committed
        assert manager._reserved_daily == 0.0
        assert manager.daily_cost == pytest.approx(1.75)

    def test_refund_reservation_releases_without_billing(self, manager):
        _, _, _, rid = manager.check_and_reserve(
            session_id="s1",
            operation_type="research",
            estimated_cost=3.0,
        )
        manager.refund_reservation(rid)
        assert manager._reserved_daily == 0.0
        assert manager.daily_cost == 0.0

    def test_parallel_reservations_block_over_commit(self, manager):
        """Two checks against the same daily cap can't both pass when the
        sum of estimates would exceed the cap. This is the core scout
        finding the lock+reservation pattern fixes."""
        manager.max_daily = 5.0
        # First call reserves 4.0
        a_allowed, _, _, a_id = manager.check_and_reserve(session_id="s1", operation_type="r", estimated_cost=4.0)
        # Second call estimates 2.0 - should be rejected because the
        # first call's reservation is still in flight.
        b_allowed, b_reason, _, _ = manager.check_and_reserve(session_id="s2", operation_type="r", estimated_cost=2.0)
        assert a_allowed is True
        assert b_allowed is False
        assert "Daily limit" in b_reason
        # Settle the first reservation as $0 actual; second can now run.
        manager.record_cost(session_id="s1", operation_type="r", actual_cost=0.0, reservation_id=a_id)
        c_allowed, _, _, _ = manager.check_and_reserve(session_id="s2", operation_type="r", estimated_cost=2.0)
        assert c_allowed is True

    def test_circuit_breaker_counts_in_flight_reservations(self):
        breaker = CostCircuitBreaker(
            cost_threshold=1.0,
            event_threshold=2,
            max_single_cost=1.0,
            window_seconds=300.0,
            cooldown_seconds=60.0,
        )
        manager = CostSafetyManager(circuit_breaker=breaker)
        manager.max_daily = 10.0
        manager.max_monthly = 10.0

        first = manager.check_and_reserve(session_id="s1", operation_type="r", estimated_cost=0.5)
        second = manager.check_and_reserve(session_id="s2", operation_type="r", estimated_cost=0.5)
        third = manager.check_and_reserve(session_id="s3", operation_type="r", estimated_cost=0.5)

        assert first[0] is True
        assert second[0] is True
        assert third[0] is False
        assert "threshold" in third[1].lower()
        assert manager._reserved_daily == pytest.approx(1.0)


class TestMonthlyReservationSymmetry:
    """The monthly projection must count in-flight reservations exactly as the
    daily one does. Without this, when the *monthly* reserve is the binding
    constraint (the $20/month fleet case, where daily headroom is large), N
    parallel checks all read the same stale monthly_cost, all pass, and the
    pool over-commits by up to N times. This is the primary over-spend path for
    a low monthly reserve, so it gets the same lock+reservation guard as daily.
    """

    def test_record_cost_settles_monthly_reservation(self, manager):
        allowed, _, _, rid = manager.check_and_reserve(session_id="s1", operation_type="research", estimated_cost=2.0)
        assert allowed
        assert manager._reserved_monthly == 2.0

        manager.record_cost(session_id="s1", operation_type="research", actual_cost=1.75, reservation_id=rid)
        assert manager._reserved_monthly == 0.0
        assert manager.monthly_cost == pytest.approx(1.75)

    def test_refund_reservation_releases_monthly_without_billing(self, manager):
        _, _, _, rid = manager.check_and_reserve(session_id="s1", operation_type="research", estimated_cost=3.0)
        manager.refund_reservation(rid)
        assert manager._reserved_monthly == 0.0
        assert manager.monthly_cost == 0.0

    def test_parallel_reservations_block_over_commit_monthly(self, manager):
        """Daily roomy, monthly binding: the second parallel check must still
        be rejected because the first reservation counts against the monthly
        projection - symmetric with the daily guarantee above."""
        manager.max_daily = 100.0  # roomy, never the binding constraint here
        manager.max_monthly = 5.0  # the binding reserve
        a_allowed, _, _, a_id = manager.check_and_reserve(session_id="s1", operation_type="r", estimated_cost=4.0)
        b_allowed, b_reason, _, _ = manager.check_and_reserve(session_id="s2", operation_type="r", estimated_cost=2.0)
        assert a_allowed is True
        assert b_allowed is False
        assert "Monthly limit" in b_reason
        # Settle the first reservation as $0 actual; the second can now run.
        manager.record_cost(session_id="s1", operation_type="r", actual_cost=0.0, reservation_id=a_id)
        c_allowed, _, _, _ = manager.check_and_reserve(session_id="s2", operation_type="r", estimated_cost=2.0)
        assert c_allowed is True


class TestReservationTTL:
    """A reservation that is never settled or refunded (a caller crash between
    reserve and record) must not hold its slice of the pool forever - on a tight
    monthly reserve that silently starves the fleet. The TTL sweep releases it.
    """

    def test_stale_reservation_is_swept_on_next_check(self, manager):
        manager.max_daily = 5.0
        _, _, _, leaked = manager.check_and_reserve(session_id="s1", operation_type="r", estimated_cost=4.0)
        assert manager._reserved_daily == 4.0
        # Simulate a leak: backdate the reservation beyond the TTL.
        manager._reservation_started[leaked] = time.time() - manager.RESERVATION_TTL_SECONDS - 1
        # The next check sweeps it, so a fresh 4.0 reservation now fits.
        allowed, _, _, _ = manager.check_and_reserve(session_id="s2", operation_type="r", estimated_cost=4.0)
        assert allowed is True
        assert leaked not in manager._reservations
        assert leaked not in manager._reservation_started

    def test_live_reservation_is_not_swept(self, manager):
        manager.max_daily = 5.0
        _, _, _, fresh = manager.check_and_reserve(session_id="s1", operation_type="r", estimated_cost=4.0)
        # Still within TTL -> a parallel over-commit is still correctly blocked.
        allowed, reason, _, _ = manager.check_and_reserve(session_id="s2", operation_type="r", estimated_cost=4.0)
        assert allowed is False
        assert "Daily limit" in reason
        assert fresh in manager._reservations  # not swept

    def test_sweep_refunds_both_daily_and_monthly(self, manager):
        manager.check_and_reserve(session_id="s1", operation_type="r", estimated_cost=3.0)
        assert manager._reserved_daily == 3.0
        assert manager._reserved_monthly == 3.0

        manager._sweep_stale_reservations(time.time() + manager.RESERVATION_TTL_SECONDS + 10)

        assert manager._reserved_daily == 0.0
        assert manager._reserved_monthly == 0.0
        assert manager._reservations == {}
        assert manager._reservation_started == {}

    def test_settling_clears_the_timestamp(self, manager):
        _, _, _, rid = manager.check_and_reserve(session_id="s1", operation_type="r", estimated_cost=2.0)
        assert rid in manager._reservation_started
        manager.record_cost(session_id="s1", operation_type="r", actual_cost=1.0, reservation_id=rid)
        assert rid not in manager._reservation_started  # no orphan timestamp left behind


class TestLegacyCheckOperation:
    def test_check_operation_still_returns_three_tuple(self, manager):
        # Public API for older callers must remain (bool, str, bool).
        result = manager.check_operation(
            session_id="s1",
            operation_type="research",
            estimated_cost=0.5,
        )
        assert isinstance(result, tuple)
        assert len(result) == 3
        allowed, reason, needs_confirm = result
        assert allowed is True
        assert isinstance(reason, str)
        assert isinstance(needs_confirm, bool)
