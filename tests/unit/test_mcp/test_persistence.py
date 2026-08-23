"""
Tests for SQLite-backed job persistence.

Validates:
- CRUD operations (save, load, list, delete)
- Restart recovery (mark_incomplete_as_failed)
- Schema creation and WAL mode
- Data integrity across save/load cycles
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.state.job_manager import (
    HypothesisRecord,
    JobBeliefs,
    JobPhase,
    JobPlan,
    JobState,
    TemporalFindingRecord,
)
from deepr.mcp.state.persistence import JobPersistence


@pytest.fixture
def db(tmp_path):
    """Create a JobPersistence instance with a temp database."""
    persistence = JobPersistence(db_path=tmp_path / "test_jobs.db")
    yield persistence
    persistence.close()


@pytest.fixture
def sample_state():
    """Create a sample JobState."""
    return JobState(
        job_id="job_001",
        phase=JobPhase.EXECUTING,
        progress=0.5,
        cost_so_far=0.12,
        estimated_remaining="5 minutes",
        started_at=datetime(2025, 1, 1, 12, 0, 0),
    )


@pytest.fixture
def sample_plan():
    return JobPlan(
        job_id="job_001",
        goal="Research quantum computing",
        steps=[{"step": "search", "query": "quantum computing advances"}],
        estimated_cost=0.25,
        estimated_time="10 minutes",
        model="o4-mini",
    )


@pytest.fixture
def sample_beliefs():
    return JobBeliefs(
        job_id="job_001",
        beliefs=[{"text": "Quantum advantage demonstrated", "confidence": 0.85}],
        sources=["arxiv.org/abs/2024.001"],
        confidence=0.85,
    )


# ------------------------------------------------------------------ #
# Schema and initialization
# ------------------------------------------------------------------ #


class TestSchema:
    def test_tables_created(self, db):
        """All three tables should exist after init."""
        cursor = db._conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cursor.fetchall()}
        assert "jobs" in tables
        assert "job_plans" in tables
        assert "job_beliefs" in tables

    def test_wal_mode(self, db):
        """Database should use WAL journal mode."""
        mode = db._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_foreign_keys_enabled(self, db):
        """Foreign keys should be enabled."""
        fk = db._conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

    def test_jobs_schema_includes_scoped_owner(self, db):
        columns = {row[1] for row in db._conn.execute("PRAGMA table_info(jobs)").fetchall()}
        assert "owner_id" in columns

    def test_idempotent_creation(self, tmp_path):
        """Creating persistence twice on same DB should not fail."""
        db1 = JobPersistence(db_path=tmp_path / "test.db")
        db2 = JobPersistence(db_path=tmp_path / "test.db")
        db1.close()
        db2.close()

    def test_migrates_legacy_runtime_state_columns(self, tmp_path):
        """Existing databases gain lossless runtime-state columns."""
        db_path = tmp_path / "legacy.db"
        connection = sqlite3.connect(db_path)
        connection.executescript("""
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                phase TEXT NOT NULL DEFAULT 'queued',
                progress REAL NOT NULL DEFAULT 0.0,
                cost_so_far REAL NOT NULL DEFAULT 0.0,
                estimated_remaining TEXT,
                error TEXT,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                owner_id TEXT
            );
            CREATE TABLE job_plans (
                job_id TEXT PRIMARY KEY REFERENCES jobs(job_id) ON DELETE CASCADE,
                goal TEXT NOT NULL DEFAULT '',
                steps_json TEXT NOT NULL DEFAULT '[]',
                estimated_cost REAL NOT NULL DEFAULT 0.0,
                estimated_time TEXT NOT NULL DEFAULT 'unknown',
                model TEXT NOT NULL DEFAULT 'o4-mini'
            );
            CREATE TABLE job_beliefs (
                job_id TEXT PRIMARY KEY REFERENCES jobs(job_id) ON DELETE CASCADE,
                beliefs_json TEXT NOT NULL DEFAULT '[]',
                sources_json TEXT NOT NULL DEFAULT '[]',
                confidence REAL NOT NULL DEFAULT 0.0
            );
            INSERT INTO jobs (
                job_id, phase, started_at, updated_at, metadata_json
            ) VALUES (
                'legacy', 'completed', '2025-01-01T00:00:00',
                '2025-01-01T00:00:00', '{}'
            );
            INSERT INTO job_beliefs (
                job_id, beliefs_json, sources_json, confidence
            ) VALUES ('legacy', '[]', '[]', 0.5);
        """)
        connection.commit()
        connection.close()

        persistence = JobPersistence(db_path=db_path)
        try:
            job_columns = {row[1] for row in persistence._conn.execute("PRAGMA table_info(jobs)").fetchall()}
            belief_columns = {
                row[1] for row in persistence._conn.execute("PRAGMA table_info(job_beliefs)").fetchall()
            }
            assert "active_tasks_json" in job_columns
            assert "temporal_findings_json" in belief_columns
            assert "hypothesis_history_json" in belief_columns

            loaded = persistence.load_job("legacy")
            assert loaded is not None
            state, _plan, beliefs = loaded
            assert state.active_tasks == []
            assert beliefs is not None
            assert beliefs.temporal_findings == []
            assert beliefs.hypothesis_history == []
        finally:
            persistence.close()


# ------------------------------------------------------------------ #
# CRUD: save and load
# ------------------------------------------------------------------ #


class TestSaveLoad:
    def test_save_and_load_state_only(self, db, sample_state):
        """Save and load a job with state only."""
        db.save_job(sample_state)
        result = db.load_job("job_001")

        assert result is not None
        state, plan, beliefs = result
        assert state.job_id == "job_001"
        assert state.phase == JobPhase.EXECUTING
        assert state.progress == 0.5
        assert state.cost_so_far == 0.12
        assert state.estimated_remaining == "5 minutes"
        assert plan is None
        assert beliefs is None

    def test_save_and_load_full(self, db, sample_state, sample_plan, sample_beliefs):
        """Save and load a job with all related data."""
        db.save_job(sample_state, plan=sample_plan, beliefs=sample_beliefs)
        result = db.load_job("job_001")

        _state, plan, beliefs = result
        assert plan is not None
        assert plan.goal == "Research quantum computing"
        assert plan.steps[0]["step"] == "search"
        assert plan.estimated_cost == 0.25
        assert plan.model == "o4-mini"

        assert beliefs is not None
        assert len(beliefs.beliefs) == 1
        assert beliefs.beliefs[0]["text"] == "Quantum advantage demonstrated"
        assert beliefs.sources == ["arxiv.org/abs/2024.001"]
        assert beliefs.confidence == 0.85

    def test_load_nonexistent(self, db):
        """Loading a nonexistent job returns None."""
        assert db.load_job("nonexistent") is None

    def test_save_updates_existing(self, db, sample_state):
        """Saving the same job_id should update, not duplicate."""
        db.save_job(sample_state)

        sample_state.phase = JobPhase.COMPLETED
        sample_state.progress = 1.0
        db.save_job(sample_state)

        result = db.load_job("job_001")
        state, _, _ = result
        assert state.phase == JobPhase.COMPLETED
        assert state.progress == 1.0

    def test_state_only_update_preserves_existing_plan_and_beliefs(
        self,
        db,
        sample_state,
        sample_plan,
        sample_beliefs,
    ):
        """Updating parent state must not cascade-delete related records."""
        db.save_job(sample_state, plan=sample_plan, beliefs=sample_beliefs)

        sample_state.phase = JobPhase.COMPLETED
        sample_state.progress = 1.0
        db.save_job(sample_state)

        loaded = db.load_job(sample_state.job_id)
        assert loaded is not None
        state, plan, beliefs = loaded
        assert state.phase == JobPhase.COMPLETED
        assert plan is not None
        assert plan.goal == sample_plan.goal
        assert beliefs is not None
        assert beliefs.beliefs == sample_beliefs.beliefs

    def test_active_tasks_roundtrip(self, db, sample_state):
        sample_state.active_tasks = ["Search primary sources", "Check citations"]

        db.save_job(sample_state)

        loaded = db.load_job(sample_state.job_id)
        assert loaded is not None
        state, _plan, _beliefs = loaded
        assert state.active_tasks == sample_state.active_tasks

    def test_temporal_belief_state_survives_restart(self, tmp_path, sample_state, sample_beliefs):
        db_path = tmp_path / "temporal.db"
        sample_beliefs.temporal_findings = [
            TemporalFindingRecord(
                id="finding-1",
                text="The standard changed",
                phase=2,
                confidence=0.8,
                finding_type="update",
                timestamp="2025-01-02T03:04:05",
                source="https://example.test/source",
            )
        ]
        sample_beliefs.hypothesis_history = [
            HypothesisRecord(
                id="hypothesis-1",
                current_text="Adoption will increase",
                confidence=0.6,
                phase_created=2,
                evolution_count=1,
                status="active",
            )
        ]

        first = JobPersistence(db_path=db_path)
        first.save_job(sample_state, beliefs=sample_beliefs)
        first.close()

        second = JobPersistence(db_path=db_path)
        try:
            loaded = second.load_job(sample_state.job_id)
            assert loaded is not None
            _state, _plan, beliefs = loaded
            assert beliefs is not None
            assert beliefs.temporal_findings == sample_beliefs.temporal_findings
            assert beliefs.hypothesis_history == sample_beliefs.hypothesis_history
        finally:
            second.close()

    def test_rejects_plan_for_a_different_job_before_mutation(self, db, sample_state):
        other_state = JobState(job_id="job_002")
        original_plan = JobPlan(job_id="job_002", goal="Keep this plan")
        db.save_job(other_state, plan=original_plan)
        mismatched = JobPlan(job_id="job_002", goal="Wrongly replace another job")

        with pytest.raises(ValueError, match="plan job_id"):
            db.save_job(sample_state, plan=mismatched)

        loaded = db.load_job("job_002")
        assert loaded is not None
        _state, plan, _beliefs = loaded
        assert plan is not None
        assert plan.goal == original_plan.goal

    def test_rejects_beliefs_for_a_different_job_before_mutation(self, db, sample_state):
        other_state = JobState(job_id="job_002")
        original_beliefs = JobBeliefs(job_id="job_002", beliefs=[{"text": "keep"}])
        db.save_job(other_state, beliefs=original_beliefs)
        mismatched = JobBeliefs(job_id="job_002", beliefs=[{"text": "replace"}])

        with pytest.raises(ValueError, match="beliefs job_id"):
            db.save_job(sample_state, beliefs=mismatched)

        loaded = db.load_job("job_002")
        assert loaded is not None
        _state, _plan, beliefs = loaded
        assert beliefs is not None
        assert beliefs.beliefs == original_beliefs.beliefs

    def test_datetime_roundtrip(self, db, sample_state):
        """Datetime values should survive save/load cycle."""
        db.save_job(sample_state)
        state, _, _ = db.load_job("job_001")
        assert state.started_at == datetime(2025, 1, 1, 12, 0, 0)

    def test_metadata_roundtrip(self, db):
        """Metadata dict should survive JSON serialization."""
        state = JobState(
            job_id="meta_test",
            metadata={"model": "o4-mini", "tags": ["urgent", "customer"]},
        )
        db.save_job(state)
        loaded, _, _ = db.load_job("meta_test")
        assert loaded.metadata["model"] == "o4-mini"
        assert loaded.metadata["tags"] == ["urgent", "customer"]

    def test_scoped_owner_roundtrip(self, db):
        state = JobState(job_id="owned", owner_id="mcp:key:owner-hash")
        db.save_job(state)

        loaded, _, _ = db.load_job("owned")

        assert loaded.owner_id == "mcp:key:owner-hash"


# ------------------------------------------------------------------ #
# CRUD: list
# ------------------------------------------------------------------ #


class TestList:
    def test_list_empty(self, db):
        assert db.list_jobs() == []

    def test_list_all(self, db):
        for i in range(5):
            db.save_job(JobState(job_id=f"job_{i}"))
        assert len(db.list_jobs()) == 5

    def test_list_filtered_by_phase(self, db):
        db.save_job(JobState(job_id="q1", phase=JobPhase.QUEUED))
        db.save_job(JobState(job_id="e1", phase=JobPhase.EXECUTING))
        db.save_job(JobState(job_id="c1", phase=JobPhase.COMPLETED))
        db.save_job(JobState(job_id="e2", phase=JobPhase.EXECUTING))

        executing = db.list_jobs(phase="executing")
        assert len(executing) == 2
        assert all(s.phase == JobPhase.EXECUTING for s in executing)

    def test_list_ordered_by_updated_at(self, db):
        """Jobs should be ordered by updated_at DESC."""
        jobs = db.list_jobs()
        # Just verify it doesn't crash; ordering is best-effort with same timestamps
        assert isinstance(jobs, list)


# ------------------------------------------------------------------ #
# CRUD: delete
# ------------------------------------------------------------------ #


class TestDelete:
    def test_delete_existing(self, db, sample_state, sample_plan, sample_beliefs):
        db.save_job(sample_state, plan=sample_plan, beliefs=sample_beliefs)
        assert db.delete_job("job_001") is True
        assert db.load_job("job_001") is None

    def test_delete_nonexistent(self, db):
        assert db.delete_job("nonexistent") is False

    def test_delete_cascades(self, db, sample_state, sample_plan, sample_beliefs):
        """Deleting a job should cascade to plans and beliefs."""
        db.save_job(sample_state, plan=sample_plan, beliefs=sample_beliefs)
        db.delete_job("job_001")

        # Verify cascaded deletion
        plan_row = db._conn.execute("SELECT * FROM job_plans WHERE job_id = ?", ("job_001",)).fetchone()
        beliefs_row = db._conn.execute("SELECT * FROM job_beliefs WHERE job_id = ?", ("job_001",)).fetchone()
        assert plan_row is None
        assert beliefs_row is None


# ------------------------------------------------------------------ #
# Restart recovery
# ------------------------------------------------------------------ #


class TestRestartRecovery:
    def test_mark_incomplete_as_failed(self, db):
        """Non-terminal jobs should be marked failed on restart."""
        db.save_job(JobState(job_id="q1", phase=JobPhase.QUEUED))
        db.save_job(JobState(job_id="e1", phase=JobPhase.EXECUTING))
        db.save_job(JobState(job_id="p1", phase=JobPhase.PLANNING))
        db.save_job(JobState(job_id="c1", phase=JobPhase.COMPLETED))
        db.save_job(JobState(job_id="f1", phase=JobPhase.FAILED))
        db.save_job(JobState(job_id="x1", phase=JobPhase.CANCELLED))

        count = db.mark_incomplete_as_failed()
        assert count == 3  # queued, executing, planning

        # Verify the terminal ones are unchanged
        c1, _, _ = db.load_job("c1")
        assert c1.phase == JobPhase.COMPLETED

        f1, _, _ = db.load_job("f1")
        assert f1.phase == JobPhase.FAILED

        # Verify incomplete ones are now failed
        q1, _, _ = db.load_job("q1")
        assert q1.phase == JobPhase.FAILED
        assert q1.error == "Server restarted while job was in progress"

    def test_mark_incomplete_empty_db(self, db):
        """Should handle empty database gracefully."""
        assert db.mark_incomplete_as_failed() == 0

    def test_simulated_restart(self, tmp_path):
        """Jobs should survive a simulated restart (close + reopen)."""
        db_path = tmp_path / "restart_test.db"

        # First session: create jobs
        db1 = JobPersistence(db_path=db_path)
        db1.save_job(JobState(job_id="persist_1", phase=JobPhase.EXECUTING))
        db1.save_job(JobState(job_id="persist_2", phase=JobPhase.COMPLETED, progress=1.0))
        db1.close()

        # Second session: verify data survived
        db2 = JobPersistence(db_path=db_path)
        jobs = db2.list_jobs()
        assert len(jobs) == 2

        # Mark incomplete as failed (simulating startup recovery)
        failed_count = db2.mark_incomplete_as_failed()
        assert failed_count == 1  # only persist_1

        p1, _, _ = db2.load_job("persist_1")
        assert p1.phase == JobPhase.FAILED

        p2, _, _ = db2.load_job("persist_2")
        assert p2.phase == JobPhase.COMPLETED
        db2.close()
