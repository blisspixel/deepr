"""Authenticated request identity for protocol-neutral MCP handlers.

Transport sessions and caller-supplied parameters are not credentials. The
HTTP transport binds this context only after authenticating the current
request, and ``ContextVar`` keeps concurrent requests isolated. Direct and
stdio calls intentionally receive a stable local-process authority instead.
"""

from __future__ import annotations

import hashlib
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Literal

MCPTransportName = Literal["stdio", "http"]
MCPAuthenticationMethod = Literal["stdio", "scoped_key", "shared_token", "none"]


def _identity_hash(namespace: str, value: str) -> str:
    material = f"deepr-mcp-owner-v1\0{namespace}\0{value}".encode()
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True)
class MCPRequestIdentity:
    """Server-derived authority for one MCP request."""

    transport: MCPTransportName
    authentication: MCPAuthenticationMethod
    owner_id: str
    authenticated: bool
    peer_is_loopback: bool
    scoped_key_id: str | None = None
    expert_allowlist: tuple[str, ...] = ()

    @classmethod
    def local_stdio(cls) -> MCPRequestIdentity:
        return cls(
            transport="stdio",
            authentication="stdio",
            owner_id="mcp:stdio:local-v1",
            authenticated=True,
            peer_is_loopback=True,
        )

    @classmethod
    def http_scoped_key(
        cls,
        *,
        key_id: str,
        expert_allowlist: tuple[str, ...],
        peer_is_loopback: bool,
    ) -> MCPRequestIdentity:
        return cls(
            transport="http",
            authentication="scoped_key",
            owner_id=f"mcp:key:{_identity_hash('scoped-key', key_id)}",
            authenticated=True,
            peer_is_loopback=peer_is_loopback,
            scoped_key_id=key_id,
            expert_allowlist=tuple(expert_allowlist),
        )

    @classmethod
    def http_shared_token(cls, *, configured_token: str, peer_is_loopback: bool) -> MCPRequestIdentity:
        return cls(
            transport="http",
            authentication="shared_token",
            owner_id=f"mcp:token:{_identity_hash('shared-token', configured_token)}",
            authenticated=True,
            peer_is_loopback=peer_is_loopback,
        )

    @classmethod
    def http_unauthenticated(cls, *, peer_is_loopback: bool) -> MCPRequestIdentity:
        return cls(
            transport="http",
            authentication="none",
            owner_id="mcp:http:unauthenticated",
            authenticated=False,
            peer_is_loopback=peer_is_loopback,
        )


_CURRENT_IDENTITY: ContextVar[MCPRequestIdentity | None] = ContextVar(
    "deepr_mcp_request_identity",
    default=None,
)


def bind_mcp_request_identity(identity: MCPRequestIdentity) -> Token[MCPRequestIdentity | None]:
    """Bind an authenticated transport identity for the current async context."""
    return _CURRENT_IDENTITY.set(identity)


def reset_mcp_request_identity(token: Token[MCPRequestIdentity | None]) -> None:
    """Restore the prior request identity after dispatch."""
    _CURRENT_IDENTITY.reset(token)


def current_mcp_request_identity() -> MCPRequestIdentity | None:
    """Return the transport-bound identity, or ``None`` for direct/stdio calls."""
    return _CURRENT_IDENTITY.get()
