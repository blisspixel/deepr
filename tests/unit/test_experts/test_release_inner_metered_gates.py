"""Inner fail-closed guards for legacy metered expert helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.experts.metered_mutation_gate import MeteredExpertMutationDisabledError
from deepr.experts.profile import ExpertProfile
from deepr.experts.profile_store import ExpertStore
from deepr.experts.synthesis import KnowledgeSynthesizer


def test_task_planner_blocks_before_client_construction(monkeypatch):
    from deepr.experts import task_planner

    monkeypatch.setattr(
        task_planner,
        "AsyncOpenAI",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("client must not be constructed")),
    )

    with pytest.raises(MeteredExpertMutationDisabledError):
        task_planner.TaskPlanner(MagicMock())


@pytest.mark.asyncio
async def test_knowledge_synthesis_blocks_before_client_dispatch():
    client = MagicMock()
    client.chat.completions.create = AsyncMock()
    synthesizer = KnowledgeSynthesizer(client)

    with pytest.raises(MeteredExpertMutationDisabledError):
        await synthesizer.synthesize_new_knowledge(
            expert_name="Security Analyst",
            domain="security",
            new_documents=[{"path": "evidence.md", "content": "bounded evidence"}],
        )

    client.chat.completions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_hosted_vector_upload_blocks_before_provider_dispatch(tmp_path):
    store = ExpertStore(base_path=str(tmp_path / "experts"))
    profile = ExpertProfile(name="Security Analyst", vector_store_id="vs_test")
    document = tmp_path / "evidence.md"
    document.write_text("bounded evidence", encoding="utf-8")
    client = MagicMock()
    client.files.create = AsyncMock()
    client.vector_stores.files.create = AsyncMock()

    with pytest.raises(MeteredExpertMutationDisabledError):
        await store.add_documents_to_vector_store(profile, [str(document)], client)

    client.files.create.assert_not_awaited()
    client.vector_stores.files.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["/council bounded question", "/plan bounded question"])
async def test_paid_slash_commands_fail_closed(command):
    from deepr.experts.command_handlers import dispatch_command

    session = MagicMock()
    session.budget = 2.0
    session.cost_accumulated = 0.0

    result = await dispatch_command(session, command, {"cli": True})

    assert result is not None
    assert result.success is False
    assert "temporarily disabled" in result.output.lower()
