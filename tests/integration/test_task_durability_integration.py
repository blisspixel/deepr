"""Integration tests for task durability across disconnections."""

import pytest
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from deepr.mcp.state.task_durability import (
    TaskDurabilityManager,
    DurableTask,
    TaskStatus,
)
from deepr.mcp.state.async_dispatcher import AsyncTaskDispatcher, DispatchResult


class TestTaskDurabilityIntegration:
    """Integration tests for task durability with simulated disconnections."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_task_survives_simulated_disconnection(self):
        """Test that a task survives a simulated disconnection and can be resumed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "durability.db"

            # Phase 1: Start a task and make progress
            manager1 = TaskDurabilityManager(db_path=db_path)

            task = await manager1.create_task(
                job_id="research_job_123",
                description="Deep research on quantum computing",
                checkpoint={
                    "phase": 1,
                    "progress": 0.0,
                    "findings": [],
                    "sources_checked": 0,
                },
            )

            # Simulate work progress
            await manager1.update_progress(
                task.id,
                progress=0.3,
                checkpoint={
                    "phase": 1,
                    "progress": 0.3,
                    "findings": ["Finding 1", "Finding 2"],
                    "sources_checked": 5,
                },
            )

            await manager1.update_progress(
                task.id,
                progress=0.6,
                checkpoint={
                    "phase": 2,
                    "progress": 0.6,
                    "findings": ["Finding 1", "Finding 2", "Finding 3"],
                    "sources_checked": 12,
                },
            )

            # Simulate disconnection (pause task, close manager)
            await manager1.pause_task(task.id)
            manager1.close()

            # Phase 2: Simulate reconnection with new manager instance
            manager2 = TaskDurabilityManager(db_path=db_path)

            # Find recoverable tasks
            recoverable = await manager2.get_recoverable_tasks("research_job_123")

            assert len(recoverable) == 1
            recovered_task = recoverable[0]

            assert recovered_task.id == task.id
            assert recovered_task.status == TaskStatus.PAUSED
            assert recovered_task.checkpoint["phase"] == 2
            assert recovered_task.checkpoint["sources_checked"] == 12
            assert len(recovered_task.checkpoint["findings"]) == 3

            # Resume the task
            resumed = await manager2.resume_task(recovered_task.id)

            assert resumed.status == TaskStatus.RUNNING

            # Continue work
            await manager2.update_progress(
                resumed.id,
                progress=0.9,
                checkpoint={
                    "phase": 3,
                    "progress": 0.9,
                    "findings": recovered_task.checkpoint["findings"] + ["Finding 4"],
                    "sources_checked": 18,
                },
            )

            # Complete the task
            completed = await manager2.complete_task(
                resumed.id,
                final_checkpoint={
                    "report": "Final research report",
                    "total_findings": 4,
                    "sources_used": 18,
                },
            )

            assert completed.status == TaskStatus.COMPLETED
            assert completed.checkpoint["total_findings"] == 4

            manager2.close()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_tasks_survive_disconnection(self):
        """Test that multiple tasks for a job survive disconnection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "durability.db"

            # Create multiple tasks
            manager1 = TaskDurabilityManager(db_path=db_path)

            task1 = await manager1.create_task(
                "job_multi",
                "Task 1: Web search",
                {"query": "topic A", "results": []},
            )
            task2 = await manager1.create_task(
                "job_multi",
                "Task 2: Academic search",
                {"query": "topic A academic", "results": []},
            )
            task3 = await manager1.create_task(
                "job_multi",
                "Task 3: Synthesis",
                {"sources": [], "draft": ""},
            )

            # Progress on tasks
            await manager1.update_progress(task1.id, 0.5, {"results": ["r1", "r2"]})
            await manager1.update_progress(task2.id, 0.3, {"results": ["a1"]})
            # Task 3 not started yet

            # Pause all for disconnection
            await manager1.pause_task(task1.id)
            await manager1.pause_task(task2.id)
            # Task 3 stays pending

            manager1.close()

            # Reconnect
            manager2 = TaskDurabilityManager(db_path=db_path)

            recoverable = await manager2.get_recoverable_tasks("job_multi")

            # Should recover paused tasks
            assert len(recoverable) == 2

            # Verify checkpoints preserved
            task1_recovered = next(t for t in recoverable if "Web search" in t.description)
            assert len(task1_recovered.checkpoint["results"]) == 2

            manager2.close()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_checkpoint_integrity_across_restarts(self):
        """Test that complex checkpoint data maintains integrity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "durability.db"

            # Create task with complex checkpoint
            complex_checkpoint = {
                "phase": 2,
                "findings": [
                    {"text": "Finding 1", "confidence": 0.9, "sources": ["url1", "url2"]},
                    {"text": "Finding 2", "confidence": 0.7, "sources": ["url3"]},
                ],
                "hypotheses": {
                    "h1": {"text": "Hypothesis 1", "status": "active"},
                    "h2": {"text": "Hypothesis 2", "status": "invalidated"},
                },
                "metadata": {
                    "start_time": datetime.now(timezone.utc).isoformat(),
                    "model": "o4-mini",
                    "token_usage": 5000,
                },
                "nested": {
                    "level1": {
                        "level2": {
                            "data": [1, 2, 3, 4, 5],
                        },
                    },
                },
            }

            manager1 = TaskDurabilityManager(db_path=db_path)
            task = await manager1.create_task("job1", "Complex task", complex_checkpoint)
            await manager1.pause_task(task.id)
            manager1.close()

            # Recover and verify
            manager2 = TaskDurabilityManager(db_path=db_path)
            recovered = await manager2.get_task(task.id)

            # Verify complex nested structure preserved
            assert recovered.checkpoint["phase"] == 2
            assert len(recovered.checkpoint["findings"]) == 2
            assert recovered.checkpoint["findings"][0]["confidence"] == 0.9
            assert recovered.checkpoint["hypotheses"]["h1"]["status"] == "active"
            assert recovered.checkpoint["nested"]["level1"]["level2"]["data"] == [1, 2, 3, 4, 5]

            manager2.close()


class TestAsyncDispatcherIntegration:
    """Integration tests for async task dispatcher."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_parallel_task_dispatch(self):
        """Test dispatching multiple tasks in parallel."""
        dispatcher = AsyncTaskDispatcher()

        async def mock_task(task_id: str, delay: float) -> dict:
            await asyncio.sleep(delay)
            return {"task_id": task_id, "completed": True}

        # Create coroutines at dispatch time
        tasks = [
            {"id": "task1", "coro": mock_task("task1", 0.1)},
            {"id": "task2", "coro": mock_task("task2", 0.1)},
            {"id": "task3", "coro": mock_task("task3", 0.1)},
        ]

        start_time = asyncio.get_event_loop().time()

        results = await dispatcher.dispatch(tasks)

        end_time = asyncio.get_event_loop().time()
        elapsed = end_time - start_time

        # Should complete faster than sequential (3 * 0.1 = 0.3s)
        assert elapsed < 0.25  # Allow some overhead

        assert isinstance(results, DispatchResult)
        assert len(results.tasks) == 3
        for task_id, task in results.tasks.items():
            if task.result:
                assert task.result["completed"] is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_dispatch_with_dependencies(self):
        """Test task dispatch with dependencies."""
        dispatcher = AsyncTaskDispatcher()

        execution_order = []

        async def tracked_task(name: str) -> dict:
            execution_order.append(name)
            await asyncio.sleep(0.05)
            return {"name": name}

        # Create coroutines at dispatch time
        tasks = [
            {"id": "A", "coro": tracked_task("A")},
            {"id": "B", "coro": tracked_task("B")},
            {"id": "C", "coro": tracked_task("C")},
        ]

        # B depends on A, C depends on B
        dependencies = {
            "B": ["A"],
            "C": ["B"],
        }

        results = await dispatcher.dispatch_with_dependencies(tasks, dependencies)

        # All tasks should complete
        assert results.success_count == 3

        # A should complete before B, B before C
        assert execution_order.index("A") < execution_order.index("B")
        assert execution_order.index("B") < execution_order.index("C")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_dispatch_with_progress_callback(self):
        """Test task dispatch with progress tracking."""
        dispatcher = AsyncTaskDispatcher()

        progress_updates = []

        async def on_progress(task_id: str, progress: float):
            progress_updates.append({
                "task_id": task_id,
                "progress": progress,
            })

        async def mock_task_with_progress(task_id: str) -> dict:
            return {"task_id": task_id, "done": True}

        tasks = [
            {"id": "task1", "coro": mock_task_with_progress("task1")},
            {"id": "task2", "coro": mock_task_with_progress("task2")},
        ]

        await dispatcher.dispatch(tasks, on_progress=on_progress)

        # Should have received progress updates (start and end for each task)
        assert len(progress_updates) > 0


class TestDurabilityWithDispatcher:
    """Integration tests combining durability and dispatcher."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_durable_parallel_tasks(self):
        """Test durable tasks running in parallel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "durability.db"

            manager = TaskDurabilityManager(db_path=db_path)
            dispatcher = AsyncTaskDispatcher()

            # Create durable tasks
            task1 = await manager.create_task("job1", "Parallel Task 1", {"data": []})
            task2 = await manager.create_task("job1", "Parallel Task 2", {"data": []})

            async def execute_with_durability(task: DurableTask, mgr: TaskDurabilityManager) -> dict:
                # Update progress
                await mgr.update_progress(
                    task.id,
                    progress=0.5,
                    checkpoint={"data": ["partial"]},
                )

                await asyncio.sleep(0.05)

                # Complete
                return {"task_id": task.id, "result": "done"}

            tasks = [
                {"id": task1.id, "coro": execute_with_durability(task1, manager)},
                {"id": task2.id, "coro": execute_with_durability(task2, manager)},
            ]

            results = await dispatcher.dispatch(tasks)

            # Both should complete
            assert results.success_count == 2

            # Verify durability recorded progress
            t1 = await manager.get_task(task1.id)
            t2 = await manager.get_task(task2.id)

            assert t1.progress == 0.5
            assert t2.progress == 0.5

            manager.close()
