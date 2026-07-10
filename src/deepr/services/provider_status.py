"""Safe normalization for provider-controlled research status values."""

from typing import Literal, cast

ProviderStatus = Literal[
    "cancelled",
    "completed",
    "expired",
    "failed",
    "in_progress",
    "incomplete",
    "queued",
    "unsupported",
]

_KNOWN_STATUSES = frozenset(
    {
        "cancelled",
        "completed",
        "expired",
        "failed",
        "in_progress",
        "incomplete",
        "queued",
    }
)
_TERMINAL_FAILURE_MESSAGES: dict[ProviderStatus, str] = {
    "cancelled": "Provider reported research cancellation",
    "expired": "Provider research request expired",
    "failed": "Provider reported research failure",
    "incomplete": "Provider returned an incomplete research result",
}


def classify_provider_status(value: object) -> ProviderStatus:
    """Map provider-controlled status data into a closed local state set."""
    if isinstance(value, str) and value in _KNOWN_STATUSES:
        return cast(ProviderStatus, value)
    return "unsupported"


def terminal_provider_error(status: ProviderStatus) -> str | None:
    """Return a content-free terminal error for a normalized status."""
    return _TERMINAL_FAILURE_MESSAGES.get(status)


def provider_exception_name(error: BaseException) -> str:
    """Return a bounded content-free exception classification for logs."""
    name = type(error).__name__
    return name[:64] if name.isidentifier() else "Exception"


__all__ = [
    "ProviderStatus",
    "classify_provider_status",
    "provider_exception_name",
    "terminal_provider_error",
]
