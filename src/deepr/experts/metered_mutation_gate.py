"""Fail-closed boundary for legacy metered expert mutation workflows."""

from __future__ import annotations

from typing import Any

from deepr.experts.parent_budget_transaction import (
    GATED_METERED_LIFECYCLE_SURFACES,
    surface_requires_parent_budget,
)

METERED_EXPERT_MUTATIONS_ENABLED = False
METERED_EXPERT_MUTATION_BLOCK_CODE = "metered_expert_mutation_accounting_unavailable"
# Parent budget substrate exists; individual surfaces remain blocked until each
# one wires open/admit/mark/settle with hermetic tests and a reviewed enable.
PARENT_BUDGET_TRANSACTION_REQUIRED = True


class MeteredExpertMutationDisabledError(RuntimeError):
    """Raised before a legacy expert workflow can reach paid provider work."""

    code = METERED_EXPERT_MUTATION_BLOCK_CODE
    category = "budget"
    retryable = False

    def __init__(self, operation: str, *, safe_alternative: str) -> None:
        self.operation = operation
        self.safe_alternative = safe_alternative
        self.details: dict[str, Any] = {
            "operation": operation,
            "safe_alternative": safe_alternative,
            "provider_work_started": False,
            "metered_mutations_enabled": METERED_EXPERT_MUTATIONS_ENABLED,
            "parent_budget_transaction_required": PARENT_BUDGET_TRANSACTION_REQUIRED,
            "parent_budget_surface_known": surface_requires_parent_budget(operation),
            "gated_lifecycle_surfaces": list(GATED_METERED_LIFECYCLE_SURFACES),
        }
        super().__init__(
            f"Metered expert operation '{operation}' is temporarily disabled because it cannot yet "
            "prove one durable parent budget transaction and canonical settlement for every "
            f"provider, tool, and storage charge. Use: {safe_alternative}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "blocked",
            "code": self.code,
            "category": self.category,
            "retryable": self.retryable,
            **self.details,
        }


def require_metered_expert_mutation(operation: str, *, safe_alternative: str) -> None:
    """Refuse an unsafe metered expert mutation before provider construction."""
    if not METERED_EXPERT_MUTATIONS_ENABLED:
        raise MeteredExpertMutationDisabledError(operation, safe_alternative=safe_alternative)


def require_api_curriculum_generation() -> None:
    """Block the legacy paid curriculum generator."""
    require_metered_expert_mutation(
        "api_curriculum_generation",
        safe_alternative="create a local expert and use expert next or explicit plan-quota sync",
    )


def require_api_autonomous_learning(expert_name: str) -> None:
    """Block the legacy paid autonomous learner."""
    require_metered_expert_mutation(
        "api_autonomous_learning",
        safe_alternative=f'deepr expert sync "{expert_name}" --local --scheduled --yes',
    )


__all__ = [
    "METERED_EXPERT_MUTATIONS_ENABLED",
    "METERED_EXPERT_MUTATION_BLOCK_CODE",
    "PARENT_BUDGET_TRANSACTION_REQUIRED",
    "MeteredExpertMutationDisabledError",
    "require_api_autonomous_learning",
    "require_api_curriculum_generation",
    "require_metered_expert_mutation",
]
