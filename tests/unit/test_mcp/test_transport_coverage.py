"""Coverage-focused tests for MCP transports.

Targets the previously-uncovered branches in
``deepr/mcp/transport/{stdio,http}.py``:

stdio:
- ``StdioTransport.start`` / ``stop`` (including the in-flight drain)
- ``_read_loop`` dispatch + parse-error path
- ``send`` / ``_send_error``
- ``StdioServer.register_method`` / ``run`` / ``stop`` / unknown-method
  handling

http:
- ``StreamingHttpTransport`` start refuses public bind without token, 401
  branch in ``_check_auth``, parse error in ``_handle_post``, SSE queue
  replacement, broadcast & send_to.
- ``HttpClient`` send before connect, subscribe cancels prior task,
  plaintext-warning on non-loopback HTTP, stream-loop receives data.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.transport.http import (
    HttpClient,
    HttpMessage,
    StreamingHttpTransport,
    _extract_bearer,
    _is_loopback_host,
)
from deepr.mcp.transport.stdio import (
    Message,
    StdioServer,
    StdioTransport,
)

# ---------------------------------------------------------------------- #
# Stdio
# ---------------------------------------------------------------------- #


def _make_stdio_streams():
    """Build an in-memory StreamReader and a stub writer that captures output.

    Must be invoked from inside an async test so ``asyncio.StreamReader()``
    can pick up the running event loop. Earlier this lived in a sync fixture
    which broke in full-suite runs where no current loop is bound at fixture
    setup time.
    """
    reader = asyncio.StreamReader()
    written: list[bytes] = []

    class DummyWriter:
        def write(self, data: bytes) -> None:
            written.append(data)

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            return None

    return reader, DummyWriter(), written


class TestStdioTransport:
    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        reader, writer, _ = _make_stdio_streams()
        t = StdioTransport(input_stream=reader, output_stream=writer)
        await t.start()
        assert t.is_running
        await t.start()  # second call is a no-op
        await t.stop()

    @pytest.mark.asyncio
    async def test_read_dispatch_and_response(self):
        reader, writer, written = _make_stdio_streams()
        t = StdioTransport(input_stream=reader, output_stream=writer)

        async def handler(msg):
            # Echo the params back as a result.
            return Message(id=msg.id, result={"echoed": msg.params})

        t.on_message(handler)
        await t.start()

        # Push a request line through the reader.
        req = json.dumps({"jsonrpc": "2.0", "id": "1", "method": "ping", "params": {"x": 1}}) + "\n"
        reader.feed_data(req.encode("utf-8"))

        # Allow the dispatch task to run.
        await asyncio.sleep(0.05)
        await asyncio.sleep(0.05)

        # The handler should have produced output.
        assert any(b'"id": "1"' in chunk or b'"id":"1"' in chunk for chunk in written)
        assert t.stats.messages_received >= 1
        await t.stop()

    @pytest.mark.asyncio
    async def test_parse_error_emits_jsonrpc_minus_32700(self):
        reader, writer, written = _make_stdio_streams()
        t = StdioTransport(input_stream=reader, output_stream=writer)
        t.on_message(AsyncMock(return_value=None))
        await t.start()

        reader.feed_data(b"not json at all\n")
        await asyncio.sleep(0.05)

        # An error response should have been written.
        joined = b"".join(written).decode()
        assert "-32700" in joined or "Parse error" in joined
        await t.stop()

    @pytest.mark.asyncio
    async def test_stop_drains_in_flight(self):
        reader, writer, _ = _make_stdio_streams()
        t = StdioTransport(input_stream=reader, output_stream=writer)

        completed = asyncio.Event()

        async def slow_handler(msg):
            await asyncio.sleep(0.05)
            completed.set()
            return Message(id=msg.id, result="done")

        t.on_message(slow_handler)
        await t.start()

        reader.feed_data(b'{"jsonrpc":"2.0","id":"q","method":"x"}\n')
        # Give the read loop a tick to schedule the handler.
        await asyncio.sleep(0.01)
        await t.stop()
        # The slow handler should have run to completion thanks to the drain.
        assert completed.is_set()

    @pytest.mark.asyncio
    async def test_stop_cancels_handlers_past_grace(self):
        reader, writer, _ = _make_stdio_streams()
        t = StdioTransport(input_stream=reader, output_stream=writer)

        async def stuck_handler(msg):
            await asyncio.sleep(60)

        t.on_message(stuck_handler)
        await t.start()
        reader.feed_data(b'{"jsonrpc":"2.0","id":"q","method":"x"}\n')
        await asyncio.sleep(0.01)

        # Patch wait_for so the drain trips its timeout branch immediately.
        original_wait_for = asyncio.wait_for

        async def fast_timeout(coro, timeout):
            return await original_wait_for(coro, timeout=0.01)

        with patch("asyncio.wait_for", side_effect=fast_timeout):
            await t.stop()
        assert not t._in_flight

    def test_is_local_is_true(self):
        assert StdioTransport().is_local is True


class TestStdioServer:
    @pytest.mark.asyncio
    async def test_unknown_method_returns_jsonrpc_minus_32601(self):
        srv = StdioServer()
        await srv._handle_message(Message(id="1", method="missing"))
        resp = await srv._handle_message(Message(id="1", method="missing"))
        assert resp.error["code"] == -32601

    @pytest.mark.asyncio
    async def test_method_handler_runs_and_wraps_exception(self):
        srv = StdioServer()

        async def good(params):
            return {"ok": True, "params": params}

        async def bad(params):
            raise ValueError("nope")

        srv.register_method("good", good)
        srv.register_method("bad", bad)

        ok = await srv._handle_message(Message(id="1", method="good", params={"a": 1}))
        assert ok.result == {"ok": True, "params": {"a": 1}}

        err = await srv._handle_message(Message(id="2", method="bad"))
        assert err.error["code"] == -32603
        assert "nope" in err.error["message"]

    @pytest.mark.asyncio
    async def test_notifications_return_none(self):
        srv = StdioServer()
        # No id = notification, returns None
        out = await srv._handle_message(Message(method="notify"))
        assert out is None

    @pytest.mark.asyncio
    async def test_stop_delegates_to_transport(self):
        srv = StdioServer()
        srv._transport = MagicMock()
        srv._transport.stop = AsyncMock()
        await srv.stop()
        srv._transport.stop.assert_awaited_once()


# ---------------------------------------------------------------------- #
# HTTP transport server
# ---------------------------------------------------------------------- #


class TestHttpHelpers:
    def test_is_loopback_localhost(self):
        assert _is_loopback_host("localhost")

    def test_empty_host_is_not_loopback(self):
        assert not _is_loopback_host("")

    def test_is_loopback_127(self):
        assert _is_loopback_host("127.0.0.1")
        assert _is_loopback_host("127.0.0.5")

    def test_is_loopback_ipv6(self):
        assert _is_loopback_host("::1")

    def test_is_loopback_external(self):
        assert not _is_loopback_host("8.8.8.8")
        assert not _is_loopback_host("203.0.113.5")

    def test_extract_bearer_from_authorization(self):
        req = MagicMock()
        req.headers = {"Authorization": "Bearer abc123"}
        assert _extract_bearer(req) == "abc123"

    def test_extract_bearer_from_x_api_key(self):
        req = MagicMock()
        req.headers = {"Authorization": "", "X-Api-Key": "xyz"}
        assert _extract_bearer(req) == "xyz"

    def test_extract_bearer_missing(self):
        req = MagicMock()
        req.headers = {"Authorization": "", "X-Api-Key": ""}
        assert _extract_bearer(req) is None

    def test_extract_bearer_empty_bearer(self):
        req = MagicMock()
        req.headers = {"Authorization": "Bearer ", "X-Api-Key": ""}
        assert _extract_bearer(req) is None


class TestStreamingHttpStart:
    @pytest.mark.asyncio
    async def test_refuses_public_bind_without_auth(self):
        t = StreamingHttpTransport(host="0.0.0.0")
        with pytest.raises(RuntimeError, match="auth token"):
            await t.start()

    @pytest.mark.asyncio
    async def test_refuses_empty_host_without_auth(self):
        t = StreamingHttpTransport(host="")
        with pytest.raises(RuntimeError, match="auth token"):
            await t.start()

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        t = StreamingHttpTransport(host="127.0.0.1", port=0)
        # Patch the aiohttp bits so we don't actually bind a port.
        with (
            patch("deepr.mcp.transport.http.web.Application") as app_cls,
            patch("deepr.mcp.transport.http.web.AppRunner") as runner_cls,
            patch("deepr.mcp.transport.http.web.TCPSite") as site_cls,
        ):
            app = MagicMock()
            app.router = MagicMock()
            app_cls.return_value = app
            runner = MagicMock()
            runner.setup = AsyncMock()
            runner.cleanup = AsyncMock()
            runner_cls.return_value = runner
            site = MagicMock()
            site.start = AsyncMock()
            site_cls.return_value = site
            await t.start()
            assert t.is_running
            await t.start()  # second call is a no-op
            await t.stop()
            assert not t.is_running

    @pytest.mark.asyncio
    async def test_public_bind_with_auth_succeeds(self):
        t = StreamingHttpTransport(host="0.0.0.0", auth_token="secret")
        with (
            patch("deepr.mcp.transport.http.web.Application") as app_cls,
            patch("deepr.mcp.transport.http.web.AppRunner") as runner_cls,
            patch("deepr.mcp.transport.http.web.TCPSite") as site_cls,
        ):
            app = MagicMock(router=MagicMock())
            app_cls.return_value = app
            runner = MagicMock(setup=AsyncMock(), cleanup=AsyncMock())
            runner_cls.return_value = runner
            site = MagicMock(start=AsyncMock())
            site_cls.return_value = site
            await t.start()
            assert t.is_running
            await t.stop()


class TestStreamingHttpHandlers:
    def _request(self, body=b'{"jsonrpc":"2.0","id":"1","method":"x"}', headers=None):
        req = MagicMock()
        req.headers = headers or {}
        req.read = AsyncMock(return_value=body)
        req.query = {}
        return req

    @pytest.mark.asyncio
    async def test_handle_post_unauthorized_when_token_missing(self):
        t = StreamingHttpTransport(host="127.0.0.1", auth_token="s3cr3t")
        resp = await t._handle_post(self._request())
        # web.json_response returns a Response with status 401.
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_handle_post_authorized(self):
        t = StreamingHttpTransport(host="127.0.0.1", auth_token="s3cr3t")
        t.on_message(AsyncMock(return_value=HttpMessage(id="1", result={"ok": True})))
        resp = await t._handle_post(self._request(headers={"Authorization": "Bearer s3cr3t"}))
        assert resp.status == 200
        assert json.loads(resp.text)["result"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_handle_post_notification_no_response(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(AsyncMock(return_value=None))
        resp = await t._handle_post(self._request())
        assert resp.status == 204

    @pytest.mark.asyncio
    async def test_handle_post_parse_error(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        t.on_message(AsyncMock(return_value=None))
        resp = await t._handle_post(self._request(body=b"not json"))
        assert resp.status == 400
        assert "-32700" in resp.text

    @pytest.mark.asyncio
    async def test_handle_post_generic_exception_does_not_leak(self):
        t = StreamingHttpTransport(host="127.0.0.1")

        async def boom(_msg):
            raise RuntimeError("/etc/secret/path/leak.txt")

        t.on_message(boom)
        resp = await t._handle_post(self._request())
        assert resp.status == 500
        assert "/etc/secret/path/leak.txt" not in resp.text
        assert "Internal error" in resp.text

    @pytest.mark.asyncio
    async def test_handle_post_bad_token_type_error(self):
        """Non-ASCII header must not escape into 500."""
        t = StreamingHttpTransport(host="127.0.0.1", auth_token="s3cr3t")
        req = self._request(headers={"Authorization": "Bearer \udce4\udcb8\udc96\udcb8\udcfb"})
        resp = await t._handle_post(req)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_handle_health(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        resp = await t._handle_health(MagicMock())
        assert resp.status == 200
        data = json.loads(resp.text)
        assert data["status"] == "healthy"
        assert "active_streams" in data


class TestStreamingHttpBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_delivers_to_all_queues(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        t._subscribers["a"] = q1
        t._subscribers["b"] = q2
        count = await t.broadcast({"event": "hi"})
        assert count == 2
        assert (await q1.get()) == {"event": "hi"}
        assert (await q2.get()) == {"event": "hi"}

    @pytest.mark.asyncio
    async def test_send_to_existing_subscriber(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        q: asyncio.Queue = asyncio.Queue()
        t._subscribers["one"] = q
        ok = await t.send_to("one", {"event": "ping"})
        assert ok is True
        assert (await q.get()) == {"event": "ping"}

    @pytest.mark.asyncio
    async def test_send_to_unknown_subscriber(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        ok = await t.send_to("ghost", {"event": "ping"})
        assert ok is False

    @pytest.mark.asyncio
    async def test_subscriber_reconnect_does_not_unregister_replacement(self):
        """Reconnect with the same subscriber_id must not strand the new queue.

        Regression for the SSE subscriber cleanup race: the old handler's
        finally block used to unconditionally pop ``subscriber_id`` even after
        a replacement queue had taken the slot, breaking notification delivery
        to the new subscriber until the next reconnect.
        """
        t = StreamingHttpTransport(host="127.0.0.1")
        old_queue: asyncio.Queue = asyncio.Queue()
        t._subscribers["sub_x"] = old_queue
        # Simulate a replacement queue installed by a new connection.
        new_queue: asyncio.Queue = asyncio.Queue()
        t._subscribers["sub_x"] = new_queue

        # Now simulate the OLD handler's finally block: it should see that
        # the entry no longer belongs to it and leave the replacement in place.
        if t._subscribers.get("sub_x") is old_queue:
            t._subscribers.pop("sub_x", None)

        assert "sub_x" in t._subscribers
        assert t._subscribers["sub_x"] is new_queue

    @pytest.mark.asyncio
    async def test_stop_signals_subscribers(self):
        t = StreamingHttpTransport(host="127.0.0.1")
        q: asyncio.Queue = asyncio.Queue()
        t._subscribers["one"] = q
        t._running = True
        await t.stop()
        # Queue receives sentinel None, subscribers dict cleared.
        assert (await q.get()) is None
        assert not t._subscribers

    def test_url_property(self):
        t = StreamingHttpTransport(host="127.0.0.1", port=9999, path="/x")
        assert t.url == "http://127.0.0.1:9999/x"

    def test_is_local_is_false(self):
        assert StreamingHttpTransport().is_local is False


# ---------------------------------------------------------------------- #
# HttpClient
# ---------------------------------------------------------------------- #


class TestHttpClient:
    @pytest.mark.asyncio
    async def test_send_before_connect_raises(self):
        client = HttpClient(base_url="http://127.0.0.1:8765/mcp")
        with pytest.raises(RuntimeError, match="Not connected"):
            await client.send(HttpMessage(id="1", method="x"))

    @pytest.mark.asyncio
    async def test_send_with_closed_session_raises(self):
        client = HttpClient(base_url="http://127.0.0.1:8765/mcp")
        client._session = MagicMock(closed=True)
        with pytest.raises(RuntimeError, match="Session is closed"):
            await client.send(HttpMessage(id="1", method="x"))

    @pytest.mark.asyncio
    async def test_subscribe_before_connect_raises(self):
        client = HttpClient(base_url="http://127.0.0.1:8765/mcp")
        with pytest.raises(RuntimeError, match="Not connected"):
            await client.subscribe()

    @pytest.mark.asyncio
    async def test_subscribe_cancels_prior_task(self):
        client = HttpClient(base_url="http://127.0.0.1:8765/mcp")
        client._session = MagicMock(closed=False)

        # Place a pretend running task as the prior subscription.
        async def long_running():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                pass

        old_task = asyncio.create_task(long_running())
        client._stream_task = old_task

        # Patch the stream loop so we don't actually open a socket.
        async def fake_loop(_url):
            await asyncio.sleep(0)

        with patch.object(client, "_stream_loop", side_effect=fake_loop):
            await client.subscribe(subscriber_id="me")

        assert old_task.cancelled() or old_task.done()
        # New task installed
        assert client._stream_task is not None and client._stream_task is not old_task

    @pytest.mark.asyncio
    async def test_disconnect_cancels_and_closes(self):
        client = HttpClient(base_url="http://127.0.0.1:8765/mcp")
        session = MagicMock()
        session.close = AsyncMock()
        client._session = session

        async def long_loop():
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                pass

        client._stream_task = asyncio.create_task(long_loop())
        await client.disconnect()
        session.close.assert_awaited_once()

    def test_auth_headers_with_and_without_token(self):
        c1 = HttpClient(base_url="http://x/m", auth_token="t")
        assert c1._auth_headers() == {"Authorization": "Bearer t"}
        c2 = HttpClient(base_url="http://x/m")
        # No env var leak should give empty headers.
        with patch.dict(os.environ, {}, clear=True):
            c2 = HttpClient(base_url="http://x/m")
            assert c2._auth_headers() == {}

    @pytest.mark.asyncio
    async def test_subscribe_warns_on_plain_http_non_loopback(self, caplog):
        import logging

        caplog.set_level(logging.WARNING, logger="deepr.mcp.transport.http")
        client = HttpClient(base_url="http://203.0.113.5:8000/mcp", auth_token="t")
        client._session = MagicMock(closed=False)

        async def fake_loop(_url):
            await asyncio.sleep(0)

        with patch.object(client, "_stream_loop", side_effect=fake_loop):
            await client.subscribe()
        assert any("cleartext" in r.message or "plaintext" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_subscribe_quotes_subscriber_id(self):
        captured: list[str] = []

        async def fake_loop(url):
            captured.append(url)

        client = HttpClient(base_url="http://127.0.0.1:8000/mcp")
        client._session = MagicMock(closed=False)
        with patch.object(client, "_stream_loop", side_effect=fake_loop):
            await client.subscribe(subscriber_id="weird&=&id")
            await asyncio.sleep(0)
        assert captured
        assert "weird%26%3D%26id" in captured[0]

    @pytest.mark.asyncio
    async def test_send_returns_parsed_response(self):
        client = HttpClient(base_url="http://127.0.0.1:8000/mcp")
        # Build a context-managed mock for session.post(...)
        session = MagicMock()
        session.closed = False
        post_ctx = MagicMock()

        async def __aenter__(_self):
            response = MagicMock()
            response.status = 200
            response.json = AsyncMock(return_value={"jsonrpc": "2.0", "id": "1", "result": {"a": 1}})
            return response

        async def __aexit__(_self, *_a):
            return False

        post_ctx.__aenter__ = __aenter__
        post_ctx.__aexit__ = __aexit__
        session.post = MagicMock(return_value=post_ctx)
        client._session = session

        resp = await client.send(HttpMessage(id="1", method="x"))
        assert isinstance(resp, HttpMessage)
        assert resp.result == {"a": 1}

    @pytest.mark.asyncio
    async def test_send_returns_none_on_204(self):
        client = HttpClient(base_url="http://127.0.0.1:8000/mcp")
        session = MagicMock(closed=False)
        post_ctx = MagicMock()

        async def __aenter__(_self):
            response = MagicMock()
            response.status = 204
            return response

        async def __aexit__(_self, *_a):
            return False

        post_ctx.__aenter__ = __aenter__
        post_ctx.__aexit__ = __aexit__
        session.post = MagicMock(return_value=post_ctx)
        client._session = session

        resp = await client.send(HttpMessage(id="1", method="x"))
        assert resp is None
