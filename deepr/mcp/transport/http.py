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
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

import aiohttp
from aiohttp import web


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
        host: str = "0.0.0.0",
        port: int = 8765,
        path: str = "/mcp",
    ):
        self._host = host
        self._port = port
        self._path = path
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
        """Start the HTTP server."""
        if self._running:
            return

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

    async def _handle_post(self, request: web.Request) -> web.Response:
        """Handle incoming POST requests (JSON-RPC messages)."""
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

        # Create queue for this subscriber
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
            except Exception:
                pass
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

    def __init__(self, base_url: str, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        self._stream_task: Optional[asyncio.Task] = None
        self._notification_handler: Optional[Callable[[dict], Awaitable[None]]] = None

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
            headers={"Content-Type": "application/json"},
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
            async with self._session.get(url) as response:
                async for line in response.content:
                    line_str = line.decode("utf-8").strip()

                    if line_str.startswith("data: "):
                        data = json.loads(line_str[6:])
                        if self._notification_handler:
                            await self._notification_handler(data)

        except asyncio.CancelledError:
            pass
        except Exception:
            # Reconnect logic could go here
            pass


# Convenience alias
HttpTransport = StreamingHttpTransport
