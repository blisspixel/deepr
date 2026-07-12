"""Temporal perspective queries over an expert's belief store.

These are the first two tools of the temporal-knowledge-graph query surface
(ROADMAP Phase 4, v2.14): read-side, cost-$0 layers over structures the
belief store already persists, shipped ahead of the full typed-edge graph.

- ``what_changed``: the perspective delta since a timestamp - beliefs added,
  revised, contested, or archived - so a host agent (an always-on autopilot,
  a coding agent with ephemeral context) re-syncs with an expert it consulted
  before instead of re-reading everything.
- ``contested``: open contradiction candidates with both sides' claims,
  confidence, provenance, and verification assurance, so consumers see live
  dissent without confusing an unverified router candidate for semantic truth.

A corpus is what was read; a perspective is what is believed. These queries
expose the *perspective*: not content, but calibrated epistemic state with
history.

Stores with the append-only belief event log (``events.jsonl``, written by
every change since v2.13.x) get exact deltas with no window limit. Legacy
stores without the log fall back to the bounded 100-record ``changes``
window and report truncation honestly (``window_truncated``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from deepr.experts.belief_edges import EDGE_TYPES, Edge, contradiction_verification
from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.edge_temporal import parse_iso_temporal

logger = logging.getLogger(__name__)

# Reason prefix written by BeliefStore.add_contested_belief - identifies a
# change record as a contested (contradiction-flagged) creation.
_CONTESTED_REASON_PREFIX = "contested:"
_DEFAULT_TEMPORAL_EDGE_LIMIT = 50
_MAX_TEMPORAL_EDGE_LIMIT = 200


def _edge_temporal_contexts(edge: Edge) -> list[dict[str, str]]:
    return [dict(context) for context in edge.temporal_contexts]


def _temporal_edge_summary(edge: Edge, belief_id: str, store: BeliefStore) -> dict[str, Any]:
    other_id = edge.dst_id if edge.src_id == belief_id else edge.src_id
    other = store.beliefs.get(other_id)
    return {
        "edge_type": edge.edge_type,
        "source_belief_id": edge.src_id,
        "target_belief_id": edge.dst_id,
        "other_belief_id": other_id,
        "other_claim": other.claim if other else "",
        "other_confidence": round(other.get_current_confidence(), 3) if other else None,
        "status": "open" if other is not None else "dangling",
        "provenance": list(edge.provenance),
        "temporal_contexts": _edge_temporal_contexts(edge),
    }


def _temporal_edges_for_belief(store: BeliefStore, belief_id: str) -> list[dict[str, Any]]:
    edges = [edge for edge in store.edges_for(belief_id) if edge.temporal_contexts]
    return [
        _temporal_edge_summary(edge, belief_id, store)
        for edge in sorted(edges, key=lambda item: (item.edge_type, item.src_id, item.dst_id))
    ]


def _edge_endpoint_summary(store: BeliefStore, belief_id: str) -> dict[str, Any]:
    belief = store.beliefs.get(belief_id)
    if belief is None:
        return {"belief_id": belief_id, "claim": "", "confidence": None, "status": "dangling"}
    return {
        "belief_id": belief.id,
        "claim": belief.claim,
        "confidence": round(belief.get_current_confidence(), 3),
        "status": "open",
    }


def _temporal_filter_active(
    valid_at: datetime | None,
    observed_since: datetime | None,
    observed_until: datetime | None,
) -> bool:
    return valid_at is not None or observed_since is not None or observed_until is not None


def _parse_filter_time(field: str, value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    parsed_value = parse_iso_temporal(str(value).strip())
    if parsed_value is None:
        raise ValueError(f"{field} is not ISO 8601: {value!r}")
    return parsed_value


def _context_matches_temporal_filters(
    context: dict[str, str],
    *,
    valid_at: datetime | None,
    observed_since: datetime | None,
    observed_until: datetime | None,
) -> bool:
    if valid_at is not None:
        valid_from = parse_iso_temporal(context.get("valid_from", ""))
        valid_until = parse_iso_temporal(context.get("valid_until", ""))
        if valid_from is None and valid_until is None:
            return False
        if valid_from is not None and valid_at < valid_from:
            return False
        if valid_until is not None and valid_at > valid_until:
            return False

    if observed_since is not None or observed_until is not None:
        observed_at = parse_iso_temporal(context.get("observed_at", ""))
        if observed_at is None:
            return False
        if observed_since is not None and observed_at < observed_since:
            return False
        if observed_until is not None and observed_at > observed_until:
            return False

    return True


def _edge_query_summary(edge: Edge, store: BeliefStore, temporal_contexts: list[dict[str, str]]) -> dict[str, Any]:
    source = _edge_endpoint_summary(store, edge.src_id)
    target = _edge_endpoint_summary(store, edge.dst_id)
    return {
        "edge_type": edge.edge_type,
        "source": source,
        "target": target,
        "source_belief_id": edge.src_id,
        "target_belief_id": edge.dst_id,
        "status": "open" if source["status"] == "open" and target["status"] == "open" else "dangling",
        "provenance": list(edge.provenance),
        "created_at": edge.created_at.isoformat(),
        "temporal_contexts": [dict(context) for context in temporal_contexts],
    }


def temporal_edges(
    store: BeliefStore,
    *,
    valid_at: str | datetime | None = None,
    observed_since: str | datetime | None = None,
    observed_until: str | datetime | None = None,
    edge_type: str = "",
    belief_ref: str = "",
    limit: int = _DEFAULT_TEMPORAL_EDGE_LIMIT,
    expert_name: str = "",
) -> dict[str, Any]:
    """List temporal edge qualifiers, optionally filtered by valid/observed time.

    This is a read-only query over persisted typed belief-graph edges. It
    filters edge-level temporal qualifiers, not belief timestamps: ``valid_at``
    asks whether the edge relationship was valid at an instant, while
    ``observed_since`` / ``observed_until`` constrain when that qualified
    relationship was observed.
    """
    valid_at_dt = _parse_filter_time("valid_at", valid_at)
    observed_since_dt = _parse_filter_time("observed_since", observed_since)
    observed_until_dt = _parse_filter_time("observed_until", observed_until)
    if observed_since_dt is not None and observed_until_dt is not None and observed_since_dt > observed_until_dt:
        raise ValueError("observed_since must be earlier than or equal to observed_until")

    edge_type = edge_type.strip()
    if edge_type and edge_type not in EDGE_TYPES:
        raise ValueError(f"edge_type must be one of {', '.join(EDGE_TYPES)}")

    bounded_limit = max(1, min(int(limit), _MAX_TEMPORAL_EDGE_LIMIT))
    resolved_belief = _resolve_belief(store, belief_ref.strip()) if belief_ref.strip() else None
    if belief_ref.strip() and resolved_belief is None:
        matched_edges: list[dict[str, Any]] = []
    else:
        source_edges = (
            store.edges_for(resolved_belief.id) if resolved_belief is not None else list(store.edges.values())
        )
        filters_active = _temporal_filter_active(valid_at_dt, observed_since_dt, observed_until_dt)
        matched_edges = []
        for edge in sorted(source_edges, key=lambda item: (item.edge_type, item.src_id, item.dst_id)):
            if edge_type and edge.edge_type != edge_type:
                continue
            if not edge.temporal_contexts:
                continue
            contexts = _edge_temporal_contexts(edge)
            if filters_active:
                contexts = [
                    context
                    for context in contexts
                    if _context_matches_temporal_filters(
                        context,
                        valid_at=valid_at_dt,
                        observed_since=observed_since_dt,
                        observed_until=observed_until_dt,
                    )
                ]
            if contexts:
                matched_edges.append(_edge_query_summary(edge, store, contexts))

    filters = {
        "valid_at": valid_at_dt.isoformat() if valid_at_dt is not None else "",
        "observed_since": observed_since_dt.isoformat() if observed_since_dt is not None else "",
        "observed_until": observed_until_dt.isoformat() if observed_until_dt is not None else "",
        "edge_type": edge_type,
        "belief_ref": belief_ref,
        "limit": bounded_limit,
    }
    return {
        "expert_name": expert_name or store.expert_name,
        "filters": filters,
        "matched_belief": _belief_summary(resolved_belief) if resolved_belief is not None else None,
        "total_edges": len(matched_edges),
        "returned_edges": len(matched_edges[:bounded_limit]),
        "edges": matched_edges[:bounded_limit],
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _belief_summary(belief: Belief, store: BeliefStore | None = None) -> dict[str, Any]:
    """Compact, consumer-facing snapshot of one belief."""
    summary: dict[str, Any] = {
        "belief_id": belief.id,
        "claim": belief.claim,
        "confidence": round(belief.get_current_confidence(), 3),
        "source_type": belief.source_type,
        "trust_class": belief.trust_class,
        "evidence_refs": list(belief.evidence_refs),
        "updated_at": belief.updated_at.isoformat(),
        "contradictions_with": list(belief.contradictions_with),
    }
    if store is not None:
        temporal_edges = _temporal_edges_for_belief(store, belief.id)
        if temporal_edges:
            summary["temporal_edges"] = temporal_edges
    return summary


@dataclass
class PerspectiveDelta:
    """What an expert's perspective did since a point in time."""

    expert_name: str
    since: datetime
    added: list[dict[str, Any]] = field(default_factory=list)
    revised: list[dict[str, Any]] = field(default_factory=list)
    contested: list[dict[str, Any]] = field(default_factory=list)
    archived: list[dict[str, Any]] = field(default_factory=list)
    window_truncated: bool = False
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.revised) + len(self.contested) + len(self.archived)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "since": self.since.isoformat(),
            "total_changes": self.total_changes,
            "added": self.added,
            "revised": self.revised,
            "contested": self.contested,
            "archived": self.archived,
            "window_truncated": self.window_truncated,
            "window_note": (
                "Change history is bounded (last 100 records); earlier changes in the requested "
                "range are not included. Re-baseline with a full belief read."
                if self.window_truncated
                else ""
            ),
            "generated_at": self.generated_at.isoformat(),
        }


def what_changed(store: BeliefStore, since: datetime, *, expert_name: str = "") -> PerspectiveDelta:
    """Compute the perspective delta since ``since``.

    Buckets persisted ``BeliefChange`` records strictly after ``since``:

    - ``contested``: creations recorded by ``add_contested_belief`` (the
      contradiction-as-signal path) - new claims that conflict with an
      existing belief and are stored with contradiction edges.
    - ``added``: ordinary belief creations.
    - ``revised``: updates/revisions to existing beliefs (old claim and
      confidence included when recorded).
    - ``archived``: beliefs retired from the store.

    Each entry carries the change reason and, when the belief still exists,
    a current snapshot - so a consumer can act on the delta without a second
    round trip.
    """
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)

    delta = PerspectiveDelta(expert_name=expert_name or store.expert_name, since=since)

    if store.has_event_log:
        # Append-only event log: unbounded, so the delta is exact - no
        # truncation possible. (iter_events already filters strictly-after.)
        changes = store.iter_events(since)
    else:
        # Legacy store: bounded window. If the oldest retained record is
        # newer than `since`, older changes in the requested range were
        # dropped.
        changes = list(store.changes)
        if changes and min(c.timestamp for c in changes) > since and len(changes) >= 100:
            delta.window_truncated = True

    for change in changes:
        ts = change.timestamp if change.timestamp.tzinfo else change.timestamp.replace(tzinfo=UTC)
        if ts <= since:
            continue

        # The host-facing confidence must be the trust-floored *effective* value
        # (get_current_confidence), never the extractor's raw self-rating: a
        # tertiary web-sourced belief caps at 0.60/0.80 no matter what the model
        # claimed, and every other read surface (digest, okf, perspective, why)
        # already shows the floored value. Fall back to the recorded change value
        # only for archived beliefs, where there is no live belief left to floor.
        current = store.beliefs.get(change.belief_id)
        effective_confidence = current.get_current_confidence() if current is not None else change.new_confidence
        entry: dict[str, Any] = {
            "belief_id": change.belief_id,
            "claim": change.new_claim,
            "confidence": round(effective_confidence, 3),
            "reason": change.reason,
            "timestamp": ts.isoformat(),
        }
        if current is not None:
            entry["current"] = _belief_summary(current, store)

        if change.change_type == "created" and change.reason.startswith(_CONTESTED_REASON_PREFIX):
            delta.contested.append(entry)
        elif change.change_type == "created":
            delta.added.append(entry)
        elif change.change_type in ("updated", "revised"):
            if change.old_claim:
                entry["old_claim"] = change.old_claim
            entry["old_confidence"] = round(change.old_confidence, 3)
            delta.revised.append(entry)
        elif change.change_type == "archived":
            delta.archived.append(entry)
        else:  # unknown change types stay visible rather than silently dropped
            entry["change_type"] = change.change_type
            delta.revised.append(entry)

    return delta


@dataclass
class BeliefExplanation:
    """Why an expert believes something: evidence, history, and graph context.

    The third temporal query (``deepr expert why`` / ``deepr_explain_belief``):
    introspection over a single belief. Built entirely from persisted
    structures - evidence_refs (provenance roots), the append-only event log
    (confidence trajectory), and typed edges (support/contradiction chains) -
    so it stays read-side and cost-$0 like the rest of the query surface.
    """

    expert_name: str
    belief: dict[str, Any]
    evidence_roots: list[str] = field(default_factory=list)
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    supports: list[dict[str, Any]] = field(default_factory=list)
    derived_from: list[dict[str, Any]] = field(default_factory=list)
    contradicts: list[dict[str, Any]] = field(default_factory=list)
    depth: int = 2
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "belief": self.belief,
            "evidence_roots": self.evidence_roots,
            "trajectory": self.trajectory,
            "supports": self.supports,
            "derived_from": self.derived_from,
            "contradicts": self.contradicts,
            "depth": self.depth,
            "generated_at": self.generated_at.isoformat(),
        }


_WORD_PUNCT = ".,;:!?'\"()[]{}"


def _resolve_belief(store: BeliefStore, belief_ref: str) -> Belief | None:
    """Resolve a belief by exact id, then by best claim-text match.

    Matching scores how much of the QUERY the claim covers (not symmetric
    overlap - a short query against a long claim must still match), with
    punctuation stripped and prefix tolerance for plurals/inflections
    ("tool" matches "tools,"). Live finding 2026-06-11: the symmetric
    score rejected "dynamic tool discovery" against the exact belief it
    described because the claim sentence was long.
    """
    exact = store.beliefs.get(belief_ref)
    if exact is not None:
        return exact

    ref_words = {w.strip(_WORD_PUNCT) for w in belief_ref.lower().split()} - {""}
    if not ref_words:
        return None

    best: tuple[float, Belief] | None = None
    for belief in store.beliefs.values():
        claim_words = {w.strip(_WORD_PUNCT) for w in belief.claim.lower().split()} - {""}
        matched = 0
        for rw in ref_words:
            if rw in claim_words:
                matched += 1
            elif len(rw) > 3 and any((cw.startswith(rw) or rw.startswith(cw)) and len(cw) > 3 for cw in claim_words):
                matched += 1  # prefix tolerance: tool/tools, graph/graphs
        coverage = matched / len(ref_words)
        if coverage >= 0.6 and (best is None or coverage > best[0]):
            best = (coverage, belief)
    return best[1] if best else None


def explain_belief(
    store: BeliefStore,
    belief_ref: str,
    *,
    expert_name: str = "",
    depth: int = 2,
) -> BeliefExplanation | None:
    """Explain one belief: provenance, confidence history, and graph chains.

    Args:
        store: The expert's belief store.
        belief_ref: Belief id, or claim text to fuzzy-match (>0.3 overlap).
        expert_name: Display name (defaults to the store's).
        depth: Max hops to walk along supports/derived_from chains (the
            contradicts list is direct neighbors only - a contradiction two
            hops away is not a contradiction of THIS belief).

    Returns:
        BeliefExplanation, or None when no belief matches ``belief_ref``.
    """
    belief = _resolve_belief(store, belief_ref)
    if belief is None:
        return None

    explanation = BeliefExplanation(
        expert_name=expert_name or store.expert_name,
        belief=_belief_summary(belief, store),
        evidence_roots=list(belief.evidence_refs),
        depth=max(1, depth),
    )

    # Confidence trajectory from the append-only event log (exact); legacy
    # stores without the log fall back to the bounded changes window.
    events = store.iter_events() if store.has_event_log else list(store.changes)
    for change in events:
        if change.belief_id != belief.id:
            continue
        ts = change.timestamp if change.timestamp.tzinfo else change.timestamp.replace(tzinfo=UTC)
        entry: dict[str, Any] = {
            "change_type": change.change_type,
            "confidence": round(change.new_confidence, 3),
            "reason": change.reason,
            "timestamp": ts.isoformat(),
        }
        if change.old_claim and change.old_claim != change.new_claim:
            entry["old_claim"] = change.old_claim
        explanation.trajectory.append(entry)

    # Walk supports/derived_from chains breadth-first, depth-bounded and
    # cycle-safe. Each entry records the edge's provenance and how many
    # hops from the root it sits.
    visited: set[str] = {belief.id}
    frontier = [(belief.id, 0)]
    while frontier:
        current_id, level = frontier.pop(0)
        if level >= explanation.depth:
            continue
        for edge in store.edges_for(current_id):
            other_id = edge.dst_id if edge.src_id == current_id else edge.src_id
            if edge.edge_type == "contradicts":
                # Direct neighbors only - record once, from the root belief
                if current_id == belief.id and other_id not in {c["belief_id"] for c in explanation.contradicts}:
                    other = store.beliefs.get(other_id)
                    entry = {
                        "edge_type": edge.edge_type,
                        "belief_id": other_id,
                        "claim": other.claim if other else "",
                        "confidence": round(other.get_current_confidence(), 3) if other else None,
                        "provenance": list(edge.provenance),
                        "verification": contradiction_verification(edge),
                        "status": "open" if other is not None else "dangling",
                    }
                    if edge.temporal_contexts:
                        entry["temporal_contexts"] = _edge_temporal_contexts(edge)
                    explanation.contradicts.append(entry)
                continue
            if other_id in visited:
                continue
            visited.add(other_id)
            other = store.beliefs.get(other_id)
            entry = {
                "edge_type": edge.edge_type,
                "belief_id": other_id,
                "claim": other.claim if other else "",
                "confidence": round(other.get_current_confidence(), 3) if other else None,
                "evidence_refs": list(other.evidence_refs) if other else [],
                "provenance": list(edge.provenance),
                "hops": level + 1,
            }
            if edge.temporal_contexts:
                entry["temporal_contexts"] = _edge_temporal_contexts(edge)
            bucket = explanation.derived_from if edge.edge_type == "derived_from" else explanation.supports
            bucket.append(entry)
            frontier.append((other_id, level + 1))

    return explanation


@dataclass
class ContestedPair:
    """One recorded contradiction candidate, with verification assurance."""

    a: dict[str, Any]
    b: dict[str, Any]
    status: str  # "open" | "dangling" (one side no longer in the store)
    verification: str = "unverified"
    provenance: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "a": self.a,
            "b": self.b,
            "status": self.status,
            "verification": self.verification,
            "provenance": list(self.provenance),
        }


def contested(store: BeliefStore, *, expert_name: str = "") -> dict[str, Any]:
    """List recorded contradiction candidates with assurance and provenance.

    Pure read over the ``contradictions_with`` edges. A pair is ``open`` when
    both beliefs are still in the store; ``dangling`` when one side has been
    removed (its id is reported so the stale edge can be cleaned up by
    maintenance). Resolution belongs to ``expert resolve-conflicts`` - this
    query only makes the candidates visible. ``verification`` describes the
    recorded process, not an independent semantic correctness verdict.
    """
    pairs: list[ContestedPair] = []
    seen: set[tuple[str, str]] = set()

    for belief in store.beliefs.values():
        for other_id in belief.contradictions_with:
            key = (min(belief.id, other_id), max(belief.id, other_id))
            if key in seen:
                continue
            seen.add(key)

            other = store.beliefs.get(other_id)
            edge = store.edges.get((key[0], key[1], "contradicts"))
            verification = contradiction_verification(edge) if edge is not None else "unverified"
            provenance = list(edge.provenance) if edge is not None else []
            if other is not None:
                pairs.append(
                    ContestedPair(
                        a=_belief_summary(belief, store),
                        b=_belief_summary(other, store),
                        status="open",
                        verification=verification,
                        provenance=provenance,
                    )
                )
            else:
                pairs.append(
                    ContestedPair(
                        a=_belief_summary(belief, store),
                        b={"belief_id": other_id, "claim": "", "note": "no longer in store"},
                        status="dangling",
                        verification=verification,
                        provenance=provenance,
                    )
                )

    confirmed_count = sum(1 for pair in pairs if pair.verification == "model_confirmed")
    return {
        "expert_name": expert_name or store.expert_name,
        "contested_count": len(pairs),
        "open_count": sum(1 for p in pairs if p.status == "open"),
        "model_confirmed_count": confirmed_count,
        "unverified_count": len(pairs) - confirmed_count,
        "pairs": [p.to_dict() for p in pairs],
        "generated_at": datetime.now(UTC).isoformat(),
    }
