"""Unit tests for MCP client pool extensions.

Tests:
- connect_all skips disabled profiles
- call_tool returns budget error when over budget
- call_tool injects trace_id into arguments
- broadcast_tool returns partial results on failure
- health() includes circuit state
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.mcp.client.base import MCPToolResult
from deepr.mcp.client.budget_propagator import BudgetPropagator
from deepr.mcp.client.circuit_breaker import CircuitState
from deepr.mcp.client.errors import MCPErrorCode, StructuredError
from deepr.mcp.client.pool import MCPClientPool
from deepr.mcp.client.profile import MCPClientProfile
from deepr.mcp.client.trace_stitcher import TraceStitcher


def _make_profile(name: str, enabled: bool = True) -> MCPClientProfile:
    return MCPClientProfile(name=name, command="echo", args=["test"], enabled=enabled)


class TestDisabledProfileExclusion:
    """Test that disabled profiles are excluded from the pool."""

    def test_register_skips_disabled(self):
        pool = MCPClientPool()
        pool.register(_make_profile("enabled-server", enabled=True))
        pool.register(_make_profile("disabled-server", enabled=False))

        assert "enabled-server" in pool
        assert "disabled-server" not in pool
        assert len(pool) == 1

    @pytest.mark.asyncio
    async def test_connect_all_only_connects_enabled(self):
        pool = MCPClientPool()
        pool.register(_make_profile("server-a", enabled=True))
        pool.register(_make_profile("disabled", enabled=False))

        # Mock the client connect to track calls
        pool._clients["server-a"].connect = AsyncMock()

        await pool.connect_all()

        pool._clients["server-a"].connect.assert_called_once()
        # disabled server should not be in pool at all
        assert "disabled" not in pool._clients


class TestBudgetIntegration:
    """Test call_tool returns budget error when over budget."""

    @pytest.mark.asyncio
    async def test_call_tool_budget_exceeded(self):
        # Create a mock budget propagator
        mock_manager = MagicMock()
        mock_manager.get_remaining_budget.return_value = 1.0
        mock_ledger = MagicMock()

        propagator = BudgetPropagator(budget_manager=mock_manager, cost_ledger=mock_ledger)

        pool = MCPClientPool(budget_propagator=propagator)
        pool.register(
            MCPClientProfile(
                name="expensive-server",
                command="echo",
                budget_limit=2.0,
            )
        )
        pool._clients["expensive-server"]._connected = True

        # Call with cost exceeding budget
        result = await pool.call_tool(
            "expensive-server",
            "tool",
            {},
            estimated_cost=5.0,
            session_remaining=1.0,
        )

        assert isinstance(result, StructuredError)
        assert result.code == MCPErrorCode.BUDGET_EXCEEDED
        assert result.retryable is False
        assert result.budget_shortfall > 0

    @pytest.mark.asyncio
    async def test_call_tool_budget_allowed(self):
        mock_manager = MagicMock()
        mock_manager.get_remaining_budget.return_value = 10.0
        mock_ledger = MagicMock()

        propagator = BudgetPropagator(budget_manager=mock_manager, cost_ledger=mock_ledger)

        pool = MCPClientPool(budget_propagator=propagator)
        pool.register(_make_profile("server-a"))
        pool._clients["server-a"]._connected = True
        pool._clients["server-a"].call_tool = AsyncMock(
            return_value=MCPToolResult(content="ok", server_name="server-a", tool_name="t")
        )

        result = await pool.call_tool("server-a", "t", {}, estimated_cost=1.0, session_remaining=10.0)

        assert isinstance(result, MCPToolResult)
        assert result.ok


class TestTraceInjection:
    """Test call_tool injects trace_id into arguments."""

    @pytest.mark.asyncio
    async def test_call_tool_injects_trace(self):
        mock_emitter = MagicMock()
        stitcher = TraceStitcher(metadata_emitter=mock_emitter)

        pool = MCPClientPool(trace_stitcher=stitcher)
        pool.register(_make_profile("server-a"))
        pool._clients["server-a"]._connected = True

        captured_args = {}

        async def capture_call(tool_name, arguments, timeout, trace_id):
            captured_args.update(arguments)
            return MCPToolResult(content="ok", server_name="server-a", tool_name=tool_name)

        pool._clients["server-a"].call_tool = capture_call

        await pool.call_tool("server-a", "lookup", {"domain": "example.com"}, trace_id="trace-abc")

        assert "trace_id" in captured_args
        assert "span_id" in captured_args
        assert captured_args["trace_id"] == "trace-abc"
        assert captured_args["domain"] == "example.com"


class TestBroadcastPartialResults:
    """Test broadcast_tool returns partial results on failure."""

    @pytest.mark.asyncio
    async def test_broadcast_partial_results(self):
        pool = MCPClientPool()

        # Register two servers: one succeeds, one fails
        pool.register(_make_profile("good-server"))
        pool.register(_make_profile("bad-server"))

        pool._clients["good-server"]._connected = True
        pool._clients["good-server"].call_tool = AsyncMock(
            return_value=MCPToolResult(content="success", server_name="good-server", tool_name="search")
        )

        pool._clients["bad-server"]._connected = True
        pool._clients["bad-server"].call_tool = AsyncMock(
            return_value=MCPToolResult(error="connection lost", server_name="bad-server", tool_name="search")
        )

        results = await pool.broadcast_tool("search", {"q": "test"}, server_names=["good-server", "bad-server"])

        assert len(results) == 2
        # First result (good-server) should succeed
        assert results[0].ok
        assert results[0].content == "success"
        # Second result (bad-server) should have error
        assert not results[1].ok
        assert results[1].server_name == "bad-server"


class TestHealthCircuitState:
    """Test health() includes circuit state."""

    def test_health_includes_circuit_state_closed(self):
        pool = MCPClientPool()
        pool.register(_make_profile("server-a"))

        report = pool.health()
        assert report["servers"]["server-a"]["circuit_state"] == "closed"

    def test_health_includes_circuit_state_open(self):
        pool = MCPClientPool()
        pool.register(_make_profile("server-a"))

        # Force circuit open
        pool._circuits["server-a"]._state = CircuitState.OPEN
        pool._circuits["server-a"]._opened_at = 9999999999.0

        report = pool.health()
        assert report["servers"]["server-a"]["circuit_state"] == "open"

    def test_health_includes_circuit_state_half_open(self):
        pool = MCPClientPool()
        pool.register(_make_profile("server-a"))

        # Force circuit to half-open (open + recovery elapsed)
        pool._circuits["server-a"]._state = CircuitState.OPEN
        pool._circuits["server-a"]._opened_at = 0.0  # Far in the past

        report = pool.health()
        assert report["servers"]["server-a"]["circuit_state"] == "half-open"
