"""Tests for authenticated MCP request identity isolation."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from deepr.mcp.request_context import (
    MCPRequestIdentity,
    bind_mcp_request_identity,
    current_mcp_request_identity,
    reset_mcp_request_identity,
    prepared_request_scope,
)


def test_owner_bindings_are_stable_and_do_not_embed_secrets() -> None:
    first = MCPRequestIdentity.http_shared_token(configured_token="top-secret", peer_is_loopback=True)
    duplicate = MCPRequestIdentity.http_shared_token(configured_token="top-secret", peer_is_loopback=True)
    other = MCPRequestIdentity.http_shared_token(configured_token="different", peer_is_loopback=True)

    assert first.owner_id == duplicate.owner_id
    assert first.owner_id != other.owner_id
    assert "top-secret" not in first.owner_id


@pytest.mark.asyncio
async def test_concurrent_request_contexts_do_not_cross() -> None:
    ready = asyncio.Event()
    observed: dict[str, str] = {}
    waiting = 0
    lock = asyncio.Lock()

    async def worker(name: str) -> None:
        nonlocal waiting
        identity = MCPRequestIdentity.http_scoped_key(
            key_id=name,
            expert_allowlist=(name,),
            peer_is_loopback=False,
        )
        token = bind_mcp_request_identity(identity)
        try:
            async with lock:
                waiting += 1
                if waiting == 2:
                    ready.set()
            await ready.wait()
            await asyncio.sleep(0)
            current = current_mcp_request_identity()
            assert current is not None
            observed[name] = str(current.scoped_key_id)
        finally:
            reset_mcp_request_identity(token)

    await asyncio.gather(worker("alpha"), worker("beta"))

    assert observed == {"alpha": "alpha", "beta": "beta"}
    assert current_mcp_request_identity() is None


@pytest.mark.parametrize("loopback", [False, True])
@pytest.mark.parametrize("authentication", ["none", "shared_token"])
def test_prepared_http_requires_scoped_key_even_on_loopback(loopback, authentication):
    from deepr.experts.preparation_privacy import PreparationIdentityError

    identity = (
        MCPRequestIdentity.http_unauthenticated(peer_is_loopback=loopback)
        if authentication == "none" else MCPRequestIdentity.http_shared_token(configured_token="secret", peer_is_loopback=loopback)
    )
    token = bind_mcp_request_identity(identity)
    try:
        with pytest.raises(PreparationIdentityError, match="scoped key"):
            prepared_request_scope("Allowed", allow_direct_stdio=True)
    finally:
        reset_mcp_request_identity(token)


def test_prepared_scope_refuses_absent_context_without_explicit_stdio_authority(monkeypatch):
    from deepr.experts import preparation_privacy

    with pytest.raises(preparation_privacy.PreparationIdentityError, match="transport identity"):
        prepared_request_scope("Allowed")
    monkeypatch.setattr(preparation_privacy, "current_os_principal", lambda: "actual-user")
    assert prepared_request_scope("Allowed", allow_direct_stdio=True) == preparation_privacy.preparation_stdio_scope()


def test_prepared_scoped_key_enforces_owner_and_canonical_expert_before_return():
    from deepr.experts.preparation_privacy import PreparationIdentityError

    identity = MCPRequestIdentity.http_scoped_key(key_id="key-id", expert_allowlist=("Allowed",), peer_is_loopback=True)
    token = bind_mcp_request_identity(identity)
    try:
        scope = prepared_request_scope("Allowed")
        assert scope.namespace_sha256 and "key-id" not in scope.namespace_sha256
        with pytest.raises(PreparationIdentityError, match="expert scope"):
            prepared_request_scope("Other")
    finally:
        reset_mcp_request_identity(token)
    token = bind_mcp_request_identity(replace(identity, owner_id="forged-owner"))
    try:
        with pytest.raises(PreparationIdentityError, match="identity binding"):
            prepared_request_scope("Allowed")
    finally:
        reset_mcp_request_identity(token)


@pytest.mark.parametrize("key_id", ["", "   "])
def test_prepared_scoped_key_requires_nonblank_server_key_identity(key_id):
    from deepr.experts.preparation_privacy import PreparationIdentityError

    identity = MCPRequestIdentity.http_scoped_key(key_id=key_id, expert_allowlist=(), peer_is_loopback=True)
    token = bind_mcp_request_identity(identity)
    try:
        with pytest.raises(PreparationIdentityError, match="scoped key"):
            prepared_request_scope("Allowed")
    finally:
        reset_mcp_request_identity(token)
