"""SQLite-based queue for local development."""

import sqlite3
import json
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
from .base import QueueBackend, ResearchJob, JobStatus, QueueError


class SQLiteQueue(QueueBackend):
    """SQLite-based queue implementation for local development."""

    def __init__(self, db_path: str = "queue/research_queue.db"):
        """
        Initialize SQLite queue.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_queue (
                id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER DEFAULT 5,

                submitted_at DATETIME NOT NULL,
                started_at DATETIME,
                completed_at DATETIME,

                documents TEXT,  -- JSON array
                enable_web_search INTEGER DEFAULT 1,
                enable_code_interpreter INTEGER DEFAULT 1,
                cost_limit REAL,

                provider_job_id TEXT,
                worker_id TEXT,
                attempts INTEGER DEFAULT 0,
                last_error TEXT,

                report_paths TEXT,  -- JSON object
                cost REAL,
                tokens_used INTEGER,

                tenant_id TEXT,
                workspace_id TEXT,
                submitted_by TEXT,
                tags TEXT,  -- JSON array
                callback_url TEXT,
                metadata TEXT  -- JSON object
            )
        """)

        # Indexes for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status_priority
            ON research_queue(status, priority DESC, submitted_at ASC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tenant
            ON research_queue(tenant_id, status)
        """)

        conn.commit()
        conn.close()

    def _job_to_dict(self, job: ResearchJob) -> Dict[str, Any]:
        """Convert job to dictionary for storage."""
        return {
            "id": job.id,
            "prompt": job.prompt,
            "model": job.model,
            "status": job.status.value,
            "priority": job.priority,
            "submitted_at": job.submitted_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "documents": json.dumps(job.documents),
            "enable_web_search": 1 if job.enable_web_search else 0,
            "enable_code_interpreter": 1 if job.enable_code_interpreter else 0,
            "cost_limit": job.cost_limit,
            "provider_job_id": job.provider_job_id,
            "worker_id": job.worker_id,
            "attempts": job.attempts,
            "last_error": job.last_error,
            "report_paths": json.dumps(job.report_paths),
            "cost": job.cost,
            "tokens_used": job.tokens_used,
            "tenant_id": job.tenant_id,
            "workspace_id": job.workspace_id,
            "submitted_by": job.submitted_by,
            "tags": json.dumps(job.tags),
            "callback_url": job.callback_url,
            "metadata": json.dumps(job.metadata),
        }

    def _dict_to_job(self, row: Dict[str, Any]) -> ResearchJob:
        """Convert database row to job object."""
        return ResearchJob(
            id=row["id"],
            prompt=row["prompt"],
            model=row["model"],
            status=JobStatus(row["status"]),
            priority=row["priority"],
            submitted_at=datetime.fromisoformat(row["submitted_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            documents=json.loads(row["documents"]) if row["documents"] else [],
            enable_web_search=bool(row["enable_web_search"]),
            enable_code_interpreter=bool(row["enable_code_interpreter"]),
            cost_limit=row["cost_limit"],
            provider_job_id=row["provider_job_id"],
            worker_id=row["worker_id"],
            attempts=row["attempts"],
            last_error=row["last_error"],
            report_paths=json.loads(row["report_paths"]) if row["report_paths"] else {},
            cost=row["cost"],
            tokens_used=row["tokens_used"],
            tenant_id=row["tenant_id"],
            workspace_id=row["workspace_id"],
            submitted_by=row["submitted_by"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            callback_url=row["callback_url"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    async def enqueue(self, job: ResearchJob) -> str:
        """Add job to SQLite queue."""
        await asyncio.to_thread(self._enqueue_sync, job)
        return job.id

    def _enqueue_sync(self, job: ResearchJob):
        """Synchronous enqueue operation."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        job_dict = self._job_to_dict(job)

        columns = ", ".join(job_dict.keys())
        placeholders = ", ".join("?" * len(job_dict))

        cursor.execute(
            f"INSERT INTO research_queue ({columns}) VALUES ({placeholders})",
            tuple(job_dict.values()),
        )

        conn.commit()
        conn.close()

    async def dequeue(self, worker_id: str) -> Optional[ResearchJob]:
        """Get next job from queue (highest priority, oldest first)."""
        return await asyncio.to_thread(self._dequeue_sync, worker_id)

    def _dequeue_sync(self, worker_id: str) -> Optional[ResearchJob]:
        """Synchronous dequeue operation."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Select job with highest priority
        cursor.execute("""
            SELECT * FROM research_queue
            WHERE status = 'queued'
            ORDER BY priority DESC, submitted_at ASC
            LIMIT 1
        """)

        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        job_id = row["id"]

        # Claim the job (atomic update)
        cursor.execute("""
            UPDATE research_queue
            SET status = 'processing',
                worker_id = ?,
                started_at = ?,
                attempts = attempts + 1
            WHERE id = ? AND status = 'queued'
        """, (worker_id, datetime.utcnow().isoformat(), job_id))

        if cursor.rowcount == 0:
            # Job was claimed by another worker
            conn.close()
            return None

        conn.commit()

        # Fetch updated job
        cursor.execute("SELECT * FROM research_queue WHERE id = ?", (job_id,))
        row = cursor.fetchone()

        conn.close()

        return self._dict_to_job(dict(row))

    async def get_job(self, job_id: str) -> Optional[ResearchJob]:
        """Get job by ID."""
        return await asyncio.to_thread(self._get_job_sync, job_id)

    def _get_job_sync(self, job_id: str) -> Optional[ResearchJob]:
        """Synchronous get job operation. Supports partial ID matching."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Try exact match first
        cursor.execute("SELECT * FROM research_queue WHERE id = ?", (job_id,))
        row = cursor.fetchone()

        # If no exact match and ID is short (< 36 chars), try prefix match
        if not row and len(job_id) < 36:
            cursor.execute("SELECT * FROM research_queue WHERE id LIKE ?", (f"{job_id}%",))
            rows = cursor.fetchall()

            # If multiple matches, take first one (ambiguous but functional)
            if rows:
                row = rows[0]

        conn.close()

        if not row:
            return None

        return self._dict_to_job(dict(row))

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error: Optional[str] = None,
        provider_job_id: Optional[str] = None,
    ) -> bool:
        """Update job status."""
        return await asyncio.to_thread(
            self._update_status_sync, job_id, status, error, provider_job_id
        )

    def _update_status_sync(
        self, job_id: str, status: JobStatus, error: Optional[str], provider_job_id: Optional[str]
    ) -> bool:
        """Synchronous status update."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        updates = ["status = ?"]
        values = [status.value]

        if error:
            updates.append("last_error = ?")
            values.append(error)

        if provider_job_id:
            updates.append("provider_job_id = ?")
            values.append(provider_job_id)

        if status == JobStatus.COMPLETED:
            updates.append("completed_at = ?")
            values.append(datetime.utcnow().isoformat())

        values.append(job_id)

        cursor.execute(
            f"UPDATE research_queue SET {', '.join(updates)} WHERE id = ?", values
        )

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return success

    async def update_results(
        self,
        job_id: str,
        report_paths: Dict[str, str],
        cost: Optional[float] = None,
        tokens_used: Optional[int] = None,
    ) -> bool:
        """Update job results."""
        return await asyncio.to_thread(
            self._update_results_sync, job_id, report_paths, cost, tokens_used
        )

    def _update_results_sync(
        self, job_id: str, report_paths: Dict[str, str], cost: Optional[float], tokens_used: Optional[int]
    ) -> bool:
        """Synchronous results update."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE research_queue
            SET report_paths = ?, cost = ?, tokens_used = ?
            WHERE id = ?
        """, (json.dumps(report_paths), cost, tokens_used, job_id))

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return success

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ResearchJob]:
        """List jobs with filtering."""
        return await asyncio.to_thread(
            self._list_jobs_sync, status, tenant_id, limit, offset
        )

    def _list_jobs_sync(
        self, status: Optional[JobStatus], tenant_id: Optional[str], limit: int, offset: int
    ) -> List[ResearchJob]:
        """Synchronous list jobs."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM research_queue WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status.value)

        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)

        query += " ORDER BY submitted_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        conn.close()

        return [self._dict_to_job(dict(row)) for row in rows]

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job."""
        return await self.update_status(job_id, JobStatus.CANCELLED)

    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return await asyncio.to_thread(self._get_stats_sync)

    def _get_stats_sync(self) -> Dict[str, Any]:
        """Synchronous stats calculation."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM research_queue
            GROUP BY status
        """)

        stats = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) FROM research_queue")
        total = cursor.fetchone()[0]

        conn.close()

        return {
            "total": total,
            "by_status": stats,
            "queued": stats.get("queued", 0),
            "processing": stats.get("processing", 0),
            "completed": stats.get("completed", 0),
            "failed": stats.get("failed", 0),
        }

    async def cleanup_old_jobs(self, days: int = 30) -> int:
        """Remove old completed/failed jobs."""
        return await asyncio.to_thread(self._cleanup_sync, days)

    def _cleanup_sync(self, days: int) -> int:
        """Synchronous cleanup."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        cursor.execute("""
            DELETE FROM research_queue
            WHERE status IN ('completed', 'failed', 'cancelled')
            AND completed_at < ?
        """, (cutoff,))

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted
