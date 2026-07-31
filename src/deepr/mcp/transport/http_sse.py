"""SSE event writing for the Streamable HTTP transport.

Keeps the event-loop mechanics of a long-lived ``subscriptions/listen``
response stream out of the transport module: the transport owns admission,
authorization, and lifecycle, while this module owns the wire format.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any, Protocol

from aiohttp import web

logger = logging.getLogger(__name__)

# Idle interval between SSE comment keep-alives. Long-lived listen streams go
# quiet for long stretches; without a periodic byte, proxies and client idle
# timeouts drop the connection.
KEEPALIVE_SECONDS = 15.0

# The legacy standalone stream used a longer idle interval; preserved so its
# observable timing does not change for existing clients.
LEGACY_KEEPALIVE_SECONDS = 30.0

_KEEPALIVE_FRAME = b": keepalive\n\n"


class SseWriter(Protocol):
    """The subset of ``web.StreamResponse`` used to emit events."""

    async def write(self, data: bytes) -> None: ...


def encode_event(payload: dict[str, Any]) -> bytes:
    """Encode one JSON-RPC payload as an SSE ``data:`` frame."""
    return f"data: {json.dumps(payload, default=str)}\n\n".encode()


async def pump_events(
    response: SseWriter,
    queue: asyncio.Queue[dict[str, Any] | None],
    *,
    is_running: Callable[[], bool],
    on_event: Callable[[int], None],
) -> bool:
    """Write queued payloads to the stream until it ends.

    Returns True when the stream ended on the server's initiative (a ``None``
    sentinel or transport shutdown), which is what tells the caller to emit
    the spec's graceful close response. Returns False only if the loop is
    entered while already stopping.
    """
    while is_running():
        try:
            payload = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
        except TimeoutError:
            await response.write(_KEEPALIVE_FRAME)
            continue
        if payload is None:
            return True
        frame = encode_event(payload)
        await response.write(frame)
        on_event(len(frame))
    return True


async def serve_legacy_stream(
    request: web.Request,
    *,
    subscriber_id: str,
    subscribers: dict[str, asyncio.Queue[Any]],
    stats: Any,
    is_running: Callable[[], bool],
) -> web.StreamResponse:
    """Run the legacy standalone SSE notification stream.

    Superseded by ``subscriptions/listen`` for modern clients; kept for
    handshake-era clients that open a separate notification stream.
    """
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await response.prepare(request)

    # Create the queue for this subscriber. If a previous connection used the
    # same subscriber_id (reconnect, or two clients omitting the id and
    # id(request) colliding), signal that handler to close cleanly before
    # replacing the queue. Without this the old handler keeps draining a queue
    # nobody ever puts to - a zombie stream that only times out later.
    old_queue = subscribers.pop(subscriber_id, None)
    if old_queue is not None:
        try:
            old_queue.put_nowait(None)  # Sentinel triggers `break` in the old loop
        except asyncio.QueueFull:
            logger.debug("Legacy stream sentinel dropped for subscriber %s (queue full)", subscriber_id)

    queue: asyncio.Queue[Any] = asyncio.Queue()
    subscribers[subscriber_id] = queue
    stats.active_streams += 1
    try:
        while is_running():
            try:
                notification = await asyncio.wait_for(queue.get(), timeout=LEGACY_KEEPALIVE_SECONDS)
                if notification is None:
                    break
                frame = encode_event(notification)
                await response.write(frame)
                stats.notifications_sent += 1
                stats.bytes_sent += len(frame)
            except TimeoutError:
                await response.write(_KEEPALIVE_FRAME)
    finally:
        stats.active_streams -= 1
        # Only remove the entry if it still points at THIS handler's queue.
        # When a reconnect with the same subscriber_id replaces ``queue``, the
        # old handler exits via its sentinel - but its finally block must NOT
        # pop the new owner, which would stall delivery until the next
        # reconnect.
        if subscribers.get(subscriber_id) is queue:
            subscribers.pop(subscriber_id, None)
    return response


async def drain_remaining(response: SseWriter, queue: asyncio.Queue[dict[str, Any] | None]) -> None:
    """Flush any already-queued payloads (e.g. the graceful close response).

    A peer that has gone away makes the write fail; that is an expected end
    state during shutdown, not an error to propagate.
    """
    while not queue.empty():
        payload = queue.get_nowait()
        if payload is None:
            continue
        try:
            await response.write(encode_event(payload))
        except (ConnectionResetError, RuntimeError):
            return


__all__ = [
    "KEEPALIVE_SECONDS",
    "LEGACY_KEEPALIVE_SECONDS",
    "SseWriter",
    "drain_remaining",
    "encode_event",
    "pump_events",
    "serve_legacy_stream",
]
