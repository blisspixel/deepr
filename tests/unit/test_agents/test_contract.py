"""Tests for subagent runtime contract primitives."""

from deepr.agents.contract import (
    AgentBudget,
    AgentIdentity,
    AgentResult,
    AgentRole,
    AgentStatus,
)


class TestAgentIdentity:
    def test_defaults(self):
        identity = AgentIdentity()
        assert len(identity.agent_id) == 12
        assert len(identity.trace_id) == 16
        assert len(identity.span_id) == 8
        assert identity.role == AgentRole.WORKER
        assert identity.parent_agent_id is None
        assert identity.name == ""

    def test_child_inherits_trace_id(self):
        parent = AgentIdentity(role=AgentRole.PLANNER, name="planner")
        child = parent.child(role=AgentRole.WORKER, name="worker-1")

        assert child.trace_id == parent.trace_id
        assert child.parent_agent_id == parent.agent_id
        assert child.agent_id != parent.agent_id
        assert child.role == AgentRole.WORKER
        assert child.name == "worker-1"

    def test_child_chain(self):
        root = AgentIdentity(name="root")
        child = root.child(name="child")
        grandchild = child.child(name="grandchild")

        assert grandchild.trace_id == root.trace_id
        assert grandchild.parent_agent_id == child.agent_id
        assert child.parent_agent_id == root.agent_id

    def test_to_dict(self):
        identity = AgentIdentity(
            agent_id="abc123",
            role=AgentRole.SYNTHESIZER,
            parent_agent_id="parent1",
            trace_id="trace1",
            span_id="span1",
            name="synth",
        )
        d = identity.to_dict()
        assert d == {
            "agent_id": "abc123",
            "role": "synthesizer",
            "parent_agent_id": "parent1",
            "trace_id": "trace1",
            "span_id": "span1",
            "name": "synth",
        }


class TestAgentBudget:
    def test_defaults(self):
        budget = AgentBudget()
        assert budget.max_cost == 10.0
        assert budget.cost_accumulated == 0.0
        assert budget.remaining == 10.0
        assert budget.utilization == 0.0

    def test_remaining_calculation(self):
        budget = AgentBudget(max_cost=5.0, cost_accumulated=3.0)
        assert budget.remaining == 2.0
        assert budget.utilization == 0.6

    def test_remaining_never_negative(self):
        budget = AgentBudget(max_cost=1.0, cost_accumulated=5.0)
        assert budget.remaining == 0.0
        assert budget.utilization == 1.0

    def test_zero_budget_utilization(self):
        budget = AgentBudget(max_cost=0.0)
        assert budget.utilization == 1.0

    def test_check_allowed(self):
        budget = AgentBudget(max_cost=5.0)
        allowed, reason = budget.check(3.0)
        assert allowed is True
        assert reason == "OK"

    def test_check_exact_remaining(self):
        budget = AgentBudget(max_cost=5.0, cost_accumulated=3.0)
        allowed, _reason = budget.check(2.0)
        assert allowed is True

    def test_check_exceeds_budget(self):
        budget = AgentBudget(max_cost=5.0, cost_accumulated=4.0)
        allowed, reason = budget.check(2.0)
        assert allowed is False
        assert "Insufficient budget" in reason

    def test_check_negative_cost(self):
        budget = AgentBudget(max_cost=5.0)
        allowed, reason = budget.check(-1.0)
        assert allowed is False
        assert "negative" in reason.lower()

    def test_record(self):
        budget = AgentBudget(max_cost=10.0)
        budget.record(3.0)
        assert budget.cost_accumulated == 3.0
        budget.record(2.5)
        assert budget.cost_accumulated == 5.5
        assert budget.remaining == 4.5

    def test_to_dict(self):
        budget = AgentBudget(max_cost=10.0, cost_accumulated=2.5)
        d = budget.to_dict()
        assert d["max_cost"] == 10.0
        assert d["cost_accumulated"] == 2.5
        assert d["remaining"] == 7.5
        assert d["utilization"] == 0.25


class TestAgentResult:
    def test_defaults(self):
        result = AgentResult()
        assert result.output == ""
        assert result.artifact_ids == []
        assert result.cost == 0.0
        assert result.status == AgentStatus.SUCCESS

    def test_to_dict(self):
        result = AgentResult(
            agent_id="a1",
            trace_id="t1",
            output="done",
            artifact_ids=["job-1", "report-1"],
            cost=0.45,
            status=AgentStatus.FAILED,
            metadata={"error": "timeout"},
        )
        d = result.to_dict()
        assert d["agent_id"] == "a1"
        assert d["trace_id"] == "t1"
        assert d["status"] == "failed"
        assert d["artifact_ids"] == ["job-1", "report-1"]
        assert d["cost"] == 0.45
        assert d["metadata"] == {"error": "timeout"}

    def test_cost_rounding(self):
        result = AgentResult(cost=0.1 + 0.2)
        d = result.to_dict()
        assert d["cost"] == 0.3


class TestAgentStatus:
    def test_values(self):
        assert AgentStatus.SUCCESS.value == "success"
        assert AgentStatus.FAILED.value == "failed"
        assert AgentStatus.CANCELLED.value == "cancelled"
        assert AgentStatus.BUDGET_EXCEEDED.value == "budget_exceeded"


class TestAgentRole:
    def test_values(self):
        assert AgentRole.PLANNER.value == "planner"
        assert AgentRole.WORKER.value == "worker"
        assert AgentRole.SYNTHESIZER.value == "synthesizer"
