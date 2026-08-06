"""Tests for the subscriptions/listen stream: acknowledgment ordering,
subscription-ID tagging, honored-subset semantics, and stdio integration."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from deepr.mcp import protocol_modern as pm
from deepr.mcp.subscriptions_listen import make_listen_opener, open_listen_session
from deepr.mcp.transport.stdio import Message, StdioServer


class FakeResourceHandler:
    """Mimics MCPResourceHandler's subscribe surface with real callbacks."""

    def __init__(self, reject=frozenset()):
        self.callbacks = {}
        self.unsubscribed = []
        self._reject = reject
        self._counter = 0

    async def handle_subscribe(self, uri, callback, wildcard=False, *, identity=None):
        if uri in self._reject:
            return {"error": "Resource not found"}
        self._counter += 1
        sub_id = f"sub_{self._counter}"
        self.callbacks[sub_id] = callback
        return {"subscription_id": sub_id, "uri": uri, "wildcard": wildcard}

    async def handle_unsubscribe(self, subscription_id, *, identity=None):
        self.unsubscribed.append(subscription_id)
        self.callbacks.pop(subscription_id, None)
        return {"success": True, "subscription_id": subscription_id}

    async def emit(self, notification):
        for callback in list(self.callbacks.values()):
            await callback(notification)


def _modern_params(notifications=None):
    params = {
        "_meta": {
            pm.META_PROTOCOL_VERSION: pm.MODERN_PROTOCOL_VERSION,
            pm.META_CLIENT_CAPABILITIES: {},
        }
    }
    if notifications is not None:
        params["notifications"] = notifications
    return params


def _collector():
    sent = []

    async def send(payload):
        sent.append(payload)

    return sent, send


class TestOpenListenSession:
    @pytest.mark.asyncio
    async def test_acknowledgment_is_first_and_reflects_honored_subset(self):
        handler = FakeResourceHandler()
        sent, send = _collector()
        session = await open_listen_session(
            handler,
            7,
            _modern_params(
                {
                    "resourceSubscriptions": ["deepr://campaigns/a/status"],
                    "toolsListChanged": True,  # declined: listChanged is false
                }
            ),
            send,
        )
        assert sent[0]["method"] == "notifications/subscriptions/acknowledged"
        params = sent[0]["params"]
        assert params["_meta"][pm.META_SUBSCRIPTION_ID] == 7
        assert params["notifications"] == {"resourceSubscriptions": ["deepr://campaigns/a/status"]}
        assert "toolsListChanged" not in params["notifications"]
        assert session.subscription_ids == ["sub_1"]

    @pytest.mark.asyncio
    async def test_notifications_carry_subscription_id_meta(self):
        handler = FakeResourceHandler()
        sent, send = _collector()
        await open_listen_session(
            handler, "req-1", _modern_params({"resourceSubscriptions": ["deepr://campaigns/a/status"]}), send
        )
        await handler.emit(
            {
                "jsonrpc": "2.0",
                "method": "notifications/resources/updated",
                "params": {"uri": "deepr://campaigns/a/status", "data": {}},
            }
        )
        assert len(sent) == 2
        assert sent[1]["method"] == "notifications/resources/updated"
        assert sent[1]["params"]["_meta"][pm.META_SUBSCRIPTION_ID] == "req-1"
        assert sent[1]["params"]["uri"] == "deepr://campaigns/a/status"

    @pytest.mark.asyncio
    async def test_rejected_uris_are_omitted_from_honored_filter(self):
        handler = FakeResourceHandler(reject={"deepr://campaigns/denied/status"})
        _sent, send = _collector()
        session = await open_listen_session(
            handler,
            1,
            _modern_params(
                {
                    "resourceSubscriptions": [
                        "deepr://campaigns/a/status",
                        "deepr://campaigns/denied/status",
                    ]
                }
            ),
            send,
        )
        assert session.honored["resourceSubscriptions"] == ["deepr://campaigns/a/status"]

    @pytest.mark.asyncio
    async def test_empty_filter_is_valid_and_honors_nothing(self):
        handler = FakeResourceHandler()
        sent, send = _collector()
        session = await open_listen_session(handler, 1, _modern_params(), send)
        assert session.honored == {}
        assert sent[0]["params"]["notifications"] == {}

    @pytest.mark.asyncio
    async def test_malformed_filter_rejected_before_state_created(self):
        handler = FakeResourceHandler()
        _sent, send = _collector()
        with pytest.raises(pm.JsonRpcProtocolError):
            await open_listen_session(handler, 1, _modern_params("nope"), send)
        with pytest.raises(pm.JsonRpcProtocolError):
            await open_listen_session(handler, 1, _modern_params({"resourceSubscriptions": [1, 2]}), send)
        assert handler.callbacks == {}

    @pytest.mark.asyncio
    async def test_close_unsubscribes_everything(self):
        handler = FakeResourceHandler()
        _sent, send = _collector()
        session = await open_listen_session(
            handler, 1, _modern_params({"resourceSubscriptions": ["deepr://campaigns/a/status"]}), send
        )
        await session.close()
        assert handler.unsubscribed == ["sub_1"]
        assert session.subscription_ids == []

    @pytest.mark.asyncio
    async def test_forward_waits_for_acknowledgment_gate(self):
        handler = FakeResourceHandler()
        sent = []
        release = asyncio.Event()

        async def send(payload):
            if payload.get("method") == "notifications/subscriptions/acknowledged":
                await release.wait()
            sent.append(payload)

        open_task = asyncio.create_task(
            open_listen_session(
                handler,
                1,
                _modern_params({"resourceSubscriptions": ["deepr://campaigns/a/status"]}),
                send,
            )
        )
        while not handler.callbacks:
            await asyncio.sleep(0)
        emit_task = asyncio.create_task(
            handler.emit(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/resources/updated",
                    "params": {"uri": "deepr://campaigns/a/status", "data": {}},
                }
            )
        )
        await asyncio.sleep(0.01)
        assert sent == []  # nothing may precede the acknowledgment
        release.set()
        await open_task
        await emit_task
        assert sent[0]["method"] == "notifications/subscriptions/acknowledged"
        assert sent[1]["method"] == "notifications/resources/updated"

    @pytest.mark.asyncio
    async def test_graceful_close_response_shape(self):
        handler = FakeResourceHandler()
        _sent, send = _collector()
        session = await open_listen_session(handler, 42, _modern_params(), send)
        response = session.graceful_close_response()
        assert response["id"] == 42
        assert response["result"]["resultType"] == "complete"
        assert response["result"]["_meta"][pm.META_SUBSCRIPTION_ID] == 42


class TestListenOpener:
    @pytest.mark.asyncio
    async def test_legacy_params_are_rejected(self):
        opener = make_listen_opener(FakeResourceHandler())
        with pytest.raises(pm.JsonRpcProtocolError) as excinfo:
            await opener({}, "1", AsyncMock())
        assert excinfo.value.code == pm.INVALID_PARAMS_CODE

    @pytest.mark.asyncio
    async def test_closer_graceful_sends_final_response(self):
        opener = make_listen_opener(FakeResourceHandler())
        sent, send = _collector()
        closer = await opener(_modern_params(), "9", send)
        await closer(True)
        assert sent[-1]["id"] == "9"
        assert sent[-1]["result"]["resultType"] == "complete"

    @pytest.mark.asyncio
    async def test_closer_silent_on_client_cancel(self):
        opener = make_listen_opener(FakeResourceHandler())
        sent, send = _collector()
        closer = await opener(_modern_params(), "9", send)
        acknowledged_count = len(sent)
        await closer(False)
        assert len(sent) == acknowledged_count  # no response after cancel


class TestStdioIntegration:
    @pytest.mark.asyncio
    async def test_listen_register_open_and_cancel(self):
        handler = FakeResourceHandler()
        server = StdioServer()
        server.register_streaming_method("subscriptions/listen", make_listen_opener(handler))
        server._transport.send = AsyncMock()

        response = await server._handle_message(
            Message(
                id="listen-1",
                method="subscriptions/listen",
                params=_modern_params({"resourceSubscriptions": ["deepr://campaigns/a/status"]}),
            )
        )
        assert response is None  # long-lived: no immediate response
        ack = server._transport.send.await_args_list[0].args[0]
        assert ack.method == "notifications/subscriptions/acknowledged"
        assert handler.callbacks

        cancel = await server._handle_message(
            Message(method="notifications/cancelled", params={"requestId": "listen-1"})
        )
        assert cancel is None
        assert handler.unsubscribed == ["sub_1"]
        # Client-initiated cancel: no JSON-RPC response for the request.
        assert len(server._transport.send.await_args_list) == 1

    @pytest.mark.asyncio
    async def test_listen_rejects_legacy_request_with_error(self):
        server = StdioServer()
        server.register_streaming_method("subscriptions/listen", make_listen_opener(FakeResourceHandler()))
        server._transport.send = AsyncMock()
        response = await server._handle_message(Message(id="1", method="subscriptions/listen", params={}))
        assert response is not None
        assert response.error["code"] == pm.INVALID_PARAMS_CODE

    @pytest.mark.asyncio
    async def test_stop_closes_streams_gracefully(self):
        handler = FakeResourceHandler()
        server = StdioServer()
        server.register_streaming_method("subscriptions/listen", make_listen_opener(handler))
        server._transport.send = AsyncMock()
        server._transport.stop = AsyncMock()

        await server._handle_message(
            Message(
                id="listen-1",
                method="subscriptions/listen",
                params=_modern_params({"resourceSubscriptions": ["deepr://campaigns/a/status"]}),
            )
        )
        await server.stop()
        final = server._transport.send.await_args_list[-1].args[0]
        assert final.id == "listen-1"
        assert final.result["resultType"] == "complete"
        assert handler.unsubscribed == ["sub_1"]

    @pytest.mark.asyncio
    async def test_protocol_error_from_regular_method_maps_to_error_response(self):
        server = StdioServer()

        async def failing(params):
            raise pm.unsupported_protocol_version_error("2030-01-01")

        server.register_method("tools/list", failing)
        response = await server._handle_message(Message(id="1", method="tools/list", params={}))
        assert response.error["code"] == pm.UNSUPPORTED_PROTOCOL_VERSION_CODE
        assert response.error["data"]["requested"] == "2030-01-01"

    @pytest.mark.asyncio
    async def test_unrelated_cancelled_notification_is_ignored(self):
        server = StdioServer()
        result = await server._handle_message(Message(method="notifications/cancelled", params={"requestId": "ghost"}))
        assert result is None
