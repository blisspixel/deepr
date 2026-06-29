"""Tests for deepr.experts.continuity_metrics - eval methodology v2 (v2.15 #5).

Continuity properties measured from stored belief state at $0 (no API calls).
Each test plants a known ground truth and asserts the metric reports it -
including the failure paths (hidden staleness, over-assertion, a dropped
contradiction, window truncation), since a metric that can only report 1.0 is
not measuring anything.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deepr.experts import continuity_metrics as continuity_module
from deepr.experts.beliefs import Belief, BeliefChange, BeliefStore, Edge
from deepr.experts.continuity_metrics import (
    CONTINUITY_METHODOLOGY_VERSION,
    measure_continuity,
)


def _store(tmp_path) -> BeliefStore:
    return BeliefStore("Test Expert", storage_dir=tmp_path / "beliefs")


def _belief(claim: str, confidence: float = 0.8, **kw) -> Belief:
    return Belief(claim=claim, confidence=confidence, domain="ai", **kw)


def _metric(report, name):
    return next(m for m in report.metrics if m.name == name)


class TestStalenessHonesty:
    def test_aged_belief_reads_stale_fresh_belief_reads_fresh(self, tmp_path):
        store = _store(tmp_path)
        # Aged + high decay -> effective confidence collapses; horizon long past.
        aged = _belief("old fact", confidence=0.9, decay_rate=0.1, trust_class="secondary")
        aged.updated_at = datetime.now(UTC) - timedelta(days=200)
        store.beliefs[aged.id] = aged
        # Fresh, well within its decay horizon.
        fresh = _belief("fresh fact", confidence=0.85, decay_rate=0.01, trust_class="secondary")
        store.beliefs[fresh.id] = fresh

        m = _metric(measure_continuity(store), "staleness_honesty")
        assert m.score == 1.0
        assert m.detail["honest_stale"] == 1
        assert m.detail["honest_fresh"] == 1
        # The machinery makes hidden staleness impossible by construction.
        assert m.detail["hidden_stale"] == 0

    def test_not_applicable_when_no_beliefs(self, tmp_path):
        m = _metric(measure_continuity(_store(tmp_path)), "staleness_honesty")
        assert not m.applicable


class TestAbstentionCorrectness:
    def test_ungrounded_tertiary_abstains_primary_over_asserts(self, tmp_path):
        store = _store(tmp_path)
        # Tertiary, no sources -> capped at 0.60 abstention ceiling.
        store.beliefs["a"] = _belief("ungrounded tertiary", confidence=0.95)
        # Primary with NO evidence refs bypasses the floor -> over-asserted.
        over = _belief("ungrounded primary", confidence=0.9, trust_class="primary")
        store.beliefs["b"] = over

        m = _metric(measure_continuity(store), "abstention_correctness")
        assert m.score == 0.5
        assert m.detail["abstained_correctly"] == 1
        assert len(m.detail["over_asserted"]) == 1
        assert m.detail["over_asserted"][0]["belief_id"] == over.id

    def test_grounded_beliefs_excluded_from_sample(self, tmp_path):
        store = _store(tmp_path)
        store.beliefs["g"] = _belief("grounded", confidence=0.9, evidence_refs=["src1", "src2"])
        m = _metric(measure_continuity(store), "abstention_correctness")
        assert not m.applicable  # no ungrounded beliefs to measure


class TestContradictionSurfacing:
    def test_recorded_contradiction_is_surfaced(self, tmp_path):
        store = _store(tmp_path)
        a = _belief("X is true")
        store.add_belief(a, check_conflicts=False)
        b = _belief("X is false", confidence=0.9)
        store.add_contested_belief(b, [a])

        m = _metric(measure_continuity(store), "contradiction_surfacing")
        assert m.score == 1.0
        assert m.detail["recorded_pairs"] == 1
        assert m.detail["surfaced_pairs"] == 1

    def test_edge_only_contradiction_not_surfaced_is_caught(self, tmp_path):
        # A contradicts edge with no mirrored contradictions_with: recorded
        # ground truth includes it, but the contested view (which reads
        # contradictions_with) misses it. The metric must catch the gap.
        store = _store(tmp_path)
        c = _belief("Y is true")
        d = _belief("Y is false")
        store.add_belief(c, check_conflicts=False)
        store.add_belief(d, check_conflicts=False)
        edge = Edge(src_id=c.id, dst_id=d.id, edge_type="contradicts")
        store.edges[edge.key()] = edge  # bypass add_edge's contradictions_with sync

        m = _metric(measure_continuity(store), "contradiction_surfacing")
        assert m.score == 0.0
        assert m.detail["recorded_pairs"] == 1
        assert m.detail["surfaced_pairs"] == 0
        assert m.detail["missed_pairs"] == [(min(c.id, d.id), max(c.id, d.id))]

    def test_not_applicable_without_contradictions(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("uncontested"), check_conflicts=False)
        m = _metric(measure_continuity(store), "contradiction_surfacing")
        assert not m.applicable


class TestWhatChangedExactness:
    def test_event_log_store_is_exact(self, tmp_path):
        store = _store(tmp_path)
        for i in range(3):
            store.add_belief(_belief(f"fact {i}"), check_conflicts=False)

        m = _metric(measure_continuity(store), "what_changed_exactness")
        assert m.score == 1.0
        assert m.detail["store_format"] == "event_log"
        assert m.detail["recorded_changes"] == 3
        assert m.detail["replayed_changes"] == 3
        assert m.detail["window_truncated"] is False

    def test_legacy_window_reports_truncation(self, tmp_path):
        store = _store(tmp_path)
        assert not store.has_event_log  # no events.jsonl yet
        old = datetime.now(UTC) - timedelta(days=1)
        for i in range(150):
            store.changes.append(
                BeliefChange(
                    belief_id=f"b{i}",
                    change_type="created",
                    new_claim=f"c{i}",
                    new_confidence=0.5,
                    timestamp=old,
                )
            )

        m = _metric(measure_continuity(store), "what_changed_exactness")
        assert m.detail["store_format"] == "legacy_window"
        assert m.detail["window_truncated"] is True

    def test_not_applicable_when_no_changes(self, tmp_path):
        m = _metric(measure_continuity(_store(tmp_path)), "what_changed_exactness")
        assert not m.applicable


class TestTemporalEdgeQualifierVisibility:
    def test_temporal_edge_qualifiers_are_visible_through_explanation(self, tmp_path):
        store = _store(tmp_path)
        source, _ = store.add_belief(_belief("Default apply is enabled"), check_conflicts=False)
        target, _ = store.add_belief(_belief("Verified compiler emits graph commits"), check_conflicts=False)
        temporal = {
            "valid_from": "2026-06-01",
            "valid_until": "2026-06-30",
            "observed_at": "2026-06-29T00:00:00+00:00",
            "temporal_scope": "June 2026",
        }
        store.add_edge(source.id, target.id, "derived_from", provenance="graph-commit", temporal_context=temporal)

        m = _metric(measure_continuity(store), "temporal_edge_qualifier_visibility")

        assert m.score == 1.0
        assert m.detail["temporal_edges"] == 1
        assert m.detail["visible_temporal_edges"] == 1
        assert m.detail["missed_edges"] == []

    def test_dangling_temporal_edge_qualifier_gap_is_caught(self, tmp_path):
        store = _store(tmp_path)
        temporal = {"valid_from": "2026-06-01"}
        edge = Edge(src_id="missing-a", dst_id="missing-b", edge_type="supports", temporal_contexts=[temporal])
        store.edges[edge.key()] = edge

        m = _metric(measure_continuity(store), "temporal_edge_qualifier_visibility")

        assert m.score == 0.0
        assert m.detail["temporal_edges"] == 1
        assert m.detail["visible_temporal_edges"] == 0
        assert m.detail["missed_edges"] == ["missing-a->missing-b:supports"]

    def test_not_applicable_without_temporal_edge_qualifiers(self, tmp_path):
        store = _store(tmp_path)
        source, _ = store.add_belief(_belief("A"), check_conflicts=False)
        target, _ = store.add_belief(_belief("B"), check_conflicts=False)
        store.add_edge(source.id, target.id, "supports", provenance="graph-commit")

        m = _metric(measure_continuity(store), "temporal_edge_qualifier_visibility")

        assert not m.applicable


class TestTemporalEdgeDigestVisibility:
    def test_temporal_edge_qualifiers_are_visible_in_digest(self, tmp_path):
        store = _store(tmp_path)
        source, _ = store.add_belief(_belief("Default apply is enabled"), check_conflicts=False)
        target, _ = store.add_belief(_belief("Verified compiler emits graph commits"), check_conflicts=False)
        temporal = {
            "valid_from": "2026-06-01",
            "valid_until": "2026-06-30",
            "observed_at": "2026-06-29T00:00:00+00:00",
            "temporal_scope": "June 2026",
        }
        store.add_edge(source.id, target.id, "derived_from", provenance="graph-commit", temporal_context=temporal)

        m = _metric(measure_continuity(store), "temporal_edge_digest_visibility")

        assert m.score == 1.0
        assert m.detail["temporal_edges"] == 1
        assert m.detail["digest_visible_temporal_edges"] == 1
        assert m.detail["missed_edges"] == []

    def test_temporal_edge_digest_gap_is_caught(self, tmp_path, monkeypatch):
        store = _store(tmp_path)
        source, _ = store.add_belief(_belief("Source"), check_conflicts=False)
        target, _ = store.add_belief(_belief("Target"), check_conflicts=False)
        store.add_edge(
            source.id,
            target.id,
            "supports",
            provenance="graph-commit",
            temporal_context={"valid_from": "2026-06-01"},
        )
        monkeypatch.setattr(continuity_module, "_build_digest", lambda *_args, **_kwargs: "# Digest without edges")

        m = _metric(measure_continuity(store), "temporal_edge_digest_visibility")

        assert m.score == 0.0
        assert m.detail["temporal_edges"] == 1
        assert m.detail["digest_visible_temporal_edges"] == 0
        assert m.detail["missed_edges"] == [f"{source.id}->{target.id}:supports"]

    def test_not_applicable_without_temporal_edge_qualifiers(self, tmp_path):
        store = _store(tmp_path)
        source, _ = store.add_belief(_belief("A"), check_conflicts=False)
        target, _ = store.add_belief(_belief("B"), check_conflicts=False)
        store.add_edge(source.id, target.id, "supports", provenance="graph-commit")

        m = _metric(measure_continuity(store), "temporal_edge_digest_visibility")

        assert not m.applicable


class TestReport:
    def test_empty_store_has_no_applicable_metrics(self, tmp_path):
        report = measure_continuity(_store(tmp_path))
        assert report.overall is None
        assert all(not m.applicable for m in report.metrics)

    def test_methodology_version_stamped(self, tmp_path):
        report = measure_continuity(_store(tmp_path))
        assert report.methodology_version == CONTINUITY_METHODOLOGY_VERSION
        assert report.to_dict()["methodology_version"] == CONTINUITY_METHODOLOGY_VERSION

    def test_overall_is_mean_of_applicable(self, tmp_path):
        store = _store(tmp_path)
        # One ungrounded over-asserted (abstention 0.5) + a clean event log
        # (exactness 1.0); other metrics not applicable.
        store.beliefs["b"] = _belief("ungrounded primary", confidence=0.9, trust_class="primary")
        store.add_belief(_belief("logged"), check_conflicts=False)

        report = measure_continuity(store)
        applicable = [m for m in report.metrics if m.applicable]
        expected = sum(m.score for m in applicable) / len(applicable)
        assert report.overall == expected

    def test_measurement_is_read_only(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("immutable"), check_conflicts=False)
        before = len(store.beliefs)
        measure_continuity(store)
        assert len(store.beliefs) == before

    def test_to_dict_shape(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("shape"), check_conflicts=False)
        d = measure_continuity(store, expert_name="Named").to_dict()
        assert d["expert_name"] == "Named"
        assert "overall" in d
        assert len(d["metrics"]) == 6
        for metric in d["metrics"]:
            assert metric["status"] in ("measured", "not_applicable")
