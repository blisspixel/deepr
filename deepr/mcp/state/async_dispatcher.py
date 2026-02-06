"""Async task dispatcher for parallel execution.

Dispatches multiple tasks in parallel with dependency management
and progress reporting.

Usage:
    from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher

    dispatcher = AsyncTaskDispatcher()

    # Dispatch independent tasks
    results = await dispatcher.dispatch(
        tasks=[
            {"id": "t1", "coro": fetch_data("url1")},
            {"id": "t2", "coro": fetch_data("url2")},
        ],
        on_progress=lambda t, p: print(f"{t}: {p:.0%}")
    )

    # Dispatch with dependencies
    results = await dispatcher.dispatch_with_dependencies(
        tasks=[
            {"id": "t1", "coro": step1, "depends_on": []},
            {"id": "t2", "coro": step2, "depends_on": ["t1"]},
            {"id": "t3", "coro": step3, "depends_on": ["t1"]},
            {"id": "t4", "coro": step4, "depends_on": ["t2", "t3"]},
        ],
        dependencies={"t2": ["t1"], "t3": ["t1"], "t4": ["t2", "t3"]}
    )
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Coroutine, Dict, List, Optional

from deepr.core.constants import MAX_CONCURRENT_TASKS


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class DispatchStatus(Enum):
    """Status of a dispatched task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"  # Waiting on dependencies


@dataclass
class DispatchedTask:
    """A task being dispatched."""

    id: str
    coro: Optional[Coroutine] = None
    status: DispatchStatus = DispatchStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    depends_on: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "result": self.result if self.status == DispatchStatus.COMPLETED else None,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "depends_on": self.depends_on,
            "duration_ms": self.duration_ms,
        }

    @property
    def duration_ms(self) -> Optional[float]:
        """Get task duration in milliseconds."""
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds() * 1000


@dataclass
class DispatchResult:
    """Result of a dispatch operation."""

    tasks: Dict[str, DispatchedTask]
    total_duration_ms: float
    success_count: int
    failure_count: int
    cancelled_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "total_duration_ms": self.total_duration_ms,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "cancelled_count": self.cancelled_count,
            "all_succeeded": self.failure_count == 0 and self.cancelled_count == 0,
        }

    def get_result(self, task_id: str) -> Any:
        """Get result for a specific task."""
        if task_id in self.tasks:
            return self.tasks[task_id].result
        return None

    def get_error(self, task_id: str) -> Optional[str]:
        """Get error for a specific task."""
        if task_id in self.tasks:
            return self.tasks[task_id].error
        return None


# Type for progress callback
ProgressCallback = Callable[[str, float], Awaitable[None]]


class AsyncTaskDispatcher:
    """Dispatches tasks in parallel with concurrency control.

    Features:
    - Concurrent execution with configurable limit
    - Dependency management
    - Progress reporting
    - Error handling and propagation

    Attributes:
        max_concurrent: Maximum concurrent tasks
    """

    def __init__(
        self,
        max_concurrent: Optional[int] = None,
    ):
        """Initialize the dispatcher.

        Args:
            max_concurrent: Maximum concurrent tasks (default from constants)
        """
        self.max_concurrent = max_concurrent or MAX_CONCURRENT_TASKS
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._active_tasks: Dict[str, DispatchedTask] = {}
        self._cancel_event = asyncio.Event()

    async def dispatch(
        self,
        tasks: List[Dict[str, Any]],
        on_progress: Optional[ProgressCallback] = None,
        timeout: Optional[float] = None,
    ) -> DispatchResult:
        """Dispatch independent tasks in parallel.

        Args:
            tasks: List of task dicts with 'id' and 'coro' keys
            on_progress: Optional progress callback
            timeout: Optional overall timeout in seconds

        Returns:
            DispatchResult with all task results
        """
        start_time = _utc_now()
        self._cancel_event.clear()

        # Create DispatchedTask objects
        dispatched = {}
        for task_spec in tasks:
            task = DispatchedTask(
                id=task_spec["id"],
                coro=task_spec.get("coro"),
                metadata=task_spec.get("metadata", {}),
            )
            dispatched[task.id] = task
            self._active_tasks[task.id] = task

        # Execute all tasks concurrently
        async def run_task(task: DispatchedTask):
            async with self._semaphore:
                if self._cancel_event.is_set():
                    task.status = DispatchStatus.CANCELLED
                    return

                task.status = DispatchStatus.RUNNING
                task.started_at = _utc_now()

                if on_progress:
                    await on_progress(task.id, 0.0)

                try:
                    if task.coro:
                        task.result = await task.coro
                    task.status = DispatchStatus.COMPLETED
                except asyncio.CancelledError:
                    task.status = DispatchStatus.CANCELLED
                except Exception as e:
                    task.status = DispatchStatus.FAILED
                    task.error = str(e)
                finally:
                    task.completed_at = _utc_now()

                    if on_progress:
                        progress = 1.0 if task.status == DispatchStatus.COMPLETED else 0.5
                        await on_progress(task.id, progress)

        # Run all tasks
        aws = [run_task(task) for task in dispatched.values()]

        if timeout:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*aws, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                # Cancel remaining tasks
                self._cancel_event.set()
                for task in dispatched.values():
                    if task.status == DispatchStatus.RUNNING:
                        task.status = DispatchStatus.CANCELLED
                        task.error = "Timeout exceeded"
        else:
            await asyncio.gather(*aws, return_exceptions=True)

        # Calculate statistics
        end_time = _utc_now()
        total_duration = (end_time - start_time).total_seconds() * 1000

        success_count = sum(1 for t in dispatched.values() if t.status == DispatchStatus.COMPLETED)
        failure_count = sum(1 for t in dispatched.values() if t.status == DispatchStatus.FAILED)
        cancelled_count = sum(1 for t in dispatched.values() if t.status == DispatchStatus.CANCELLED)

        # Clean up
        for task_id in dispatched:
            self._active_tasks.pop(task_id, None)

        return DispatchResult(
            tasks=dispatched,
            total_duration_ms=total_duration,
            success_count=success_count,
            failure_count=failure_count,
            cancelled_count=cancelled_count,
        )

    async def dispatch_with_dependencies(
        self,
        tasks: List[Dict[str, Any]],
        dependencies: Dict[str, List[str]],
        on_progress: Optional[ProgressCallback] = None,
        timeout: Optional[float] = None,
    ) -> DispatchResult:
        """Dispatch tasks with dependency management.

        Tasks execute in order respecting dependencies.

        Args:
            tasks: List of task dicts with 'id' and 'coro' keys
            dependencies: Dict mapping task_id to list of dependency task_ids
            on_progress: Optional progress callback
            timeout: Optional overall timeout in seconds

        Returns:
            DispatchResult with all task results
        """
        start_time = _utc_now()
        self._cancel_event.clear()

        # Create DispatchedTask objects
        dispatched: Dict[str, DispatchedTask] = {}
        for task_spec in tasks:
            task_id = task_spec["id"]
            task = DispatchedTask(
                id=task_id,
                coro=task_spec.get("coro"),
                depends_on=dependencies.get(task_id, []),
                status=DispatchStatus.BLOCKED if dependencies.get(task_id) else DispatchStatus.PENDING,
                metadata=task_spec.get("metadata", {}),
            )
            dispatched[task_id] = task
            self._active_tasks[task_id] = task

        # Track completed tasks
        completed_tasks: set = set()
        completion_events: Dict[str, asyncio.Event] = {task_id: asyncio.Event() for task_id in dispatched}

        async def wait_for_dependencies(task: DispatchedTask):
            """Wait for all dependencies to complete."""
            for dep_id in task.depends_on:
                if dep_id in completion_events:
                    await completion_events[dep_id].wait()

                # Check if dependency failed
                if dep_id in dispatched:
                    dep_task = dispatched[dep_id]
                    if dep_task.status == DispatchStatus.FAILED:
                        task.status = DispatchStatus.FAILED
                        task.error = f"Dependency {dep_id} failed"
                        return False
                    elif dep_task.status == DispatchStatus.CANCELLED:
                        task.status = DispatchStatus.CANCELLED
                        task.error = f"Dependency {dep_id} cancelled"
                        return False

            return True

        async def run_task(task: DispatchedTask):
            async with self._semaphore:
                if self._cancel_event.is_set():
                    task.status = DispatchStatus.CANCELLED
                    completion_events[task.id].set()
                    return

                # Wait for dependencies
                if task.depends_on:
                    deps_ok = await wait_for_dependencies(task)
                    if not deps_ok:
                        completion_events[task.id].set()
                        return

                task.status = DispatchStatus.RUNNING
                task.started_at = _utc_now()

                if on_progress:
                    await on_progress(task.id, 0.0)

                try:
                    if task.coro:
                        task.result = await task.coro
                    task.status = DispatchStatus.COMPLETED
                    completed_tasks.add(task.id)
                except asyncio.CancelledError:
                    task.status = DispatchStatus.CANCELLED
                except Exception as e:
                    task.status = DispatchStatus.FAILED
                    task.error = str(e)
                finally:
                    task.completed_at = _utc_now()
                    completion_events[task.id].set()

                    if on_progress:
                        progress = 1.0 if task.status == DispatchStatus.COMPLETED else 0.5
                        await on_progress(task.id, progress)

        # Run all tasks (dependency waiting happens inside run_task)
        aws = [run_task(task) for task in dispatched.values()]

        if timeout:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*aws, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                self._cancel_event.set()
                # Signal all events to unblock waiting tasks
                for event in completion_events.values():
                    event.set()
                for task in dispatched.values():
                    if task.status in {DispatchStatus.RUNNING, DispatchStatus.BLOCKED}:
                        task.status = DispatchStatus.CANCELLED
                        task.error = "Timeout exceeded"
        else:
            await asyncio.gather(*aws, return_exceptions=True)

        # Calculate statistics
        end_time = _utc_now()
        total_duration = (end_time - start_time).total_seconds() * 1000

        success_count = sum(1 for t in dispatched.values() if t.status == DispatchStatus.COMPLETED)
        failure_count = sum(1 for t in dispatched.values() if t.status == DispatchStatus.FAILED)
        cancelled_count = sum(1 for t in dispatched.values() if t.status == DispatchStatus.CANCELLED)

        # Clean up
        for task_id in dispatched:
            self._active_tasks.pop(task_id, None)

        return DispatchResult(
            tasks=dispatched,
            total_duration_ms=total_duration,
            success_count=success_count,
            failure_count=failure_count,
            cancelled_count=cancelled_count,
        )

    async def cancel_all(self):
        """Cancel all active tasks."""
        self._cancel_event.set()
        for task in self._active_tasks.values():
            if task.status in {DispatchStatus.RUNNING, DispatchStatus.PENDING, DispatchStatus.BLOCKED}:
                task.status = DispatchStatus.CANCELLED

    def get_active_tasks(self) -> List[DispatchedTask]:
        """Get all currently active tasks."""
        return list(self._active_tasks.values())

    def get_active_count(self) -> int:
        """Get count of currently active tasks."""
        return len(self._active_tasks)
