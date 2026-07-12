"""Tests for the regenerated expert digest (TKG step 4 / regeneration invariant).

The digest is a derived view over the canonical belief store: deterministic,
byte-stable for an unchanged store, $0 (no LLM), and it surfaces open
contradictions instead of smoothing them.
"""

from __future__ import annotations

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.digest import DIGEST_MARKER, build_digest


def _store(tmp_path) -> BeliefStore:
    return BeliefStore("Digest Test Expert", storage_dir=tmp_path / "beliefs")


def _belief(claim: str, confidence: float = 0.8, domain: str = "ai") -> Belief:
    return Belief(claim=claim, confidence=confidence, domain=domain)


class TestDigest:
    def test_carries_marker_banner_and_counts(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("Fact one"), check_conflicts=False)
        store.add_belief(_belief("Other-domain fact", domain="security"), check_conflicts=False)

        digest = build_digest(store)
        assert DIGEST_MARKER in digest
        assert "do not hand-edit" in digest
        assert "# Expert Digest: Digest Test Expert" in digest
        assert "**2** beliefs across **2** domain(s)" in digest
        assert "## ai (1)" in digest
        assert "## security (1)" in digest

    def test_byte_stable_for_unchanged_store(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("Stable fact A"), check_conflicts=False)
        store.add_belief(_belief("Stable fact B", confidence=0.6), check_conflicts=False)

        first = build_digest(store)
        second = build_digest(store)
        assert first == second  # no wall-clock timestamp, deterministic order

    def test_beliefs_sorted_by_confidence_within_domain(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("Low confidence claim", confidence=0.4), check_conflicts=False)
        store.add_belief(_belief("High confidence claim", confidence=0.95), check_conflicts=False)

        digest = build_digest(store)
        assert digest.index("High confidence claim") < digest.index("Low confidence claim")

    def test_open_contradictions_surfaced_not_smoothed(self, tmp_path):
        store = _store(tmp_path)
        existing, _ = store.add_belief(_belief("X is true"), check_conflicts=False)
        store.add_contested_belief(_belief("X is not true", confidence=0.9), [existing])

        digest = build_digest(store)
        assert "## Recorded Contradiction Candidates" in digest
        assert "0 model-confirmed, 1 unverified" in digest
        assert "X is true" in digest and "X is not true" in digest
        assert "resolve-conflicts" in digest
        assert "[contested x1]" in digest  # flags on the belief lines too

    def test_empty_store_renders_honestly(self, tmp_path):
        digest = build_digest(_store(tmp_path))
        assert "No beliefs recorded yet" in digest
        assert "As of: never" in digest

    def test_as_of_uses_latest_event_not_clock(self, tmp_path):
        store = _store(tmp_path)
        store.add_belief(_belief("Timed fact"), check_conflicts=False)
        events = store.iter_events()
        digest = build_digest(store)
        assert f"As of: {events[-1].timestamp.isoformat()}" in digest

    def test_temporal_edge_qualifiers_are_rendered_from_store(self, tmp_path):
        store = _store(tmp_path)
        source, _ = store.add_belief(_belief("Compiled sync applies graph commits"), check_conflicts=False)
        target, _ = store.add_belief(_belief("Graph commits can carry temporal edges"), check_conflicts=False)
        store.add_edge(
            source.id,
            target.id,
            "derived_from",
            provenance="graph-commit",
            temporal_context={
                "valid_from": "2026-06-01T00:00:00+00:00",
                "valid_until": "2026-06-30T00:00:00+00:00",
                "observed_at": "2026-06-15T12:00:00+00:00",
                "temporal_scope": "release-window",
            },
        )

        digest = build_digest(store)

        assert "## Temporal Edge Qualifiers" in digest
        assert "These time-scoped relationships are derived from stored edge metadata" in digest
        assert "`derived_from`" in digest
        assert "Compiled sync applies graph commits" in digest
        assert "Graph commits can carry temporal edges" in digest
        assert "provenance: graph-commit" in digest
        assert "valid 2026-06-01T00:00:00+00:00 to 2026-06-30T00:00:00+00:00" in digest
        assert "observed 2026-06-15T12:00:00+00:00" in digest
        assert "scope release-window" in digest

    def test_temporal_edge_section_renders_missing_endpoint_honestly(self, tmp_path):
        store = _store(tmp_path)
        target, _ = store.add_belief(_belief("Known target"), check_conflicts=False)
        store.add_edge(
            "missing-belief",
            target.id,
            "supports",
            temporal_context={"valid_from": "2026-06-01T00:00:00+00:00"},
        )

        digest = build_digest(store)

        assert "[missing-belief] missing belief" in digest
        assert "provenance: none" in digest
        assert "valid 2026-06-01T00:00:00+00:00 to unknown" in digest
