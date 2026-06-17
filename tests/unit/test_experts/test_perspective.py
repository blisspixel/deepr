"""Tests for deepr.experts.perspective - temporal perspective queries.

what_changed and contested are read-side, cost-$0 layers over the belief
store's persisted structures (BeliefChange records, contradiction edges).
These tests use a real BeliefStore on a tmp dir; no API calls.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deepr.experts.beliefs import Belief, BeliefChange, BeliefStore
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


class TestBeliefEventLog:
    """The append-only events.jsonl (TKG step 1): unbounded, durable, exact.

    See docs/design/temporal-knowledge-graph.md - the event log removes
    what_changed's 100-record truncation caveat; legacy stores without the
    log keep the honest caveat.
    """

    def test_events_appended_and_replayed_across_reload(self, tmp_path):
        store = _store(tmp_path)
        b1, _ = store.add_belief(_belief("Fact one"), check_conflicts=False)
        store.add_belief(_belief("Fact two"), check_conflicts=False)
        store.update_belief(b1.id, new_confidence=0.95, reason="corroborated")
        store.archive_belief(b1.id, reason="superseded")

        reloaded = BeliefStore("Test Expert", storage_dir=tmp_path / "beliefs")
        events = reloaded.iter_events()
        kinds = [e.change_type for e in events]
        assert kinds == ["created", "created", "updated", "archived"]
        assert events[2].new_confidence == 0.95
        assert events[2].reason == "corroborated"

    def test_what_changed_is_exact_beyond_the_legacy_window(self, tmp_path):
        store = _store(tmp_path)
        epoch = datetime.now(UTC) - timedelta(days=1)
        for i in range(120):
            store.add_belief(_belief(f"Fact number {i}"), check_conflicts=False)

        # Reload so the legacy changes list is capped by _save's 100-record
        # window - the event log must still have all 120.
        reloaded = BeliefStore("Test Expert", storage_dir=tmp_path / "beliefs")
        assert len(reloaded.changes) <= 100

        delta = what_changed(reloaded, epoch)
        assert len(delta.added) == 120
        assert delta.window_truncated is False
        assert delta.to_dict()["window_note"] == ""

    def test_legacy_store_without_log_reports_truncation(self, tmp_path):
        store = _store(tmp_path)
        epoch = datetime.now(UTC) - timedelta(days=1)
        for i in range(120):
            store.add_belief(_belief(f"Fact number {i}"), check_conflicts=False)
        store.events_path.unlink()  # simulate a pre-event-log store

        reloaded = BeliefStore("Test Expert", storage_dir=tmp_path / "beliefs")
        assert reloaded.has_event_log is False

        delta = what_changed(reloaded, epoch)
        assert len(delta.added) <= 100
        assert delta.window_truncated is True
        assert "bounded" in delta.to_dict()["window_note"]

    def test_malformed_event_lines_skipped_not_fatal(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("Good fact"), check_conflicts=False)
        with open(store.events_path, "a", encoding="utf-8") as f:
            f.write("this is not json\n")
            f.write('{"missing": "required fields"}\n')
        store.add_belief(_belief("Another good fact"), check_conflicts=False)

        events = store.iter_events()
        assert [e.new_claim for e in events] == ["Good fact", "Another good fact"]

    def test_since_filter_is_strictly_after(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("Before"), check_conflicts=False)
        cutoff = store.iter_events()[-1].timestamp
        store.add_belief(_belief("After"), check_conflicts=False)

        events = store.iter_events(since=cutoff)
        assert [e.new_claim for e in events] == ["After"]

    def test_equal_event_timestamps_are_made_queryable(self, tmp_path):
        store = _store(tmp_path)
        timestamp = datetime(2026, 1, 1, tzinfo=UTC)
        store._record_change(
            BeliefChange(
                belief_id="before",
                change_type="created",
                new_claim="Before",
                new_confidence=0.8,
                timestamp=timestamp,
            )
        )
        store._record_change(
            BeliefChange(
                belief_id="after",
                change_type="created",
                new_claim="After",
                new_confidence=0.8,
                timestamp=timestamp,
            )
        )

        all_events = store.iter_events()
        assert all_events[1].timestamp > all_events[0].timestamp
        assert [e.new_claim for e in store.iter_events(since=timestamp)] == ["After"]


class TestTypedEdges:
    """Typed belief-graph edges (TKG step 2): dedup, symmetry, migration."""

    def test_edge_roundtrip_and_dedup_with_provenance_accumulation(self, tmp_path):
        store = _store(tmp_path)
        a, _ = store.add_belief(_belief("A"), check_conflicts=False)
        b, _ = store.add_belief(_belief("B"), check_conflicts=False)

        e1 = store.add_edge(a.id, b.id, "supports", provenance="report-1")
        e2 = store.add_edge(a.id, b.id, "supports", provenance="report-2")
        assert e1 is e2
        assert e1.provenance == ["report-1", "report-2"]

        reloaded = BeliefStore("Test Expert", storage_dir=tmp_path / "beliefs")
        edges = reloaded.edges_for(a.id, "supports")
        assert len(edges) == 1
        assert edges[0].provenance == ["report-1", "report-2"]

    def test_contradicts_is_symmetric_and_mirrors_legacy_field(self, tmp_path):
        store = _store(tmp_path)
        a, _ = store.add_belief(_belief("X is true"), check_conflicts=False)
        b, _ = store.add_belief(_belief("Unrelated"), check_conflicts=False)

        store.add_edge(a.id, b.id, "contradicts", provenance="manual")
        # Reversed direction dedups onto the same edge
        store.add_edge(b.id, a.id, "contradicts", provenance="reversed")
        assert len(store.edges_for(a.id, "contradicts")) == 1
        # Legacy field mirrored both ways - existing readers keep working
        assert b.id in a.contradictions_with
        assert a.id in b.contradictions_with

    def test_contested_belief_writes_typed_edge(self, tmp_path):
        store = _store(tmp_path)
        existing, _ = store.add_belief(_belief("X is true"), check_conflicts=False)
        challenger = _belief("X is not true", confidence=0.9)
        store.add_contested_belief(challenger, [existing])

        edges = store.edges_for(challenger.id, "contradicts")
        assert len(edges) == 1
        assert "contested:absorb" in edges[0].provenance

    def test_legacy_store_migrates_contradictions_to_edges(self, tmp_path):
        import json as _json

        store = _store(tmp_path)
        existing, _ = store.add_belief(_belief("X is true"), check_conflicts=False)
        challenger = _belief("X is not true", confidence=0.9)
        store.add_contested_belief(challenger, [existing])

        # Simulate a pre-edge-store file: strip the edges key
        data = _json.loads(store.storage_path.read_text(encoding="utf-8"))
        data.pop("edges", None)
        store.storage_path.write_text(_json.dumps(data), encoding="utf-8")

        reloaded = BeliefStore("Test Expert", storage_dir=tmp_path / "beliefs")
        edges = reloaded.edges_for(challenger.id, "contradicts")
        assert len(edges) == 1
        assert "migrated:contradictions_with" in edges[0].provenance

        # Idempotent: a second reload neither duplicates nor re-migrates
        again = BeliefStore("Test Expert", storage_dir=tmp_path / "beliefs")
        assert len(again.edges_for(challenger.id, "contradicts")) == 1

    def test_invalid_edges_rejected(self, tmp_path):
        import pytest as _pytest

        store = _store(tmp_path)
        a, _ = store.add_belief(_belief("A"), check_conflicts=False)
        b, _ = store.add_belief(_belief("B"), check_conflicts=False)

        with _pytest.raises(ValueError, match="Unknown edge type"):
            store.add_edge(a.id, b.id, "refutes")
        with _pytest.raises(ValueError, match="itself"):
            store.add_edge(a.id, a.id, "supports")


class TestExplainBelief:
    """The introspection query (TKG step 4): evidence, history, chains."""

    def test_explains_by_id_with_evidence_and_trajectory(self, tmp_path):
        from deepr.experts.perspective import explain_belief

        store = _store(tmp_path)
        belief = Belief(
            claim="MCP supports dynamic tool discovery", confidence=0.7, domain="ai", evidence_refs=["report:mcp-2026"]
        )
        store.add_belief(belief, check_conflicts=False)
        store.update_belief(belief.id, new_confidence=0.9, reason="corroborated by spec")

        result = explain_belief(store, belief.id)
        assert result is not None
        assert result.belief["claim"] == "MCP supports dynamic tool discovery"
        assert result.evidence_roots == ["report:mcp-2026"]
        kinds = [t["change_type"] for t in result.trajectory]
        assert kinds == ["created", "updated"]
        assert result.trajectory[-1]["confidence"] == 0.9
        assert result.trajectory[-1]["reason"] == "corroborated by spec"

    def test_resolves_by_fuzzy_claim_text(self, tmp_path):
        from deepr.experts.perspective import explain_belief

        store = _store(tmp_path)
        store.add_belief(_belief("Temporal knowledge graphs beat flat buffers"), check_conflicts=False)

        result = explain_belief(store, "temporal knowledge graphs")
        assert result is not None
        assert "Temporal knowledge graphs" in result.belief["claim"]

    def test_unknown_reference_returns_none(self, tmp_path):
        from deepr.experts.perspective import explain_belief

        store = _store(tmp_path)
        store.add_belief(_belief("Something"), check_conflicts=False)
        assert explain_belief(store, "completely unrelated zebra quantum") is None

    def test_walks_support_chain_depth_bounded_and_cycle_safe(self, tmp_path):
        from deepr.experts.perspective import explain_belief

        store = _store(tmp_path)
        a, _ = store.add_belief(_belief("Claim A root"), check_conflicts=False)
        b, _ = store.add_belief(_belief("Claim B middle"), check_conflicts=False)
        c, _ = store.add_belief(_belief("Claim C far"), check_conflicts=False)
        store.add_edge(a.id, b.id, "supports", provenance="report-1")
        store.add_edge(b.id, c.id, "supports", provenance="report-2")
        store.add_edge(c.id, a.id, "supports", provenance="cycle-edge")  # cycle

        shallow = explain_belief(store, a.id, depth=1)
        assert {e["belief_id"] for e in shallow.supports} == {b.id, c.id}  # both touch A at 1 hop
        deep = explain_belief(store, a.id, depth=3)
        ids = {e["belief_id"] for e in deep.supports}
        assert ids == {b.id, c.id}  # cycle does not duplicate or recurse forever
        hops = {e["belief_id"]: e["hops"] for e in deep.supports}
        assert hops[b.id] == 1

    def test_contradictions_are_direct_neighbors_with_status(self, tmp_path):
        from deepr.experts.perspective import explain_belief

        store = _store(tmp_path)
        x, _ = store.add_belief(_belief("X is true"), check_conflicts=False)
        challenger = _belief("X is not true", confidence=0.9)
        store.add_contested_belief(challenger, [x])

        result = explain_belief(store, x.id)
        assert len(result.contradicts) == 1
        assert result.contradicts[0]["belief_id"] == challenger.id
        assert result.contradicts[0]["status"] == "open"
        assert "contested:absorb" in result.contradicts[0]["provenance"]

    def test_to_dict_shape(self, tmp_path):
        from deepr.experts.perspective import explain_belief

        store = _store(tmp_path)
        b, _ = store.add_belief(_belief("Shape test"), check_conflicts=False)
        d = explain_belief(store, b.id).to_dict()
        for key in (
            "expert_name",
            "belief",
            "evidence_roots",
            "trajectory",
            "supports",
            "derived_from",
            "contradicts",
            "depth",
            "generated_at",
        ):
            assert key in d
