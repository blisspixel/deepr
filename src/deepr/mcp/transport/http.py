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
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from deepr.mcp.protocol_compat import HttpMessage as HttpMessage
from deepr.mcp.protocol_compat import canonical_legacy_tool_call
from deepr.mcp.request_context import (
    MCPRequestIdentity,
    bind_mcp_request_identity,
    reset_mcp_request_identity,
)
from deepr.mcp.security.scoped_admission import ScopedMCPAdmission, ScopedMCPAdmissionStore
from deepr.mcp.security.scoped_audit import scoped_mcp_response_cost_usd, scoped_mcp_response_error_code
from deepr.mcp.security.scoped_keys import (
    RemoteMCPAuditLog,
    ScopedMCPAuthzDecision,
    ScopedMCPBudgetDecision,
    ScopedMCPKeyContext,
    ScopedMCPKeyStore,
    ScopedMCPRateLimitDecision,
    authorize_scoped_mcp_tool_call,
    constrain_scoped_mcp_expert_arguments,
)
from deepr.utils.security import is_loopback_bind_host

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT_REQUESTS = 32
CONCURRENCY_RETRY_AFTER_SECONDS = 1
_SCOPED_RESOURCE_METHODS = frozenset(
    {
        "resources/list",
        "resources/read",
        "resources/subscribe",
        "resources/unsubscribe",
    }
)


def _is_loopback_host(host: str) -> bool:
    """Return True if host is a loopback address ('localhost', 127.0.0.0/8, ::1)."""
    return is_loopback_bind_host(host)


def _request_peer_is_loopback(request: "web.Request", *, bind_host: str) -> bool:
    """Classify the direct peer without trusting forwarding headers."""
    remote = request.remote
    if not remote:
        return _is_loopback_host(bind_host)
    candidate = str(remote).split("%", 1)[0]
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return candidate.lower() == "localhost"


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


def _max_concurrent_requests_from_env() -> int:
    raw = os.getenv("DEEPR_MCP_HTTP_MAX_CONCURRENCY", "").strip()
    if not raw:
        return DEFAULT_MAX_CONCURRENT_REQUESTS
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid DEEPR_MCP_HTTP_MAX_CONCURRENCY=%r; using %d", raw, DEFAULT_MAX_CONCURRENT_REQUESTS)
        return DEFAULT_MAX_CONCURRENT_REQUESTS
    return max(value, 1)


@dataclass
class HttpTransportStats:
    """Statistics for HTTP transport monitoring."""

    requests_received: int = 0
    responses_sent: int = 0
    notifications_sent: int = 0
    bytes_received: int = 0
    bytes_sent: int = 0
    errors: int = 0
    active_requests: int = 0
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
        max_concurrent_requests: int | None = None,
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
            max_concurrent_requests: Maximum simultaneous HTTP POST requests
                allowed before returning 429. Defaults to
                DEEPR_MCP_HTTP_MAX_CONCURRENCY or 32.
        """
        self._host = host
        self._port = port
        self._path = path
        self._auth_token = auth_token or os.getenv("MCP_AUTH_TOKEN") or os.getenv("DEEPR_MCP_AUTH_TOKEN") or None
        self._allow_unauthenticated_public_bind = allow_unauthenticated_public_bind
        self._max_concurrent_requests = (
            max(int(max_concurrent_requests), 1)
            if max_concurrent_requests is not None
            else _max_concurrent_requests_from_env()
        )
        self._scoped_key_store = scoped_key_store or _scoped_key_store_from_env()
        self._audit_log = (
            audit_log if audit_log is not None else RemoteMCPAuditLog() if self._scoped_key_store else None
        )
        self._admission_store = (
            ScopedMCPAdmissionStore(self._audit_log)
            if self._scoped_key_store is not None and self._audit_log is not None
            else None
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

    def _request_identity(
        self,
        request: "web.Request",
        scoped_context: ScopedMCPKeyContext | None,
    ) -> MCPRequestIdentity:
        """Derive handler authority only from the authenticated transport."""
        peer_is_loopback = _request_peer_is_loopback(request, bind_host=self._host)
        if scoped_context is not None:
            return MCPRequestIdentity.http_scoped_key(
                key_id=scoped_context.key_id,
                expert_allowlist=scoped_context.expert_allowlist,
                peer_is_loopback=peer_is_loopback,
            )
        provided = _extract_bearer(request)
        if self._auth_token and self._shared_token_matches(provided):
            return MCPRequestIdentity.http_shared_token(
                configured_token=self._auth_token,
                peer_is_loopback=peer_is_loopback,
            )
        return MCPRequestIdentity.http_unauthenticated(peer_is_loopback=peer_is_loopback)

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
            return "", {}
        tool_name = str(message.params.get("name") or "")
        arguments = message.params.get("arguments", {})
        return tool_name, dict(arguments) if isinstance(arguments, dict) else {}

    def _canonicalize_legacy_method(self, message: HttpMessage) -> None:
        canonical = canonical_legacy_tool_call(message.method, message.params)
        if canonical is None:
            return
        tool_name, arguments = canonical
        message.method = "tools/call"
        message.params = {"name": tool_name, "arguments": arguments}

    def _scoped_operation_parts(self, message: HttpMessage) -> tuple[str, dict[str, Any], str | None]:
        tool_name, arguments = self._tool_call_parts(message)
        if tool_name:
            return tool_name, arguments, tool_name
        if message.method in _SCOPED_RESOURCE_METHODS:
            raw_params = message.params if isinstance(message.params, dict) else {}
            params = {key: value for key, value in raw_params.items() if key != "_scoped_key"}
            return str(message.method), params, None
        return "", {}, None

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

    def _try_acquire_request_slot(self) -> bool:
        if self._stats.active_requests >= self._max_concurrent_requests:
            return False
        self._stats.active_requests += 1
        return True

    def _release_request_slot(self) -> None:
        self._stats.active_requests = max(self._stats.active_requests - 1, 0)

    def _concurrency_limited_response(self) -> web.Response:
        payload = {
            "jsonrpc": "2.0",
            "error": {
                "code": -32006,
                "message": "MCP HTTP concurrency limit exceeded",
                "data": {
                    "error_code": "MCP_HTTP_CONCURRENCY_LIMIT_EXCEEDED",
                    "limit": self._max_concurrent_requests,
                    "retry_after_seconds": CONCURRENCY_RETRY_AFTER_SECONDS,
                },
            },
            "id": None,
        }
        response_data = json.dumps(payload)
        self._stats.bytes_sent += len(response_data)
        self._stats.responses_sent += 1
        return web.Response(
            text=response_data,
            status=429,
            headers={"Retry-After": str(CONCURRENCY_RETRY_AFTER_SECONDS)},
            content_type="application/json",
        )

    def _message_web_response(self, message: HttpMessage) -> web.Response:
        response_data = json.dumps(message.to_dict())
        self._stats.bytes_sent += len(response_data)
        self._stats.responses_sent += 1
        return web.Response(text=response_data, content_type="application/json")

    def _scoped_authorization_response(
        self,
        context: ScopedMCPKeyContext,
        message: HttpMessage,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> web.Response | None:
        decision = authorize_scoped_mcp_tool_call(context, tool_name, arguments)
        if decision.allowed:
            return None
        denied = self._scoped_denial_message(message, decision)
        self._record_remote_call(context, message, denied, error_code=decision.error_code)
        return self._message_web_response(denied)

    def _scoped_rate_limit_response(
        self,
        context: ScopedMCPKeyContext,
        message: HttpMessage,
        decision: ScopedMCPRateLimitDecision,
    ) -> web.Response | None:
        if decision.allowed:
            return None
        denied = self._scoped_rate_limit_denial_message(message, decision)
        self._record_remote_call(context, message, denied, error_code=decision.error_code)
        return self._message_web_response(denied)

    def _scoped_budget_response(
        self,
        context: ScopedMCPKeyContext,
        message: HttpMessage,
        decision: ScopedMCPBudgetDecision,
    ) -> web.Response | None:
        if decision.allowed:
            return None
        denied = self._scoped_budget_denial_message(message, decision)
        self._record_remote_call(context, message, denied, error_code=decision.error_code)
        return self._message_web_response(denied)

    def _scoped_tool_authorization_response(
        self,
        context: ScopedMCPKeyContext,
        message: HttpMessage,
    ) -> web.Response | None:
        tool_name, arguments = self._tool_call_parts(message)
        if not tool_name:
            return None
        arguments = constrain_scoped_mcp_expert_arguments(context, tool_name, arguments)
        if isinstance(message.params, dict):
            message.params = {**message.params, "arguments": arguments}
        return self._scoped_authorization_response(context, message, tool_name, arguments)

    def _apply_scoped_key_context(
        self,
        context: ScopedMCPKeyContext,
        message: HttpMessage,
    ) -> tuple[ScopedMCPAdmission | None, web.Response | None]:
        denied = self._scoped_tool_authorization_response(context, message)
        if denied is not None:
            return None, denied

        operation, operation_arguments, resolved_tool = self._scoped_operation_parts(message)
        admission = None
        if operation:
            if self._admission_store is None:
                raise RuntimeError("Scoped MCP admission store is unavailable")
            result = self._admission_store.reserve(
                context,
                operation=operation,
                arguments=operation_arguments,
                tool_name=resolved_tool,
            )
            denied = self._scoped_rate_limit_response(context, message, result.rate_decision)
            if denied is not None:
                return None, denied
            if resolved_tool is not None and isinstance(message.params, dict):
                message.params = {**message.params, "arguments": result.arguments}
            if result.budget_decision is not None:
                denied = self._scoped_budget_response(context, message, result.budget_decision)
                if denied is not None:
                    return None, denied
            admission = result.admission
        if isinstance(message.params, dict):
            message.params = {**message.params, "_scoped_key": context.to_dict()}
        return admission, None

    def _append_remote_call(
        self,
        context: ScopedMCPKeyContext,
        message: HttpMessage,
        response: HttpMessage | None,
        *,
        error_code: str,
        cost_usd: float | None,
    ) -> None:
        if not self._audit_log:
            return
        operation, arguments, _tool_name = self._scoped_operation_parts(message)
        if not operation:
            return
        resolved_error = error_code or scoped_mcp_response_error_code(response)
        outcome = "error" if resolved_error or (response and response.error) else "success"
        self._audit_log.record_tool_call(
            context,
            tool=operation,
            arguments=arguments,
            outcome=outcome,
            error_code=resolved_error,
            cost_usd=cost_usd,
        )

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
        operation, arguments, tool_name = self._scoped_operation_parts(message)
        if not operation:
            return
        cost_usd = scoped_mcp_response_cost_usd(tool_name, arguments, response) if tool_name else None

        def _record() -> None:
            self._append_remote_call(
                context,
                message,
                response,
                error_code=error_code,
                cost_usd=cost_usd,
            )

        if self._admission_store is not None:
            self._admission_store.record_audit(context.key_id, _record)
        else:
            _record()

    def _settle_remote_call(
        self,
        context: ScopedMCPKeyContext,
        message: HttpMessage,
        response: HttpMessage | None,
        admission: ScopedMCPAdmission,
        *,
        error_code: str = "",
    ) -> None:
        if self._admission_store is None:
            raise RuntimeError("Scoped MCP admission store is unavailable")
        _operation, arguments, tool_name = self._scoped_operation_parts(message)
        actual_cost = scoped_mcp_response_cost_usd(tool_name, arguments, response) if tool_name else None

        def _record(charge: float | None) -> None:
            self._append_remote_call(
                context,
                message,
                response,
                error_code=error_code,
                cost_usd=charge,
            )

        if not self._admission_store.settle(
            admission,
            actual_cost_usd=actual_cost,
            recorder=_record,
        ):
            raise RuntimeError("Scoped MCP admission reservation is missing")

    async def _dispatch_message(
        self,
        request: web.Request,
        context: ScopedMCPKeyContext | None,
        message: HttpMessage,
        admission: ScopedMCPAdmission | None,
    ) -> HttpMessage | None:
        if self._handler is None:
            if context is not None and admission is not None:
                self._settle_remote_call(
                    context,
                    message,
                    None,
                    admission,
                    error_code="MCP_HANDLER_UNAVAILABLE",
                )
            return None

        identity_token = bind_mcp_request_identity(self._request_identity(request, context))
        try:
            try:
                response = await self._handler(message)
            except BaseException:
                if context is not None and admission is not None:
                    self._settle_remote_call(
                        context,
                        message,
                        None,
                        admission,
                        error_code="MCP_HANDLER_FAILED",
                    )
                raise
        finally:
            reset_mcp_request_identity(identity_token)
        if context is not None and admission is not None:
            self._settle_remote_call(context, message, response, admission)
        else:
            self._record_remote_call(context, message, response)
        return response

    async def _handle_post(self, request: web.Request) -> web.Response:
        """Handle incoming POST requests (JSON-RPC messages)."""
        auth_context, unauthorized = self._authenticate_request(request)
        if unauthorized is not None:
            self._stats.errors += 1
            return unauthorized
        if not self._try_acquire_request_slot():
            self._stats.errors += 1
            return self._concurrency_limited_response()
        try:
            body = await request.read()
            self._stats.bytes_received += len(body)
            self._stats.requests_received += 1

            data = json.loads(body.decode("utf-8"))
            message = HttpMessage.from_dict(data)
            self._canonicalize_legacy_method(message)

            admission = None
            if auth_context:
                admission, scoped_response = self._apply_scoped_key_context(auth_context, message)
                if scoped_response is not None:
                    return scoped_response

            response = await self._dispatch_message(request, auth_context, message, admission)
            if response:
                return self._message_web_response(response)

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
        finally:
            self._release_request_slot()

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
        # old handler keeps draining a queue nobody ever puts to -
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
            # ``_subscribers``, the old handler exits via its sentinel - but its
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
                "active_requests": self._stats.active_requests,
                "max_concurrent_requests": self._max_concurrent_requests,
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

        # Warn about plaintext-bearer over HTTP - the auth token will be
        # observable in transit. Allowed (silently) for loopback only.
        if self._auth_token and self._base_url.startswith("http://"):
            loopback = any(self._base_url.startswith(p) for p in ("http://127.", "http://localhost", "http://[::1]"))
            if not loopback:
                logger.warning(
                    "MCP HTTP client subscribing with auth token over plaintext HTTP to %s - token will be in cleartext.",
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

__all__ = [
    "HttpClient",
    "HttpMessage",
    "HttpTransport",
    "HttpTransportStats",
    "StreamingHttpTransport",
]
