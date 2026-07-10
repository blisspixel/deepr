"""Fail-closed vector-index checks for explicit recall route preference."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def recall_retrieval_contract(*, top_k: int, domain: str | None, min_score: float) -> dict[str, Any]:
    """Normalize the retrieval parameters that evaluation evidence authorizes."""
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("recall retrieval top_k must be a positive integer")
    if isinstance(min_score, bool):
        raise ValueError("recall retrieval min_score must be numeric")
    score = float(min_score)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError("recall retrieval min_score must be between zero and one")
    return {
        "top_k": top_k,
        "domain": str(domain or ""),
        "min_score": score,
    }


def belief_index_coverage(belief_store: Any, embedding_model: str | None) -> dict[str, Any]:
    """Return sanitized coverage and state identity for one model label."""
    stats_fn = getattr(belief_store, "belief_embedding_stats", None)
    if not callable(stats_fn) or not embedding_model:
        return {}
    stats = dict(stats_fn(embedding_model=embedding_model))
    return {
        "embedding_model": embedding_model,
        "belief_count": int(stats.get("belief_count", 0) or 0),
        "current_vector_count": int(stats.get("current_vector_count", 0) or 0),
        "missing_or_stale_count": int(stats.get("missing_or_stale_count", 0) or 0),
        "record_count": int(stats.get("record_count", 0) or 0),
        "state_digest": str(stats.get("state_digest", "") or ""),
    }


def validate_belief_index_coverage(index: Any, *, embedding_model: str) -> dict[str, Any]:
    """Validate model binding, count consistency, and state-digest shape."""
    if not isinstance(index, Mapping) or index.get("embedding_model") != embedding_model:
        raise ValueError("recall eval report index model does not match the request")
    counts: dict[str, int] = {}
    for field in ("record_count", "belief_count", "current_vector_count", "missing_or_stale_count"):
        value = index.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"recall eval report index has invalid {field}")
        counts[field] = value
    if counts["current_vector_count"] + counts["missing_or_stale_count"] != counts["belief_count"]:
        raise ValueError("recall eval report index counts are inconsistent")
    state_digest = index.get("state_digest")
    if (
        not isinstance(state_digest, str)
        or len(state_digest) != 64
        or any(character not in "0123456789abcdef" for character in state_digest)
    ):
        raise ValueError("recall eval report index has an invalid state digest")
    return dict(index)


def validate_preference_current_index(
    preference: Mapping[str, Any],
    current_index: Any,
    *,
    embedding_model: str,
) -> None:
    """Reject eligible preference evidence when live vector state has drifted."""
    if preference.get("eligible") is not True:
        return
    validated = validate_belief_index_coverage(current_index, embedding_model=embedding_model)
    if validated["current_vector_count"] <= 0 or validated["missing_or_stale_count"] != 0:
        raise ValueError("current belief-vector index coverage is incomplete")
    if preference.get("embedding_model") != embedding_model:
        raise ValueError("recall preference embedding model does not match current index state")
    if preference.get("index_state_digest") != validated["state_digest"]:
        raise ValueError("recall preference report is stale for the current belief-vector index")


def validate_preference_retrieval_contract(
    preference: Mapping[str, Any],
    *,
    top_k: int,
    domain: str | None,
    min_score: float,
) -> None:
    """Reject preference evidence measured under different retrieval parameters."""
    if preference.get("eligible") is not True:
        return
    expected = recall_retrieval_contract(top_k=top_k, domain=domain, min_score=min_score)
    if preference.get("retrieval_contract") != expected:
        raise ValueError("recall preference retrieval contract does not match the current recall request")


__all__ = [
    "belief_index_coverage",
    "recall_retrieval_contract",
    "validate_belief_index_coverage",
    "validate_preference_current_index",
    "validate_preference_retrieval_contract",
]
