"""Fail-closed policy for outbound MCP HTTP validation clients."""

from __future__ import annotations

from math import isfinite
from typing import Any
from urllib.parse import urlsplit, urlunsplit

MAX_MCP_HTTP_TIMEOUT_SECONDS = 300.0
STRUCTURAL_MCP_HTTP_METHODS = frozenset({"health", "initialize", "ping", "tools/list"})


class MCPHttpDispatchBlockedError(RuntimeError):
    """Raised before POST when a remote MCP method lacks cost authority."""


def validated_mcp_http_timeout(value: Any) -> float:
    """Return a finite bounded HTTP timeout or fail before client creation."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("timeout_seconds must be a finite number")
    timeout = float(value)
    if not isfinite(timeout) or timeout <= 0 or timeout > MAX_MCP_HTTP_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be finite and greater than 0, up to {MAX_MCP_HTTP_TIMEOUT_SECONDS:g}")
    return timeout


def validated_remote_mcp_url(value: Any) -> str:
    """Return a credential-free HTTP origin/path suitable for a report or client."""
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 2048:
        raise ValueError("MCP URL must be a non-empty URL of at most 2048 characters")
    try:
        parsed = urlsplit(value)
        _port = parsed.port
    except ValueError as exc:
        raise ValueError("MCP URL must be a valid HTTP or HTTPS URL") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or parsed.hostname is None:
        raise ValueError("MCP URL must use HTTP or HTTPS and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("MCP URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("MCP URL must not contain a query or fragment")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, path, "", ""))


def require_structural_mcp_http_method(method: Any) -> None:
    """Reject remote work methods until a durable cost authority is supplied."""
    if not isinstance(method, str) or method not in STRUCTURAL_MCP_HTTP_METHODS:
        raise MCPHttpDispatchBlockedError(
            "Outbound MCP HTTP dispatch is limited to structural initialize, tools/list, ping, "
            "and health methods. Cost-capable methods require a private durable dispatch authority."
        )


def finite_nonnegative_number(value: Any) -> float | None:
    """Return a finite non-negative numeric value without coercing strings or booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) and number >= 0 else None


def is_exact_zero_cost(value: Any) -> bool:
    """Return whether a cost field is a finite numeric zero."""
    number = finite_nonnegative_number(value)
    return number == 0.0 if number is not None else False


__all__ = [
    "MAX_MCP_HTTP_TIMEOUT_SECONDS",
    "STRUCTURAL_MCP_HTTP_METHODS",
    "MCPHttpDispatchBlockedError",
    "finite_nonnegative_number",
    "is_exact_zero_cost",
    "require_structural_mcp_http_method",
    "validated_mcp_http_timeout",
    "validated_remote_mcp_url",
]
