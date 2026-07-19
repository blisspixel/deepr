"""Stable structured error envelopes for MCP tool adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolError:
    """Structured tool failure that callers can classify without message parsing."""

    error_code: str
    message: str
    retry_hint: str | None = None
    fallback_suggestion: str | None = None
    category: str = "internal"
    retryable: bool = False
    retry_after: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "error_code": self.error_code,
            "category": self.category,
            "retryable": self.retryable,
            "message": self.message,
        }
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        if self.retry_hint:
            result["retry_hint"] = self.retry_hint
        if self.fallback_suggestion:
            result["fallback_suggestion"] = self.fallback_suggestion
        return result

    @classmethod
    def from_exception(cls, error_code: str, exc: Exception, message: str | None = None) -> ToolError:
        """Preserve typed retry metadata exposed by Deepr and provider errors."""
        category = getattr(exc, "category", "internal")
        retryable = bool(getattr(exc, "retryable", False))
        retry_after = getattr(exc, "retry_after", None)
        if not isinstance(retry_after, int):
            details = getattr(exc, "details", None)
            retry_after = details.get("retry_after") if isinstance(details, dict) else None
            if not isinstance(retry_after, int):
                retry_after = None
        return cls(
            error_code=error_code,
            message=message if message is not None else str(getattr(exc, "message", exc)),
            category=category if isinstance(category, str) else "internal",
            retryable=retryable,
            retry_after=retry_after,
        )


def make_tool_error(
    code: str,
    message: str,
    retry_hint: str | None = None,
    fallback: str | None = None,
    *,
    category: str = "internal",
    retryable: bool = False,
    retry_after: int | None = None,
) -> dict[str, Any]:
    """Build the canonical dictionary representation returned by MCP tools."""
    return ToolError(
        error_code=code,
        message=message,
        retry_hint=retry_hint,
        fallback_suggestion=fallback,
        category=category,
        retryable=retryable,
        retry_after=retry_after,
    ).to_dict()
