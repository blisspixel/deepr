"""Tests for token budget allocation module.

Requirements: 1.3 - Test Coverage
"""

import pytest

from deepr.services.token_budget import (
    AllocationStrategy,
    BudgetPlan,
    BudgetTracker,
    PhaseAllocation,
    TokenBudgetAllocator,
)


class TestAllocationStrategy:
    """Tests for AllocationStrategy enum."""

    def test_all_strategies_exist(self):
        """Should have all expected strategies."""
        assert AllocationStrategy.EQUAL
        assert AllocationStrategy.WEIGHTED
        assert AllocationStrategy.FRONT_LOADED
        assert AllocationStrategy.BACK_LOADED
        assert AllocationStrategy.ADAPTIVE

    def test_strategy_values(self):
        """Should have correct string values."""
        assert AllocationStrategy.EQUAL.value == "equal"
        assert AllocationStrategy.WEIGHTED.value == "weighted"


class TestPhaseAllocation:
    """Tests for PhaseAllocation dataclass."""

    def test_create_allocation(self):
        """Should create allocation with defaults."""
        alloc = PhaseAllocation(phase=1, allocated=1000)

        assert alloc.phase == 1
        assert alloc.allocated == 1000
        assert alloc.used == 0
        assert alloc.remaining == 1000
        assert alloc.status == "pending"

    def test_remaining_calculated_on_init(self):
        """Should set remaining from allocated on init."""
        alloc = PhaseAllocation(phase=2, allocated=5000)

        assert alloc.remaining == 5000

    def test_custom_remaining(self):
        """Should preserve custom remaining if provided."""
        alloc = PhaseAllocation(phase=3, allocated=5000, remaining=3000)

        assert alloc.remaining == 3000

    def test_to_dict(self):
        """Should convert to dictionary."""
        alloc = PhaseAllocation(phase=1, allocated=1000, used=300)
        alloc.remaining = 700

        result = alloc.to_dict()

        assert result["phase"] == 1
        assert result["allocated"] == 1000
        assert result["used"] == 300
        assert result["remaining"] == 700
        assert result["utilization"] == 0.3
        assert result["status"] == "pending"


class TestBudgetPlan:
    """Tests for BudgetPlan dataclass."""

    def test_create_plan(self):
        """Should create budget plan."""
        phases = {
            1: PhaseAllocation(phase=1, allocated=3000),
            2: PhaseAllocation(phase=2, allocated=4000),
        }

        plan = BudgetPlan(
            total_budget=10000,
            synthesis_reserve=2000,
            phases=phases,
            strategy=AllocationStrategy.EQUAL,
        )

        assert plan.total_budget == 10000
        assert plan.synthesis_reserve == 2000
        assert len(plan.phases) == 2

    def test_total_used(self):
        """Should calculate total used tokens."""
        phases = {
            1: PhaseAllocation(phase=1, allocated=3000, used=1000),
            2: PhaseAllocation(phase=2, allocated=4000, used=2000),
        }
        phases[1].remaining = 2000
        phases[2].remaining = 2000

        plan = BudgetPlan(
            total_budget=10000,
            synthesis_reserve=2000,
            phases=phases,
            strategy=AllocationStrategy.EQUAL,
        )

        assert plan.total_used == 3000

    def test_total_remaining(self):
        """Should calculate total remaining tokens."""
        phases = {
            1: PhaseAllocation(phase=1, allocated=3000),
            2: PhaseAllocation(phase=2, allocated=4000),
        }

        plan = BudgetPlan(
            total_budget=10000,
            synthesis_reserve=2000,
            phases=phases,
            strategy=AllocationStrategy.EQUAL,
        )

        assert plan.total_remaining == 7000

    def test_overall_utilization(self):
        """Should calculate overall utilization."""
        phases = {
            1: PhaseAllocation(phase=1, allocated=4000, used=2000),
        }
        phases[1].remaining = 2000

        plan = BudgetPlan(
            total_budget=10000,
            synthesis_reserve=2000,
            phases=phases,
            strategy=AllocationStrategy.EQUAL,
        )

        # Used 2000 out of 8000 working budget = 25%
        assert plan.overall_utilization == 0.25

    def test_to_dict(self):
        """Should convert to dictionary."""
        phases = {
            1: PhaseAllocation(phase=1, allocated=4000),
        }

        plan = BudgetPlan(
            total_budget=10000,
            synthesis_reserve=2000,
            phases=phases,
            strategy=AllocationStrategy.WEIGHTED,
        )

        result = plan.to_dict()

        assert result["total_budget"] == 10000
        assert result["synthesis_reserve"] == 2000
        assert result["working_budget"] == 8000
        assert result["strategy"] == "weighted"
        assert "phases" in result


class TestTokenBudgetAllocatorInit:
    """Tests for TokenBudgetAllocator initialization."""

    def test_default_init(self):
        """Should initialize with defaults."""
        allocator = TokenBudgetAllocator()

        assert allocator.total_budget > 0
        assert 0 < allocator.synthesis_reserve_pct < 1
        assert allocator.max_context_per_phase > 0

    def test_custom_init(self):
        """Should accept custom values."""
        allocator = TokenBudgetAllocator(
            total_budget=100000,
            synthesis_reserve_pct=0.15,
            max_context_per_phase=50000,
        )

        assert allocator.total_budget == 100000
        assert allocator.synthesis_reserve_pct == 0.15
        assert allocator.max_context_per_phase == 50000


class TestTokenBudgetAllocatorCreatePlan:
    """Tests for create_plan method."""

    @pytest.fixture
    def allocator(self):
        """Create allocator with known budget."""
        return TokenBudgetAllocator(
            total_budget=10000,
            synthesis_reserve_pct=0.2,
        )

    def test_create_plan_basic(self, allocator):
        """Should create plan with phases."""
        plan = allocator.create_plan(num_phases=3)

        assert plan.total_budget == 10000
        assert plan.synthesis_reserve == 2000
        assert len(plan.phases) == 3

    def test_create_plan_with_weights(self, allocator):
        """Should use custom weights."""
        weights = {1: 0.5, 2: 0.3, 3: 0.2}
        plan = allocator.create_plan(num_phases=3, phase_weights=weights)

        # First phase should have most budget
        assert plan.phases[1].allocated > plan.phases[2].allocated
        assert plan.phases[2].allocated > plan.phases[3].allocated

    def test_create_plan_equal_strategy(self, allocator):
        """Should distribute equally with EQUAL strategy."""
        plan = allocator.create_plan(
            num_phases=4,
            strategy=AllocationStrategy.EQUAL,
        )

        allocations = [p.allocated for p in plan.phases.values()]
        # All should be approximately equal
        assert max(allocations) - min(allocations) <= 1

    def test_create_plan_front_loaded(self, allocator):
        """Should allocate more to early phases with FRONT_LOADED."""
        plan = allocator.create_plan(
            num_phases=4,
            strategy=AllocationStrategy.FRONT_LOADED,
        )

        assert plan.phases[1].allocated > plan.phases[4].allocated

    def test_create_plan_back_loaded(self, allocator):
        """Should allocate more to later phases with BACK_LOADED."""
        plan = allocator.create_plan(
            num_phases=4,
            strategy=AllocationStrategy.BACK_LOADED,
        )

        assert plan.phases[4].allocated > plan.phases[1].allocated

    def test_create_plan_respects_max_context(self):
        """Should cap allocation at max_context_per_phase."""
        allocator = TokenBudgetAllocator(
            total_budget=1000000,
            synthesis_reserve_pct=0.1,
            max_context_per_phase=10000,
        )

        plan = allocator.create_plan(num_phases=2)

        for phase in plan.phases.values():
            assert phase.allocated <= 10000


class TestTokenBudgetAllocatorUsage:
    """Tests for usage recording methods."""

    @pytest.fixture
    def allocator(self):
        """Create allocator."""
        return TokenBudgetAllocator(total_budget=10000, synthesis_reserve_pct=0.2)

    @pytest.fixture
    def plan(self, allocator):
        """Create a budget plan."""
        return allocator.create_plan(num_phases=3)

    def test_record_usage(self, allocator, plan):
        """Should record usage for a phase."""
        plan = allocator.record_usage(plan, phase=1, tokens_used=1500)

        assert plan.phases[1].used == 1500
        assert plan.phases[1].status == "completed"

    def test_record_usage_updates_remaining(self, allocator, plan):
        """Should update remaining tokens."""
        original_allocated = plan.phases[1].allocated
        plan = allocator.record_usage(plan, phase=1, tokens_used=500)

        assert plan.phases[1].remaining == original_allocated - 500

    def test_record_usage_invalid_phase(self, allocator, plan):
        """Should handle invalid phase gracefully."""
        plan = allocator.record_usage(plan, phase=99, tokens_used=1000)
        # Should not crash, just return plan unchanged

    def test_get_phase_budget(self, allocator, plan):
        """Should return available budget for phase."""
        budget = allocator.get_phase_budget(plan, phase=1)

        assert budget == plan.phases[1].remaining

    def test_get_phase_budget_invalid_phase(self, allocator, plan):
        """Should return 0 for invalid phase."""
        budget = allocator.get_phase_budget(plan, phase=99)

        assert budget == 0


class TestTokenBudgetAllocatorReallocation:
    """Tests for token reallocation."""

    @pytest.fixture
    def allocator(self):
        """Create allocator."""
        return TokenBudgetAllocator(total_budget=10000, synthesis_reserve_pct=0.2)

    def test_reallocate_unused(self, allocator):
        """Should reallocate unused tokens."""
        plan = allocator.create_plan(num_phases=3)
        original_phase2_alloc = plan.phases[2].allocated

        # Use only half of phase 1
        plan = allocator.record_usage(plan, phase=1, tokens_used=plan.phases[1].allocated // 2)
        plan = allocator.reallocate_unused(plan, from_phase=1)

        # Phase 2 and 3 should have more tokens now
        assert plan.phases[2].allocated > original_phase2_alloc
        assert plan.reallocation_count == 1

    def test_reallocate_marks_source_empty(self, allocator):
        """Should mark source phase remaining as 0."""
        plan = allocator.create_plan(num_phases=3)
        plan = allocator.record_usage(plan, phase=1, tokens_used=plan.phases[1].allocated // 2)
        plan = allocator.reallocate_unused(plan, from_phase=1)

        assert plan.phases[1].remaining == 0

    def test_reallocate_no_unused(self, allocator):
        """Should do nothing if no unused tokens."""
        plan = allocator.create_plan(num_phases=3)
        plan = allocator.record_usage(plan, phase=1, tokens_used=plan.phases[1].allocated)
        plan = allocator.reallocate_unused(plan, from_phase=1)

        assert plan.reallocation_count == 0

    def test_reallocate_invalid_phase(self, allocator):
        """Should handle invalid phase gracefully."""
        plan = allocator.create_plan(num_phases=3)
        plan = allocator.reallocate_unused(plan, from_phase=99)
        # Should not crash


class TestTokenBudgetAllocatorEstimation:
    """Tests for capacity estimation."""

    @pytest.fixture
    def allocator(self):
        """Create allocator."""
        return TokenBudgetAllocator(total_budget=10000, synthesis_reserve_pct=0.2)

    def test_estimate_remaining_capacity(self, allocator):
        """Should estimate remaining capacity."""
        plan = allocator.create_plan(num_phases=4)

        estimate = allocator.estimate_remaining_capacity(plan, current_phase=2)

        assert "remaining_phases" in estimate
        assert "remaining_budget" in estimate
        assert "synthesis_reserve" in estimate
        assert "estimated_findings_capacity" in estimate
        assert estimate["remaining_phases"] == 3  # phases 2, 3, 4


class TestTokenBudgetAllocatorOptimization:
    """Tests for optimization suggestions."""

    @pytest.fixture
    def allocator(self):
        """Create allocator."""
        return TokenBudgetAllocator(total_budget=10000, synthesis_reserve_pct=0.2)

    def test_suggest_underutilization(self, allocator):
        """Should suggest for underutilized phases."""
        plan = allocator.create_plan(num_phases=3)
        # Use only 20% of phase 1
        plan.phases[1].used = int(plan.phases[1].allocated * 0.2)
        plan.phases[1].status = "completed"

        suggestions = allocator.suggest_optimization(plan)

        assert len(suggestions) > 0
        # Check for reducing allocation suggestion
        assert any("reduc" in s.lower() for s in suggestions)

    def test_suggest_overutilization(self, allocator):
        """Should suggest for near-exhausted phases."""
        plan = allocator.create_plan(num_phases=3)
        # Use 98% of phase 1
        plan.phases[1].used = int(plan.phases[1].allocated * 0.98)
        plan.phases[1].status = "completed"

        suggestions = allocator.suggest_optimization(plan)

        assert len(suggestions) > 0
        # Check for increasing allocation suggestion
        assert any("increas" in s.lower() for s in suggestions)


class TestBudgetTracker:
    """Tests for BudgetTracker class."""

    @pytest.fixture
    def tracker(self):
        """Create tracker with a plan."""
        allocator = TokenBudgetAllocator(total_budget=10000, synthesis_reserve_pct=0.2)
        plan = allocator.create_plan(num_phases=3)
        return BudgetTracker(plan)

    def test_log_usage(self, tracker):
        """Should log usage events."""
        tracker.log_usage(phase=1, operation="search", tokens=500)

        assert len(tracker.usage_log) == 1
        assert tracker.usage_log[0]["phase"] == 1
        assert tracker.usage_log[0]["operation"] == "search"
        assert tracker.usage_log[0]["tokens"] == 500

    def test_log_usage_creates_alerts(self, tracker):
        """Should create alerts when near capacity."""
        # Use 95% of phase budget
        high_usage = int(tracker.plan.phases[1].allocated * 0.95)
        tracker.plan.phases[1].used = high_usage

        tracker.log_usage(phase=1, operation="analysis", tokens=100)

        assert len(tracker.alerts) > 0

    def test_get_usage_summary(self, tracker):
        """Should return usage summary."""
        tracker.log_usage(phase=1, operation="search", tokens=500)
        tracker.log_usage(phase=1, operation="analysis", tokens=300)

        summary = tracker.get_usage_summary()

        assert "plan" in summary
        assert summary["usage_events"] == 2
        assert summary["total_logged_tokens"] == 800
