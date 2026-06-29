"""MCP helper for read-only expert semantic recall."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from deepr.experts.beliefs import BeliefStore
from deepr.experts.expert_semantic_recall import build_expert_semantic_recall, coerce_query_embedding
from deepr.experts.profile import ExpertStore
from deepr.security.output_safety import sanitize_host_facing_payload


def _error(
    error_code: str,
    message: str,
    *,
    category: str = "internal",
    retryable: bool = False,
) -> dict[str, Any]:
    return {"error_code": error_code, "category": category, "retryable": retryable, "message": message}


def _optional_query_embedding(raw: Any) -> tuple[float, ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("query_embedding must be an array of numbers")
    if len(raw) == 0:
        return None
    return coerce_query_embedding(raw)


async def get_semantic_recall(
    store: ExpertStore,
    *,
    expert_name: str = "",
    query: str = "",
    top_k: int = 5,
    min_score: float = 0.0,
    domain: str = "",
    query_embedding: Any = None,
    embedding_model: str = "",
    include_lexical_fallback: bool = True,
) -> dict[str, Any]:
    """Return read-only belief recall candidates for a host agent."""
    try:
        parsed_top_k = int(top_k)
        parsed_min_score = float(min_score)
        parsed_query_embedding = _optional_query_embedding(query_embedding)
    except (TypeError, ValueError) as exc:
        return _error("INVALID_SEMANTIC_RECALL_PARAMS", str(exc), category="validation")

    try:
        expert = store.load(expert_name)
        if not expert:
            return _error("EXPERT_NOT_FOUND", f"Expert '{expert_name}' not found")

        payload = build_expert_semantic_recall(
            expert,
            BeliefStore(str(getattr(expert, "name", expert_name) or expert_name)),
            query,
            top_k=parsed_top_k,
            min_score=parsed_min_score,
            domain=domain or None,
            query_embedding=parsed_query_embedding,
            embedding_model=embedding_model or None,
            include_lexical_fallback=bool(include_lexical_fallback),
        )
        return cast(dict[str, Any], sanitize_host_facing_payload(payload, source_label="mcp semantic recall"))
    except ValueError as exc:
        return _error("INVALID_SEMANTIC_RECALL_PARAMS", str(exc), category="validation")
    except (OSError, KeyError) as exc:
        return _error("SEMANTIC_RECALL_FAILED", str(exc))


__all__ = ["get_semantic_recall"]
