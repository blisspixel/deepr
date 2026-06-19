"""Tests for MCP HTTP transport concurrency guards."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.mcp.transport.http import HttpMessage, StreamingHttpTransport


def _request(body: dict):
    req = MagicMock()
    req.headers = {}
    req.read = AsyncMock(return_value=json.dumps(body).encode("utf-8"))
    req.query = {}
    return req


class TestStreamingHttpConcurrency:
    @pytest.mark.asyncio
    async def test_http_post_rejects_when_concurrency_limit_is_full(self):
        transport = StreamingHttpTransport(max_concurrent_requests=1)
        first_started = asyncio.Event()
        release_first = asyncio.Event()

        async def handler(message: HttpMessage):
            first_started.set()
            await release_first.wait()
            return HttpMessage(id=message.id, result={"ok": True})

        transport.on_message(handler)
        first_task = asyncio.create_task(
            transport._handle_post(
                _request(
                    {
                        "jsonrpc": "2.0",
                        "id": "1",
                        "method": "tools/call",
                        "params": {"name": "deepr_status", "arguments": {}},
                    }
                )
            )
        )
        await first_started.wait()

        second = await transport._handle_post(
            _request(
                {
                    "jsonrpc": "2.0",
                    "id": "2",
                    "method": "tools/call",
                    "params": {"name": "deepr_status", "arguments": {}},
                }
            )
        )

        assert second.status == 429
        assert second.headers["Retry-After"] == "1"
        payload = json.loads(second.text)
        assert payload["error"]["data"]["error_code"] == "MCP_HTTP_CONCURRENCY_LIMIT_EXCEEDED"
        assert payload["error"]["data"]["limit"] == 1

        release_first.set()
        first = await first_task
        assert first.status == 200
        assert transport.stats.active_requests == 0

    @pytest.mark.asyncio
    async def test_health_reports_concurrency_limits(self):
        transport = StreamingHttpTransport(max_concurrent_requests=7)

        response = await transport._handle_health(MagicMock())

        assert response.status == 200
        payload = json.loads(response.text)
        assert payload["active_requests"] == 0
        assert payload["max_concurrent_requests"] == 7

    @pytest.mark.asyncio
    async def test_concurrency_limit_can_come_from_env(self, monkeypatch):
        monkeypatch.setenv("DEEPR_MCP_HTTP_MAX_CONCURRENCY", "5")
        transport = StreamingHttpTransport()

        response = await transport._handle_health(MagicMock())

        assert response.status == 200
        assert json.loads(response.text)["max_concurrent_requests"] == 5
