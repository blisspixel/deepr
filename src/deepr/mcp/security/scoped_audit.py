"""Response classification for scoped MCP audit and budget settlement."""

from __future__ import annotations

import json
from typing import Any, Protocol

_TOOL_RESPONSE_COST_FIELDS = {
    "deepr_get_result": "cost_final",
    "deepr_query_expert": "cost",
    "deepr_expert_absorb": "estimated_cost",
}


class MCPResponse(Protocol):
    """Minimal response shape used by scoped audit classification."""

    result: Any | None
    error: dict[str, Any] | None


def _payload(response: MCPResponse | None) -> dict[str, Any] | None:
    if not response or response.error or not isinstance(response.result, dict):
        return None
    if response.result.get("isError") is True:
        return None
    content = response.result.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and isinstance(first.get("text"), str):
            try:
                decoded = json.loads(first["text"])
            except json.JSONDecodeError:
                return None
            return decoded if isinstance(decoded, dict) else None
    return response.result


def scoped_mcp_response_error_code(response: MCPResponse | None) -> str:
    """Return a safe structured error code from a tools/call response."""
    if response is None:
        return ""
    if response.error:
        data = response.error.get("data")
        return str(data.get("error_code") or "") if isinstance(data, dict) else ""
    if not isinstance(response.result, dict) or response.result.get("isError") is not True:
        return ""
    content = response.result.get("content")
    if not isinstance(content, list) or not content:
        return "TOOL_ERROR"
    first = content[0]
    if not isinstance(first, dict) or not isinstance(first.get("text"), str):
        return "TOOL_ERROR"
    try:
        payload = json.loads(first["text"])
    except json.JSONDecodeError:
        return "TOOL_ERROR"
    if not isinstance(payload, dict):
        return "TOOL_ERROR"
    if isinstance(payload.get("error_code"), str):
        return str(payload["error_code"])
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return str(error["code"])
    return "TOOL_ERROR"


def _read_cost(payload: dict[str, Any], field: str) -> float | None:
    value = payload.get(field)
    if value is None or isinstance(value, bool):
        return None
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return max(resolved, 0.0)


def _reflect_cost(arguments: dict[str, Any]) -> float:
    try:
        depth = int(arguments.get("depth", 1) or 1)
    except (TypeError, ValueError):
        depth = 1
    return 0.02 if depth > 0 else 0.0


def scoped_mcp_response_cost_usd(
    tool_name: str,
    arguments: dict[str, Any],
    response: MCPResponse | None,
) -> float | None:
    """Return actual or fixed response cost for scoped budget settlement."""
    payload = _payload(response)
    if not payload or "error_code" in payload:
        return None
    if cost_field := _TOOL_RESPONSE_COST_FIELDS.get(tool_name):
        return _read_cost(payload, cost_field)
    if tool_name == "deepr_expert_validate":
        return 0.02
    if tool_name == "deepr_reflect":
        return _reflect_cost(arguments)
    return None


__all__ = ["scoped_mcp_response_cost_usd", "scoped_mcp_response_error_code"]
