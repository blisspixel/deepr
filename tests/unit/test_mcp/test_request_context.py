"""Tests for authenticated MCP request identity isolation."""

from __future__ import annotations

import asyncio

import pytest

from deepr.mcp.request_context import (
    MCPRequestIdentity,
    bind_mcp_request_identity,
    current_mcp_request_identity,
    reset_mcp_request_identity,
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
