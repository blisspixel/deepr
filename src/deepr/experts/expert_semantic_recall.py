"""Operator-facing semantic recall over expert belief memory.

Recall is a read-only router. This module exposes belief candidates for a later
verifier or graph query, but it never creates embeddings, calls a provider,
writes graph state, or turns a score into a semantic verdict.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from deepr.experts.belief_embedding_refresh import BeliefEmbeddingRefreshResult, refresh_missing_belief_embeddings
from deepr.experts.belief_vector_index import MAX_VECTOR_DIMENSIONS
from deepr.experts.semantic_recall import CANDIDATE_ONLY, LEXICAL_METHOD, VECTOR_METHOD, RecallCandidate

EXPERT_SEMANTIC_RECALL_SCHEMA_VERSION = "deepr-expert-semantic-recall-v1"
EXPERT_SEMANTIC_RECALL_REFRESH_SCHEMA_VERSION = "deepr-expert-semantic-recall-refresh-v1"
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


def coerce_belief_embedding_map(raw: Any) -> dict[str, tuple[float, ...]]:
    """Validate a precomputed belief-id-to-vector mapping."""
    if not isinstance(raw, Mapping):
        raise ValueError("embeddings JSON must be an object mapping belief id to numeric vector")

    vectors: dict[str, tuple[float, ...]] = {}
    for raw_belief_id, raw_vector in raw.items():
        belief_id = str(raw_belief_id).strip()
        if not belief_id:
            raise ValueError("embedding belief id must not be empty")
        vectors[belief_id] = coerce_query_embedding(raw_vector)
    return vectors


def _candidate_payload(candidate: RecallCandidate) -> dict[str, Any]:
    payload = candidate.to_dict()
    payload["text"] = candidate.text
    return payload


def _embedding_stats(belief_store: Any, embedding_model: str | None) -> dict[str, Any]:
    stats = getattr(belief_store, "belief_embedding_stats", None)
    if not callable(stats):
        return {}
    return dict(stats(embedding_model=embedding_model))


def _profile_payload(profile: Any, belief_store: Any) -> dict[str, str]:
    return {
        "name": str(getattr(profile, "name", "") or getattr(belief_store, "expert_name", "") or ""),
        "domain": str(getattr(profile, "domain", "") or ""),
    }


def _refresh_contract(result: BeliefEmbeddingRefreshResult) -> dict[str, Any]:
    return {
        "cost_usd": 0.0,
        "estimated_external_cost_usd": result.estimated_cost_usd,
        "writes_graph": False,
        "writes_beliefs": False,
        "writes_belief_vectors": result.indexed_count > 0,
        "semantic_verdict": False,
        "candidate_verdict": CANDIDATE_ONLY,
        "routing": "candidate_only",
        "embedding_generation": "not_performed_by_deepr",
        "embedding_source": "precomputed_json",
    }


async def build_expert_semantic_recall_refresh(
    profile: Any,
    belief_store: Any,
    embedding_vectors: Mapping[str, Sequence[Any]],
    *,
    embedding_model: str,
    budget_usd: float = 0.0,
    estimated_cost_per_belief: float = 0.0,
    max_beliefs: int | None = None,
) -> dict[str, Any]:
    """Refresh the local belief-vector index from precomputed vectors.

    This is the explicit construction-side path for semantic recall. It never
    calls an embedding provider; spend policy must already have been handled by
    the caller that produced ``embedding_vectors``.
    """
    model = embedding_model.strip()
    if not model:
        raise ValueError("embedding_model is required")

    vectors = coerce_belief_embedding_map(embedding_vectors)
    limit = None if max_beliefs is None else max(0, int(max_beliefs))
    target_ids = list(belief_store.missing_belief_embedding_ids(embedding_model=model))
    if limit is not None:
        target_ids = target_ids[:limit]
    missing_vector_ids = [belief_id for belief_id in target_ids if belief_id not in vectors]
    if missing_vector_ids:
        preview = ", ".join(missing_vector_ids[:5])
        suffix = "" if len(missing_vector_ids) <= 5 else f" and {len(missing_vector_ids) - 5} more"
        raise ValueError(f"embeddings JSON is missing vector(s) for belief id(s): {preview}{suffix}")

    def embed_claims(_claims: list[str]) -> list[tuple[float, ...]]:
        return [vectors[belief_id] for belief_id in target_ids]

    result = await refresh_missing_belief_embeddings(
        belief_store,
        embed_claims,
        model=model,
        budget_usd=budget_usd,
        estimated_cost_per_belief=estimated_cost_per_belief,
        max_beliefs=max_beliefs,
        metadata={
            "source": "cli.expert.refresh-semantic-recall",
            "embedding_source": "precomputed_json",
            "semantic_verdict": False,
            "candidate_verdict": CANDIDATE_ONLY,
        },
    )
    target_id_set = set(target_ids)
    extra_vector_count = sum(1 for belief_id in vectors if belief_id not in target_id_set)

    return {
        "schema_version": EXPERT_SEMANTIC_RECALL_REFRESH_SCHEMA_VERSION,
        "kind": "deepr.expert.semantic_recall_refresh",
        "expert": _profile_payload(profile, belief_store),
        "request": {
            "embedding_model": model,
            "budget_usd": float(budget_usd),
            "estimated_cost_per_belief": float(estimated_cost_per_belief),
            "max_beliefs": max_beliefs,
            "precomputed_vector_count": len(vectors),
            "unused_precomputed_vector_count": extra_vector_count,
        },
        "contract": _refresh_contract(result),
        "summary": {
            "status": result.status,
            "requested_count": result.requested_count,
            "indexed_count": result.indexed_count,
            "skipped_count": result.skipped_count,
        },
        "refresh": result.to_dict(),
        "index": {
            "stats": _embedding_stats(belief_store, model),
        },
    }


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
    stats = _embedding_stats(belief_store, embedding_model)

    return {
        "schema_version": EXPERT_SEMANTIC_RECALL_SCHEMA_VERSION,
        "kind": "deepr.expert.semantic_recall",
        "expert": _profile_payload(profile, belief_store),
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
    "EXPERT_SEMANTIC_RECALL_REFRESH_SCHEMA_VERSION",
    "EXPERT_SEMANTIC_RECALL_SCHEMA_VERSION",
    "MAX_OPERATOR_RECALL_CANDIDATES",
    "build_expert_semantic_recall",
    "build_expert_semantic_recall_refresh",
    "coerce_belief_embedding_map",
    "coerce_query_embedding",
    "parse_query_embedding_json",
]
