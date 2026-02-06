"""User profile tracking for personalized expert interactions.

Tracks user expertise level, interests, context, and learning patterns to enable
experts to remember users and adapt responses.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class UserInteraction:
    """Record of a single user interaction."""

    timestamp: datetime
    question: str
    topic: str
    expert_name: str
    research_triggered: bool
    cost: float


@dataclass
class UserProfile:
    """Profile of a user interacting with experts."""

    user_id: str
    first_seen: datetime
    last_seen: datetime
    total_interactions: int = 0

    # Interests and expertise
    topics_asked_about: Dict[str, int] = field(default_factory=dict)  # topic -> count
    expertise_signals: Dict[str, str] = field(default_factory=dict)  # topic -> level (beginner/intermediate/expert)

    # Context
    tech_stack: List[str] = field(default_factory=list)
    current_projects: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)

    # Learning patterns
    preferred_detail_level: str = "balanced"  # concise, balanced, comprehensive
    prefers_examples: bool = True
    prefers_comparisons: bool = False

    # Interaction history
    recent_interactions: List[UserInteraction] = field(default_factory=list)
    total_cost: float = 0.0

    # Metadata
    notes: str = ""


class UserProfileTracker:
    """Manages user profiles for personalized expert interactions."""

    def __init__(self, base_path: str = "data/users"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.current_user_id: Optional[str] = None
        self.current_profile: Optional[UserProfile] = None

    def _get_profile_path(self, user_id: str) -> Path:
        """Get path to user profile file."""
        return self.base_path / f"{user_id}.json"

    def _serialize_interaction(self, interaction: UserInteraction) -> Dict:
        """Serialize interaction to dict."""
        return {
            "timestamp": interaction.timestamp.isoformat(),
            "question": interaction.question,
            "topic": interaction.topic,
            "expert_name": interaction.expert_name,
            "research_triggered": interaction.research_triggered,
            "cost": interaction.cost,
        }

    def _deserialize_interaction(self, data: Dict) -> UserInteraction:
        """Deserialize interaction from dict."""
        return UserInteraction(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            question=data["question"],
            topic=data["topic"],
            expert_name=data["expert_name"],
            research_triggered=data["research_triggered"],
            cost=data["cost"],
        )

    def load_or_create(self, user_id: str) -> UserProfile:
        """Load existing profile or create new one.

        Args:
            user_id: User identifier (email, username, or system-generated ID)

        Returns:
            UserProfile object
        """
        self.current_user_id = user_id
        profile_path = self._get_profile_path(user_id)

        if profile_path.exists():
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                profile = UserProfile(
                    user_id=data["user_id"],
                    first_seen=datetime.fromisoformat(data["first_seen"]),
                    last_seen=datetime.fromisoformat(data["last_seen"]),
                    total_interactions=data["total_interactions"],
                    topics_asked_about=data["topics_asked_about"],
                    expertise_signals=data["expertise_signals"],
                    tech_stack=data.get("tech_stack", []),
                    current_projects=data.get("current_projects", []),
                    goals=data.get("goals", []),
                    preferred_detail_level=data.get("preferred_detail_level", "balanced"),
                    prefers_examples=data.get("prefers_examples", True),
                    prefers_comparisons=data.get("prefers_comparisons", False),
                    recent_interactions=[self._deserialize_interaction(i) for i in data.get("recent_interactions", [])],
                    total_cost=data.get("total_cost", 0.0),
                    notes=data.get("notes", ""),
                )

                self.current_profile = profile
                return profile

            except Exception as e:
                logger.error("Error loading user profile: %s", e)

        # Create new profile
        now = datetime.now(timezone.utc)
        profile = UserProfile(user_id=user_id, first_seen=now, last_seen=now)

        self.current_profile = profile
        return profile

    def save(self, profile: Optional[UserProfile] = None):
        """Save user profile to disk.

        Args:
            profile: Profile to save (uses current_profile if not specified)
        """
        profile = profile or self.current_profile
        if not profile:
            return

        try:
            profile_path = self._get_profile_path(profile.user_id)

            data = {
                "user_id": profile.user_id,
                "first_seen": profile.first_seen.isoformat(),
                "last_seen": profile.last_seen.isoformat(),
                "total_interactions": profile.total_interactions,
                "topics_asked_about": profile.topics_asked_about,
                "expertise_signals": profile.expertise_signals,
                "tech_stack": profile.tech_stack,
                "current_projects": profile.current_projects,
                "goals": profile.goals,
                "preferred_detail_level": profile.preferred_detail_level,
                "prefers_examples": profile.prefers_examples,
                "prefers_comparisons": profile.prefers_comparisons,
                "recent_interactions": [
                    self._serialize_interaction(i)
                    for i in profile.recent_interactions[-100:]  # Keep last 100
                ],
                "total_cost": profile.total_cost,
                "notes": profile.notes,
            }

            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error("Error saving user profile: %s", e)

    def record_interaction(self, question: str, topic: str, expert_name: str, research_triggered: bool, cost: float):
        """Record a user interaction.

        Args:
            question: The user's question
            topic: Main topic of the question
            expert_name: Name of the expert consulted
            research_triggered: Whether research was triggered
            cost: Cost of the interaction
        """
        if not self.current_profile:
            return

        now = datetime.now(timezone.utc)
        profile = self.current_profile

        # Update profile
        profile.last_seen = now
        profile.total_interactions += 1
        profile.total_cost += cost

        # Track topic interest
        if topic:
            profile.topics_asked_about[topic] = profile.topics_asked_about.get(topic, 0) + 1

        # Record interaction
        interaction = UserInteraction(
            timestamp=now,
            question=question,
            topic=topic,
            expert_name=expert_name,
            research_triggered=research_triggered,
            cost=cost,
        )
        profile.recent_interactions.append(interaction)

        # Keep only last 100 interactions in memory
        if len(profile.recent_interactions) > 100:
            profile.recent_interactions = profile.recent_interactions[-100:]

        self.save()

    def detect_expertise_level(self, topic: str) -> str:
        """Detect user's expertise level in a topic based on question patterns.

        Args:
            topic: The topic to assess

        Returns:
            Expertise level: "beginner", "intermediate", or "expert"
        """
        if not self.current_profile:
            return "intermediate"

        # Simple heuristic: frequency and depth of questions
        times_asked = self.current_profile.topics_asked_about.get(topic, 0)

        if times_asked == 0:
            return "beginner"
        elif times_asked < 5:
            return "intermediate"
        else:
            return "expert"

    def get_context_summary(self) -> str:
        """Get a summary of user context for expert to use.

        Returns:
            String summary of user context
        """
        if not self.current_profile:
            return "New user, no previous context."

        profile = self.current_profile

        parts = []

        # Interaction history
        if profile.total_interactions > 0:
            parts.append(f"User has had {profile.total_interactions} previous interactions.")

        # Top interests
        if profile.topics_asked_about:
            top_topics = sorted(profile.topics_asked_about.items(), key=lambda x: x[1], reverse=True)[:3]
            topics_str = ", ".join([f"{topic} ({count}x)" for topic, count in top_topics])
            parts.append(f"Primary interests: {topics_str}")

        # Tech stack
        if profile.tech_stack:
            parts.append(f"Tech stack: {', '.join(profile.tech_stack)}")

        # Current projects
        if profile.current_projects:
            parts.append(f"Current projects: {', '.join(profile.current_projects)}")

        # Goals
        if profile.goals:
            parts.append(f"Goals: {', '.join(profile.goals)}")

        # Learning preferences
        parts.append(f"Prefers {profile.preferred_detail_level} detail level")
        if profile.prefers_examples:
            parts.append("Appreciates examples")

        # Recent activity
        if profile.recent_interactions:
            last_interaction = profile.recent_interactions[-1]
            days_ago = (datetime.now(timezone.utc) - last_interaction.timestamp).days
            if days_ago == 0:
                parts.append("Active today")
            elif days_ago == 1:
                parts.append("Last active yesterday")
            else:
                parts.append(f"Last active {days_ago} days ago")

        return " | ".join(parts) if parts else "New user."

    def update_context(
        self,
        tech_stack: Optional[List[str]] = None,
        projects: Optional[List[str]] = None,
        goals: Optional[List[str]] = None,
    ):
        """Update user context information.

        Args:
            tech_stack: User's technology stack
            projects: Current projects
            goals: User's goals
        """
        if not self.current_profile:
            return

        if tech_stack is not None:
            self.current_profile.tech_stack = tech_stack
        if projects is not None:
            self.current_profile.current_projects = projects
        if goals is not None:
            self.current_profile.goals = goals

        self.save()

    def get_top_interests(self, limit: int = 5) -> List[tuple]:
        """Get user's top interests by frequency.

        Args:
            limit: Maximum number of interests to return

        Returns:
            List of (topic, count) tuples
        """
        if not self.current_profile:
            return []

        return sorted(self.current_profile.topics_asked_about.items(), key=lambda x: x[1], reverse=True)[:limit]
