"""A2A (Agent-to-Agent) protocol support for Deepr.

Exposes Deepr experts as A2A-discoverable agents with task lifecycle
management and HTTP endpoints.
"""

from deepr.a2a.models import AgentCard, AgentSkill, Task, TaskRequest, TaskState

__all__ = [
    "AgentCard",
    "AgentSkill",
    "Task",
    "TaskRequest",
    "TaskState",
]
