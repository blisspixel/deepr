"""Tests for AgentIdentity propagation through TaskPlanner."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.agents.contract import AgentIdentity, AgentRole


@pytest.fixture
def parent_identity():
    return AgentIdentity(
        agent_id="planner-root",
        role=AgentRole.PLANNER,
        trace_id="trace-plan-123",
        name="task-planner",
    )


def _make_mock_session():
    session = MagicMock()
    session.send_message = AsyncMock(return_value="Step result")
    session.cost_accumulated = 0.0

    async def _send(query, status_callback=None):
        session.cost_accumulated += 0.05
        return "Step result"

    session.send_message = _send
    return session


@pytest.mark.asyncio
async def test_planner_with_identity_logs_steps(parent_identity):
    """TaskPlanner should create child identities per step when identity is provided."""
    from deepr.experts.task_planner import TaskPlanner

    session = _make_mock_session()
    planner = TaskPlanner(session, agent_identity=parent_identity)

    plan_data = {
        "query": "test",
        "steps": [
            {"id": 1, "title": "Step A", "query": "query-a", "depends_on": []},
            {"id": 2, "title": "Step B", "query": "query-b", "depends_on": []},
        ],
    }

    with patch("deepr.agents.contract.AgentIdentity.child") as mock_child:
        # Let child() return real identities
        mock_child.side_effect = lambda **kwargs: AgentIdentity(
            parent_agent_id=parent_identity.agent_id,
            trace_id=parent_identity.trace_id,
            **kwargs,
        )
        result = await planner.execute_plan(plan_data)

    assert len(result["steps"]) == 2
    assert all(s["status"] == "done" for s in result["steps"])


@pytest.mark.asyncio
async def test_planner_without_identity_still_works():
    """TaskPlanner should work normally without identity (backward compat)."""
    from deepr.experts.task_planner import TaskPlanner

    session = _make_mock_session()
    planner = TaskPlanner(session, agent_identity=None)

    plan_data = {
        "query": "test",
        "steps": [
            {"id": 1, "title": "Step A", "query": "query-a", "depends_on": []},
        ],
    }

    result = await planner.execute_plan(plan_data)
    assert len(result["steps"]) == 1
    assert result["steps"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_planner_tracks_per_step_cost(parent_identity):
    """TaskPlanner should track cost delta per step."""
    from deepr.experts.task_planner import TaskPlanner

    session = _make_mock_session()
    planner = TaskPlanner(session, agent_identity=parent_identity)

    plan_data = {
        "query": "test",
        "steps": [
            {"id": 1, "title": "Step A", "query": "q1", "depends_on": []},
            {"id": 2, "title": "Step B", "query": "q2", "depends_on": [1]},
        ],
    }

    result = await planner.execute_plan(plan_data)
    # Two steps each costing 0.05
    assert session.cost_accumulated == pytest.approx(0.10, abs=0.01)
    assert result["total_cost"] == pytest.approx(0.10, abs=0.01)
