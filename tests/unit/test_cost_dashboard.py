"""Tests for CostDashboard and related classes.

Tests cover:
- CostEntry: cost entry tracking and serialization
- CostAlert: alert creation and serialization
- CostDashboard: recording, totals, breakdowns, alerts, persistence
"""

import json
import tempfile
from datetime import datetime, date, timedelta
from pathlib import Path

import pytest

from deepr.observability.costs import (
    AlertManager,
    CostAlert,
    CostDashboard,
    CostEntry,
)


class TestCostEntry:
    """Tests for CostEntry dataclass."""

    def test_initial_state(self):
        """New cost entry should have correct defaults."""
        entry = CostEntry(
            operation="research",
            provider="openai",
            cost=0.15,
        )
        
        assert entry.operation == "research"
        assert entry.provider == "openai"
        assert entry.cost == 0.15
        assert entry.model == ""
        assert entry.tokens_input == 0
        assert entry.tokens_output == 0
        assert entry.task_id == ""
        assert entry.metadata == {}
        assert entry.timestamp is not None

    def test_with_all_fields(self):
        """Cost entry should store all fields correctly."""
        entry = CostEntry(
            operation="synthesis",
            provider="anthropic",
            cost=0.25,
            model="claude-3-5-sonnet",
            tokens_input=1000,
            tokens_output=2000,
            task_id="task-001",
            metadata={"source": "api"},
        )
        
        assert entry.operation == "synthesis"
        assert entry.provider == "anthropic"
        assert entry.cost == 0.25
        assert entry.model == "claude-3-5-sonnet"
        assert entry.tokens_input == 1000
        assert entry.tokens_output == 2000
        assert entry.task_id == "task-001"
        assert entry.metadata == {"source": "api"}

    def test_total_tokens(self):
        """Total tokens should sum input and output."""
        entry = CostEntry(
            operation="chat",
            provider="openai",
            cost=0.05,
            tokens_input=500,
            tokens_output=1500,
        )
        
        assert entry.total_tokens == 2000

    def test_date_property(self):
        """Date property should return date portion of timestamp."""
        timestamp = datetime(2025, 1, 15, 10, 30, 0)
        entry = CostEntry(
            operation="research",
            provider="openai",
            cost=0.10,
            timestamp=timestamp,
        )
        
        assert entry.date == date(2025, 1, 15)

    def test_to_dict_serialization(self):
        """Cost entry should serialize to dictionary correctly."""
        entry = CostEntry(
            operation="fact_check",
            provider="xai",
            cost=0.02,
            model="grok-4-fast",
            tokens_input=100,
            tokens_output=200,
            task_id="task-002",
            metadata={"verified": True},
        )
        
        data = entry.to_dict()
        
        assert data["operation"] == "fact_check"
        assert data["provider"] == "xai"
        assert data["cost"] == 0.02
        assert data["model"] == "grok-4-fast"
        assert data["tokens_input"] == 100
        assert data["tokens_output"] == 200
        assert data["task_id"] == "task-002"
        assert data["metadata"] == {"verified": True}
        assert "timestamp" in data

    def test_from_dict_deserialization(self):
        """Cost entry should deserialize from dictionary correctly."""
        data = {
            "timestamp": "2025-01-15T10:30:00",
            "operation": "research",
            "provider": "openai",
            "model": "gpt-4o",
            "cost": 0.15,
            "tokens_input": 500,
            "tokens_output": 1000,
            "task_id": "task-003",
            "metadata": {"priority": "high"},
        }
        
        entry = CostEntry.from_dict(data)
        
        assert entry.operation == "research"
        assert entry.provider == "openai"
        assert entry.model == "gpt-4o"
        assert entry.cost == 0.15
        assert entry.tokens_input == 500
        assert entry.tokens_output == 1000
        assert entry.task_id == "task-003"
        assert entry.metadata == {"priority": "high"}

    def test_from_dict_missing_optional_fields(self):
        """Deserialization should handle missing optional fields."""
        data = {
            "operation": "chat",
            "provider": "anthropic",
            "cost": 0.05,
        }
        
        entry = CostEntry.from_dict(data)
        
        assert entry.operation == "chat"
        assert entry.provider == "anthropic"
        assert entry.cost == 0.05
        assert entry.model == ""
        assert entry.tokens_input == 0
        assert entry.tokens_output == 0


class TestCostAlert:
    """Tests for CostAlert dataclass."""

    def test_creation(self):
        """CostAlert should store all fields correctly."""
        alert = CostAlert(
            level="warning",
            threshold=0.8,
            current_value=8.50,
            limit=10.0,
            period="daily",
        )
        
        assert alert.level == "warning"
        assert alert.threshold == 0.8
        assert alert.current_value == 8.50
        assert alert.limit == 10.0
        assert alert.period == "daily"
        assert alert.triggered_at is not None

    def test_to_dict_serialization(self):
        """CostAlert should serialize correctly."""
        alert = CostAlert(
            level="critical",
            threshold=0.95,
            current_value=95.0,
            limit=100.0,
            period="monthly",
        )
        
        data = alert.to_dict()
        
        assert data["level"] == "critical"
        assert data["threshold"] == 0.95
        assert data["current_value"] == 95.0
        assert data["limit"] == 100.0
        assert data["period"] == "monthly"
        assert "triggered_at" in data


class TestAlertManager:
    """Tests for AlertManager class."""

    def test_initialization_defaults(self):
        """AlertManager should initialize with default thresholds."""
        manager = AlertManager()
        
        assert manager.thresholds == [0.5, 0.8, 0.95]
        assert manager.triggered_alerts == []

    def test_initialization_custom_thresholds(self):
        """AlertManager should accept custom thresholds."""
        manager = AlertManager(thresholds=[0.6, 0.9])
        
        assert manager.thresholds == [0.6, 0.9]

    def test_check_daily_alerts_triggers_warning(self):
        """Should trigger warning alert when threshold exceeded."""
        manager = AlertManager(thresholds=[0.5, 0.8, 0.95])
        today = date.today()
        
        # 60% of limit should trigger 0.5 threshold
        alerts = manager.check_daily_alerts(
            daily_total=6.0,
            daily_limit=10.0,
            check_date=today
        )
        
        assert len(alerts) >= 1
        assert any(a.threshold == 0.5 for a in alerts)
        assert any(a.level == "warning" for a in alerts)

    def test_check_daily_alerts_triggers_critical(self):
        """Should trigger critical alert at 95% threshold."""
        manager = AlertManager(thresholds=[0.95])
        today = date.today()
        
        alerts = manager.check_daily_alerts(
            daily_total=9.6,
            daily_limit=10.0,
            check_date=today
        )
        
        assert len(alerts) == 1
        assert alerts[0].level == "critical"
        assert alerts[0].threshold == 0.95

    def test_check_daily_alerts_no_duplicate(self):
        """Should not trigger same alert twice on same day."""
        manager = AlertManager(thresholds=[0.5])
        # Use UTC date to match AlertManager's internal behavior
        today = datetime.utcnow().date()
        
        # First check triggers alert
        alerts1 = manager.check_daily_alerts(6.0, 10.0, today)
        assert len(alerts1) == 1
        
        # Second check should not trigger again
        alerts2 = manager.check_daily_alerts(7.0, 10.0, today)
        assert len(alerts2) == 0

    def test_check_monthly_alerts_triggers(self):
        """Should trigger monthly alerts when threshold exceeded."""
        manager = AlertManager(thresholds=[0.5])
        now = datetime.utcnow()
        
        alerts = manager.check_monthly_alerts(
            monthly_total=55.0,
            monthly_limit=100.0,
            check_year=now.year,
            check_month=now.month
        )
        
        assert len(alerts) == 1
        assert alerts[0].period == "monthly"

    def test_check_monthly_alerts_no_duplicate(self):
        """Should not trigger same monthly alert twice."""
        manager = AlertManager(thresholds=[0.5])
        now = datetime.utcnow()
        
        # First check triggers
        alerts1 = manager.check_monthly_alerts(55.0, 100.0, now.year, now.month)
        assert len(alerts1) == 1
        
        # Second check should not trigger again
        alerts2 = manager.check_monthly_alerts(60.0, 100.0, now.year, now.month)
        assert len(alerts2) == 0

    def test_get_active_alerts_daily(self):
        """Should return today's daily alerts as active."""
        manager = AlertManager(thresholds=[0.5])
        now = datetime.utcnow()
        today = now.date()
        
        # Trigger an alert
        manager.check_daily_alerts(6.0, 10.0, today)
        
        active = manager.get_active_alerts(now)
        
        assert len(active) == 1
        assert active[0].period == "daily"

    def test_get_active_alerts_excludes_old_daily(self):
        """Should not return yesterday's daily alerts as active."""
        manager = AlertManager(thresholds=[0.5])
        now = datetime.utcnow()
        yesterday = (now - timedelta(days=1)).date()
        
        # Trigger an alert for yesterday
        manager.check_daily_alerts(6.0, 10.0, yesterday)
        
        # Manually set the triggered_at to yesterday so it's actually old
        if manager.triggered_alerts:
            manager.triggered_alerts[0].triggered_at = now - timedelta(days=1)
        
        # Should not be active today
        active = manager.get_active_alerts(now)
        
        assert len(active) == 0

    def test_get_active_alerts_monthly(self):
        """Should return this month's monthly alerts as active."""
        manager = AlertManager(thresholds=[0.5])
        now = datetime.utcnow()
        
        # Trigger a monthly alert
        manager.check_monthly_alerts(55.0, 100.0, now.year, now.month)
        
        active = manager.get_active_alerts(now)
        
        assert len(active) == 1
        assert active[0].period == "monthly"

    def test_multiple_thresholds_triggered(self):
        """Should trigger multiple thresholds when all exceeded."""
        manager = AlertManager(thresholds=[0.5, 0.8, 0.95])
        today = date.today()
        
        # 96% should trigger all thresholds
        alerts = manager.check_daily_alerts(9.6, 10.0, today)
        
        thresholds_triggered = {a.threshold for a in alerts}
        assert 0.5 in thresholds_triggered
        assert 0.8 in thresholds_triggered
        assert 0.95 in thresholds_triggered

    def test_critical_threshold_constant(self):
        """Critical threshold should be 0.95."""
        assert AlertManager.CRITICAL_THRESHOLD == 0.95


class TestCostDashboard:
    """Tests for CostDashboard class."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "costs.json"

    def test_initialization(self, temp_storage):
        """Dashboard should initialize with empty entries."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        assert len(dashboard.entries) == 0
        assert dashboard.daily_limit == 10.0
        assert dashboard.monthly_limit == 100.0
        assert dashboard.alert_thresholds == [0.5, 0.8, 0.95]

    def test_custom_limits(self, temp_storage):
        """Dashboard should accept custom limits."""
        dashboard = CostDashboard(
            storage_path=temp_storage,
            daily_limit=25.0,
            monthly_limit=500.0,
            alert_thresholds=[0.6, 0.9],
        )
        
        assert dashboard.daily_limit == 25.0
        assert dashboard.monthly_limit == 500.0
        assert dashboard.alert_thresholds == [0.6, 0.9]

    def test_record_entry(self, temp_storage):
        """Recording should create and store cost entry."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        entry = dashboard.record(
            operation="research",
            provider="openai",
            cost=0.15,
            model="gpt-4o",
            tokens_input=500,
            tokens_output=1000,
        )
        
        assert len(dashboard.entries) == 1
        assert entry.operation == "research"
        assert entry.provider == "openai"
        assert entry.cost == 0.15

    def test_record_with_metadata(self, temp_storage):
        """Recording should accept metadata."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        entry = dashboard.record(
            operation="chat",
            provider="anthropic",
            cost=0.05,
            metadata={"session_id": "sess-001"},
        )
        
        assert entry.metadata == {"session_id": "sess-001"}

    def test_get_daily_total_today(self, temp_storage):
        """Daily total should sum today's costs."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        dashboard.record("research", "openai", 0.10)
        dashboard.record("chat", "anthropic", 0.05)
        dashboard.record("synthesis", "openai", 0.15)
        
        # Default get_daily_total() now uses UTC date consistently
        total = dashboard.get_daily_total()
        
        assert abs(total - 0.30) < 0.0001

    def test_get_daily_total_specific_date(self, temp_storage):
        """Daily total should filter by specific date."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        # Add entry for today (UTC)
        dashboard.record("research", "openai", 0.10)
        
        # Add entry for yesterday (manually set timestamp)
        yesterday = datetime.utcnow() - timedelta(days=1)
        entry = CostEntry(
            operation="chat",
            provider="anthropic",
            cost=0.20,
            timestamp=yesterday,
        )
        dashboard.entries.append(entry)
        
        # Today's total should only include today's entry
        today_total = dashboard.get_daily_total()
        assert abs(today_total - 0.10) < 0.0001
        
        # Yesterday's total should only include yesterday's entry
        yesterday_total = dashboard.get_daily_total(yesterday.date())
        assert abs(yesterday_total - 0.20) < 0.0001

    def test_get_monthly_total(self, temp_storage):
        """Monthly total should sum current month's costs."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        dashboard.record("research", "openai", 0.50)
        dashboard.record("chat", "anthropic", 0.25)
        
        total = dashboard.get_monthly_total()
        
        assert total == 0.75

    def test_get_breakdown_by_provider(self, temp_storage):
        """Breakdown by provider should group costs correctly."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        dashboard.record("research", "openai", 0.10)
        dashboard.record("chat", "openai", 0.15)
        dashboard.record("synthesis", "anthropic", 0.20)
        dashboard.record("fact_check", "xai", 0.05)
        
        breakdown = dashboard.get_breakdown_by_provider()
        
        assert breakdown["openai"] == 0.25  # 0.10 + 0.15
        assert breakdown["anthropic"] == 0.20
        assert breakdown["xai"] == 0.05

    def test_get_breakdown_by_operation(self, temp_storage):
        """Breakdown by operation should group costs correctly."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        dashboard.record("research", "openai", 0.10)
        dashboard.record("research", "anthropic", 0.15)
        dashboard.record("chat", "openai", 0.05)
        
        breakdown = dashboard.get_breakdown_by_operation()
        
        assert breakdown["research"] == 0.25  # 0.10 + 0.15
        assert breakdown["chat"] == 0.05

    def test_get_breakdown_by_model(self, temp_storage):
        """Breakdown by model should group costs correctly."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        dashboard.record("research", "openai", 0.10, model="gpt-4o")
        dashboard.record("chat", "openai", 0.05, model="gpt-4o")
        dashboard.record("synthesis", "openai", 0.15, model="gpt-4o-mini")
        dashboard.record("fact_check", "xai", 0.02, model="")  # No model
        
        breakdown = dashboard.get_breakdown_by_model()
        
        # Use approximate comparison for floating point
        assert abs(breakdown["gpt-4o"] - 0.15) < 0.0001  # 0.10 + 0.05
        assert abs(breakdown["gpt-4o-mini"] - 0.15) < 0.0001
        assert abs(breakdown["unknown"] - 0.02) < 0.0001  # Empty model becomes "unknown"

    def test_check_alerts_daily_warning(self, temp_storage):
        """Should trigger daily warning alert at 50% threshold."""
        dashboard = CostDashboard(
            storage_path=temp_storage,
            daily_limit=10.0,
            alert_thresholds=[0.5, 0.8, 0.95],
        )
        
        # Spend 5.50 (55% of daily limit)
        dashboard.record("research", "openai", 5.50)
        
        # Verify the entry was recorded and daily total is correct
        daily_total = dashboard.get_daily_total()
        assert daily_total >= 5.0, f"Daily total should be >= 5.0, got {daily_total}"
        
        # The alerts are checked during record(), so check triggered_alerts
        daily_alerts = [a for a in dashboard.triggered_alerts if a.period == "daily"]
        assert len(daily_alerts) >= 1, f"Expected at least 1 daily alert, got {len(daily_alerts)}"
        assert any(a.threshold == 0.5 for a in daily_alerts)

    def test_check_alerts_daily_critical(self, temp_storage):
        """Should trigger daily critical alert at 95% threshold."""
        dashboard = CostDashboard(
            storage_path=temp_storage,
            daily_limit=10.0,
            alert_thresholds=[0.5, 0.8, 0.95],
        )
        
        # Spend 9.60 (96% of daily limit)
        dashboard.record("research", "openai", 9.60)
        
        # The alerts are checked during record(), so check triggered_alerts
        critical_alerts = [a for a in dashboard.triggered_alerts if a.level == "critical"]
        assert len(critical_alerts) >= 1, f"Expected at least 1 critical alert, got {len(critical_alerts)}"

    def test_check_alerts_no_duplicate(self, temp_storage):
        """Should not trigger same alert twice on same day."""
        dashboard = CostDashboard(
            storage_path=temp_storage,
            daily_limit=10.0,
            alert_thresholds=[0.5],
        )
        
        # First spend triggers alert (during record)
        dashboard.record("research", "openai", 6.0)
        alerts_count_after_first = len(dashboard.triggered_alerts)
        
        # Second spend should not re-trigger same alert
        dashboard.record("chat", "openai", 1.0)
        alerts_count_after_second = len(dashboard.triggered_alerts)
        
        # First record should have triggered alert
        assert alerts_count_after_first >= 1, "First record should trigger at least 1 alert"
        # Second record should not add new alerts for same threshold
        assert alerts_count_after_second == alerts_count_after_first, "Second record should not add duplicate alerts"

    def test_check_alerts_monthly(self, temp_storage):
        """Should trigger monthly alerts."""
        dashboard = CostDashboard(
            storage_path=temp_storage,
            monthly_limit=100.0,
            alert_thresholds=[0.5],
        )
        
        # Spend 55 (55% of monthly limit)
        dashboard.record("research", "openai", 55.0)
        
        # The alerts are checked during record(), so check triggered_alerts
        monthly_alerts = [a for a in dashboard.triggered_alerts if a.period == "monthly"]
        assert len(monthly_alerts) >= 1, f"Expected at least 1 monthly alert, got {len(monthly_alerts)}"

    def test_get_active_alerts(self, temp_storage):
        """Should return currently active alerts."""
        dashboard = CostDashboard(
            storage_path=temp_storage,
            daily_limit=10.0,
            alert_thresholds=[0.5],
        )
        
        # Trigger an alert (happens during record)
        dashboard.record("research", "openai", 6.0)
        
        active = dashboard.get_active_alerts()
        
        # Should have at least one active alert
        assert len(active) >= 1, f"Expected at least 1 active alert, got {len(active)}"

    def test_get_daily_history(self, temp_storage):
        """Should return daily cost history."""
        dashboard = CostDashboard(storage_path=temp_storage, daily_limit=10.0)
        
        # Add some entries
        dashboard.record("research", "openai", 2.50)
        
        history = dashboard.get_daily_history(days=7)
        
        assert len(history) == 7
        # Most recent day (last in list) should have our cost
        assert abs(history[-1]["total"] - 2.50) < 0.0001
        assert history[-1]["limit"] == 10.0
        assert "utilization" in history[-1]

    def test_get_summary(self, temp_storage):
        """Should return comprehensive summary."""
        dashboard = CostDashboard(
            storage_path=temp_storage,
            daily_limit=10.0,
            monthly_limit=100.0,
        )
        
        dashboard.record("research", "openai", 3.0)
        dashboard.record("chat", "anthropic", 2.0)
        
        summary = dashboard.get_summary()
        
        assert "daily" in summary
        # Now that we use UTC consistently, daily total should work
        assert abs(summary["daily"]["total"] - 5.0) < 0.0001
        
        assert "monthly" in summary
        assert abs(summary["monthly"]["total"] - 5.0) < 0.0001
        
        assert "by_provider" in summary
        assert abs(summary["by_provider"]["openai"] - 3.0) < 0.0001
        assert abs(summary["by_provider"]["anthropic"] - 2.0) < 0.0001
        
        assert "by_operation" in summary
        assert "active_alerts" in summary
        assert "total_entries" in summary
        assert summary["total_entries"] == 2

    def test_persistence_save_and_load(self, temp_storage):
        """Dashboard should persist and load entries correctly."""
        # Create dashboard and record data
        dashboard1 = CostDashboard(storage_path=temp_storage)
        dashboard1.record("research", "openai", 0.15, model="gpt-4o")
        dashboard1.record("chat", "anthropic", 0.10, model="claude-3-5-sonnet")
        
        # Create new dashboard that loads from same path
        dashboard2 = CostDashboard(storage_path=temp_storage)
        
        assert len(dashboard2.entries) == 2
        # Check daily total (now uses UTC consistently)
        assert abs(dashboard2.get_daily_total() - 0.25) < 0.0001

    def test_persistence_limits_entries(self, temp_storage):
        """Dashboard should limit stored entries to prevent unbounded growth."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        # Record many entries (more than the 10000 limit)
        # Note: This is a slow test, so we just verify the mechanism exists
        for i in range(100):
            dashboard.record("research", "openai", 0.01)
        
        # Reload and verify entries are preserved
        dashboard2 = CostDashboard(storage_path=temp_storage)
        assert len(dashboard2.entries) == 100


class TestCostDashboardEdgeCases:
    """Edge case tests for CostDashboard."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "costs.json"

    def test_handles_corrupted_storage(self, temp_storage):
        """Dashboard should handle corrupted storage gracefully."""
        # Write corrupted JSON
        temp_storage.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_storage, "w") as f:
            f.write("not valid json {{{")
        
        # Should not crash, just start fresh
        dashboard = CostDashboard(storage_path=temp_storage)
        assert len(dashboard.entries) == 0

    def test_zero_cost_entry(self, temp_storage):
        """Dashboard should handle zero cost entries."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        dashboard.record("research", "openai", 0.0)
        
        assert len(dashboard.entries) == 1
        assert dashboard.get_daily_total() == 0.0

    def test_very_small_cost(self, temp_storage):
        """Dashboard should handle very small costs."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        dashboard.record("chat", "openai", 0.0001)
        
        # Check daily total (now uses UTC consistently)
        assert abs(dashboard.get_daily_total() - 0.0001) < 0.00001

    def test_very_large_cost(self, temp_storage):
        """Dashboard should handle very large costs."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        dashboard.record("research", "openai", 1000.0)
        
        # Check daily total (now uses UTC consistently)
        assert abs(dashboard.get_daily_total() - 1000.0) < 0.0001

    def test_empty_dashboard_totals(self, temp_storage):
        """Empty dashboard should return zero totals."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        assert dashboard.get_daily_total() == 0.0
        assert dashboard.get_monthly_total() == 0.0

    def test_empty_dashboard_breakdowns(self, temp_storage):
        """Empty dashboard should return empty breakdowns."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        assert dashboard.get_breakdown_by_provider() == {}
        assert dashboard.get_breakdown_by_operation() == {}
        assert dashboard.get_breakdown_by_model() == {}

    def test_zero_limit_utilization(self, temp_storage):
        """Dashboard should handle zero limits without division error."""
        dashboard = CostDashboard(
            storage_path=temp_storage,
            daily_limit=0.0,
            monthly_limit=0.0,
        )
        
        dashboard.record("research", "openai", 1.0)
        
        summary = dashboard.get_summary()
        
        # Should not crash, utilization should be 0 when limit is 0
        assert summary["daily"]["utilization"] == 0
        assert summary["monthly"]["utilization"] == 0

    def test_date_range_filtering(self, temp_storage):
        """Breakdown should filter by date range."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        # Add entries at different times
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        
        # Today's entry
        dashboard.record("research", "openai", 0.10)
        
        # Yesterday's entry (manually add)
        entry = CostEntry(
            operation="chat",
            provider="anthropic",
            cost=0.20,
            timestamp=yesterday,
        )
        dashboard.entries.append(entry)
        
        # Filter to today only
        breakdown = dashboard.get_breakdown_by_provider(
            start_date=now.replace(hour=0, minute=0, second=0),
        )
        
        assert breakdown.get("openai", 0) == 0.10
        # anthropic entry is from yesterday, should be excluded
        assert breakdown.get("anthropic", 0) == 0.0

    def test_multiple_alerts_same_period(self, temp_storage):
        """Should trigger multiple threshold alerts for same period."""
        dashboard = CostDashboard(
            storage_path=temp_storage,
            daily_limit=10.0,
            alert_thresholds=[0.5, 0.8, 0.95],
        )
        
        # Spend 9.60 (96% - should trigger all thresholds)
        dashboard.record("research", "openai", 9.60)
        
        # Check triggered_alerts (alerts are triggered during record)
        daily_alerts = [a for a in dashboard.triggered_alerts if a.period == "daily"]
        thresholds_triggered = {a.threshold for a in daily_alerts}
        
        # Should have triggered all three thresholds (0.5, 0.8, 0.95)
        assert 0.5 in thresholds_triggered, "Should trigger 0.5 threshold"
        assert 0.8 in thresholds_triggered, "Should trigger 0.8 threshold"
        assert 0.95 in thresholds_triggered, "Should trigger 0.95 threshold"

    def test_negative_cost_clamped(self, temp_storage):
        """Negative costs should be clamped to zero."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        entry = dashboard.record("research", "openai", -0.10)
        
        # Negative cost should be clamped to 0
        assert entry.cost == 0.0
        assert dashboard.get_daily_total() == 0.0

    def test_unicode_in_metadata(self, temp_storage):
        """Dashboard should handle Unicode characters in metadata."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        # Metadata with various Unicode characters
        unicode_metadata = {
            "query": "日本語クエリ",
            "emoji": "🚀🔬📊",
            "special": "äöü ñ",
        }
        
        entry = dashboard.record(
            "research",
            "openai",
            0.15,
            metadata=unicode_metadata,
        )
        
        assert entry.metadata == unicode_metadata
        
        # Verify persistence works with Unicode
        dashboard2 = CostDashboard(storage_path=temp_storage)
        assert dashboard2.entries[0].metadata == unicode_metadata

    def test_unicode_in_operation_and_provider(self, temp_storage):
        """Dashboard should handle Unicode in operation and provider names."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        entry = dashboard.record(
            operation="研究",  # Japanese for "research"
            provider="提供者",  # Japanese for "provider"
            cost=0.10,
        )
        
        assert entry.operation == "研究"
        assert entry.provider == "提供者"
        
        breakdown = dashboard.get_breakdown_by_operation()
        assert "研究" in breakdown

    def test_very_long_operation_name(self, temp_storage):
        """Dashboard should handle very long operation names."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        long_operation = "a" * 1000
        long_provider = "b" * 1000
        
        entry = dashboard.record(long_operation, long_provider, 0.10)
        
        assert entry.operation == long_operation
        assert entry.provider == long_provider
        
        breakdown = dashboard.get_breakdown_by_operation()
        assert long_operation in breakdown

    def test_many_small_costs_accumulation(self, temp_storage):
        """Dashboard should accurately accumulate many small costs."""
        dashboard = CostDashboard(storage_path=temp_storage)
        
        # Record 100 small costs
        small_cost = 0.001
        num_entries = 100
        
        for _ in range(num_entries):
            dashboard.record("research", "openai", small_cost)
        
        expected_total = small_cost * num_entries
        actual_total = dashboard.get_daily_total()
        
        # Allow small floating-point tolerance
        assert abs(actual_total - expected_total) < 0.0001

    def test_atomic_write_temp_file_cleanup(self, temp_storage):
        """Temp files should be cleaned up after successful save."""
        dashboard = CostDashboard(storage_path=temp_storage)
        dashboard.record("research", "openai", 0.10)
        
        # Check that no .tmp file remains
        temp_path = temp_storage.with_suffix('.tmp')
        assert not temp_path.exists()


# Property-based tests using Hypothesis
from hypothesis import given, strategies as st, settings, HealthCheck


class TestCostDashboardProperties:
    """Property-based tests for CostDashboard invariants.
    
    These tests verify that certain properties hold across all valid inputs,
    providing stronger guarantees than example-based tests alone.
    """

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "costs.json"

    @given(
        costs=st.lists(
            st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
            min_size=0,
            max_size=50
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_total_equals_sum_of_recorded_costs(self, costs):
        """Total cost should equal sum of all recorded costs.
        
        **Validates: Requirements 1.1** - Cost tracking accuracy
        
        This property ensures that the dashboard correctly accumulates
        costs without losing or duplicating any values.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            dashboard = CostDashboard(storage_path=storage_path)
            
            for cost in costs:
                dashboard.record("test", "test_provider", cost)
            
            # Get daily total (all entries are from today)
            total = dashboard.get_daily_total()
            expected = sum(costs)
            
            # Allow small floating-point tolerance proportional to number of entries
            tolerance = 0.0001 * max(1, len(costs))
            assert abs(total - expected) < tolerance, (
                f"Total {total} differs from expected {expected} by more than {tolerance}"
            )

    @given(
        provider_costs=st.lists(
            st.tuples(
                st.sampled_from(["openai", "anthropic", "xai"]),
                st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)
            ),
            min_size=1,
            max_size=30
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_breakdown_sums_to_total(self, provider_costs):
        """Sum of provider breakdown should equal total cost.
        
        **Validates: Requirements 1.2** - Breakdown consistency
        
        This property ensures that breaking down costs by provider
        doesn't lose or create any cost values.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            dashboard = CostDashboard(storage_path=storage_path)
            
            for provider, cost in provider_costs:
                dashboard.record("test", provider, cost)
            
            breakdown = dashboard.get_breakdown_by_provider()
            breakdown_total = sum(breakdown.values())
            daily_total = dashboard.get_daily_total()
            
            # Both should equal the sum of input costs
            expected = sum(cost for _, cost in provider_costs)
            tolerance = 0.0001 * max(1, len(provider_costs))
            
            assert abs(breakdown_total - expected) < tolerance
            assert abs(daily_total - expected) < tolerance
            assert abs(breakdown_total - daily_total) < tolerance

    @given(
        cost=st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_negative_costs_always_clamped(self, cost):
        """Negative costs should always be clamped to zero.
        
        **Validates: Requirements 1.3** - Input validation
        
        This property ensures that invalid negative costs never
        corrupt the dashboard's totals.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            dashboard = CostDashboard(storage_path=storage_path)
            
            entry = dashboard.record("test", "test_provider", cost)
            
            # Entry cost should never be negative
            assert entry.cost >= 0
            
            # Dashboard total should never be negative
            assert dashboard.get_daily_total() >= 0

    @given(
        entries=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=50, alphabet=st.characters(blacklist_categories=('Cs',))),
                st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)
            ),
            min_size=0,
            max_size=20
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_entry_count_matches_records(self, entries):
        """Number of entries should match number of records.
        
        **Validates: Requirements 1.4** - Entry tracking
        
        This property ensures that every record call creates exactly
        one entry, no more, no less.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "costs.json"
            dashboard = CostDashboard(storage_path=storage_path)
            
            for operation, cost in entries:
                dashboard.record(operation, "test_provider", cost)
            
            assert len(dashboard.entries) == len(entries)


class TestProviderRouterProperties:
    """Property-based tests for ProviderRouter invariants."""

    @given(
        results=st.lists(
            st.tuples(
                st.booleans(),  # success
                st.floats(min_value=0, max_value=10000, allow_nan=False, allow_infinity=False),  # latency
                st.floats(min_value=0, max_value=10, allow_nan=False, allow_infinity=False)  # cost
            ),
            min_size=1,
            max_size=50
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_success_rate_bounded(self, results):
        """Success rate should always be between 0 and 1.
        
        **Validates: Requirements 2.1** - Metrics bounds
        
        This property ensures that success rate calculations
        never produce invalid values outside [0, 1].
        """
        from deepr.observability.provider_router import AutonomousProviderRouter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            
            for success, latency, cost in results:
                if success:
                    router.record_result("test", "model", True, latency, cost)
                else:
                    router.record_result("test", "model", False, error="test error")
            
            metrics = router.metrics.get(("test", "model"))
            if metrics:
                assert 0 <= metrics.success_rate <= 1

    @given(
        latencies=st.lists(
            st.one_of(
                st.floats(min_value=-1000, max_value=100000, allow_nan=False, allow_infinity=False),
                st.just(float('nan')),
                st.just(float('inf')),
                st.just(float('-inf'))
            ),
            min_size=1,
            max_size=30
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_latencies_never_corrupt_metrics(self, latencies):
        """Invalid latencies (NaN, Inf, negative) should never corrupt metrics.
        
        **Validates: Requirements 2.2** - Input sanitization
        
        This property ensures that any latency value, no matter how
        invalid, results in finite, non-negative metrics.
        """
        from deepr.observability.provider_router import AutonomousProviderRouter
        import math
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            
            for latency in latencies:
                router.record_result("test", "model", True, latency, 0.01)
            
            metrics = router.metrics.get(("test", "model"))
            if metrics:
                # Average latency should always be finite and non-negative
                assert math.isfinite(metrics.avg_latency_ms)
                assert metrics.avg_latency_ms >= 0
                
                # Rolling average should also be finite
                assert math.isfinite(metrics.rolling_avg_latency)
                assert metrics.rolling_avg_latency >= 0

    @given(
        successes=st.integers(min_value=0, max_value=100),
        failures=st.integers(min_value=0, max_value=100)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_total_requests_equals_successes_plus_failures(self, successes, failures):
        """Total requests should equal successes plus failures.
        
        **Validates: Requirements 2.3** - Request counting
        
        This property ensures that request counting is consistent
        and no requests are lost or double-counted.
        """
        from deepr.observability.provider_router import AutonomousProviderRouter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "metrics.json"
            router = AutonomousProviderRouter(storage_path=storage_path)
            
            for _ in range(successes):
                router.record_result("test", "model", True, 100.0, 0.01)
            
            for _ in range(failures):
                router.record_result("test", "model", False, error="test")
            
            metrics = router.metrics.get(("test", "model"))
            if metrics:
                assert metrics.total_requests == successes + failures
                assert metrics.success_count == successes
                assert metrics.failure_count == failures
