"""Tests for MCP client pool — multi-server management, circuit breakers."""

from unittest.mock import AsyncMock

import pytest

from deepr.mcp.client.base import MCPToolResult
from deepr.mcp.client.pool import MCPClientPool, _CircuitState
from deepr.mcp.client.profile import MCPClientProfile


class TestCircuitState:
    def test_initially_closed(self):
        cs = _CircuitState(threshold=3)
        assert cs.is_available()
        assert not cs.is_open

    def test_opens_after_threshold(self):
        cs = _CircuitState(threshold=3, recovery_seconds=60.0)
        cs.record_failure()
        cs.record_failure()
        assert cs.is_available()
        cs.record_failure()
        assert cs.is_open
        assert not cs.is_available()

    def test_success_resets(self):
        cs = _CircuitState(threshold=2)
        cs.record_failure()
        cs.record_failure()
        assert cs.is_open
        cs.record_success()
        assert not cs.is_open
        assert cs.is_available()

    def test_recovery_allows_retry(self):
        cs = _CircuitState(threshold=1, recovery_seconds=0.01)
        cs.record_failure()
        assert cs.is_open
        # Manually set opened_at to the past so recovery period has elapsed
        cs.opened_at = 0.0
        assert cs.is_available()


class TestMCPClientPool:
    def _make_profile(self, name: str) -> MCPClientProfile:
        return MCPClientProfile(
            name=name,
            command="echo",
            args=["test"],
            timeout=5.0,
        )

    def test_register_and_contains(self):
        pool = MCPClientPool()
        pool.register(self._make_profile("server-a"))
        assert "server-a" in pool
        assert len(pool) == 1

    def test_unregister(self):
        pool = MCPClientPool()
        pool.register(self._make_profile("server-a"))
        pool.unregister("server-a")
        assert "server-a" not in pool
        assert len(pool) == 0

    @pytest.mark.asyncio
    async def test_call_unknown_server(self):
        pool = MCPClientPool()
        result = await pool.call_tool("nonexistent", "tool", {})
        assert not result.ok
        assert "Unknown server" in result.error

    @pytest.mark.asyncio
    async def test_call_circuit_open(self):
        pool = MCPClientPool()
        pool.register(self._make_profile("server-a"))
        # Force circuit open
        pool._circuits["server-a"].is_open = True
        pool._circuits["server-a"].opened_at = 9999999999.0  # Far future

        result = await pool.call_tool("server-a", "tool", {})
        assert not result.ok
        assert "Circuit breaker open" in result.error

    @pytest.mark.asyncio
    async def test_call_success_resets_circuit(self):
        pool = MCPClientPool()
        pool.register(self._make_profile("server-a"))

        # Mock the client to return success
        mock_result = MCPToolResult(content="ok", server_name="server-a", tool_name="test")
        pool._clients["server-a"].call_tool = AsyncMock(return_value=mock_result)
        pool._clients["server-a"]._connected = True

        # Set circuit to have some failures
        pool._circuits["server-a"].failure_count = 2

        result = await pool.call_tool("server-a", "test", {})
        assert result.ok
        assert pool._circuits["server-a"].failure_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_tool(self):
        pool = MCPClientPool()

        for name in ["server-a", "server-b"]:
            pool.register(self._make_profile(name))
            mock_result = MCPToolResult(content=f"result-{name}", server_name=name, tool_name="search")
            pool._clients[name].call_tool = AsyncMock(return_value=mock_result)
            pool._clients[name]._connected = True

        results = await pool.broadcast_tool("search", {"query": "test"}, server_names=["server-a", "server-b"])

        assert len(results) == 2
        contents = {r.content for r in results}
        assert "result-server-a" in contents
        assert "result-server-b" in contents

    def test_health_report(self):
        pool = MCPClientPool()
        pool.register(self._make_profile("server-a"))
        pool.register(self._make_profile("server-b"))

        h = pool.health()
        assert h["total_servers"] == 2
        assert h["connected"] == 0
        assert h["disconnected"] == 2
        assert "server-a" in h["servers"]
        assert "server-b" in h["servers"]

    def test_list_all_tools_empty_when_disconnected(self):
        pool = MCPClientPool()
        pool.register(self._make_profile("server-a"))
        assert pool.list_all_tools() == []
