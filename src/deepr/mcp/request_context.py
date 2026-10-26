"""Authenticated request identity for protocol-neutral MCP handlers.

Transport sessions and caller-supplied parameters are not credentials. The
HTTP transport binds this context only after authenticating the current
request, and ``ContextVar`` keeps concurrent requests isolated. Direct and
stdio calls intentionally receive a stable local-process authority instead.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from deepr.experts.preparation_contracts import CallerScope

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


@contextmanager
def trusted_stdio_request() -> Iterator[None]:
    """Bind real stdio transport authority for exactly one dispatch."""
    token = bind_mcp_request_identity(MCPRequestIdentity.local_stdio())
    try:
        yield
    finally:
        reset_mcp_request_identity(token)


def current_mcp_request_identity() -> MCPRequestIdentity | None:
    """Return the transport-bound identity, or ``None`` for direct/stdio calls."""
    return _CURRENT_IDENTITY.get()


def current_scoped_mcp_owner_id() -> str | None:
    """Return the server-derived owner only for a scoped-key request."""
    identity = current_mcp_request_identity()
    if identity is None or identity.authentication != "scoped_key":
        return None
    return identity.owner_id


def current_mcp_request_can_access_owner(owner_id: str | None) -> bool:
    """Require exact object ownership for scoped keys and preserve operator authority."""
    identity = current_mcp_request_identity()
    if identity is None or identity.authentication != "scoped_key":
        return True
    return owner_id is not None and identity.owner_id == owner_id


def prepared_request_scope(canonical_expert: str, *, allow_direct_stdio: bool = False) -> CallerScope:
    """Require trusted scoped HTTP authority before private preparation work."""
    from deepr.experts.preparation_privacy import (
        PreparationIdentityError,
        preparation_scoped_key_scope,
        preparation_stdio_scope,
    )

    if not canonical_expert or not canonical_expert.strip():
        raise PreparationIdentityError("Prepared consultation requires an explicit canonical expert")
    identity = current_mcp_request_identity()
    if identity is None:
        if not allow_direct_stdio:
            raise PreparationIdentityError("Prepared consultation requires a trusted transport identity")
        return preparation_stdio_scope()
    if identity.transport == "stdio":
        if not identity.authenticated or identity.authentication != "stdio":
            raise PreparationIdentityError("Prepared stdio identity is unavailable")
        return preparation_stdio_scope()
    if (
        identity.transport != "http"
        or not identity.authenticated
        or identity.authentication != "scoped_key"
        or not isinstance(identity.scoped_key_id, str)
        or not identity.scoped_key_id.strip()
    ):
        raise PreparationIdentityError("Prepared HTTP consultation requires an authenticated scoped key")
    expected = MCPRequestIdentity.http_scoped_key(
        key_id=identity.scoped_key_id,
        expert_allowlist=identity.expert_allowlist,
        peer_is_loopback=identity.peer_is_loopback,
    )
    if identity.owner_id != expected.owner_id:
        raise PreparationIdentityError("Prepared HTTP identity binding is unavailable")
    if identity.expert_allowlist and canonical_expert not in identity.expert_allowlist:
        raise PreparationIdentityError("Prepared consultation is outside the current expert scope")
    return preparation_scoped_key_scope(identity.owner_id)
