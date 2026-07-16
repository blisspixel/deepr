"""MCP adapter tests for durable expert conversations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from deepr.experts.conversation.service import ExpertConversationService
from deepr.experts.conversation.store import ExpertConversationStore
from deepr.mcp import expert_conversation as adapter_module
from deepr.mcp.expert_conversation import (
    OPERATION_KIND,
    OPERATION_SCHEMA_VERSION,
    MCPExpertConversationTools,
)
from deepr.mcp.request_context import (
    MCPRequestIdentity,
    bind_mcp_request_identity,
    reset_mcp_request_identity,
)
from tests.unit.conversation_fixtures import CompletingExecutor, expert_snapshot


class EmptyExpertStore:
    def list_all(self) -> list[Any]:
        return []


async def _model() -> str:
    return "fixture-local-model"


def _adapter(tmp_path: Path) -> tuple[MCPExpertConversationTools, CompletingExecutor]:
    executor = CompletingExecutor()
    service = ExpertConversationService(
        ExpertConversationStore(tmp_path / "conversations.db"),
        lambda: executor,
    )
    return MCPExpertConversationTools(EmptyExpertStore(), service=service, model_resolver=_model), executor


def _error_code(payload: dict[str, Any]) -> str:
    return str(payload["error"]["code"])


@pytest.mark.asyncio
async def test_start_continue_get_close_and_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adapter_module,
        "compile_conversation_snapshots",
        lambda *_args, **_kwargs: (expert_snapshot(),),
    )
    adapter, executor = _adapter(tmp_path)

    started = await adapter.start(message="First question", idempotency_key="start-1")
    assert started["schema_version"] == OPERATION_SCHEMA_VERSION
    assert started["kind"] == OPERATION_KIND
    assert started["operation"] == "start"
    assert started["conversation"]["backend"]["backend_class"] == "local"
    assert started["conversation"]["backend"]["live_metered_fallback"] is False
    assert started["turn"]["state"] == "completed"
    assert len(executor.contexts) == 1

    replayed = await adapter.start(message="First question", idempotency_key="start-1")
    assert replayed["replayed"] is True
    assert replayed["conversation"]["conversation_id"] == started["conversation"]["conversation_id"]
    assert len(executor.contexts) == 1

    conversation_id = started["conversation"]["conversation_id"]
    continued = await adapter.continue_conversation(
        conversation_id=conversation_id,
        expected_version=started["conversation"]["version"],
        idempotency_key="continue-1",
        message="Follow-up question",
    )
    assert continued["operation"] == "continue"
    assert continued["turn"]["ordinal"] == 2
    assert len(executor.contexts) == 2

    restarted_service = ExpertConversationService(
        ExpertConversationStore(tmp_path / "conversations.db"),
        lambda: executor,
    )
    restarted = MCPExpertConversationTools(
        EmptyExpertStore(),
        service=restarted_service,
        model_resolver=_model,
    )
    inspected = await restarted.get(conversation_id=conversation_id)
    assert inspected["operation"] == "get"
    assert inspected["turn"]["ordinal"] == 2

    closed = await restarted.close(
        conversation_id=conversation_id,
        expected_version=inspected["conversation"]["version"],
        delete_content=True,
    )
    assert closed["conversation"]["state"] == "closed"
    assert closed["conversation"]["retention"]["content_deleted"] is True
    assert closed["turn"]["request"]["content_available"] is False
    assert closed["turn"]["artifact_available"] is False


@pytest.mark.asyncio
async def test_duplicate_start_replays_even_when_compiled_snapshot_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markers = iter(("1", "2"))
    monkeypatch.setattr(
        adapter_module,
        "compile_conversation_snapshots",
        lambda *_args, **_kwargs: (expert_snapshot(marker=next(markers)),),
    )
    adapter, executor = _adapter(tmp_path)

    first = await adapter.start(message="Same caller request", idempotency_key="stable-key")
    second = await adapter.start(message="Same caller request", idempotency_key="stable-key")

    assert second["replayed"] is True
    assert second["conversation"]["conversation_id"] == first["conversation"]["conversation_id"]
    assert len(executor.contexts) == 1


@pytest.mark.asyncio
async def test_cross_key_lookup_is_indistinguishable_from_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adapter_module,
        "compile_conversation_snapshots",
        lambda *_args, **_kwargs: (expert_snapshot(),),
    )
    adapter, _executor = _adapter(tmp_path)
    first_identity = MCPRequestIdentity.http_scoped_key(
        key_id="first",
        expert_allowlist=("reliability_engineering",),
        peer_is_loopback=False,
    )
    token = bind_mcp_request_identity(first_identity)
    try:
        started = await adapter.start(
            message="Private question",
            idempotency_key="private-start",
            experts=["reliability_engineering"],
        )
    finally:
        reset_mcp_request_identity(token)

    second_identity = MCPRequestIdentity.http_scoped_key(
        key_id="second",
        expert_allowlist=("reliability_engineering",),
        peer_is_loopback=False,
    )
    token = bind_mcp_request_identity(second_identity)
    try:
        denied = await adapter.get(conversation_id=started["conversation"]["conversation_id"])
    finally:
        reset_mcp_request_identity(token)

    assert _error_code(denied) == "not_found"
    assert denied["error"]["safe_message"] == "Conversation not found."


@pytest.mark.asyncio
async def test_current_key_scope_is_revalidated_on_every_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adapter_module,
        "compile_conversation_snapshots",
        lambda *_args, **_kwargs: (expert_snapshot(),),
    )
    adapter, _executor = _adapter(tmp_path)
    allowed = MCPRequestIdentity.http_scoped_key(
        key_id="agent",
        expert_allowlist=("reliability_engineering",),
        peer_is_loopback=False,
    )
    token = bind_mcp_request_identity(allowed)
    try:
        started = await adapter.start(
            message="Scoped question",
            idempotency_key="scope-start",
            experts=["reliability_engineering"],
        )
    finally:
        reset_mcp_request_identity(token)

    narrowed = MCPRequestIdentity.http_scoped_key(
        key_id="agent",
        expert_allowlist=("different_expert",),
        peer_is_loopback=False,
    )
    token = bind_mcp_request_identity(narrowed)
    try:
        denied = await adapter.get(conversation_id=started["conversation"]["conversation_id"])
    finally:
        reset_mcp_request_identity(token)

    assert _error_code(denied) == "ownership_denied"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity",
    [
        MCPRequestIdentity.http_unauthenticated(peer_is_loopback=True),
        MCPRequestIdentity.http_shared_token(configured_token="secret", peer_is_loopback=False),
    ],
)
async def test_http_auth_and_lan_scoped_key_requirements_fail_before_model_probe(
    tmp_path: Path,
    identity: MCPRequestIdentity,
) -> None:
    probed = False

    async def resolver() -> str:
        nonlocal probed
        probed = True
        return "should-not-run"

    service = ExpertConversationService(
        ExpertConversationStore(tmp_path / "conversations.db"),
        CompletingExecutor,
    )
    adapter = MCPExpertConversationTools(EmptyExpertStore(), service=service, model_resolver=resolver)
    token = bind_mcp_request_identity(identity)
    try:
        denied = await adapter.start(message="question", idempotency_key="auth-start")
    finally:
        reset_mcp_request_identity(token)

    assert _error_code(denied) == "ownership_denied"
    assert probed is False
