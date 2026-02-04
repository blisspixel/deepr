"""Tests for job management module.

Requirements: 1.3 - Test Coverage
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from deepr.core.jobs import JobManager, JobRecord


class TestJobRecord:
    """Tests for JobRecord dataclass."""

    def test_create_minimal_record(self):
        """Should create record with minimal required fields."""
        record = JobRecord(
            response_id="resp_123",
            status="queued",
            timestamp="2026-01-01T00:00:00+00:00",
            original_prompt="Test query"
        )

        assert record.response_id == "resp_123"
        assert record.status == "queued"
        assert record.original_prompt == "Test query"
        assert record.refined_prompt is None
        assert record.model is None
        assert record.provider is None

    def test_create_full_record(self):
        """Should create record with all fields."""
        record = JobRecord(
            response_id="resp_456",
            status="completed",
            timestamp="2026-01-02T12:00:00+00:00",
            original_prompt="Test query",
            refined_prompt="Refined test query",
            model="gpt-5",
            provider="openai",
            run_id="run_789",
            metadata={"key": "value"}
        )

        assert record.response_id == "resp_456"
        assert record.refined_prompt == "Refined test query"
        assert record.model == "gpt-5"
        assert record.provider == "openai"
        assert record.run_id == "run_789"
        assert record.metadata == {"key": "value"}


class TestJobManagerInit:
    """Tests for JobManager initialization."""

    def test_default_initialization(self, tmp_path):
        """Should initialize with defaults."""
        manager = JobManager(log_path=str(tmp_path / "jobs.jsonl"))

        assert manager.backend_type == "jsonl"
        assert manager.log_path == tmp_path / "jobs.jsonl"

    def test_creates_log_directory(self, tmp_path):
        """Should create log directory if it doesn't exist."""
        log_path = tmp_path / "nested" / "logs" / "jobs.jsonl"
        manager = JobManager(log_path=str(log_path))

        assert log_path.parent.exists()


class TestJobManagerLogSubmission:
    """Tests for log_submission method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create JobManager with temp path."""
        return JobManager(log_path=str(tmp_path / "jobs.jsonl"))

    @pytest.mark.asyncio
    async def test_log_minimal_submission(self, manager):
        """Should log submission with minimal fields."""
        await manager.log_submission(
            response_id="resp_001",
            original_prompt="Test query"
        )

        # Verify log file exists and contains record
        assert manager.log_path.exists()

        with open(manager.log_path) as f:
            record = json.loads(f.readline())

        assert record["response_id"] == "resp_001"
        assert record["status"] == "queued"
        assert record["original_prompt"] == "Test query"

    @pytest.mark.asyncio
    async def test_log_full_submission(self, manager):
        """Should log submission with all fields."""
        await manager.log_submission(
            response_id="resp_002",
            original_prompt="Test query",
            refined_prompt="Refined query",
            model="gpt-5",
            provider="openai",
            run_id="run_123",
            metadata={"key": "value"}
        )

        with open(manager.log_path) as f:
            record = json.loads(f.readline())

        assert record["refined_prompt"] == "Refined query"
        assert record["model"] == "gpt-5"
        assert record["provider"] == "openai"
        assert record["run_id"] == "run_123"
        assert record["metadata"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_log_multiple_submissions(self, manager):
        """Should append multiple submissions."""
        await manager.log_submission("resp_001", "Query 1")
        await manager.log_submission("resp_002", "Query 2")
        await manager.log_submission("resp_003", "Query 3")

        with open(manager.log_path) as f:
            lines = f.readlines()

        assert len(lines) == 3


class TestJobManagerUpdateStatus:
    """Tests for update_status method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create JobManager with temp path."""
        return JobManager(log_path=str(tmp_path / "jobs.jsonl"))

    @pytest.mark.asyncio
    async def test_update_status(self, manager):
        """Should update job status."""
        await manager.log_submission("resp_001", "Query 1")
        await manager.update_status("resp_001", "completed")

        with open(manager.log_path) as f:
            record = json.loads(f.readline())

        assert record["status"] == "completed"

    @pytest.mark.asyncio
    async def test_update_status_nonexistent_file(self, manager):
        """Should handle update when file doesn't exist."""
        # Should not raise error
        await manager.update_status("resp_nonexistent", "completed")

    @pytest.mark.asyncio
    async def test_update_status_preserves_other_records(self, manager):
        """Should preserve other records when updating one."""
        await manager.log_submission("resp_001", "Query 1")
        await manager.log_submission("resp_002", "Query 2")
        await manager.update_status("resp_001", "completed")

        with open(manager.log_path) as f:
            lines = f.readlines()

        record1 = json.loads(lines[0])
        record2 = json.loads(lines[1])

        assert record1["status"] == "completed"
        assert record2["status"] == "queued"


class TestJobManagerGetJob:
    """Tests for get_job method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create JobManager with temp path."""
        return JobManager(log_path=str(tmp_path / "jobs.jsonl"))

    @pytest.mark.asyncio
    async def test_get_existing_job(self, manager):
        """Should retrieve existing job."""
        await manager.log_submission("resp_001", "Query 1", model="gpt-5")

        job = await manager.get_job("resp_001")

        assert job is not None
        assert job.response_id == "resp_001"
        assert job.original_prompt == "Query 1"
        assert job.model == "gpt-5"

    @pytest.mark.asyncio
    async def test_get_nonexistent_job(self, manager):
        """Should return None for nonexistent job."""
        await manager.log_submission("resp_001", "Query 1")

        job = await manager.get_job("resp_999")

        assert job is None

    @pytest.mark.asyncio
    async def test_get_job_empty_file(self, manager):
        """Should return None when file doesn't exist."""
        job = await manager.get_job("resp_001")

        assert job is None


class TestJobManagerListJobs:
    """Tests for list_jobs method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create JobManager with temp path."""
        return JobManager(log_path=str(tmp_path / "jobs.jsonl"))

    @pytest.mark.asyncio
    async def test_list_all_jobs(self, manager):
        """Should list all jobs."""
        await manager.log_submission("resp_001", "Query 1")
        await manager.log_submission("resp_002", "Query 2")
        await manager.log_submission("resp_003", "Query 3")

        jobs = await manager.list_jobs()

        assert len(jobs) == 3

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, manager):
        """Should return empty list when no jobs."""
        jobs = await manager.list_jobs()

        assert jobs == []

    @pytest.mark.asyncio
    async def test_list_jobs_filtered_by_status(self, manager):
        """Should filter jobs by status."""
        await manager.log_submission("resp_001", "Query 1")
        await manager.log_submission("resp_002", "Query 2")
        await manager.update_status("resp_001", "completed")

        queued_jobs = await manager.list_jobs(status="queued")
        completed_jobs = await manager.list_jobs(status="completed")

        assert len(queued_jobs) == 1
        assert len(completed_jobs) == 1

    @pytest.mark.asyncio
    async def test_list_jobs_with_limit(self, manager):
        """Should respect limit parameter."""
        for i in range(10):
            await manager.log_submission(f"resp_{i:03d}", f"Query {i}")

        jobs = await manager.list_jobs(limit=5)

        assert len(jobs) == 5

    @pytest.mark.asyncio
    async def test_list_jobs_sorted_by_timestamp(self, manager):
        """Should return jobs sorted by timestamp (newest first)."""
        await manager.log_submission("resp_001", "Query 1")
        await manager.log_submission("resp_002", "Query 2")
        await manager.log_submission("resp_003", "Query 3")

        jobs = await manager.list_jobs()

        # Most recent should be first
        for i in range(len(jobs) - 1):
            assert jobs[i].timestamp >= jobs[i + 1].timestamp


class TestJobManagerCleanup:
    """Tests for cleanup_old_jobs method."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create JobManager with temp path."""
        return JobManager(log_path=str(tmp_path / "jobs.jsonl"))

    @pytest.mark.asyncio
    async def test_cleanup_removes_old_completed(self, manager):
        """Should remove old completed jobs."""
        # Create an old completed job
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        old_record = {
            "response_id": "resp_old",
            "status": "completed",
            "timestamp": old_timestamp,
            "original_prompt": "Old query"
        }

        with open(manager.log_path, "w") as f:
            f.write(json.dumps(old_record) + "\n")

        # Create a new job
        await manager.log_submission("resp_new", "New query")
        await manager.update_status("resp_new", "completed")

        cleaned = await manager.cleanup_old_jobs(days=7)

        assert cleaned == 1
        jobs = await manager.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].response_id == "resp_new"

    @pytest.mark.asyncio
    async def test_cleanup_preserves_queued(self, manager):
        """Should preserve queued jobs even if old."""
        # Create an old queued job
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        old_record = {
            "response_id": "resp_old",
            "status": "queued",
            "timestamp": old_timestamp,
            "original_prompt": "Old query"
        }

        with open(manager.log_path, "w") as f:
            f.write(json.dumps(old_record) + "\n")

        cleaned = await manager.cleanup_old_jobs(days=7)

        assert cleaned == 0
        jobs = await manager.list_jobs()
        assert len(jobs) == 1

    @pytest.mark.asyncio
    async def test_cleanup_empty_file(self, manager):
        """Should handle cleanup of nonexistent file."""
        cleaned = await manager.cleanup_old_jobs(days=7)

        assert cleaned == 0
