"""Property-based tests for ExpertProfile.

Uses Hypothesis to verify universal correctness properties:
- Property 6: ExpertProfile Serialization Round-Trip
- Property 7: Domain Velocity Threshold Calculation

Requirements: 4.5, 4.6 - Property-based testing for ExpertProfile
"""

import pytest
from datetime import datetime, timedelta, timezone
from hypothesis import given, strategies as st, settings, assume

from deepr.experts.profile import ExpertProfile


def utc_now():
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)
from deepr.experts.budget_manager import BudgetManager
from deepr.experts.activity_tracker import ActivityTracker
from deepr.experts.serializer import (
    profile_to_dict,
    dict_to_profile_kwargs,
    datetime_to_iso,
    iso_to_datetime
)


# =============================================================================
# Custom Strategies
# =============================================================================

# Strategy for valid expert names (alphanumeric with spaces/hyphens)
expert_name_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_"),
    min_size=1,
    max_size=50
).filter(lambda x: x.strip() and not x.startswith(" ") and not x.endswith(" "))

# Strategy for vector store IDs
vector_store_id_strategy = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789_"),
    min_size=5,
    max_size=30
).map(lambda x: f"vs_{x}")

# Strategy for domain velocity
domain_velocity_strategy = st.sampled_from(["slow", "medium", "fast"])

# Strategy for reasonable datetime values (within last 2 years) - timezone-aware
datetime_strategy = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2026, 12, 31),
    timezones=st.just(timezone.utc)
)

# Strategy for optional datetime
optional_datetime_strategy = st.one_of(st.none(), datetime_strategy)

# Strategy for budget amounts
budget_strategy = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)

# Strategy for spending amounts
spending_strategy = st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)


# =============================================================================
# Property 6: ExpertProfile Serialization Round-Trip
# =============================================================================

class TestSerializationRoundTrip:
    """Property tests for serialization round-trip consistency."""
    
    @given(
        name=expert_name_strategy,
        vector_store_id=vector_store_id_strategy,
        domain_velocity=domain_velocity_strategy,
        monthly_budget=budget_strategy,
        monthly_spending=spending_strategy
    )
    @settings(max_examples=50, deadline=None)
    def test_profile_roundtrip_preserves_core_fields(
        self,
        name: str,
        vector_store_id: str,
        domain_velocity: str,
        monthly_budget: float,
        monthly_spending: float
    ):
        """Property: to_dict -> from_dict preserves all core fields."""
        # Ensure spending doesn't exceed budget
        monthly_spending = min(monthly_spending, monthly_budget)
        
        original = ExpertProfile(
            name=name,
            vector_store_id=vector_store_id,
            domain_velocity=domain_velocity,
            monthly_learning_budget=monthly_budget,
            monthly_spending=monthly_spending
        )
        
        # Round-trip
        data = original.to_dict()
        restored = ExpertProfile.from_dict(data)
        
        # Core fields must be preserved
        assert restored.name == original.name
        assert restored.vector_store_id == original.vector_store_id
        assert restored.domain_velocity == original.domain_velocity
        assert restored.monthly_learning_budget == original.monthly_learning_budget
        assert restored.monthly_spending == original.monthly_spending
    
    @given(
        name=expert_name_strategy,
        vector_store_id=vector_store_id_strategy,
        knowledge_cutoff=optional_datetime_strategy,
        last_refresh=optional_datetime_strategy
    )
    @settings(max_examples=50, deadline=None)
    def test_profile_roundtrip_preserves_datetime_fields(
        self,
        name: str,
        vector_store_id: str,
        knowledge_cutoff,
        last_refresh
    ):
        """Property: datetime fields survive serialization round-trip."""
        original = ExpertProfile(
            name=name,
            vector_store_id=vector_store_id,
            knowledge_cutoff_date=knowledge_cutoff,
            last_knowledge_refresh=last_refresh
        )
        
        # Round-trip
        data = original.to_dict()
        restored = ExpertProfile.from_dict(data)
        
        # Datetime fields must be preserved (with microsecond precision loss acceptable)
        if original.knowledge_cutoff_date:
            assert restored.knowledge_cutoff_date is not None
            # Allow 1 second tolerance for serialization
            delta = abs((restored.knowledge_cutoff_date - original.knowledge_cutoff_date).total_seconds())
            assert delta < 1
        else:
            assert restored.knowledge_cutoff_date is None
        
        if original.last_knowledge_refresh:
            assert restored.last_knowledge_refresh is not None
            delta = abs((restored.last_knowledge_refresh - original.last_knowledge_refresh).total_seconds())
            assert delta < 1
        else:
            assert restored.last_knowledge_refresh is None
    
    @given(
        name=expert_name_strategy,
        vector_store_id=vector_store_id_strategy,
        conversations=st.integers(min_value=0, max_value=10000),
        research_triggered=st.integers(min_value=0, max_value=1000)
    )
    @settings(max_examples=50, deadline=None)
    def test_profile_roundtrip_preserves_counters(
        self,
        name: str,
        vector_store_id: str,
        conversations: int,
        research_triggered: int
    ):
        """Property: activity counters survive serialization round-trip."""
        original = ExpertProfile(
            name=name,
            vector_store_id=vector_store_id,
            conversations=conversations,
            research_triggered=research_triggered
        )
        
        # Round-trip
        data = original.to_dict()
        restored = ExpertProfile.from_dict(data)
        
        assert restored.conversations == original.conversations
        assert restored.research_triggered == original.research_triggered


# =============================================================================
# Property 7: Domain Velocity Threshold Calculation
# =============================================================================

class TestDomainVelocityThresholds:
    """Property tests for domain velocity threshold calculations."""
    
    @given(
        domain_velocity=domain_velocity_strategy,
        days_old=st.integers(min_value=0, max_value=365)
    )
    @settings(max_examples=100, deadline=None)
    def test_staleness_consistent_with_velocity(
        self,
        domain_velocity: str,
        days_old: int
    ):
        """Property: staleness detection is consistent with domain velocity thresholds."""
        now = utc_now()
        cutoff = now - timedelta(days=days_old)
        
        profile = ExpertProfile(
            name="test",
            vector_store_id="vs_test",
            knowledge_cutoff_date=cutoff,
            domain_velocity=domain_velocity
        )
        
        # Get threshold for this velocity
        velocity_thresholds = {"slow": 180, "medium": 90, "fast": 30}
        threshold = velocity_thresholds[domain_velocity]
        
        is_stale = profile.is_knowledge_stale()
        
        # Staleness should be consistent with threshold
        # Note: FreshnessChecker uses threshold as the stale boundary
        if days_old > threshold:
            assert is_stale is True, f"Should be stale: {days_old} days > {threshold} threshold"
        elif days_old < threshold * 0.5:
            # Well under threshold should be fresh
            assert is_stale is False, f"Should be fresh: {days_old} days < {threshold * 0.5} (50% of threshold)"
    
    @given(domain_velocity=domain_velocity_strategy)
    @settings(max_examples=30, deadline=None)
    def test_freshness_status_has_required_fields(self, domain_velocity: str):
        """Property: freshness status always contains required fields."""
        now = utc_now()
        cutoff = now - timedelta(days=45)
        
        profile = ExpertProfile(
            name="test",
            vector_store_id="vs_test",
            knowledge_cutoff_date=cutoff,
            domain_velocity=domain_velocity
        )
        
        status = profile.get_freshness_status()
        
        # Required fields must always be present
        assert "status" in status
        assert status["status"] in ["fresh", "aging", "stale", "incomplete", "unknown"]
        
        # If not incomplete, should have age info
        if status["status"] != "incomplete":
            assert "age_days" in status
            assert "threshold_days" in status
            assert isinstance(status["age_days"], int)
            assert isinstance(status["threshold_days"], int)
    
    @given(domain_velocity=domain_velocity_strategy)
    @settings(max_examples=30, deadline=None)
    def test_incomplete_expert_always_incomplete_status(self, domain_velocity: str):
        """Property: expert without knowledge_cutoff_date is always 'incomplete'."""
        profile = ExpertProfile(
            name="test",
            vector_store_id="vs_test",
            knowledge_cutoff_date=None,
            domain_velocity=domain_velocity
        )
        
        status = profile.get_freshness_status()
        
        assert status["status"] == "incomplete"
        assert "action_required" in status
        assert status["action_required"] is not None


# =============================================================================
# Property Tests for Composed Managers
# =============================================================================

class TestBudgetManagerProperties:
    """Property tests for BudgetManager."""
    
    @given(
        budget=budget_strategy,
        spending=spending_strategy
    )
    @settings(max_examples=50, deadline=None)
    def test_remaining_budget_never_negative(self, budget: float, spending: float):
        """Property: remaining budget is never negative."""
        manager = BudgetManager(
            monthly_budget=budget,
            monthly_spending=spending
        )
        
        remaining = manager.get_remaining_budget()
        
        assert remaining >= 0
    
    @given(
        budget=st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        amount=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=50, deadline=None)
    def test_can_spend_consistent_with_remaining(self, budget: float, amount: float):
        """Property: can_spend result is consistent with remaining budget."""
        manager = BudgetManager(monthly_budget=budget, monthly_spending=0.0)
        
        can_spend, _ = manager.can_spend(amount)
        remaining = manager.get_remaining_budget()
        
        if amount <= 0:
            assert can_spend is True
        elif amount <= remaining:
            assert can_spend is True
        else:
            assert can_spend is False
    
    @given(
        budget=budget_strategy,
        spending=spending_strategy
    )
    @settings(max_examples=50, deadline=None)
    def test_budget_manager_serialization_roundtrip(self, budget: float, spending: float):
        """Property: BudgetManager survives serialization round-trip."""
        original = BudgetManager(
            monthly_budget=budget,
            monthly_spending=spending,
            total_spending=spending * 2
        )
        
        data = original.to_dict()
        restored = BudgetManager.from_dict(data)
        
        assert restored.monthly_budget == original.monthly_budget
        assert restored.monthly_spending == original.monthly_spending
        assert restored.total_spending == original.total_spending


class TestActivityTrackerProperties:
    """Property tests for ActivityTracker."""
    
    @given(
        conversations=st.integers(min_value=0, max_value=10000),
        research=st.integers(min_value=0, max_value=1000)
    )
    @settings(max_examples=50, deadline=None)
    def test_activity_tracker_serialization_roundtrip(
        self,
        conversations: int,
        research: int
    ):
        """Property: ActivityTracker survives serialization round-trip."""
        original = ActivityTracker(
            conversations=conversations,
            research_triggered=research
        )
        
        data = original.to_dict()
        restored = ActivityTracker.from_dict(data)
        
        assert restored.conversations == original.conversations
        assert restored.research_triggered == original.research_triggered
    
    @given(activity_type=st.sampled_from(["chat", "research", "learning", "other"]))
    @settings(max_examples=30, deadline=None)
    def test_record_activity_updates_last_activity(self, activity_type: str):
        """Property: recording activity always updates last_activity timestamp."""
        tracker = ActivityTracker()
        
        assert tracker.last_activity is None
        
        tracker.record_activity(activity_type)
        
        assert tracker.last_activity is not None
        assert isinstance(tracker.last_activity, datetime)


# =============================================================================
# Property Tests for Serializer Module
# =============================================================================

class TestSerializerProperties:
    """Property tests for serializer utilities."""
    
    @given(dt=datetime_strategy)
    @settings(max_examples=50, deadline=None)
    def test_datetime_iso_roundtrip(self, dt: datetime):
        """Property: datetime -> ISO -> datetime preserves value."""
        iso_str = datetime_to_iso(dt)
        restored = iso_to_datetime(iso_str)
        
        # Allow microsecond precision loss
        delta = abs((restored - dt).total_seconds())
        assert delta < 1
    
    @given(st.none())
    @settings(max_examples=1, deadline=None)
    def test_datetime_iso_handles_none(self, _):
        """Property: None datetime converts to None ISO and back."""
        assert datetime_to_iso(None) is None
        assert iso_to_datetime(None) is None
