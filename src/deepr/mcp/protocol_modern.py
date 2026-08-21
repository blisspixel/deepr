"""Protocol-version negotiation for the final MCP 2026-07-28 revision.

Deepr's MCP server is dual-era per the 2026-07-28 versioning specification
(https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning):

- Modern requests carry ``io.modelcontextprotocol/protocolVersion`` and
  ``io.modelcontextprotocol/clientCapabilities`` in ``params._meta`` on every
  request and are served statelessly.
- Legacy clients open with an ``initialize`` handshake and are served under
  the negotiated pre-2026 revision.

This module owns the shared protocol facts: supported versions, reserved
``_meta`` keys, spec error codes, per-request context extraction, and the
modern result envelope (``resultType``, server identity, cache hints).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deepr import __version__ as SERVER_VERSION

MODERN_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSIONS: tuple[str, ...] = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_LEGACY_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (MODERN_PROTOCOL_VERSION, *LEGACY_PROTOCOL_VERSIONS)

META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_LOG_LEVEL = "io.modelcontextprotocol/logLevel"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
META_SUBSCRIPTION_ID = "io.modelcontextprotocol/subscriptionId"

METHOD_NOT_FOUND_CODE = -32601
INVALID_PARAMS_CODE = -32602
HEADER_MISMATCH_CODE = -32020
MISSING_CLIENT_CAPABILITY_CODE = -32021
UNSUPPORTED_PROTOCOL_VERSION_CODE = -32022

DISCOVER_INSTRUCTIONS = (
    "Deepr exposes persistent research experts. Start with the deepr_tool_search "
    "gateway tool to discover the full tool surface (tools/list returns only the "
    "gateway by default; configured host profiles advertise the full policy-filtered "
    "catalog), then deepr_capabilities for the "
    "expert roster and cost posture. All tool results are JSON and include "
    "structuredContent."
)


class JsonRpcProtocolError(Exception):
    """A JSON-RPC error with a spec-mandated code and HTTP status binding.

    Transports map ``http_status`` onto Streamable HTTP responses; the stdio
    transport ignores it and emits only the JSON-RPC error object.
    """

    def __init__(
        self,
        code: int,
        message: str,
        *,
        data: dict[str, Any] | None = None,
        http_status: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
        self.http_status = http_status

    def to_error(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return error


def unsupported_protocol_version_error(requested: Any) -> JsonRpcProtocolError:
    """-32022 with the spec's ``supported``/``requested`` data shape (HTTP 400)."""
    return JsonRpcProtocolError(
        UNSUPPORTED_PROTOCOL_VERSION_CODE,
        "Unsupported protocol version",
        data={"supported": list(SUPPORTED_PROTOCOL_VERSIONS), "requested": requested},
    )


def method_not_found_error(method: str, *, modern: bool) -> JsonRpcProtocolError:
    """-32601; modern Streamable HTTP binds unknown methods to HTTP 404."""
    return JsonRpcProtocolError(
        METHOD_NOT_FOUND_CODE,
        f"Method not found: {method}",
        http_status=404 if modern else 200,
    )


@dataclass(frozen=True)
class ModernRequestContext:
    """Per-request protocol fields extracted from a modern request's ``_meta``."""

    protocol_version: str
    client_capabilities: dict[str, Any]
    client_info: dict[str, Any] | None = None
    log_level: str | None = None


def modern_request_context(params: dict[str, Any] | None) -> ModernRequestContext | None:
    """Return the modern per-request context, or None for a legacy request.

    Raises JsonRpcProtocolError for a modern request Deepr cannot serve: an
    unsupported version (-32022) or a missing required ``clientCapabilities``
    field (-32602). Both bind to HTTP 400 per the spec.
    """
    meta = (params or {}).get("_meta")
    if not isinstance(meta, dict) or META_PROTOCOL_VERSION not in meta:
        return None
    requested = meta.get(META_PROTOCOL_VERSION)
    if requested != MODERN_PROTOCOL_VERSION:
        raise unsupported_protocol_version_error(requested)
    capabilities = meta.get(META_CLIENT_CAPABILITIES)
    if not isinstance(capabilities, dict):
        raise JsonRpcProtocolError(
            INVALID_PARAMS_CODE,
            f"Modern requests must include {META_CLIENT_CAPABILITIES} in _meta",
        )
    client_info = meta.get(META_CLIENT_INFO)
    log_level = meta.get(META_LOG_LEVEL)
    return ModernRequestContext(
        protocol_version=str(requested),
        client_capabilities=capabilities,
        client_info=client_info if isinstance(client_info, dict) else None,
        log_level=log_level if isinstance(log_level, str) else None,
    )


def server_info() -> dict[str, Any]:
    """Self-reported server identity for initialize results and result ``_meta``."""
    return {"name": "deepr-research", "version": SERVER_VERSION}


def server_capabilities() -> dict[str, Any]:
    """Capability map advertised on both eras.

    ``logging`` is intentionally absent: no ``logging/setLevel`` handler or
    ``notifications/message`` emitter exists, so advertising it (as pre-2.41
    releases did) was an over-claim. There is no ``extensions`` entry: Deepr
    does not ship or claim the background Tasks extension.
    """
    return {
        "tools": {"listChanged": False},
        "resources": {"subscribe": True, "listChanged": False},
        "prompts": {"listChanged": False},
    }


def negotiate_legacy_initialize_version(requested: Any) -> str:
    """Legacy handshake negotiation (2025-06-18 lifecycle rules).

    Echo the requested revision when Deepr can serve it; otherwise answer with
    the latest legacy revision Deepr supports and let the client decide.
    ``initialize`` never negotiates the modern stateless revision: modern
    clients use per-request ``_meta`` instead of a handshake.
    """
    if isinstance(requested, str) and requested in LEGACY_PROTOCOL_VERSIONS:
        return requested
    return LATEST_LEGACY_PROTOCOL_VERSION


# (ttl_ms, cache_scope) per cacheable method (CacheableResult, SEP-2549).
# tools/list and prompts/list are process-static; resources/list and
# resources/read are identity-scoped and change as jobs and experts progress,
# so they carry short private TTLs.
_CACHEABLE_METHOD_POLICY: dict[str, tuple[int, str]] = {
    "server/discover": (3_600_000, "public"),
    "tools/list": (3_600_000, "public"),
    "prompts/list": (3_600_000, "public"),
    "resources/list": (30_000, "private"),
    "resources/read": (5_000, "private"),
}


def finalize_modern_result(method: str, result: dict[str, Any]) -> dict[str, Any]:
    """Stamp the 2026-07-28 result envelope onto a handler result.

    Adds ``resultType`` (always ``"complete"``: Deepr never emits MRTR input
    requests), the ``serverInfo`` result ``_meta``, and the required cache
    fields on cacheable methods.
    """
    stamped = dict(result)
    stamped.setdefault("resultType", "complete")
    meta = stamped.get("_meta")
    stamped["_meta"] = {
        **(meta if isinstance(meta, dict) else {}),
        META_SERVER_INFO: server_info(),
    }
    cache_policy = _CACHEABLE_METHOD_POLICY.get(method)
    if cache_policy is not None:
        ttl_ms, cache_scope = cache_policy
        stamped.setdefault("ttlMs", ttl_ms)
        stamped.setdefault("cacheScope", cache_scope)
    return stamped


def discover_result() -> dict[str, Any]:
    """Result body for the mandatory ``server/discover`` RPC (pre-stamp)."""
    return {
        "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
        "capabilities": server_capabilities(),
        "instructions": DISCOVER_INSTRUCTIONS,
    }


__all__ = [
    "DISCOVER_INSTRUCTIONS",
    "HEADER_MISMATCH_CODE",
    "INVALID_PARAMS_CODE",
    "LATEST_LEGACY_PROTOCOL_VERSION",
    "LEGACY_PROTOCOL_VERSIONS",
    "META_CLIENT_CAPABILITIES",
    "META_CLIENT_INFO",
    "META_LOG_LEVEL",
    "META_PROTOCOL_VERSION",
    "META_SERVER_INFO",
    "META_SUBSCRIPTION_ID",
    "METHOD_NOT_FOUND_CODE",
    "MISSING_CLIENT_CAPABILITY_CODE",
    "MODERN_PROTOCOL_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "JsonRpcProtocolError",
    "ModernRequestContext",
    "discover_result",
    "finalize_modern_result",
    "method_not_found_error",
    "modern_request_context",
    "negotiate_legacy_initialize_version",
    "server_capabilities",
    "server_info",
    "unsupported_protocol_version_error",
]
