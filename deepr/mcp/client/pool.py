"""MCP client pool — manages multiple server connections with health monitoring.

Provides parallel dispatch across MCP servers, circuit breaker per server,
automatic fallback, and aggregated health reporting.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from deepr.mcp.client.base import MCPClient, MCPClientError, MCPToolResult
from deepr.mcp.client.profile import MCPClientProfile
from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher

logger = logging.getLogger(__name__)


class _CircuitState:
    """Per-server circuit breaker state."""

    def __init__(self, threshold: int = 5, recovery_seconds: float = 60.0):
        self.threshold = threshold
        self.recovery_seconds = recovery_seconds
        self.failure_count = 0
        self.is_open = False
        self.opened_at: float = 0.0

    def record_success(self) -> None:
        self.failure_count = 0
        self.is_open = False

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.threshold:
            self.is_open = True
            self.opened_at = time.time()

    def is_available(self) -> bool:
        if not self.is_open:
            return True
        # Allow half-open after recovery period
        if time.time() - self.opened_at > self.recovery_seconds:
            return True
        return False


class MCPClientPool:
    """Manages a pool of MCP client connections.

    Features:
    - Named client registration from profiles
    - Parallel tool dispatch across multiple servers
    - Per-server circuit breakers
    - Aggregated health reporting

    Usage::

        pool = MCPClientPool()
        pool.register(profile)
        await pool.connect_all()

        result = await pool.call_tool("server-name", "tool-name", {"key": "val"})

        # Or dispatch same call to multiple servers
        results = await pool.broadcast_tool("search", {"query": "test"})

        await pool.close_all()
    """

    def __init__(self, max_concurrent: int = 5):
        self._clients: dict[str, MCPClient] = {}
        self._profiles: dict[str, MCPClientProfile] = {}
        self._circuits: dict[str, _CircuitState] = {}
        self._max_concurrent = max_concurrent

    def register(self, profile: MCPClientProfile) -> None:
        """Register an MCP server profile.

        Does not connect — call ``connect_all()`` or ``connect(name)`` after.
        """
        self._profiles[profile.name] = profile
        self._clients[profile.name] = MCPClient(
            name=profile.name,
            command=profile.command,
            args=profile.args,
            env=profile.env,
            timeout=profile.timeout,
            max_retries=profile.max_retries,
            retry_delay=profile.retry_delay,
        )
        self._circuits[profile.name] = _CircuitState(
            threshold=profile.circuit_breaker_threshold,
            recovery_seconds=profile.circuit_breaker_recovery,
        )

    def unregister(self, name: str) -> None:
        """Remove a server from the pool."""
        self._profiles.pop(name, None)
        self._clients.pop(name, None)
        self._circuits.pop(name, None)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self, name: str) -> None:
        """Connect a specific server by name."""
        client = self._clients.get(name)
        if not client:
            raise MCPClientError(f"Unknown server: {name}", server_name=name)
        await client.connect()

    async def connect_all(self) -> dict[str, str | None]:
        """Connect all registered servers. Returns {name: error_or_none}."""
        results: dict[str, str | None] = {}
        for name, client in self._clients.items():
            try:
                await client.connect()
                results[name] = None
            except MCPClientError as e:
                results[name] = str(e)
                logger.warning("Failed to connect MCP server '%s': %s", name, e)
        return results

    async def close(self, name: str) -> None:
        """Close a specific server connection."""
        client = self._clients.get(name)
        if client:
            await client.close()

    async def close_all(self) -> None:
        """Close all server connections."""
        for client in self._clients.values():
            await client.close()

    # ------------------------------------------------------------------
    # Tool calling
    # ------------------------------------------------------------------

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
        trace_id: str = "",
    ) -> MCPToolResult:
        """Call a tool on a specific server with circuit breaker protection."""
        client = self._clients.get(server_name)
        if not client:
            return MCPToolResult(
                error=f"Unknown server: {server_name}",
                server_name=server_name,
                tool_name=tool_name,
                trace_id=trace_id,
            )

        circuit = self._circuits.get(server_name)
        if circuit and not circuit.is_available():
            return MCPToolResult(
                error=f"Circuit breaker open for '{server_name}' — server temporarily unavailable",
                server_name=server_name,
                tool_name=tool_name,
                trace_id=trace_id,
            )

        result = await client.call_tool(tool_name, arguments, timeout, trace_id)

        # Update circuit breaker
        if circuit:
            if result.ok:
                circuit.record_success()
            else:
                circuit.record_failure()

        return result

    async def broadcast_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        server_names: list[str] | None = None,
        trace_id: str = "",
    ) -> list[MCPToolResult]:
        """Call the same tool on multiple servers in parallel.

        Args:
            tool_name: Tool to call on each server.
            arguments: Shared arguments.
            server_names: Specific servers (default: all connected).
            trace_id: Trace ID for correlation.

        Returns:
            List of results, one per server attempted.
        """
        targets = server_names or [name for name, client in self._clients.items() if client.connected]

        if not targets:
            return []

        dispatcher = AsyncTaskDispatcher(max_concurrent=self._max_concurrent)

        async def _call(name: str) -> MCPToolResult:
            return await self.call_tool(name, tool_name, arguments, trace_id=trace_id)

        dispatch_tasks = [{"id": name, "coro": _call(name)} for name in targets]
        dispatch_result = await dispatcher.dispatch(dispatch_tasks)

        results: list[MCPToolResult] = []
        for name in targets:
            task = dispatch_result.tasks.get(name)
            if task and task.result is not None:
                results.append(task.result)
            else:
                results.append(
                    MCPToolResult(
                        error=f"Dispatch failed for '{name}'",
                        server_name=name,
                        tool_name=tool_name,
                        trace_id=trace_id,
                    )
                )

        return results

    # ------------------------------------------------------------------
    # Health & discovery
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Aggregated health report across all servers."""
        servers = {}
        for name, client in self._clients.items():
            h = client.health()
            circuit = self._circuits.get(name)
            if circuit:
                h["circuit_open"] = circuit.is_open
            servers[name] = h

        connected = sum(1 for c in self._clients.values() if c.connected)
        return {
            "total_servers": len(self._clients),
            "connected": connected,
            "disconnected": len(self._clients) - connected,
            "servers": servers,
        }

    def list_all_tools(self) -> list[dict[str, Any]]:
        """List all tools available across all connected servers."""
        tools = []
        for name, client in self._clients.items():
            if not client.connected:
                continue
            for tool in client.available_tools:
                tools.append(
                    {
                        "server": name,
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "inputSchema": tool.get("inputSchema", {}),
                    }
                )
        return tools

    def __len__(self) -> int:
        return len(self._clients)

    def __contains__(self, name: str) -> bool:
        return name in self._clients
