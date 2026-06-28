"""A2A protocol data models.

Pure data definitions for the Agent-to-Agent protocol including
task state, agent cards, and task requests.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

A2A_TASK_SCHEMA_VERSION = "deepr-a2a-task-v1"
A2A_TASK_KIND = "deepr.a2a.task"


class TaskState(str, Enum):
    """Lifecycle states for an A2A task."""

    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid state transitions
VALID_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.SUBMITTED: frozenset({TaskState.WORKING, TaskState.CANCELLED}),
    TaskState.WORKING: frozenset(
        {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


@dataclass
class AgentSkill:
    """A single skill in the agent card."""

    name: str
    description: str
    domain: str
    input_modes: list[str] = field(default_factory=lambda: ["text/plain"])
    output_modes: list[str] = field(default_factory=lambda: ["application/json"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "input_modes": self.input_modes,
            "output_modes": self.output_modes,
        }


@dataclass
class AgentCard:
    """Agent card served at /.well-known/agent.json."""

    name: str = "deepr"
    description: str = "Multi-provider research automation with persistent expert agents"
    version: str = ""
    url: str = ""
    skills: list[AgentSkill] = field(default_factory=list)
    supported_modes: list[str] = field(default_factory=lambda: ["text/plain", "application/json"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "url": self.url,
            "skills": [s.to_dict() for s in self.skills],
            "supported_modes": self.supported_modes,
        }


@dataclass
class TaskRequest:
    """Incoming A2A task request."""

    skill: str
    input: str
    input_mode: str = "text/plain"
    budget: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    """A2A task with lifecycle state."""

    id: str
    state: TaskState
    skill: str
    input: str
    result: Any = None
    error: Any = None
    cost: float = 0.0
    trace_id: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": A2A_TASK_SCHEMA_VERSION,
            "kind": A2A_TASK_KIND,
            "contract": {
                "task_state_authoritative": True,
                "cost_field": "cost",
                "result_untrusted": True,
                "compatibility": {
                    "additive_fields": True,
                    "breaking_changes_require_new_schema_version": True,
                    "deprecation_policy": "Additive fields only within v1.",
                },
            },
            "id": self.id,
            "state": self.state.value,
            "skill": self.skill,
            "input": self.input,
            "result": self.result,
            "error": self.error,
            "cost": self.cost,
            "trace_id": self.trace_id,
            "artifacts": self.artifacts,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }
