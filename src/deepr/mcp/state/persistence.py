"""
SQLite-backed job persistence for the MCP server.

Ensures research jobs survive server restarts. On startup, incomplete
jobs are marked as FAILED with a note about the restart.

Storage location: data/mcp_jobs.db (alongside reports/)
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from deepr.config import runtime_data_path

from .job_manager import HypothesisRecord, JobBeliefs, JobPhase, JobPlan, JobState, TemporalFindingRecord


def _default_mcp_jobs_db() -> Path:
    return runtime_data_path("mcp_jobs.db")


DEFAULT_DB_PATH = _default_mcp_jobs_db()


class JobPersistence:
    """SQLite-backed persistence for MCP job state.

    Thread-safe via sqlite3's built-in serialization. Uses WAL mode
    for better concurrent read performance.
    """

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or _default_mcp_jobs_db()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
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
                metadata_json TEXT NOT NULL DEFAULT '{}',
                owner_id TEXT,
                active_tasks_json TEXT NOT NULL DEFAULT '[]'
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
                confidence REAL NOT NULL DEFAULT 0.0,
                temporal_findings_json TEXT NOT NULL DEFAULT '[]',
                hypothesis_history_json TEXT NOT NULL DEFAULT '[]'
            );
        """)
        columns = {str(row[1]) for row in self._conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "owner_id" not in columns:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN owner_id TEXT")
        if "active_tasks_json" not in columns:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN active_tasks_json TEXT NOT NULL DEFAULT '[]'")
        belief_columns = {str(row[1]) for row in self._conn.execute("PRAGMA table_info(job_beliefs)").fetchall()}
        if "temporal_findings_json" not in belief_columns:
            self._conn.execute("ALTER TABLE job_beliefs ADD COLUMN temporal_findings_json TEXT NOT NULL DEFAULT '[]'")
        if "hypothesis_history_json" not in belief_columns:
            self._conn.execute("ALTER TABLE job_beliefs ADD COLUMN hypothesis_history_json TEXT NOT NULL DEFAULT '[]'")
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # CRUD operations
    # ------------------------------------------------------------------ #

    def save_job(self, state: JobState, plan: JobPlan | None = None, beliefs: JobBeliefs | None = None) -> None:
        """Save or update a job and its related data atomically.

        Related records omitted by the caller remain unchanged. Every supplied
        record must belong to the state job before the transaction begins.
        """
        if plan is not None and plan.job_id != state.job_id:
            raise ValueError(f"plan job_id {plan.job_id!r} does not match state job_id {state.job_id!r}")
        if beliefs is not None and beliefs.job_id != state.job_id:
            raise ValueError(f"beliefs job_id {beliefs.job_id!r} does not match state job_id {state.job_id!r}")

        now = datetime.now().isoformat()
        active_tasks_json = json.dumps(state.active_tasks, default=str)
        metadata_json = json.dumps(state.metadata, default=str)
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO jobs
                   (job_id, phase, progress, cost_so_far, estimated_remaining, error,
                    started_at, updated_at, metadata_json, owner_id, active_tasks_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(job_id) DO UPDATE SET
                       phase = excluded.phase,
                       progress = excluded.progress,
                       cost_so_far = excluded.cost_so_far,
                       estimated_remaining = excluded.estimated_remaining,
                       error = excluded.error,
                       started_at = excluded.started_at,
                       updated_at = excluded.updated_at,
                       metadata_json = excluded.metadata_json,
                       owner_id = excluded.owner_id,
                       active_tasks_json = excluded.active_tasks_json""",
                (
                    state.job_id,
                    state.phase.value,
                    state.progress,
                    state.cost_so_far,
                    state.estimated_remaining,
                    state.error,
                    state.started_at.isoformat(),
                    now,
                    metadata_json,
                    state.owner_id,
                    active_tasks_json,
                ),
            )

            if plan is not None:
                self._conn.execute(
                    """INSERT INTO job_plans
                       (job_id, goal, steps_json, estimated_cost, estimated_time, model)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(job_id) DO UPDATE SET
                           goal = excluded.goal,
                           steps_json = excluded.steps_json,
                           estimated_cost = excluded.estimated_cost,
                           estimated_time = excluded.estimated_time,
                           model = excluded.model""",
                    (
                        plan.job_id,
                        plan.goal,
                        json.dumps(plan.steps, default=str),
                        plan.estimated_cost,
                        plan.estimated_time,
                        plan.model,
                    ),
                )

            if beliefs is not None:
                self._conn.execute(
                    """INSERT INTO job_beliefs
                       (job_id, beliefs_json, sources_json, confidence,
                        temporal_findings_json, hypothesis_history_json)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(job_id) DO UPDATE SET
                           beliefs_json = excluded.beliefs_json,
                           sources_json = excluded.sources_json,
                           confidence = excluded.confidence,
                           temporal_findings_json = excluded.temporal_findings_json,
                           hypothesis_history_json = excluded.hypothesis_history_json""",
                    (
                        beliefs.job_id,
                        json.dumps(beliefs.beliefs, default=str),
                        json.dumps(beliefs.sources, default=str),
                        beliefs.confidence,
                        json.dumps([record.to_dict() for record in beliefs.temporal_findings]),
                        json.dumps([record.to_dict() for record in beliefs.hypothesis_history]),
                    ),
                )

    def load_job(self, job_id: str) -> tuple[JobState, JobPlan | None, JobBeliefs | None] | None:
        """Load a job and its related data."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not row:
                return None
            plan_row = self._conn.execute("SELECT * FROM job_plans WHERE job_id = ?", (job_id,)).fetchone()
            beliefs_row = self._conn.execute("SELECT * FROM job_beliefs WHERE job_id = ?", (job_id,)).fetchone()

        state = self._row_to_state(row)
        plan = self._row_to_plan(plan_row) if plan_row else None
        beliefs = self._row_to_beliefs(beliefs_row) if beliefs_row else None
        return state, plan, beliefs

    def list_jobs(self, phase: str | None = None) -> list[JobState]:
        """List all jobs, optionally filtered by phase."""
        with self._lock:
            if phase:
                rows = self._conn.execute(
                    "SELECT * FROM jobs WHERE phase = ? ORDER BY updated_at DESC",
                    (phase,),
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC").fetchall()
        return [self._row_to_state(r) for r in rows]

    def delete_job(self, job_id: str) -> bool:
        """Delete a job and its related data (cascades)."""
        with self._lock, self._conn:
            cursor = self._conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        return cursor.rowcount > 0

    def mark_incomplete_as_failed(self) -> int:
        """Mark all non-terminal jobs as FAILED on restart.

        Returns the number of jobs updated.
        """
        terminal = ("completed", "failed", "cancelled")
        terminal_markers = ",".join("?" for _ in terminal)
        now = datetime.now().isoformat()

        with self._lock, self._conn:
            cursor = self._conn.execute(
                f"""UPDATE jobs
                    SET phase = 'failed',
                        error = 'Server restarted while job was in progress',
                        updated_at = ?,
                        active_tasks_json = '[]'
                    WHERE phase NOT IN ({terminal_markers})""",
                (now, *terminal),
            )
        return cursor.rowcount

    # ------------------------------------------------------------------ #
    # Row mappers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _row_to_state(row: tuple[Any, ...]) -> JobState:
        """Convert a database row to a JobState."""
        (
            job_id,
            phase,
            progress,
            cost_so_far,
            estimated_remaining,
            error,
            started_at,
            updated_at,
            metadata_json,
            owner_id,
            active_tasks_json,
        ) = row
        return JobState(
            job_id=job_id,
            phase=JobPhase(phase),
            progress=progress,
            cost_so_far=cost_so_far,
            estimated_remaining=estimated_remaining,
            error=error,
            started_at=datetime.fromisoformat(started_at),
            updated_at=datetime.fromisoformat(updated_at),
            active_tasks=json.loads(active_tasks_json) if active_tasks_json else [],
            owner_id=owner_id,
            metadata=json.loads(metadata_json) if metadata_json else {},
        )

    @staticmethod
    def _row_to_plan(row: tuple[Any, ...]) -> JobPlan:
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
    def _row_to_beliefs(row: tuple[Any, ...]) -> JobBeliefs:
        """Convert a database row to a JobBeliefs."""
        (
            job_id,
            beliefs_json,
            sources_json,
            confidence,
            temporal_findings_json,
            hypothesis_history_json,
        ) = row
        return JobBeliefs(
            job_id=job_id,
            beliefs=json.loads(beliefs_json) if beliefs_json else [],
            sources=json.loads(sources_json) if sources_json else [],
            confidence=confidence,
            temporal_findings=[
                TemporalFindingRecord(**record)
                for record in (json.loads(temporal_findings_json) if temporal_findings_json else [])
            ],
            hypothesis_history=[
                HypothesisRecord(**record)
                for record in (json.loads(hypothesis_history_json) if hypothesis_history_json else [])
            ],
        )

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()
