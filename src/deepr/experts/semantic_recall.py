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
from pathlib import Path
from typing import Any

from deepr.experts.belief_vector_index import BeliefVectorIndex
from deepr.experts.perspective_state import (
    ORIGINAL_IDEA_AUTHORITY,
    ORIGINAL_IDEA_PROMOTION_POLICY,
    PERSPECTIVE_STATE_SCHEMA_VERSION,
)

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


def _string_list_attribute(item: Any, attribute: str) -> list[str]:
    values = getattr(item, attribute, []) or []
    if isinstance(values, str):
        values = [values]
    return [text for value in values if (text := str(value).strip())]


def _iso_attribute(item: Any, attribute: str) -> str:
    value = getattr(item, attribute, None)
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def _original_idea_recall_text(original_idea: Any) -> str:
    text_parts = [
        str(getattr(original_idea, "title", "") or ""),
        str(getattr(original_idea, "statement", "") or ""),
        str(getattr(original_idea, "rationale", "") or ""),
        str(getattr(original_idea, "uncertainty", "") or ""),
        *_string_list_attribute(original_idea, "assumptions"),
        *_string_list_attribute(original_idea, "implications"),
        *_string_list_attribute(original_idea, "expected_observations"),
        *_string_list_attribute(original_idea, "disconfirming_signals"),
    ]
    return " ".join(part.strip() for part in text_parts if part.strip())


def original_idea_recall_items(original_ideas: Iterable[Any]) -> list[RecallItem]:
    """Adapt original ideas into perspective-state recall items."""
    items: list[RecallItem] = []
    for original_idea in original_ideas:
        idea_id = str(getattr(original_idea, "id", "") or "")
        text = _original_idea_recall_text(original_idea)
        if not idea_id or not text:
            continue
        items.append(
            RecallItem(
                item_id=idea_id,
                text=text,
                kind="original_idea",
                payload=original_idea,
                metadata={
                    "state_type": "original_idea",
                    "schema_version": PERSPECTIVE_STATE_SCHEMA_VERSION,
                    "authority": ORIGINAL_IDEA_AUTHORITY,
                    "promotion_policy": ORIGINAL_IDEA_PROMOTION_POLICY,
                    "factual_claim": False,
                    "semantic_verdict": False,
                    "confidence": getattr(original_idea, "confidence", None),
                    "priority": getattr(original_idea, "priority", None),
                    "status": getattr(original_idea, "status", ""),
                    "created_at": _iso_attribute(original_idea, "created_at"),
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


def recall_original_idea_candidates(
    query: str,
    original_ideas: Iterable[Any],
    *,
    top_k: int = 5,
    min_score: float = 0.0,
    query_embedding: Sequence[float] | None = None,
    original_idea_embeddings: Mapping[str, Sequence[float]] | None = None,
    include_lexical_fallback: bool = True,
) -> list[RecallCandidate]:
    """Return original-idea candidates for perspective routing only."""
    return recall_items(
        query,
        original_idea_recall_items(original_ideas),
        top_k=top_k,
        min_score=min_score,
        query_embedding=query_embedding,
        item_embeddings=original_idea_embeddings,
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
    embedding_model: str | None = None,
    include_lexical_fallback: bool = True,
) -> list[RecallCandidate]:
    """BeliefStore-compatible wrapper for local recall routing."""
    resolved_embeddings = belief_embeddings
    if resolved_embeddings is None and query_embedding is not None:
        resolved_embeddings = _store_belief_vector_index(self).vectors_for(
            self.beliefs.values(),
            model=embedding_model,
        )
    return recall_belief_candidates(
        query,
        self.beliefs.values(),
        top_k=top_k,
        min_score=min_score,
        domain=domain,
        query_embedding=query_embedding,
        belief_embeddings=resolved_embeddings,
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
    embedding_model: str | None = None,
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
        embedding_model=embedding_model,
        include_lexical_fallback=include_lexical_fallback,
    )
    belief_id = str(getattr(belief, "id", ""))
    return [candidate for candidate in candidates if candidate.item_id != belief_id][:top_k]


def _store_belief_vector_index(self: Any) -> BeliefVectorIndex:
    index = getattr(self, "_belief_vector_index", None)
    if index is None:
        index = BeliefVectorIndex.for_belief_store(Path(self.storage_dir))
        self._belief_vector_index = index
    return index


def _store_upsert_belief_embedding(
    self: Any,
    belief_id: str,
    embedding: Sequence[float],
    *,
    model: str = "",
    embedded_at: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> bool:
    """Persist an already computed embedding for one current belief."""
    belief = self.beliefs.get(str(belief_id))
    if belief is None:
        raise ValueError(f"unknown belief id: {belief_id}")
    return _store_belief_vector_index(self).upsert_belief(
        belief,
        embedding,
        model=model,
        embedded_at=embedded_at,
        metadata=metadata,
    )


def _store_missing_belief_embedding_ids(self: Any, *, embedding_model: str | None = None) -> list[str]:
    """Return current belief ids missing a non-stale indexed vector."""
    return _store_belief_vector_index(self).missing_or_stale_ids(
        self.beliefs.values(),
        model=embedding_model,
    )


def _store_prune_belief_embeddings(self: Any) -> int:
    """Remove vectors for beliefs no longer present in the canonical store."""
    return _store_belief_vector_index(self).prune(self.beliefs.keys())


def _store_belief_embedding_stats(self: Any, *, embedding_model: str | None = None) -> dict[str, Any]:
    """Return local belief-vector index statistics."""
    return _store_belief_vector_index(self).stats(
        self.beliefs.values(),
        model=embedding_model,
    )


def install_belief_store_recall_methods(store_cls: Any) -> None:
    """Attach recall convenience methods without growing the store module."""
    store_cls.recall_belief_candidates = _store_recall_belief_candidates
    store_cls.recall_contradiction_candidates = _store_recall_contradiction_candidates
    store_cls.upsert_belief_embedding = _store_upsert_belief_embedding
    store_cls.missing_belief_embedding_ids = _store_missing_belief_embedding_ids
    store_cls.prune_belief_embeddings = _store_prune_belief_embeddings
    store_cls.belief_embedding_stats = _store_belief_embedding_stats


def _tracker_recall_original_idea_candidates(
    self: Any,
    query: str,
    *,
    top_k: int = 5,
    min_score: float = 0.0,
    query_embedding: Sequence[float] | None = None,
    original_idea_embeddings: Mapping[str, Sequence[float]] | None = None,
    include_lexical_fallback: bool = True,
) -> list[RecallCandidate]:
    """MetaCognitionTracker-compatible wrapper for read-only idea recall."""
    return recall_original_idea_candidates(
        query,
        self.get_original_ideas(),
        top_k=top_k,
        min_score=min_score,
        query_embedding=query_embedding,
        original_idea_embeddings=original_idea_embeddings,
        include_lexical_fallback=include_lexical_fallback,
    )


def install_metacognition_recall_methods(tracker_cls: Any) -> None:
    """Attach perspective-state recall without growing the tracker module."""
    tracker_cls.recall_original_idea_candidates = _tracker_recall_original_idea_candidates


__all__ = [
    "CANDIDATE_ONLY",
    "LEXICAL_METHOD",
    "VECTOR_METHOD",
    "RecallCandidate",
    "RecallItem",
    "belief_recall_items",
    "concept_recall_items",
    "install_belief_store_recall_methods",
    "install_metacognition_recall_methods",
    "original_idea_recall_items",
    "recall_belief_candidates",
    "recall_concept_candidates",
    "recall_items",
    "recall_original_idea_candidates",
    "tokenize_for_recall",
]
