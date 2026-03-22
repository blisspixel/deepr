"""Tests for MCP client base — connection, retry, health tracking."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.mcp.client.base import MCPClient, MCPClientError, MCPToolResult


def _mock_process(responses: list[dict]):
    """Create a mock subprocess that returns JSON-RPC responses."""
    proc = AsyncMock()
    proc.returncode = None
    proc.pid = 12345

    stdin = MagicMock()
    stdin.write = MagicMock()
    stdin.drain = AsyncMock()
    proc.stdin = stdin

    stdout = AsyncMock()
    response_lines = [json.dumps(r).encode() + b"\n" for r in responses]
    stdout.readline = AsyncMock(side_effect=response_lines)
    proc.stdout = stdout

    proc.stderr = AsyncMock()
    proc.wait = AsyncMock()
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    return proc


class TestMCPToolResult:
    def test_ok_when_no_error(self):
        r = MCPToolResult(content="hello")
        assert r.ok is True

    def test_not_ok_when_error(self):
        r = MCPToolResult(error="failed")
        assert r.ok is False

    def test_to_dict(self):
        r = MCPToolResult(content="hi", server_name="s1", tool_name="t1", latency_ms=42.567)
        d = r.to_dict()
        assert d["content"] == "hi"
        assert d["latency_ms"] == 42.6
        assert d["server_name"] == "s1"


class TestMCPClientConnect:
    @pytest.mark.asyncio
    async def test_connect_initializes(self):
        """Connect should spawn subprocess and do MCP handshake."""
        init_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": True},
            },
        }
        tools_response = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "tools": [
                    {"name": "search", "description": "Search things"},
                ],
            },
        }
        proc = _mock_process([init_response, tools_response])

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            client = MCPClient(name="test", command="echo")
            await client.connect()

            assert client.connected
            assert len(client.available_tools) == 1
            assert client.available_tools[0]["name"] == "search"

            await client.close()
            assert not client.connected

    @pytest.mark.asyncio
    async def test_connect_failure_raises(self):
        """Failed subprocess spawn should raise MCPClientError."""
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("not found")):
            client = MCPClient(name="bad", command="nonexistent")
            with pytest.raises(MCPClientError, match="not found"):
                await client.connect()


class TestMCPClientCallTool:
    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Tool call should extract text content from response."""
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}
        tool_resp = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "content": [{"type": "text", "text": "search result"}],
            },
        }
        proc = _mock_process([init_resp, tool_resp])

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            client = MCPClient(name="test", command="echo", max_retries=1)
            await client.connect()

            result = await client.call_tool("search", {"query": "test"}, trace_id="t1")

            assert result.ok
            assert result.content == "search result"
            assert result.trace_id == "t1"
            assert result.latency_ms >= 0
            assert client.stats.successful_calls == 1

            await client.close()

    @pytest.mark.asyncio
    async def test_error_response(self):
        """Server error should be captured in result."""
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}
        error_resp = {"jsonrpc": "2.0", "id": 2, "error": {"code": -1, "message": "bad request"}}
        proc = _mock_process([init_resp, error_resp])

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            client = MCPClient(name="test", command="echo", max_retries=1)
            await client.connect()

            result = await client.call_tool("bad_tool", {})

            assert not result.ok
            assert "bad request" in result.error
            assert client.stats.failed_calls == 1

            await client.close()

    @pytest.mark.asyncio
    async def test_timeout_retries(self):
        """Timeout should trigger retry with backoff."""
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}

        # Process that hangs (readline never returns in time)
        proc = _mock_process([init_resp])
        # Override readline to block forever after init
        call_count = 0

        async def slow_readline():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                # Init response
                return json.dumps(init_resp).encode() + b"\n"
            # Hang on tool calls
            await asyncio.sleep(100)
            return b""

        proc.stdout.readline = slow_readline

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            client = MCPClient(name="test", command="echo", timeout=0.1, max_retries=2, retry_delay=0.01)
            await client.connect()

            result = await client.call_tool("slow_tool", {})

            assert not result.ok
            assert "Failed after 2 attempts" in result.error
            assert client.stats.failed_calls == 1

            await client.close()


class TestMCPClientHealth:
    @pytest.mark.asyncio
    async def test_health_report(self):
        init_resp = {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}
        proc = _mock_process([init_resp])

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            client = MCPClient(name="my-server", command="echo")
            await client.connect()

            h = client.health()
            assert h["name"] == "my-server"
            assert h["connected"] is True
            assert h["pid"] == 12345

            await client.close()


class TestMCPClientRepr:
    def test_disconnected(self):
        client = MCPClient(name="test", command="echo")
        assert "disconnected" in repr(client)
