"""Tests for AgentTool — wrapping SubagentContract as OpenAI tool."""

import pytest

from deepr.agents.agent_tool import AgentTool
from deepr.agents.contract import (
    AgentBudget,
    AgentIdentity,
    AgentResult,
    AgentRole,
    AgentStatus,
    SubagentContract,
)


class MockAgent(SubagentContract):
    """Simple mock agent for testing."""

    def __init__(self, response: str = "mock output", cost: float = 0.10):
        self._response = response
        self._cost = cost

    async def execute(self, query: str, budget: AgentBudget, identity: AgentIdentity) -> AgentResult:
        budget.record(self._cost)
        return AgentResult(
            agent_id=identity.agent_id,
            trace_id=identity.trace_id,
            output=f"{self._response}: {query}",
            cost=self._cost,
            status=AgentStatus.SUCCESS,
        )


class FailingAgent(SubagentContract):
    async def execute(self, query: str, budget: AgentBudget, identity: AgentIdentity) -> AgentResult:
        raise RuntimeError("Agent exploded")


class TestAgentToolSchema:
    def test_to_openai_tool(self):
        tool = AgentTool(
            name="research_agent",
            description="Runs deep research",
            agent=MockAgent(),
        )
        schema = tool.to_openai_tool()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "research_agent"
        assert "query" in schema["function"]["parameters"]["properties"]
        assert "query" in schema["function"]["parameters"]["required"]

    def test_schema_description(self):
        tool = AgentTool(name="test", description="Test agent tool", agent=MockAgent())
        schema = tool.to_openai_tool()
        assert schema["function"]["description"] == "Test agent tool"


class TestAgentToolExecution:
    @pytest.mark.asyncio
    async def test_execute_with_dict_args(self):
        tool = AgentTool(name="worker", description="Worker", agent=MockAgent("done"), budget_limit=2.0)
        parent = AgentIdentity(role=AgentRole.PLANNER, name="parent")

        result = await tool.execute({"query": "test query"}, parent)

        assert result.status == AgentStatus.SUCCESS
        assert "done: test query" in result.output
        assert result.cost == 0.10
        assert result.trace_id == parent.trace_id

    @pytest.mark.asyncio
    async def test_execute_with_json_string(self):
        tool = AgentTool(name="worker", description="Worker", agent=MockAgent())
        parent = AgentIdentity()

        result = await tool.execute('{"query": "json test"}', parent)

        assert result.status == AgentStatus.SUCCESS
        assert "json test" in result.output

    @pytest.mark.asyncio
    async def test_execute_creates_child_identity(self):
        tool = AgentTool(name="worker", description="Worker", agent=MockAgent())
        parent = AgentIdentity(agent_id="parent-1", trace_id="trace-abc")

        result = await tool.execute({"query": "test"}, parent)

        # Result should inherit parent's trace_id
        assert result.trace_id == "trace-abc"
        # But have its own agent_id
        assert result.agent_id != "parent-1"

    @pytest.mark.asyncio
    async def test_execute_respects_budget_limit(self):
        tool = AgentTool(name="worker", description="Worker", agent=MockAgent(cost=0.10), budget_limit=3.0)
        parent = AgentIdentity()

        result = await tool.execute({"query": "test"}, parent)

        assert result.cost == 0.10

    @pytest.mark.asyncio
    async def test_execute_handles_failure(self):
        tool = AgentTool(name="failing", description="Fails", agent=FailingAgent())
        parent = AgentIdentity()

        result = await tool.execute({"query": "test"}, parent)

        assert result.status == AgentStatus.FAILED
        assert "Agent tool failed" in result.output
        assert "exploded" in result.metadata.get("error", "")
