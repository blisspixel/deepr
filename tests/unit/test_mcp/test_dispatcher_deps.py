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

from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher, DispatchStatus


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


@pytest.mark.asyncio
async def test_duplicate_task_ids_are_rejected_and_coroutines_closed():
    async def work() -> str:
        return "done"

    first = work()
    second = work()
    dispatcher = AsyncTaskDispatcher()
    try:
        with pytest.raises(ValueError, match="Duplicate task id"):
            await dispatcher.dispatch(
                [
                    {"id": "same", "coro": first},
                    {"id": "same", "coro": second},
                ]
            )
    finally:
        first.close()
        second.close()

    assert first.cr_frame is None
    assert second.cr_frame is None


@pytest.mark.asyncio
async def test_missing_coroutine_is_rejected_and_other_coroutines_are_closed():
    async def work() -> str:
        return "done"

    operation = work()
    dispatcher = AsyncTaskDispatcher()
    try:
        with pytest.raises(ValueError, match="coroutine"):
            await dispatcher.dispatch(
                [
                    {"id": "missing"},
                    {"id": "valid", "coro": operation},
                ]
            )
    finally:
        operation.close()

    assert operation.cr_frame is None


@pytest.mark.asyncio
async def test_unknown_dependency_is_rejected_before_execution():
    ran = False

    async def work() -> str:
        nonlocal ran
        ran = True
        return "done"

    operation = work()
    dispatcher = AsyncTaskDispatcher()
    try:
        with pytest.raises(ValueError, match="unknown task"):
            await dispatcher.dispatch_with_dependencies(
                tasks=[{"id": "A", "coro": operation}],
                dependencies={"A": ["missing"]},
            )
    finally:
        operation.close()

    assert operation.cr_frame is None
    assert ran is False


@pytest.mark.asyncio
async def test_dependency_cycle_is_rejected_without_timeout_wait():
    async def work() -> str:
        return "done"

    first = work()
    second = work()
    dispatcher = AsyncTaskDispatcher()
    try:
        with pytest.raises(ValueError, match="cycle"):
            await asyncio.wait_for(
                dispatcher.dispatch_with_dependencies(
                    tasks=[{"id": "A", "coro": first}, {"id": "B", "coro": second}],
                    dependencies={"A": ["B"], "B": ["A"]},
                ),
                timeout=1.0,
            )
    finally:
        first.close()
        second.close()

    assert first.cr_frame is None
    assert second.cr_frame is None


@pytest.mark.asyncio
async def test_cancel_all_stops_running_coroutine():
    started = asyncio.Event()
    stopped = asyncio.Event()
    side_effect_happened = False

    async def work() -> str:
        nonlocal side_effect_happened
        started.set()
        try:
            await asyncio.Event().wait()
            side_effect_happened = True
            return "done"
        finally:
            stopped.set()

    dispatcher = AsyncTaskDispatcher(max_concurrent=1)
    dispatch_task = asyncio.create_task(dispatcher.dispatch([{"id": "A", "coro": work()}]))
    await asyncio.wait_for(started.wait(), timeout=1.0)

    await dispatcher.cancel_all()
    result = await asyncio.wait_for(dispatch_task, timeout=1.0)

    assert stopped.is_set()
    assert side_effect_happened is False
    assert result.tasks["A"].status is DispatchStatus.CANCELLED
    assert result.cancelled_count == 1


@pytest.mark.asyncio
async def test_cancel_all_stops_same_id_tasks_from_concurrent_batches():
    started = [asyncio.Event(), asyncio.Event()]
    stopped = [asyncio.Event(), asyncio.Event()]

    async def work(index: int) -> str:
        started[index].set()
        try:
            await asyncio.Event().wait()
            return "done"
        finally:
            stopped[index].set()

    dispatcher = AsyncTaskDispatcher(max_concurrent=2)
    batches = [
        asyncio.create_task(dispatcher.dispatch([{"id": "shared", "coro": work(index)}]))
        for index in range(2)
    ]
    await asyncio.gather(*(asyncio.wait_for(event.wait(), timeout=1.0) for event in started))

    await dispatcher.cancel_all()
    results = await asyncio.wait_for(asyncio.gather(*batches), timeout=1.0)

    assert all(event.is_set() for event in stopped)
    assert all(result.tasks["shared"].status is DispatchStatus.CANCELLED for result in results)
    assert dispatcher.get_active_count() == 0


@pytest.mark.parametrize("max_concurrent", [0, -1, True, 1.5])
def test_invalid_concurrency_is_rejected(max_concurrent):
    with pytest.raises(ValueError, match="max_concurrent"):
        AsyncTaskDispatcher(max_concurrent=max_concurrent)
