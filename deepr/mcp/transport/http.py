"""
HTTP Transport for MCP.

Implements Streamable HTTP transport with chunked transfer encoding
for cloud-based deployment scenarios. Supports bidirectional
communication over a single HTTP connection.

Use Cases:
- Cloud-based research farms
- Remote Deepr server deployment
- Enterprise network constraints (no WebSockets)
"""

import asyncio
import hmac
import ipaddress
import json
import logging
import os
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

import aiohttp
from aiohttp import web

logger = logging.getLogger(__name__)


def _is_loopback_host(host: str) -> bool:
    """Return True if host is a loopback address ('localhost', 127.0.0.0/8, ::1)."""
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _extract_bearer(request: "web.Request") -> Optional[str]:
    """Return the Bearer token from Authorization, or X-Api-Key value, if any."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if token:
            return token
    api_key = request.headers.get("X-Api-Key", "").strip()
    return api_key or None


@dataclass
class HttpMessage:
    """A JSON-RPC message for HTTP transport."""

    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: Optional[str] = None
    params: Optional[dict] = None
    result: Optional[Any] = None
    error: Optional[dict] = None

    def is_request(self) -> bool:
        return self.method is not None and self.id is not None

    def is_notification(self) -> bool:
        return self.method is not None and self.id is None

    def is_response(self) -> bool:
        return self.result is not None or self.error is not None

    def to_dict(self) -> dict:
        d = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            d["id"] = self.id
        if self.method is not None:
            d["method"] = self.method
        if self.params is not None:
            d["params"] = self.params
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "HttpMessage":
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error"),
        )


@dataclass
class HttpTransportStats:
    """Statistics for HTTP transport monitoring."""

    requests_received: int = 0
    responses_sent: int = 0
    notifications_sent: int = 0
    bytes_received: int = 0
    bytes_sent: int = 0
    errors: int = 0
    active_streams: int = 0
    started_at: datetime = field(default_factory=datetime.now)


class StreamingHttpTransport:
    """
    Streamable HTTP transport for MCP.

    Implements bidirectional communication using:
    - POST requests for client-to-server messages
    - Server-Sent Events (SSE) for server-to-client streaming
    - Chunked transfer encoding for large responses

    This transport is suitable for cloud deployment where
    the Deepr research engine runs on a remote server.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        path: str = "/mcp",
        auth_token: Optional[str] = None,
        allow_unauthenticated_public_bind: bool = False,
    ):
        """Initialize the streaming HTTP transport.

        Args:
            host: Interface to bind. Defaults to loopback. Use 0.0.0.0 only with
                an auth_token configured.
            port: TCP port to bind.
            path: Base path for the MCP routes.
            auth_token: Shared secret required as `Authorization: Bearer <token>`
                or `X-Api-Key` on POST and SSE. If None, falls back to
                MCP_AUTH_TOKEN / DEEPR_MCP_AUTH_TOKEN environment variables.
            allow_unauthenticated_public_bind: Set True to bind a non-loopback
                interface without auth. Refused otherwise so the unauthenticated
                MCP tool surface is not silently exposed.
        """
        self._host = host
        self._port = port
        self._path = path
        self._auth_token = auth_token or os.getenv("MCP_AUTH_TOKEN") or os.getenv("DEEPR_MCP_AUTH_TOKEN") or None
        self._allow_unauthenticated_public_bind = allow_unauthenticated_public_bind
        self._handler: Optional[Callable[[HttpMessage], Awaitable[Optional[HttpMessage]]]] = None
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._stats = HttpTransportStats()
        self._subscribers: dict[str, asyncio.Queue] = {}
        self._running = False

    def on_message(self, handler: Callable[[HttpMessage], Awaitable[Optional[HttpMessage]]]) -> None:
        """Set the message handler for incoming requests."""
        self._handler = handler

    async def start(self) -> None:
        """Start the HTTP server.

        Refuses to bind a non-loopback interface without an auth_token unless
        the caller explicitly opted in via allow_unauthenticated_public_bind.
        The MCP tool surface exposes research submission, result retrieval,
        expert queries, and agentic workflows backed by provider API keys, so
        exposing it unauthenticated would let any reachable peer consume the
        operator's provider budget and read private expert/research data.
        """
        if self._running:
            return

        loopback = _is_loopback_host(self._host)
        if not loopback and not self._auth_token and not self._allow_unauthenticated_public_bind:
            raise RuntimeError(
                f"Refusing to bind MCP HTTP transport to {self._host!r} without an auth token. "
                "Set MCP_AUTH_TOKEN (or DEEPR_MCP_AUTH_TOKEN), pass auth_token=..., "
                "or set allow_unauthenticated_public_bind=True if you accept the risk."
            )
        if not loopback and not self._auth_token:
            logger.warning(
                "MCP HTTP transport binding %s without authentication. Any reachable peer can "
                "invoke MCP tools (research submission, expert queries) and consume provider budget.",
                self._host,
            )

        self._app = web.Application()
        self._app.router.add_post(self._path, self._handle_post)
        self._app.router.add_get(f"{self._path}/stream", self._handle_stream)
        self._app.router.add_get(f"{self._path}/health", self._handle_health)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()

        self._running = True

    async def stop(self) -> None:
        """Stop the HTTP server."""
        self._running = False

        # Close all subscriber streams
        for queue in self._subscribers.values():
            await queue.put(None)
        self._subscribers.clear()

        if self._runner:
            await self._runner.cleanup()

    def _check_auth(self, request: "web.Request") -> Optional[web.Response]:
        """Return an unauthorized response if auth fails, else None.

        Authentication is required whenever a token is configured. When the
        transport is bound to loopback and no token is configured, requests
        are allowed (local-dev mode). When the transport is bound to a
        non-loopback interface, configuring a token is enforced at start().
        """
        token = self._auth_token
        if not token:
            return None
        provided = _extract_bearer(request)
        # hmac.compare_digest raises TypeError on str inputs that contain
        # non-ASCII characters; treat that as Unauthorized so a malformed
        # Authorization / X-Api-Key header cannot escape into the generic
        # 500 handler (same fix as deepr/web/app.py and deepr/api/app.py).
        ok = False
        if provided:
            try:
                ok = hmac.compare_digest(provided, token)
            except TypeError:
                ok = False
        if not ok:
            return web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized"}, "id": None},
                status=401,
            )
        return None

    async def _handle_post(self, request: web.Request) -> web.Response:
        """Handle incoming POST requests (JSON-RPC messages)."""
        unauthorized = self._check_auth(request)
        if unauthorized is not None:
            self._stats.errors += 1
            return unauthorized
        try:
            body = await request.read()
            self._stats.bytes_received += len(body)
            self._stats.requests_received += 1

            data = json.loads(body.decode("utf-8"))
            message = HttpMessage.from_dict(data)

            if self._handler:
                response = await self._handler(message)

                if response:
                    response_data = json.dumps(response.to_dict())
                    self._stats.bytes_sent += len(response_data)
                    self._stats.responses_sent += 1

                    return web.Response(
                        text=response_data,
                        content_type="application/json",
                    )

            # No response needed (notification)
            return web.Response(status=204)

        except json.JSONDecodeError:
            self._stats.errors += 1
            return web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
                status=400,
            )
        except Exception as e:
            self._stats.errors += 1
            return web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": None},
                status=500,
            )

    async def _handle_stream(self, request: web.Request) -> web.StreamResponse:
        """
        Handle SSE stream for server-to-client notifications.

        Clients connect here to receive push notifications
        (e.g., resource updates, job progress).
        """
        unauthorized = self._check_auth(request)
        if unauthorized is not None:
            self._stats.errors += 1
            return unauthorized
        subscriber_id = request.query.get("subscriber_id", str(id(request)))

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

        # Create queue for this subscriber. If a previous connection
        # used the same subscriber_id (reconnect, or two clients omitting
        # the id and id(request) colliding), signal that handler to
        # close cleanly before replacing the queue. Without this the
        # old handler keeps draining a queue nobody ever puts to —
        # a zombie stream that only times out 30s later.
        old_queue = self._subscribers.pop(subscriber_id, None)
        if old_queue is not None:
            try:
                old_queue.put_nowait(None)  # Sentinel triggers `break` in the old loop
            except asyncio.QueueFull:
                pass

        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[subscriber_id] = queue
        self._stats.active_streams += 1

        try:
            while self._running:
                try:
                    # Wait for notification with timeout
                    notification = await asyncio.wait_for(queue.get(), timeout=30.0)

                    if notification is None:
                        break

                    # Send as SSE event
                    event_data = f"data: {json.dumps(notification)}\n\n"
                    await response.write(event_data.encode("utf-8"))
                    self._stats.notifications_sent += 1
                    self._stats.bytes_sent += len(event_data)

                except asyncio.TimeoutError:
                    # Send keepalive
                    await response.write(b": keepalive\n\n")

        finally:
            self._stats.active_streams -= 1
            self._subscribers.pop(subscriber_id, None)

        return response

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response(
            {
                "status": "healthy",
                "uptime_seconds": (datetime.now() - self._stats.started_at).total_seconds(),
                "active_streams": self._stats.active_streams,
            }
        )

    async def broadcast(self, notification: dict) -> int:
        """
        Broadcast a notification to all connected subscribers.

        Returns the number of subscribers notified.
        """
        count = 0
        for queue in self._subscribers.values():
            try:
                await queue.put(notification)
                count += 1
            except Exception as exc:
                self._stats.errors += 1
                logger.warning("Failed to broadcast MCP notification to subscriber: %s", exc)
        return count

    async def send_to(self, subscriber_id: str, notification: dict) -> bool:
        """
        Send a notification to a specific subscriber.

        Returns True if sent, False if subscriber not found.
        """
        queue = self._subscribers.get(subscriber_id)
        if queue:
            await queue.put(notification)
            return True
        return False

    @property
    def stats(self) -> HttpTransportStats:
        return self._stats

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_local(self) -> bool:
        """HTTP transport is not local - data goes over network."""
        return False

    @property
    def url(self) -> str:
        """Get the server URL."""
        return f"http://{self._host}:{self._port}{self._path}"


class HttpClient:
    """
    HTTP client for connecting to a remote MCP server.

    Used when Deepr runs as a remote service and Claude
    needs to connect to it over HTTP.
    """

    def __init__(self, base_url: str, timeout: float = 30.0, auth_token: Optional[str] = None):
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._auth_token = auth_token or os.getenv("MCP_AUTH_TOKEN") or os.getenv("DEEPR_MCP_AUTH_TOKEN") or None
        self._session: Optional[aiohttp.ClientSession] = None
        self._stream_task: Optional[asyncio.Task] = None
        self._notification_handler: Optional[Callable[[dict], Awaitable[None]]] = None

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._auth_token}"} if self._auth_token else {}

    async def connect(self) -> None:
        """Establish connection to the server."""
        self._session = aiohttp.ClientSession(timeout=self._timeout)

    async def disconnect(self) -> None:
        """Close the connection."""
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass

        if self._session:
            await self._session.close()

    async def send(self, message: HttpMessage) -> Optional[HttpMessage]:
        """
        Send a message to the server and get response.

        Args:
            message: The message to send

        Returns:
            Response message, or None for notifications (no response expected)

        Raises:
            RuntimeError: If not connected (call connect() first)
            aiohttp.ClientError: On network errors
        """
        if not self._session:
            raise RuntimeError("Not connected. Call connect() first.")

        if self._session.closed:
            raise RuntimeError("Session is closed. Call connect() to reconnect.")

        async with self._session.post(
            self._base_url,
            json=message.to_dict(),
            headers={"Content-Type": "application/json", **self._auth_headers()},
        ) as response:
            if response.status == 204:
                return None

            data = await response.json()
            return HttpMessage.from_dict(data)

    def on_notification(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        """Set handler for incoming notifications."""
        self._notification_handler = handler

    async def subscribe(self, subscriber_id: Optional[str] = None) -> None:
        """
        Start listening for server notifications via SSE.

        Notifications are delivered to the handler set via on_notification().

        Args:
            subscriber_id: Optional identifier for this subscriber.
                          Used for targeted notifications.

        Raises:
            RuntimeError: If not connected (call connect() first)
        """
        if not self._session:
            raise RuntimeError("Not connected. Call connect() first.")

        if self._session.closed:
            raise RuntimeError("Session is closed. Call connect() to reconnect.")

        url = f"{self._base_url}/stream"
        if subscriber_id:
            url += f"?subscriber_id={subscriber_id}"

        self._stream_task = asyncio.create_task(self._stream_loop(url))

    async def _stream_loop(self, url: str) -> None:
        """Internal loop for processing SSE stream."""
        try:
            async with self._session.get(url, headers=self._auth_headers()) as response:
                async for line in response.content:
                    line_str = line.decode("utf-8").strip()

                    if line_str.startswith("data: "):
                        data = json.loads(line_str[6:])
                        if self._notification_handler:
                            await self._notification_handler(data)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            # Reconnect logic could go here
            logger.warning("MCP HTTP stream loop terminated with error for %s: %s", url, exc)


# Convenience alias
HttpTransport = StreamingHttpTransport
