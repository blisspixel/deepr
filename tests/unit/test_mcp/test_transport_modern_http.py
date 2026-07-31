"""Transport-level tests for 2026-07-28 Streamable HTTP behavior: status
codes, Origin enforcement, and the subscriptions/listen SSE stream."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.mcp import protocol_modern as pm
from deepr.mcp.protocol_compat import HttpMessage
from deepr.mcp.subscriptions_listen import make_listen_opener
from deepr.mcp.transport.http import StreamingHttpTransport


def _modern_body(method="tools/list", params=None, message_id="1"):
    body_params = {
        "_meta": {
            pm.META_PROTOCOL_VERSION: pm.MODERN_PROTOCOL_VERSION,
            pm.META_CLIENT_CAPABILITIES: {},
        }
    }
    body_params.update(params or {})
    body = {"jsonrpc": "2.0", "method": method, "params": body_params}
    if message_id is not None:
        body["id"] = message_id
    return json.dumps(body).encode("utf-8")


def _modern_headers(method="tools/list", name=None, **extra):
    headers = {
        "MCP-Protocol-Version": pm.MODERN_PROTOCOL_VERSION,
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    headers.update(extra)
    return headers


def _request(body, headers=None):
    req = MagicMock()
    req.headers = headers or {}
    req.read = AsyncMock(return_value=body)
    req.query = {}
    req.remote = "127.0.0.1"
    return req


class TestModernPostStatuses:
    @pytest.mark.asyncio
    async def test_valid_modern_request_succeeds(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(AsyncMock(return_value=HttpMessage(id="1", result={"resultType": "complete"})))
        resp = await t._handle_post(_request(_modern_body(), _modern_headers()))
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_header_mismatch_is_400_with_32020(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(AsyncMock(return_value=None))
        headers = _modern_headers(method="prompts/list")  # body says tools/list
        resp = await t._handle_post(_request(_modern_body(), headers))
        assert resp.status == 400
        error = json.loads(resp.text)["error"]
        assert error["code"] == pm.HEADER_MISMATCH_CODE

    @pytest.mark.asyncio
    async def test_missing_headers_on_modern_body_is_400(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(AsyncMock(return_value=None))
        resp = await t._handle_post(_request(_modern_body()))
        assert resp.status == 400
        assert json.loads(resp.text)["error"]["code"] == pm.HEADER_MISMATCH_CODE

    @pytest.mark.asyncio
    async def test_unsupported_version_is_400_with_supported_list(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(AsyncMock(return_value=None))
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/list",
                "params": {"_meta": {pm.META_PROTOCOL_VERSION: "2030-01-01"}},
            }
        ).encode()
        headers = {"MCP-Protocol-Version": "2030-01-01", "Mcp-Method": "tools/list"}
        resp = await t._handle_post(_request(body, headers))
        assert resp.status == 400
        error = json.loads(resp.text)["error"]
        assert error["code"] == pm.UNSUPPORTED_PROTOCOL_VERSION_CODE
        assert pm.MODERN_PROTOCOL_VERSION in error["data"]["supported"]

    @pytest.mark.asyncio
    async def test_unknown_modern_method_is_404(self):
        from deepr.mcp.http_server import _make_http_message_handler

        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(_make_http_message_handler(MagicMock()))
        resp = await t._handle_post(
            _request(_modern_body(method="tasks/get"), _modern_headers(method="tasks/get"))
        )
        assert resp.status == 404
        assert json.loads(resp.text)["error"]["code"] == pm.METHOD_NOT_FOUND_CODE

    @pytest.mark.asyncio
    async def test_session_and_resume_headers_are_ignored(self):
        # Protocol sessions and SSE resumability are gone in 2026-07-28; the
        # server must not fail on (or honor) these legacy headers.
        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(AsyncMock(return_value=HttpMessage(id="1", result={"resultType": "complete"})))
        headers = _modern_headers(**{"Mcp-Session-Id": "stale", "Last-Event-ID": "9"})
        resp = await t._handle_post(_request(_modern_body(), headers))
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_unknown_notification_is_accepted_202(self):
        # notifications/initialized arrives after every legacy handshake and
        # must be accepted-and-ignored, never answered with an error.
        from deepr.mcp.http_server import _make_http_message_handler

        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(_make_http_message_handler(MagicMock()))
        body = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}).encode()
        resp = await t._handle_post(_request(body))
        assert resp.status == 202

    @pytest.mark.asyncio
    async def test_modern_legacy_alias_keeps_modern_envelope(self):
        # Canonicalizing a legacy alias method must keep _meta on params (so
        # dispatch stays modern) and out of tool arguments (no TypeError).
        from unittest.mock import AsyncMock as AM

        from deepr.mcp.http_server import _make_http_message_handler

        t = StreamingHttpTransport(host="127.0.0.1")
        server = MagicMock()
        t.on_message(_make_http_message_handler(server))
        body = _modern_body(method="query_expert", params={"expert_name": "a"})
        with patch(
            "deepr.mcp.server._handle_tools_call",
            new=AM(return_value={"content": []}),
        ) as tools_call:
            resp = await t._handle_post(_request(body, _modern_headers(method="query_expert")))
        assert resp.status == 200
        result = json.loads(resp.text)["result"]
        assert result["resultType"] == "complete"
        called_params = tools_call.await_args.args[1]
        assert "_meta" not in called_params["arguments"]
        assert called_params["arguments"] == {"expert_name": "a"}


class TestOriginEnforcement:
    @pytest.mark.asyncio
    async def test_disallowed_origin_is_403(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(AsyncMock(return_value=None))
        resp = await t._handle_post(
            _request(_modern_body(), {**_modern_headers(), "Origin": "https://evil.example.com"})
        )
        assert resp.status == 403

    @pytest.mark.asyncio
    async def test_loopback_origin_is_allowed(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(AsyncMock(return_value=HttpMessage(id="1", result={})))
        resp = await t._handle_post(
            _request(_modern_body(), {**_modern_headers(), "Origin": "http://localhost:5173"})
        )
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_health_rejects_bad_origin(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        resp = await t._handle_health(MagicMock(headers={"Origin": "https://evil.example.com"}))
        assert resp.status == 403


class FakeStreamResponse:
    """Captures SSE writes without a real aiohttp request."""

    def __init__(self, *args, **kwargs):
        self.status = kwargs.get("status", 200)
        self.headers = kwargs.get("headers", {})
        self.written = []

    async def prepare(self, request):
        return None

    async def write(self, data):
        self.written.append(data)

    def events(self):
        payloads = []
        for chunk in self.written:
            text = chunk.decode("utf-8")
            if text.startswith("data: "):
                payloads.append(json.loads(text[len("data: ") :]))
        return payloads


class TestSubscriptionsListenOverHttp:
    def _transport_with_listen(self, handler):
        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_listen(make_listen_opener(handler))
        t._running = True
        return t

    @pytest.mark.asyncio
    async def test_listen_streams_ack_then_shutdown_response(self):
        from tests.unit.test_mcp.test_subscriptions_listen import FakeResourceHandler

        handler = FakeResourceHandler()
        t = self._transport_with_listen(handler)
        body = _modern_body(
            method="subscriptions/listen",
            params={"notifications": {"resourceSubscriptions": ["deepr://campaigns/a/status"]}},
            message_id="listen-1",
        )

        with patch("deepr.mcp.transport.http.web.StreamResponse", FakeStreamResponse):
            post_task = asyncio.create_task(
                t._handle_post(_request(body, _modern_headers(method="subscriptions/listen")))
            )
            while not t._listen_queues:
                await asyncio.sleep(0)
            await handler.emit(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/resources/updated",
                    "params": {"uri": "deepr://campaigns/a/status", "data": {}},
                }
            )
            await t.stop()
            response = await asyncio.wait_for(post_task, timeout=5)

        events = response.events()
        assert events[0]["method"] == "notifications/subscriptions/acknowledged"
        assert events[1]["method"] == "notifications/resources/updated"
        assert events[1]["params"]["_meta"][pm.META_SUBSCRIPTION_ID] == "listen-1"
        # Graceful shutdown: the final event is the JSON-RPC response.
        assert events[-1]["id"] == "listen-1"
        assert events[-1]["result"]["resultType"] == "complete"
        assert handler.unsubscribed == ["sub_1"]


    @pytest.mark.asyncio
    async def test_listen_stream_does_not_hold_a_request_slot(self):
        from tests.unit.test_mcp.test_subscriptions_listen import FakeResourceHandler

        t = self._transport_with_listen(FakeResourceHandler())
        body = _modern_body(method="subscriptions/listen", message_id="listen-1")

        with patch("deepr.mcp.transport.http.web.StreamResponse", FakeStreamResponse):
            post_task = asyncio.create_task(
                t._handle_post(_request(body, _modern_headers(method="subscriptions/listen")))
            )
            while not t._listen_queues:
                await asyncio.sleep(0)
            # The long-lived stream must not pin a POST slot; otherwise N idle
            # streams would starve every request on the transport.
            assert t.stats.active_requests == 0
            await t.stop()
            await asyncio.wait_for(post_task, timeout=5)
        assert t.stats.active_requests == 0

    @pytest.mark.asyncio
    async def test_listen_preserves_integer_request_id(self):
        from tests.unit.test_mcp.test_subscriptions_listen import FakeResourceHandler

        t = self._transport_with_listen(FakeResourceHandler())
        body = _modern_body(method="subscriptions/listen", message_id=7)

        with patch("deepr.mcp.transport.http.web.StreamResponse", FakeStreamResponse):
            post_task = asyncio.create_task(
                t._handle_post(_request(body, _modern_headers(method="subscriptions/listen")))
            )
            while not t._listen_queues:
                await asyncio.sleep(0)
            await t.stop()
            response = await asyncio.wait_for(post_task, timeout=5)

        events = response.events()
        # The spec echoes the JSON-RPC id verbatim as the subscription ID.
        assert events[0]["params"]["_meta"][pm.META_SUBSCRIPTION_ID] == 7
        assert events[-1]["id"] == 7

    @pytest.mark.asyncio
    async def test_listen_streams_are_capped(self):
        from tests.unit.test_mcp.test_subscriptions_listen import FakeResourceHandler

        t = StreamingHttpTransport(host="127.0.0.1", max_concurrent_requests=1)
        t.on_listen(make_listen_opener(FakeResourceHandler()))
        t._running = True
        assert t._try_acquire_listen_slot()  # simulate one active stream
        body = _modern_body(method="subscriptions/listen", message_id="listen-2")
        resp = await t._handle_post(_request(body, _modern_headers(method="subscriptions/listen")))
        assert resp.status == 429

    @pytest.mark.asyncio
    async def test_listen_slot_is_returned_after_stream_ends(self):
        from tests.unit.test_mcp.test_subscriptions_listen import FakeResourceHandler

        t = self._transport_with_listen(FakeResourceHandler())
        body = _modern_body(method="subscriptions/listen", message_id="listen-1")
        with patch("deepr.mcp.transport.http.web.StreamResponse", FakeStreamResponse):
            post_task = asyncio.create_task(
                t._handle_post(_request(body, _modern_headers(method="subscriptions/listen")))
            )
            while not t._listen_queues:
                await asyncio.sleep(0)
            assert t._listen_slots == 1
            await t.stop()
            await asyncio.wait_for(post_task, timeout=5)
        assert t._listen_slots == 0

    @pytest.mark.asyncio
    async def test_resource_subscription_list_is_capped_and_deduped(self):
        from deepr.mcp.subscriptions_listen import MAX_RESOURCE_SUBSCRIPTIONS
        from tests.unit.test_mcp.test_subscriptions_listen import FakeResourceHandler

        handler = FakeResourceHandler()
        t = self._transport_with_listen(handler)
        # Duplicates would otherwise register N independent subscriptions and
        # fan one resource update out N times.
        uris = ["deepr://campaigns/a/status"] * (MAX_RESOURCE_SUBSCRIPTIONS + 50)
        body = _modern_body(
            method="subscriptions/listen",
            params={"notifications": {"resourceSubscriptions": uris}},
            message_id="listen-1",
        )
        with patch("deepr.mcp.transport.http.web.StreamResponse", FakeStreamResponse):
            post_task = asyncio.create_task(
                t._handle_post(_request(body, _modern_headers(method="subscriptions/listen")))
            )
            while not t._listen_queues:
                await asyncio.sleep(0)
            assert len(handler.callbacks) == 1
            await t.stop()
            await asyncio.wait_for(post_task, timeout=5)

    @pytest.mark.asyncio
    async def test_too_many_unique_subscriptions_is_rejected(self):
        from deepr.mcp.subscriptions_listen import MAX_RESOURCE_SUBSCRIPTIONS
        from tests.unit.test_mcp.test_subscriptions_listen import FakeResourceHandler

        t = self._transport_with_listen(FakeResourceHandler())
        uris = [f"deepr://campaigns/c{i}/status" for i in range(MAX_RESOURCE_SUBSCRIPTIONS + 1)]
        body = _modern_body(
            method="subscriptions/listen",
            params={"notifications": {"resourceSubscriptions": uris}},
            message_id="listen-1",
        )
        resp = await t._handle_post(_request(body, _modern_headers(method="subscriptions/listen")))
        assert resp.status == 400
        assert json.loads(resp.text)["error"]["code"] == pm.INVALID_PARAMS_CODE
        # The rejected request must not leak its listen slot.
        assert t._listen_slots == 0

    @pytest.mark.asyncio
    async def test_listen_with_malformed_filter_is_json_error_not_stream(self):
        from tests.unit.test_mcp.test_subscriptions_listen import FakeResourceHandler

        t = self._transport_with_listen(FakeResourceHandler())
        body = _modern_body(
            method="subscriptions/listen",
            params={"notifications": "nope"},
            message_id="listen-1",
        )
        resp = await t._handle_post(_request(body, _modern_headers(method="subscriptions/listen")))
        assert resp.status == 400
        assert json.loads(resp.text)["error"]["code"] == pm.INVALID_PARAMS_CODE

    @pytest.mark.asyncio
    async def test_listen_without_opener_is_404(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(AsyncMock(return_value=None))
        t._running = True
        body = _modern_body(method="subscriptions/listen", message_id="listen-1")
        resp = await t._handle_post(_request(body, _modern_headers(method="subscriptions/listen")))
        assert resp.status == 404
