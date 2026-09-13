"""HTTP notifications cannot enter scoped tool admission or accounting."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.mcp.protocol_modern import META_CLIENT_CAPABILITIES, META_PROTOCOL_VERSION, MODERN_PROTOCOL_VERSION
from deepr.mcp.security.scoped_keys import ScopedMCPKeyContext
from deepr.mcp.security.tool_allowlist import ResearchMode
from deepr.mcp.transport.http import StreamingHttpTransport


def _request(payload, *, modern=False):
    headers = {"MCP-Protocol-Version": MODERN_PROTOCOL_VERSION} if modern else {}
    return SimpleNamespace(
        headers=headers, query={}, remote="127.0.0.1", read=AsyncMock(return_value=json.dumps(payload).encode())
    )


@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("tools/call", {"name": "deepr_research", "arguments": {}}),
        ("tools/call", {"name": "deepr_status", "arguments": {}}),
        ("resources/read", {"uri": "deepr://experts"}),
        ("get_expert_info", {"name": "fixture"}),
        ("notifications/initialized", {}),
    ],
)
@pytest.mark.asyncio
async def test_raw_http_notification_bypasses_request_admission_and_accounting(method, params, modern):
    transport = StreamingHttpTransport(host="127.0.0.1")
    context = ScopedMCPKeyContext("fixture-reader", ResearchMode.READ_ONLY)
    transport._authenticate_request = MagicMock(return_value=(context, None))
    transport._apply_scoped_key_context = MagicMock(return_value=(None, None))
    transport._dispatch_message = AsyncMock(return_value=None)
    transport._record_remote_call = MagicMock()
    transport._settle_remote_call = MagicMock()
    if modern:
        params = {**params, "_meta": {META_PROTOCOL_VERSION: MODERN_PROTOCOL_VERSION, META_CLIENT_CAPABILITIES: {}}}
    request = _request({"jsonrpc": "2.0", "method": method, "params": params}, modern=modern)

    response = await transport._handle_post(request)

    assert response.status == 202
    assert not response.body
    transport._authenticate_request.assert_called_once_with(request)
    transport._apply_scoped_key_context.assert_not_called()
    transport._dispatch_message.assert_not_awaited()
    transport._record_remote_call.assert_not_called()
    transport._settle_remote_call.assert_not_called()


@pytest.mark.asyncio
async def test_real_scoped_tool_denial_does_not_answer_a_notification():
    transport = StreamingHttpTransport(host="127.0.0.1")
    context = ScopedMCPKeyContext("fixture-reader", ResearchMode.READ_ONLY)
    transport._authenticate_request = MagicMock(return_value=(context, None))
    transport._audit_log = MagicMock()
    response = await transport._handle_post(
        _request({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "deepr_research", "arguments": {}}})
    )

    assert response.status == 202
    assert not response.body
    assert transport._audit_log.mock_calls == []


@pytest.mark.asyncio
async def test_notification_still_requires_http_authentication():
    transport = StreamingHttpTransport(host="127.0.0.1", auth_token="fixture-token")
    transport._apply_scoped_key_context = MagicMock()
    transport._dispatch_message = AsyncMock()
    request = _request({"jsonrpc": "2.0", "method": "notifications/initialized"})

    response = await transport._handle_post(request)

    assert response.status == 401
    request.read.assert_not_awaited()
    transport._apply_scoped_key_context.assert_not_called()
    transport._dispatch_message.assert_not_awaited()
