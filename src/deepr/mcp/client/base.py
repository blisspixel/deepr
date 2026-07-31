"""Release-blocked outbound MCP client contracts.

The profile inventory remains available so users can inspect prospective MCP
servers. Subprocess startup and tool dispatch are intentionally unavailable
until Deepr can bind an immutable executable identity to a durable cost
reservation and conservative settlement.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any

# Outbound handshake revision when dispatch is unblocked. Deepr-as-client
# still opens with the legacy initialize handshake (broadest server compat);
# a stateless 2026-07-28 client mode lands with the dispatch unblock itself.
MCP_PROTOCOL_VERSION = "2025-06-18"
_MCP_CHILD_ENV_ALLOWLIST = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "WINDIR",
    }
)
_OUTBOUND_MCP_BLOCK = (
    "Outbound MCP dispatch authority was not found. Connection and tool calls are disabled until Deepr can "
    "prove immutable executable provenance and durably reserve and settle every possible cost."
)


class MCPClientError(Exception):
    """Error from an MCP client operation."""

    def __init__(self, message: str, server_name: str = "", retryable: bool = False):
        super().__init__(message)
        self.server_name = server_name
        self.retryable = retryable


@dataclass
class MCPToolResult:
    """Result contract retained for inventory and blocked-dispatch callers."""

    content: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    latency_ms: float = 0.0
    server_name: str = ""
    tool_name: str = ""
    trace_id: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "error": self.error,
            "latency_ms": round(self.latency_ms, 1),
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "trace_id": self.trace_id,
        }


@dataclass
class _ConnectionStats:
    """Health shape retained while outbound connections are disabled."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_latency_ms: float = 0.0
    last_error: str = ""
    last_error_time: float = 0.0
    connected_since: float = 0.0
    reconnect_count: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_calls == 0:
            return 0.0
        return self.total_latency_ms / self.successful_calls

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": round(self.success_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "reconnect_count": self.reconnect_count,
            "last_error": self.last_error,
        }


class MCPClient:
    """Read-only MCP server profile that fails closed on outbound work."""

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 1,
        retry_delay: float = 1.0,
    ) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("MCP timeout must be a finite positive number")
        if not math.isfinite(float(timeout)) or float(timeout) <= 0:
            raise ValueError("MCP timeout must be a finite positive number")
        if isinstance(retry_delay, bool) or not isinstance(retry_delay, (int, float)):
            raise ValueError("MCP retry delay must be a finite non-negative number")
        if not math.isfinite(float(retry_delay)) or float(retry_delay) < 0:
            raise ValueError("MCP retry delay must be a finite non-negative number")

        self.name = name
        self.command = command
        self.args = args or []
        runtime_env = {key: value for key, value in os.environ.items() if key.upper() in _MCP_CHILD_ENV_ALLOWLIST}
        self.env = {**runtime_env, **self._resolve_env(env or {})}
        self.timeout = float(timeout)
        # Ambiguous side effects must never be replayed. Caller values cannot
        # widen this invariant, even though dispatch is currently blocked.
        self.max_retries = 1
        self.retry_delay = float(retry_delay)
        self._connected = False
        self._stats = _ConnectionStats()
        self._available_tools: list[dict[str, Any]] = []

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def stats(self) -> _ConnectionStats:
        return self._stats

    @property
    def available_tools(self) -> list[dict[str, Any]]:
        return self._available_tools

    async def connect(self) -> None:
        """Refuse subprocess startup before any executable can run."""
        raise MCPClientError(_OUTBOUND_MCP_BLOCK, server_name=self.name)

    async def reconnect(self) -> None:
        """Refuse reconnection for the same reason as initial connection."""
        raise MCPClientError(_OUTBOUND_MCP_BLOCK, server_name=self.name)

    async def close(self) -> None:
        """Clear inert local state without starting or contacting a server."""
        self._connected = False
        self._available_tools = []

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
        trace_id: str = "",
    ) -> MCPToolResult:
        """Refuse tool dispatch before any subprocess or JSON-RPC write."""
        del tool_name, arguments, timeout, trace_id
        raise MCPClientError(_OUTBOUND_MCP_BLOCK, server_name=self.name)

    @staticmethod
    def _resolve_env(env: dict[str, str]) -> dict[str, str]:
        """Resolve explicit environment references from the sanitized parent."""
        resolved = {}
        for key, value in env.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                resolved[key] = os.environ.get(value[2:-1], "")
            else:
                resolved[key] = str(value)
        return resolved

    def health(self) -> dict[str, Any]:
        """Return deterministic disconnected health for this profile."""
        return {
            "name": self.name,
            "connected": False,
            "pid": None,
            "tools": 0,
            "stats": self._stats.to_dict(),
        }

    def __repr__(self) -> str:
        return f"MCPClient(name={self.name!r}, disconnected, tools=0)"
