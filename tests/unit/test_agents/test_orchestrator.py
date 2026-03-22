"""Tests for AgentOrchestrator — planner -> workers -> synthesizer pipeline."""

import pytest

from deepr.agents.contract import (
    AgentBudget,
    AgentIdentity,
    AgentResult,
    AgentStatus,
    SubagentContract,
)
from deepr.agents.orchestrator import AgentOrchestrator


class PlannerAgent(SubagentContract):
    """Returns subtasks as newline-separated strings."""

    def __init__(self, subtasks: list[str]):
        self._subtasks = subtasks

    async def execute(self, query: str, budget: AgentBudget, identity: AgentIdentity) -> AgentResult:
        cost = 0.01
        budget.record(cost)
        return AgentResult(
            agent_id=identity.agent_id,
            trace_id=identity.trace_id,
            output="\n".join(self._subtasks),
            cost=cost,
            status=AgentStatus.SUCCESS,
        )


class WorkerAgent(SubagentContract):
    """Echoes the query with a prefix."""

    def __init__(self, prefix: str = "result"):
        self._prefix = prefix

    async def execute(self, query: str, budget: AgentBudget, identity: AgentIdentity) -> AgentResult:
        cost = 0.05
        budget.record(cost)
        return AgentResult(
            agent_id=identity.agent_id,
            trace_id=identity.trace_id,
            output=f"{self._prefix}: {query}",
            cost=cost,
            status=AgentStatus.SUCCESS,
            artifact_ids=[f"artifact-{identity.agent_id}"],
        )


class SynthesizerAgent(SubagentContract):
    """Combines input into a summary."""

    async def execute(self, query: str, budget: AgentBudget, identity: AgentIdentity) -> AgentResult:
        cost = 0.02
        budget.record(cost)
        return AgentResult(
            agent_id=identity.agent_id,
            trace_id=identity.trace_id,
            output=f"SYNTHESIS: {query[:200]}",
            cost=cost,
            status=AgentStatus.SUCCESS,
        )


class FailingPlannerAgent(SubagentContract):
    async def execute(self, query: str, budget: AgentBudget, identity: AgentIdentity) -> AgentResult:
        raise RuntimeError("Planner crashed")


@pytest.mark.asyncio
async def test_full_pipeline():
    """End-to-end: planner returns 3 subtasks, workers execute, synthesizer combines."""
    planner = PlannerAgent(["task-1", "task-2", "task-3"])
    workers = [WorkerAgent("w1"), WorkerAgent("w2"), WorkerAgent("w3")]
    synthesizer = SynthesizerAgent()

    orchestrator = AgentOrchestrator(planner, workers, synthesizer)
    result = await orchestrator.run("complex question", budget=10.0)

    assert result.status == AgentStatus.SUCCESS
    assert "SYNTHESIS" in result.output
    # Cost = planner(0.01) + 3 workers(0.15) + synthesizer(0.02)
    assert result.cost == pytest.approx(0.18, abs=0.01)
    assert len(result.artifact_ids) == 3  # One per worker
    assert result.metadata["subtask_count"] == 3
    assert result.metadata["worker_count"] == 3


@pytest.mark.asyncio
async def test_planner_failure_returns_failed():
    """If planner fails, orchestrator returns FAILED without running workers."""
    planner = FailingPlannerAgent()
    workers = [WorkerAgent()]
    synthesizer = SynthesizerAgent()

    orchestrator = AgentOrchestrator(planner, workers, synthesizer)
    result = await orchestrator.run("test", budget=10.0)

    assert result.status == AgentStatus.FAILED
    assert "Planning failed" in result.output
    assert result.cost == 0.0


@pytest.mark.asyncio
async def test_no_workers_uses_planner_output():
    """With no workers, synthesizer gets planner output directly."""
    planner = PlannerAgent(["single task"])
    synthesizer = SynthesizerAgent()

    orchestrator = AgentOrchestrator(planner, workers=[], synthesizer=synthesizer)
    result = await orchestrator.run("test", budget=10.0)

    assert result.status == AgentStatus.SUCCESS
    assert "SYNTHESIS" in result.output
    # Cost = planner(0.01) + synthesizer(0.02)
    assert result.cost == pytest.approx(0.03, abs=0.01)


@pytest.mark.asyncio
async def test_trace_id_propagated():
    """All agents should share the same trace_id."""
    planner = PlannerAgent(["task-1"])
    workers = [WorkerAgent()]
    synthesizer = SynthesizerAgent()

    orchestrator = AgentOrchestrator(planner, workers, synthesizer)
    result = await orchestrator.run("test", budget=10.0, trace_id="shared-trace")

    assert result.trace_id == "shared-trace"


@pytest.mark.asyncio
async def test_budget_split():
    """Budget should be split across phases."""
    planner = PlannerAgent(["a", "b"])
    workers = [WorkerAgent(), WorkerAgent()]
    synthesizer = SynthesizerAgent()

    orchestrator = AgentOrchestrator(planner, workers, synthesizer)
    result = await orchestrator.run("test", budget=100.0)

    # Planner gets 10% = $10, workers get 70% / 2 = $35 each, synthesizer gets 20% = $20
    # Actual spending is much less, but it shouldn't exceed these limits
    assert result.cost < 100.0
    assert result.status == AgentStatus.SUCCESS
