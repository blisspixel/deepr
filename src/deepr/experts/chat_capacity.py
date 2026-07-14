"""Release-safe capacity gate for live expert chat provider work."""

from __future__ import annotations

import os
from typing import Any

METERED_EXPERT_CHAT_EXECUTION_ENABLED = False
METERED_EXPERT_CHAT_BLOCK_CODE = "metered_expert_chat_accounting_unavailable"
METERED_EXPERT_CHAT_CONFIRM_CODE = "metered_expert_chat_confirmation_required"
_METERED_CHAT_ALLOW_ENV = "DEEPR_ALLOW_METERED_EXPERT_CHAT"


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
                "Metered expert chat is temporarily disabled until every provider call "
                "shares durable reserve, dispatch-mark, and settlement accounting. "
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
    """Return True only when the operator opted into live metered chat spend.

    Even after ``METERED_EXPERT_CHAT_EXECUTION_ENABLED`` is flipped true, live
    metered dispatch still requires ``DEEPR_ALLOW_METERED_EXPERT_CHAT=1`` (or
    true/yes/on). That keeps re-enable behind an explicit operator action.
    """
    raw = os.environ.get(_METERED_CHAT_ALLOW_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


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
    if not METERED_EXPERT_CHAT_EXECUTION_ENABLED:
        raise MeteredExpertChatDisabledError(operation)
    if not explicit_metered_chat_allowed():
        raise MeteredExpertChatDisabledError(
            operation,
            code=METERED_EXPERT_CHAT_CONFIRM_CODE,
            message=(
                "Metered expert chat execution substrate is present, but live spend "
                f"requires explicit operator confirmation via {_METERED_CHAT_ALLOW_ENV}=1. "
                "Use local or non-metered plan capacity, or set that env var under a "
                "reviewed budget policy."
            ),
        )


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
    if not METERED_EXPERT_CHAT_EXECUTION_ENABLED:
        return {
            "metered": True,
            "execution_enabled": False,
            "status": "blocked",
            "block_code": METERED_EXPERT_CHAT_BLOCK_CODE,
            "explicit_allow": explicit_metered_chat_allowed(),
        }
    allowed = explicit_metered_chat_allowed()
    return {
        "metered": True,
        "execution_enabled": allowed,
        "status": "available" if allowed else "blocked",
        "block_code": "" if allowed else METERED_EXPERT_CHAT_CONFIRM_CODE,
        "explicit_allow": allowed,
    }


__all__ = [
    "METERED_EXPERT_CHAT_BLOCK_CODE",
    "METERED_EXPERT_CHAT_CONFIRM_CODE",
    "METERED_EXPERT_CHAT_EXECUTION_ENABLED",
    "MeteredExpertChatDisabledError",
    "expert_chat_backend_is_metered",
    "expert_chat_capacity",
    "explicit_metered_chat_allowed",
    "require_expert_chat_dispatch",
]
