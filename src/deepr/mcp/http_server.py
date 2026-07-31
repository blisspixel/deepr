"""Streamable HTTP serve entrypoint for the Deepr MCP server."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from deepr.mcp import server as mcp_server
from deepr.mcp.protocol_dispatch import dispatch_protocol_method
from deepr.mcp.protocol_modern import METHOD_NOT_FOUND_CODE, JsonRpcProtocolError
from deepr.mcp.request_context import current_mcp_request_identity
from deepr.mcp.subscriptions_listen import make_listen_opener
from deepr.mcp.transport.http import HttpMessage, StreamingHttpTransport

logger = logging.getLogger("deepr.mcp")


def _make_http_message_handler(
    server: mcp_server.DeeprMCPServer,
) -> Callable[[HttpMessage], Awaitable[HttpMessage | None]]:
    async def _handle(message: HttpMessage) -> HttpMessage | None:
        if message.method is None:
            return None
        if message.id is not None and message.params is not None and not isinstance(message.params, dict):
            return HttpMessage(
                id=message.id,
                error={"code": -32600, "message": "Invalid request params"},
            )
        params = message.params or {}
        try:
            result = await dispatch_protocol_method(server, message.method, params)
        except JsonRpcProtocolError as exc:
            if message.id is None and exc.code == METHOD_NOT_FOUND_CODE:
                # Unknown notifications (e.g. notifications/initialized from
                # every legacy handshake) are accepted and ignored: JSON-RPC
                # forbids responding to a notification, and the transport
                # answers 202 for None.
                return None
            if exc.http_status != 200 or message.id is None:
                # Propagate to the transport, which binds the spec-mandated
                # HTTP status (400 for version/header errors, 404 for unknown
                # modern methods) that an in-band error response would lose.
                raise
            # Legacy-era errors keep the transport-neutral 200 + error shape.
            return HttpMessage(id=message.id, error=exc.to_error())
        except Exception:
            logger.exception("MCP HTTP method %s failed", message.method)
            if message.id is None:
                return None
            return HttpMessage(
                id=message.id,
                error={"code": -32603, "message": "Internal error"},
            )
        if message.id is None:
            return None
        return HttpMessage(id=message.id, result=result)

    return _handle


async def run_http_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    path: str = "/mcp",
    auth_token: str | None = None,
    keys_path: str | None = None,
    allow_unauthenticated_public_bind: bool = False,
    max_concurrent_requests: int | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run MCP server using Streamable HTTP transport."""
    mcp_server._server_start_time = time.time()

    scoped_key_store = None
    if keys_path:
        from deepr.mcp.security.scoped_keys import ScopedMCPKeyStore

        scoped_key_store = ScopedMCPKeyStore(Path(keys_path))

    deepr_server = mcp_server.DeeprMCPServer()
    transport = StreamingHttpTransport(
        host=host,
        port=port,
        path=path,
        auth_token=auth_token,
        allow_unauthenticated_public_bind=allow_unauthenticated_public_bind,
        scoped_key_store=scoped_key_store,
        max_concurrent_requests=max_concurrent_requests,
    )
    transport.on_message(_make_http_message_handler(deepr_server))
    # Modern subscriptions/listen streams: identity was bound by the transport
    # for the opening request, so the provider reads the request-scoped value.
    transport.on_listen(
        make_listen_opener(
            deepr_server.resource_handler,
            identity_provider=current_mcp_request_identity,
        )
    )

    await transport.start()
    server_version = str(getattr(mcp_server, "SERVER_VERSION", "unknown"))
    logger.info("Deepr MCP Server v%s started (HTTP transport at %s)", server_version, transport.url)
    logger.info("Registered %d tools, gateway discovery enabled", deepr_server.registry.count())

    try:
        await (stop_event.wait() if stop_event is not None else asyncio.Event().wait())
    finally:
        await transport.stop()
