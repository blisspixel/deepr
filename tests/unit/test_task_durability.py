"""Unit tests for task durability."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from deepr.mcp.state.task_durability import (
    DurableTask,
    TaskDurabilityManager,
    TaskStatus,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_durability.db"
        yield db_path


@pytest.fixture
def manager(temp_db):
    """Create a TaskDurabilityManager instance."""
    m = TaskDurabilityManager(db_path=temp_db)
    yield m
    m.close()


class TestTaskCreation:
    """Tests for creating durable tasks."""

    @pytest.mark.asyncio
    async def test_create_task(self, manager):
        """Test creating a durable task."""
        task = await manager.create_task(
            job_id="job123",
            description="Research quantum computing",
            checkpoint={"phase": 1, "progress": 0.0},
        )

        assert isinstance(task, DurableTask)
        assert task.job_id == "job123"
        assert task.description == "Research quantum computing"
        assert task.status == TaskStatus.PENDING
        assert task.checkpoint["phase"] == 1

    @pytest.mark.asyncio
    async def test_create_task_generates_id(self, manager):
        """Test that task creation generates unique IDs."""
        task1 = await manager.create_task("job1", "Task 1", {})
        task2 = await manager.create_task("job1", "Task 2", {})

        assert task1.id != task2.id

    @pytest.mark.asyncio
    async def test_create_task_persists(self, manager):
        """Test that created task is persisted."""
        task = await manager.create_task("job1", "Persistent task", {"data": "test"})

        # Retrieve the task
        retrieved = await manager.get_task(task.id)

        assert retrieved is not None
        assert retrieved.description == "Persistent task"
        assert retrieved.checkpoint["data"] == "test"


class TestTaskProgress:
    """Tests for task progress updates."""

    @pytest.mark.asyncio
    async def test_update_progress(self, manager):
        """Test updating task progress."""
        task = await manager.create_task("job1", "Task", {"progress": 0.0})

        updated = await manager.update_progress(
            task.id,
            progress=0.5,
            checkpoint={"progress": 0.5, "items_processed": 50},
        )

        assert updated.progress == 0.5
        assert updated.checkpoint["items_processed"] == 50
        assert updated.status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_update_progress_preserves_checkpoint(self, manager):
        """Test that progress update preserves checkpoint data."""
        task = await manager.create_task("job1", "Task", {"initial": "data", "progress": 0.0})

        await manager.update_progress(task.id, progress=0.3, checkpoint={"progress": 0.3, "new_field": "value"})

        retrieved = await manager.get_task(task.id)

        assert retrieved.checkpoint["new_field"] == "value"


class TestTaskPauseResume:
    """Tests for pausing and resuming tasks."""

    @pytest.mark.asyncio
    async def test_pause_task(self, manager):
        """Test pausing a task."""
        task = await manager.create_task("job1", "Task", {})
        await manager.update_progress(task.id, 0.3, {"progress": 0.3})

        paused = await manager.pause_task(task.id)

        assert paused.status == TaskStatus.PAUSED

    @pytest.mark.asyncio
    async def test_resume_task(self, manager):
        """Test resuming a paused task."""
        task = await manager.create_task("job1", "Task", {"progress": 0.5})
        await manager.pause_task(task.id)

        resumed = await manager.resume_task(task.id)

        assert resumed.status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_resume_preserves_checkpoint(self, manager):
        """Test that resume preserves checkpoint."""
        task = await manager.create_task("job1", "Task", {"phase": 2, "items": [1, 2, 3]})
        await manager.pause_task(task.id)

        resumed = await manager.resume_task(task.id)

        assert resumed.checkpoint["phase"] == 2
        assert resumed.checkpoint["items"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_cannot_resume_completed_task(self, manager):
        """Test that completed tasks cannot be resumed."""
        task = await manager.create_task("job1", "Task", {})
        await manager.complete_task(task.id, {"result": "done"})

        resumed = await manager.resume_task(task.id)

        # Should not resume a completed task
        assert resumed is None or resumed.status == TaskStatus.COMPLETED


class TestTaskCompletion:
    """Tests for task completion."""

    @pytest.mark.asyncio
    async def test_complete_task(self, manager):
        """Test completing a task."""
        task = await manager.create_task("job1", "Task", {})

        completed = await manager.complete_task(task.id, final_checkpoint={"output": "research results"})

        assert completed.status == TaskStatus.COMPLETED
        assert completed.checkpoint["output"] == "research results"

    @pytest.mark.asyncio
    async def test_fail_task(self, manager):
        """Test marking a task as failed."""
        task = await manager.create_task("job1", "Task", {})

        failed = await manager.fail_task(task.id, error="Connection timeout")

        assert failed.status == TaskStatus.FAILED
        assert failed.error == "Connection timeout"


class TestRecoverableTasks:
    """Tests for recoverable task listing."""

    @pytest.mark.asyncio
    async def test_get_recoverable_tasks(self, manager):
        """Test getting recoverable tasks for a job."""
        # Create tasks in various states
        task1 = await manager.create_task("job1", "Task 1", {})
        await manager.pause_task(task1.id)

        task2 = await manager.create_task("job1", "Task 2", {})
        await manager.update_progress(task2.id, 0.5, {})
        await manager.pause_task(task2.id)

        task3 = await manager.create_task("job1", "Task 3", {})
        await manager.complete_task(task3.id, {})

        # Different job
        task4 = await manager.create_task("job2", "Task 4", {})
        await manager.pause_task(task4.id)

        recoverable = await manager.get_recoverable_tasks("job1")

        # Should only get paused tasks for job1
        assert len(recoverable) == 2
        for task in recoverable:
            assert task.job_id == "job1"
            assert task.status == TaskStatus.PAUSED

    @pytest.mark.asyncio
    async def test_no_recoverable_tasks(self, manager):
        """Test when no recoverable tasks exist."""
        recoverable = await manager.get_recoverable_tasks("nonexistent_job")

        assert len(recoverable) == 0


class TestDurableTask:
    """Tests for DurableTask dataclass."""

    def test_task_to_dict(self):
        """Test DurableTask serialization."""
        now = datetime.now(timezone.utc)
        task = DurableTask(
            id="task123",
            job_id="job456",
            description="Test task",
            status=TaskStatus.RUNNING,
            progress=0.5,
            checkpoint={"phase": 2},
            created_at=now,
            updated_at=now,
        )

        data = task.to_dict()

        assert data["id"] == "task123"
        assert data["job_id"] == "job456"
        assert data["status"] == "running"
        assert data["progress"] == 0.5
        assert "created_at" in data


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_status_values(self):
        """Test TaskStatus enum values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.PAUSED.value == "paused"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"


class TestCheckpointPersistence:
    """Tests for checkpoint persistence across operations."""

    @pytest.mark.asyncio
    async def test_checkpoint_survives_manager_restart(self, temp_db):
        """Test that checkpoints survive manager restart."""
        # Create manager and task
        manager1 = TaskDurabilityManager(db_path=temp_db)
        task = await manager1.create_task("job1", "Task", {"important_data": [1, 2, 3], "state": "processing"})
        await manager1.update_progress(
            task.id,
            0.7,
            {
                "important_data": [1, 2, 3],
                "state": "almost_done",
                "items_processed": 70,
            },
        )
        await manager1.pause_task(task.id)
        manager1.close()

        # Create new manager instance
        manager2 = TaskDurabilityManager(db_path=temp_db)
        retrieved = await manager2.get_task(task.id)
        manager2.close()

        assert retrieved is not None
        assert retrieved.checkpoint["items_processed"] == 70
        assert retrieved.checkpoint["state"] == "almost_done"
        assert retrieved.status == TaskStatus.PAUSED
