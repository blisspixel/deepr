"""Fail-closed managed MCP conversation-validation entry point."""

from __future__ import annotations

from collections.abc import Callable

from deepr.experts.conversation.service import ExpertConversationTurnExecutor
from deepr.mcp.conversation_validation import (
    DEFAULT_CONTINUE_MESSAGE,
    DEFAULT_START_MESSAGE,
    MCPConversationValidationReport,
    _failed,
)
from deepr.mcp.http_client_policy import validated_mcp_http_timeout

ExecutorFactory = Callable[[], ExpertConversationTurnExecutor]


async def run_managed_loopback_conversation_validation(
    *,
    expert: str | None = None,
    local_model: str | None = None,
    start_message: str = DEFAULT_START_MESSAGE,
    continue_message: str = DEFAULT_CONTINUE_MESSAGE,
    timeout_seconds: float = 180.0,
    executor_factory: ExecutorFactory | None = None,
) -> MCPConversationValidationReport:
    """Block HTTP tools/call until it has an independently enforced cost authority."""
    try:
        validated_mcp_http_timeout(timeout_seconds)
    except ValueError as exc:
        detail = str(exc)
        return MCPConversationValidationReport(
            mode="managed_loopback",
            endpoint=None,
            checks=(_failed("timeout_configuration", detail),),
            local_model=local_model,
            error={"error_code": "INVALID_TIMEOUT", "message": detail},
        )

    del expert, start_message, continue_message, executor_factory
    detail = (
        "Managed loopback HTTP conversation validation is blocked because MCP tools/call "
        "has no independently enforced cost authority. A loopback address, zero-dollar "
        "request fields, and local backend metadata do not grant transport-level dispatch "
        "authority. Use direct offline validation until a bounded authority can be proven "
        "and consumed before dispatch."
    )
    return MCPConversationValidationReport(
        mode="managed_loopback",
        endpoint=None,
        checks=(_failed("managed_tool_cost_authority", detail),),
        local_model=local_model,
        error={"error_code": "MCP_MANAGED_CONVERSATION_VALIDATION_BLOCKED", "message": detail},
    )


__all__ = ["run_managed_loopback_conversation_validation"]
