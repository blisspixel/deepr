"""Tests for the MCP HTTP server entrypoint."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.mcp.http_server import _make_http_message_handler, run_http_server
from deepr.mcp.transport.http import HttpMessage


@pytest.mark.asyncio
async def test_http_message_handler_returns_unknown_method_error():
    handler = _make_http_message_handler(MagicMock())

    response = await handler(HttpMessage(id="1", method="missing", params={}))

    assert response is not None
    assert response.error is not None
    assert response.error["code"] == -32601


@pytest.mark.asyncio
async def test_http_message_handler_rejects_non_dict_request_params():
    handler = _make_http_message_handler(MagicMock())

    response = await handler(HttpMessage(id="1", method="initialize", params=[]))

    assert response is not None
    assert response.error is not None
    assert response.error["code"] == -32600


@pytest.mark.asyncio
async def test_http_message_handler_routes_legacy_methods():
    server = MagicMock()
    handler = _make_http_message_handler(server)

    with patch(
        "deepr.mcp.http_server.mcp_server._handle_tools_call", new=AsyncMock(return_value={"ok": True})
    ) as tools_call:
        response = await handler(HttpMessage(id="1", method="query_expert", params={"expert_name": "alpha"}))

    assert response is not None
    assert response.result == {"ok": True}
    tools_call.assert_awaited_once_with(
        server,
        {"name": "deepr_query_expert", "arguments": {"expert_name": "alpha"}},
    )


@pytest.mark.asyncio
async def test_http_message_handler_redacts_unexpected_exception_text():
    handler = _make_http_message_handler(MagicMock())

    with patch(
        "deepr.mcp.http_server._dispatch_mcp_method",
        new=AsyncMock(side_effect=RuntimeError("private-path-and-token")),
    ):
        response = await handler(HttpMessage(id="1", method="initialize", params={}))

    assert response is not None
    assert response.error == {"code": -32603, "message": "Internal error"}
    assert "private-path-and-token" not in str(response.to_dict())


@pytest.mark.asyncio
async def test_run_http_server_starts_and_stops_transport():
    stop_event = asyncio.Event()
    created: list[MagicMock] = []

    class FakeTransport:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.url = f"http://{kwargs['host']}:{kwargs['port']}{kwargs['path']}"
            self.start = AsyncMock(side_effect=lambda: stop_event.set())
            self.stop = AsyncMock()
            self.on_message = MagicMock()
            created.append(self)

    server = MagicMock()
    server.registry.count.return_value = 28

    with (
        patch("deepr.mcp.http_server.mcp_server.DeeprMCPServer", return_value=server),
        patch("deepr.mcp.http_server.StreamingHttpTransport", FakeTransport),
    ):
        await run_http_server(
            host="127.0.0.1",
            port=18888,
            path="/x",
            auth_token="token",
            max_concurrent_requests=11,
            stop_event=stop_event,
        )

    transport = created[0]
    assert transport.kwargs["host"] == "127.0.0.1"
    assert transport.kwargs["port"] == 18888
    assert transport.kwargs["path"] == "/x"
    assert transport.kwargs["auth_token"] == "token"
    assert transport.kwargs["max_concurrent_requests"] == 11
    assert transport.on_message.called
    transport.start.assert_awaited_once()
    transport.stop.assert_awaited_once()
