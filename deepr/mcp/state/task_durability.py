"""Task durability for MCP - persistence and reconnection support.

Ensures research tasks survive disconnections and server restarts
with checkpoint-based recovery.

Usage:
    from deepr.mcp.state.task_durability import TaskDurabilityManager

    manager = TaskDurabilityManager()

    # Create a durable task
    task = await manager.create_task(
        job_id="job123",
        description="Research quantum computing",
        checkpoint={"phase": 1, "findings": [...]}
    )

    # Update progress
    task = await manager.update_progress(
        task_id=task.id,
        progress=0.5,
        checkpoint={"phase": 2, "findings": [...]}
    )

    # On disconnect
    task = await manager.pause_task(task.id)

    # On reconnect
    tasks = await manager.get_recoverable_tasks("job123")
    task = await manager.resume_task(task.id)
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path
from enum import Enum

from deepr.core.constants import TASK_CHECKPOINT_INTERVAL, TASK_DEFAULT_TIMEOUT


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


# Default database path
DEFAULT_DB_PATH = Path("data/durable_tasks.db")


class TaskStatus(Enum):
    """Status of a durable task."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"  # Disconnected but recoverable
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskCheckpoint:
    """A checkpoint for task recovery."""
    checkpoint_id: str
    task_id: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "task_id": self.task_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class DurableTask:
    """A task that survives disconnections."""
    id: str
    job_id: str
    description: str
    status: TaskStatus
    progress: float
    created_at: datetime
    updated_at: datetime
    checkpoint: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = TASK_DEFAULT_TIMEOUT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "description": self.description,
            "status": self.status.value,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "checkpoint": self.checkpoint,
            "error": self.error,
            "metadata": self.metadata,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "DurableTask":
        """Create from database row."""
        (id, job_id, description, status, progress, created_at,
         updated_at, checkpoint_json, error, metadata_json, timeout) = row

        return cls(
            id=id,
            job_id=job_id,
            description=description,
            status=TaskStatus(status),
            progress=progress,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
            checkpoint=json.loads(checkpoint_json) if checkpoint_json else None,
            error=error,
            metadata=json.loads(metadata_json) if metadata_json else {},
            timeout_seconds=timeout,
        )

    @property
    def is_recoverable(self) -> bool:
        """Check if task can be recovered."""
        return self.status in {TaskStatus.PAUSED, TaskStatus.RUNNING}

    @property
    def is_terminal(self) -> bool:
        """Check if task is in terminal state."""
        return self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }


class TaskDurabilityManager:
    """Manages durable tasks with checkpoint-based recovery.

    Provides:
    - Task persistence across restarts
    - Checkpoint-based recovery
    - Progress tracking
    - Timeout handling

    Attributes:
        db_path: Path to SQLite database
        checkpoint_interval: Seconds between auto-checkpoints
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        checkpoint_interval: Optional[int] = None,
    ):
        """Initialize the durability manager.

        Args:
            db_path: Path to database (default: data/durable_tasks.db)
            checkpoint_interval: Seconds between checkpoints (default from constants)
        """
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_interval = checkpoint_interval or TASK_CHECKPOINT_INTERVAL

        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self):
        """Create database tables."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS durable_tasks (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                progress REAL NOT NULL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                checkpoint_json TEXT,
                error TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                timeout_seconds INTEGER NOT NULL DEFAULT 600
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_job ON durable_tasks(job_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON durable_tasks(status);

            CREATE TABLE IF NOT EXISTS task_checkpoints (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                data_json TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES durable_tasks(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_checkpoints_task ON task_checkpoints(task_id);
        """)
        self._conn.commit()

    async def create_task(
        self,
        job_id: str,
        description: str,
        checkpoint: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> DurableTask:
        """Create a new durable task.

        Args:
            job_id: Associated job ID
            description: Task description
            checkpoint: Initial checkpoint data
            metadata: Additional metadata
            timeout_seconds: Task timeout

        Returns:
            Created DurableTask
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now = _utc_now()

        task = DurableTask(
            id=task_id,
            job_id=job_id,
            description=description,
            status=TaskStatus.PENDING,
            progress=0.0,
            created_at=now,
            updated_at=now,
            checkpoint=checkpoint,
            metadata=metadata or {},
            timeout_seconds=timeout_seconds or TASK_DEFAULT_TIMEOUT,
        )

        self._conn.execute(
            """INSERT INTO durable_tasks
               (id, job_id, description, status, progress, created_at, updated_at,
                checkpoint_json, metadata_json, timeout_seconds)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id,
                task.job_id,
                task.description,
                task.status.value,
                task.progress,
                task.created_at.isoformat(),
                task.updated_at.isoformat(),
                json.dumps(task.checkpoint) if task.checkpoint else None,
                json.dumps(task.metadata),
                task.timeout_seconds,
            )
        )

        # Save initial checkpoint if provided
        if checkpoint:
            await self._save_checkpoint(task_id, checkpoint)

        self._conn.commit()
        return task

    async def update_progress(
        self,
        task_id: str,
        progress: float,
        checkpoint: Optional[Dict[str, Any]] = None,
        status: Optional[TaskStatus] = None,
    ) -> Optional[DurableTask]:
        """Update task progress and optionally save checkpoint.

        Args:
            task_id: Task ID
            progress: Progress percentage (0.0 to 1.0)
            checkpoint: Optional checkpoint data to save
            status: Optional new status

        Returns:
            Updated DurableTask or None if not found
        """
        task = await self.get_task(task_id)
        if not task:
            return None

        now = _utc_now()
        task.progress = min(1.0, max(0.0, progress))
        task.updated_at = now

        if status:
            task.status = status
        elif task.status == TaskStatus.PENDING:
            task.status = TaskStatus.RUNNING

        if checkpoint:
            task.checkpoint = checkpoint
            await self._save_checkpoint(task_id, checkpoint)

        self._conn.execute(
            """UPDATE durable_tasks
               SET progress = ?, status = ?, updated_at = ?, checkpoint_json = ?
               WHERE id = ?""",
            (
                task.progress,
                task.status.value,
                task.updated_at.isoformat(),
                json.dumps(task.checkpoint) if task.checkpoint else None,
                task_id,
            )
        )
        self._conn.commit()

        return task

    async def pause_task(self, task_id: str) -> Optional[DurableTask]:
        """Pause a task (on disconnection).

        Args:
            task_id: Task ID

        Returns:
            Paused DurableTask or None if not found
        """
        task = await self.get_task(task_id)
        if not task:
            return None

        if task.is_terminal:
            return task  # Can't pause terminal tasks

        task.status = TaskStatus.PAUSED
        task.updated_at = _utc_now()

        self._conn.execute(
            """UPDATE durable_tasks
               SET status = ?, updated_at = ?
               WHERE id = ?""",
            (task.status.value, task.updated_at.isoformat(), task_id)
        )
        self._conn.commit()

        return task

    async def resume_task(self, task_id: str) -> Optional[DurableTask]:
        """Resume a paused task.

        Args:
            task_id: Task ID

        Returns:
            Resumed DurableTask or None if not found/not resumable
        """
        task = await self.get_task(task_id)
        if not task:
            return None

        if not task.is_recoverable:
            return None

        task.status = TaskStatus.RUNNING
        task.updated_at = _utc_now()

        self._conn.execute(
            """UPDATE durable_tasks
               SET status = ?, updated_at = ?
               WHERE id = ?""",
            (task.status.value, task.updated_at.isoformat(), task_id)
        )
        self._conn.commit()

        return task

    async def complete_task(
        self,
        task_id: str,
        final_checkpoint: Optional[Dict[str, Any]] = None,
    ) -> Optional[DurableTask]:
        """Mark a task as completed.

        Args:
            task_id: Task ID
            final_checkpoint: Final checkpoint data

        Returns:
            Completed DurableTask or None if not found
        """
        return await self.update_progress(
            task_id=task_id,
            progress=1.0,
            checkpoint=final_checkpoint,
            status=TaskStatus.COMPLETED,
        )

    async def fail_task(
        self,
        task_id: str,
        error: str,
        checkpoint: Optional[Dict[str, Any]] = None,
    ) -> Optional[DurableTask]:
        """Mark a task as failed.

        Args:
            task_id: Task ID
            error: Error message
            checkpoint: Optional checkpoint at failure

        Returns:
            Failed DurableTask or None if not found
        """
        task = await self.get_task(task_id)
        if not task:
            return None

        task.status = TaskStatus.FAILED
        task.error = error
        task.updated_at = _utc_now()

        if checkpoint:
            task.checkpoint = checkpoint
            await self._save_checkpoint(task_id, checkpoint)

        self._conn.execute(
            """UPDATE durable_tasks
               SET status = ?, error = ?, updated_at = ?, checkpoint_json = ?
               WHERE id = ?""",
            (
                task.status.value,
                task.error,
                task.updated_at.isoformat(),
                json.dumps(task.checkpoint) if task.checkpoint else None,
                task_id,
            )
        )
        self._conn.commit()

        return task

    async def cancel_task(self, task_id: str) -> Optional[DurableTask]:
        """Cancel a task.

        Args:
            task_id: Task ID

        Returns:
            Cancelled DurableTask or None if not found
        """
        task = await self.get_task(task_id)
        if not task:
            return None

        if task.is_terminal:
            return task

        task.status = TaskStatus.CANCELLED
        task.updated_at = _utc_now()

        self._conn.execute(
            """UPDATE durable_tasks
               SET status = ?, updated_at = ?
               WHERE id = ?""",
            (task.status.value, task.updated_at.isoformat(), task_id)
        )
        self._conn.commit()

        return task

    async def get_task(self, task_id: str) -> Optional[DurableTask]:
        """Get a task by ID.

        Args:
            task_id: Task ID

        Returns:
            DurableTask or None if not found
        """
        row = self._conn.execute(
            """SELECT id, job_id, description, status, progress, created_at,
                      updated_at, checkpoint_json, error, metadata_json, timeout_seconds
               FROM durable_tasks WHERE id = ?""",
            (task_id,)
        ).fetchone()

        if not row:
            return None

        return DurableTask.from_row(row)

    async def get_recoverable_tasks(self, job_id: str) -> List[DurableTask]:
        """Get all recoverable tasks for a job.

        Args:
            job_id: Job ID

        Returns:
            List of recoverable DurableTask objects
        """
        rows = self._conn.execute(
            """SELECT id, job_id, description, status, progress, created_at,
                      updated_at, checkpoint_json, error, metadata_json, timeout_seconds
               FROM durable_tasks
               WHERE job_id = ? AND status IN ('paused', 'running')
               ORDER BY created_at""",
            (job_id,)
        ).fetchall()

        return [DurableTask.from_row(row) for row in rows]

    async def get_tasks_by_job(
        self,
        job_id: str,
        status: Optional[TaskStatus] = None,
    ) -> List[DurableTask]:
        """Get all tasks for a job.

        Args:
            job_id: Job ID
            status: Optional status filter

        Returns:
            List of DurableTask objects
        """
        if status:
            rows = self._conn.execute(
                """SELECT id, job_id, description, status, progress, created_at,
                          updated_at, checkpoint_json, error, metadata_json, timeout_seconds
                   FROM durable_tasks
                   WHERE job_id = ? AND status = ?
                   ORDER BY created_at""",
                (job_id, status.value)
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT id, job_id, description, status, progress, created_at,
                          updated_at, checkpoint_json, error, metadata_json, timeout_seconds
                   FROM durable_tasks
                   WHERE job_id = ?
                   ORDER BY created_at""",
                (job_id,)
            ).fetchall()

        return [DurableTask.from_row(row) for row in rows]

    async def get_checkpoint_history(
        self,
        task_id: str,
        limit: int = 10,
    ) -> List[TaskCheckpoint]:
        """Get checkpoint history for a task.

        Args:
            task_id: Task ID
            limit: Maximum checkpoints to return

        Returns:
            List of TaskCheckpoint objects (newest first)
        """
        rows = self._conn.execute(
            """SELECT id, task_id, data_json, timestamp
               FROM task_checkpoints
               WHERE task_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (task_id, limit)
        ).fetchall()

        checkpoints = []
        for id, task_id, data_json, timestamp in rows:
            checkpoints.append(TaskCheckpoint(
                checkpoint_id=id,
                task_id=task_id,
                data=json.loads(data_json),
                timestamp=datetime.fromisoformat(timestamp),
            ))

        return checkpoints

    async def cleanup_old_tasks(
        self,
        days: int = 7,
        terminal_only: bool = True,
    ) -> int:
        """Clean up old tasks.

        Args:
            days: Delete tasks older than this many days
            terminal_only: Only delete terminal tasks

        Returns:
            Number of tasks deleted
        """
        cutoff = _utc_now()
        cutoff_str = cutoff.isoformat()

        if terminal_only:
            cursor = self._conn.execute(
                """DELETE FROM durable_tasks
                   WHERE updated_at < datetime(?, '-' || ? || ' days')
                     AND status IN ('completed', 'failed', 'cancelled')""",
                (cutoff_str, days)
            )
        else:
            cursor = self._conn.execute(
                """DELETE FROM durable_tasks
                   WHERE updated_at < datetime(?, '-' || ? || ' days')""",
                (cutoff_str, days)
            )

        self._conn.commit()
        return cursor.rowcount

    async def mark_stale_tasks_failed(self) -> int:
        """Mark tasks that have been running too long as failed.

        Returns:
            Number of tasks marked failed
        """
        now = _utc_now()

        # Find running tasks that have exceeded timeout
        rows = self._conn.execute(
            """SELECT id, timeout_seconds, updated_at
               FROM durable_tasks
               WHERE status = 'running'"""
        ).fetchall()

        count = 0
        for task_id, timeout, updated_at in rows:
            task_updated = datetime.fromisoformat(updated_at)
            if task_updated.tzinfo is None:
                task_updated = task_updated.replace(tzinfo=timezone.utc)

            elapsed = (now - task_updated).total_seconds()
            if elapsed > timeout:
                await self.fail_task(task_id, "Task timeout exceeded")
                count += 1

        return count

    async def _save_checkpoint(
        self,
        task_id: str,
        data: Dict[str, Any],
    ) -> TaskCheckpoint:
        """Save a checkpoint.

        Args:
            task_id: Task ID
            data: Checkpoint data

        Returns:
            Saved TaskCheckpoint
        """
        checkpoint = TaskCheckpoint(
            checkpoint_id=f"cp_{uuid.uuid4().hex[:12]}",
            task_id=task_id,
            data=data,
        )

        self._conn.execute(
            """INSERT INTO task_checkpoints
               (id, task_id, data_json, timestamp)
               VALUES (?, ?, ?, ?)""",
            (
                checkpoint.checkpoint_id,
                checkpoint.task_id,
                json.dumps(checkpoint.data),
                checkpoint.timestamp.isoformat(),
            )
        )

        return checkpoint

    def close(self):
        """Close database connection."""
        self._conn.close()
