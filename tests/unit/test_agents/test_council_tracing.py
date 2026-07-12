"""Tests for AgentIdentity propagation through ExpertCouncil."""

from unittest.mock import AsyncMock, patch

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
    """Stored-context perspectives retain child identity lineage."""
    experts = [
        {"name": "expert-a", "domain": "security"},
        {"name": "expert-b", "domain": "cloud"},
    ]

    with patch.object(council, "_synthesise", new_callable=AsyncMock) as mock_synth:
        mock_synth.return_value = {"text": "Synthesis", "agreements": [], "disagreements": [], "cost": 0.001}
        result = await council.consult("test query", experts=experts, budget=5.0, agent_identity=parent_identity)

    identities = [perspective["context"]["agent_identity"] for perspective in result["perspectives"]]
    assert len(identities) == 2
    for child in identities:
        assert child["trace_id"] == parent_identity.trace_id
        assert child["parent_agent_id"] == parent_identity.agent_id
        assert child["role"] == AgentRole.WORKER.value
        assert child["name"].startswith("council-")


@pytest.mark.asyncio
async def test_council_no_identity_without_parent(council):
    """Stored-context perspectives omit lineage without a parent."""
    experts = [{"name": "expert-a", "domain": "security"}]

    with patch.object(council, "_synthesise", new_callable=AsyncMock) as mock_synth:
        mock_synth.return_value = {"text": "Synthesis", "agreements": [], "disagreements": [], "cost": 0.001}
        result = await council.consult("test query", experts=experts, budget=5.0)

    assert all("agent_identity" not in perspective["context"] for perspective in result["perspectives"])


@pytest.mark.asyncio
async def test_council_child_identities_are_unique(council, parent_identity):
    """Each expert in a council should get a unique child agent_id."""
    experts = [
        {"name": "a", "domain": "x"},
        {"name": "b", "domain": "y"},
        {"name": "c", "domain": "z"},
    ]

    with patch.object(council, "_synthesise", new_callable=AsyncMock) as mock_synth:
        mock_synth.return_value = {"text": "", "agreements": [], "disagreements": [], "cost": 0.0}
        result = await council.consult("q", experts=experts, budget=5.0, agent_identity=parent_identity)

    agent_ids = [perspective["context"]["agent_identity"]["agent_id"] for perspective in result["perspectives"]]
    assert len(agent_ids) == len(experts)
    assert len(agent_ids) == len(set(agent_ids)), "Child agent_ids must be unique"
