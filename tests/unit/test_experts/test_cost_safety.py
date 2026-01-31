"""Tests for the cost safety system.

This module tests the defensive cost controls that prevent runaway costs
from autonomous expert operations (learning, chat, curriculum execution).
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import json

from deepr.experts.cost_safety import (
    CostAlertLevel,
    CostAlert,
    SessionCostTracker,
    CostSafetyManager,
    estimate_curriculum_cost,
    format_cost_warning,
    is_pausable_limit,
    get_resume_message,
)


class TestCostAlertLevel:
    """Tests for CostAlertLevel enum."""
    
    def test_all_levels_exist(self):
        """Verify all expected alert levels exist."""
        assert CostAlertLevel.INFO.value == "info"
        assert CostAlertLevel.WARNING.value == "warning"
        assert CostAlertLevel.CRITICAL.value == "critical"
        assert CostAlertLevel.BLOCKED.value == "blocked"
        assert CostAlertLevel.PAUSED.value == "paused"
    
    def test_level_ordering(self):
        """Alert levels should have logical ordering."""
        levels = [CostAlertLevel.INFO, CostAlertLevel.WARNING, 
                  CostAlertLevel.CRITICAL, CostAlertLevel.BLOCKED]
        # Just verify they're distinct
        assert len(set(levels)) == 4


class TestCostAlert:
    """Tests for CostAlert dataclass."""
    
    def test_create_alert(self):
        """Test creating a cost alert."""
        alert = CostAlert(
            level=CostAlertLevel.WARNING,
            message="Budget warning",
            current_cost=5.0,
            budget_limit=10.0
        )
        
        assert alert.level == CostAlertLevel.WARNING
        assert alert.message == "Budget warning"
        assert alert.current_cost == 5.0
        assert alert.budget_limit == 10.0
        assert alert.timestamp is not None
    
    def test_alert_to_dict(self):
        """Test converting alert to dictionary."""
        alert = CostAlert(
            level=CostAlertLevel.CRITICAL,
            message="Budget critical",
            current_cost=8.0,
            budget_limit=10.0
        )
        
        d = alert.to_dict()
        
        assert d["level"] == "critical"
        assert d["message"] == "Budget critical"
        assert d["current_cost"] == 8.0
        assert d["budget_limit"] == 10.0
        assert "timestamp" in d


class TestSessionCostTracker:
    """Tests for SessionCostTracker."""
    
    def test_create_session(self):
        """Test creating a session tracker."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=5.0
        )
        
        assert session.session_id == "test-123"
        assert session.session_type == "chat"
        assert session.budget_limit == 5.0
        assert session.total_cost == 0.0
        assert session.operation_count == 0
    
    def test_record_operation(self):
        """Test recording an operation."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=5.0
        )
        
        session.record_operation("research", 0.50, "Quick lookup")
        
        assert session.total_cost == 0.50
        assert session.operation_count == 1
        assert len(session.operations) == 1
        assert session.operations[0]["type"] == "research"
        assert session.operations[0]["cost"] == 0.50
    
    def test_multiple_operations_accumulate(self):
        """Test that multiple operations accumulate correctly."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="learning",
            budget_limit=10.0
        )
        
        session.record_operation("research", 0.50)
        session.record_operation("research", 1.00)
        session.record_operation("synthesis", 0.25)
        
        assert session.total_cost == 1.75
        assert session.operation_count == 3
    
    def test_alert_at_50_percent(self):
        """Test warning alert at 50% budget."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=10.0
        )
        
        session.record_operation("research", 5.0)  # 50%
        
        assert len(session.alerts) == 1
        assert session.alerts[0].level == CostAlertLevel.WARNING
        assert session.last_alert_level == CostAlertLevel.WARNING
    
    def test_alert_at_80_percent(self):
        """Test critical alert at 80% budget."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=10.0
        )
        
        session.record_operation("research", 8.0)  # 80%
        
        assert len(session.alerts) == 1
        assert session.alerts[0].level == CostAlertLevel.CRITICAL
    
    def test_alert_at_95_percent(self):
        """Test blocked alert at 95% budget."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=10.0
        )
        
        session.record_operation("research", 9.5)  # 95%
        
        assert len(session.alerts) == 1
        assert session.alerts[0].level == CostAlertLevel.BLOCKED
    
    def test_no_duplicate_alerts(self):
        """Test that alerts don't spam on same level."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=10.0
        )
        
        # Multiple operations at same level shouldn't create multiple alerts
        session.record_operation("research", 5.0)  # 50% - WARNING
        session.record_operation("research", 0.5)  # 55% - still WARNING
        session.record_operation("research", 0.5)  # 60% - still WARNING
        
        # Should only have one WARNING alert
        warning_alerts = [a for a in session.alerts if a.level == CostAlertLevel.WARNING]
        assert len(warning_alerts) == 1
    
    def test_can_proceed_within_budget(self):
        """Test can_proceed returns True within budget."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=10.0
        )
        
        session.record_operation("research", 2.0)
        
        can_proceed, reason = session.can_proceed(estimated_cost=1.0)
        
        assert can_proceed is True
        assert reason is None
    
    def test_can_proceed_exceeds_budget(self):
        """Test can_proceed returns False when exceeding budget."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=5.0
        )
        
        session.record_operation("research", 4.0)
        
        can_proceed, reason = session.can_proceed(estimated_cost=2.0)
        
        assert can_proceed is False
        assert "exceed budget" in reason.lower()
    
    def test_can_proceed_near_budget_limit(self):
        """Test can_proceed blocks at 95%+ budget."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=10.0
        )
        
        session.record_operation("research", 9.0)  # 90%
        
        # Trying to add 0.6 would put us at 96%
        can_proceed, reason = session.can_proceed(estimated_cost=0.6)
        
        assert can_proceed is False
        assert "95%" in reason or "exhausted" in reason.lower()
    
    def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opens after consecutive failures."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=10.0,
        )
        session.max_consecutive_failures = 3
        
        # Record 3 failures
        session.record_failure("research", "API error")
        session.record_failure("research", "API error")
        session.record_failure("research", "API error")
        
        assert session.is_circuit_open is True
        assert session.consecutive_failures == 3
    
    def test_circuit_breaker_blocks_operations(self):
        """Test circuit breaker blocks new operations."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=10.0,
        )
        session.max_consecutive_failures = 2
        
        session.record_failure("research", "Error 1")
        session.record_failure("research", "Error 2")
        
        can_proceed, reason = session.can_proceed(estimated_cost=0.1)
        
        assert can_proceed is False
        assert "circuit breaker" in reason.lower()
    
    def test_success_resets_failure_counter(self):
        """Test successful operation resets failure counter."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=10.0,
        )
        
        session.record_failure("research", "Error 1")
        session.record_failure("research", "Error 2")
        assert session.consecutive_failures == 2
        
        session.record_operation("research", 0.5)
        assert session.consecutive_failures == 0
    
    def test_get_remaining_budget(self):
        """Test getting remaining budget."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=10.0
        )
        
        session.record_operation("research", 3.0)
        
        assert session.get_remaining_budget() == 7.0
    
    def test_get_remaining_budget_no_limit(self):
        """Test remaining budget with no limit returns infinity."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="chat",
            budget_limit=0.0
        )
        
        assert session.get_remaining_budget() == float('inf')
    
    def test_get_summary(self):
        """Test getting session summary."""
        session = SessionCostTracker(
            session_id="test-123",
            session_type="learning",
            budget_limit=10.0
        )
        
        session.record_operation("research", 2.5)
        
        summary = session.get_summary()
        
        assert summary["session_id"] == "test-123"
        assert summary["session_type"] == "learning"
        assert summary["total_cost"] == 2.5
        assert summary["budget_limit"] == 10.0
        assert summary["remaining"] == 7.5
        assert summary["operation_count"] == 1


class TestCostSafetyManager:
    """Tests for CostSafetyManager."""
    
    def test_create_manager_with_defaults(self):
        """Test creating manager with default limits."""
        manager = CostSafetyManager()
        
        assert manager.max_per_operation == 5.0
        assert manager.max_daily == 25.0
        assert manager.max_monthly == 200.0
    
    def test_hard_limits_enforced(self):
        """Test that hard limits cannot be exceeded."""
        # Try to set limits above hard caps
        manager = CostSafetyManager(
            max_per_operation=100.0,  # Above $10 hard cap
            max_daily=1000.0,         # Above $50 hard cap
            max_monthly=10000.0       # Above $500 hard cap
        )
        
        # Should be capped at hard limits
        assert manager.max_per_operation == 10.0
        assert manager.max_daily == 50.0
        assert manager.max_monthly == 500.0
    
    def test_create_session(self):
        """Test creating a cost tracking session."""
        manager = CostSafetyManager()
        
        session = manager.create_session(
            session_id="test-123",
            session_type="chat",
            budget_limit=5.0
        )
        
        assert session.session_id == "test-123"
        assert session.session_type == "chat"
        assert "test-123" in manager.active_sessions
    
    def test_session_budget_capped_by_daily_remaining(self):
        """Test session budget is capped by remaining daily budget."""
        manager = CostSafetyManager(max_daily=10.0)
        manager.daily_cost = 7.0  # Already spent $7 today
        
        session = manager.create_session(
            session_id="test-123",
            session_type="chat",
            budget_limit=5.0  # Wants $5 but only $3 remaining
        )
        
        assert session.budget_limit == 3.0  # Capped at remaining daily
    
    def test_check_operation_allowed(self):
        """Test checking an allowed operation."""
        manager = CostSafetyManager()
        session = manager.create_session("test-123", "chat", 10.0)
        
        allowed, reason, needs_confirm = manager.check_operation(
            session_id="test-123",
            operation_type="research",
            estimated_cost=0.50
        )
        
        assert allowed is True
        assert reason is None
        assert needs_confirm is False  # Under $1 threshold
    
    def test_check_operation_needs_confirmation(self):
        """Test operation over $1 needs confirmation."""
        manager = CostSafetyManager()
        session = manager.create_session("test-123", "chat", 10.0)
        
        allowed, reason, needs_confirm = manager.check_operation(
            session_id="test-123",
            operation_type="research",
            estimated_cost=1.50
        )
        
        assert allowed is True
        assert needs_confirm is True
    
    def test_check_operation_exceeds_per_operation_limit(self):
        """Test operation exceeding per-operation limit is blocked."""
        manager = CostSafetyManager(max_per_operation=2.0)
        session = manager.create_session("test-123", "chat", 10.0)
        
        allowed, reason, _ = manager.check_operation(
            session_id="test-123",
            operation_type="research",
            estimated_cost=3.0
        )
        
        assert allowed is False
        assert "exceeds limit" in reason.lower()
    
    def test_check_operation_exceeds_daily_limit(self):
        """Test operation exceeding daily limit is blocked with DAILY_LIMIT."""
        manager = CostSafetyManager(max_daily=10.0)
        manager.daily_cost = 9.0
        session = manager.create_session("test-123", "chat", 5.0)
        
        allowed, reason, _ = manager.check_operation(
            session_id="test-123",
            operation_type="research",
            estimated_cost=2.0
        )
        
        assert allowed is False
        assert "DAILY_LIMIT" in reason
    
    def test_check_operation_exceeds_monthly_limit(self):
        """Test operation exceeding monthly limit is blocked with MONTHLY_LIMIT."""
        manager = CostSafetyManager(max_monthly=100.0)
        manager.monthly_cost = 99.0
        session = manager.create_session("test-123", "chat", 5.0)
        
        allowed, reason, _ = manager.check_operation(
            session_id="test-123",
            operation_type="research",
            estimated_cost=2.0
        )
        
        assert allowed is False
        assert "MONTHLY_LIMIT" in reason
    
    def test_record_cost(self):
        """Test recording actual cost."""
        manager = CostSafetyManager()
        session = manager.create_session("test-123", "chat", 10.0)
        
        manager.record_cost(
            session_id="test-123",
            operation_type="research",
            actual_cost=0.75,
            details="Quick lookup"
        )
        
        assert manager.daily_cost == 0.75
        assert manager.monthly_cost == 0.75
        assert session.total_cost == 0.75
    
    def test_record_failure(self):
        """Test recording a failed operation."""
        manager = CostSafetyManager()
        session = manager.create_session("test-123", "chat", 10.0)
        
        manager.record_failure(
            session_id="test-123",
            operation_type="research",
            error="API timeout"
        )
        
        assert session.consecutive_failures == 1
    
    def test_get_spending_summary(self):
        """Test getting spending summary."""
        manager = CostSafetyManager(max_daily=25.0, max_monthly=200.0)
        manager.daily_cost = 5.0
        manager.monthly_cost = 50.0
        
        summary = manager.get_spending_summary()
        
        assert summary["daily"]["spent"] == 5.0
        assert summary["daily"]["limit"] == 25.0
        assert summary["daily"]["remaining"] == 20.0
        assert summary["monthly"]["spent"] == 50.0
        assert summary["monthly"]["limit"] == 200.0
    
    def test_close_session(self):
        """Test closing a session."""
        manager = CostSafetyManager()
        session = manager.create_session("test-123", "chat", 10.0)
        session.record_operation("research", 1.0)
        
        summary = manager.close_session("test-123")
        
        assert summary is not None
        assert summary["total_cost"] == 1.0
        assert "test-123" not in manager.active_sessions
    
    def test_close_nonexistent_session(self):
        """Test closing a session that doesn't exist."""
        manager = CostSafetyManager()
        
        summary = manager.close_session("nonexistent")
        
        assert summary is None
    
    def test_daily_reset(self):
        """Test daily cost resets on new day."""
        manager = CostSafetyManager()
        manager.daily_cost = 10.0
        manager.last_reset_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        
        # Trigger reset check
        manager._reset_if_needed()
        
        assert manager.daily_cost == 0.0
    
    def test_monthly_reset(self):
        """Test monthly cost resets on new month."""
        manager = CostSafetyManager()
        manager.monthly_cost = 100.0
        
        # Set to previous month
        now = datetime.now(timezone.utc)
        if now.month == 1:
            manager.last_reset_month = 12
        else:
            manager.last_reset_month = now.month - 1
        
        # Trigger reset check
        manager._reset_if_needed()
        
        assert manager.monthly_cost == 0.0
    
    def test_audit_log_to_file(self):
        """Test audit logging to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            
            manager = CostSafetyManager(audit_log_path=audit_path)
            session = manager.create_session("test-123", "chat", 10.0)
            manager.record_cost("test-123", "research", 0.5)
            
            # Check file was written
            assert audit_path.exists()
            
            with open(audit_path) as f:
                lines = f.readlines()
            
            assert len(lines) >= 2  # session_created + cost_recorded
            
            # Verify JSON format
            for line in lines:
                entry = json.loads(line)
                assert "timestamp" in entry
                assert "event" in entry
                assert "data" in entry


class TestEstimateCurriculumCost:
    """Tests for curriculum cost estimation."""
    
    def test_estimate_with_explicit_counts(self):
        """Test estimation with explicit topic counts."""
        estimate = estimate_curriculum_cost(
            topic_count=10,
            deep_research_count=3,
            quick_research_count=5,
            docs_count=2
        )
        
        assert "expected_cost" in estimate
        assert "min_cost" in estimate
        assert "max_cost" in estimate
        assert "breakdown" in estimate
        
        # Deep research: 3 * $1.0 = $3.0
        assert estimate["breakdown"]["deep_research"] == 3.0
        # Quick research: 5 * $0.002 = $0.01
        assert estimate["breakdown"]["quick_research"] == 0.01
    
    def test_estimate_with_auto_distribution(self):
        """Test estimation with automatic distribution."""
        estimate = estimate_curriculum_cost(topic_count=10)
        
        # Should auto-distribute: 30% deep, 40% quick, 30% docs
        assert estimate["expected_cost"] > 0
        assert estimate["min_cost"] < estimate["expected_cost"]
        assert estimate["max_cost"] > estimate["expected_cost"]
    
    def test_estimate_min_max_range(self):
        """Test min/max are reasonable multiples of expected."""
        estimate = estimate_curriculum_cost(
            topic_count=10,
            deep_research_count=5,
            quick_research_count=5
        )
        
        # Min should be approximately 50% of expected (with rounding)
        assert abs(estimate["min_cost"] - estimate["expected_cost"] * 0.5) < 0.1
        # Max should be approximately 200% of expected (with rounding)
        assert abs(estimate["max_cost"] - estimate["expected_cost"] * 2.0) < 0.1


class TestFormatCostWarning:
    """Tests for cost warning formatting."""
    
    def test_format_within_budget(self):
        """Test formatting when within budget."""
        msg = format_cost_warning(estimated_cost=3.0, budget_limit=10.0)
        
        assert "$3.00" in msg
        assert "$10.00" in msg
        assert "30%" in msg
    
    def test_format_over_80_percent(self):
        """Test formatting when over 80% budget."""
        msg = format_cost_warning(estimated_cost=8.5, budget_limit=10.0)
        
        assert "Remaining" in msg
        assert "$1.50" in msg  # Remaining amount
    
    def test_format_exceeds_budget(self):
        """Test formatting when exceeding budget."""
        msg = format_cost_warning(estimated_cost=12.0, budget_limit=10.0)
        
        assert "EXCEEDS" in msg
        assert "Over budget" in msg
        assert "$2.00" in msg  # Over by amount
    
    def test_format_no_budget_limit(self):
        """Test formatting with no budget limit."""
        msg = format_cost_warning(estimated_cost=5.0, budget_limit=0.0)
        
        assert "no budget limit" in msg.lower()


class TestPausableLimitHelpers:
    """Tests for pausable limit helper functions."""
    
    def test_is_pausable_daily_limit(self):
        """Test detecting daily limit as pausable."""
        reason = "DAILY_LIMIT: Daily limit would be exceeded"
        assert is_pausable_limit(reason) is True
    
    def test_is_pausable_monthly_limit(self):
        """Test detecting monthly limit as pausable."""
        reason = "MONTHLY_LIMIT: Monthly limit would be exceeded"
        assert is_pausable_limit(reason) is True
    
    def test_is_not_pausable_operation_limit(self):
        """Test operation limit is not pausable."""
        reason = "Operation cost exceeds limit"
        assert is_pausable_limit(reason) is False
    
    def test_is_not_pausable_none(self):
        """Test None reason is not pausable."""
        assert is_pausable_limit(None) is False
    
    def test_is_not_pausable_empty(self):
        """Test empty reason is not pausable."""
        assert is_pausable_limit("") is False
    
    def test_get_resume_message_daily(self):
        """Test resume message for daily limit."""
        reason = "DAILY_LIMIT: exceeded"
        msg = get_resume_message(reason)
        
        assert "Daily" in msg
        assert "tomorrow" in msg.lower()
    
    def test_get_resume_message_monthly(self):
        """Test resume message for monthly limit."""
        reason = "MONTHLY_LIMIT: exceeded"
        msg = get_resume_message(reason)
        
        assert "Monthly" in msg
        assert "next month" in msg.lower()
    
    def test_get_resume_message_other(self):
        """Test resume message for non-pausable limit."""
        reason = "Operation blocked"
        msg = get_resume_message(reason)
        
        assert "Check the error" in msg


class TestCostSafetyIntegration:
    """Integration tests for cost safety system."""
    
    def test_full_session_lifecycle(self):
        """Test complete session lifecycle."""
        manager = CostSafetyManager(
            max_per_operation=5.0,
            max_daily=25.0,
            max_monthly=200.0
        )
        
        # Create session
        session = manager.create_session("test-123", "learning", 10.0)
        
        # Check and record multiple operations
        for i in range(5):
            allowed, reason, _ = manager.check_operation(
                "test-123", "research", 0.50
            )
            assert allowed is True
            manager.record_cost("test-123", "research", 0.50)
        
        # Verify totals
        assert session.total_cost == 2.5
        assert manager.daily_cost == 2.5
        
        # Close session
        summary = manager.close_session("test-123")
        assert summary["total_cost"] == 2.5
    
    def test_budget_exhaustion_flow(self):
        """Test flow when budget is exhausted."""
        manager = CostSafetyManager()
        session = manager.create_session("test-123", "chat", 2.0)
        
        # Use most of budget
        manager.record_cost("test-123", "research", 1.8)
        
        # Try to do more
        allowed, reason, _ = manager.check_operation(
            "test-123", "research", 0.5
        )
        
        assert allowed is False
        assert "budget" in reason.lower() or "95%" in reason
    
    def test_circuit_breaker_recovery(self):
        """Test circuit breaker opens and blocks operations."""
        manager = CostSafetyManager()
        session = manager.create_session("test-123", "chat", 10.0)
        session.max_consecutive_failures = 2
        
        # Trigger circuit breaker
        manager.record_failure("test-123", "research", "Error 1")
        manager.record_failure("test-123", "research", "Error 2")
        
        # Should be blocked
        allowed, reason, _ = manager.check_operation(
            "test-123", "research", 0.1
        )
        
        assert allowed is False
        assert "circuit breaker" in reason.lower()
