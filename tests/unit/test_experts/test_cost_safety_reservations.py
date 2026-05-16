"""Tests for the cost-safety reservation pattern and absolute ceilings.

Covers the changes from the bug-hunt pass:
- ``ABSOLUTE_MAX_*`` class constants (used by mcp/server.py and cli/budget.py).
- Atomic ``check_and_reserve`` + ``record_cost(reservation_id=...)`` settling.
- ``refund_reservation`` releases the in-flight pool without billing.
- Reservation pool is consulted in subsequent ``check_operation`` calls so
  N parallel callers cannot over-commit against the daily cap.
"""

from __future__ import annotations

import pytest

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
        # Second call estimates 2.0 — should be rejected because the
        # first call's reservation is still in flight.
        b_allowed, b_reason, _, _ = manager.check_and_reserve(session_id="s2", operation_type="r", estimated_cost=2.0)
        assert a_allowed is True
        assert b_allowed is False
        assert "Daily limit" in b_reason
        # Settle the first reservation as $0 actual; second can now run.
        manager.record_cost(session_id="s1", operation_type="r", actual_cost=0.0, reservation_id=a_id)
        c_allowed, _, _, _ = manager.check_and_reserve(session_id="s2", operation_type="r", estimated_cost=2.0)
        assert c_allowed is True


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
