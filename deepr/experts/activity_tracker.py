"""Activity tracking for expert interactions.

This module extracts activity recording logic from ExpertProfile to reduce
god class complexity. Handles conversation and research counting.

Requirements: 5.3 - Extract activity recording logic
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class ActivityTracker:
    """Tracks expert activity and usage statistics.
    
    Records conversations, research triggers, and maintains activity
    history for analytics and freshness calculations.
    
    Attributes:
        conversations: Total conversation count
        research_triggered: Total research operations triggered
        last_activity: Timestamp of last activity
        activity_history: Recent activity log
    """
    
    conversations: int = 0
    research_triggered: int = 0
    last_activity: Optional[datetime] = None
    activity_history: List[Dict] = field(default_factory=list)
    
    # Maximum history entries to retain
    MAX_HISTORY_ENTRIES: int = field(default=50, repr=False)
    
    def record_activity(
        self,
        activity_type: str,
        details: Optional[Dict] = None
    ) -> None:
        """Record an activity event.
        
        Args:
            activity_type: Type of activity (chat, research, learning, etc.)
            details: Optional additional details
        """
        now = datetime.now(timezone.utc)
        self.last_activity = now
        
        # Update counters based on activity type
        if activity_type == "chat":
            self.conversations += 1
        elif activity_type == "research":
            self.research_triggered += 1
        
        # Add to history
        entry = {
            "timestamp": now.isoformat(),
            "type": activity_type,
            "details": details
        }
        self.activity_history.append(entry)
        
        # Trim history if needed
        if len(self.activity_history) > self.MAX_HISTORY_ENTRIES:
            self.activity_history = self.activity_history[-self.MAX_HISTORY_ENTRIES:]
    
    def get_stats(self) -> Dict[str, any]:
        """Get activity statistics.
        
        Returns:
            Dictionary with activity statistics
        """
        return {
            "conversations": self.conversations,
            "research_triggered": self.research_triggered,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "total_activities": len(self.activity_history),
            "recent_activity_types": self._get_recent_activity_types()
        }
    
    def _get_recent_activity_types(self, limit: int = 10) -> List[str]:
        """Get types of recent activities.
        
        Args:
            limit: Maximum number of recent activities to include
            
        Returns:
            List of recent activity types
        """
        recent = self.activity_history[-limit:] if self.activity_history else []
        return [entry.get("type", "unknown") for entry in recent]
    
    def get_activity_count_since(self, since: datetime) -> int:
        """Count activities since a given timestamp.
        
        Args:
            since: Start timestamp
            
        Returns:
            Number of activities since timestamp
        """
        count = 0
        for entry in self.activity_history:
            timestamp_str = entry.get("timestamp")
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    if timestamp >= since:
                        count += 1
                except (ValueError, TypeError):
                    continue
        return count
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization.
        
        Returns:
            Dictionary representation
        """
        return {
            "conversations": self.conversations,
            "research_triggered": self.research_triggered,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "activity_history": self.activity_history
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ActivityTracker':
        """Create from dictionary.
        
        Args:
            data: Dictionary with activity data
            
        Returns:
            ActivityTracker instance
        """
        last_activity = None
        if data.get("last_activity"):
            last_activity = datetime.fromisoformat(data["last_activity"])
        
        return cls(
            conversations=data.get("conversations", 0),
            research_triggered=data.get("research_triggered", 0),
            last_activity=last_activity,
            activity_history=data.get("activity_history", [])
        )
