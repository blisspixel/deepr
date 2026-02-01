"""Property-based tests for CostDashboard and related classes.

Tests verify:
- Cost tracking accuracy (total cost = sum of all entries)
- Breakdown consistency (breakdowns sum to total)
- Alert threshold triggering
- Persistence roundtrip
- Aggregation correctness
"""

import json
import tempfile
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List

import pytest
from hypothesis import given, settings, strategies as st, assume, HealthCheck

from deepr.observability.costs import (
    AlertManager,
    CostAggregator,
    CostAlert,
    CostDashboard,
    CostEntry,
)


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Valid operation names
operations = st.sampled_from([
    "research", "chat", "synthesis", "fact_check", "analysis",
    "summarize", "translate", "embed", "search", "index"
])

# Valid provider names
providers = st.sampled_from([
    "openai", "anthropic", "xai", "google", "azure", "local"
])

# Valid model names
models = st.sampled_from([
    "gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet", "claude-3-haiku",
    "grok-4", "grok-4-fast", "gemini-pro", ""
])

# Non-negative costs (realistic range)
costs = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)

# Token counts
tokens = st.integers(min_value=0, max_value=100000)

# Timestamps within reasonable range (last 30 days)
timestamps = st.datetimes(
    min_value=datetime.utcnow() - timedelta(days=30),
    max_value=datetime.utcnow()
)

# Alert thresholds (valid fractions)
thresholds = st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)

# Spending limits
limits = st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False)


@st.composite
def cost_entries(draw, timestamp=None):
    """Generate a valid CostEntry."""
    return CostEntry(
        operation=draw(operations),
        provider=draw(providers),
        cost=draw(costs),
        model=draw(models),
        tokens_input=draw(tokens),
        tokens_output=draw(tokens),
        task_id=draw(st.text(min_size=0, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-")),
        timestamp=timestamp or draw(timestamps),
        metadata=draw(st.dictionaries(
            keys=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
            values=st.one_of(st.text(max_size=20), st.integers(), st.booleans()),
            max_size=3
        ))
    )


@st.composite
def cost_entry_lists(draw, min_size=0, max_size=50):
    """Generate a list of cost entries."""
    return draw(st.lists(cost_entries(), min_size=min_size, max_size=max_size))


@st.composite
def threshold_lists(draw):
    """Generate a sorted list of unique thresholds."""
    thresholds_list = draw(st.lists(
        st.floats(min_value=0.1, max_value=0.99, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=5,
        unique=True
    ))
    return sorted(thresholds_list)


# =============================================================================
# Property Tests for CostEntry
# =============================================================================

class TestCostEntryProperties:
    """Property-based tests for CostEntry."""

    @given(cost_entries())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_total_tokens_is_sum(self, entry: CostEntry):
        """Property: total_tokens always equals tokens_input + tokens_output."""
        assert entry.total_tokens == entry.tokens_input + entry.tokens_output

    @given(cost_entries())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_date_property_matches_timestamp(self, entry: CostEntry):
        """Property: date property always matches timestamp.date()."""
        assert entry.date == entry.timestamp.date()

    @given(cost_entries())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_serialization_roundtrip(self, entry: CostEntry):
        """Property: to_dict/from_dict roundtrip preserves all fields."""
        data = entry.to_dict()
        restored = CostEntry.from_dict(data)
        
        assert restored.operation == entry.operation
        assert restored.provider == entry.provider
        assert abs(restored.cost - entry.cost) < 1e-10
        assert restored.model == entry.model
        assert restored.tokens_input == entry.tokens_input
        assert restored.tokens_output == entry.tokens_output
        assert restored.task_id == entry.task_id
        assert restored.metadata == entry.metadata

    @given(cost_entries())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_to_dict_contains_all_fields(self, entry: CostEntry):
        """Property: to_dict always contains all required fields."""
        data = entry.to_dict()
        
        required_fields = [
            "timestamp", "operation", "provider", "model",
            "cost", "tokens_input", "tokens_output", "task_id", "metadata"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


# =============================================================================
# Property Tests for CostAggregator
# =============================================================================

class TestCostAggregatorProperties:
    """Property-based tests for CostAggregator."""

    @given(cost_entry_lists(min_size=0, max_size=100))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_breakdown_by_provider_sums_to_total(self, entries: List[CostEntry]):
        """Property: sum of provider breakdown equals total of all entries."""
        aggregator = CostAggregator(entries)
        breakdown = aggregator.get_breakdown_by_provider()
        
        total_from_breakdown = sum(breakdown.values())
        total_from_entries = sum(e.cost for e in entries)
        
        assert abs(total_from_breakdown - total_from_entries) < 1e-6

    @given(cost_entry_lists(min_size=0, max_size=100))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_breakdown_by_operation_sums_to_total(self, entries: List[CostEntry]):
        """Property: sum of operation breakdown equals total of all entries."""
        aggregator = CostAggregator(entries)
        breakdown = aggregator.get_breakdown_by_operation()
        
        total_from_breakdown = sum(breakdown.values())
        total_from_entries = sum(e.cost for e in entries)
        
        assert abs(total_from_breakdown - total_from_entries) < 1e-6

    @given(cost_entry_lists(min_size=0, max_size=100))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_breakdown_by_model_sums_to_total(self, entries: List[CostEntry]):
        """Property: sum of model breakdown equals total of all entries."""
        aggregator = CostAggregator(entries)
        breakdown = aggregator.get_breakdown_by_model()
        
        total_from_breakdown = sum(breakdown.values())
        total_from_entries = sum(e.cost for e in entries)
        
        assert abs(total_from_breakdown - total_from_entries) < 1e-6

    @given(cost_entry_lists(min_size=0, max_size=100))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_all_breakdowns_consistent(self, entries: List[CostEntry]):
        """Property: all breakdowns from get_all_breakdowns sum to same total."""
        aggregator = CostAggregator(entries)
        breakdowns = aggregator.get_all_breakdowns()
        
        total_by_provider = sum(breakdowns["by_provider"].values())
        total_by_operation = sum(breakdowns["by_operation"].values())
        total_by_model = sum(breakdowns["by_model"].values())
        
        assert abs(total_by_provider - total_by_operation) < 1e-6
        assert abs(total_by_operation - total_by_model) < 1e-6

    @given(cost_entry_lists(min_size=0, max_size=100))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_provider_breakdown_keys_match_entries(self, entries: List[CostEntry]):
        """Property: provider breakdown keys are subset of entry providers."""
        aggregator = CostAggregator(entries)
        breakdown = aggregator.get_breakdown_by_provider()
        
        entry_providers = {e.provider for e in entries}
        breakdown_providers = set(breakdown.keys())
        
        assert breakdown_providers <= entry_providers

    @given(cost_entry_lists(min_size=0, max_size=100))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_operation_breakdown_keys_match_entries(self, entries: List[CostEntry]):
        """Property: operation breakdown keys are subset of entry operations."""
        aggregator = CostAggregator(entries)
        breakdown = aggregator.get_breakdown_by_operation()
        
        entry_operations = {e.operation for e in entries}
        breakdown_operations = set(breakdown.keys())
        
        assert breakdown_operations <= entry_operations

    @given(cost_entry_lists(min_size=1, max_size=50))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_daily_total_never_exceeds_total(self, entries: List[CostEntry]):
        """Property: daily total for any date never exceeds total of all entries."""
        aggregator = CostAggregator(entries)
        
        # Get all unique dates
        dates = {e.date for e in entries}
        
        total_all = sum(e.cost for e in entries)
        
        for d in dates:
            daily = aggregator.get_daily_total(d)
            assert daily <= total_all + 1e-6


# =============================================================================
# Property Tests for AlertManager
# =============================================================================

class TestAlertManagerProperties:
    """Property-based tests for AlertManager."""

    @given(
        threshold_lists(),
        st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        limits
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_alerts_only_trigger_when_threshold_exceeded(
        self, thresholds: List[float], daily_total: float, daily_limit: float
    ):
        """Property: alerts only trigger when spending exceeds threshold * limit."""
        assume(daily_limit > 0)
        
        manager = AlertManager(thresholds=thresholds)
        today = datetime.utcnow().date()
        
        alerts = manager.check_daily_alerts(daily_total, daily_limit, today)
        
        for alert in alerts:
            threshold_value = alert.threshold * daily_limit
            assert daily_total >= threshold_value

    @given(
        threshold_lists(),
        st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        limits
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_no_duplicate_alerts_same_day(
        self, thresholds: List[float], daily_total: float, daily_limit: float
    ):
        """Property: same threshold never triggers twice on same day."""
        assume(daily_limit > 0)
        
        manager = AlertManager(thresholds=thresholds)
        today = datetime.utcnow().date()
        
        # First check
        alerts1 = manager.check_daily_alerts(daily_total, daily_limit, today)
        triggered_thresholds = {a.threshold for a in alerts1}
        
        # Second check with higher total
        alerts2 = manager.check_daily_alerts(daily_total + 100, daily_limit, today)
        
        # No duplicate thresholds
        for alert in alerts2:
            assert alert.threshold not in triggered_thresholds

    @given(threshold_lists())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_critical_threshold_level(self, thresholds: List[float]):
        """Property: alerts at >= 0.95 threshold are always critical."""
        manager = AlertManager(thresholds=thresholds)
        today = datetime.utcnow().date()
        
        # Trigger all thresholds
        alerts = manager.check_daily_alerts(1000.0, 100.0, today)
        
        for alert in alerts:
            if alert.threshold >= AlertManager.CRITICAL_THRESHOLD:
                assert alert.level == "critical"
            else:
                assert alert.level == "warning"

    @given(
        threshold_lists(),
        st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        limits
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_alert_current_value_matches_input(
        self, thresholds: List[float], daily_total: float, daily_limit: float
    ):
        """Property: alert current_value always matches the input total."""
        assume(daily_limit > 0)
        
        manager = AlertManager(thresholds=thresholds)
        today = datetime.utcnow().date()
        
        alerts = manager.check_daily_alerts(daily_total, daily_limit, today)
        
        for alert in alerts:
            assert alert.current_value == daily_total
            assert alert.limit == daily_limit


# =============================================================================
# Property Tests for CostDashboard
# =============================================================================

class TestCostDashboardProperties:
    """Property-based tests for CostDashboard."""

    @given(
        st.lists(
            st.tuples(operations, providers, costs, models),
            min_size=1,
            max_size=50
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_total_cost_equals_sum_of_entries(self, records):
        """Property: total cost always equals sum of all recorded costs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            dashboard = CostDashboard(storage_path=storage_path)
            
            expected_total = 0.0
            for operation, provider, cost, model in records:
                dashboard.record(operation, provider, cost, model=model)
                expected_total += cost
            
            # Get monthly total (all entries are from today)
            actual_total = dashboard.get_monthly_total()
            
            assert abs(actual_total - expected_total) < 1e-6

    @given(
        st.lists(
            st.tuples(operations, providers, costs),
            min_size=1,
            max_size=50
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_provider_breakdown_sums_to_total(self, records):
        """Property: provider breakdown always sums to total cost."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            dashboard = CostDashboard(storage_path=storage_path)
            
            for operation, provider, cost in records:
                dashboard.record(operation, provider, cost)
            
            breakdown = dashboard.get_breakdown_by_provider()
            total_from_breakdown = sum(breakdown.values())
            total_from_entries = sum(e.cost for e in dashboard.entries)
            
            assert abs(total_from_breakdown - total_from_entries) < 1e-6

    @given(
        st.lists(
            st.tuples(operations, providers, costs),
            min_size=1,
            max_size=50
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_operation_breakdown_sums_to_total(self, records):
        """Property: operation breakdown always sums to total cost."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            dashboard = CostDashboard(storage_path=storage_path)
            
            for operation, provider, cost in records:
                dashboard.record(operation, provider, cost)
            
            breakdown = dashboard.get_breakdown_by_operation()
            total_from_breakdown = sum(breakdown.values())
            total_from_entries = sum(e.cost for e in dashboard.entries)
            
            assert abs(total_from_breakdown - total_from_entries) < 1e-6

    @given(
        st.lists(
            st.tuples(operations, providers, costs),
            min_size=1,
            max_size=30
        )
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_persistence_roundtrip(self, records):
        """Property: save/load roundtrip preserves all entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            
            # Create and populate dashboard
            dashboard1 = CostDashboard(storage_path=storage_path)
            for operation, provider, cost in records:
                dashboard1.record(operation, provider, cost)
            
            original_count = len(dashboard1.entries)
            original_total = sum(e.cost for e in dashboard1.entries)
            
            # Create new dashboard that loads from same path
            dashboard2 = CostDashboard(storage_path=storage_path)
            
            assert len(dashboard2.entries) == original_count
            assert abs(sum(e.cost for e in dashboard2.entries) - original_total) < 1e-6

    @given(
        st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_negative_costs_clamped_to_zero(self, cost: float):
        """Property: negative costs are always clamped to zero."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            dashboard = CostDashboard(storage_path=storage_path)
            
            entry = dashboard.record("test", "openai", cost)
            
            assert entry.cost >= 0.0
            if cost < 0:
                assert entry.cost == 0.0

    @given(
        limits,
        st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_alerts_trigger_at_correct_thresholds(self, daily_limit: float, utilization: float):
        """Property: alerts trigger when utilization exceeds threshold."""
        assume(daily_limit > 0)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            dashboard = CostDashboard(
                storage_path=storage_path,
                daily_limit=daily_limit,
                alert_thresholds=[0.5, 0.8, 0.95]
            )
            
            # Record cost to reach target utilization
            cost = daily_limit * utilization
            dashboard.record("test", "openai", cost)
            
            # Check which thresholds should have triggered
            expected_thresholds = [t for t in [0.5, 0.8, 0.95] if utilization >= t]
            actual_thresholds = {a.threshold for a in dashboard.triggered_alerts if a.period == "daily"}
            
            for t in expected_thresholds:
                assert t in actual_thresholds, f"Threshold {t} should have triggered at {utilization*100}% utilization"

    @given(
        st.lists(
            st.tuples(operations, providers, costs, tokens, tokens),
            min_size=1,
            max_size=30
        )
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_entry_count_matches_record_count(self, records):
        """Property: number of entries always matches number of records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            dashboard = CostDashboard(storage_path=storage_path)
            
            for operation, provider, cost, tokens_in, tokens_out in records:
                dashboard.record(
                    operation, provider, cost,
                    tokens_input=tokens_in, tokens_output=tokens_out
                )
            
            assert len(dashboard.entries) == len(records)

    @given(
        st.lists(
            st.tuples(operations, providers, costs),
            min_size=1,
            max_size=30
        )
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_summary_breakdowns_consistent(self, records):
        """Property: summary breakdowns are consistent with individual breakdowns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            dashboard = CostDashboard(storage_path=storage_path)
            
            for operation, provider, cost in records:
                dashboard.record(operation, provider, cost)
            
            summary = dashboard.get_summary()
            
            # Verify provider breakdown matches
            individual_provider = dashboard.get_breakdown_by_provider()
            assert summary["by_provider"] == individual_provider
            
            # Verify operation breakdown matches
            individual_operation = dashboard.get_breakdown_by_operation()
            assert summary["by_operation"] == individual_operation


# =============================================================================
# Property Tests for CostAlert
# =============================================================================

class TestCostAlertProperties:
    """Property-based tests for CostAlert."""

    @given(
        st.sampled_from(["warning", "critical"]),
        thresholds,
        costs,
        limits,
        st.sampled_from(["daily", "monthly"])
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_alert_serialization_roundtrip(
        self, level: str, threshold: float, current_value: float, limit: float, period: str
    ):
        """Property: to_dict preserves all alert fields."""
        alert = CostAlert(
            level=level,
            threshold=threshold,
            current_value=current_value,
            limit=limit,
            period=period
        )
        
        data = alert.to_dict()
        
        assert data["level"] == level
        assert data["threshold"] == threshold
        assert data["current_value"] == current_value
        assert data["limit"] == limit
        assert data["period"] == period
        assert "triggered_at" in data
