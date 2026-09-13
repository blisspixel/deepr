"""MCP envelope validation at both wire boundaries, before application work."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.mcp.http_server import _make_http_message_handler
from deepr.mcp.protocol_compat import HttpMessage, validate_mcp_envelope
from deepr.mcp.protocol_modern import JsonRpcProtocolError
from deepr.mcp.transport.http import StreamingHttpTransport
from deepr.mcp.transport.stdio import Message, StdioServer, StdioTransport


def _request(**overrides):
    return {"jsonrpc": "2.0", "id": 1, "method": "ping", **overrides}


INVALID_ENVELOPES = [
    [],
    1,
    None,
    "message",
    {},
    {"method": "ping", "id": 1},
    _request(jsonrpc="1.0"),
    *[_request(id=value) for value in (None, True, False, 1.5, [], {})],
    *[_request(method=value) for value in (None, True, 1, [], {})],
    *[_request(params=value) for value in (None, True, 1, [])],
    _request(result={}),
    _request(error={"code": -32603, "message": "invalid mixed envelope"}),
    {"jsonrpc": "2.0", "id": 1, "result": {}, "error": {}},
    {"jsonrpc": "2.0", "id": True, "result": {}},
    {"jsonrpc": "2.0", "error": {"code": True, "message": "bad code"}},
]


@pytest.mark.parametrize("payload", INVALID_ENVELOPES)
@pytest.mark.parametrize("transport", ["stdio", "http"])
@pytest.mark.asyncio
async def test_invalid_wire_envelope_is_rejected_before_dispatch(payload, transport):
    handler = AsyncMock(return_value=None)
    body = json.dumps(payload).encode()
    if transport == "http":
        server = StreamingHttpTransport(host="127.0.0.1")
        server.on_message(handler)
        request = SimpleNamespace(headers={}, query={}, remote="127.0.0.1", read=AsyncMock(return_value=body))
        response = await server._handle_post(request)
        assert response.status == 400
        result = json.loads(response.text)
    else:
        reader = asyncio.StreamReader()
        reader.feed_data(body + b"\n")
        reader.feed_eof()
        written = []
        writer = SimpleNamespace(write=written.append, drain=AsyncMock())
        server = StdioTransport(input_stream=reader, output_stream=writer)
        server._running = True
        server.on_message(handler)
        await server._read_loop()
        result = json.loads(b"".join(written))
    assert result["error"]["code"] == -32600
    expected_id = payload.get("id") if isinstance(payload, dict) else None
    if type(expected_id) in (str, int):
        assert result["id"] == expected_id
    elif transport == "http":
        assert result["id"] is None
    else:
        assert "id" not in result
    handler.assert_not_awaited()


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.asyncio
async def test_http_uncorrelated_error_id_preserves_protocol_era(modern):
    server = StreamingHttpTransport(host="127.0.0.1")
    headers = {"MCP-Protocol-Version": "2026-07-28"} if modern else {}
    request = SimpleNamespace(headers=headers, query={}, remote="127.0.0.1", read=AsyncMock(return_value=b"[]"))
    response = await server._handle_post(request)
    result = json.loads(response.text)
    assert response.status == 400
    assert result["error"]["code"] == -32600
    if modern:
        assert "id" not in result
    else:
        assert result["id"] is None


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("body", [b"\xff", b"{"])
@pytest.mark.asyncio
async def test_http_parse_errors_preserve_protocol_era(body, modern):
    server = StreamingHttpTransport(host="127.0.0.1")
    handler = AsyncMock()
    server.on_message(handler)
    headers = {"MCP-Protocol-Version": "2026-07-28"} if modern else {}
    request = SimpleNamespace(headers=headers, query={}, remote="127.0.0.1", read=AsyncMock(return_value=body))
    response = await server._handle_post(request)
    result = json.loads(response.text)
    assert response.status == 400
    assert result["error"]["code"] == -32700
    if modern:
        assert "id" not in result
    else:
        assert result["id"] is None
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_stdio_invalid_utf8_reports_parse_error():
    reader = asyncio.StreamReader()
    reader.feed_data(b"\xff\n")
    reader.feed_eof()
    written = []
    writer = SimpleNamespace(write=written.append, drain=AsyncMock())
    server = StdioTransport(input_stream=reader, output_stream=writer)
    server._running = True
    handler = AsyncMock()
    server.on_message(handler)
    await server._read_loop()
    assert json.loads(b"".join(written))["error"]["code"] == -32700
    handler.assert_not_awaited()


@pytest.mark.parametrize("transport", ["stdio", "http"])
@pytest.mark.asyncio
async def test_valid_notifications_and_responses_never_invoke_request_work(transport):
    application = MagicMock()
    if transport == "http":
        handler = _make_http_message_handler(application)
        message_type = HttpMessage
    else:
        server = StdioServer()
        server.register_method("tools/call", application)
        handler = server._handle_message
        message_type = Message
    for data in (
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "method": "vendor/notification", "params": {"arbitrary": 1}},
        {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "ignored"}},
        {"jsonrpc": "2.0", "id": 0, "result": {}},
        {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}},
    ):
        assert await handler(message_type.from_dict(data)) is None
    assert application.mock_calls == []


@pytest.mark.parametrize("request_id", [0, -1, "", "1"])
def test_valid_ids_and_unknown_extension_fields_are_preserved(request_id):
    data = _request(id=request_id, method="vendor/extension", params={"custom": [1]}, custom_field=True)
    assert validate_mcp_envelope(data) is data


def test_uncorrelated_legacy_error_response_accepts_null_id():
    data = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
    assert validate_mcp_envelope(data) is data


@pytest.mark.parametrize("params", [None, [], 1, True])
def test_explicit_invalid_notification_params_are_not_normalized_to_empty(params):
    with pytest.raises(JsonRpcProtocolError) as error:
        validate_mcp_envelope({"jsonrpc": "2.0", "method": "vendor/notice", "params": params})
    assert error.value.code == -32600
