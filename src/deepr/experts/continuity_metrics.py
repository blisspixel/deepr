"""Continuity-property metrics over an expert's belief store (eval methodology v2).

The memory-systems literature (ATANT 2604.10981, audited in
docs/design/belief-lifecycle.md finding 6) shows that popular memory
benchmarks (LoCoMo, LongMemEval) measure at most 2 of 7 continuity
properties, so chasing those scores would be measurement theater - the same
trap the saturated-eval incident proved live on 2026-06-11. Instead this
module measures deepr's *own* continuity properties, from already-stored
state, at $0 (no LLM, no network):

- **staleness honesty** - aged beliefs read as low-confidence rather than
  presenting their undiminished raw confidence. Guards the decay + trust
  machinery against silently going stale.
- **abstention correctness** - ungrounded claims are not asserted with high
  confidence; the source-trust floors (v2.15 #1) hold end-to-end.
- **contradiction surfacing** - every recorded contradiction is exposed by
  the contested view; nothing is smoothed into a single coherent narrative
  (the Rashomon rule, design finding 5).
- **what-changed exactness** - the event-log replay reproduces the true
  mutation history with no loss; legacy bounded-window stores report their
  truncation honestly rather than claiming completeness.
- **temporal edge qualifier visibility** - every stored temporal edge qualifier
  is visible through the read-side explanation surface instead of being hidden
  in the backing store.

Each metric carries its own ground truth derived *independently* of the
surface it scores (time-based vs confidence-based; recorded edges vs the
contested reader; the raw event log vs the what_changed buckets), so a high
score means the surfaces agree with reality, not with themselves. A metric
with no applicable sample is reported ``not_applicable`` and excluded from
the overall score - silent zeros would read as failures.

This is read-side and cost-$0 like the rest of the perspective query
surface (perspective.py); it never mutates the store.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.perspective import contested as _contested
from deepr.experts.perspective import explain_belief as _explain_belief
from deepr.experts.perspective import what_changed as _what_changed

# Bump on any change to how a metric is computed, so stored runs stay
# comparable (the roadmap's "methodology versioning for run comparability").
# 1.0: initial four continuity properties.
# 1.1: add temporal edge qualifier visibility.
CONTINUITY_METHODOLOGY_VERSION = "1.1"

# A belief carrying no source provenance must not read as more than
# abstention-level confidence - this is the tertiary single-source trust
# ceiling (Belief._trust_ceiling), restated here as the assertion floor the
# abstention metric checks against.
_ABSTENTION_CEILING = 0.60

# Epoch sentinel for "replay everything" - what_changed/iter_events filter
# strictly after this, so every recorded change is included.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass
class MetricResult:
    """One continuity property: a score in [0, 1], or not-applicable."""

    name: str
    score: float | None  # None => not enough data to measure (excluded from overall)
    sample_size: int
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def applicable(self) -> bool:
        return self.score is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 3) if self.score is not None else None,
            "status": "measured" if self.applicable else "not_applicable",
            "sample_size": self.sample_size,
            "detail": self.detail,
        }


@dataclass
class ContinuityReport:
    """An expert's continuity properties, measured from stored state at $0."""

    expert_name: str
    metrics: list[MetricResult]
    methodology_version: str = CONTINUITY_METHODOLOGY_VERSION
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def overall(self) -> float | None:
        """Mean of the applicable metric scores (None if none apply)."""
        scored = [m.score for m in self.metrics if m.score is not None]
        return sum(scored) / len(scored) if scored else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "methodology_version": self.methodology_version,
            "overall": round(self.overall, 3) if self.overall is not None else None,
            "metrics": [m.to_dict() for m in self.metrics],
            "generated_at": self.generated_at.isoformat(),
        }


def _refresh_horizon_days(belief: Belief, threshold: float) -> float:
    """Days until decay alone would drop raw confidence below ``threshold``.

    Time-based ground truth, deliberately computed from the *raw* stored
    confidence and decay rate only - independent of the trust-ceiling that
    ``get_current_confidence`` applies - so the staleness metric compares two
    genuinely different computations rather than the surface against itself.
    """
    if belief.decay_rate <= 0:
        return math.inf
    if belief.confidence <= threshold:
        return 0.0
    # confidence * exp(-rate * days) = threshold  =>  days = ln(conf/thr) / rate
    return math.log(belief.confidence / threshold) / belief.decay_rate


def _staleness_honesty(store: BeliefStore, threshold: float) -> MetricResult:
    """Do aged beliefs read as stale instead of presenting raw confidence?

    Ground truth (time-based): a belief is *due* if its age since last update
    exceeds the decay horizon computed from raw confidence + decay rate.
    Report (confidence-based): ``is_stale`` over the effective confidence
    (decay + trust ceiling). The dangerous divergence is ``hidden_stale`` - a
    belief past its horizon that the surface still reports fresh; the
    trust-ceiling normally makes the surface *more* conservative, so a healthy
    store has none. Scored as balanced accuracy so neither class dominates.
    """
    now = datetime.now(UTC)
    tp = tn = hidden_stale = false_stale = 0
    for belief in store.beliefs.values():
        age_days = (now - belief.updated_at).days
        due = age_days >= _refresh_horizon_days(belief, threshold)
        reported = belief.is_stale(threshold)
        if due and reported:
            tp += 1
        elif not due and not reported:
            tn += 1
        elif due and not reported:
            hidden_stale += 1  # the failure staleness honesty guards against
        else:
            false_stale += 1  # surface is conservative; honest, not a hazard

    total = tp + tn + hidden_stale + false_stale
    if total == 0:
        return MetricResult("staleness_honesty", None, 0, {"reason": "no beliefs"})

    due_total = tp + hidden_stale
    fresh_total = tn + false_stale
    # Balanced accuracy: average of the two class recalls. When a class is
    # empty its recall is treated as perfect (nothing to get wrong there).
    due_recall = tp / due_total if due_total else 1.0
    fresh_recall = tn / fresh_total if fresh_total else 1.0
    score = (due_recall + fresh_recall) / 2

    return MetricResult(
        "staleness_honesty",
        score,
        total,
        {
            "honest_stale": tp,
            "honest_fresh": tn,
            "hidden_stale": hidden_stale,
            "conservative_stale": false_stale,
            "threshold": threshold,
        },
    )


def _abstention_correctness(store: BeliefStore) -> MetricResult:
    """Are ungrounded claims down-weighted instead of asserted confidently?

    Sample: beliefs with no source provenance (``evidence_refs`` empty) - the
    expert should abstain (low effective confidence) rather than assert them.
    Correct when effective confidence stays at/below the abstention ceiling;
    a value above it means the trust floor was bypassed (a poisoned or
    fabricated high-confidence claim is exactly this failure). Measures the
    v2.15 source-trust floors working end-to-end.
    """
    ungrounded = [b for b in store.beliefs.values() if not set(b.evidence_refs)]
    if not ungrounded:
        return MetricResult("abstention_correctness", None, 0, {"reason": "no ungrounded beliefs"})

    abstained = 0
    over_asserted: list[dict[str, Any]] = []
    for belief in ungrounded:
        if belief.get_current_confidence() <= _ABSTENTION_CEILING + 1e-9:
            abstained += 1
        else:
            over_asserted.append({"belief_id": belief.id, "confidence": round(belief.get_current_confidence(), 3)})

    return MetricResult(
        "abstention_correctness",
        abstained / len(ungrounded),
        len(ungrounded),
        {
            "ungrounded": len(ungrounded),
            "abstained_correctly": abstained,
            "over_asserted": over_asserted,
            "ceiling": _ABSTENTION_CEILING,
        },
    )


def _recorded_contradiction_pairs(store: BeliefStore) -> set[tuple[str, str]]:
    """Canonical contradiction pairs recorded in the store (the ground truth).

    Reads both the legacy ``contradictions_with`` lists and the typed
    ``contradicts`` edges - the union is what *should* surface as contested.
    """
    pairs: set[tuple[str, str]] = set()
    for belief in store.beliefs.values():
        for other_id in belief.contradictions_with:
            pairs.add((min(belief.id, other_id), max(belief.id, other_id)))
    for edge in store.edges.values():
        if edge.edge_type == "contradicts":
            pairs.add((min(edge.src_id, edge.dst_id), max(edge.src_id, edge.dst_id)))
    return pairs


def _contradiction_surfacing(store: BeliefStore) -> MetricResult:
    """Does the contested view surface every recorded contradiction?

    Ground truth: contradiction pairs recorded on beliefs/edges. Report: the
    pairs ``contested()`` returns. Recall guards against the smoothing failure
    where a conflict is quietly dropped instead of shown - the one signal most
    worth keeping (design finding 5, the Rashomon rule).
    """
    recorded = _recorded_contradiction_pairs(store)
    if not recorded:
        return MetricResult("contradiction_surfacing", None, 0, {"reason": "no recorded contradictions"})

    view = _contested(store, expert_name=store.expert_name)
    surfaced: set[tuple[str, str]] = set()
    open_pairs = 0
    for pair in view["pairs"]:
        a_id = pair["a"].get("belief_id", "")
        b_id = pair["b"].get("belief_id", "")
        if a_id and b_id:
            surfaced.add((min(a_id, b_id), max(a_id, b_id)))
        if pair.get("status") == "open":
            open_pairs += 1

    hit = len(recorded & surfaced)
    return MetricResult(
        "contradiction_surfacing",
        hit / len(recorded),
        len(recorded),
        {
            "recorded_pairs": len(recorded),
            "surfaced_pairs": hit,
            "missed_pairs": sorted(recorded - surfaced),
            "open_pairs": open_pairs,
        },
    )


def _what_changed_exactness(store: BeliefStore) -> MetricResult:
    """Does the what_changed replay reproduce the full mutation history?

    Ground truth: the raw event log (``iter_events``), which is the unbounded
    append-only record. Report: the buckets ``what_changed(since=epoch)``
    produces. For an event-log store this is exact (1.0); a legacy
    bounded-window store scores below 1.0 in proportion to what its 100-record
    cap dropped, and the divergence is reported rather than hidden.
    """
    if store.has_event_log:
        truth = len(store.iter_events())
        store_format = "event_log"
    else:
        truth = len(store.changes)
        store_format = "legacy_window"

    if truth == 0:
        return MetricResult("what_changed_exactness", None, 0, {"reason": "no recorded changes"})

    delta = _what_changed(store, _EPOCH, expert_name=store.expert_name)
    represented = delta.total_changes
    score = min(1.0, represented / truth)

    return MetricResult(
        "what_changed_exactness",
        score,
        truth,
        {
            "recorded_changes": truth,
            "replayed_changes": represented,
            "store_format": store_format,
            "window_truncated": delta.window_truncated,
            "buckets": {
                "added": len(delta.added),
                "revised": len(delta.revised),
                "contested": len(delta.contested),
                "archived": len(delta.archived),
            },
        },
    )


def _explanation_edges_for(
    edge_id: str, store: BeliefStore, cache: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    if edge_id in cache:
        return cache[edge_id]
    explanation = _explain_belief(store, edge_id)
    if explanation is None:
        cache[edge_id] = []
    else:
        cache[edge_id] = [*explanation.supports, *explanation.derived_from, *explanation.contradicts]
    return cache[edge_id]


def _temporal_edge_key(src_id: str, dst_id: str, edge_type: str) -> str:
    return f"{src_id}->{dst_id}:{edge_type}"


def _temporal_edge_visible(
    store: BeliefStore,
    cache: dict[str, list[dict[str, Any]]],
    src_id: str,
    dst_id: str,
    edge_type: str,
    contexts: list[dict[str, str]],
) -> bool:
    for entry in [*_explanation_edges_for(src_id, store, cache), *_explanation_edges_for(dst_id, store, cache)]:
        if entry.get("belief_id") not in {src_id, dst_id}:
            continue
        if entry.get("edge_type") != edge_type:
            continue
        if entry.get("temporal_contexts") == contexts:
            return True
    return False


def _temporal_edge_qualifier_visibility(store: BeliefStore) -> MetricResult:
    """Are stored temporal edge qualifiers visible through read-side queries?

    Ground truth: typed belief edges that carry temporal contexts. Report: the
    `explain_belief` edge entries for each endpoint. This guards the newest
    graph-commit write path against producing metadata that can be written but
    not inspected by host agents.
    """
    temporal_edges = [edge for edge in store.edges.values() if edge.temporal_contexts]
    if not temporal_edges:
        return MetricResult("temporal_edge_qualifier_visibility", None, 0, {"reason": "no temporal edge qualifiers"})

    visible = 0
    missed: list[str] = []
    explanation_cache: dict[str, list[dict[str, Any]]] = {}
    for edge in temporal_edges:
        contexts = [dict(context) for context in edge.temporal_contexts]
        if _temporal_edge_visible(store, explanation_cache, edge.src_id, edge.dst_id, edge.edge_type, contexts):
            visible += 1
        else:
            missed.append(_temporal_edge_key(edge.src_id, edge.dst_id, edge.edge_type))

    return MetricResult(
        "temporal_edge_qualifier_visibility",
        visible / len(temporal_edges),
        len(temporal_edges),
        {
            "temporal_edges": len(temporal_edges),
            "visible_temporal_edges": visible,
            "missed_edges": sorted(missed),
        },
    )


def measure_continuity(
    store: BeliefStore,
    *,
    staleness_threshold: float = 0.3,
    expert_name: str = "",
) -> ContinuityReport:
    """Measure all continuity properties of an expert from stored state ($0).

    Args:
        store: The expert's belief store (read only - never mutated).
        staleness_threshold: Effective-confidence floor for the staleness and
            honesty checks (matches health-check's default).
        expert_name: Display name (defaults to the store's).

    Returns:
        A methodology-versioned ``ContinuityReport``. Metrics with no
        applicable sample are reported ``not_applicable`` and excluded from
        the overall score.
    """
    metrics = [
        _staleness_honesty(store, staleness_threshold),
        _abstention_correctness(store),
        _contradiction_surfacing(store),
        _what_changed_exactness(store),
        _temporal_edge_qualifier_visibility(store),
    ]
    return ContinuityReport(expert_name=expert_name or store.expert_name, metrics=metrics)
