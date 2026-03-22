"""Tests for AgentIdentity propagation through ExpertCouncil."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.agents.contract import AgentIdentity, AgentRole


@pytest.fixture
def council():
    from deepr.experts.council import ExpertCouncil

    return ExpertCouncil()


@pytest.fixture
def parent_identity():
    return AgentIdentity(
        agent_id="council-root",
        role=AgentRole.PLANNER,
        trace_id="trace-abc123",
        name="council-orchestrator",
    )


@pytest.mark.asyncio
async def test_council_creates_child_identities(council, parent_identity):
    """Council should create child AgentIdentity per expert when parent identity is provided."""
    captured_identities = []

    async def mock_start_session(name, budget=None, agentic=False, quiet=False, agent_identity=None, **kwargs):
        if agent_identity is not None:
            captured_identities.append(agent_identity)
        session = MagicMock()
        session.send_message = AsyncMock(return_value="Expert response")
        session.cost_accumulated = 0.01
        return session

    experts = [
        {"name": "expert-a", "domain": "security"},
        {"name": "expert-b", "domain": "cloud"},
    ]

    with patch("deepr.experts.chat.start_chat_session", side_effect=mock_start_session):
        with patch.object(council, "_synthesise", new_callable=AsyncMock) as mock_synth:
            mock_synth.return_value = {"text": "Synthesis", "agreements": [], "disagreements": [], "cost": 0.001}
            result = await council.consult(
                "test query",
                experts=experts,
                budget=5.0,
                agent_identity=parent_identity,
            )

    assert len(captured_identities) == 2
    for child in captured_identities:
        assert child.trace_id == parent_identity.trace_id
        assert child.parent_agent_id == parent_identity.agent_id
        assert child.role == AgentRole.WORKER
        assert child.name.startswith("council-")


@pytest.mark.asyncio
async def test_council_no_identity_without_parent(council):
    """Council should NOT create identities when no parent identity is provided."""
    captured_identities = []

    async def mock_start_session(name, budget=None, agentic=False, quiet=False, agent_identity=None, **kwargs):
        captured_identities.append(agent_identity)
        session = MagicMock()
        session.send_message = AsyncMock(return_value="Expert response")
        session.cost_accumulated = 0.01
        return session

    experts = [{"name": "expert-a", "domain": "security"}]

    with patch("deepr.experts.chat.start_chat_session", side_effect=mock_start_session):
        with patch.object(council, "_synthesise", new_callable=AsyncMock) as mock_synth:
            mock_synth.return_value = {"text": "Synthesis", "agreements": [], "disagreements": [], "cost": 0.001}
            await council.consult("test query", experts=experts, budget=5.0)

    # agent_identity should be None when no parent provided
    assert all(ident is None for ident in captured_identities)


@pytest.mark.asyncio
async def test_council_child_identities_are_unique(council, parent_identity):
    """Each expert in a council should get a unique child agent_id."""
    captured_identities = []

    async def mock_start_session(name, budget=None, agentic=False, quiet=False, agent_identity=None, **kwargs):
        if agent_identity is not None:
            captured_identities.append(agent_identity)
        session = MagicMock()
        session.send_message = AsyncMock(return_value="response")
        session.cost_accumulated = 0.0
        return session

    experts = [
        {"name": "a", "domain": "x"},
        {"name": "b", "domain": "y"},
        {"name": "c", "domain": "z"},
    ]

    with patch("deepr.experts.chat.start_chat_session", side_effect=mock_start_session):
        with patch.object(council, "_synthesise", new_callable=AsyncMock) as mock_synth:
            mock_synth.return_value = {"text": "", "agreements": [], "disagreements": [], "cost": 0.0}
            await council.consult("q", experts=experts, budget=10.0, agent_identity=parent_identity)

    agent_ids = [c.agent_id for c in captured_identities]
    assert len(agent_ids) == len(set(agent_ids)), "Child agent_ids must be unique"
