"""Tests for composed manager integration in ExpertProfile.

Verifies that BudgetManager and ActivityTracker are properly integrated
with ExpertProfile and that delegation works correctly.

Requirements: 5.1, 5.2, 5.3 - Composed manager integration
"""

import pytest
from datetime import datetime, timedelta

from deepr.experts import ExpertProfile, BudgetManager, ActivityTracker


class TestBudgetManagerIntegration:
    """Test BudgetManager integration with ExpertProfile."""
    
    def test_budget_manager_initialized(self):
        """Budget manager should be initialized on profile creation."""
        profile = ExpertProfile(name="test", vector_store_id="vs_123")
        assert profile.budget_manager is not None
        assert isinstance(profile.budget_manager, BudgetManager)
    
    def test_can_spend_delegates_to_manager(self):
        """can_spend_learning_budget should delegate to BudgetManager."""
        profile = ExpertProfile(
            name="test",
            vector_store_id="vs_123",
            monthly_learning_budget=10.0
        )
        
        can_spend, reason = profile.can_spend_learning_budget(5.0)
        assert can_spend is True
        assert "Within budget" in reason
    
    def test_record_spending_updates_profile(self):
        """record_learning_spend should update profile fields."""
        profile = ExpertProfile(
            name="test",
            vector_store_id="vs_123",
            monthly_learning_budget=10.0
        )
        
        profile.record_learning_spend(3.0, "test_op", "test details")
        
        # Profile fields should be synced
        assert profile.monthly_spending == 3.0
        assert profile.total_research_cost == 3.0
        assert len(profile.refresh_history) == 1
    
    def test_budget_status_returns_correct_values(self):
        """get_monthly_budget_status should return correct values."""
        profile = ExpertProfile(
            name="test",
            vector_store_id="vs_123",
            monthly_learning_budget=10.0
        )
        
        profile.record_learning_spend(4.0, "test_op")
        status = profile.get_monthly_budget_status()
        
        assert status["monthly_budget"] == 10.0
        assert status["monthly_spent"] == 4.0
        assert status["monthly_remaining"] == 6.0
        assert status["usage_percent"] == 40.0
    
    def test_budget_exhausted_blocks_spending(self):
        """Should not allow spending when budget exhausted."""
        profile = ExpertProfile(
            name="test",
            vector_store_id="vs_123",
            monthly_learning_budget=5.0
        )
        
        profile.record_learning_spend(5.0, "test_op")
        
        can_spend, reason = profile.can_spend_learning_budget(1.0)
        assert can_spend is False
        assert "exhausted" in reason.lower()


class TestActivityTrackerIntegration:
    """Test ActivityTracker integration with ExpertProfile."""
    
    def test_activity_tracker_initialized(self):
        """Activity tracker should be initialized on profile creation."""
        profile = ExpertProfile(name="test", vector_store_id="vs_123")
        assert profile.activity_tracker is not None
        assert isinstance(profile.activity_tracker, ActivityTracker)
    
    def test_record_chat_increments_conversations(self):
        """Recording chat activity should increment conversations."""
        profile = ExpertProfile(name="test", vector_store_id="vs_123")
        
        profile.record_activity("chat", {"topic": "test"})
        profile.record_activity("chat", {"topic": "test2"})
        
        assert profile.conversations == 2
    
    def test_record_research_increments_research_triggered(self):
        """Recording research activity should increment research_triggered."""
        profile = ExpertProfile(name="test", vector_store_id="vs_123")
        
        profile.record_activity("research", {"query": "test"})
        
        assert profile.research_triggered == 1
    
    def test_record_activity_updates_timestamp(self):
        """Recording activity should update updated_at timestamp."""
        profile = ExpertProfile(name="test", vector_store_id="vs_123")
        original_time = profile.updated_at
        
        # Small delay to ensure timestamp changes
        import time
        time.sleep(0.01)
        
        profile.record_activity("chat")
        
        assert profile.updated_at > original_time


class TestSerializationWithManagers:
    """Test serialization preserves manager state."""
    
    def test_budget_state_preserved_in_serialization(self):
        """Budget state should be preserved through serialization."""
        profile = ExpertProfile(
            name="test",
            vector_store_id="vs_123",
            monthly_learning_budget=10.0
        )
        
        profile.record_learning_spend(3.5, "test_op", "details")
        
        # Serialize and restore
        data = profile.to_dict()
        restored = ExpertProfile.from_dict(data)
        
        assert restored.monthly_spending == 3.5
        assert restored.total_research_cost == 3.5
        assert len(restored.refresh_history) == 1
    
    def test_activity_state_preserved_in_serialization(self):
        """Activity state should be preserved through serialization."""
        profile = ExpertProfile(name="test", vector_store_id="vs_123")
        
        profile.record_activity("chat")
        profile.record_activity("chat")
        profile.record_activity("research")
        
        # Serialize and restore
        data = profile.to_dict()
        restored = ExpertProfile.from_dict(data)
        
        assert restored.conversations == 2
        assert restored.research_triggered == 1
    
    def test_composed_components_not_in_dict(self):
        """Composed components should not appear in serialized dict."""
        profile = ExpertProfile(name="test", vector_store_id="vs_123")
        data = profile.to_dict()
        
        assert "_budget_manager" not in data
        assert "_activity_tracker" not in data
        assert "_temporal_state" not in data
        assert "_freshness_checker" not in data


class TestBudgetManagerStandalone:
    """Test BudgetManager as standalone component."""
    
    def test_create_budget_manager(self):
        """Should create BudgetManager with defaults."""
        manager = BudgetManager()
        assert manager.monthly_budget == 5.0
        assert manager.monthly_spending == 0.0
    
    def test_budget_manager_can_spend(self):
        """Should correctly check spending allowance."""
        manager = BudgetManager(monthly_budget=10.0)
        
        can, reason = manager.can_spend(5.0)
        assert can is True
        
        can, reason = manager.can_spend(15.0)
        assert can is False
    
    def test_budget_manager_record_spending(self):
        """Should record spending correctly."""
        manager = BudgetManager(monthly_budget=10.0)
        
        manager.record_spending(3.0, "test", "details")
        
        assert manager.monthly_spending == 3.0
        assert manager.total_spending == 3.0
        assert len(manager.refresh_history) == 1
    
    def test_budget_manager_serialization(self):
        """Should serialize and deserialize correctly."""
        manager = BudgetManager(monthly_budget=10.0)
        manager.record_spending(2.5, "test")
        
        data = manager.to_dict()
        restored = BudgetManager.from_dict(data)
        
        assert restored.monthly_budget == 10.0
        assert restored.monthly_spending == 2.5
        assert restored.total_spending == 2.5


class TestActivityTrackerStandalone:
    """Test ActivityTracker as standalone component."""
    
    def test_create_activity_tracker(self):
        """Should create ActivityTracker with defaults."""
        tracker = ActivityTracker()
        assert tracker.conversations == 0
        assert tracker.research_triggered == 0
    
    def test_activity_tracker_record_chat(self):
        """Should record chat activity."""
        tracker = ActivityTracker()
        
        tracker.record_activity("chat", {"topic": "test"})
        
        assert tracker.conversations == 1
        assert tracker.last_activity is not None
    
    def test_activity_tracker_record_research(self):
        """Should record research activity."""
        tracker = ActivityTracker()
        
        tracker.record_activity("research", {"query": "test"})
        
        assert tracker.research_triggered == 1
    
    def test_activity_tracker_serialization(self):
        """Should serialize and deserialize correctly."""
        tracker = ActivityTracker()
        tracker.record_activity("chat")
        tracker.record_activity("research")
        
        data = tracker.to_dict()
        restored = ActivityTracker.from_dict(data)
        
        assert restored.conversations == 1
        assert restored.research_triggered == 1
