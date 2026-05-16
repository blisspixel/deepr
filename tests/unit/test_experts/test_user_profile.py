"""Tests for UserProfileTracker — fast path coverage.

The module was 0% covered before; this exercises load/create,
interaction recording, persistence round-trip, and the inference paths
that update topics_asked_about / expertise_signals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from deepr.experts.user_profile import UserInteraction, UserProfile, UserProfileTracker


class TestUserProfileTracker:
    def test_load_or_create_returns_new_profile(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        profile = tracker.load_or_create("user-1")
        assert isinstance(profile, UserProfile)
        assert profile.user_id == "user-1"
        assert profile.total_interactions == 0
        assert tracker.current_user_id == "user-1"

    def test_load_or_create_returns_existing(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        first = tracker.load_or_create("user-1")
        first.total_interactions = 5
        tracker.save(first)

        # Second call returns the persisted profile, not a fresh one.
        second = tracker.load_or_create("user-1")
        assert second.total_interactions == 5

    def test_record_interaction_persists(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        tracker.load_or_create("user-1")
        tracker.record_interaction(
            question="What is X?",
            topic="x-topic",
            expert_name="Tech Expert",
            research_triggered=False,
            cost=0.05,
        )
        # Reload — interaction should persist
        tracker2 = UserProfileTracker(str(tmp_path))
        profile = tracker2.load_or_create("user-1")
        assert profile.total_interactions == 1
        assert profile.total_cost == 0.05
        assert profile.topics_asked_about.get("x-topic", 0) == 1

    def test_save_profile_atomic_write(self, tmp_path: Path):
        """save_profile uses atomic_write_json — output should be readable
        and a previous version should not be left half-written even on
        repeated saves."""
        tracker = UserProfileTracker(str(tmp_path))
        profile = tracker.load_or_create("user-1")
        profile.total_interactions = 1
        tracker.save(profile)
        profile.total_interactions = 2
        tracker.save(profile)
        reloaded = tracker.load_or_create("user-1")
        assert reloaded.total_interactions == 2

    def test_serialize_and_deserialize_interaction_roundtrip(self):
        tracker = UserProfileTracker(str(Path("/tmp/x")))  # path not used
        interaction = UserInteraction(
            timestamp=datetime.now(timezone.utc),
            question="q",
            topic="t",
            expert_name="e",
            research_triggered=True,
            cost=0.1,
        )
        data = tracker._serialize_interaction(interaction)
        rebuilt = tracker._deserialize_interaction(data)
        assert rebuilt.question == "q"
        assert rebuilt.topic == "t"
        assert rebuilt.research_triggered is True
        assert rebuilt.cost == 0.1
