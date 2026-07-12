"""Fail-closed boundary for legacy metered expert mutation workflows."""

from __future__ import annotations

METERED_EXPERT_MUTATIONS_ENABLED = False
METERED_EXPERT_MUTATION_BLOCK_CODE = "metered_expert_mutation_accounting_unavailable"


class MeteredExpertMutationDisabledError(RuntimeError):
    """Raised before a legacy expert workflow can reach paid provider work."""

    code = METERED_EXPERT_MUTATION_BLOCK_CODE
    category = "budget"
    retryable = False

    def __init__(self, operation: str, *, safe_alternative: str) -> None:
        self.operation = operation
        self.safe_alternative = safe_alternative
        self.details = {
            "operation": operation,
            "safe_alternative": safe_alternative,
            "provider_work_started": False,
        }
        super().__init__(
            f"Metered expert operation '{operation}' is temporarily disabled because it cannot yet "
            "prove one durable reservation and canonical settlement for every provider, tool, and "
            f"storage charge. Use: {safe_alternative}"
        )


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
    "MeteredExpertMutationDisabledError",
    "require_api_autonomous_learning",
    "require_api_curriculum_generation",
    "require_metered_expert_mutation",
]
