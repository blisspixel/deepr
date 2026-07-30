"""Release-blocked outbound MCP profile inventory and health state.

Connection and tool dispatch remain disabled until Deepr can prove immutable
executable provenance and enforce durable cost reservation and settlement.
"""

from __future__ import annotations

import logging
from typing import Any

from deepr.mcp.client.base import MCPClient, MCPClientError, MCPToolResult
from deepr.mcp.client.budget_propagator import BudgetPropagator
from deepr.mcp.client.circuit_breaker import CircuitBreaker
from deepr.mcp.client.config_loader import ConfigLoader
from deepr.mcp.client.errors import MCPErrorCode, StructuredError
from deepr.mcp.client.profile import MCPClientProfile
from deepr.mcp.client.progress_notifier import ProgressNotifier
from deepr.mcp.client.trace_stitcher import TraceStitcher
from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher

logger = logging.getLogger(__name__)

_OUTBOUND_MCP_CONNECTION_BLOCK = (
    "Outbound MCP connection is disabled until Deepr can bind immutable executable provenance, "
    "prove zero-dollar behavior, and durably account for every metered tool."
)


class MCPClientPool:
    """Manage profiles while failing closed at every outbound boundary.

    Features:
    - Named client registration from profiles (skips disabled)
    - Single-attempt client construction for future audited use
    - Fail-closed connection, direct call, and broadcast entry points
    - Aggregated non-connected health reporting
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        budget_propagator: BudgetPropagator | None = None,
        trace_stitcher: TraceStitcher | None = None,
        progress_notifier: ProgressNotifier | None = None,
    ) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._profiles: dict[str, MCPClientProfile] = {}
        self._circuits: dict[str, CircuitBreaker] = {}
        self._max_concurrent = max_concurrent
        self._budget_propagator = budget_propagator
        self._trace_stitcher = trace_stitcher
        self._progress_notifier = progress_notifier

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, profile: MCPClientProfile) -> None:
        """Register an MCP server profile. Skips disabled profiles."""
        if not profile.enabled:
            logger.debug("Skipping disabled profile: %s", profile.name)
            return
        self._profiles[profile.name] = profile
        self._clients[profile.name] = MCPClient(
            name=profile.name,
            command=profile.command,
            args=profile.args,
            env=profile.env,
            timeout=profile.timeout,
            # A logical pool call can never replay an ambiguous tool request.
            # Profiles cannot relax this boundary.
            max_retries=1,
            retry_delay=profile.retry_delay,
        )
        self._circuits[profile.name] = CircuitBreaker(
            threshold=profile.circuit_breaker_threshold,
            recovery_seconds=profile.circuit_breaker_recovery,
        )

    def unregister(self, name: str) -> None:
        """Remove a server from the pool."""
        self._profiles.pop(name, None)
        self._clients.pop(name, None)
        self._circuits.pop(name, None)

    def load_from_config(self, config_loader: ConfigLoader) -> list[str]:
        """Load profiles from YAML config and register enabled ones.

        Returns list of registered profile names.
        """
        profiles = config_loader.load()
        registered: list[str] = []
        for profile in profiles:
            self.register(profile)
            if profile.enabled:
                registered.append(profile.name)
        return registered

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self, name: str) -> None:
        """Refuse connection until the outbound release gate is implemented."""
        client = self._clients.get(name)
        if not client:
            raise MCPClientError(f"Unknown server: {name}", server_name=name)
        raise MCPClientError(_OUTBOUND_MCP_CONNECTION_BLOCK, server_name=name)

    async def connect_all(self) -> dict[str, str | None]:
        """Return the release-block reason for every registered server."""
        return {name: _OUTBOUND_MCP_CONNECTION_BLOCK for name in self._clients}

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
        estimated_cost: float = 0.0,
        session_remaining: float = 0.0,
    ) -> MCPToolResult | StructuredError:
        """Refuse outbound MCP until executable provenance and accounting exist."""
        client = self._clients.get(server_name)
        if not client:
            return MCPToolResult(
                error=f"Unknown server: {server_name}",
                server_name=server_name,
                tool_name=tool_name,
                trace_id=trace_id,
            )

        return StructuredError(
            code=MCPErrorCode.COST_ACCOUNTING_UNAVAILABLE,
            message=(
                f"Outbound MCP tool '{server_name}/{tool_name}' lacks immutable executable and zero-dollar proof; "
                "execution is disabled until deterministic maximum-cost reservation and settlement are available."
            ),
            retryable=False,
            fallback_suggestion=(
                "Use Deepr-owned local or safety-eligible plan-quota capacity, or run metered work through a "
                "durable Deepr budget gate; profile.free_tools alone cannot authorize dispatch."
            ),
        )

    async def broadcast_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        server_names: list[str] | None = None,
        trace_id: str = "",
    ) -> list[MCPToolResult]:
        """Return one release-blocked result per requested server.

        Preserves order so callers get a deterministic explanation for every
        target without starting a subprocess or reaching a remote endpoint.
        """
        targets = server_names or [name for name, client in self._clients.items() if client.connected]
        if not targets:
            return []

        dispatcher = AsyncTaskDispatcher(max_concurrent=self._max_concurrent)

        async def _call(name: str) -> MCPToolResult:
            result = await self.call_tool(name, tool_name, arguments, trace_id=trace_id)
            # call_tool may return StructuredError; wrap it as MCPToolResult
            if isinstance(result, StructuredError):
                return MCPToolResult(
                    error=result.message,
                    server_name=name,
                    tool_name=tool_name,
                    trace_id=trace_id,
                )
            return result

        dispatch_tasks = [{"id": name, "coro": _call(name)} for name in targets]
        dispatch_result = await dispatcher.dispatch(dispatch_tasks)

        # Preserve order of targets
        results: list[MCPToolResult] = []
        for name in targets:
            task = dispatch_result.tasks.get(name)
            if task and task.result is not None:
                results.append(task.result)
            else:
                error_msg = task.error if task else f"Dispatch failed for '{name}'"
                results.append(
                    MCPToolResult(
                        error=error_msg or f"Dispatch failed for '{name}'",
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
                h["circuit_state"] = circuit.state.value
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
