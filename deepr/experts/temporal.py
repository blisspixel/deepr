"""Temporal state management for experts.

Extracts temporal logic from ExpertProfile for better separation of concerns.

Usage:
    from deepr.experts.temporal import TemporalState

    state = TemporalState()
    state.record_activity("chat")
    print(state.days_since_last_activity())
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


@dataclass
class TemporalState:
    """Manages temporal state for an expert.

    Tracks creation time, last activity, and activity history.

    Attributes:
        created_at: When expert was created
        last_activity: Last activity timestamp
        last_learning: Last learning activity
        last_chat: Last chat interaction
        activity_history: Recent activity log
    """

    created_at: datetime = field(default_factory=_utc_now)
    last_activity: datetime = field(default_factory=_utc_now)
    last_learning: Optional[datetime] = None
    last_chat: Optional[datetime] = None
    activity_history: List[Dict[str, Any]] = field(default_factory=list)

    def record_activity(self, activity_type: str, details: Optional[Dict[str, Any]] = None):
        """Record an activity.

        Args:
            activity_type: Type of activity (chat, learn, refresh, etc.)
            details: Optional activity details
        """
        now = _utc_now()
        self.last_activity = now

        if activity_type == "chat":
            self.last_chat = now
        elif activity_type in ("learn", "refresh", "upload"):
            self.last_learning = now

        entry = {"type": activity_type, "timestamp": now.isoformat(), "details": details or {}}

        self.activity_history.append(entry)

        # Keep last 100 activities
        if len(self.activity_history) > 100:
            self.activity_history = self.activity_history[-100:]

    def days_since_creation(self) -> int:
        """Get days since expert was created.

        Returns:
            Number of days
        """
        return (_utc_now() - self.created_at).days

    def days_since_last_activity(self) -> int:
        """Get days since last activity.

        Returns:
            Number of days
        """
        return (_utc_now() - self.last_activity).days

    def days_since_last_learning(self) -> Optional[int]:
        """Get days since last learning activity.

        Returns:
            Number of days or None if never learned
        """
        if self.last_learning is None:
            return None
        return (_utc_now() - self.last_learning).days

    def days_since_last_chat(self) -> Optional[int]:
        """Get days since last chat.

        Returns:
            Number of days or None if never chatted
        """
        if self.last_chat is None:
            return None
        return (_utc_now() - self.last_chat).days

    def get_activity_count(self, activity_type: str, days: int = 30) -> int:
        """Get activity count in recent period.

        Args:
            activity_type: Type of activity to count
            days: Number of days to look back

        Returns:
            Count of activities
        """
        cutoff = _utc_now() - timedelta(days=days)
        count = 0

        for entry in self.activity_history:
            if entry["type"] != activity_type:
                continue

            timestamp = datetime.fromisoformat(entry["timestamp"])
            if timestamp >= cutoff:
                count += 1

        return count

    def get_recent_activities(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent activities.

        Args:
            limit: Maximum activities to return

        Returns:
            List of recent activities
        """
        return self.activity_history[-limit:]

    def is_active(self, threshold_days: int = 30) -> bool:
        """Check if expert is actively used.

        Args:
            threshold_days: Days threshold for activity

        Returns:
            True if active within threshold
        """
        return self.days_since_last_activity() <= threshold_days

    def is_dormant(self, threshold_days: int = 90) -> bool:
        """Check if expert is dormant.

        Args:
            threshold_days: Days threshold for dormancy

        Returns:
            True if no activity beyond threshold
        """
        return self.days_since_last_activity() > threshold_days

    def get_age_category(self) -> str:
        """Get expert age category.

        Returns:
            Age category string
        """
        days = self.days_since_creation()

        if days < 7:
            return "new"
        elif days < 30:
            return "young"
        elif days < 180:
            return "established"
        else:
            return "mature"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "last_learning": self.last_learning.isoformat() if self.last_learning else None,
            "last_chat": self.last_chat.isoformat() if self.last_chat else None,
            "activity_history": self.activity_history,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TemporalState":
        """Deserialize from dictionary.

        Args:
            data: Dictionary data

        Returns:
            TemporalState instance
        """
        return cls(
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else _utc_now(),
            last_activity=datetime.fromisoformat(data["last_activity"]) if "last_activity" in data else _utc_now(),
            last_learning=datetime.fromisoformat(data["last_learning"]) if data.get("last_learning") else None,
            last_chat=datetime.fromisoformat(data["last_chat"]) if data.get("last_chat") else None,
            activity_history=data.get("activity_history", []),
        )
