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

from aiohttp import web

from deepr.mcp.protocol_compat import HttpMessage as HttpMessage
from deepr.mcp.protocol_compat import canonical_legacy_tool_call
from deepr.mcp.protocol_modern import JsonRpcProtocolError
from deepr.mcp.request_context import (
    MCPRequestIdentity,
    bind_mcp_request_identity,
    reset_mcp_request_identity,
)
from deepr.mcp.security.scoped_admission import ScopedMCPAdmission, ScopedMCPAdmissionStore
from deepr.mcp.security.scoped_audit import scoped_mcp_response_cost_usd, scoped_mcp_response_error_code
from deepr.mcp.security.scoped_keys import (
    RemoteMCPAuditLog,
    ScopedMCPBudgetDecision,
    ScopedMCPKeyContext,
    ScopedMCPKeyStore,
    ScopedMCPRateLimitDecision,
    authorize_scoped_mcp_tool_call,
    constrain_scoped_mcp_expert_arguments,
)
from deepr.mcp.subscriptions_listen import StreamCloser, StreamOpener
from deepr.mcp.transport import http_scoped, http_sse
from deepr.mcp.transport.http_validation import (
    allowed_origins_from_env,
    origin_is_allowed,
    validate_streamable_http_request,
)
from deepr.utils.security import is_loopback_bind_host

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT_REQUESTS = 32
CONCURRENCY_RETRY_AFTER_SECONDS = 1
# Pending SSE payloads per listen stream. A peer that stops reading hits
# backpressure here instead of growing the queue until the process dies.
LISTEN_QUEUE_MAXSIZE = 1024


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
        self._listen_opener: StreamOpener | None = None
        self._allowed_origins = allowed_origins_from_env()
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._stats = HttpTransportStats()
        self._subscribers: dict[str, asyncio.Queue[Any]] = {}
        self._listen_queues: set[asyncio.Queue[Any]] = set()
        self._listen_slots = 0
        self._running = False

    def on_message(self, handler: Callable[[HttpMessage], Awaitable[HttpMessage | None]]) -> None:
        """Set the message handler for incoming requests."""
        self._handler = handler

    def on_listen(self, opener: StreamOpener) -> None:
        """Set the opener for modern ``subscriptions/listen`` streams."""
        self._listen_opener = opener

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

        # Signal active subscriptions/listen streams so they end gracefully
        # (spec: server-initiated end sends the empty listen response first).
        for listen_queue in list(self._listen_queues):
            await listen_queue.put(None)

        if self._runner:
            await self._runner.cleanup()

    def _unauthorized_response(self) -> web.Response:
        return web.json_response(
            {"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized"}, "id": None},
            status=401,
        )

    def _origin_rejection(self, request: "web.Request") -> web.Response | None:
        """DNS-rebinding defense (spec MUST): 403 for a present-but-invalid Origin."""
        origin = request.headers.get("Origin")
        if origin_is_allowed(origin, extra_allowed=self._allowed_origins):
            return None
        self._stats.errors += 1
        return web.json_response(
            {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Origin not allowed"}, "id": None},
            status=403,
        )

    def _protocol_error_response(self, message_id: Any, exc: JsonRpcProtocolError) -> web.Response:
        """Map a JsonRpcProtocolError onto its spec-mandated HTTP status."""
        payload = {"jsonrpc": "2.0", "error": exc.to_error(), "id": message_id}
        response_data = json.dumps(payload)
        self._stats.bytes_sent += len(response_data)
        self._stats.responses_sent += 1
        return web.Response(text=response_data, status=exc.http_status, content_type="application/json")

    def _shared_token_matches(self, provided: str | None) -> bool:
        token = self._auth_token
        if not token or not provided:
            return False
        try:
            return hmac.compare_digest(provided, token)
        except (TypeError, ValueError):
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

    def _canonicalize_legacy_method(self, message: HttpMessage) -> None:
        canonical = canonical_legacy_tool_call(message.method, message.params)
        if canonical is None:
            return
        tool_name, arguments = canonical
        # _meta is protocol metadata, not a tool argument: keep it on the
        # canonical params so modern requests stay modern through dispatch,
        # and out of arguments so **kwargs tool handlers don't TypeError.
        meta = arguments.pop("_meta", None)
        message.method = "tools/call"
        params: dict[str, Any] = {"name": tool_name, "arguments": arguments}
        if isinstance(meta, dict):
            params["_meta"] = meta
        message.params = params

    def _try_acquire_request_slot(self) -> bool:
        if self._stats.active_requests >= self._max_concurrent_requests:
            return False
        self._stats.active_requests += 1
        return True

    def _release_request_slot(self) -> None:
        self._stats.active_requests = max(self._stats.active_requests - 1, 0)

    def _try_acquire_listen_slot(self) -> bool:
        """Reserve a listen-stream slot atomically (no await between check
        and increment, so concurrent opens cannot exceed the cap)."""
        if self._listen_slots >= self._max_concurrent_requests:
            return False
        self._listen_slots += 1
        return True

    def _release_listen_slot(self) -> None:
        self._listen_slots = max(self._listen_slots - 1, 0)

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
        denied = http_scoped.authz_denial_message(message, decision)
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
        denied = http_scoped.rate_limit_denial_message(message, decision)
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
        denied = http_scoped.budget_denial_message(message, decision)
        self._record_remote_call(context, message, denied, error_code=decision.error_code)
        return self._message_web_response(denied)

    def _scoped_tool_authorization_response(
        self,
        context: ScopedMCPKeyContext,
        message: HttpMessage,
    ) -> web.Response | None:
        tool_name, arguments = http_scoped.tool_call_parts(message)
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

        operation, operation_arguments, resolved_tool = http_scoped.scoped_operation_parts(message)
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
        operation, arguments, _tool_name = http_scoped.scoped_operation_parts(message)
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
        operation, arguments, tool_name = http_scoped.scoped_operation_parts(message)
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
        _operation, arguments, tool_name = http_scoped.scoped_operation_parts(message)
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

    async def _handle_post(self, request: web.Request) -> web.StreamResponse:
        """Handle incoming POST requests (JSON-RPC messages)."""
        origin_rejection = self._origin_rejection(request)
        if origin_rejection is not None:
            return origin_rejection
        auth_context, unauthorized = self._authenticate_request(request)
        if unauthorized is not None:
            self._stats.errors += 1
            return unauthorized
        if not self._try_acquire_request_slot():
            self._stats.errors += 1
            return self._concurrency_limited_response()
        message_id: Any = None
        slot_transferred = False
        try:
            body = await request.read()
            self._stats.bytes_received += len(body)
            self._stats.requests_received += 1

            data = json.loads(body.decode("utf-8"))
            message = HttpMessage.from_dict(data)
            message_id = message.id

            # 2026-07-28 transport validation: Origin was checked above;
            # metadata headers must match the body on modern requests. The
            # legacy Mcp-Session-Id / Last-Event-ID headers are ignored per
            # spec (protocol sessions and SSE resumability are gone).
            validation = validate_streamable_http_request(request.headers, message)

            if validation.modern and message.method == "subscriptions/listen":
                # The POST slot pool exists for request/response work; a
                # long-lived stream would otherwise pin one slot per stream
                # and N idle streams would starve every other request. Hand
                # the slot back now; streams are capped separately.
                self._release_request_slot()
                slot_transferred = True
                return await self._handle_subscriptions_listen(request, auth_context, message)

            return await self._handle_rpc_message(request, auth_context, message)

        except JsonRpcProtocolError as exc:
            self._stats.errors += 1
            return self._protocol_error_response(message_id, exc)
        except json.JSONDecodeError:
            self._stats.errors += 1
            return web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
                status=400,
            )
        except web.HTTPException:
            # aiohttp's own statuses (e.g. 413 for a body over client_max_size)
            # must not be flattened into a 500.
            self._stats.errors += 1
            raise
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
            if not slot_transferred:
                self._release_request_slot()

    async def _handle_rpc_message(
        self,
        request: web.Request,
        auth_context: ScopedMCPKeyContext | None,
        message: HttpMessage,
    ) -> web.StreamResponse:
        """Dispatch one ordinary (non-streaming) JSON-RPC message."""
        self._canonicalize_legacy_method(message)

        admission = None
        if auth_context:
            admission, scoped_response = self._apply_scoped_key_context(auth_context, message)
            if scoped_response is not None:
                return scoped_response

        response = await self._dispatch_message(request, auth_context, message, admission)
        if response:
            return self._message_web_response(response)

        # Accepted notification (202 per Streamable HTTP spec)
        return web.Response(status=202)

    async def _handle_subscriptions_listen(
        self,
        request: web.Request,
        auth_context: ScopedMCPKeyContext | None,
        message: HttpMessage,
    ) -> web.StreamResponse:
        """Serve a modern ``subscriptions/listen`` request as a long-lived SSE stream.

        The session (filter validation, acknowledgment, resource
        subscriptions) is opened before the SSE response starts so a malformed
        request still gets a proper JSON error status. Closing the stream is
        the cancellation signal; on server shutdown the graceful empty
        response is emitted as the final event.
        """
        if message.id is None:
            # Notification-shaped listen: nothing to stream to, but JSON-RPC
            # forbids answering a notification with an error.
            return web.Response(status=202)
        if self._listen_opener is None:
            raise JsonRpcProtocolError(-32601, "subscriptions/listen is not available", http_status=404)
        # Listen streams are bounded separately from request slots; the count
        # is reserved here (not derived from _listen_queues membership) so the
        # cap cannot be exceeded by concurrent opens racing across an await.
        if not self._try_acquire_listen_slot():
            raise JsonRpcProtocolError(
                -32006,
                "MCP HTTP listen-stream limit exceeded",
                data={"limit": self._max_concurrent_requests},
                http_status=429,
            )

        # Bounded queue: an SSE peer that stops reading applies backpressure
        # instead of growing the queue without limit.
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=LISTEN_QUEUE_MAXSIZE)
        try:
            opened = await self._open_listen_session(
                request, auth_context, message, queue, self._listen_opener, message.id
            )
        except BaseException:
            self._release_listen_slot()
            raise
        if isinstance(opened, web.Response):  # scoped-key denial
            self._release_listen_slot()
            return opened
        return await self._stream_listen_events(request, queue, opened)

    async def _open_listen_session(
        self,
        request: web.Request,
        auth_context: ScopedMCPKeyContext | None,
        message: HttpMessage,
        queue: asyncio.Queue[dict[str, Any] | None],
        opener: StreamOpener,
        request_id: str | int,
    ) -> StreamCloser | web.Response:
        """Authorize and open one listen session, or return a scoped denial.

        Scoped keys get the same rate-limit and audit treatment on listen as
        on the legacy subscribe RPCs. The reservation settles immediately:
        opening a stream costs `$0`, and a stream must not hold an admission
        for its lifetime.
        """
        admission = None
        if auth_context:
            admission, scoped_response = self._apply_scoped_key_context(auth_context, message)
            if scoped_response is not None:
                return scoped_response

        async def _send(payload: dict[str, Any]) -> None:
            await queue.put(payload)

        identity_token = bind_mcp_request_identity(self._request_identity(request, auth_context))
        try:
            return await opener(message.params or {}, request_id, _send)
        finally:
            reset_mcp_request_identity(identity_token)
            if auth_context is not None and admission is not None:
                self._settle_remote_call(auth_context, message, None, admission)

    async def _stream_listen_events(
        self,
        request: web.Request,
        queue: asyncio.Queue[dict[str, Any] | None],
        closer: StreamCloser,
    ) -> web.StreamResponse:
        """Run the SSE response stream for an open listen session."""
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

        def _count_event(size: int) -> None:
            self._stats.notifications_sent += 1
            self._stats.bytes_sent += size

        # A None sentinel is enqueued only by stop(): server-initiated end.
        # Client cancellation is the transport-level disconnect instead.
        self._listen_queues.add(queue)
        graceful = False
        try:
            await response.prepare(request)
            self._stats.active_streams += 1
            try:
                graceful = await http_sse.pump_events(
                    response,
                    queue,
                    is_running=lambda: self._running,
                    on_event=_count_event,
                )
            finally:
                self._stats.active_streams -= 1
        finally:
            self._listen_queues.discard(queue)
            self._release_listen_slot()
            await closer(graceful)
            if graceful:
                # closer(graceful=True) enqueued the final JSON-RPC response;
                # drain it onto the stream before closing.
                await http_sse.drain_remaining(response, queue)
        return response

    async def _handle_stream(self, request: web.Request) -> web.StreamResponse:
        """Serve the legacy (pre-2026) SSE notification endpoint.

        Modern clients use ``subscriptions/listen`` instead; this route stays
        for handshake-era clients that opened a standalone stream.
        """
        origin_rejection = self._origin_rejection(request)
        if origin_rejection is not None:
            return origin_rejection
        unauthorized = self._check_auth(request)
        if unauthorized is not None:
            self._stats.errors += 1
            return unauthorized
        # Namespace the client-supplied id by the authenticated caller so one
        # client cannot evict another client's stream by guessing its id.
        identity = self._request_identity(request, self._authenticate_request(request)[0])
        requested_id = request.query.get("subscriber_id", str(id(request)))
        subscriber_id = f"{identity.owner_id or identity.authentication}:{requested_id}"
        return await http_sse.serve_legacy_stream(
            request,
            subscriber_id=subscriber_id,
            subscribers=self._subscribers,
            stats=self._stats,
            is_running=lambda: self._running,
        )

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        origin_rejection = self._origin_rejection(request)
        if origin_rejection is not None:
            return origin_rejection
        # Saturation counters are operational detail: require the same
        # credential as the tool surface whenever one is configured.
        unauthorized = self._check_auth(request)
        if unauthorized is not None:
            self._stats.errors += 1
            return unauthorized
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


# Outbound client lives in its own module; re-exported here for compatibility.
from deepr.mcp.transport.http_client import HttpClient as HttpClient

# Convenience alias
HttpTransport = StreamingHttpTransport


__all__ = [
    "HttpClient",
    "HttpMessage",
    "HttpTransport",
    "HttpTransportStats",
    "StreamingHttpTransport",
]
