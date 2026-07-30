"""Release-safe capacity gate for live expert chat provider work."""

from __future__ import annotations

from typing import Any

METERED_EXPERT_CHAT_EXECUTION_ENABLED = False
HOSTED_EXPERT_STORAGE_LIFECYCLE_ACCOUNTING_ENABLED = False
METERED_EXPERT_CHAT_BLOCK_CODE = "metered_expert_chat_accounting_unavailable"
METERED_EXPERT_CHAT_CONFIRM_CODE = "metered_expert_chat_confirmation_required"
_METERED_CHAT_ALLOW_ENV = "DEEPR_ALLOW_METERED_EXPERT_CHAT"


def validate_expert_chat_release_invariants() -> None:
    """Prevent a release from enabling chat without a hard provider charge bound."""
    if METERED_EXPERT_CHAT_EXECUTION_ENABLED:
        raise RuntimeError(
            "Metered expert chat cannot be enabled until serialized input, output, tools, cache writes, "
            "and hosted storage all have provider-enforceable maximum-charge envelopes"
        )


validate_expert_chat_release_invariants()


class MeteredExpertChatDisabledError(RuntimeError):
    """A metered live-chat call was refused before provider dispatch."""

    code = METERED_EXPERT_CHAT_BLOCK_CODE
    status = "blocked"
    retryable = False
    provider_work_dispatched = False

    def __init__(self, operation: str, *, code: str | None = None, message: str | None = None) -> None:
        self.operation = operation
        if code is not None:
            self.code = code
        super().__init__(
            message
            or (
                "Metered expert chat is disabled because its serialized input, output, tools, "
                "cache writes, and hosted storage do not have one provider-enforceable maximum charge. "
                "Use explicit local or non-metered plan capacity."
            )
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
            "explicit_allow_env": _METERED_CHAT_ALLOW_ENV,
        }


def expert_chat_backend_is_metered(backend: Any) -> bool:
    """Treat unknown backend accounting modes as metered and fail closed."""
    return getattr(backend, "metered", None) is not False


def explicit_metered_chat_allowed() -> bool:
    """Return False because an environment variable cannot waive a hard cost proof."""
    return False


def require_expert_chat_dispatch(
    backend: Any,
    operation: str,
    *,
    metered: bool | None = None,
) -> None:
    """Refuse metered work while preserving explicit owned-capacity calls."""
    uses_metered_capacity = expert_chat_backend_is_metered(backend) if metered is None else metered
    if not uses_metered_capacity:
        return
    raise MeteredExpertChatDisabledError(operation)


def expert_chat_capacity(backend: Any) -> dict[str, Any]:
    """Describe whether this exact backend can dispatch live chat work."""
    metered = expert_chat_backend_is_metered(backend)
    if not metered:
        return {
            "metered": False,
            "execution_enabled": True,
            "status": "available",
            "block_code": "",
            "explicit_allow": True,
        }
    return {
        "metered": True,
        "execution_enabled": False,
        "status": "blocked",
        "block_code": METERED_EXPERT_CHAT_BLOCK_CODE,
        "explicit_allow": False,
    }


__all__ = [
    "HOSTED_EXPERT_STORAGE_LIFECYCLE_ACCOUNTING_ENABLED",
    "METERED_EXPERT_CHAT_BLOCK_CODE",
    "METERED_EXPERT_CHAT_CONFIRM_CODE",
    "METERED_EXPERT_CHAT_EXECUTION_ENABLED",
    "MeteredExpertChatDisabledError",
    "expert_chat_backend_is_metered",
    "expert_chat_capacity",
    "explicit_metered_chat_allowed",
    "require_expert_chat_dispatch",
    "validate_expert_chat_release_invariants",
]
