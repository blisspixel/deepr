"""MCP client pool — manages multiple server connections with health monitoring.

Provides parallel dispatch across MCP servers, circuit breaker per server,
automatic fallback, budget/trace/progress integration, and aggregated health.
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


class MCPClientPool:
    """Manages a pool of MCP client connections.

    Features:
    - Named client registration from profiles (skips disabled)
    - Parallel tool dispatch across multiple servers
    - Per-server circuit breakers with half-open probe
    - Budget check, trace stitching, and progress relay
    - Aggregated health reporting

    Usage::

        pool = MCPClientPool()
        pool.register(profile)
        await pool.connect_all()

        result = await pool.call_tool("server-name", "tool-name", {"key": "val"})
        results = await pool.broadcast_tool("search", {"query": "test"})

        await pool.close_all()
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
            max_retries=profile.max_retries,
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
        """Connect a specific server by name."""
        client = self._clients.get(name)
        if not client:
            raise MCPClientError(f"Unknown server: {name}", server_name=name)
        await client.connect()

    async def connect_all(self) -> dict[str, str | None]:
        """Connect all registered (enabled) servers. Returns {name: error_or_none}."""
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
        estimated_cost: float = 0.0,
        session_remaining: float = 0.0,
    ) -> MCPToolResult | StructuredError:
        """Call a tool on a specific server with budget, trace, and circuit breaker.

        Integration order:
        1. Budget check (if propagator configured)
        2. Circuit breaker check
        3. Trace span creation (if stitcher configured)
        4. Dispatch call
        5. Record cost + complete span
        """
        client = self._clients.get(server_name)
        if not client:
            return MCPToolResult(
                error=f"Unknown server: {server_name}",
                server_name=server_name,
                tool_name=tool_name,
                trace_id=trace_id,
            )

        profile = self._profiles.get(server_name)

        # 1. Budget check
        if self._budget_propagator and profile and estimated_cost > 0:
            decision = self._budget_propagator.check_budget(
                profile, estimated_cost, session_remaining
            )
            if not decision.allowed:
                return StructuredError(
                    code=MCPErrorCode.BUDGET_EXCEEDED,
                    message=decision.reason,
                    retryable=False,
                    budget_shortfall=decision.shortfall,
                )

        # 2. Circuit breaker check
        circuit = self._circuits.get(server_name)
        if circuit and not circuit.is_available():
            return MCPToolResult(
                error=f"Circuit breaker open for '{server_name}' — server temporarily unavailable",
                server_name=server_name,
                tool_name=tool_name,
                trace_id=trace_id,
            )

        # 3. Trace span creation
        span = None
        call_args = arguments or {}
        if self._trace_stitcher and trace_id:
            span = self._trace_stitcher.create_span(trace_id, server_name, tool_name)
            call_args = self._trace_stitcher.inject_trace(call_args, span.trace_id, span.span_id)

        # 4. Dispatch
        result = await client.call_tool(tool_name, call_args, timeout, trace_id)

        # 5. Post-dispatch: circuit breaker update
        if circuit:
            if result.ok:
                circuit.record_success()
            else:
                circuit.record_failure()

        # 6. Record cost + complete span
        if self._budget_propagator and profile:
            actual_cost = result.raw.get("cost", 0.0) if result.ok else 0.0
            if actual_cost > 0:
                self._budget_propagator.record_cost(
                    server_name, tool_name, actual_cost, trace_id
                )

        if span and self._trace_stitcher:
            cost = result.raw.get("cost", 0.0) if result.ok else 0.0
            self._trace_stitcher.complete_span(span, result, cost)

        return result

    async def broadcast_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        server_names: list[str] | None = None,
        trace_id: str = "",
    ) -> list[MCPToolResult]:
        """Call the same tool on multiple servers concurrently.

        Preserves order of requested servers. Failed servers produce
        error results in their slot without blocking others.
        """
        targets = server_names or [
            name for name, client in self._clients.items() if client.connected
        ]
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
