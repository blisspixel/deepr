"""Unit and property tests for TemporalState and FreshnessChecker.

Task 17.5: Tests for refactored classes including:
- TemporalState methods
- FreshnessChecker methods
- Backward compatibility

Uses hypothesis for property-based testing.
"""

import math
from datetime import datetime, timedelta, timezone


def utc_now():
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from deepr.experts.freshness import FreshnessChecker, FreshnessLevel, FreshnessStatus
from deepr.experts.temporal import TemporalState

# =============================================================================
# Unit Tests: TemporalState
# =============================================================================


class TestTemporalStateCreation:
    """Unit tests for TemporalState creation."""

    def test_default_creation(self):
        """Test creating TemporalState with defaults."""
        state = TemporalState()

        assert state.created_at is not None
        assert state.last_activity is not None
        assert state.last_learning is None
        assert state.last_chat is None
        assert state.activity_history == []

    def test_creation_with_values(self):
        """Test creating TemporalState with specific values."""
        created = datetime(2024, 1, 1)
        last_activity = datetime(2024, 6, 1)

        state = TemporalState(created_at=created, last_activity=last_activity)

        assert state.created_at == created
        assert state.last_activity == last_activity


class TestTemporalStateActivity:
    """Unit tests for TemporalState activity recording."""

    def test_record_chat_activity(self):
        """Test recording chat activity."""
        state = TemporalState()

        state.record_activity("chat", {"message": "test"})

        assert state.last_chat is not None
        assert len(state.activity_history) == 1
        assert state.activity_history[0]["type"] == "chat"

    def test_record_learn_activity(self):
        """Test recording learn activity."""
        state = TemporalState()

        state.record_activity("learn", {"document": "test.pdf"})

        assert state.last_learning is not None
        assert len(state.activity_history) == 1
        assert state.activity_history[0]["type"] == "learn"

    def test_record_refresh_activity(self):
        """Test recording refresh activity updates last_learning."""
        state = TemporalState()

        state.record_activity("refresh")

        assert state.last_learning is not None

    def test_record_upload_activity(self):
        """Test recording upload activity updates last_learning."""
        state = TemporalState()

        state.record_activity("upload")

        assert state.last_learning is not None

    def test_activity_history_limit(self):
        """Test activity history is limited to 100 entries."""
        state = TemporalState()

        for i in range(150):
            state.record_activity("chat", {"index": i})

        assert len(state.activity_history) == 100
        # Should keep most recent
        assert state.activity_history[-1]["details"]["index"] == 149


class TestTemporalStateDays:
    """Unit tests for TemporalState day calculations."""

    def test_days_since_creation(self):
        """Test days since creation calculation."""
        state = TemporalState(created_at=utc_now() - timedelta(days=30))

        days = state.days_since_creation()

        assert days == 30

    def test_days_since_last_activity(self):
        """Test days since last activity calculation."""
        state = TemporalState(last_activity=utc_now() - timedelta(days=15))

        days = state.days_since_last_activity()

        assert days == 15

    def test_days_since_last_learning_none(self):
        """Test days since last learning when never learned."""
        state = TemporalState()

        days = state.days_since_last_learning()

        assert days is None

    def test_days_since_last_learning_with_value(self):
        """Test days since last learning with value."""
        state = TemporalState(last_learning=utc_now() - timedelta(days=10))

        days = state.days_since_last_learning()

        assert days == 10

    def test_days_since_last_chat_none(self):
        """Test days since last chat when never chatted."""
        state = TemporalState()

        days = state.days_since_last_chat()

        assert days is None

    def test_days_since_last_chat_with_value(self):
        """Test days since last chat with value."""
        state = TemporalState(last_chat=utc_now() - timedelta(days=5))

        days = state.days_since_last_chat()

        assert days == 5


class TestTemporalStateActivityCount:
    """Unit tests for activity counting."""

    def test_get_activity_count_empty(self):
        """Test activity count with no history."""
        state = TemporalState()

        count = state.get_activity_count("chat")

        assert count == 0

    def test_get_activity_count_with_activities(self):
        """Test activity count with activities."""
        state = TemporalState()

        for _ in range(5):
            state.record_activity("chat")
        for _ in range(3):
            state.record_activity("learn")

        assert state.get_activity_count("chat") == 5
        assert state.get_activity_count("learn") == 3

    def test_get_activity_count_respects_days(self):
        """Test activity count respects days parameter."""
        state = TemporalState()

        # Add recent activity
        state.record_activity("chat")

        # Add old activity manually
        old_entry = {"type": "chat", "timestamp": (utc_now() - timedelta(days=60)).isoformat(), "details": {}}
        state.activity_history.insert(0, old_entry)

        # Should only count recent
        assert state.get_activity_count("chat", days=30) == 1
        # Should count all
        assert state.get_activity_count("chat", days=90) == 2


class TestTemporalStateStatus:
    """Unit tests for activity status checks."""

    def test_is_active_true(self):
        """Test is_active returns True for recent activity."""
        state = TemporalState(last_activity=utc_now() - timedelta(days=10))

        assert state.is_active(threshold_days=30) is True

    def test_is_active_false(self):
        """Test is_active returns False for old activity."""
        state = TemporalState(last_activity=utc_now() - timedelta(days=60))

        assert state.is_active(threshold_days=30) is False

    def test_is_dormant_true(self):
        """Test is_dormant returns True for very old activity."""
        state = TemporalState(last_activity=utc_now() - timedelta(days=120))

        assert state.is_dormant(threshold_days=90) is True

    def test_is_dormant_false(self):
        """Test is_dormant returns False for recent activity."""
        state = TemporalState(last_activity=utc_now() - timedelta(days=30))

        assert state.is_dormant(threshold_days=90) is False


class TestTemporalStateAgeCategory:
    """Unit tests for age category."""

    def test_age_category_new(self):
        """Test new age category."""
        state = TemporalState(created_at=utc_now() - timedelta(days=3))

        assert state.get_age_category() == "new"

    def test_age_category_young(self):
        """Test young age category."""
        state = TemporalState(created_at=utc_now() - timedelta(days=15))

        assert state.get_age_category() == "young"

    def test_age_category_established(self):
        """Test established age category."""
        state = TemporalState(created_at=utc_now() - timedelta(days=60))

        assert state.get_age_category() == "established"

    def test_age_category_mature(self):
        """Test mature age category."""
        state = TemporalState(created_at=utc_now() - timedelta(days=200))

        assert state.get_age_category() == "mature"


class TestTemporalStateSerialization:
    """Unit tests for TemporalState serialization."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        state = TemporalState()
        state.record_activity("chat")

        data = state.to_dict()

        assert "created_at" in data
        assert "last_activity" in data
        assert "activity_history" in data
        assert len(data["activity_history"]) == 1

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        original = TemporalState()
        original.record_activity("chat")
        original.record_activity("learn")

        data = original.to_dict()
        restored = TemporalState.from_dict(data)

        assert restored.created_at == original.created_at
        assert restored.last_activity == original.last_activity
        assert len(restored.activity_history) == len(original.activity_history)

    def test_roundtrip_serialization(self):
        """Test roundtrip serialization preserves data."""
        original = TemporalState(
            created_at=datetime(2024, 1, 1),
            last_activity=datetime(2024, 6, 1),
            last_learning=datetime(2024, 5, 1),
            last_chat=datetime(2024, 6, 1),
        )

        data = original.to_dict()
        restored = TemporalState.from_dict(data)

        assert restored.created_at == original.created_at
        assert restored.last_learning == original.last_learning
        assert restored.last_chat == original.last_chat


# =============================================================================
# Unit Tests: FreshnessChecker
# =============================================================================


class TestFreshnessCheckerCreation:
    """Unit tests for FreshnessChecker creation."""

    def test_default_creation(self):
        """Test creating FreshnessChecker with defaults."""
        checker = FreshnessChecker()

        assert checker.domain == "general"
        assert checker.velocity_days == 365

    def test_creation_with_domain(self):
        """Test creating FreshnessChecker with specific domain."""
        checker = FreshnessChecker(domain="technology")

        assert checker.domain == "technology"
        assert checker.velocity_days == 90

    def test_creation_with_custom_velocity(self):
        """Test creating FreshnessChecker with custom velocity."""
        checker = FreshnessChecker(domain="technology", velocity_days=60)

        assert checker.velocity_days == 60

    def test_for_domain_factory(self):
        """Test for_domain factory method."""
        checker = FreshnessChecker.for_domain("ai")

        assert checker.domain == "ai"
        assert checker.velocity_days == 60


class TestFreshnessCheckerCheck:
    """Unit tests for FreshnessChecker.check()."""

    def test_check_no_learning_history(self):
        """Test check with no learning history."""
        checker = FreshnessChecker()

        status = checker.check()

        assert status.level == FreshnessLevel.CRITICAL
        assert status.days_since_update == 999
        assert status.score == 0.0

    def test_check_fresh(self):
        """Test check with fresh knowledge."""
        checker = FreshnessChecker(domain="technology", velocity_days=90)

        status = checker.check(last_learning=utc_now() - timedelta(days=10))

        assert status.level == FreshnessLevel.FRESH
        assert status.days_since_update == 10
        assert status.score > 0.8

    def test_check_aging(self):
        """Test check with aging knowledge."""
        checker = FreshnessChecker(domain="technology", velocity_days=90)

        # 50-80% of velocity = aging (45-72 days for 90 day velocity)
        status = checker.check(last_learning=utc_now() - timedelta(days=60))

        assert status.level == FreshnessLevel.AGING
        assert status.days_since_update == 60

    def test_check_stale(self):
        """Test check with stale knowledge."""
        checker = FreshnessChecker(domain="technology", velocity_days=90)

        # 100-150% of velocity = stale (90-135 days for 90 day velocity)
        status = checker.check(last_learning=utc_now() - timedelta(days=100))

        assert status.level == FreshnessLevel.STALE
        assert status.days_since_update == 100

    def test_check_critical(self):
        """Test check with critical knowledge."""
        checker = FreshnessChecker(domain="technology", velocity_days=90)

        # >150% of velocity = critical (>135 days for 90 day velocity)
        status = checker.check(last_learning=utc_now() - timedelta(days=200))

        assert status.level == FreshnessLevel.CRITICAL
        assert status.days_since_update == 200

    def test_check_uses_last_activity_fallback(self):
        """Test check falls back to last_activity."""
        checker = FreshnessChecker(domain="technology", velocity_days=90)

        status = checker.check(last_activity=utc_now() - timedelta(days=30))

        assert status.level == FreshnessLevel.FRESH
        assert status.days_since_update == 30


class TestFreshnessCheckerMethods:
    """Unit tests for FreshnessChecker helper methods."""

    def test_is_stale_true(self):
        """Test is_stale returns True for stale knowledge."""
        checker = FreshnessChecker(domain="technology", velocity_days=90)

        result = checker.is_stale(last_learning=utc_now() - timedelta(days=100))

        assert result is True

    def test_is_stale_false(self):
        """Test is_stale returns False for fresh knowledge."""
        checker = FreshnessChecker(domain="technology", velocity_days=90)

        result = checker.is_stale(last_learning=utc_now() - timedelta(days=30))

        assert result is False

    def test_days_until_stale_positive(self):
        """Test days_until_stale with fresh knowledge."""
        checker = FreshnessChecker(domain="technology", velocity_days=90)

        days = checker.days_until_stale(last_learning=utc_now() - timedelta(days=30))

        assert days == 60  # 90 - 30

    def test_days_until_stale_negative(self):
        """Test days_until_stale with stale knowledge."""
        checker = FreshnessChecker(domain="technology", velocity_days=90)

        days = checker.days_until_stale(last_learning=utc_now() - timedelta(days=120))

        assert days == -30  # 90 - 120

    def test_days_until_stale_no_learning(self):
        """Test days_until_stale with no learning."""
        checker = FreshnessChecker()

        days = checker.days_until_stale(last_learning=None)

        assert days == -999

    def test_get_status(self):
        """Test get_status returns dictionary."""
        checker = FreshnessChecker(domain="technology", velocity_days=90)

        status = checker.get_status(last_learning=utc_now() - timedelta(days=30))

        assert isinstance(status, dict)
        assert "level" in status
        assert "score" in status
        assert "recommendation" in status


class TestFreshnessStatus:
    """Unit tests for FreshnessStatus."""

    def test_is_stale_for_stale_level(self):
        """Test is_stale returns True for STALE level."""
        status = FreshnessStatus(
            level=FreshnessLevel.STALE,
            days_since_update=100,
            threshold_days=90,
            score=0.3,
            recommendation="Refresh",
            details={},
        )

        assert status.is_stale() is True

    def test_is_stale_for_critical_level(self):
        """Test is_stale returns True for CRITICAL level."""
        status = FreshnessStatus(
            level=FreshnessLevel.CRITICAL,
            days_since_update=200,
            threshold_days=90,
            score=0.1,
            recommendation="Urgent refresh",
            details={},
        )

        assert status.is_stale() is True

    def test_is_stale_for_fresh_level(self):
        """Test is_stale returns False for FRESH level."""
        status = FreshnessStatus(
            level=FreshnessLevel.FRESH,
            days_since_update=10,
            threshold_days=90,
            score=0.9,
            recommendation="No action",
            details={},
        )

        assert status.is_stale() is False

    def test_needs_refresh_for_aging(self):
        """Test needs_refresh returns True for AGING level."""
        status = FreshnessStatus(
            level=FreshnessLevel.AGING,
            days_since_update=60,
            threshold_days=90,
            score=0.5,
            recommendation="Consider refresh",
            details={},
        )

        assert status.needs_refresh() is True

    def test_needs_refresh_for_fresh(self):
        """Test needs_refresh returns False for FRESH level."""
        status = FreshnessStatus(
            level=FreshnessLevel.FRESH,
            days_since_update=10,
            threshold_days=90,
            score=0.9,
            recommendation="No action",
            details={},
        )

        assert status.needs_refresh() is False

    def test_to_dict(self):
        """Test FreshnessStatus serialization."""
        status = FreshnessStatus(
            level=FreshnessLevel.FRESH,
            days_since_update=10,
            threshold_days=90,
            score=0.9,
            recommendation="No action",
            details={"domain": "test"},
        )

        data = status.to_dict()

        assert data["level"] == "fresh"
        assert data["days_since_update"] == 10
        assert data["score"] == 0.9


class TestFreshnessCheckerDomainVelocities:
    """Unit tests for domain-specific velocities."""

    def test_technology_velocity(self):
        """Test technology domain velocity."""
        checker = FreshnessChecker(domain="technology")
        assert checker.velocity_days == 90

    def test_ai_velocity(self):
        """Test AI domain velocity."""
        checker = FreshnessChecker(domain="ai")
        assert checker.velocity_days == 60

    def test_science_velocity(self):
        """Test science domain velocity."""
        checker = FreshnessChecker(domain="science")
        assert checker.velocity_days == 365

    def test_current_events_velocity(self):
        """Test current_events domain velocity."""
        checker = FreshnessChecker(domain="current_events")
        assert checker.velocity_days == 7

    def test_unknown_domain_defaults_to_general(self):
        """Test unknown domain uses general velocity."""
        checker = FreshnessChecker(domain="unknown_domain")
        assert checker.velocity_days == 365


# =============================================================================
# Property-Based Tests: TemporalState
# =============================================================================


class TestTemporalStateProperties:
    """Property-based tests for TemporalState."""

    @given(days_old=st.integers(min_value=0, max_value=3650))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_days_since_creation_non_negative(self, days_old):
        """Property: Days since creation is always non-negative."""
        state = TemporalState(created_at=utc_now() - timedelta(days=days_old))

        days = state.days_since_creation()

        assert days >= 0

    @given(days_old=st.integers(min_value=0, max_value=3650))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_days_since_activity_non_negative(self, days_old):
        """Property: Days since activity is always non-negative."""
        state = TemporalState(last_activity=utc_now() - timedelta(days=days_old))

        days = state.days_since_last_activity()

        assert days >= 0

    @given(
        activity_types=st.lists(
            st.sampled_from(["chat", "learn", "refresh", "upload", "other"]), min_size=1, max_size=50
        )
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_activity_history_bounded(self, activity_types):
        """Property: Activity history never exceeds 100 entries."""
        state = TemporalState()

        for activity_type in activity_types:
            state.record_activity(activity_type)

        assert len(state.activity_history) <= 100

    @given(activity_types=st.lists(st.sampled_from(["chat", "learn", "refresh", "upload"]), min_size=1, max_size=20))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_activity_updates_last_activity(self, activity_types):
        """Property: Recording activity always updates last_activity."""
        state = TemporalState(last_activity=utc_now() - timedelta(days=100))
        old_activity = state.last_activity

        for activity_type in activity_types:
            state.record_activity(activity_type)

        assert state.last_activity > old_activity

    @given(threshold=st.integers(min_value=1, max_value=365), days_old=st.integers(min_value=0, max_value=500))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_is_active_is_dormant_mutually_exclusive(self, threshold, days_old):
        """Property: is_active and is_dormant are mutually exclusive at same threshold."""
        state = TemporalState(last_activity=utc_now() - timedelta(days=days_old))

        active = state.is_active(threshold_days=threshold)
        dormant = state.is_dormant(threshold_days=threshold)

        # Can't be both active and dormant at same threshold
        assert not (active and dormant)

    @given(days_old=st.integers(min_value=0, max_value=1000))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_age_category_always_valid(self, days_old):
        """Property: Age category is always one of the valid values."""
        state = TemporalState(created_at=utc_now() - timedelta(days=days_old))

        category = state.get_age_category()

        assert category in ["new", "young", "established", "mature"]

    @given(days_old=st.integers(min_value=0, max_value=500))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_serialization_roundtrip(self, days_old):
        """Property: Serialization roundtrip preserves data."""
        original = TemporalState(
            created_at=utc_now() - timedelta(days=days_old), last_activity=utc_now() - timedelta(days=days_old // 2)
        )
        original.record_activity("chat")

        data = original.to_dict()
        restored = TemporalState.from_dict(data)

        assert restored.created_at == original.created_at
        assert restored.last_activity == original.last_activity
        assert len(restored.activity_history) == len(original.activity_history)


# =============================================================================
# Property-Based Tests: FreshnessChecker
# =============================================================================


class TestFreshnessCheckerProperties:
    """Property-based tests for FreshnessChecker."""

    @given(velocity_days=st.integers(min_value=1, max_value=365), days_since=st.integers(min_value=0, max_value=1000))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_score_always_bounded(self, velocity_days, days_since):
        """Property: Freshness score is always between 0 and 1."""
        checker = FreshnessChecker(velocity_days=velocity_days)

        status = checker.check(last_learning=utc_now() - timedelta(days=days_since))

        assert 0.0 <= status.score <= 1.0

    @given(velocity_days=st.integers(min_value=1, max_value=365), days_since=st.integers(min_value=0, max_value=1000))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_level_always_valid(self, velocity_days, days_since):
        """Property: Freshness level is always a valid enum value."""
        checker = FreshnessChecker(velocity_days=velocity_days)

        status = checker.check(last_learning=utc_now() - timedelta(days=days_since))

        assert status.level in FreshnessLevel

    @given(
        velocity_days=st.integers(min_value=10, max_value=365),
        days1=st.integers(min_value=0, max_value=500),
        days2=st.integers(min_value=0, max_value=500),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_score_monotonically_decreases(self, velocity_days, days1, days2):
        """Property: Older knowledge has lower or equal score."""
        checker = FreshnessChecker(velocity_days=velocity_days)

        status1 = checker.check(last_learning=utc_now() - timedelta(days=days1))
        status2 = checker.check(last_learning=utc_now() - timedelta(days=days2))

        if days1 <= days2:
            assert status1.score >= status2.score - 0.001  # Small epsilon
        else:
            assert status2.score >= status1.score - 0.001

    @given(velocity_days=st.integers(min_value=10, max_value=365))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_fresh_threshold_correct(self, velocity_days):
        """Property: Knowledge within 50% of velocity is FRESH."""
        checker = FreshnessChecker(velocity_days=velocity_days)

        # Just under 50% threshold
        days = int(velocity_days * 0.4)
        status = checker.check(last_learning=utc_now() - timedelta(days=days))

        assert status.level == FreshnessLevel.FRESH

    @given(velocity_days=st.integers(min_value=20, max_value=365))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_critical_threshold_correct(self, velocity_days):
        """Property: Knowledge beyond 150% of velocity is CRITICAL."""
        checker = FreshnessChecker(velocity_days=velocity_days)

        # Beyond 150% threshold
        days = int(velocity_days * 2.0)
        status = checker.check(last_learning=utc_now() - timedelta(days=days))

        assert status.level == FreshnessLevel.CRITICAL

    @given(velocity_days=st.integers(min_value=10, max_value=365), days_since=st.integers(min_value=0, max_value=500))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_is_stale_consistent_with_level(self, velocity_days, days_since):
        """Property: is_stale is consistent with level."""
        checker = FreshnessChecker(velocity_days=velocity_days)

        status = checker.check(last_learning=utc_now() - timedelta(days=days_since))

        is_stale = status.is_stale()

        if status.level in (FreshnessLevel.STALE, FreshnessLevel.CRITICAL):
            assert is_stale is True
        else:
            assert is_stale is False

    @given(velocity_days=st.integers(min_value=10, max_value=365), days_since=st.integers(min_value=0, max_value=500))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_needs_refresh_consistent_with_level(self, velocity_days, days_since):
        """Property: needs_refresh is consistent with level."""
        checker = FreshnessChecker(velocity_days=velocity_days)

        status = checker.check(last_learning=utc_now() - timedelta(days=days_since))

        needs_refresh = status.needs_refresh()

        if status.level == FreshnessLevel.FRESH:
            assert needs_refresh is False
        else:
            assert needs_refresh is True

    @given(velocity_days=st.integers(min_value=10, max_value=365), days_since=st.integers(min_value=0, max_value=500))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_days_until_stale_formula(self, velocity_days, days_since):
        """Property: days_until_stale follows formula."""
        checker = FreshnessChecker(velocity_days=velocity_days)

        last_learning = utc_now() - timedelta(days=days_since)
        days_until = checker.days_until_stale(last_learning=last_learning)

        expected = velocity_days - days_since
        assert days_until == expected


# =============================================================================
# Property-Based Tests: Score Calculation
# =============================================================================


class TestScoreCalculationProperties:
    """Property-based tests for score calculation."""

    @given(velocity_days=st.integers(min_value=10, max_value=365))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_fresh_knowledge_high_score(self, velocity_days):
        """Property: Fresh knowledge (0 days) has score of 1.0."""
        checker = FreshnessChecker(velocity_days=velocity_days)

        status = checker.check(last_learning=utc_now())

        assert abs(status.score - 1.0) < 0.01

    @given(velocity_days=st.integers(min_value=10, max_value=365))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_score_at_velocity_days(self, velocity_days):
        """Property: Score at velocity_days follows exponential decay."""
        checker = FreshnessChecker(velocity_days=velocity_days)

        status = checker.check(last_learning=utc_now() - timedelta(days=velocity_days))

        # At velocity_days, score should be e^(-1) ~ 0.368
        expected = math.exp(-1)
        assert abs(status.score - expected) < 0.01


# =============================================================================
# Property-Based Tests: Backward Compatibility
# =============================================================================


class TestBackwardCompatibility:
    """Property-based tests for backward compatibility."""

    @given(days_old=st.integers(min_value=0, max_value=365))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_temporal_state_handles_missing_fields(self, days_old):
        """Property: TemporalState handles missing fields in from_dict."""
        # Minimal data (simulating old format)
        data = {
            "created_at": (utc_now() - timedelta(days=days_old)).isoformat(),
            "last_activity": utc_now().isoformat(),
        }

        state = TemporalState.from_dict(data)

        assert state.created_at is not None
        assert state.last_activity is not None
        assert state.last_learning is None
        assert state.last_chat is None
        assert state.activity_history == []

    @given(domain=st.sampled_from(list(FreshnessChecker.DEFAULT_VELOCITIES.keys())))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_freshness_checker_known_domains(self, domain):
        """Property: All known domains have valid velocities."""
        checker = FreshnessChecker(domain=domain)

        assert checker.velocity_days > 0
        assert checker.velocity_days <= 365
