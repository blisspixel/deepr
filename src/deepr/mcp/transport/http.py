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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from deepr.mcp.security.scoped_keys import (
    RemoteMCPAuditLog,
    ScopedMCPAuthzDecision,
    ScopedMCPBudgetDecision,
    ScopedMCPKeyContext,
    ScopedMCPKeyStore,
    ScopedMCPRateLimitDecision,
    authorize_scoped_mcp_budget,
    authorize_scoped_mcp_rate_limit,
    authorize_scoped_mcp_tool_call,
    constrain_scoped_mcp_budget_arguments,
)

logger = logging.getLogger(__name__)


def _is_loopback_host(host: str) -> bool:
    """Return True if host is a loopback address ('localhost', 127.0.0.0/8, ::1)."""
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _extract_bearer(request: "web.Request") -> str | None:
    """Return the Bearer token from Authorization, or X-Api-Key value, if any."""
    auth: str = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if token:
            return token
    api_key: str = request.headers.get("X-Api-Key", "").strip()
    return api_key or None


def _scoped_key_store_from_env() -> ScopedMCPKeyStore | None:
    path = os.getenv("DEEPR_MCP_KEYS_PATH", "").strip()
    return ScopedMCPKeyStore(Path(path)) if path else None


@dataclass
class HttpMessage:
    """A JSON-RPC message for HTTP transport."""

    jsonrpc: str = "2.0"
    id: str | None = None
    method: str | None = None
    params: dict[str, Any] | None = None
    result: Any | None = None
    error: dict[str, Any] | None = None

    def is_request(self) -> bool:
        return self.method is not None and self.id is not None

    def is_notification(self) -> bool:
        return self.method is not None and self.id is None

    def is_response(self) -> bool:
        return self.result is not None or self.error is not None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc}
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
    def from_dict(cls, data: dict[str, Any]) -> "HttpMessage":
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
        auth_token: str | None = None,
        allow_unauthenticated_public_bind: bool = False,
        scoped_key_store: ScopedMCPKeyStore | None = None,
        audit_log: RemoteMCPAuditLog | None = None,
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
            scoped_key_store: Optional scoped-key store for remote MCP callers.
                When configured, requests authenticate against per-key mode,
                expert, and budget metadata instead of only a shared token.
            audit_log: Optional append-only audit sink for scoped-key calls.
        """
        self._host = host
        self._port = port
        self._path = path
        self._auth_token = auth_token or os.getenv("MCP_AUTH_TOKEN") or os.getenv("DEEPR_MCP_AUTH_TOKEN") or None
        self._allow_unauthenticated_public_bind = allow_unauthenticated_public_bind
        self._scoped_key_store = scoped_key_store or _scoped_key_store_from_env()
        self._audit_log = (
            audit_log if audit_log is not None else RemoteMCPAuditLog() if self._scoped_key_store else None
        )
        self._handler: Callable[[HttpMessage], Awaitable[HttpMessage | None]] | None = None
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._stats = HttpTransportStats()
        self._subscribers: dict[str, asyncio.Queue[Any]] = {}
        self._running = False

    def on_message(self, handler: Callable[[HttpMessage], Awaitable[HttpMessage | None]]) -> None:
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
        has_scoped_keys = bool(self._scoped_key_store and self._scoped_key_store.has_active_keys())
        if (
            not loopback
            and not self._auth_token
            and not has_scoped_keys
            and not self._allow_unauthenticated_public_bind
        ):
            raise RuntimeError(
                f"Refusing to bind MCP HTTP transport to {self._host!r} without an auth token or scoped key. "
                "Set MCP_AUTH_TOKEN (or DEEPR_MCP_AUTH_TOKEN), pass auth_token=..., "
                "configure DEEPR_MCP_KEYS_PATH with at least one active key, "
                "or set allow_unauthenticated_public_bind=True if you accept the risk."
            )
        if not loopback and not self._auth_token and not has_scoped_keys:
            logger.warning(
                "MCP HTTP transport binding %s without authentication. Any reachable peer can "
                "invoke MCP tools (research submission, expert queries) and consume provider budget.",
                self._host,
            )

        # Hard cap on request body size. aiohttp defaults to 1 MiB but
        # set it explicitly so the limit is auditable and aligns with the
        # webhook + A2A surfaces.
        self._app = web.Application(client_max_size=1 * 1024 * 1024)
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

    def _unauthorized_response(self) -> web.Response:
        return web.json_response(
            {"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized"}, "id": None},
            status=401,
        )

    def _shared_token_matches(self, provided: str | None) -> bool:
        token = self._auth_token
        if not token or not provided:
            return False
        try:
            return hmac.compare_digest(provided, token)
        except TypeError:
            return False

    def _authenticate_request(self, request: "web.Request") -> tuple[ScopedMCPKeyContext | None, web.Response | None]:
        """Authenticate a request and return scoped context when a key matched."""
        provided = _extract_bearer(request)
        if self._scoped_key_store:
            context = self._scoped_key_store.authenticate(provided)
            if context:
                return context, None
            if self._shared_token_matches(provided):
                return None, None
            return None, self._unauthorized_response()
        if self._auth_token and not self._shared_token_matches(provided):
            return None, self._unauthorized_response()
        return None, None

    def _check_auth(self, request: "web.Request") -> web.Response | None:
        """Return an unauthorized response if auth fails, else None.

        Authentication is required whenever a token is configured. When the
        transport is bound to loopback and no token is configured, requests
        are allowed (local-dev mode). When the transport is bound to a
        non-loopback interface, configuring a token is enforced at start().
        """
        return self._authenticate_request(request)[1]

    def _tool_call_parts(self, message: HttpMessage) -> tuple[str, dict[str, Any]]:
        if message.method != "tools/call" or not isinstance(message.params, dict):
            return message.method or "", {}
        tool_name = str(message.params.get("name") or "")
        arguments = message.params.get("arguments", {})
        return tool_name, dict(arguments) if isinstance(arguments, dict) else {}

    def _scoped_denial_message(self, message: HttpMessage, decision: ScopedMCPAuthzDecision) -> HttpMessage:
        return HttpMessage(
            id=message.id,
            error={
                "code": -32003,
                "message": decision.reason,
                "data": {
                    "error_code": decision.error_code,
                    "requires_confirmation": decision.requires_confirmation,
                    "requested_experts": list(decision.requested_experts),
                },
            },
        )

    def _scoped_budget_denial_message(self, message: HttpMessage, decision: ScopedMCPBudgetDecision) -> HttpMessage:
        return HttpMessage(
            id=message.id,
            error={
                "code": -32004,
                "message": decision.reason,
                "data": {
                    "error_code": decision.error_code,
                    "budget_limit_usd": decision.budget_limit_usd,
                    "spent_usd": decision.spent_usd,
                    "remaining_usd": decision.remaining_usd,
                    "estimated_cost_usd": decision.estimated_cost_usd,
                },
            },
        )

    def _scoped_rate_limit_denial_message(
        self,
        message: HttpMessage,
        decision: ScopedMCPRateLimitDecision,
    ) -> HttpMessage:
        return HttpMessage(
            id=message.id,
            error={
                "code": -32005,
                "message": decision.reason,
                "data": {
                    "error_code": decision.error_code,
                    "limit_per_minute": decision.limit_per_minute,
                    "calls_in_window": decision.calls_in_window,
                    "window_seconds": decision.window_seconds,
                    "retry_after_seconds": decision.retry_after_seconds,
                },
            },
        )

    def _scoped_rate_limit_decision(self, context: ScopedMCPKeyContext) -> ScopedMCPRateLimitDecision:
        if not self._audit_log:
            return authorize_scoped_mcp_rate_limit(context, 0)
        now = datetime.now(UTC)
        window_seconds = 60
        calls_in_window = self._audit_log.count_for_key_since(
            context.key_id,
            now - timedelta(seconds=window_seconds),
        )
        retry_after = self._audit_log.retry_after_seconds_for_key(
            context.key_id,
            now=now,
            window_seconds=window_seconds,
        )
        return authorize_scoped_mcp_rate_limit(
            context,
            calls_in_window,
            window_seconds=window_seconds,
            retry_after_seconds=retry_after or None,
        )

    def _scoped_key_spent(self, context: ScopedMCPKeyContext) -> float:
        if not self._audit_log:
            return 0.0
        return self._audit_log.total_cost_for_key(context.key_id)

    def _payload_from_tool_response(self, response: HttpMessage | None) -> dict[str, Any] | None:
        if not response or response.error or not isinstance(response.result, dict):
            return None
        if response.result.get("isError") is True:
            return None
        content = response.result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and isinstance(first.get("text"), str):
                try:
                    payload = json.loads(first["text"])
                except json.JSONDecodeError:
                    return None
                return payload if isinstance(payload, dict) else None
        return response.result

    def _response_cost_usd(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        response: HttpMessage | None,
    ) -> float | None:
        payload = self._payload_from_tool_response(response)
        if not payload or "error_code" in payload:
            return None

        def read_cost(field: str) -> float | None:
            value = payload.get(field)
            if value is None or isinstance(value, bool):
                return None
            try:
                resolved = float(value)
            except (TypeError, ValueError):
                return None
            return max(resolved, 0.0)

        if tool_name == "deepr_get_result":
            return read_cost("cost_final")
        if tool_name == "deepr_query_expert":
            return read_cost("cost")
        if tool_name == "deepr_expert_absorb":
            return read_cost("estimated_cost")
        if tool_name == "deepr_expert_validate":
            return 0.02
        if tool_name == "deepr_reflect":
            try:
                depth = int(arguments.get("depth", 1) or 1)
            except (TypeError, ValueError):
                depth = 1
            return 0.02 if depth > 0 else 0.0
        return None

    def _record_remote_call(
        self,
        context: ScopedMCPKeyContext | None,
        message: HttpMessage,
        response: HttpMessage | None,
        *,
        error_code: str = "",
    ) -> None:
        if not context or not self._audit_log:
            return
        tool_name, arguments = self._tool_call_parts(message)
        if not tool_name:
            return
        outcome = "error" if error_code or (response and response.error) else "success"
        resolved_error = error_code
        if response and response.error and not resolved_error:
            data = response.error.get("data")
            if isinstance(data, dict):
                resolved_error = str(data.get("error_code") or "")
        self._audit_log.record_tool_call(
            context,
            tool=tool_name,
            arguments=arguments,
            outcome=outcome,
            error_code=resolved_error,
            cost_usd=self._response_cost_usd(tool_name, arguments, response),
        )

    async def _handle_post(self, request: web.Request) -> web.Response:
        """Handle incoming POST requests (JSON-RPC messages)."""
        auth_context, unauthorized = self._authenticate_request(request)
        if unauthorized is not None:
            self._stats.errors += 1
            return unauthorized
        try:
            body = await request.read()
            self._stats.bytes_received += len(body)
            self._stats.requests_received += 1

            data = json.loads(body.decode("utf-8"))
            message = HttpMessage.from_dict(data)

            if auth_context:
                tool_name, arguments = self._tool_call_parts(message)
                if tool_name:
                    decision = authorize_scoped_mcp_tool_call(auth_context, tool_name, arguments)
                    if not decision.allowed:
                        denied = self._scoped_denial_message(message, decision)
                        self._record_remote_call(auth_context, message, denied, error_code=decision.error_code)
                        response_data = json.dumps(denied.to_dict())
                        self._stats.bytes_sent += len(response_data)
                        self._stats.responses_sent += 1
                        return web.Response(text=response_data, content_type="application/json")
                    rate_limit_decision = self._scoped_rate_limit_decision(auth_context)
                    if not rate_limit_decision.allowed:
                        denied = self._scoped_rate_limit_denial_message(message, rate_limit_decision)
                        self._record_remote_call(
                            auth_context,
                            message,
                            denied,
                            error_code=rate_limit_decision.error_code,
                        )
                        response_data = json.dumps(denied.to_dict())
                        self._stats.bytes_sent += len(response_data)
                        self._stats.responses_sent += 1
                        return web.Response(text=response_data, content_type="application/json")
                    spent_usd = self._scoped_key_spent(auth_context)
                    arguments = constrain_scoped_mcp_budget_arguments(auth_context, tool_name, arguments, spent_usd)
                    budget_decision = authorize_scoped_mcp_budget(auth_context, tool_name, arguments, spent_usd)
                    if not budget_decision.allowed:
                        denied = self._scoped_budget_denial_message(message, budget_decision)
                        self._record_remote_call(auth_context, message, denied, error_code=budget_decision.error_code)
                        response_data = json.dumps(denied.to_dict())
                        self._stats.bytes_sent += len(response_data)
                        self._stats.responses_sent += 1
                        return web.Response(text=response_data, content_type="application/json")
                    if isinstance(message.params, dict):
                        message.params = {**message.params, "arguments": arguments}
                if isinstance(message.params, dict):
                    message.params = {**message.params, "_scoped_key": auth_context.to_dict()}

            if self._handler:
                response = await self._handler(message)
                self._record_remote_call(auth_context, message, response)

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
        except Exception:
            # Log the full exception locally but return a generic
            # message to the caller. The previous ``str(e)`` echoed
            # traceback fragments / internal path names to anyone who
            # could reach the endpoint.
            logger.exception("MCP HTTP POST handler failed")
            self._stats.errors += 1
            return web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32603, "message": "Internal error"}, "id": None},
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

        queue: asyncio.Queue[Any] = asyncio.Queue()
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

                except TimeoutError:
                    # Send keepalive
                    await response.write(b": keepalive\n\n")

        finally:
            self._stats.active_streams -= 1
            # Only remove the entry if it still points at THIS handler's queue.
            # When a reconnect with the same subscriber_id replaces ``queue`` in
            # ``_subscribers``, the old handler exits via its sentinel — but its
            # finally block must NOT pop the new owner. An unconditional pop
            # silently unregisters the replacement and stalls notification
            # delivery until the next reconnect.
            if self._subscribers.get(subscriber_id) is queue:
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

    async def broadcast(self, notification: dict[str, Any]) -> int:
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

    async def send_to(self, subscriber_id: str, notification: dict[str, Any]) -> bool:
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

    def __init__(self, base_url: str, timeout: float = 30.0, auth_token: str | None = None):
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._auth_token = auth_token or os.getenv("MCP_AUTH_TOKEN") or os.getenv("DEEPR_MCP_AUTH_TOKEN") or None
        self._session: aiohttp.ClientSession | None = None
        self._stream_task: asyncio.Task[None] | None = None
        self._notification_handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None

    def _auth_headers(self) -> dict[str, Any]:
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

    async def send(self, message: HttpMessage) -> HttpMessage | None:
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

    def on_notification(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Set handler for incoming notifications."""
        self._notification_handler = handler

    async def subscribe(self, subscriber_id: str | None = None) -> None:
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

        # Cancel any prior subscription task before replacing it.
        # Without this the previous task continued reading from a now-
        # orphaned URL forever, leaking sockets and consuming the SSE
        # response buffer.
        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except (asyncio.CancelledError, Exception):
                pass  # stream task cancel during HTTP MCP reconnect is expected

        url = f"{self._base_url}/stream"
        if subscriber_id:
            # urllib-quote the subscriber id so any ``&`` or ``=`` in
            # caller-supplied ids can't corrupt the URL.
            from urllib.parse import quote as _quote

            url += f"?subscriber_id={_quote(str(subscriber_id), safe='')}"

        # Warn about plaintext-bearer over HTTP — the auth token will be
        # observable in transit. Allowed (silently) for loopback only.
        if self._auth_token and self._base_url.startswith("http://"):
            loopback = any(self._base_url.startswith(p) for p in ("http://127.", "http://localhost", "http://[::1]"))
            if not loopback:
                logger.warning(
                    "MCP HTTP client subscribing with auth token over plaintext HTTP to %s — token will be in cleartext.",
                    self._base_url,
                )

        self._stream_task = asyncio.create_task(self._stream_loop(url))

    async def _stream_loop(self, url: str) -> None:
        """Internal loop for processing SSE stream."""
        try:
            assert self._session is not None  # set in connect()
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
