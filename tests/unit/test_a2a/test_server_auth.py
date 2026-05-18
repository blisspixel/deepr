"""Regression tests: A2A server now requires a bearer token for
state-changing endpoints (POST /tasks, POST /tasks/{id}/cancel).

Discovery (GET /.well-known/agent.json) remains public so peers can
introspect skills without auth.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from deepr.a2a.server import A2AServer
from deepr.a2a.task_manager import TaskManager


@pytest.fixture
def server():
    card = MagicMock()
    card.to_dict.return_value = {"name": "test-agent"}
    return A2AServer(card_generator=card, task_manager=TaskManager(), auth_token="secret-123")


@pytest.fixture
def server_no_auth():
    card = MagicMock()
    card.to_dict.return_value = {"name": "test-agent"}
    return A2AServer(card_generator=card, task_manager=TaskManager(), auth_token=None)


@pytest.mark.asyncio
async def test_agent_card_is_public(server):
    status, body = await server.handle_request("GET", "/.well-known/agent.json", "")
    assert status == 200
    assert body == {"name": "test-agent"}


@pytest.mark.asyncio
async def test_create_task_requires_auth(server):
    status, body = await server.handle_request(
        "POST",
        "/tasks",
        '{"skill":"x","input":"y"}',
        auth_header="",
    )
    assert status == 401


@pytest.mark.asyncio
async def test_create_task_with_wrong_token(server):
    status, body = await server.handle_request(
        "POST",
        "/tasks",
        '{"skill":"x","input":"y"}',
        auth_header="Bearer wrong-token",
    )
    assert status == 401


@pytest.mark.asyncio
async def test_create_task_with_valid_token(server):
    status, body = await server.handle_request(
        "POST",
        "/tasks",
        '{"skill":"deepr_research","input":"hello"}',
        auth_header="Bearer secret-123",
    )
    assert status == 201


@pytest.mark.asyncio
async def test_create_task_with_non_ascii_token(server):
    """compare_digest raises TypeError on non-ASCII strings — we treat that
    as a normal 401 rather than letting it escape as 500."""
    status, body = await server.handle_request(
        "POST",
        "/tasks",
        '{"skill":"x","input":"y"}',
        auth_header="Bearer 非ascii",
    )
    assert status == 401


@pytest.mark.asyncio
async def test_no_token_configured_allows_all(server_no_auth):
    """When no token is configured (loopback-only dev mode) the gate is open."""
    status, body = await server_no_auth.handle_request(
        "POST",
        "/tasks",
        '{"skill":"deepr_research","input":"hello"}',
    )
    assert status == 201


def test_start_refuses_non_loopback_without_token():
    import asyncio

    card = MagicMock()
    card.to_dict.return_value = {"name": "test-agent"}
    server = A2AServer(card_generator=card, task_manager=TaskManager(), auth_token=None)

    async def _try_start():
        await server.start("0.0.0.0", 0)

    with pytest.raises(RuntimeError, match="DEEPR_A2A_TOKEN"):
        asyncio.run(_try_start())


def test_start_refuses_empty_host_without_token():
    """Regression: host='' makes asyncio.start_server bind ALL interfaces,
    not loopback. The earlier guard listed '' alongside 'localhost', so a
    caller could bypass the public-bind refusal entirely by passing an
    empty string. Empty/None hosts must be treated as public binds.
    """
    import asyncio

    card = MagicMock()
    card.to_dict.return_value = {"name": "test-agent"}
    server = A2AServer(card_generator=card, task_manager=TaskManager(), auth_token=None)

    async def _try_start():
        await server.start("", 0)

    with pytest.raises(RuntimeError, match="DEEPR_A2A_TOKEN"):
        asyncio.run(_try_start())
