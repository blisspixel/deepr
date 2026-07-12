"""HTTP response helper for fail-closed metered expert mutations."""

from __future__ import annotations

from typing import Any

from deepr.experts.metered_mutation_gate import MeteredExpertMutationDisabledError


def metered_expert_mutation_block(operation: str, *, safe_alternative: str) -> tuple[dict[str, Any], int]:
    """Return a typed 503 response without constructing a provider client."""
    error = MeteredExpertMutationDisabledError(operation, safe_alternative=safe_alternative)
    return (
        {
            "error": str(error),
            "error_code": error.code,
            "status": "blocked",
            "retryable": False,
            "provider_work_started": False,
            "safe_alternative": safe_alternative,
        },
        503,
    )


__all__ = ["metered_expert_mutation_block"]
