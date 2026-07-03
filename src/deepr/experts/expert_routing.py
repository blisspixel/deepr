"""Deterministic keyword-overlap router for selecting experts for a query.

This is a high-recall SELECTION router, never a meaning verdict (AGENTIC_BALANCE):
keyword overlap between a query and an expert's domain/description picks candidate
experts to consult; it never concludes which expert is authoritative or whether an
answer will be correct. It is shared by the council's auto-selection and by
`deepr route explain` so both act on and explain the same deterministic signal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+\-.]*")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "should",
        "that",
        "the",
        "this",
        "to",
        "we",
        "what",
        "when",
        "where",
        "why",
        "with",
    }
)

# Upper bound on auto-fan-out experts per consult, shared with the council. Keeps
# a wide selection from padding a consult with irrelevant experts. Parallel
# dispatch is separately bounded by MAX_COUNCIL_CONCURRENCY, so a 10-expert
# fan-out runs in concurrency-sized waves rather than 10 at once.
MAX_ROUTED_EXPERTS = 10


def route_terms(text: str) -> set[str]:
    """Tokenize text for retrieval routing only, never as a truth verdict."""
    terms: set[str] = set()
    for term in _TOKEN_RE.findall(text.lower()):
        if len(term) <= 2 or term in _STOPWORDS:
            continue
        terms.add(term)
        if term.endswith("s") and len(term) > 4:
            terms.add(term[:-1])
        if term == "agentic":
            terms.add("agent")
    return terms


@dataclass(frozen=True)
class ExpertRouteScore:
    """One expert's keyword-overlap routing score for a query.

    ``score`` is the count of shared terms - a router signal for selection, not a
    ranking of answer quality or authority.
    """

    name: str
    domain: str
    score: int
    matched_terms: tuple[str, ...]


def score_experts_for_query(
    query: str, experts: list[Any], *, exclude: set[str] | None = None
) -> list[ExpertRouteScore]:
    """Rank experts by query/domain keyword overlap, descending. Router only.

    Each expert is scored by the number of query terms that also appear in its
    ``name``/``domain``/``description``. The ordering routes selection; it never
    concludes which expert is right (AGENTIC_BALANCE).
    """
    excluded = exclude or set()
    query_words = route_terms(query)
    scored: list[ExpertRouteScore] = []
    for exp in experts:
        name = exp.name
        if name in excluded:
            continue
        domain = getattr(exp, "domain", "") or ""
        description = getattr(exp, "description", "") or ""
        expert_words = route_terms(f"{name} {domain} {description}")
        matched = query_words & expert_words
        scored.append(
            ExpertRouteScore(name=name, domain=domain, score=len(matched), matched_terms=tuple(sorted(matched)))
        )
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def select_top_experts(scored: list[ExpertRouteScore], *, max_experts: int) -> list[dict]:
    """Apply the relevant-else-fallback selection over ranked scores.

    Prefer experts with any overlap so a wide fan-out does not pad the council
    with irrelevant experts; fall back to the top scorers when nothing overlaps
    so a consult is never starved. Caps at ``max_experts`` bounded by
    ``MAX_ROUTED_EXPERTS``. Returns ``{"name", "domain"}`` dicts in ranked order.
    """
    limit = min(max_experts, MAX_ROUTED_EXPERTS)
    relevant = [s for s in scored if s.score > 0]
    chosen = relevant if relevant else scored
    return [{"name": s.name, "domain": s.domain} for s in chosen[:limit]]


__all__ = [
    "MAX_ROUTED_EXPERTS",
    "ExpertRouteScore",
    "route_terms",
    "score_experts_for_query",
    "select_top_experts",
]
