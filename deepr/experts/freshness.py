"""Freshness checking for expert knowledge.

Extracts freshness logic from ExpertProfile for better separation of concerns.

Usage:
    from deepr.experts.freshness import FreshnessChecker, FreshnessStatus

    checker = FreshnessChecker(domain="technology", velocity_days=90)
    status = checker.check(last_learning=datetime(2024, 1, 1))
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class FreshnessLevel(Enum):
    """Freshness level categories."""

    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    CRITICAL = "critical"


@dataclass
class FreshnessStatus:
    """Status of knowledge freshness.

    Attributes:
        level: Freshness level
        days_since_update: Days since last knowledge update
        threshold_days: Domain-specific threshold
        score: Freshness score 0-1
        recommendation: Recommended action
        details: Additional details
    """

    level: FreshnessLevel
    days_since_update: int
    threshold_days: int
    score: float
    recommendation: str
    details: dict[str, Any]

    def is_stale(self) -> bool:
        """Check if knowledge is stale.

        Returns:
            True if stale or critical
        """
        return self.level in (FreshnessLevel.STALE, FreshnessLevel.CRITICAL)

    def needs_refresh(self) -> bool:
        """Check if refresh is recommended.

        Returns:
            True if aging, stale, or critical
        """
        return self.level != FreshnessLevel.FRESH

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "days_since_update": self.days_since_update,
            "threshold_days": self.threshold_days,
            "score": self.score,
            "recommendation": self.recommendation,
            "details": self.details,
        }


class FreshnessChecker:
    """Checks freshness of expert knowledge.

    Attributes:
        domain: Knowledge domain
        velocity_days: Domain velocity (days until stale)
        custom_thresholds: Custom freshness thresholds
    """

    # Default domain velocities
    DEFAULT_VELOCITIES = {
        "technology": 90,
        "ai": 60,
        "machine_learning": 90,
        "programming": 180,
        "science": 365,
        "business": 180,
        "finance": 90,
        "regulations": 180,
        "current_events": 7,
        "general": 365,
    }

    def __init__(
        self,
        domain: str = "general",
        velocity_days: Optional[int] = None,
        custom_thresholds: Optional[dict[str, int]] = None,
    ):
        """Initialize freshness checker.

        Args:
            domain: Knowledge domain
            velocity_days: Override domain velocity
            custom_thresholds: Custom threshold overrides
        """
        self.domain = domain
        self.velocity_days = velocity_days or self.DEFAULT_VELOCITIES.get(domain, 365)
        self.custom_thresholds = custom_thresholds or {}

    def check(
        self,
        last_learning: Optional[datetime] = None,
        last_activity: Optional[datetime] = None,
        knowledge_sources: Optional[list[dict[str, Any]]] = None,
    ) -> FreshnessStatus:
        """Check knowledge freshness.

        Args:
            last_learning: Last learning activity timestamp
            last_activity: Last activity timestamp
            knowledge_sources: List of knowledge sources with dates

        Returns:
            FreshnessStatus with assessment
        """
        now = datetime.now(timezone.utc)

        # Determine reference date
        if last_learning:
            reference_date = last_learning
        elif last_activity:
            reference_date = last_activity
        else:
            # No activity - assume very stale
            return FreshnessStatus(
                level=FreshnessLevel.CRITICAL,
                days_since_update=999,
                threshold_days=self.velocity_days,
                score=0.0,
                recommendation="Expert has no learning history. Upload documents to build knowledge.",
                details={"reason": "no_learning_history"},
            )

        days_since = (now - reference_date).days

        # Calculate freshness score
        score = self._calculate_score(days_since)

        # Determine level
        level = self._determine_level(days_since)

        # Generate recommendation
        recommendation = self._generate_recommendation(level, days_since)

        # Build details
        details = {
            "domain": self.domain,
            "velocity_days": self.velocity_days,
            "last_update": reference_date.isoformat(),
            "source_freshness": self._analyze_sources(knowledge_sources) if knowledge_sources else None,
        }

        return FreshnessStatus(
            level=level,
            days_since_update=days_since,
            threshold_days=self.velocity_days,
            score=score,
            recommendation=recommendation,
            details=details,
        )

    def get_status(self, last_learning: Optional[datetime] = None) -> dict[str, Any]:
        """Get simple status dictionary.

        Args:
            last_learning: Last learning timestamp

        Returns:
            Status dictionary
        """
        status = self.check(last_learning=last_learning)
        return status.to_dict()

    def is_stale(self, last_learning: Optional[datetime] = None) -> bool:
        """Quick check if knowledge is stale.

        Args:
            last_learning: Last learning timestamp

        Returns:
            True if stale
        """
        return self.check(last_learning=last_learning).is_stale()

    def days_until_stale(self, last_learning: Optional[datetime] = None) -> int:
        """Calculate days until knowledge becomes stale.

        Args:
            last_learning: Last learning timestamp

        Returns:
            Days until stale (negative if already stale)
        """
        if last_learning is None:
            return -999

        days_since = (datetime.now(timezone.utc) - last_learning).days
        return self.velocity_days - days_since

    def _calculate_score(self, days_since: int) -> float:
        """Calculate freshness score.

        Args:
            days_since: Days since last update

        Returns:
            Score between 0 and 1
        """
        if days_since <= 0:
            return 1.0

        # Exponential decay based on domain velocity
        import math

        decay_rate = 1.0 / self.velocity_days
        score = math.exp(-decay_rate * days_since)

        return max(0.0, min(1.0, score))

    def _determine_level(self, days_since: int) -> FreshnessLevel:
        """Determine freshness level.

        Args:
            days_since: Days since last update

        Returns:
            FreshnessLevel
        """
        # Thresholds as fractions of velocity
        fresh_threshold = self.velocity_days * 0.5
        aging_threshold = self.velocity_days * 0.8
        critical_threshold = self.velocity_days * 1.5

        if days_since <= fresh_threshold:
            return FreshnessLevel.FRESH
        elif days_since <= aging_threshold:
            return FreshnessLevel.AGING
        elif days_since <= critical_threshold:
            return FreshnessLevel.STALE
        else:
            return FreshnessLevel.CRITICAL

    def _generate_recommendation(self, level: FreshnessLevel, days_since: int) -> str:
        """Generate recommendation based on level.

        Args:
            level: Freshness level
            days_since: Days since update

        Returns:
            Recommendation string
        """
        if level == FreshnessLevel.FRESH:
            return "Knowledge is up to date. No action needed."

        if level == FreshnessLevel.AGING:
            return f"Knowledge is {days_since} days old. Consider refreshing soon."

        if level == FreshnessLevel.STALE:
            return f"Knowledge is stale ({days_since} days). Recommend refreshing with recent sources."

        return f"Knowledge is critically outdated ({days_since} days). Urgent refresh recommended."

    def _analyze_sources(self, sources: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze freshness of knowledge sources.

        Args:
            sources: List of source metadata

        Returns:
            Analysis results
        """
        if not sources:
            return {"count": 0}

        now = datetime.now(timezone.utc)
        ages = []

        for source in sources:
            if "date" in source:
                try:
                    source_date = datetime.fromisoformat(source["date"])
                    ages.append((now - source_date).days)
                except (ValueError, TypeError):
                    pass

        if not ages:
            return {"count": len(sources), "dated_count": 0}

        return {
            "count": len(sources),
            "dated_count": len(ages),
            "avg_age_days": sum(ages) / len(ages),
            "oldest_days": max(ages),
            "newest_days": min(ages),
        }

    @classmethod
    def for_domain(cls, domain: str) -> "FreshnessChecker":
        """Create checker for a specific domain.

        Args:
            domain: Domain name

        Returns:
            FreshnessChecker configured for domain
        """
        return cls(domain=domain)
