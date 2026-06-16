"""Core subagent runtime contracts.

Defines the typed primitives for agent identity, budget isolation,
result reporting, and the abstract contract that all subagents implement.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    """Role a subagent plays in an orchestration."""

    PLANNER = "planner"
    WORKER = "worker"
    SYNTHESIZER = "synthesizer"


class AgentStatus(str, Enum):
    """Terminal status of an agent execution."""

    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass
class AgentIdentity:
    """Identity and lineage of a subagent within an orchestration.

    Every agent gets a unique agent_id and inherits the trace_id from
    its parent orchestration. parent_agent_id links the tree.
    """

    agent_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    role: AgentRole = AgentRole.WORKER
    parent_agent_id: str | None = None
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""

    def child(
        self,
        role: AgentRole = AgentRole.WORKER,
        name: str = "",
    ) -> AgentIdentity:
        """Create a child identity that inherits this agent's trace_id."""
        return AgentIdentity(
            role=role,
            parent_agent_id=self.agent_id,
            trace_id=self.trace_id,
            name=name,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "parent_agent_id": self.parent_agent_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "name": self.name,
        }


@dataclass
class AgentBudget:
    """Per-agent budget isolation with guard checks.

    Tracks cost accumulation against a hard cap. The ``check`` method
    should be called before any cost-incurring operation.
    """

    max_cost: float = 10.0
    cost_accumulated: float = 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.max_cost - self.cost_accumulated)

    @property
    def utilization(self) -> float:
        """Fraction of budget consumed (0.0 - 1.0)."""
        if self.max_cost <= 0:
            return 1.0
        return min(1.0, self.cost_accumulated / self.max_cost)

    def check(self, estimated_cost: float) -> tuple[bool, str]:
        """Return (allowed, reason) for a proposed spend."""
        if estimated_cost < 0:
            return False, "Estimated cost cannot be negative"
        if estimated_cost > self.remaining:
            return (
                False,
                f"Insufficient budget: ${estimated_cost:.4f} > ${self.remaining:.4f} remaining",
            )
        return True, "OK"

    def record(self, cost: float) -> None:
        """Record an actual spend against this budget."""
        self.cost_accumulated += cost

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cost": self.max_cost,
            "cost_accumulated": round(self.cost_accumulated, 6),
            "remaining": round(self.remaining, 6),
            "utilization": round(self.utilization, 4),
        }


@dataclass
class AgentResult:
    """Standardised result returned by every subagent execution."""

    agent_id: str = ""
    trace_id: str = ""
    output: str = ""
    artifact_ids: list[str] = field(default_factory=list)
    cost: float = 0.0
    status: AgentStatus = AgentStatus.SUCCESS
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "trace_id": self.trace_id,
            "output": self.output,
            "artifact_ids": self.artifact_ids,
            "cost": round(self.cost, 6),
            "status": self.status.value,
            "metadata": self.metadata,
        }


class SubagentContract(ABC):
    """Abstract contract that all subagents must implement.

    Callers invoke ``execute`` with a query, budget, and identity.
    The implementation must:
    - Respect the budget (call ``budget.check()`` before spending)
    - Record costs via ``budget.record()``
    - Return a well-formed ``AgentResult``
    - Propagate ``identity.trace_id`` in any downstream calls
    """

    @abstractmethod
    async def execute(
        self,
        query: str,
        budget: AgentBudget,
        identity: AgentIdentity,
    ) -> AgentResult:
        """Execute the agent's task within the given budget and identity."""
        ...
