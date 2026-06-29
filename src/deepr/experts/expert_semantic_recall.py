"""Operator-facing semantic recall over expert belief memory.

Recall is a read-only router. This module exposes belief candidates for a later
verifier or graph query, but it never creates embeddings, calls a provider,
writes graph state, or turns a score into a semantic verdict.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any

from deepr.experts.belief_vector_index import MAX_VECTOR_DIMENSIONS
from deepr.experts.semantic_recall import CANDIDATE_ONLY, LEXICAL_METHOD, VECTOR_METHOD, RecallCandidate

EXPERT_SEMANTIC_RECALL_SCHEMA_VERSION = "deepr-expert-semantic-recall-v1"
MAX_OPERATOR_RECALL_CANDIDATES = 50


def parse_query_embedding_json(raw: str) -> tuple[float, ...]:
    """Parse an explicit caller-supplied query embedding."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"query embedding must be JSON: {exc.msg}") from exc
    return coerce_query_embedding(payload)


def coerce_query_embedding(raw: Sequence[Any]) -> tuple[float, ...]:
    """Validate a query embedding before local vector recall uses it."""
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise ValueError("query embedding must be a JSON array of numbers")
    if not raw:
        raise ValueError("query embedding must not be empty")
    if len(raw) > MAX_VECTOR_DIMENSIONS:
        raise ValueError(f"query embedding exceeds {MAX_VECTOR_DIMENSIONS} dimensions")

    values: list[float] = []
    for index, value in enumerate(raw):
        if isinstance(value, bool):
            raise ValueError(f"query embedding value {index} must be numeric, not boolean")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"query embedding value {index} must be numeric") from exc
        if not math.isfinite(number):
            raise ValueError(f"query embedding value {index} must be finite")
        values.append(number)
    return tuple(values)


def _candidate_payload(candidate: RecallCandidate) -> dict[str, Any]:
    payload = candidate.to_dict()
    payload["text"] = candidate.text
    return payload


def _embedding_stats(belief_store: Any, embedding_model: str | None) -> dict[str, Any]:
    stats = getattr(belief_store, "belief_embedding_stats", None)
    if not callable(stats):
        return {}
    return dict(stats(embedding_model=embedding_model))


def build_expert_semantic_recall(
    profile: Any,
    belief_store: Any,
    query: str,
    *,
    top_k: int = 5,
    min_score: float = 0.0,
    domain: str | None = None,
    query_embedding: Sequence[float] | None = None,
    embedding_model: str | None = None,
    include_lexical_fallback: bool = True,
) -> dict[str, Any]:
    """Build a read-only semantic-recall payload for one expert."""
    query_text = query.strip()
    if not query_text:
        raise ValueError("query must not be empty")
    if not 0.0 <= float(min_score) <= 1.0:
        raise ValueError("min_score must be between 0 and 1")

    bounded_top_k = max(1, min(int(top_k), MAX_OPERATOR_RECALL_CANDIDATES))
    query_vector = tuple(query_embedding) if query_embedding is not None else None
    if query_vector is not None:
        query_vector = coerce_query_embedding(query_vector)
        if not embedding_model:
            raise ValueError("embedding_model is required when query_embedding is supplied")
    elif embedding_model:
        raise ValueError("query_embedding is required when embedding_model is supplied")

    recall = getattr(belief_store, "recall_belief_candidates", None)
    candidates = (
        recall(
            query_text,
            top_k=bounded_top_k,
            min_score=float(min_score),
            domain=domain,
            query_embedding=query_vector,
            embedding_model=embedding_model,
            include_lexical_fallback=include_lexical_fallback,
        )
        if callable(recall)
        else []
    )
    candidate_payloads = [_candidate_payload(candidate) for candidate in candidates]
    vector_count = sum(1 for candidate in candidates if candidate.method == VECTOR_METHOD)
    lexical_count = sum(1 for candidate in candidates if candidate.method == LEXICAL_METHOD)
    expert_name = str(getattr(profile, "name", "") or getattr(belief_store, "expert_name", "") or "")
    expert_domain = str(getattr(profile, "domain", "") or "")
    stats = _embedding_stats(belief_store, embedding_model)

    return {
        "schema_version": EXPERT_SEMANTIC_RECALL_SCHEMA_VERSION,
        "kind": "deepr.expert.semantic_recall",
        "expert": {
            "name": expert_name,
            "domain": expert_domain,
        },
        "query": {
            "text": query_text,
            "domain_filter": domain or "",
            "top_k": bounded_top_k,
            "min_score": float(min_score),
            "embedding_model": embedding_model or "",
            "query_embedding_dimensions": len(query_vector or ()),
            "include_lexical_fallback": include_lexical_fallback,
        },
        "contract": {
            "cost_usd": 0.0,
            "writes_graph": False,
            "writes_belief_store": False,
            "semantic_verdict": False,
            "candidate_verdict": CANDIDATE_ONLY,
            "routing": "candidate_only",
            "embedding_generation": "not_performed",
        },
        "index": {
            "used": query_vector is not None,
            "stats": stats,
        },
        "summary": {
            "candidate_count": len(candidate_payloads),
            "vector_candidate_count": vector_count,
            "lexical_candidate_count": lexical_count,
        },
        "candidates": candidate_payloads,
    }


__all__ = [
    "EXPERT_SEMANTIC_RECALL_SCHEMA_VERSION",
    "MAX_OPERATOR_RECALL_CANDIDATES",
    "build_expert_semantic_recall",
    "coerce_query_embedding",
    "parse_query_embedding_json",
]
