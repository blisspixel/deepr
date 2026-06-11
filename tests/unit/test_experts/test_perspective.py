"""Tests for deepr.experts.perspective - temporal perspective queries.

what_changed and contested are read-side, cost-$0 layers over the belief
store's persisted structures (BeliefChange records, contradiction edges).
These tests use a real BeliefStore on a tmp dir; no API calls.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.perspective import contested, what_changed


def _store(tmp_path) -> BeliefStore:
    return BeliefStore("Test Expert", storage_dir=tmp_path / "beliefs")


def _belief(claim: str, confidence: float = 0.8) -> Belief:
    return Belief(claim=claim, confidence=confidence, domain="ai")


class TestWhatChanged:
    def test_added_beliefs_appear_in_delta(self, tmp_path):
        store = _store(tmp_path)
        since = datetime.now(UTC) - timedelta(minutes=1)
        store.add_belief(_belief("New fact about MCP"), check_conflicts=False)

        delta = what_changed(store, since)
        assert delta.total_changes == 1
        assert len(delta.added) == 1
        assert delta.added[0]["claim"] == "New fact about MCP"
        assert delta.added[0]["current"]["claim"] == "New fact about MCP"

    def test_changes_before_since_excluded(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("Old fact"), check_conflicts=False)
        since = datetime.now(UTC) + timedelta(seconds=1)  # after the add

        delta = what_changed(store, since)
        assert delta.total_changes == 0

    def test_contested_creations_bucketed_separately(self, tmp_path):
        store = _store(tmp_path)
        existing = _belief("X is true")
        store.add_belief(existing, check_conflicts=False)
        since = datetime.now(UTC) - timedelta(minutes=1)

        challenger = _belief("X is not true", confidence=0.9)
        store.add_contested_belief(challenger, [existing])

        delta = what_changed(store, since)
        assert len(delta.contested) == 1
        assert delta.contested[0]["claim"] == "X is not true"
        assert "contested" in delta.contested[0]["reason"]
        # The contested entry's snapshot carries its contradiction edge.
        assert existing.id in delta.contested[0]["current"]["contradictions_with"]

    def test_revised_beliefs_carry_old_confidence(self, tmp_path):
        store = _store(tmp_path)
        b = _belief("Confidence will change", confidence=0.5)
        store.add_belief(b, check_conflicts=False)
        since = datetime.now(UTC) - timedelta(minutes=1)
        store.update_belief(b.id, new_confidence=0.9, reason="stronger evidence")

        delta = what_changed(store, since)
        assert len(delta.revised) == 1
        assert delta.revised[0]["confidence"] == 0.9
        assert delta.revised[0]["reason"] == "stronger evidence"

    def test_naive_since_treated_as_utc(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("Tz handling"), check_conflicts=False)
        naive = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)

        delta = what_changed(store, naive)
        assert delta.total_changes == 1
        assert delta.since.tzinfo is not None

    def test_serializes(self, tmp_path):
        store = _store(tmp_path)
        since = datetime.now(UTC) - timedelta(minutes=1)
        store.add_belief(_belief("Serializable"), check_conflicts=False)

        d = what_changed(store, since, expert_name="Named Expert").to_dict()
        assert d["expert_name"] == "Named Expert"
        assert d["total_changes"] == 1
        assert d["window_truncated"] is False
        assert d["added"][0]["claim"] == "Serializable"


class TestContested:
    def test_no_conflicts_empty(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("Uncontested"), check_conflicts=False)

        result = contested(store)
        assert result["contested_count"] == 0
        assert result["pairs"] == []

    def test_open_pair_has_both_sides(self, tmp_path):
        store = _store(tmp_path)
        existing = _belief("X is true", confidence=0.6)
        store.add_belief(existing, check_conflicts=False)
        challenger = _belief("X is not true", confidence=0.9)
        store.add_contested_belief(challenger, [existing])

        result = contested(store, expert_name="Named Expert")
        assert result["expert_name"] == "Named Expert"
        assert result["contested_count"] == 1
        assert result["open_count"] == 1
        pair = result["pairs"][0]
        claims = {pair["a"]["claim"], pair["b"]["claim"]}
        assert claims == {"X is true", "X is not true"}
        assert pair["status"] == "open"

    def test_pair_reported_once_not_twice(self, tmp_path):
        # Edges are bidirectional; the pair must be deduped.
        store = _store(tmp_path)
        a = _belief("A claim")
        store.add_belief(a, check_conflicts=False)
        b = _belief("Not a claim")
        store.add_contested_belief(b, [a])

        result = contested(store)
        assert result["contested_count"] == 1

    def test_dangling_edge_reported(self, tmp_path):
        store = _store(tmp_path)
        a = _belief("Survivor")
        a.add_contradiction("gone123")
        store.add_belief(a, check_conflicts=False)

        result = contested(store)
        assert result["contested_count"] == 1
        assert result["open_count"] == 0
        assert result["pairs"][0]["status"] == "dangling"
        assert result["pairs"][0]["b"]["belief_id"] == "gone123"
