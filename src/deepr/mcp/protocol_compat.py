"""Shared compatibility aliases for legacy MCP method names."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deepr.mcp.protocol_modern import JsonRpcProtocolError


def mcp_response_id(data: object) -> str | int | None:
    """Return only an id that is safe to echo in an MCP response."""
    value = data.get("id") if isinstance(data, dict) else None
    return value if isinstance(value, str | int) and not isinstance(value, bool) else None


def validate_mcp_envelope(data: object) -> dict[str, Any]:
    """Validate MCP message shape without interpreting methods or extensions."""
    if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
        raise JsonRpcProtocolError(-32600, "Invalid JSON-RPC message")
    if "method" in data:
        if not isinstance(data["method"], str) or "result" in data or "error" in data:
            raise JsonRpcProtocolError(-32600, "Invalid request envelope")
        if "id" in data and mcp_response_id(data) is None:
            raise JsonRpcProtocolError(-32600, "Request id must be a string or integer")
        if "params" in data and not isinstance(data["params"], dict):
            raise JsonRpcProtocolError(-32600, "Invalid request params")
    elif "result" in data and "error" not in data:
        if mcp_response_id(data) is None or not isinstance(data["result"], dict):
            raise JsonRpcProtocolError(-32600, "Invalid result envelope")
    elif "error" in data and "result" not in data:
        error = data["error"]
        if (
            not isinstance(error, dict)
            or type(error.get("code")) is not int
            or not isinstance(error.get("message"), str)
            or (data.get("id") is not None and mcp_response_id(data) is None)
        ):
            raise JsonRpcProtocolError(-32600, "Invalid error envelope")
    else:
        raise JsonRpcProtocolError(-32600, "Invalid JSON-RPC message")
    return data


@dataclass
class HttpMessage:
    """A JSON-RPC message shared by HTTP protocol and compatibility policy."""

    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str | None = None
    params: dict[str, Any] | None = None
    result: Any | None = None
    error: dict[str, Any] | None = None

    def is_request(self) -> bool:
        return self.method is not None and self.id is not None

    def is_notification(self) -> bool:
        return self.method is not None and self.id is None

    def is_response(self) -> bool:
        return self.result is not None or self.error is not None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            data["id"] = self.id
        if self.method is not None:
            data["method"] = self.method
        if self.params is not None:
            data["params"] = self.params
        if self.result is not None:
            data["result"] = self.result
        if self.error is not None:
            data["error"] = self.error
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HttpMessage:
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error"),
        )


LEGACY_METHOD_MAP: dict[str, str] = {
    "list_experts": "deepr_list_experts",
    "get_expert_info": "deepr_get_expert_info",
    "query_expert": "deepr_query_expert",
    "expert_manifest": "deepr_expert_manifest",
    "expert_validate": "deepr_expert_validate",
    "rank_gaps": "deepr_rank_gaps",
    "expert_health_check": "deepr_expert_health_check",
    "route_gaps": "deepr_route_gaps",
    "expert_absorb": "deepr_expert_absorb",
    "reflect": "deepr_reflect",
    "what_changed": "deepr_what_changed",
    "contested": "deepr_contested",
    "explain_belief": "deepr_explain_belief",
    "temporal_edges": "deepr_temporal_edges",
}


def canonical_legacy_tool_call(
    method: str | None,
    params: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]] | None:
    """Return the canonical tool envelope for a valid legacy request."""
    tool_name = LEGACY_METHOD_MAP.get(method or "")
    if tool_name is None:
        return None
    if params is None:
        return tool_name, {}
    if isinstance(params, dict):
        return tool_name, dict(params)
    return None


__all__ = ["LEGACY_METHOD_MAP", "HttpMessage", "canonical_legacy_tool_call", "mcp_response_id", "validate_mcp_envelope"]
