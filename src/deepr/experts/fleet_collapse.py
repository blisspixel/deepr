"""$0 automatic-consult collapse telemetry.

Neural MoE papers name expert collapse: a few shards take almost all traffic.
Deepr's analog is automatic consult routing concentrating on a few name-overlapping
experts. This module measures that load. It never concludes which expert is
right, whether the answer was good, or that routing defaults should change.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from deepr.experts.expert_routing import (
    MAX_ROUTED_EXPERTS,
    score_experts_for_query,
    select_top_experts,
)

ROUTE_COLLAPSE_SCHEMA_VERSION = "deepr-route-collapse-v1"
ROUTE_COLLAPSE_KIND = "deepr.route.collapse"
_MAX_SCORES = 20


def _contract() -> dict[str, Any]:
    return {
        "read_only": True,
        "cost_usd": 0.0,
        "no_model_call": True,
        "routing_only": True,
        "quality_verdict": False,
        "routing_default_unchanged": True,
    }


def shannon_entropy(counts: Mapping[str, int]) -> float:
    """Shannon entropy in bits over a selection histogram."""
    total = sum(int(value) for value in counts.values() if int(value) > 0)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for value in counts.values():
        count = int(value)
        if count <= 0:
            continue
        probability = count / total
        entropy -= probability * math.log2(probability)
    return entropy


def _selected_names(trace: Mapping[str, Any]) -> tuple[str, ...]:
    packet = trace.get("context_packet") if isinstance(trace.get("context_packet"), dict) else {}
    always = packet.get("always") if isinstance(packet.get("always"), dict) else {}
    names = always.get("experts_consulted")
    if not isinstance(names, list) or not names:
        output = trace.get("output") if isinstance(trace.get("output"), dict) else {}
        names = output.get("experts_consulted")
    if not isinstance(names, list):
        return ()
    cleaned = [str(name).strip() for name in names if str(name).strip()]
    return tuple(cleaned)


def _is_automatic(trace: Mapping[str, Any]) -> bool:
    payload = trace.get("input") if isinstance(trace.get("input"), dict) else {}
    return str(payload.get("selection_mode") or "") == "automatic"


def observe_automatic_routing(
    question: str,
    *,
    selected: Sequence[str],
    max_experts: int,
    experts: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Snapshot the current overlap router for one automatic consult.

    Form only: overlap scores and whether every expert scored zero (the recency
    fallback). Not a quality or authority verdict.
    """
    roster = list(experts) if experts is not None else _load_roster()
    scored = score_experts_for_query(question, roster)
    selected_set = {str(name).strip() for name in selected if str(name).strip()}
    recency_fallback = bool(scored) and all(item.score == 0 for item in scored)
    return {
        "method": "keyword_overlap",
        "recency_fallback": recency_fallback,
        "scores": [
            {
                "name": item.name,
                "overlap_score": item.score,
                "matched_terms": list(item.matched_terms),
                "selected": item.name in selected_set,
            }
            for item in scored[:_MAX_SCORES]
        ],
        "max_experts": min(int(max_experts), MAX_ROUTED_EXPERTS),
    }


def _load_roster() -> list[Any]:
    from deepr.experts.profile import ExpertStore

    return list(ExpertStore().list_all())


def _flagship_names(roster: Iterable[Any]) -> set[str]:
    names: set[str] = set()
    for expert in roster:
        name = str(getattr(expert, "name", "") or "").strip()
        if name and str(getattr(expert, "roster_tier", "standard") or "standard") == "flagship":
            names.add(name)
    return names


def _replay_selected(question: str, max_experts: int, roster: Sequence[Any]) -> set[str]:
    scored = score_experts_for_query(question, list(roster))
    chosen = select_top_experts(scored, max_experts=max_experts)
    return {str(item.get("name") or "").strip() for item in chosen if str(item.get("name") or "").strip()}


def build_route_collapse_report(
    traces: Sequence[Mapping[str, Any]],
    *,
    roster: Sequence[Any] | None = None,
    replay: bool = True,
) -> dict[str, Any]:
    """Measure automatic-consult concentration. Not a quality verdict."""
    current_roster = list(roster) if roster is not None else _load_roster()
    flagship = _flagship_names(current_roster)
    frequencies: Counter[str] = Counter()
    automatic = 0
    recency_known = 0
    recency_fallback = 0
    replayed = 0
    replay_disagreements = 0
    for trace in traces:
        if not isinstance(trace, Mapping) or not _is_automatic(trace):
            continue
        names = _selected_names(trace)
        if not names:
            continue
        automatic += 1
        frequencies.update(names)
        payload = trace.get("input") if isinstance(trace.get("input"), dict) else {}
        routing = payload.get("routing") if isinstance(payload.get("routing"), dict) else {}
        if "recency_fallback" in routing:
            recency_known += 1
            if routing.get("recency_fallback") is True:
                recency_fallback += 1
        if replay and current_roster:
            question = str(payload.get("question") or "")
            max_experts = int(payload.get("max_experts") or payload.get("requested_max_experts") or 3)
            if question:
                replayed += 1
                current = _replay_selected(question, max_experts, current_roster)
                if current != set(names):
                    replay_disagreements += 1

    total_selections = sum(frequencies.values())
    unique = len(frequencies)
    roster_size = len(current_roster)
    top = frequencies.most_common()
    top1 = (top[0][1] / total_selections) if top and total_selections else 0.0
    top3 = (sum(count for _, count in top[:3]) / total_selections) if total_selections else 0.0
    entropy = shannon_entropy(frequencies)
    max_entropy = math.log2(unique) if unique > 1 else 0.0
    flagship_selections = sum(count for name, count in frequencies.items() if name in flagship)
    return {
        "schema_version": ROUTE_COLLAPSE_SCHEMA_VERSION,
        "kind": ROUTE_COLLAPSE_KIND,
        "contract": _contract(),
        "automatic_consults": automatic,
        "selection_events": total_selections,
        "unique_experts_selected": unique,
        "roster_size": roster_size,
        "unique_share": (unique / roster_size) if roster_size else 0.0,
        "top1_share": top1,
        "top3_share": top3,
        "entropy_bits": entropy,
        "max_entropy_bits": max_entropy,
        "recency_fallback_known": recency_known,
        "recency_fallback_count": recency_fallback,
        "replayed": replayed,
        "replay_disagreements": replay_disagreements,
        "flagship_selection_share": (flagship_selections / total_selections) if total_selections else 0.0,
        "flagship_is_label_only": True,
        "frequencies": [
            {
                "name": name,
                "count": count,
                "share": (count / total_selections) if total_selections else 0.0,
                "roster_tier": "flagship" if name in flagship else "standard",
            }
            for name, count in top
        ],
        "note": (
            "Routing-load report over automatic consult traces. Keyword overlap is a "
            "high-recall selector, not a quality or authority verdict. Flagship is a "
            "presentation label, not a routing prior. This report does not change defaults."
        ),
    }


__all__ = [
    "ROUTE_COLLAPSE_KIND",
    "ROUTE_COLLAPSE_SCHEMA_VERSION",
    "build_route_collapse_report",
    "observe_automatic_routing",
    "shannon_entropy",
]
