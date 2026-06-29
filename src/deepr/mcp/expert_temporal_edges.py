"""MCP helper for read-only temporal edge queries."""

from __future__ import annotations

from typing import Any

from deepr.experts.beliefs import BeliefStore
from deepr.experts.perspective import temporal_edges
from deepr.experts.profile import ExpertStore


def _error(
    error_code: str,
    message: str,
    *,
    category: str = "internal",
    retryable: bool = False,
) -> dict[str, Any]:
    return {"error_code": error_code, "category": category, "retryable": retryable, "message": message}


async def get_temporal_edges(
    store: ExpertStore,
    *,
    expert_name: str = "",
    valid_at: str = "",
    observed_since: str = "",
    observed_until: str = "",
    edge_type: str = "",
    belief_ref: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Return temporal edge qualifiers filtered by valid or observed time."""
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        return _error(
            "INVALID_TEMPORAL_FILTER",
            "limit must be an integer between 1 and 200",
            category="validation",
        )

    try:
        expert = store.load(expert_name)
        if not expert:
            return _error("EXPERT_NOT_FOUND", f"Expert '{expert_name}' not found")

        belief_store = BeliefStore(expert_name)
        return temporal_edges(
            belief_store,
            valid_at=valid_at,
            observed_since=observed_since,
            observed_until=observed_until,
            edge_type=edge_type,
            belief_ref=belief_ref,
            limit=parsed_limit,
            expert_name=expert_name,
        )
    except ValueError as e:
        return _error("INVALID_TEMPORAL_FILTER", str(e), category="validation")
    except (OSError, KeyError) as e:
        return _error("TEMPORAL_EDGES_FAILED", str(e))
