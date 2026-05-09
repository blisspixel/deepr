"""A2A task lifecycle state machine.

Manages task creation, state transitions, and metadata tracking
for the Agent-to-Agent protocol.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from deepr.a2a.models import VALID_TRANSITIONS, Task, TaskRequest, TaskState

logger = logging.getLogger(__name__)


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, task_id: str, current: TaskState, target: TaskState) -> None:
        self.task_id = task_id
        self.current_state = current
        self.target_state = target
        super().__init__(
            f"Invalid transition for task {task_id}: "
            f"{current.value} → {target.value}"
        )


class TaskNotFoundError(Exception):
    """Raised when a task ID is not found."""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(f"Task not found: {task_id}")


class TaskManager:
    """Manage A2A task lifecycle with state machine enforcement.

    Enforces valid transitions:
    - submitted → working → (completed | failed | cancelled)
    - submitted → cancelled

    Completed tasks include cost, trace_id, confidence metadata.
    Failed tasks include error with reason and retryable flag.

    Usage::

        manager = TaskManager()
        task = manager.create_task(TaskRequest(skill="recon", input="example.com"))
        task = manager.transition(task.id, TaskState.WORKING)
        task = manager.transition(task.id, TaskState.COMPLETED, result={"data": "..."})
    """

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def create_task(
        self,
        request: TaskRequest,
        budget: float | None = None,
    ) -> Task:
        """Create a new task in SUBMITTED state.

        Args:
            request: The incoming task request.
            budget: Optional budget cap for this task's expert session.

        Returns:
            The created Task with a unique ID.
        """
        task_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc)

        metadata = dict(request.metadata)
        if budget is not None or request.budget is not None:
            metadata["budget_cap"] = budget if budget is not None else request.budget

        task = Task(
            id=task_id,
            state=TaskState.SUBMITTED,
            skill=request.skill,
            input=request.input,
            created_at=now,
            updated_at=now,
            metadata=metadata,
        )

        self._tasks[task_id] = task
        logger.debug("Created task %s for skill '%s'", task_id, request.skill)
        return task

    def get_task(self, task_id: str) -> Task | None:
        """Get task by ID. Returns None if not found."""
        return self._tasks.get(task_id)

    def transition(
        self,
        task_id: str,
        new_state: TaskState,
        result: Any = None,
        error: Any = None,
        cost: float = 0.0,
        trace_id: str = "",
    ) -> Task:
        """Transition task state with validation.

        Args:
            task_id: The task to transition.
            new_state: Target state.
            result: Result data (for completed tasks).
            error: Error info (for failed tasks).
            cost: Cost incurred (for completed/failed tasks).
            trace_id: Trace ID for correlation.

        Returns:
            The updated Task.

        Raises:
            TaskNotFoundError: If task_id not found.
            InvalidTransitionError: If transition is not valid.
        """
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        valid_targets = VALID_TRANSITIONS.get(task.state, frozenset())
        if new_state not in valid_targets:
            raise InvalidTransitionError(task_id, task.state, new_state)

        task.state = new_state
        task.updated_at = datetime.now(timezone.utc)

        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        if cost > 0:
            task.cost = cost
        if trace_id:
            task.trace_id = trace_id

        logger.debug(
            "Task %s transitioned to %s (cost=%.4f)",
            task_id,
            new_state.value,
            task.cost,
        )
        return task

    @property
    def task_count(self) -> int:
        """Total number of tasks."""
        return len(self._tasks)

    def list_tasks(self, state: TaskState | None = None) -> list[Task]:
        """List tasks, optionally filtered by state."""
        if state is None:
            return list(self._tasks.values())
        return [t for t in self._tasks.values() if t.state == state]
