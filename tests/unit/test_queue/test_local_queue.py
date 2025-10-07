"""Tests for SQLite queue implementation."""

import pytest
import os
from datetime import datetime
from deepr.queue import SQLiteQueue, ResearchJob, JobStatus


@pytest.mark.asyncio
class TestSQLiteQueue:
    """Test SQLite queue backend."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create test queue instance."""
        db_path = tmp_path / "test_queue.db"
        return SQLiteQueue(str(db_path))

    @pytest.fixture
    def sample_job(self):
        """Create sample job for testing."""
        return ResearchJob(
            id="test-job-001",
            prompt="Test research prompt",
            model="o3-deep-research",
            priority=5,
        )

    async def test_enqueue_and_get(self, queue, sample_job):
        """Test enqueueing and retrieving a job."""
        # Enqueue
        job_id = await queue.enqueue(sample_job)
        assert job_id == "test-job-001"

        # Get job
        retrieved = await queue.get_job(job_id)
        assert retrieved is not None
        assert retrieved.id == sample_job.id
        assert retrieved.prompt == sample_job.prompt
        assert retrieved.status == JobStatus.QUEUED

    async def test_dequeue_priority(self, queue):
        """Test dequeue respects priority."""
        # Enqueue low priority job
        low_priority = ResearchJob(
            id="low-priority",
            prompt="Low priority task",
            priority=1,
        )
        await queue.enqueue(low_priority)

        # Enqueue high priority job
        high_priority = ResearchJob(
            id="high-priority",
            prompt="High priority task",
            priority=10,
        )
        await queue.enqueue(high_priority)

        # Dequeue should return high priority first
        job = await queue.dequeue("worker-1")
        assert job is not None
        assert job.id == "high-priority"
        assert job.status == JobStatus.PROCESSING
        assert job.worker_id == "worker-1"

    async def test_dequeue_fifo_same_priority(self, queue):
        """Test dequeue is FIFO for same priority."""
        # Enqueue two jobs with same priority
        job1 = ResearchJob(id="job-1", prompt="First", priority=5)
        job2 = ResearchJob(id="job-2", prompt="Second", priority=5)

        await queue.enqueue(job1)
        await queue.enqueue(job2)

        # Should dequeue in order
        first = await queue.dequeue("worker-1")
        assert first.id == "job-1"

        second = await queue.dequeue("worker-2")
        assert second.id == "job-2"

    async def test_update_status(self, queue, sample_job):
        """Test status updates."""
        await queue.enqueue(sample_job)

        # Update to processing
        success = await queue.update_status(
            sample_job.id,
            JobStatus.PROCESSING,
            provider_job_id="provider-123",
        )
        assert success is True

        # Verify update
        job = await queue.get_job(sample_job.id)
        assert job.status == JobStatus.PROCESSING
        assert job.provider_job_id == "provider-123"

    async def test_update_results(self, queue, sample_job):
        """Test results updates."""
        await queue.enqueue(sample_job)

        # Update results
        report_paths = {
            "md": "/reports/job-001/report.md",
            "docx": "/reports/job-001/report.docx",
        }

        success = await queue.update_results(
            sample_job.id,
            report_paths=report_paths,
            cost=2.50,
            tokens_used=10000,
        )
        assert success is True

        # Verify
        job = await queue.get_job(sample_job.id)
        assert job.report_paths == report_paths
        assert job.cost == 2.50
        assert job.tokens_used == 10000

    async def test_list_jobs_filter_by_status(self, queue):
        """Test listing jobs filtered by status."""
        # Enqueue jobs with different statuses
        queued_job = ResearchJob(id="queued-1", prompt="Queued", status=JobStatus.QUEUED)
        await queue.enqueue(queued_job)

        processing_job = ResearchJob(id="processing-1", prompt="Processing")
        await queue.enqueue(processing_job)
        await queue.update_status(processing_job.id, JobStatus.PROCESSING)

        # List queued jobs
        queued_jobs = await queue.list_jobs(status=JobStatus.QUEUED)
        assert len(queued_jobs) == 1
        assert queued_jobs[0].id == "queued-1"

        # List processing jobs
        processing_jobs = await queue.list_jobs(status=JobStatus.PROCESSING)
        assert len(processing_jobs) == 1
        assert processing_jobs[0].id == "processing-1"

    async def test_cancel_job(self, queue, sample_job):
        """Test job cancellation."""
        await queue.enqueue(sample_job)

        # Cancel
        success = await queue.cancel_job(sample_job.id)
        assert success is True

        # Verify
        job = await queue.get_job(sample_job.id)
        assert job.status == JobStatus.CANCELLED

    async def test_queue_stats(self, queue):
        """Test queue statistics."""
        # Enqueue various jobs
        for i in range(3):
            await queue.enqueue(ResearchJob(id=f"queued-{i}", prompt=f"Task {i}"))

        # Process one
        job = await queue.dequeue("worker-1")
        await queue.update_status(job.id, JobStatus.COMPLETED)

        # Get stats
        stats = await queue.get_queue_stats()

        assert stats["total"] == 3
        assert stats["queued"] >= 1  # At least 1 still queued (processed one was dequeued)
        assert stats["completed"] == 1

    async def test_cleanup_old_jobs(self, queue):
        """Test cleanup of old jobs."""
        # Enqueue and complete a job
        job = ResearchJob(id="old-job", prompt="Old task")
        await queue.enqueue(job)
        await queue.update_status(job.id, JobStatus.COMPLETED)

        # Cleanup (0 days = all completed jobs)
        deleted = await queue.cleanup_old_jobs(days=0)

        assert deleted >= 1

        # Verify job is gone
        retrieved = await queue.get_job(job.id)
        assert retrieved is None

    async def test_concurrent_dequeue(self, queue):
        """Test multiple workers dequeuing concurrently."""
        # Enqueue job
        job = ResearchJob(id="concurrent-test", prompt="Concurrent task")
        await queue.enqueue(job)

        # Two workers try to dequeue
        import asyncio

        results = await asyncio.gather(
            queue.dequeue("worker-1"),
            queue.dequeue("worker-2"),
        )

        # Only one should succeed
        successful = [r for r in results if r is not None]
        assert len(successful) == 1
        assert successful[0].id == "concurrent-test"
