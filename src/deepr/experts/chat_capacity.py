"""Release-safe capacity gate for live expert chat provider work."""

from __future__ import annotations

from typing import Any

METERED_EXPERT_CHAT_EXECUTION_ENABLED = False
METERED_EXPERT_CHAT_BLOCK_CODE = "metered_expert_chat_accounting_unavailable"


class MeteredExpertChatDisabledError(RuntimeError):
    """A metered live-chat call was refused before provider dispatch."""

    code = METERED_EXPERT_CHAT_BLOCK_CODE
    status = "blocked"
    retryable = False
    provider_work_dispatched = False

    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(
            "Metered expert chat is temporarily disabled until every provider call "
            "shares durable reserve, dispatch-mark, and settlement accounting. "
            "Use explicit local or non-metered plan capacity."
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a machine-readable blocked-capacity result."""
        return {
            "status": self.status,
            "code": self.code,
            "operation": self.operation,
            "retryable": self.retryable,
            "provider_work_dispatched": self.provider_work_dispatched,
            "metered_chat_execution_enabled": METERED_EXPERT_CHAT_EXECUTION_ENABLED,
        }


def expert_chat_backend_is_metered(backend: Any) -> bool:
    """Treat unknown backend accounting modes as metered and fail closed."""
    return getattr(backend, "metered", None) is not False


def require_expert_chat_dispatch(
    backend: Any,
    operation: str,
    *,
    metered: bool | None = None,
) -> None:
    """Refuse metered work while preserving explicit owned-capacity calls."""
    uses_metered_capacity = expert_chat_backend_is_metered(backend) if metered is None else metered
    if uses_metered_capacity and not METERED_EXPERT_CHAT_EXECUTION_ENABLED:
        raise MeteredExpertChatDisabledError(operation)


def expert_chat_capacity(backend: Any) -> dict[str, Any]:
    """Describe whether this exact backend can dispatch live chat work."""
    metered = expert_chat_backend_is_metered(backend)
    enabled = not metered or METERED_EXPERT_CHAT_EXECUTION_ENABLED
    return {
        "metered": metered,
        "execution_enabled": enabled,
        "status": "available" if enabled else "blocked",
        "block_code": "" if enabled else METERED_EXPERT_CHAT_BLOCK_CODE,
    }


__all__ = [
    "METERED_EXPERT_CHAT_BLOCK_CODE",
    "METERED_EXPERT_CHAT_EXECUTION_ENABLED",
    "MeteredExpertChatDisabledError",
    "expert_chat_backend_is_metered",
    "expert_chat_capacity",
    "require_expert_chat_dispatch",
]
