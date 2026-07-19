"""Shared compatibility aliases for legacy MCP method names."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HttpMessage:
    """A JSON-RPC message shared by HTTP protocol and compatibility policy."""

    jsonrpc: str = "2.0"
    id: str | None = None
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


__all__ = ["LEGACY_METHOD_MAP", "HttpMessage", "canonical_legacy_tool_call"]
