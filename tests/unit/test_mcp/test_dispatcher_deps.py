"""Regression test: AsyncTaskDispatcher must not deadlock when the
dependency graph requires waiting for a task that itself hasn't acquired
the concurrency slot yet.

Previously ``run_task`` did ``async with self._semaphore`` *before*
awaiting dependencies, so with max_concurrent=N and N tasks all
depending on an N+1th task, all N slots were held by waiters and the
dependency could never run, creating a classic deadlock.
"""

from __future__ import annotations

import asyncio

import pytest

from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher


@pytest.mark.asyncio
async def test_no_deadlock_when_many_tasks_depend_on_single_root():
    """B, C, and D all depend on A. With max_concurrent=2, the previous
    implementation could acquire both slots for B/C/D before A runs,
    deadlocking. After the fix, dependency waits happen outside the
    semaphore so A can always acquire a slot."""

    async def work() -> str:
        await asyncio.sleep(0.01)
        return "done"

    dispatcher = AsyncTaskDispatcher(max_concurrent=2)
    tasks = [
        {"id": "A", "coro": work()},
        {"id": "B", "coro": work()},
        {"id": "C", "coro": work()},
        {"id": "D", "coro": work()},
    ]
    dependencies = {
        "A": [],
        "B": ["A"],
        "C": ["A"],
        "D": ["A"],
    }

    # With the old code this would hang forever. With the fix it
    # completes well within the timeout.
    result = await asyncio.wait_for(
        dispatcher.dispatch_with_dependencies(tasks=tasks, dependencies=dependencies),
        timeout=5.0,
    )

    # All four tasks completed.
    assert len(result.tasks) == 4
    for task_id in ("A", "B", "C", "D"):
        assert result.tasks[task_id].status.value == "completed"


@pytest.mark.asyncio
async def test_failed_dependency_closes_blocked_coroutine():
    """Blocked coroutines should be closed when their dependency fails."""

    async def fail() -> str:
        raise RuntimeError("boom")

    async def work() -> str:
        return "done"

    dispatcher = AsyncTaskDispatcher(max_concurrent=2)
    tasks = [
        {"id": "A", "coro": fail()},
        {"id": "B", "coro": work()},
    ]
    dependencies = {"A": [], "B": ["A"]}

    result = await dispatcher.dispatch_with_dependencies(tasks=tasks, dependencies=dependencies)

    assert result.tasks["A"].status.value == "failed"
    assert result.tasks["B"].status.value == "failed"
    assert result.tasks["B"].error == "Dependency A failed"
    assert result.tasks["B"].coro is None
