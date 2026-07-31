"""Era-aware JSON-RPC method dispatch shared by the stdio and HTTP transports.

Routes each request under the correct protocol era per the dual-era rules in
the 2026-07-28 versioning spec: modern requests (per-request ``_meta``) get
the stateless envelope, mandatory ``server/discover``, and modern error
codes; legacy requests keep the pre-2026 handshake surface unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from deepr.mcp import protocol_modern as pm
from deepr.mcp.protocol_compat import LEGACY_METHOD_MAP
from deepr.mcp.request_context import current_mcp_request_identity

if TYPE_CHECKING:
    from deepr.mcp.server import DeeprMCPServer

MethodHandler = Callable[["DeeprMCPServer", dict[str, Any]], Awaitable[dict[str, Any]]]

# Removed by the 2026-07-28 stateless core: modern requests to these return
# method-not-found. initialize is replaced by per-request _meta plus
# server/discover; resources/subscribe|unsubscribe by subscriptions/listen.
_LEGACY_ONLY_METHODS = frozenset({"initialize", "resources/subscribe", "resources/unsubscribe"})

# subscriptions/listen is opened at the transport layer (it needs a
# long-lived notification stream), so it is not part of this dispatch table.


async def _handle_server_discover(server: DeeprMCPServer, params: dict[str, Any]) -> dict[str, Any]:
    del server, params
    return pm.discover_result()


async def _modern_resources_read(server: DeeprMCPServer, params: dict[str, Any]) -> dict[str, Any]:
    """resources/read under 2026-07-28 semantics.

    A failed read is a JSON-RPC -32602 error (the revision retires the legacy
    -32002 code); the legacy dispatch keeps its embedded-error contents shape
    for pre-2026 clients.
    """
    uri = str(params.get("uri", ""))
    response = server.resource_handler.read_resource(uri, identity=current_mcp_request_identity())
    if not response.success:
        raise pm.JsonRpcProtocolError(
            pm.INVALID_PARAMS_CODE,
            f"Resource not found: {uri}",
            data={"uri": uri},
        )
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps(response.data, default=str),
            }
        ]
    }


def method_handlers() -> dict[str, MethodHandler]:
    """Canonical JSON-RPC method table (shared by stdio and HTTP)."""
    # Imported lazily: deepr.mcp.server imports this module for registration.
    from deepr.mcp import server as mcp_server

    return {
        "initialize": mcp_server._handle_initialize,
        "server/discover": _handle_server_discover,
        "tools/list": mcp_server._handle_tools_list,
        "tools/call": mcp_server._handle_tools_call,
        "resources/list": mcp_server._handle_resources_list,
        "resources/read": mcp_server._handle_resources_read,
        "resources/subscribe": mcp_server._handle_resources_subscribe,
        "resources/unsubscribe": mcp_server._handle_resources_unsubscribe,
        "prompts/list": mcp_server._handle_prompts_list,
        "prompts/get": mcp_server._handle_prompts_get,
    }


def registered_method_names() -> list[str]:
    """Every method name a transport should register, including legacy aliases."""
    return [*method_handlers(), *LEGACY_METHOD_MAP]


def _legacy_alias_handler(tool_name: str) -> MethodHandler:
    async def _handler(server: DeeprMCPServer, params: dict[str, Any]) -> dict[str, Any]:
        from deepr.mcp import server as mcp_server

        arguments = {key: value for key, value in params.items() if key != "_meta"}
        return await mcp_server._handle_tools_call(server, {"name": tool_name, "arguments": arguments})

    return _handler


async def dispatch_protocol_method(
    server: DeeprMCPServer,
    method: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch one JSON-RPC request under the correct protocol era.

    Raises JsonRpcProtocolError for spec-mandated failures (unsupported
    version, missing required ``_meta`` fields, unknown method, modern
    resource-read failure).
    """
    context = pm.modern_request_context(params)
    modern = context is not None

    handler: MethodHandler | None
    if modern and method in _LEGACY_ONLY_METHODS:
        handler = None
    elif modern and method == "resources/read":
        handler = _modern_resources_read
    else:
        handler = method_handlers().get(method)
        if handler is None:
            legacy_tool = LEGACY_METHOD_MAP.get(method)
            handler = _legacy_alias_handler(legacy_tool) if legacy_tool is not None else None
    if handler is None:
        raise pm.method_not_found_error(method, modern=modern)

    result = await handler(server, params)
    if modern:
        return pm.finalize_modern_result(method, result)
    return result


__all__ = [
    "MethodHandler",
    "dispatch_protocol_method",
    "method_handlers",
    "registered_method_names",
]
