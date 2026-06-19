"""Streamable HTTP serve entrypoint for the Deepr MCP server."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from deepr.mcp import server as mcp_server
from deepr.mcp.transport.http import HttpMessage, StreamingHttpTransport

logger = logging.getLogger("deepr.mcp")


async def _dispatch_mcp_method(
    server: mcp_server.DeeprMCPServer,
    method: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    if method == "initialize":
        return await mcp_server._handle_initialize(server, params)
    if method == "tools/list":
        return await mcp_server._handle_tools_list(server, params)
    if method == "tools/call":
        return await mcp_server._handle_tools_call(server, params)
    if method == "resources/list":
        return await mcp_server._handle_resources_list(server, params)
    if method == "resources/read":
        return await mcp_server._handle_resources_read(server, params)
    if method == "resources/subscribe":
        return await mcp_server._handle_resources_subscribe(server, params)
    if method == "resources/unsubscribe":
        return await mcp_server._handle_resources_unsubscribe(server, params)
    if method == "prompts/list":
        return await mcp_server._handle_prompts_list(server, params)
    if method == "prompts/get":
        return await mcp_server._handle_prompts_get(server, params)
    legacy_tool = mcp_server._LEGACY_METHOD_MAP.get(method)
    if legacy_tool:
        return await mcp_server._handle_tools_call(server, {"name": legacy_tool, "arguments": params})
    raise KeyError(method)


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
            result = await _dispatch_mcp_method(server, message.method, params)
        except KeyError:
            if message.id is None:
                return None
            return HttpMessage(
                id=message.id,
                error={"code": -32601, "message": f"Method not found: {message.method}"},
            )
        except Exception as exc:
            logger.exception("MCP HTTP method %s failed", message.method)
            if message.id is None:
                return None
            return HttpMessage(
                id=message.id,
                error={"code": -32603, "message": "Internal error", "data": {"error": str(exc)}},
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
    )
    transport.on_message(_make_http_message_handler(deepr_server))

    await transport.start()
    server_version = str(getattr(mcp_server, "SERVER_VERSION", "unknown"))
    logger.info("Deepr MCP Server v%s started (HTTP transport at %s)", server_version, transport.url)
    logger.info("Registered %d tools, gateway discovery enabled", deepr_server.registry.count())

    try:
        await (stop_event.wait() if stop_event is not None else asyncio.Event().wait())
    finally:
        await transport.stop()
