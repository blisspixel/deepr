"""A2A task lifecycle state machine.

Manages task creation, state transitions, and metadata tracking
for the Agent-to-Agent protocol.

Feature: mcp-client-agent-interop
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from deepr.a2a.models import VALID_TRANSITIONS, Task, TaskRequest, TaskState

logger = logging.getLogger(__name__)


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, task_id: str, current: TaskState, target: TaskState) -> None:
        self.task_id = task_id
        self.current_state = current
        self.target_state = target
        super().__init__(f"Invalid transition for task {task_id}: {current.value} → {target.value}")


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

    def __init__(self, max_terminal_tasks: int = 10_000) -> None:
        # OrderedDict so we can evict oldest terminal tasks first.
        # Without bounded eviction, a long-running A2A server leaks one
        # Task per request - even after the consumer has read the
        # final state, the entry stays in memory forever.
        from collections import OrderedDict

        self._tasks: OrderedDict[str, Task] = OrderedDict()
        self._max_terminal_tasks = max_terminal_tasks

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
        now = datetime.now(UTC)

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
        task.updated_at = datetime.now(UTC)

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

        # Bounded eviction: once a task reaches a terminal state, mark
        # it as eligible for eviction and trim from the front (oldest
        # terminal tasks) when we exceed the cap. Active states
        # (SUBMITTED / WORKING) are never evicted.
        if new_state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
            self._tasks.move_to_end(task_id)
            self._evict_old_terminal()
        return task

    def _evict_old_terminal(self) -> None:
        terminal = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
        terminal_count = sum(1 for t in self._tasks.values() if t.state in terminal)
        if terminal_count <= self._max_terminal_tasks:
            return
        # Walk from the oldest end and drop terminal entries.
        to_remove: list[str] = []
        for tid, t in self._tasks.items():
            if terminal_count <= self._max_terminal_tasks:
                break
            if t.state in terminal:
                to_remove.append(tid)
                terminal_count -= 1
        for tid in to_remove:
            self._tasks.pop(tid, None)

    @property
    def task_count(self) -> int:
        """Total number of tasks."""
        return len(self._tasks)

    def list_tasks(self, state: TaskState | None = None) -> list[Task]:
        """List tasks, optionally filtered by state."""
        if state is None:
            return list(self._tasks.values())
        return [t for t in self._tasks.values() if t.state == state]
