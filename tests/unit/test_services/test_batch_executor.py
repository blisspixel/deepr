"""Tests for batch executor service."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from deepr.queue.base import JobStatus
from deepr.services.batch_executor import BatchExecutor


class TestBatchExecutor:
    """Test BatchExecutor campaign orchestration."""

    @pytest.fixture
    def mock_queue(self):
        return AsyncMock()

    @pytest.fixture
    def mock_provider(self):
        return AsyncMock()

    @pytest.fixture
    def mock_storage(self):
        return AsyncMock()

    @pytest.fixture
    def mock_context_builder(self):
        return AsyncMock()

    @pytest.fixture
    def executor(self, mock_queue, mock_provider, mock_storage, mock_context_builder):
        return BatchExecutor(
            queue=mock_queue,
            provider=mock_provider,
            storage=mock_storage,
            context_builder=mock_context_builder,
        )

    def test_init_stores_dependencies(self, executor, mock_queue, mock_provider, mock_storage, mock_context_builder):
        """All injected services stored as attributes."""
        assert executor.queue is mock_queue
        assert executor.provider is mock_provider
        assert executor.storage is mock_storage
        assert executor.context_builder is mock_context_builder

    def test_group_by_phase_single(self, executor):
        """Single phase grouping."""
        tasks = [
            {"id": 1, "title": "T1", "prompt": "P1", "phase": 1},
            {"id": 2, "title": "T2", "prompt": "P2", "phase": 1},
        ]
        phases = executor._group_by_phase(tasks)
        assert len(phases) == 1
        assert len(phases[1]) == 2

    def test_group_by_phase_multiple(self, executor):
        """Multi-phase grouping."""
        tasks = [
            {"id": 1, "title": "T1", "prompt": "P1", "phase": 1},
            {"id": 2, "title": "T2", "prompt": "P2", "phase": 2},
            {"id": 3, "title": "T3", "prompt": "P3", "phase": 1},
        ]
        phases = executor._group_by_phase(tasks)
        assert len(phases) == 2
        assert len(phases[1]) == 2
        assert len(phases[2]) == 1

    def test_group_by_phase_default(self, executor):
        """Missing phase defaults to 1."""
        tasks = [{"id": 1, "title": "T1", "prompt": "P1"}]
        phases = executor._group_by_phase(tasks)
        assert 1 in phases

    @pytest.mark.asyncio
    @patch("deepr.services.batch_executor.asyncio.sleep", new_callable=AsyncMock)
    async def test_execute_campaign_single_phase(self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder):
        """Single phase campaign completes."""
        mock_context_builder.build_phase_context.return_value = ""
        mock_provider.submit_research.return_value = "provider-job-1"

        # Mock job as completed on first poll
        mock_job = MagicMock()
        mock_job.status = JobStatus.COMPLETED
        mock_job.cost = 1.00
        mock_job.tokens_used = 1000
        mock_queue.get_job.return_value = mock_job
        mock_storage.get_report.return_value = b"# Research Report"

        tasks = [{"id": 1, "title": "Task 1", "prompt": "Research X", "phase": 1}]
        result = await executor.execute_campaign(tasks, "campaign-1")

        assert result["campaign_id"] == "campaign-1"
        assert 1 in result["phases"]
        assert result["total_cost"] >= 0

    @pytest.mark.asyncio
    @patch("deepr.services.batch_executor.asyncio.sleep", new_callable=AsyncMock)
    async def test_execute_campaign_multi_phase(self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder):
        """Multi-phase campaign executes phases sequentially."""
        mock_context_builder.build_phase_context.return_value = ""
        mock_provider.submit_research.return_value = "provider-job"

        mock_job = MagicMock()
        mock_job.status = JobStatus.COMPLETED
        mock_job.cost = 0.50
        mock_job.tokens_used = 500
        mock_queue.get_job.return_value = mock_job
        mock_storage.get_report.return_value = b"Report"

        tasks = [
            {"id": 1, "title": "Foundation", "prompt": "P1", "phase": 1},
            {"id": 2, "title": "Analysis", "prompt": "P2", "phase": 2, "depends_on": [1]},
        ]
        result = await executor.execute_campaign(tasks, "campaign-2")
        assert 1 in result["phases"]
        assert 2 in result["phases"]

    @pytest.mark.asyncio
    @patch("deepr.services.batch_executor.asyncio.sleep", new_callable=AsyncMock)
    async def test_execute_campaign_tracks_costs(self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder):
        """total_cost is accumulated across tasks."""
        mock_context_builder.build_phase_context.return_value = ""
        mock_provider.submit_research.return_value = "pj"

        mock_job = MagicMock()
        mock_job.status = JobStatus.COMPLETED
        mock_job.cost = 2.00
        mock_job.tokens_used = 1000
        mock_queue.get_job.return_value = mock_job
        mock_storage.get_report.return_value = b"Report"

        tasks = [
            {"id": 1, "title": "T1", "prompt": "P1", "phase": 1},
            {"id": 2, "title": "T2", "prompt": "P2", "phase": 1},
        ]
        result = await executor.execute_campaign(tasks, "cost-test")
        assert result["total_cost"] == 4.00

    @pytest.mark.asyncio
    @patch("deepr.services.batch_executor.asyncio.sleep", new_callable=AsyncMock)
    async def test_execute_campaign_saves_results(self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder):
        """storage.save_report is called for campaign results."""
        mock_context_builder.build_phase_context.return_value = ""
        mock_provider.submit_research.return_value = "pj"

        mock_job = MagicMock()
        mock_job.status = JobStatus.COMPLETED
        mock_job.cost = 1.00
        mock_job.tokens_used = 500
        mock_queue.get_job.return_value = mock_job
        mock_storage.get_report.return_value = b"Report"

        tasks = [{"id": 1, "title": "T1", "prompt": "P1", "phase": 1}]
        await executor.execute_campaign(tasks, "save-test")
        # save_report called twice: campaign_results.json + campaign_summary.md
        assert mock_storage.save_report.call_count == 2

    @pytest.mark.asyncio
    @patch("deepr.services.batch_executor.asyncio.sleep", new_callable=AsyncMock)
    async def test_execute_phase_builds_context(self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder):
        """context_builder.build_phase_context is called for each task."""
        mock_context_builder.build_phase_context.return_value = "Prior context"
        mock_provider.submit_research.return_value = "pj"

        mock_job = MagicMock()
        mock_job.status = JobStatus.COMPLETED
        mock_job.cost = 0
        mock_job.tokens_used = 0
        mock_queue.get_job.return_value = mock_job
        mock_storage.get_report.return_value = b"R"

        tasks = [{"id": 1, "title": "T", "prompt": "P", "phase": 1}]
        await executor._execute_phase(tasks, 1, {}, "campaign")
        mock_context_builder.build_phase_context.assert_called_once()

    @pytest.mark.asyncio
    @patch("deepr.services.batch_executor.asyncio.sleep", new_callable=AsyncMock)
    async def test_execute_phase_prepends_context(self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder):
        """Non-empty context is prepended to prompt."""
        mock_context_builder.build_phase_context.return_value = "CONTEXT_PREFIX"
        mock_provider.submit_research.return_value = "pj"

        mock_job = MagicMock()
        mock_job.status = JobStatus.COMPLETED
        mock_job.cost = 0
        mock_job.tokens_used = 0
        mock_queue.get_job.return_value = mock_job
        mock_storage.get_report.return_value = b"R"

        tasks = [{"id": 1, "title": "T", "prompt": "Original prompt", "phase": 1}]
        await executor._execute_phase(tasks, 1, {}, "campaign")

        # Check the prompt submitted to provider
        submit_call = mock_provider.submit_research.call_args[0][0]
        assert "CONTEXT_PREFIX" in submit_call.prompt

    @pytest.mark.asyncio
    async def test_submit_task_enqueues_job(self, executor, mock_queue, mock_provider):
        """queue.enqueue is called."""
        mock_provider.submit_research.return_value = "provider-123"
        await executor._submit_task("Prompt", 1, "campaign-1", {"phase": 1, "title": "T"})
        mock_queue.enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_task_submits_to_provider(self, executor, mock_queue, mock_provider):
        """provider.submit_research is called."""
        mock_provider.submit_research.return_value = "provider-123"
        await executor._submit_task("Prompt", 1, "campaign-1", {"phase": 1, "title": "T"})
        mock_provider.submit_research.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_task_updates_status(self, executor, mock_queue, mock_provider):
        """queue.update_status is called with PROCESSING."""
        mock_provider.submit_research.return_value = "provider-123"
        await executor._submit_task("Prompt", 1, "campaign-1", {"phase": 1, "title": "T"})
        mock_queue.update_status.assert_called_once()
        call_kwargs = mock_queue.update_status.call_args[1]
        assert call_kwargs["status"] == JobStatus.PROCESSING

    @pytest.mark.asyncio
    @patch("deepr.services.batch_executor.asyncio.sleep", new_callable=AsyncMock)
    async def test_wait_for_completion_failed(self, mock_sleep, executor, mock_queue, mock_storage):
        """Failed job records failure."""
        mock_job = MagicMock()
        mock_job.status = JobStatus.FAILED
        mock_queue.get_job.return_value = mock_job

        tasks = [{"id": 1, "title": "Failing task"}]
        results = await executor._wait_for_completion({1: "job-fail"}, tasks)
        assert results[1]["status"] == "failed"

    def test_generate_campaign_summary_format(self, executor):
        """Summary contains phases and tasks."""
        results = {
            "campaign_id": "test-campaign",
            "started_at": "2025-01-01T00:00:00",
            "completed_at": "2025-01-01T01:00:00",
            "total_cost": 5.00,
            "phases": {1: {"task_count": 2, "completed": 2}},
            "tasks": {
                "1": {"title": "Task A", "phase": 1, "status": "completed", "cost": 2.50, "job_id": "j1"},
                "2": {"title": "Task B", "phase": 1, "status": "completed", "cost": 2.50, "job_id": "j2"},
            },
        }
        summary = executor._generate_campaign_summary(results)
        assert "# Campaign Results" in summary
        assert "Phase 1" in summary
        assert "Task A" in summary
        assert "$5.00" in summary
