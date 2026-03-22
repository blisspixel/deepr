"""Tests for bounded parallel fan-out and cost_checker integration."""

import asyncio

import pytest

from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher, DispatchStatus


@pytest.mark.asyncio
async def test_concurrency_bounded():
    """Dispatcher should never exceed max_concurrent tasks running simultaneously."""
    max_concurrent = 2
    dispatcher = AsyncTaskDispatcher(max_concurrent=max_concurrent)

    peak_concurrent = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    async def tracked_task():
        nonlocal peak_concurrent, current_concurrent
        async with lock:
            current_concurrent += 1
            peak_concurrent = max(peak_concurrent, current_concurrent)
        await asyncio.sleep(0.05)
        async with lock:
            current_concurrent -= 1
        return "done"

    tasks = [{"id": f"t{i}", "coro": tracked_task()} for i in range(6)]
    result = await dispatcher.dispatch(tasks)

    assert peak_concurrent <= max_concurrent
    assert result.success_count == 6


@pytest.mark.asyncio
async def test_cost_checker_cancels_tasks():
    """Tasks should be cancelled when cost_checker returns False."""
    dispatcher = AsyncTaskDispatcher(max_concurrent=10)

    call_count = 0

    def checker(task_id: str) -> tuple[bool, str]:
        nonlocal call_count
        call_count += 1
        # Allow first 2 tasks, block the rest
        if call_count <= 2:
            return True, "OK"
        return False, "Budget exhausted"

    async def work():
        return "result"

    tasks = [{"id": f"t{i}", "coro": work()} for i in range(5)]
    result = await dispatcher.dispatch(tasks, cost_checker=checker)

    assert result.success_count == 2
    assert result.cancelled_count == 3
    # Cancelled tasks should have error messages
    for task_id, task in result.tasks.items():
        if task.status == DispatchStatus.CANCELLED:
            assert "Budget exhausted" in task.error


@pytest.mark.asyncio
async def test_cost_checker_none_allows_all():
    """Without cost_checker, all tasks should proceed."""
    dispatcher = AsyncTaskDispatcher(max_concurrent=10)

    async def work():
        return "ok"

    tasks = [{"id": f"t{i}", "coro": work()} for i in range(3)]
    result = await dispatcher.dispatch(tasks, cost_checker=None)

    assert result.success_count == 3
    assert result.cancelled_count == 0


@pytest.mark.asyncio
async def test_dispatch_with_dependencies_respects_concurrency():
    """dispatch_with_dependencies should respect max_concurrent."""
    dispatcher = AsyncTaskDispatcher(max_concurrent=2)

    execution_order = []

    async def tracked(task_id):
        execution_order.append(("start", task_id))
        await asyncio.sleep(0.02)
        execution_order.append(("end", task_id))
        return task_id

    tasks = [
        {"id": "a", "coro": tracked("a")},
        {"id": "b", "coro": tracked("b")},
        {"id": "c", "coro": tracked("c")},
    ]
    deps = {"a": [], "b": [], "c": ["a", "b"]}
    result = await dispatcher.dispatch_with_dependencies(tasks, deps)

    assert result.success_count == 3
    # c should start after a and b end
    a_end = next(i for i, (action, tid) in enumerate(execution_order) if action == "end" and tid == "a")
    b_end = next(i for i, (action, tid) in enumerate(execution_order) if action == "end" and tid == "b")
    c_start = next(i for i, (action, tid) in enumerate(execution_order) if action == "start" and tid == "c")
    assert c_start > a_end
    assert c_start > b_end
