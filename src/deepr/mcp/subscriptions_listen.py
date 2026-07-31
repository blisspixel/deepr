"""The 2026-07-28 ``subscriptions/listen`` stream, shared by both transports.

``subscriptions/listen`` replaces the legacy ``resources/subscribe`` RPC and
the custom HTTP GET notification stream for modern clients
(https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/subscriptions).

Deepr honors the ``resourceSubscriptions`` filter (resource-updated
notifications for explicit URIs). The list-changed filters are declined: the
tool, prompt, and resource list surfaces advertise ``listChanged: false``, so
the acknowledgment omits those fields per spec.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from deepr.mcp import protocol_modern as pm
from deepr.mcp.request_context import MCPRequestIdentity

# One listen request may not register an unbounded number of resource
# subscriptions: SubscriptionManager registers duplicates independently, so an
# uncapped list turns one resource update into a notification flood (N per
# update, per stream). URIs are deduplicated and the count is capped.
MAX_RESOURCE_SUBSCRIPTIONS = 64

SendPayload = Callable[[dict[str, Any]], Awaitable[None]]
# closer(graceful): tear the stream down; graceful=True additionally sends the
# spec's empty listen response so the client sees a clean server-initiated end.
StreamCloser = Callable[[bool], Awaitable[None]]
# The request id keeps its JSON-RPC type (string or integer): the spec echoes
# it verbatim as io.modelcontextprotocol/subscriptionId.
StreamOpener = Callable[[dict[str, Any], "str | int", SendPayload], Awaitable[StreamCloser]]


@dataclass
class ListenSession:
    """One active subscriptions/listen stream (request-scoped state)."""

    request_id: str | int
    honored: dict[str, Any]
    subscription_ids: list[str]
    resource_handler: Any
    identity: MCPRequestIdentity | None = None
    # Gates forwarded notifications until the acknowledgment is on the wire:
    # the spec forbids any notification on the subscription before it.
    acknowledged: asyncio.Event = field(default_factory=asyncio.Event)
    # Set at the start of close() so no notification is forwarded after
    # cancellation, even while the unsubscribes are still awaiting.
    closed: bool = False

    async def close(self) -> None:
        self.closed = True
        # Unblock any in-flight forward waiting on the acknowledgment gate so
        # SubscriptionManager.emit is never wedged by a dead stream.
        self.acknowledged.set()
        for sub_id in self.subscription_ids:
            await self.resource_handler.handle_unsubscribe(sub_id, identity=self.identity)
        self.subscription_ids.clear()

    def acknowledged_notification(self) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "method": "notifications/subscriptions/acknowledged",
            "params": {
                "_meta": {pm.META_SUBSCRIPTION_ID: self.request_id},
                "notifications": self.honored,
            },
        }

    def graceful_close_response(self) -> dict[str, Any]:
        # The JSON-RPC response to the long-lived listen request: signals a
        # server-initiated graceful end, as opposed to a bare transport drop.
        return {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "result": {
                "resultType": "complete",
                "_meta": {pm.META_SUBSCRIPTION_ID: self.request_id},
            },
        }


def _validated_resource_uris(params: dict[str, Any]) -> list[str]:
    notifications = params.get("notifications")
    if notifications is None:
        return []
    if not isinstance(notifications, dict):
        raise pm.JsonRpcProtocolError(
            pm.INVALID_PARAMS_CODE,
            "subscriptions/listen notifications filter must be an object",
        )
    raw_uris = notifications.get("resourceSubscriptions", [])
    if not isinstance(raw_uris, list) or not all(isinstance(uri, str) for uri in raw_uris):
        raise pm.JsonRpcProtocolError(
            pm.INVALID_PARAMS_CODE,
            "notifications.resourceSubscriptions must be an array of resource URIs",
        )
    # dict.fromkeys dedupes while preserving the client's ordering.
    unique_uris = list(dict.fromkeys(raw_uris))
    if len(unique_uris) > MAX_RESOURCE_SUBSCRIPTIONS:
        raise pm.JsonRpcProtocolError(
            pm.INVALID_PARAMS_CODE,
            "notifications.resourceSubscriptions exceeds the per-request limit of "
            f"{MAX_RESOURCE_SUBSCRIPTIONS} unique URIs",
            data={"limit": MAX_RESOURCE_SUBSCRIPTIONS, "requested": len(unique_uris)},
        )
    return unique_uris


async def open_listen_session(
    resource_handler: Any,
    request_id: str | int,
    params: dict[str, Any],
    send: SendPayload,
    *,
    identity: MCPRequestIdentity | None = None,
) -> ListenSession:
    """Register the honored filter subset and emit the acknowledgment.

    Callers receive a session whose subscriptions only start forwarding after
    the acknowledgment has been sent (spec ordering requirement). Raises
    JsonRpcProtocolError on a malformed filter before any state is created.
    """
    requested_uris = _validated_resource_uris(params)

    session = ListenSession(
        request_id=request_id,
        honored={},
        subscription_ids=[],
        resource_handler=resource_handler,
        identity=identity,
    )

    async def _forward(notification: dict[str, Any]) -> None:
        if not session.acknowledged.is_set():
            await session.acknowledged.wait()
        if session.closed:
            return  # nothing may be forwarded after cancellation/close
        payload = dict(notification)
        raw_params = payload.get("params")
        notif_params = dict(raw_params) if isinstance(raw_params, dict) else {}
        meta = notif_params.get("_meta")
        notif_params["_meta"] = {
            **(meta if isinstance(meta, dict) else {}),
            pm.META_SUBSCRIPTION_ID: request_id,
        }
        payload["params"] = notif_params
        await send(payload)

    accepted_uris: list[str] = []
    try:
        for uri in requested_uris:
            outcome = await resource_handler.handle_subscribe(uri, _forward, identity=identity)
            sub_id = outcome.get("subscription_id")
            if isinstance(sub_id, str):
                session.subscription_ids.append(sub_id)
                accepted_uris.append(uri)
        if accepted_uris:
            session.honored["resourceSubscriptions"] = accepted_uris
        await send(session.acknowledged_notification())
    except BaseException:
        # Never leak registered subscriptions when a later subscribe or the
        # acknowledgment send fails.
        await session.close()
        raise
    session.acknowledged.set()
    return session


def make_listen_opener(
    resource_handler: Any,
    *,
    identity_provider: Callable[[], MCPRequestIdentity | None] | None = None,
) -> StreamOpener:
    """Build the transport-facing opener for ``subscriptions/listen``.

    The opener validates the modern per-request ``_meta`` (the method does not
    exist in legacy revisions), opens the session, and returns a closer the
    transport invokes on cancellation (client-initiated: silent) or shutdown
    (server-initiated: graceful empty response first).
    """

    async def _opener(params: dict[str, Any], request_id: str | int, send: SendPayload) -> StreamCloser:
        context = pm.modern_request_context(params)
        if context is None:
            raise pm.JsonRpcProtocolError(
                pm.INVALID_PARAMS_CODE,
                "subscriptions/listen requires modern per-request _meta "
                f"({pm.META_PROTOCOL_VERSION} and {pm.META_CLIENT_CAPABILITIES})",
            )
        identity = identity_provider() if identity_provider is not None else None
        session = await open_listen_session(
            resource_handler,
            request_id,
            params,
            send,
            identity=identity,
        )

        async def _close(graceful: bool) -> None:
            await session.close()
            if graceful:
                await send(session.graceful_close_response())

        return _close

    return _opener


__all__ = [
    "ListenSession",
    "SendPayload",
    "StreamCloser",
    "StreamOpener",
    "make_listen_opener",
    "open_listen_session",
]
