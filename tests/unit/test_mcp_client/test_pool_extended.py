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
from deepr.mcp.client.config_loader import get_recon_profile
from deepr.mcp.client.errors import MCPErrorCode, StructuredError
from deepr.mcp.client.pool import MCPClientPool
from deepr.mcp.client.profile import MCPClientProfile
from deepr.mcp.client.trace_stitcher import TraceStitcher


def _make_profile(name: str, enabled: bool = True) -> MCPClientProfile:
    return MCPClientProfile(
        name=name,
        command="echo",
        args=["test"],
        enabled=enabled,
        max_retries=1,
        free_tools=["lookup", "search", "t"],
    )


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

        result = await pool.connect_all()

        pool._clients["server-a"].connect.assert_not_awaited()
        assert "immutable executable provenance" in result["server-a"]
        # disabled server should not be in pool at all
        assert "disabled" not in pool._clients


class TestBudgetIntegration:
    """Test call_tool returns budget error when over budget."""

    @pytest.mark.asyncio
    async def test_positive_estimate_is_refused_before_budget_or_dispatch(self):
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
                max_retries=1,
                free_tools=["tool"],
            )
        )
        pool._clients["expensive-server"]._connected = True
        call = AsyncMock(side_effect=AssertionError("a positive estimate must not dispatch"))
        pool._clients["expensive-server"].call_tool = call

        result = await pool.call_tool(
            "expensive-server",
            "tool",
            {},
            estimated_cost=5.0,
            session_remaining=1.0,
        )

        assert isinstance(result, StructuredError)
        assert result.code == MCPErrorCode.COST_ACCOUNTING_UNAVAILABLE
        assert result.retryable is False
        assert "lacks immutable executable and zero-dollar proof" in result.message
        call.assert_not_awaited()
        mock_ledger.record_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_estimate_cannot_bypass_release_block(self):
        mock_manager = MagicMock()
        mock_manager.get_remaining_budget.return_value = 10.0
        mock_ledger = MagicMock()

        propagator = BudgetPropagator(budget_manager=mock_manager, cost_ledger=mock_ledger)

        pool = MCPClientPool(budget_propagator=propagator)
        pool.register(_make_profile("server-a"))
        pool._clients["server-a"]._connected = True
        call = AsyncMock(side_effect=AssertionError("zero estimate must not dispatch"))
        pool._clients["server-a"].call_tool = call

        result = await pool.call_tool("server-a", "t", {}, estimated_cost=0.0, session_remaining=10.0)

        assert isinstance(result, StructuredError)
        assert result.code == MCPErrorCode.COST_ACCOUNTING_UNAVAILABLE
        call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unclassified_tool_is_refused_before_dispatch_even_with_estimate(self):
        mock_manager = MagicMock()
        mock_ledger = MagicMock()
        propagator = BudgetPropagator(budget_manager=mock_manager, cost_ledger=mock_ledger)
        pool = MCPClientPool(budget_propagator=propagator)
        pool.register(MCPClientProfile(name="paid-server", command="echo", budget_limit=5.0))
        call = AsyncMock(side_effect=AssertionError("unclassified remote tool must not run"))
        pool._clients["paid-server"].call_tool = call

        result = await pool.call_tool(
            "paid-server",
            "research_company",
            {},
            estimated_cost=1.0,
            session_remaining=10.0,
        )

        assert isinstance(result, StructuredError)
        assert result.code == MCPErrorCode.COST_ACCOUNTING_UNAVAILABLE
        assert "lacks immutable executable and zero-dollar proof" in result.message
        call.assert_not_awaited()
        mock_ledger.record_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_profile_fields_cannot_authorize_outbound_mcp(self):
        pool = MCPClientPool()
        profile = _make_profile("trusted-server")
        pool.register(profile)
        call = AsyncMock(side_effect=AssertionError("tampered profile must not dispatch"))
        pool._clients[profile.name].call_tool = call

        result = await pool.call_tool(profile.name, "lookup", {})

        assert isinstance(result, StructuredError)
        assert result.code == MCPErrorCode.COST_ACCOUNTING_UNAVAILABLE
        call.assert_not_awaited()


class TestBuiltInProfileReleaseBlock:
    @pytest.mark.asyncio
    async def test_deepr_curated_profile_fails_closed_without_executable_provenance(self):
        pool = MCPClientPool()
        profile = get_recon_profile()
        pool.register(profile)
        call = AsyncMock(side_effect=AssertionError("PATH-discovered profile must not dispatch"))
        pool._clients[profile.name].call_tool = call

        result = await pool.call_tool(profile.name, "lookup_tenant", {"domain": "example.com"})

        assert isinstance(result, StructuredError)
        assert result.code == MCPErrorCode.COST_ACCOUNTING_UNAVAILABLE
        call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_serialized_curated_profile_clone_loses_dispatch_authority(self):
        original = get_recon_profile()
        clone = MCPClientProfile.from_dict(original.to_dict())
        pool = MCPClientPool()
        pool.register(clone)
        call = AsyncMock(side_effect=AssertionError("serialized authority must not dispatch"))
        pool._clients[clone.name].call_tool = call

        result = await pool.call_tool(clone.name, "lookup_tenant", {"domain": "example.com"})

        assert isinstance(result, StructuredError)
        assert result.code == MCPErrorCode.COST_ACCOUNTING_UNAVAILABLE
        call.assert_not_awaited()


class TestTraceInjection:
    """Trace setup cannot cross the release block."""

    @pytest.mark.asyncio
    async def test_call_tool_injects_trace(self):
        mock_emitter = MagicMock()
        stitcher = TraceStitcher(metadata_emitter=mock_emitter)

        pool = MCPClientPool(trace_stitcher=stitcher)
        pool.register(_make_profile("server-a"))
        pool._clients["server-a"]._connected = True

        call = AsyncMock(side_effect=AssertionError("trace metadata must not dispatch"))
        pool._clients["server-a"].call_tool = call

        result = await pool.call_tool("server-a", "lookup", {"domain": "example.com"}, trace_id="trace-abc")

        assert isinstance(result, StructuredError)
        call.assert_not_awaited()
        mock_emitter.emit.assert_not_called()


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
        assert all(not result.ok for result in results)
        assert all("immutable executable" in result.error for result in results)
        pool._clients["good-server"].call_tool.assert_not_awaited()
        pool._clients["bad-server"].call_tool.assert_not_awaited()


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
