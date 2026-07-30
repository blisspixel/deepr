"""Tests for the release-blocked outbound MCP client contract."""

from unittest.mock import AsyncMock, patch

import pytest

from deepr.mcp.client.base import MCPClient, MCPClientError, MCPToolResult


class TestMCPToolResult:
    def test_ok_when_no_error(self):
        result = MCPToolResult(content="hello")
        assert result.ok is True

    def test_not_ok_when_error(self):
        result = MCPToolResult(error="failed")
        assert result.ok is False

    def test_to_dict(self):
        result = MCPToolResult(content="hi", server_name="s1", tool_name="t1", latency_ms=42.567)
        serialized = result.to_dict()
        assert serialized["content"] == "hi"
        assert serialized["latency_ms"] == 42.6
        assert serialized["server_name"] == "s1"


class TestMCPClientSafety:
    def test_child_environment_excludes_unrelated_parent_secrets(self, monkeypatch):
        monkeypatch.setenv("PATH", "validation-path")
        monkeypatch.setenv("DEEPR_VALIDATION_SELECTED", "selected-value")
        monkeypatch.setenv("OPENAI_API_KEY", "unrelated-secret")

        client = MCPClient(
            name="test",
            command="echo",
            env={"CHILD_TOKEN": "${DEEPR_VALIDATION_SELECTED}"},
        )

        assert client.env["PATH"] == "validation-path"
        assert client.env["CHILD_TOKEN"] == "selected-value"
        assert "OPENAI_API_KEY" not in client.env
        assert "DEEPR_VALIDATION_SELECTED" not in client.env

    @pytest.mark.asyncio
    async def test_connect_fails_before_subprocess_spawn(self):
        spawn = AsyncMock(side_effect=AssertionError("must not spawn"))
        client = MCPClient(name="paid-server", command="paid-mcp", args=["serve"])

        with patch("asyncio.create_subprocess_exec", spawn):
            with pytest.raises(MCPClientError, match="dispatch authority was not found"):
                await client.connect()

        spawn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_call_tool_fails_before_connect_or_subprocess(self):
        spawn = AsyncMock(side_effect=AssertionError("must not spawn"))
        client = MCPClient(name="paid-server", command="paid-mcp", max_retries=999)
        client.connect = AsyncMock(side_effect=AssertionError("must not connect"))

        with patch("asyncio.create_subprocess_exec", spawn):
            with pytest.raises(MCPClientError, match="durably reserve and settle"):
                await client.call_tool("expensive_tool", {"budget": 999})

        client.connect.assert_not_awaited()
        spawn.assert_not_awaited()
        assert client.max_retries == 1

    @pytest.mark.parametrize("timeout", [0.0, -1.0, float("nan"), float("inf"), True])
    def test_rejects_invalid_timeout(self, timeout):
        with pytest.raises(ValueError, match="finite positive"):
            MCPClient(name="test", command="echo", timeout=timeout)

    @pytest.mark.parametrize("retry_delay", [-1.0, float("nan"), float("inf"), True])
    def test_rejects_invalid_retry_delay(self, retry_delay):
        with pytest.raises(ValueError, match="finite non-negative"):
            MCPClient(name="test", command="echo", retry_delay=retry_delay)

    @pytest.mark.asyncio
    async def test_health_and_close_remain_inert(self):
        client = MCPClient(name="my-server", command="echo")
        client._connected = True
        client._available_tools = [{"name": "stale"}]

        await client.close()

        assert client.connected is False
        assert client.available_tools == []
        assert client.health() == {
            "name": "my-server",
            "connected": False,
            "pid": None,
            "tools": 0,
            "stats": client.stats.to_dict(),
        }
        assert "disconnected" in repr(client)
