"""Tests for freshness checking module.

Requirements: 1.3 - Test Coverage
"""

from datetime import datetime, timedelta, timezone

import pytest

from deepr.experts.freshness import (
    FreshnessChecker,
    FreshnessLevel,
    FreshnessStatus,
)


class TestFreshnessLevel:
    """Tests for FreshnessLevel enum."""

    def test_all_levels_exist(self):
        """Should have all expected levels."""
        assert FreshnessLevel.FRESH
        assert FreshnessLevel.AGING
        assert FreshnessLevel.STALE
        assert FreshnessLevel.CRITICAL

    def test_level_values(self):
        """Should have correct string values."""
        assert FreshnessLevel.FRESH.value == "fresh"
        assert FreshnessLevel.AGING.value == "aging"
        assert FreshnessLevel.STALE.value == "stale"
        assert FreshnessLevel.CRITICAL.value == "critical"


class TestFreshnessStatus:
    """Tests for FreshnessStatus dataclass."""

    def test_create_status(self):
        """Should create status with required fields."""
        status = FreshnessStatus(
            level=FreshnessLevel.FRESH,
            days_since_update=10,
            threshold_days=90,
            score=0.9,
            recommendation="No action needed",
            details={},
        )

        assert status.level == FreshnessLevel.FRESH
        assert status.days_since_update == 10
        assert status.threshold_days == 90
        assert status.score == 0.9

    def test_is_stale_fresh(self):
        """Fresh should not be stale."""
        status = FreshnessStatus(
            level=FreshnessLevel.FRESH,
            days_since_update=10,
            threshold_days=90,
            score=0.9,
            recommendation="",
            details={},
        )
        assert status.is_stale() is False

    def test_is_stale_aging(self):
        """Aging should not be stale."""
        status = FreshnessStatus(
            level=FreshnessLevel.AGING,
            days_since_update=60,
            threshold_days=90,
            score=0.5,
            recommendation="",
            details={},
        )
        assert status.is_stale() is False

    def test_is_stale_stale(self):
        """Stale should be stale."""
        status = FreshnessStatus(
            level=FreshnessLevel.STALE,
            days_since_update=100,
            threshold_days=90,
            score=0.3,
            recommendation="",
            details={},
        )
        assert status.is_stale() is True

    def test_is_stale_critical(self):
        """Critical should be stale."""
        status = FreshnessStatus(
            level=FreshnessLevel.CRITICAL,
            days_since_update=200,
            threshold_days=90,
            score=0.1,
            recommendation="",
            details={},
        )
        assert status.is_stale() is True

    def test_needs_refresh_fresh(self):
        """Fresh should not need refresh."""
        status = FreshnessStatus(
            level=FreshnessLevel.FRESH,
            days_since_update=10,
            threshold_days=90,
            score=0.9,
            recommendation="",
            details={},
        )
        assert status.needs_refresh() is False

    def test_needs_refresh_aging(self):
        """Aging should need refresh."""
        status = FreshnessStatus(
            level=FreshnessLevel.AGING,
            days_since_update=60,
            threshold_days=90,
            score=0.5,
            recommendation="",
            details={},
        )
        assert status.needs_refresh() is True

    def test_to_dict(self):
        """Should convert to dictionary."""
        status = FreshnessStatus(
            level=FreshnessLevel.FRESH,
            days_since_update=10,
            threshold_days=90,
            score=0.9,
            recommendation="Test recommendation",
            details={"key": "value"},
        )

        result = status.to_dict()

        assert result["level"] == "fresh"
        assert result["days_since_update"] == 10
        assert result["threshold_days"] == 90
        assert result["score"] == 0.9
        assert result["recommendation"] == "Test recommendation"
        assert result["details"] == {"key": "value"}


class TestFreshnessCheckerInit:
    """Tests for FreshnessChecker initialization."""

    def test_default_init(self):
        """Should initialize with defaults."""
        checker = FreshnessChecker()

        assert checker.domain == "general"
        assert checker.velocity_days == 365

    def test_init_with_domain(self):
        """Should use domain velocity."""
        checker = FreshnessChecker(domain="technology")

        assert checker.domain == "technology"
        assert checker.velocity_days == 90

    def test_init_with_ai_domain(self):
        """Should use AI domain velocity."""
        checker = FreshnessChecker(domain="ai")

        assert checker.velocity_days == 60

    def test_init_with_custom_velocity(self):
        """Should use custom velocity override."""
        checker = FreshnessChecker(domain="technology", velocity_days=30)

        assert checker.velocity_days == 30

    def test_default_velocities(self):
        """Should have all expected domain velocities."""
        assert "technology" in FreshnessChecker.DEFAULT_VELOCITIES
        assert "ai" in FreshnessChecker.DEFAULT_VELOCITIES
        assert "current_events" in FreshnessChecker.DEFAULT_VELOCITIES


class TestFreshnessCheckerCheck:
    """Tests for FreshnessChecker.check method."""

    @pytest.fixture
    def checker(self):
        """Create checker with 90-day velocity."""
        return FreshnessChecker(domain="technology", velocity_days=90)

    def test_check_fresh(self, checker):
        """Should return fresh for recent learning."""
        now = datetime.now(timezone.utc)
        last_learning = now - timedelta(days=10)

        status = checker.check(last_learning=last_learning)

        assert status.level == FreshnessLevel.FRESH
        assert status.days_since_update <= 11

    def test_check_aging(self, checker):
        """Should return aging for moderately old learning."""
        now = datetime.now(timezone.utc)
        last_learning = now - timedelta(days=60)

        status = checker.check(last_learning=last_learning)

        assert status.level == FreshnessLevel.AGING

    def test_check_stale(self, checker):
        """Should return stale for old learning."""
        now = datetime.now(timezone.utc)
        last_learning = now - timedelta(days=100)

        status = checker.check(last_learning=last_learning)

        assert status.level == FreshnessLevel.STALE

    def test_check_critical(self, checker):
        """Should return critical for very old learning."""
        now = datetime.now(timezone.utc)
        last_learning = now - timedelta(days=200)

        status = checker.check(last_learning=last_learning)

        assert status.level == FreshnessLevel.CRITICAL

    def test_check_no_learning_history(self, checker):
        """Should return critical when no learning history."""
        status = checker.check(last_learning=None)

        assert status.level == FreshnessLevel.CRITICAL
        assert status.days_since_update == 999
        assert "no learning history" in status.recommendation.lower()

    def test_check_uses_activity_fallback(self, checker):
        """Should use activity as fallback."""
        now = datetime.now(timezone.utc)
        last_activity = now - timedelta(days=30)

        status = checker.check(last_learning=None, last_activity=last_activity)

        assert status.days_since_update <= 31

    def test_check_includes_details(self, checker):
        """Should include details in status."""
        now = datetime.now(timezone.utc)
        last_learning = now - timedelta(days=10)

        status = checker.check(last_learning=last_learning)

        assert "domain" in status.details
        assert "velocity_days" in status.details
        assert status.details["domain"] == "technology"

    def test_check_with_knowledge_sources(self, checker):
        """Should analyze knowledge sources."""
        now = datetime.now(timezone.utc)
        last_learning = now - timedelta(days=10)
        sources = [
            {"date": (now - timedelta(days=5)).isoformat()},
            {"date": (now - timedelta(days=15)).isoformat()},
        ]

        status = checker.check(last_learning=last_learning, knowledge_sources=sources)

        assert status.details["source_freshness"] is not None
        assert status.details["source_freshness"]["count"] == 2


class TestFreshnessCheckerMethods:
    """Tests for FreshnessChecker helper methods."""

    @pytest.fixture
    def checker(self):
        """Create checker with 90-day velocity."""
        return FreshnessChecker(domain="technology", velocity_days=90)

    def test_is_stale_true(self, checker):
        """Should return True when stale."""
        now = datetime.now(timezone.utc)
        last_learning = now - timedelta(days=100)

        assert checker.is_stale(last_learning=last_learning) is True

    def test_is_stale_false(self, checker):
        """Should return False when fresh."""
        now = datetime.now(timezone.utc)
        last_learning = now - timedelta(days=10)

        assert checker.is_stale(last_learning=last_learning) is False

    def test_days_until_stale_positive(self, checker):
        """Should return positive days until stale."""
        now = datetime.now(timezone.utc)
        last_learning = now - timedelta(days=30)

        days = checker.days_until_stale(last_learning=last_learning)

        assert days > 0
        assert days == 60  # 90 - 30

    def test_days_until_stale_negative(self, checker):
        """Should return negative when already stale."""
        now = datetime.now(timezone.utc)
        last_learning = now - timedelta(days=100)

        days = checker.days_until_stale(last_learning=last_learning)

        assert days < 0

    def test_days_until_stale_no_learning(self, checker):
        """Should return -999 when no learning."""
        days = checker.days_until_stale(last_learning=None)

        assert days == -999

    def test_get_status(self, checker):
        """Should return status dictionary."""
        now = datetime.now(timezone.utc)
        last_learning = now - timedelta(days=10)

        status = checker.get_status(last_learning=last_learning)

        assert isinstance(status, dict)
        assert "level" in status
        assert "score" in status


class TestFreshnessCheckerScoreCalculation:
    """Tests for score calculation."""

    def test_score_fresh_knowledge(self):
        """Fresh knowledge should have high score."""
        checker = FreshnessChecker(velocity_days=90)
        score = checker._calculate_score(0)

        assert score == 1.0

    def test_score_at_velocity(self):
        """Score at velocity days should be ~0.37."""
        checker = FreshnessChecker(velocity_days=90)
        score = checker._calculate_score(90)

        # e^-1 ≈ 0.368
        assert 0.35 <= score <= 0.4

    def test_score_old_knowledge(self):
        """Very old knowledge should have low score."""
        checker = FreshnessChecker(velocity_days=90)
        score = checker._calculate_score(300)

        assert score < 0.1

    def test_score_bounded(self):
        """Score should be between 0 and 1."""
        checker = FreshnessChecker(velocity_days=90)

        for days in [0, 30, 90, 180, 365, 1000]:
            score = checker._calculate_score(days)
            assert 0.0 <= score <= 1.0


class TestFreshnessCheckerLevelDetermination:
    """Tests for level determination."""

    def test_fresh_threshold(self):
        """Should be fresh within 50% of velocity."""
        checker = FreshnessChecker(velocity_days=100)

        assert checker._determine_level(0) == FreshnessLevel.FRESH
        assert checker._determine_level(45) == FreshnessLevel.FRESH
        assert checker._determine_level(50) == FreshnessLevel.FRESH

    def test_aging_threshold(self):
        """Should be aging between 50-80% of velocity."""
        checker = FreshnessChecker(velocity_days=100)

        assert checker._determine_level(55) == FreshnessLevel.AGING
        assert checker._determine_level(75) == FreshnessLevel.AGING
        assert checker._determine_level(80) == FreshnessLevel.AGING

    def test_stale_threshold(self):
        """Should be stale between 100-150% of velocity."""
        checker = FreshnessChecker(velocity_days=100)

        assert checker._determine_level(100) == FreshnessLevel.STALE
        assert checker._determine_level(125) == FreshnessLevel.STALE
        assert checker._determine_level(150) == FreshnessLevel.STALE

    def test_critical_threshold(self):
        """Should be critical above 150% of velocity."""
        checker = FreshnessChecker(velocity_days=100)

        assert checker._determine_level(155) == FreshnessLevel.CRITICAL
        assert checker._determine_level(200) == FreshnessLevel.CRITICAL


class TestFreshnessCheckerRecommendations:
    """Tests for recommendation generation."""

    def test_fresh_recommendation(self):
        """Fresh should have no action needed."""
        checker = FreshnessChecker()
        rec = checker._generate_recommendation(FreshnessLevel.FRESH, 10)

        assert "no action" in rec.lower()

    def test_aging_recommendation(self):
        """Aging should suggest refresh soon."""
        checker = FreshnessChecker()
        rec = checker._generate_recommendation(FreshnessLevel.AGING, 60)

        assert "60" in rec
        assert "soon" in rec.lower()

    def test_stale_recommendation(self):
        """Stale should recommend refreshing."""
        checker = FreshnessChecker()
        rec = checker._generate_recommendation(FreshnessLevel.STALE, 100)

        assert "stale" in rec.lower()
        assert "100" in rec

    def test_critical_recommendation(self):
        """Critical should urgently recommend refresh."""
        checker = FreshnessChecker()
        rec = checker._generate_recommendation(FreshnessLevel.CRITICAL, 200)

        assert "urgent" in rec.lower()
        assert "200" in rec


class TestFreshnessCheckerSourceAnalysis:
    """Tests for source analysis."""

    def test_analyze_empty_sources(self):
        """Should handle empty sources."""
        checker = FreshnessChecker()
        result = checker._analyze_sources([])

        assert result == {"count": 0}

    def test_analyze_sources_without_dates(self):
        """Should handle sources without dates."""
        checker = FreshnessChecker()
        result = checker._analyze_sources([{"title": "Source 1"}, {"title": "Source 2"}])

        assert result["count"] == 2
        assert result["dated_count"] == 0

    def test_analyze_sources_with_dates(self):
        """Should calculate age statistics."""
        checker = FreshnessChecker()
        now = datetime.now(timezone.utc)

        sources = [
            {"date": (now - timedelta(days=10)).isoformat()},
            {"date": (now - timedelta(days=30)).isoformat()},
            {"date": (now - timedelta(days=50)).isoformat()},
        ]

        result = checker._analyze_sources(sources)

        assert result["count"] == 3
        assert result["dated_count"] == 3
        assert "avg_age_days" in result
        assert "oldest_days" in result
        assert "newest_days" in result


class TestFreshnessCheckerFactory:
    """Tests for factory method."""

    def test_for_domain(self):
        """Should create checker for domain."""
        checker = FreshnessChecker.for_domain("ai")

        assert checker.domain == "ai"
        assert checker.velocity_days == 60

    def test_for_unknown_domain(self):
        """Should use default for unknown domain."""
        checker = FreshnessChecker.for_domain("unknown_domain")

        assert checker.domain == "unknown_domain"
        assert checker.velocity_days == 365
