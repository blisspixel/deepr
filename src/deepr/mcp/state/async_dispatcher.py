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
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from deepr.core.constants import MAX_CONCURRENT_TASKS


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


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
    coro: Coroutine[Any, Any, Any] | None = None
    status: DispatchStatus = DispatchStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    depends_on: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def close_unstarted_coro(self) -> None:
        """Close a coroutine that will never be awaited."""
        if self.coro is not None:
            self.coro.close()
            self.coro = None

    def to_dict(self) -> dict[str, Any]:
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
    def duration_ms(self) -> float | None:
        """Get task duration in milliseconds."""
        if not self.started_at or not self.completed_at:
            return None
        return (self.completed_at - self.started_at).total_seconds() * 1000


@dataclass
class DispatchResult:
    """Result of a dispatch operation."""

    tasks: dict[str, DispatchedTask]
    total_duration_ms: float
    success_count: int
    failure_count: int
    cancelled_count: int

    def to_dict(self) -> dict[str, Any]:
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

    def get_error(self, task_id: str) -> str | None:
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
        max_concurrent: int | None = None,
    ):
        """Initialize the dispatcher.

        Args:
            max_concurrent: Maximum concurrent tasks (default from constants)
        """
        self.max_concurrent = max_concurrent or MAX_CONCURRENT_TASKS
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._active_tasks: dict[str, DispatchedTask] = {}
        self._cancel_event = asyncio.Event()

    async def _report_progress(
        self,
        task: DispatchedTask,
        on_progress: ProgressCallback | None,
        progress: float,
    ) -> None:
        if on_progress:
            await on_progress(task.id, progress)

    async def _await_task_coro(self, task: DispatchedTask) -> None:
        if task.coro is None:
            return
        coro = task.coro
        task.coro = None
        task.result = await coro

    def _cancel_task(self, task: DispatchedTask, error: str | None = None) -> None:
        task.status = DispatchStatus.CANCELLED
        if error and task.error is None:
            task.error = error
        task.close_unstarted_coro()
        task.completed_at = task.completed_at or _utc_now()

    def _fail_task(self, task: DispatchedTask, error: Exception) -> None:
        task.status = DispatchStatus.FAILED
        task.error = str(error)

    def _cancel_pending_task(self, task: DispatchedTask) -> None:
        if task.status in {DispatchStatus.PENDING, DispatchStatus.BLOCKED}:
            self._cancel_task(task)
        else:
            task.completed_at = task.completed_at or _utc_now()

    def _check_cost_or_cancel(
        self,
        task: DispatchedTask,
        cost_checker: Callable[[str], tuple[bool, str]] | None,
    ) -> bool:
        if cost_checker is None:
            return True
        allowed, reason = cost_checker(task.id)
        if allowed:
            return True
        self._cancel_task(task, f"Cost check failed: {reason}")
        return False

    async def _execute_task_body(
        self,
        task: DispatchedTask,
        on_progress: ProgressCallback | None,
        on_success: Callable[[], None] | None = None,
        fatal_exception_types: tuple[type[Exception], ...] = (),
    ) -> None:
        task.status = DispatchStatus.RUNNING
        task.started_at = _utc_now()
        await self._report_progress(task, on_progress, 0.0)

        try:
            await self._await_task_coro(task)
        except asyncio.CancelledError:
            self._cancel_task(task)
        except Exception as e:
            self._fail_task(task, e)
            if isinstance(e, fatal_exception_types):
                raise
        else:
            task.status = DispatchStatus.COMPLETED
            if on_success:
                on_success()
        finally:
            task.completed_at = task.completed_at or _utc_now()
            progress = 1.0 if task.status == DispatchStatus.COMPLETED else 0.5
            await self._report_progress(task, on_progress, progress)

    def _timeout_remaining(self, dispatched: dict[str, DispatchedTask]) -> None:
        self._cancel_event.set()
        for task in dispatched.values():
            if task.status in {
                DispatchStatus.PENDING,
                DispatchStatus.BLOCKED,
                DispatchStatus.CANCELLED,
                DispatchStatus.RUNNING,
            }:
                self._cancel_task(task, task.error or "Timeout exceeded")

    async def _await_independent_tasks(
        self,
        awaitables: list[asyncio.Task[None]],
        dispatched: dict[str, DispatchedTask],
        *,
        timeout: float | None,
        fatal_exception_types: tuple[type[Exception], ...],
    ) -> None:
        try:
            gathered = asyncio.gather(*awaitables, return_exceptions=not fatal_exception_types)
            if timeout:
                await asyncio.wait_for(gathered, timeout=timeout)
            else:
                await gathered
        except TimeoutError:
            self._timeout_remaining(dispatched)
        except Exception:
            for awaitable in awaitables:
                if not awaitable.done():
                    awaitable.cancel()
            await asyncio.gather(*awaitables, return_exceptions=True)
            for task_id in dispatched:
                self._active_tasks.pop(task_id, None)
            raise

    async def dispatch(
        self,
        tasks: list[dict[str, Any]],
        on_progress: ProgressCallback | None = None,
        timeout: float | None = None,
        cost_checker: Callable[[str], tuple[bool, str]] | None = None,
        fatal_exception_types: tuple[type[Exception], ...] = (),
    ) -> DispatchResult:
        """Dispatch independent tasks in parallel.

        Args:
            tasks: List of task dicts with 'id' and 'coro' keys
            on_progress: Optional progress callback
            timeout: Optional overall timeout in seconds
            cost_checker: Optional guard called before each task starts.
                Returns (allowed, reason). If not allowed, task is CANCELLED.
            fatal_exception_types: Exceptions that cancel sibling work and propagate.

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
        async def run_task(task: DispatchedTask) -> None:
            try:
                async with self._semaphore:
                    if self._cancel_event.is_set():
                        self._cancel_task(task)
                        return

                    if not self._check_cost_or_cancel(task, cost_checker):
                        return

                    await self._execute_task_body(
                        task,
                        on_progress,
                        fatal_exception_types=fatal_exception_types,
                    )
            except asyncio.CancelledError:
                self._cancel_pending_task(task)

        # Run all tasks
        aws = [asyncio.create_task(run_task(task)) for task in dispatched.values()]
        await self._await_independent_tasks(
            aws,
            dispatched,
            timeout=timeout,
            fatal_exception_types=fatal_exception_types,
        )

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
        tasks: list[dict[str, Any]],
        dependencies: dict[str, list[str]],
        on_progress: ProgressCallback | None = None,
        timeout: float | None = None,
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
        dispatched: dict[str, DispatchedTask] = {}
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
        completed_tasks: set[str] = set()
        completion_events: dict[str, asyncio.Event] = {task_id: asyncio.Event() for task_id in dispatched}

        async def wait_for_dependencies(task: DispatchedTask) -> bool:
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

        async def run_task(task: DispatchedTask) -> None:
            try:
                # Wait for dependencies before acquiring the concurrency slot.
                # Holding the semaphore while awaiting a dependency that itself
                # needs a slot deadlocks any chain of length > max_concurrent
                # (e.g. max=2 with B -> A, C -> A, D -> A: B and C hold both
                # slots, A can never acquire one, B and C wait forever).
                if self._cancel_event.is_set():
                    self._cancel_task(task)
                    completion_events[task.id].set()
                    return

                if task.depends_on:
                    deps_ok = await wait_for_dependencies(task)
                    if not deps_ok:
                        task.close_unstarted_coro()
                        task.completed_at = _utc_now()
                        completion_events[task.id].set()
                        return

                async with self._semaphore:
                    if self._cancel_event.is_set():
                        self._cancel_task(task)
                        completion_events[task.id].set()
                        return

                    try:
                        await self._execute_task_body(
                            task,
                            on_progress,
                            on_success=lambda: completed_tasks.add(task.id),
                        )
                    finally:
                        completion_events[task.id].set()
            except asyncio.CancelledError:
                self._cancel_pending_task(task)
                completion_events[task.id].set()

        # Run all tasks (dependency waiting happens inside run_task)
        aws = [run_task(task) for task in dispatched.values()]

        if timeout:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*aws, return_exceptions=True),
                    timeout=timeout,
                )
            except TimeoutError:
                self._timeout_remaining(dispatched)
                # Signal all events to unblock waiting tasks
                for event in completion_events.values():
                    event.set()
                for task_id in dispatched:
                    completion_events[task_id].set()
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

    async def cancel_all(self) -> None:
        """Cancel all active tasks."""
        self._cancel_event.set()
        for task in self._active_tasks.values():
            if task.status in {DispatchStatus.RUNNING, DispatchStatus.PENDING, DispatchStatus.BLOCKED}:
                if task.status in {DispatchStatus.PENDING, DispatchStatus.BLOCKED}:
                    task.close_unstarted_coro()
                task.status = DispatchStatus.CANCELLED

    def get_active_tasks(self) -> list[DispatchedTask]:
        """Get all currently active tasks."""
        return list(self._active_tasks.values())

    def get_active_count(self) -> int:
        """Get count of currently active tasks."""
        return len(self._active_tasks)
