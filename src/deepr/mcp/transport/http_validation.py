"""Streamable HTTP request validation for the 2026-07-28 revision.

Implements the transport's server-side validation rules
(https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http):

- ``Origin`` validation on every incoming connection (DNS-rebinding defense).
- Modern request metadata headers: ``MCP-Protocol-Version`` must match the
  body ``_meta``, ``Mcp-Method`` must match the body method, and ``Mcp-Name``
  must match ``params.name``/``params.uri`` on the three named methods, with
  Base64 sentinel decoding before comparison. Mismatches are HTTP 400 with
  JSON-RPC ``HeaderMismatch`` (-32020).
- Legacy requests (no modern body ``_meta``) stay tolerant: pre-2025-06-18
  clients never sent these headers, and 2025-06-18 clients send only
  ``MCP-Protocol-Version`` with a legacy value.

Deepr publishes no ``x-mcp-header`` tool-parameter annotations, so no
``Mcp-Param-*`` headers are recognized or expected.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from deepr.mcp.protocol_compat import HttpMessage
from deepr.mcp.protocol_modern import (
    HEADER_MISMATCH_CODE,
    LEGACY_PROTOCOL_VERSIONS,
    META_PROTOCOL_VERSION,
    MODERN_PROTOCOL_VERSION,
    JsonRpcProtocolError,
    unsupported_protocol_version_error,
)

PROTOCOL_VERSION_HEADER = "MCP-Protocol-Version"
METHOD_HEADER = "Mcp-Method"
NAME_HEADER = "Mcp-Name"

_SENTINEL_PREFIX = "=?base64?"
_SENTINEL_SUFFIX = "?="

# Methods whose Mcp-Name header mirrors a body field, per the spec table.
_NAME_HEADER_SOURCES: dict[str, str] = {
    "tools/call": "name",
    "resources/read": "uri",
    "prompts/get": "name",
}

ALLOWED_ORIGINS_ENV = "DEEPR_MCP_HTTP_ALLOWED_ORIGINS"


def _header_mismatch(message: str) -> JsonRpcProtocolError:
    return JsonRpcProtocolError(HEADER_MISMATCH_CODE, message)


def decode_header_value(value: str) -> str:
    """Decode the spec's Base64 sentinel encoding, if present.

    ``=?base64?{payload}?=`` carries UTF-8 values that are not header-safe;
    servers must decode before comparing against the body.
    """
    if not (value.startswith(_SENTINEL_PREFIX) and value.endswith(_SENTINEL_SUFFIX)):
        return value
    encoded = value[len(_SENTINEL_PREFIX) : -len(_SENTINEL_SUFFIX)]
    try:
        return base64.b64decode(encoded.encode("ascii"), validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeError) as exc:
        raise _header_mismatch(f"Malformed Base64 sentinel value in header: {encoded!r}") from exc


@dataclass(frozen=True)
class HttpRequestValidation:
    """Outcome of transport-level validation for one POST body."""

    modern: bool
    protocol_version: str | None


def _body_protocol_version(message: HttpMessage) -> object | None:
    params = message.params if isinstance(message.params, dict) else {}
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return None
    return meta.get(META_PROTOCOL_VERSION) if META_PROTOCOL_VERSION in meta else None


def _validate_legacy_request(header_version: str | None) -> HttpRequestValidation:
    """Classify a request whose body carries no modern ``_meta`` version."""
    if header_version is None or header_version in LEGACY_PROTOCOL_VERSIONS:
        # Pre-2025-06-18 clients sent no header at all; the spec lets the
        # server treat those requests as 2025-03-26.
        return HttpRequestValidation(modern=False, protocol_version=header_version)
    if header_version == MODERN_PROTOCOL_VERSION:
        raise _header_mismatch(
            f"{PROTOCOL_VERSION_HEADER} header declares {MODERN_PROTOCOL_VERSION} "
            f"but the request body carries no {META_PROTOCOL_VERSION} _meta field"
        )
    raise unsupported_protocol_version_error(header_version)


def _validate_name_header(headers: Mapping[str, str], message: HttpMessage) -> None:
    """Check ``Mcp-Name`` against the body for the methods that require it."""
    name_source = _NAME_HEADER_SOURCES.get(message.method or "")
    if name_source is None:
        return
    params = message.params if isinstance(message.params, dict) else {}
    body_name = params.get(name_source)
    name_header = headers.get(NAME_HEADER)
    if name_header is None:
        raise _header_mismatch(f"Missing required {NAME_HEADER} header for {message.method}")
    if decode_header_value(name_header) != body_name:
        raise _header_mismatch(f"{NAME_HEADER} header value does not match body {name_source!r} value")


def _validate_modern_headers(
    headers: Mapping[str, str],
    message: HttpMessage,
    body_version: object,
) -> None:
    """Check the required metadata headers of a modern request against its body."""
    header_version = headers.get(PROTOCOL_VERSION_HEADER)
    if header_version is None:
        raise _header_mismatch(f"Missing required {PROTOCOL_VERSION_HEADER} header")
    if header_version != body_version:
        raise _header_mismatch(
            f"{PROTOCOL_VERSION_HEADER} header value {header_version!r} does not match body value {body_version!r}"
        )

    method_header = headers.get(METHOD_HEADER)
    if method_header is None:
        raise _header_mismatch(f"Missing required {METHOD_HEADER} header")
    if method_header != message.method:
        raise _header_mismatch(
            f"{METHOD_HEADER} header value {method_header!r} does not match body method {message.method!r}"
        )

    _validate_name_header(headers, message)


def validate_streamable_http_request(
    headers: Mapping[str, str],
    message: HttpMessage,
) -> HttpRequestValidation:
    """Validate one POST's metadata headers against its JSON-RPC body.

    Raises JsonRpcProtocolError (HeaderMismatch -32020 or
    UnsupportedProtocolVersion -32022, both HTTP 400) per the spec's server
    validation rules. Header requirements for notification POSTs are not
    defined by the revision, so notifications skip header enforcement.
    """
    body_version = _body_protocol_version(message)
    if body_version is None:
        return _validate_legacy_request(headers.get(PROTOCOL_VERSION_HEADER))

    if body_version != MODERN_PROTOCOL_VERSION:
        # A body _meta version Deepr does not serve statelessly is rejected at
        # the transport (400 + -32022) regardless of downstream handlers.
        raise unsupported_protocol_version_error(body_version)

    if message.is_request():
        _validate_modern_headers(headers, message, body_version)
    return HttpRequestValidation(modern=True, protocol_version=str(body_version))


def allowed_origins_from_env() -> frozenset[str]:
    raw = os.getenv(ALLOWED_ORIGINS_ENV, "")
    return frozenset(origin.strip() for origin in raw.split(",") if origin.strip())


def origin_is_allowed(origin: str | None, *, extra_allowed: frozenset[str] = frozenset()) -> bool:
    """DNS-rebinding defense: accept absent Origin (non-browser clients),
    loopback origins, and explicitly allowlisted origins; reject the rest.
    """
    if origin is None:
        return True
    if origin in extra_allowed:
        return True
    if "\\" in origin or "@" in origin:
        # urlsplit does not treat "\" as a delimiter the way browsers do, and
        # a real Origin never carries userinfo; reject rather than parse.
        return False
    parsed = urlsplit(origin)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


__all__ = [
    "ALLOWED_ORIGINS_ENV",
    "METHOD_HEADER",
    "NAME_HEADER",
    "PROTOCOL_VERSION_HEADER",
    "HttpRequestValidation",
    "allowed_origins_from_env",
    "decode_header_value",
    "origin_is_allowed",
    "validate_streamable_http_request",
]
