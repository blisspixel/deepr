"""Tests for UserProfileTracker - fast path coverage.

The module was 0% covered before; this exercises load/create,
interaction recording, persistence round-trip, and the inference paths
that update topics_asked_about / expertise_signals.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
        # Reload - interaction should persist
        tracker2 = UserProfileTracker(str(tmp_path))
        profile = tracker2.load_or_create("user-1")
        assert profile.total_interactions == 1
        assert profile.total_cost == 0.05
        assert profile.topics_asked_about.get("x-topic", 0) == 1

    def test_save_profile_atomic_write(self, tmp_path: Path):
        """save_profile uses atomic_write_json - output should be readable
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
            timestamp=datetime.now(UTC),
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


class TestUserProfileInferenceAndSummary:
    """Cover the summary / expertise / context / interests helpers."""

    def test_corrupt_profile_falls_back_to_new(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        tracker._get_profile_path("c").write_text("{ broken json", encoding="utf-8")
        profile = tracker.load_or_create("c")
        assert profile.user_id == "c"
        assert profile.total_interactions == 0

    def test_record_without_profile_is_noop(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        tracker.record_interaction("q", "t", "E", False, 0.1)  # no current profile
        assert tracker.current_profile is None

    def test_recent_interactions_trim_to_100(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        tracker.load_or_create("u")
        for i in range(105):
            tracker.record_interaction(f"q{i}", "t", "E", False, 0.0)
        assert len(tracker.current_profile.recent_interactions) == 100

    def test_detect_expertise_levels(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        tracker.load_or_create("u")
        assert tracker.detect_expertise_level("unseen") == "beginner"
        tracker.current_profile.topics_asked_about["mid"] = 3
        assert tracker.detect_expertise_level("mid") == "intermediate"
        tracker.current_profile.topics_asked_about["deep"] = 9
        assert tracker.detect_expertise_level("deep") == "expert"

    def test_detect_expertise_no_profile_default(self, tmp_path: Path):
        assert UserProfileTracker(str(tmp_path)).detect_expertise_level("x") == "intermediate"

    def test_context_summary_new_user(self, tmp_path: Path):
        assert "New user" in UserProfileTracker(str(tmp_path)).get_context_summary()

    def test_context_summary_populated(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        tracker.load_or_create("u")
        p = tracker.current_profile
        p.total_interactions = 4
        p.topics_asked_about = {"ai": 5, "ml": 2}
        p.tech_stack = ["python"]
        p.current_projects = ["proj-x"]
        p.goals = ["ship"]
        tracker.record_interaction("recent?", "ai", "E", False, 0.0)
        out = tracker.get_context_summary()
        assert "previous interactions" in out
        assert "Primary interests" in out
        assert "Tech stack: python" in out
        assert "proj-x" in out and "ship" in out
        assert "Active today" in out

    def test_context_summary_days_ago(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        tracker.load_or_create("u")
        tracker.record_interaction("q", "t", "E", False, 0.0)
        tracker.current_profile.recent_interactions[-1].timestamp = datetime.now(UTC) - timedelta(days=2)
        assert "Last active 2 days ago" in tracker.get_context_summary()

    def test_update_context(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        tracker.load_or_create("u")
        tracker.update_context(tech_stack=["go"], projects=["p"], goals=["g"])
        assert tracker.current_profile.tech_stack == ["go"]
        assert tracker.current_profile.current_projects == ["p"]
        assert tracker.current_profile.goals == ["g"]

    def test_update_context_no_profile_noop(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        tracker.update_context(tech_stack=["go"])
        assert tracker.current_profile is None

    def test_top_interests_sorted_and_limited(self, tmp_path: Path):
        tracker = UserProfileTracker(str(tmp_path))
        tracker.load_or_create("u")
        tracker.current_profile.topics_asked_about = {"a": 1, "b": 5, "c": 3}
        assert tracker.get_top_interests(limit=2) == [("b", 5), ("c", 3)]

    def test_top_interests_no_profile(self, tmp_path: Path):
        assert UserProfileTracker(str(tmp_path)).get_top_interests() == []
