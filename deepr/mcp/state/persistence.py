"""
SQLite-backed job persistence for the MCP server.

Ensures research jobs survive server restarts. On startup, incomplete
jobs are marked as FAILED with a note about the restart.

Storage location: data/mcp_jobs.db (alongside reports/)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .job_manager import JobState, JobPhase, JobPlan, JobBeliefs


# Default database path (relative to project root)
DEFAULT_DB_PATH = Path("data/mcp_jobs.db")


class JobPersistence:
    """SQLite-backed persistence for MCP job state.

    Thread-safe via sqlite3's built-in serialization. Uses WAL mode
    for better concurrent read performance.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                phase TEXT NOT NULL DEFAULT 'queued',
                progress REAL NOT NULL DEFAULT 0.0,
                cost_so_far REAL NOT NULL DEFAULT 0.0,
                estimated_remaining TEXT,
                error TEXT,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS job_plans (
                job_id TEXT PRIMARY KEY REFERENCES jobs(job_id) ON DELETE CASCADE,
                goal TEXT NOT NULL DEFAULT '',
                steps_json TEXT NOT NULL DEFAULT '[]',
                estimated_cost REAL NOT NULL DEFAULT 0.0,
                estimated_time TEXT NOT NULL DEFAULT 'unknown',
                model TEXT NOT NULL DEFAULT 'o4-mini'
            );

            CREATE TABLE IF NOT EXISTS job_beliefs (
                job_id TEXT PRIMARY KEY REFERENCES jobs(job_id) ON DELETE CASCADE,
                beliefs_json TEXT NOT NULL DEFAULT '[]',
                sources_json TEXT NOT NULL DEFAULT '[]',
                confidence REAL NOT NULL DEFAULT 0.0
            );
        """)
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # CRUD operations
    # ------------------------------------------------------------------ #

    def save_job(self, state: JobState, plan: Optional[JobPlan] = None, beliefs: Optional[JobBeliefs] = None) -> None:
        """Save or update a job and its related data."""
        now = datetime.now().isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO jobs
               (job_id, phase, progress, cost_so_far, estimated_remaining, error, started_at, updated_at, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                state.job_id,
                state.phase.value,
                state.progress,
                state.cost_so_far,
                state.estimated_remaining,
                state.error,
                state.started_at.isoformat(),
                now,
                json.dumps(state.metadata, default=str),
            ),
        )

        if plan:
            self._conn.execute(
                """INSERT OR REPLACE INTO job_plans
                   (job_id, goal, steps_json, estimated_cost, estimated_time, model)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    plan.job_id,
                    plan.goal,
                    json.dumps(plan.steps, default=str),
                    plan.estimated_cost,
                    plan.estimated_time,
                    plan.model,
                ),
            )

        if beliefs:
            self._conn.execute(
                """INSERT OR REPLACE INTO job_beliefs
                   (job_id, beliefs_json, sources_json, confidence)
                   VALUES (?, ?, ?, ?)""",
                (
                    beliefs.job_id,
                    json.dumps(beliefs.beliefs, default=str),
                    json.dumps(beliefs.sources, default=str),
                    beliefs.confidence,
                ),
            )

        self._conn.commit()

    def load_job(self, job_id: str) -> Optional[tuple[JobState, Optional[JobPlan], Optional[JobBeliefs]]]:
        """Load a job and its related data."""
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if not row:
            return None

        state = self._row_to_state(row)

        plan_row = self._conn.execute(
            "SELECT * FROM job_plans WHERE job_id = ?", (job_id,)
        ).fetchone()
        plan = self._row_to_plan(plan_row) if plan_row else None

        beliefs_row = self._conn.execute(
            "SELECT * FROM job_beliefs WHERE job_id = ?", (job_id,)
        ).fetchone()
        beliefs = self._row_to_beliefs(beliefs_row) if beliefs_row else None

        return state, plan, beliefs

    def list_jobs(self, phase: Optional[str] = None) -> list[JobState]:
        """List all jobs, optionally filtered by phase."""
        if phase:
            rows = self._conn.execute(
                "SELECT * FROM jobs WHERE phase = ? ORDER BY updated_at DESC",
                (phase,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC"
            ).fetchall()
        return [self._row_to_state(r) for r in rows]

    def delete_job(self, job_id: str) -> bool:
        """Delete a job and its related data (cascades)."""
        cursor = self._conn.execute(
            "DELETE FROM jobs WHERE job_id = ?", (job_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def mark_incomplete_as_failed(self) -> int:
        """Mark all non-terminal jobs as FAILED on restart.

        Returns the number of jobs updated.
        """
        terminal = ("completed", "failed", "cancelled")
        placeholders = ",".join("?" for _ in terminal)
        now = datetime.now().isoformat()

        cursor = self._conn.execute(
            f"""UPDATE jobs
                SET phase = 'failed',
                    error = 'Server restarted while job was in progress',
                    updated_at = ?
                WHERE phase NOT IN ({placeholders})""",
            (now, *terminal),
        )
        self._conn.commit()
        return cursor.rowcount

    # ------------------------------------------------------------------ #
    # Row mappers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _row_to_state(row: tuple) -> JobState:
        """Convert a database row to a JobState."""
        (job_id, phase, progress, cost_so_far, estimated_remaining,
         error, started_at, updated_at, metadata_json) = row
        return JobState(
            job_id=job_id,
            phase=JobPhase(phase),
            progress=progress,
            cost_so_far=cost_so_far,
            estimated_remaining=estimated_remaining,
            error=error,
            started_at=datetime.fromisoformat(started_at),
            updated_at=datetime.fromisoformat(updated_at),
            metadata=json.loads(metadata_json) if metadata_json else {},
        )

    @staticmethod
    def _row_to_plan(row: tuple) -> JobPlan:
        """Convert a database row to a JobPlan."""
        (job_id, goal, steps_json, estimated_cost, estimated_time, model) = row
        return JobPlan(
            job_id=job_id,
            goal=goal,
            steps=json.loads(steps_json) if steps_json else [],
            estimated_cost=estimated_cost,
            estimated_time=estimated_time,
            model=model,
        )

    @staticmethod
    def _row_to_beliefs(row: tuple) -> JobBeliefs:
        """Convert a database row to a JobBeliefs."""
        (job_id, beliefs_json, sources_json, confidence) = row
        return JobBeliefs(
            job_id=job_id,
            beliefs=json.loads(beliefs_json) if beliefs_json else [],
            sources=json.loads(sources_json) if sources_json else [],
            confidence=confidence,
        )

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
