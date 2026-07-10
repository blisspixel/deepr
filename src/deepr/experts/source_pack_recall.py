"""Recall context helpers for source-pack compiler artifacts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from deepr.experts.recall_preference import (
    belief_index_coverage,
    validate_preference_current_index,
    validate_preference_retrieval_contract,
)
from deepr.experts.semantic_recall import LEXICAL_METHOD, VECTOR_METHOD
from deepr.experts.source_pack_values import float_0_1 as _float_0_1

_RECALL_ROUTING = "candidate_only"
_RECALL_GUIDANCE = "routing_only"
_MEMORY_QUALITY_BANDS = ("deduplication", "contradiction", "temporal_scope")
_PREFERENCE_SOURCE = "recall_eval_scheduler_preference"


def _recall_value(candidate: Any, key: str, default: Any = "") -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(key, default)
    return getattr(candidate, key, default)


def _recall_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    values: Iterable[Any]
    if isinstance(value, set):
        values = sorted(value)
    elif isinstance(value, Iterable):
        values = value
    else:
        return []
    return [text for item in values if (text := str(item).strip())]


def _recall_metadata(candidate: Any) -> dict[str, Any]:
    metadata = _recall_value(candidate, "metadata", {})
    if not isinstance(metadata, Mapping):
        return {}
    return dict(metadata)


def _recall_candidate_packet(candidate: Any) -> dict[str, Any]:
    return {
        "item_id": str(_recall_value(candidate, "item_id", "") or ""),
        "kind": str(_recall_value(candidate, "kind", "") or ""),
        "domain": str(_recall_value(candidate, "domain", "") or ""),
        "text": str(_recall_value(candidate, "text", "") or ""),
        "score": _float_0_1(_recall_value(candidate, "score", 0.0)),
        "method": str(_recall_value(candidate, "method", "") or ""),
        "matched_terms": _recall_string_list(_recall_value(candidate, "matched_terms", [])),
        "metadata": _recall_metadata(candidate),
        "verdict": _RECALL_ROUTING,
        "guidance": _RECALL_GUIDANCE,
    }


def _recall_candidate_iter(raw_candidates: Any) -> Iterable[Any]:
    if raw_candidates is None or isinstance(raw_candidates, str):
        return []
    if isinstance(raw_candidates, Mapping):
        return [raw_candidates] if "item_id" in raw_candidates else []
    if isinstance(raw_candidates, Iterable):
        return raw_candidates
    return [raw_candidates]


def build_recall_context(raw_candidates: Any) -> dict[str, Any]:
    """Build a read-only recall packet for verifier routing."""
    candidates = [
        packet
        for candidate in _recall_candidate_iter(raw_candidates)
        if (packet := _recall_candidate_packet(candidate))["item_id"]
    ]
    return {
        "routing": _RECALL_ROUTING,
        "semantic_verdict": False,
        "writes_graph": False,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _ready_claim_candidates(claim_extraction: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    raw_candidates = claim_extraction.get("candidates", [])
    if not isinstance(raw_candidates, list):
        return []
    ready_candidates = []
    for candidate in raw_candidates:
        if not isinstance(candidate, Mapping) or not candidate.get("candidate_id") or not candidate.get("statement"):
            continue
        readiness = candidate.get("readiness", {}) or {}
        if isinstance(readiness, Mapping) and readiness.get("ready_for_verification") is True:
            ready_candidates.append(candidate)
    return ready_candidates


def _memory_quality_packet(candidate: Any) -> dict[str, Any]:
    packet = _recall_candidate_packet(candidate)
    metadata = dict(packet["metadata"])
    metadata["recall_role"] = "memory_quality_candidate"
    metadata["verifier_bands"] = list(_MEMORY_QUALITY_BANDS)
    packet["metadata"] = metadata
    return packet


def _prefers_vector_route(
    route_preference: Mapping[str, Any] | None,
    belief_store: Any,
    embedding_model: str | None,
    *,
    top_k: int,
    domain: str | None,
    min_score: float,
) -> bool:
    if not isinstance(route_preference, Mapping):
        return False
    contract_allows_vector = (
        route_preference.get("eligible") is True
        and route_preference.get("preferred_route") == VECTOR_METHOD
        and route_preference.get("fallback_route") == LEXICAL_METHOD
        and route_preference.get("routing_evidence_only") is True
        and route_preference.get("semantic_verdict") is False
    )
    if not contract_allows_vector or not embedding_model:
        return False
    try:
        current_index = belief_index_coverage(belief_store, embedding_model)
        validate_preference_current_index(
            route_preference,
            current_index,
            embedding_model=embedding_model,
        )
        validate_preference_retrieval_contract(
            route_preference,
            top_k=top_k,
            domain=domain,
            min_score=min_score,
        )
    except (TypeError, ValueError):
        return False
    return True


def _mark_preferred_route(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    marked: list[dict[str, Any]] = []
    for packet in packets:
        metadata = dict(packet.get("metadata", {}))
        metadata["route_preference"] = {
            "source": _PREFERENCE_SOURCE,
            "preferred_route": VECTOR_METHOD,
            "fallback_route": LEXICAL_METHOD,
            "routing_evidence_only": True,
            "semantic_verdict": False,
        }
        marked.append({**packet, "metadata": metadata})
    return marked


async def embed_ready_claim_statements(
    claim_extraction: Mapping[str, Any],
    embed_claims: Any,
) -> dict[str, tuple[float, ...]]:
    """Batch-embed ready claim-candidate statements for vector recall routing.

    Returns candidate id to query vector, preserving batch order. The vectors
    are routing inputs for ``build_verification_recall_candidates`` only; they
    carry no semantic verdict and never touch the graph.
    """
    ready = [
        (candidate_id, statement)
        for candidate in _ready_claim_candidates(claim_extraction)
        if (candidate_id := str(candidate.get("candidate_id", "") or ""))
        and (statement := str(candidate.get("statement", "") or ""))
    ]
    if not ready:
        return {}
    vectors = list(await embed_claims([statement for _, statement in ready]))
    if len(vectors) != len(ready):
        raise ValueError(f"embedder returned {len(vectors)} vector(s) for {len(ready)} ready claim candidate(s)")
    return {
        candidate_id: tuple(float(value) for value in vector)
        for (candidate_id, _), vector in zip(ready, vectors, strict=True)
    }


def build_verification_recall_candidates(
    claim_extraction: Mapping[str, Any],
    belief_store: Any,
    *,
    domain: str | None = None,
    top_k: int = 5,
    min_score: float = 0.0,
    query_embeddings_by_candidate_id: Mapping[str, Sequence[float]] | None = None,
    embedding_model: str | None = None,
    include_lexical_fallback: bool = True,
    route_preference: Mapping[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Route ready claim candidates to existing beliefs for verifier inspection.

    The returned packets are candidate-only hints. They do not assert support,
    contradiction, deduplication, or temporal validity; the downstream verifier
    owns those semantic decisions.
    """
    recall = getattr(belief_store, "recall_belief_candidates", None)
    if not callable(recall) or top_k <= 0:
        return {}

    routed: dict[str, list[dict[str, Any]]] = {}
    prefer_vector = _prefers_vector_route(
        route_preference,
        belief_store,
        embedding_model,
        top_k=top_k,
        domain=domain,
        min_score=min_score,
    )
    for candidate in _ready_claim_candidates(claim_extraction):
        candidate_id = str(candidate.get("candidate_id", "") or "")
        statement = str(candidate.get("statement", "") or "")
        query_embedding = (
            query_embeddings_by_candidate_id.get(candidate_id) if query_embeddings_by_candidate_id else None
        )
        if prefer_vector and query_embedding is not None:
            vector_hits = recall(
                statement,
                top_k=top_k,
                min_score=min_score,
                domain=domain,
                query_embedding=query_embedding,
                embedding_model=embedding_model,
                include_lexical_fallback=False,
            )
            packets = [_memory_quality_packet(hit) for hit in vector_hits]
            if packets:
                routed[candidate_id] = _mark_preferred_route(packets)
                continue
            if not include_lexical_fallback:
                continue
        if not include_lexical_fallback:
            continue
        hits = recall(
            statement,
            top_k=top_k,
            min_score=min_score,
            domain=domain,
            query_embedding=None,
            embedding_model=None,
            include_lexical_fallback=True,
        )
        packets = [_memory_quality_packet(hit) for hit in hits]
        if packets:
            routed[candidate_id] = packets
    return routed


def resolve_verification_recall_candidates(
    provided: Mapping[str, Iterable[Any]] | None,
    claim_extraction: Mapping[str, Any],
    belief_store: Any | None,
    *,
    domain: str | None = None,
    top_k: int = 5,
    min_score: float = 0.0,
    query_embeddings_by_candidate_id: Mapping[str, Sequence[float]] | None = None,
    embedding_model: str | None = None,
    route_preference: Mapping[str, Any] | None = None,
) -> Mapping[str, Iterable[Any]]:
    if provided is not None:
        return provided
    if belief_store is None:
        return {}
    return build_verification_recall_candidates(
        claim_extraction,
        belief_store,
        domain=domain,
        top_k=top_k,
        min_score=min_score,
        query_embeddings_by_candidate_id=query_embeddings_by_candidate_id,
        embedding_model=embedding_model,
        route_preference=route_preference,
    )


__all__ = [
    "build_recall_context",
    "build_verification_recall_candidates",
    "embed_ready_claim_statements",
    "resolve_verification_recall_candidates",
]
