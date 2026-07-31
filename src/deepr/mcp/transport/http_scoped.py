"""Scoped-key request shapes for the MCP HTTP transport.

Pure helpers: which operation a JSON-RPC message represents for scoped-key
accounting, and the JSON-RPC denial envelopes for authorization, rate-limit,
and budget refusals. Kept separate from the transport so the wire-shape
contract is readable (and testable) on its own.
"""

from __future__ import annotations

from typing import Any

from deepr.mcp.protocol_compat import HttpMessage
from deepr.mcp.security.scoped_keys import (
    ScopedMCPAuthzDecision,
    ScopedMCPBudgetDecision,
    ScopedMCPRateLimitDecision,
)

# Non-tool methods that still consume scoped-key rate limit and audit budget.
SCOPED_RESOURCE_METHODS = frozenset(
    {
        "resources/list",
        "resources/read",
        "resources/subscribe",
        "resources/unsubscribe",
        "subscriptions/listen",
    }
)

AUTHZ_DENIED_CODE = -32003
BUDGET_DENIED_CODE = -32004
RATE_LIMITED_CODE = -32005


def tool_call_parts(message: HttpMessage) -> tuple[str, dict[str, Any]]:
    """Return ``(tool_name, arguments)`` for a ``tools/call``, else empties."""
    if message.method != "tools/call" or not isinstance(message.params, dict):
        return "", {}
    tool_name = str(message.params.get("name") or "")
    arguments = message.params.get("arguments", {})
    return tool_name, dict(arguments) if isinstance(arguments, dict) else {}


def scoped_operation_parts(message: HttpMessage) -> tuple[str, dict[str, Any], str | None]:
    """Return ``(operation, arguments, tool_name)`` for scoped-key accounting.

    ``tool_name`` is None for resource and subscription operations, which are
    accounted by method name rather than by tool.
    """
    tool_name, arguments = tool_call_parts(message)
    if tool_name:
        return tool_name, arguments, tool_name
    if message.method in SCOPED_RESOURCE_METHODS:
        raw_params = message.params if isinstance(message.params, dict) else {}
        params = {key: value for key, value in raw_params.items() if key != "_scoped_key"}
        return str(message.method), params, None
    return "", {}, None


def authz_denial_message(message: HttpMessage, decision: ScopedMCPAuthzDecision) -> HttpMessage:
    return HttpMessage(
        id=message.id,
        error={
            "code": AUTHZ_DENIED_CODE,
            "message": decision.reason,
            "data": {
                "error_code": decision.error_code,
                "requires_confirmation": decision.requires_confirmation,
                "requested_experts": list(decision.requested_experts),
            },
        },
    )


def budget_denial_message(message: HttpMessage, decision: ScopedMCPBudgetDecision) -> HttpMessage:
    return HttpMessage(
        id=message.id,
        error={
            "code": BUDGET_DENIED_CODE,
            "message": decision.reason,
            "data": {
                "error_code": decision.error_code,
                "budget_limit_usd": decision.budget_limit_usd,
                "spent_usd": decision.spent_usd,
                "remaining_usd": decision.remaining_usd,
                "estimated_cost_usd": decision.estimated_cost_usd,
            },
        },
    )


def rate_limit_denial_message(message: HttpMessage, decision: ScopedMCPRateLimitDecision) -> HttpMessage:
    return HttpMessage(
        id=message.id,
        error={
            "code": RATE_LIMITED_CODE,
            "message": decision.reason,
            "data": {
                "error_code": decision.error_code,
                "limit_per_minute": decision.limit_per_minute,
                "calls_in_window": decision.calls_in_window,
                "window_seconds": decision.window_seconds,
                "retry_after_seconds": decision.retry_after_seconds,
            },
        },
    )


__all__ = [
    "AUTHZ_DENIED_CODE",
    "BUDGET_DENIED_CODE",
    "RATE_LIMITED_CODE",
    "SCOPED_RESOURCE_METHODS",
    "authz_denial_message",
    "budget_denial_message",
    "rate_limit_denial_message",
    "scoped_operation_parts",
    "tool_call_parts",
]
