"""Tests for batch executor service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
    async def test_execute_campaign_single_phase(
        self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder
    ):
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
    async def test_execute_campaign_multi_phase(
        self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder
    ):
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
    async def test_execute_campaign_tracks_costs(
        self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder
    ):
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
    async def test_execute_campaign_saves_results(
        self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder
    ):
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
    async def test_execute_phase_builds_context(
        self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder
    ):
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
    async def test_execute_phase_prepends_context(
        self, mock_sleep, executor, mock_queue, mock_provider, mock_storage, mock_context_builder
    ):
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
        queued_job = mock_queue.enqueue.call_args.args[0]
        assert queued_job.metadata["cost_reservation_id"]
        assert queued_job.metadata["cost_reservation_estimated_usd"] > 0

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
    async def test_submit_task_preserves_selected_model(self, executor, mock_queue, mock_provider):
        """The selected campaign model reaches admission, queue, and provider."""
        mock_provider.submit_research.return_value = "provider-123"
        reservation = MagicMock()
        reservation.metadata.return_value = {
            "cost_reservation_id": "reservation-1",
            "cost_reservation_estimated_usd": 1.0,
        }

        with (
            patch(
                "deepr.experts.research_cost_gate.reserve_configured_research_cost",
                return_value=(1.0, reservation),
            ) as reserve,
            patch(
                "deepr.services.research_submission.dispatch_reserved_research",
                new_callable=AsyncMock,
            ) as dispatch,
        ):
            await executor._submit_task(
                "Prompt",
                1,
                "campaign-1",
                {"phase": 1, "title": "T"},
                model="o3-deep-research",
            )

        queued_job = dispatch.await_args.kwargs["job"]
        submitted_request = dispatch.await_args.kwargs["request"]
        assert reserve.call_args.kwargs["model"] == "o3-deep-research"
        assert queued_job.model == "o3-deep-research"
        assert submitted_request.model == "o3-deep-research"

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

    @pytest.mark.asyncio
    @patch("deepr.services.batch_executor.asyncio.sleep", new_callable=AsyncMock)
    async def test_wait_for_completion_polls_provider_without_external_worker(
        self, mock_sleep, executor, mock_queue, mock_storage
    ):
        processing = MagicMock(status=JobStatus.PROCESSING, provider_job_id="provider-1")
        completed = MagicMock(
            status=JobStatus.COMPLETED,
            provider_job_id="provider-1",
            report_paths={"markdown": "report.md"},
            cost=0.2,
            tokens_used=10,
        )
        mock_queue.get_job.side_effect = [processing, completed]
        mock_storage.get_report.return_value = b"Report"
        poller = MagicMock(check_job_status=AsyncMock())

        with patch("deepr.worker.poller.JobPoller", return_value=poller):
            results = await executor._wait_for_completion(
                {1: "job-1"},
                [{"id": 1, "title": "Task"}],
            )

        poller.check_job_status.assert_awaited_once_with(processing)
        assert results[1]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_wait_timeout_retains_pending_job_when_cancel_is_unconfirmed(self, executor, mock_queue):
        from deepr.services.research_cancellation import ResearchCancellationOutcome

        processing = MagicMock(status=JobStatus.PROCESSING, provider_job_id="provider-1")
        mock_queue.get_job.return_value = processing
        outcome = ResearchCancellationOutcome(queue_cancelled=False, cost_closed=False)

        with (
            patch("time.monotonic", side_effect=[0.0, 2.0]),
            patch(
                "deepr.services.research_cancellation.cancel_reserved_research",
                new_callable=AsyncMock,
                return_value=outcome,
            ) as cancel,
        ):
            results = await executor._wait_for_completion(
                {1: "job-1"},
                [{"id": 1, "title": "Task"}],
                max_wait_seconds=1.0,
            )

        cancel.assert_awaited_once()
        assert results[1]["status"] == "pending"
        assert "tracking remains active" in results[1]["error"]

    @pytest.mark.asyncio
    async def test_campaign_pauses_before_later_phase_when_work_is_pending(self, executor):
        pending_result = {
            1: {
                "title": "Foundation",
                "job_id": "job-1",
                "status": "pending",
                "result": "",
                "cost": 0.0,
            }
        }
        executor._execute_phase = AsyncMock(return_value=(pending_result, None))
        executor._save_campaign_results = AsyncMock()
        tasks = [
            {"id": 1, "title": "Foundation", "prompt": "P1", "phase": 1},
            {"id": 2, "title": "Analysis", "prompt": "P2", "phase": 2, "depends_on": [1]},
        ]

        result = await executor.execute_campaign(tasks, "campaign-pending")

        assert result["status"] == "pending"
        assert executor._execute_phase.await_count == 1
        assert 2 not in result["phases"]

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
