"""Candidate recall for expert beliefs and concepts.

Recall is routing, not judgment. A recall hit says "inspect this item next";
it does not say two items are the same claim, that one supports another, or
that they contradict. Semantic verdicts stay with calibrated model checks and
graph commit gates.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.+#][a-z0-9]+)*")
VECTOR_METHOD = "vector_similarity"
LEXICAL_METHOD = "lexical_router"
CANDIDATE_ONLY = "candidate_only"

_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "with",
}


@dataclass(frozen=True)
class RecallItem:
    """A text-bearing memory object that can be routed for later inspection."""

    item_id: str
    text: str
    kind: str
    domain: str = ""
    payload: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecallCandidate:
    """A retrieved item that needs a downstream verifier before any conclusion."""

    item_id: str
    text: str
    kind: str
    score: float
    method: str
    domain: str = ""
    matched_terms: tuple[str, ...] = ()
    payload: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    verdict: str = CANDIDATE_ONLY
    guidance: str = "routing_only"

    def to_dict(self) -> dict[str, Any]:
        """Serialize public candidate metadata without embedding the payload."""
        return {
            "item_id": self.item_id,
            "kind": self.kind,
            "domain": self.domain,
            "score": self.score,
            "method": self.method,
            "matched_terms": list(self.matched_terms),
            "metadata": self.metadata,
            "verdict": self.verdict,
            "guidance": self.guidance,
        }


def tokenize_for_recall(text: str) -> tuple[str, ...]:
    """Normalize recall terms for a cheap candidate router."""
    return tuple(token for token in TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS)


def _lexical_score(query: str, text: str) -> tuple[float, tuple[str, ...]]:
    query_terms = set(tokenize_for_recall(query))
    item_terms = set(tokenize_for_recall(text))
    if not query_terms or not item_terms:
        return 0.0, ()
    matched = tuple(sorted(query_terms & item_terms))
    if not matched:
        return 0.0, ()
    precision = len(matched) / len(item_terms)
    recall = len(matched) / len(query_terms)
    score = (2 * precision * recall) / (precision + recall)
    return round(score, 6), matched


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float | None:
    if not left or len(left) != len(right):
        return None
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for left_value, right_value in zip(left, right):
        dot += left_value * right_value
        left_norm += left_value * left_value
        right_norm += right_value * right_value
    denominator = math.sqrt(left_norm) * math.sqrt(right_norm)
    if denominator == 0.0:
        return None
    return max(-1.0, min(1.0, dot / denominator))


def _vector_score(
    item_id: str,
    *,
    query_embedding: Sequence[float] | None,
    item_embeddings: Mapping[str, Sequence[float]] | None,
) -> float | None:
    if query_embedding is None or item_embeddings is None:
        return None
    item_embedding = item_embeddings.get(item_id)
    if item_embedding is None:
        return None
    cosine = _cosine_similarity(query_embedding, item_embedding)
    if cosine is None:
        return None
    return round((cosine + 1.0) / 2.0, 6)


def recall_items(
    query: str,
    items: Iterable[RecallItem],
    *,
    top_k: int = 5,
    min_score: float = 0.0,
    query_embedding: Sequence[float] | None = None,
    item_embeddings: Mapping[str, Sequence[float]] | None = None,
    include_lexical_fallback: bool = True,
) -> list[RecallCandidate]:
    """Return candidate items for later verifier or graph inspection.

    If embeddings are supplied, vector similarity is used locally over the
    provided vectors. This function never computes embeddings and never calls a
    provider. Items without vectors can optionally fall back to the lexical
    router, still with `candidate_only` semantics.
    """
    if top_k <= 0:
        return []

    candidates: list[RecallCandidate] = []
    threshold = max(0.0, min_score)
    for item in items:
        vector_score = _vector_score(
            item.item_id,
            query_embedding=query_embedding,
            item_embeddings=item_embeddings,
        )
        lexical_score, matched_terms = _lexical_score(query, item.text)
        method = VECTOR_METHOD
        score = vector_score
        if score is None:
            if not include_lexical_fallback:
                continue
            method = LEXICAL_METHOD
            score = lexical_score

        if score <= threshold:
            continue
        candidates.append(
            RecallCandidate(
                item_id=item.item_id,
                text=item.text,
                kind=item.kind,
                domain=item.domain,
                score=score,
                method=method,
                matched_terms=matched_terms,
                payload=item.payload,
                metadata=item.metadata,
            )
        )

    candidates.sort(key=lambda candidate: (-candidate.score, candidate.kind, candidate.item_id))
    return candidates[:top_k]


def belief_recall_items(beliefs: Iterable[Any]) -> list[RecallItem]:
    """Adapt belief-like objects into recall items without importing Belief."""
    items: list[RecallItem] = []
    for belief in beliefs:
        claim = str(getattr(belief, "claim", "") or "")
        belief_id = str(getattr(belief, "id", "") or "")
        if not claim or not belief_id:
            continue
        domain = str(getattr(belief, "domain", "") or "")
        items.append(
            RecallItem(
                item_id=belief_id,
                text=claim,
                kind="belief",
                domain=domain,
                payload=belief,
                metadata={
                    "confidence": getattr(belief, "confidence", None),
                    "source_type": getattr(belief, "source_type", ""),
                    "grounding_assurance": getattr(belief, "grounding_assurance", ""),
                },
            )
        )
    return items


def concept_recall_items(concepts: Iterable[Any]) -> list[RecallItem]:
    """Adapt concept-like objects into recall items without owning the graph."""
    items: list[RecallItem] = []
    for concept in concepts:
        text = str(getattr(concept, "text", "") or "")
        concept_id = str(getattr(concept, "id", "") or "")
        if not text or not concept_id:
            continue
        items.append(
            RecallItem(
                item_id=concept_id,
                text=text,
                kind="concept",
                payload=concept,
                metadata={
                    "concept_type": getattr(concept, "concept_type", ""),
                    "frequency": getattr(concept, "frequency", None),
                    "tf_idf_score": getattr(concept, "tf_idf_score", None),
                },
            )
        )
    return items


def recall_belief_candidates(
    query: str,
    beliefs: Iterable[Any],
    *,
    top_k: int = 5,
    min_score: float = 0.0,
    domain: str | None = None,
    query_embedding: Sequence[float] | None = None,
    belief_embeddings: Mapping[str, Sequence[float]] | None = None,
    include_lexical_fallback: bool = True,
) -> list[RecallCandidate]:
    """Return belief candidates for verifier routing only."""
    items = belief_recall_items(beliefs)
    if domain is not None:
        items = [item for item in items if item.domain == domain]
    return recall_items(
        query,
        items,
        top_k=top_k,
        min_score=min_score,
        query_embedding=query_embedding,
        item_embeddings=belief_embeddings,
        include_lexical_fallback=include_lexical_fallback,
    )


def recall_concept_candidates(
    query: str,
    concepts: Iterable[Any],
    *,
    top_k: int = 5,
    min_score: float = 0.0,
    query_embedding: Sequence[float] | None = None,
    concept_embeddings: Mapping[str, Sequence[float]] | None = None,
    include_lexical_fallback: bool = True,
) -> list[RecallCandidate]:
    """Return concept candidates for context routing only."""
    return recall_items(
        query,
        concept_recall_items(concepts),
        top_k=top_k,
        min_score=min_score,
        query_embedding=query_embedding,
        item_embeddings=concept_embeddings,
        include_lexical_fallback=include_lexical_fallback,
    )


def _store_recall_belief_candidates(
    self: Any,
    query: str,
    *,
    top_k: int = 5,
    min_score: float = 0.0,
    domain: str | None = None,
    query_embedding: Sequence[float] | None = None,
    belief_embeddings: Mapping[str, Sequence[float]] | None = None,
    include_lexical_fallback: bool = True,
) -> list[RecallCandidate]:
    """BeliefStore-compatible wrapper for local recall routing."""
    return recall_belief_candidates(
        query,
        self.beliefs.values(),
        top_k=top_k,
        min_score=min_score,
        domain=domain,
        query_embedding=query_embedding,
        belief_embeddings=belief_embeddings,
        include_lexical_fallback=include_lexical_fallback,
    )


def _store_recall_contradiction_candidates(
    self: Any,
    belief: Any,
    *,
    top_k: int = 8,
    min_score: float = 0.0,
    query_embedding: Sequence[float] | None = None,
    belief_embeddings: Mapping[str, Sequence[float]] | None = None,
    include_lexical_fallback: bool = True,
) -> list[RecallCandidate]:
    """Return same-domain candidates; a verifier still decides contradiction."""
    candidates = _store_recall_belief_candidates(
        self,
        str(getattr(belief, "claim", "")),
        top_k=top_k + 1,
        min_score=min_score,
        domain=str(getattr(belief, "domain", "")),
        query_embedding=query_embedding,
        belief_embeddings=belief_embeddings,
        include_lexical_fallback=include_lexical_fallback,
    )
    belief_id = str(getattr(belief, "id", ""))
    return [candidate for candidate in candidates if candidate.item_id != belief_id][:top_k]


def install_belief_store_recall_methods(store_cls: Any) -> None:
    """Attach recall convenience methods without growing the store module."""
    store_cls.recall_belief_candidates = _store_recall_belief_candidates
    store_cls.recall_contradiction_candidates = _store_recall_contradiction_candidates


__all__ = [
    "CANDIDATE_ONLY",
    "LEXICAL_METHOD",
    "VECTOR_METHOD",
    "RecallCandidate",
    "RecallItem",
    "belief_recall_items",
    "concept_recall_items",
    "install_belief_store_recall_methods",
    "recall_belief_candidates",
    "recall_concept_candidates",
    "recall_items",
    "tokenize_for_recall",
]
