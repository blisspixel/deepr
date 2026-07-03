"""Deterministic, $0, no-model route explanation for `deepr route explain`.

Answers "if I asked this, which experts get consulted, and will it cost money?"
BEFORE anything is dispatched. It renders only deterministic FORM signals - the
keyword-overlap selection router (a high-recall candidate picker, never a verdict
on which expert is right) and the non-probing admitted-capacity outlook ($0 local
/ prepaid plan vs metered) - so an operator can inspect the route and its spend
posture without an LLM call. This is the "workflow enforces and explains the
threshold" side of AGENTIC_BALANCE, not a meaning judgment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deepr.experts.expert_routing import MAX_ROUTED_EXPERTS, score_experts_for_query, select_top_experts
from deepr.experts.loop_capacity_outlook import build_capacity_outlook
from deepr.security.output_safety import sanitize_host_facing_payload

ROUTE_EXPLANATION_SCHEMA_VERSION = "deepr-route-explanation-v1"
ROUTE_EXPLANATION_KIND = "deepr.route.explanation"

# The cheapest-first backend order the capacity waterfall walks for maintenance
# work, shown so the fallback chain is explicit before any dispatch.
BACKEND_FALLBACK_ORDER = ("local ($0)", "plan-quota (prepaid)", "metered API")

_ROUTER_NOTE = (
    "Keyword overlap is a high-recall selection router, not a judgment of which "
    "expert is authoritative or whether the answer will be correct. Zero-overlap "
    "fallbacks are still shown so a consult is never starved of experts."
)


def build_route_explanation(
    query: str,
    *,
    max_experts: int = 3,
    top_n: int = 5,
    admissions_path: Path | None = None,
) -> dict[str, Any]:
    """Explain how a query would route, deterministically and at $0 (no model call).

    Returns a schema-versioned payload with the keyword-overlap expert routing
    (which experts would be consulted and why, plus lower-ranked candidates) and
    the non-probing capacity outlook (whether the next maintenance run of each
    task class has cheap capacity admitted or would fall to metered budget).
    """
    if max_experts < 1:
        raise ValueError("max_experts must be positive")
    if top_n < 1:
        raise ValueError("top_n must be positive")

    from deepr.experts.profile import ExpertStore

    experts = ExpertStore().list_all()
    scored = score_experts_for_query(query, experts)
    would_consult_names = {entry["name"] for entry in select_top_experts(scored, max_experts=max_experts)}

    candidates = [
        {
            "name": score.name,
            "domain": score.domain,
            "overlap_score": score.score,
            "matched_terms": list(score.matched_terms),
            "would_consult": score.name in would_consult_names,
        }
        for score in scored[:top_n]
    ]

    payload: dict[str, Any] = {
        "schema_version": ROUTE_EXPLANATION_SCHEMA_VERSION,
        "kind": ROUTE_EXPLANATION_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "no_model_call": True,
            "routing_only": True,
            "stability": "experimental",
            "compatibility": {
                "additive_fields": True,
                "breaking_changes_require_new_schema_version": True,
                "deprecation_policy": "Fields in this v1 payload are additive within v1; removals use a new schema.",
            },
        },
        "query": query,
        "expert_routing": {
            "method": "keyword_overlap",
            "note": _ROUTER_NOTE,
            "expert_count": len(experts),
            "max_experts": min(max_experts, MAX_ROUTED_EXPERTS),
            "would_consult": sorted(would_consult_names),
            "candidates": candidates,
        },
        "capacity_outlook": build_capacity_outlook(admissions_path=admissions_path),
        "backend_fallback_order": list(BACKEND_FALLBACK_ORDER),
    }
    return sanitize_host_facing_payload(payload, source_label=f"route explanation: {query}")


__all__ = [
    "BACKEND_FALLBACK_ORDER",
    "ROUTE_EXPLANATION_KIND",
    "ROUTE_EXPLANATION_SCHEMA_VERSION",
    "build_route_explanation",
]
