"""Tests for job poller worker."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.queue.base import JobStatus, ResearchJob


class TestJobPoller:
    """Test JobPoller polling and job management."""

    @pytest.fixture
    def mock_config(self):
        return {
            "queue": "local",
            "queue_db_path": "test/queue.db",
            "storage": "local",
            "results_dir": "test/results",
            "provider": "openai",
            "api_key": "sk-test",
            "max_cost_per_job": 5.0,
            "max_daily_cost": 25.0,
            "max_monthly_cost": 200.0,
        }

    @pytest.fixture
    def poller(self, mock_config):
        with (
            patch("deepr.worker.poller.load_config", return_value=mock_config),
            patch("deepr.worker.poller.create_queue") as mock_cq,
            patch("deepr.worker.poller.create_storage") as mock_cs,
            patch("deepr.worker.poller.create_provider") as mock_cp,
            patch("deepr.worker.poller.CostController"),
            patch("deepr.worker.poller.reconcile_research_cost_from_ledger", return_value=True),
        ):
            mock_cq.return_value = AsyncMock()
            mock_cs.return_value = AsyncMock()
            mock_cp.return_value = AsyncMock()
            from deepr.worker.poller import JobPoller

            p = JobPoller(poll_interval=5)
            yield p

    def test_init_sets_poll_interval(self, poller):
        """poll_interval stored correctly."""
        assert poller.poll_interval == 5

    def test_init_running_false(self, poller):
        """Poller starts not running."""
        assert poller.running is False

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, poller):
        """stop() sets running to False."""
        poller.running = True
        await poller.stop()
        assert poller.running is False

    @pytest.mark.asyncio
    async def test_poll_cycle_no_jobs(self, poller):
        """No active jobs returns quietly."""
        poller.queue.list_jobs.return_value = []
        await poller._poll_cycle()
        poller.queue.list_jobs.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_cycle_with_jobs(self, poller):
        """Active jobs trigger _check_job_status calls."""
        mock_job = MagicMock()
        mock_job.id = "job-1"
        mock_job.provider_job_id = "pj-1"
        poller.queue.list_jobs.return_value = [mock_job]

        mock_resp = MagicMock()
        mock_resp.status = "in_progress"
        poller.provider.get_status.return_value = mock_resp

        await poller._poll_cycle()
        poller.provider.get_status.assert_called_once_with("pj-1")

    @pytest.mark.asyncio
    async def test_poll_cycle_pages_beyond_first_hundred(self, poller):
        """Processing backlog larger than one page must not starve older jobs."""
        page1 = []
        for i in range(100):
            job = MagicMock()
            job.id = f"new-{i}"
            job.provider_job_id = f"pj-new-{i}"
            page1.append(job)
        older = MagicMock()
        older.id = "old-1"
        older.provider_job_id = "pj-old-1"

        poller.queue.list_jobs = AsyncMock(side_effect=[page1, [older]])
        mock_resp = MagicMock()
        mock_resp.status = "in_progress"
        poller.provider.get_status.return_value = mock_resp

        await poller._poll_cycle()

        assert poller.queue.list_jobs.await_count == 2
        poller.queue.list_jobs.assert_any_await(status=JobStatus.PROCESSING, limit=100, offset=0)
        poller.queue.list_jobs.assert_any_await(status=JobStatus.PROCESSING, limit=100, offset=100)
        assert poller.provider.get_status.await_count == 101

    @pytest.mark.asyncio
    async def test_check_job_skips_missing_provider_id(self, poller):
        """Jobs without provider_job_id are skipped."""
        mock_job = MagicMock()
        mock_job.id = "no-pj"
        mock_job.provider_job_id = None
        await poller._check_job_status(mock_job)
        poller.provider.get_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_job_completed(self, poller):
        """Completed job triggers _handle_completion."""
        mock_job = MagicMock()
        mock_job.id = "done-job"
        mock_job.provider_job_id = "pj-done"
        mock_job.prompt = "Test"
        mock_job.model = "o3"

        mock_resp = MagicMock()
        mock_resp.status = "completed"
        mock_resp.output = []
        mock_resp.usage = MagicMock(cost=1.0, total_tokens=5000)
        poller.provider.get_status.return_value = mock_resp

        await poller._check_job_status(mock_job)
        poller.storage.save_report.assert_called_once()
        poller.queue.update_status.assert_called()

    @pytest.mark.asyncio
    async def test_check_job_failed(self, poller):
        """Failed job triggers _handle_failure."""
        mock_job = MagicMock()
        mock_job.id = "fail-job"
        mock_job.provider_job_id = "pj-fail"

        mock_resp = MagicMock()
        mock_resp.status = "failed"
        mock_resp.error = "Rate limit exceeded"
        poller.provider.get_status.return_value = mock_resp

        await poller._check_job_status(mock_job)
        poller.queue.update_status.assert_called_once()
        call_kwargs = poller.queue.update_status.call_args[1]
        assert call_kwargs["error"] == "Provider reported research failure"

    @pytest.mark.asyncio
    async def test_check_job_in_progress_no_action(self, poller):
        """In-progress job does not update queue."""
        mock_job = MagicMock()
        mock_job.id = "prog-job"
        mock_job.provider_job_id = "pj-prog"

        mock_resp = MagicMock()
        mock_resp.status = "in_progress"
        poller.provider.get_status.return_value = mock_resp

        await poller._check_job_status(mock_job)
        poller.queue.update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_stuck_job_detection(self, poller):
        """Jobs queued >10 minutes are auto-cancelled."""
        mock_job = MagicMock()
        mock_job.id = "stuck-job"
        mock_job.provider_job_id = "pj-stuck"
        mock_job.submitted_at = datetime.now(UTC) - timedelta(minutes=15)

        mock_resp = MagicMock()
        mock_resp.status = "queued"
        poller.provider.get_status.return_value = mock_resp

        await poller._check_job_status(mock_job)
        poller.provider.cancel_job.assert_called_once_with("pj-stuck")
        poller.queue.update_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_completion_saves_and_updates(self, poller):
        """_handle_completion saves report and updates queue."""
        mock_job = MagicMock()
        mock_job.id = "comp-job"
        mock_job.prompt = "Test prompt"
        mock_job.model = "o3"
        mock_job.provider_job_id = "pj"

        mock_resp = MagicMock()
        mock_resp.output = [{"type": "message", "content": [{"text": "Result text"}]}]
        mock_resp.usage = MagicMock(cost=2.0, total_tokens=10000)

        await poller._handle_completion(mock_job, mock_resp)
        poller.storage.save_report.assert_called_once()
        poller.queue.update_results.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_completion_settles_persisted_cost_reservation(self, poller):
        mock_job = MagicMock()
        mock_job.id = "reserved-job"
        mock_job.prompt = "Test prompt"
        mock_job.model = "o3"
        mock_job.provider = "openai"
        mock_job.provider_job_id = "provider-job"
        mock_job.metadata = {"cost_reservation_id": "reservation"}
        response = MagicMock()
        response.output = []
        response.usage = MagicMock(cost=0.6, total_tokens=120)
        reservation = MagicMock()

        with (
            patch("deepr.worker.poller.restore_research_cost_reservation", return_value=reservation),
            patch("deepr.worker.poller.settle_research_cost") as settle,
        ):
            await poller._handle_completion(mock_job, response)

        settle.assert_called_once_with(
            reservation,
            actual_cost=0.6,
            tokens=120,
            request_id="provider-job",
            source="worker.poller._handle_completion",
        )

    @pytest.mark.asyncio
    async def test_handle_failure_updates_queue(self, poller):
        """_handle_failure updates queue status to FAILED."""
        mock_job = MagicMock()
        mock_job.id = "fail-handle"

        await poller._handle_failure(mock_job, "Test error")
        poller.queue.update_status.assert_called_once()
        call_kwargs = poller.queue.update_status.call_args[1]
        assert call_kwargs["error"] == "Test error"

    @pytest.mark.asyncio
    async def test_handle_failure_settles_accepted_job_estimate(self, poller):
        mock_job = MagicMock()
        mock_job.id = "accepted-failure"
        mock_job.model = "o3"
        mock_job.provider = "openai"
        mock_job.provider_job_id = "provider-job"
        mock_job.metadata = {"cost_reservation_id": "reservation"}
        reservation = MagicMock()

        with (
            patch("deepr.worker.poller.restore_research_cost_reservation", return_value=reservation),
            patch("deepr.worker.poller.settle_research_cost") as settle,
        ):
            await poller._handle_failure(mock_job, "Provider failed")

        settle.assert_called_once_with(
            reservation,
            actual_cost=None,
            request_id="provider-job",
            source="worker.poller._handle_failure",
        )

    @pytest.mark.asyncio
    async def test_handle_failure_retains_active_state_when_cost_closure_fails(self, poller):
        mock_job = ResearchJob(
            id="cost-open",
            prompt="test",
            status=JobStatus.PROCESSING,
            provider_job_id="provider-job",
        )
        poller.queue.update_status = AsyncMock()

        with patch(
            "deepr.worker.poller.restore_research_cost_reservation",
            side_effect=RuntimeError("ledger unavailable"),
        ):
            await poller._handle_failure(mock_job, "Provider cancelled", status=JobStatus.CANCELLED)

        poller.queue.update_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_completion_error_retains_processing_for_retry(self, poller):
        """Local completion failure must not rewrite provider success."""
        mock_job = MagicMock()
        mock_job.id = "err-comp"
        mock_job.prompt = "Test"
        mock_job.model = "o3"
        mock_job.provider_job_id = "pj"

        mock_resp = MagicMock()
        mock_resp.output = []
        mock_resp.usage = None
        poller.storage.save_report.side_effect = Exception("Storage down")

        await poller._handle_completion(mock_job, mock_resp)
        poller.queue.update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_completion_update_results_failure_retains_processing(self, poller):
        """Result persistence failure must remain retryable."""
        mock_job = MagicMock()
        mock_job.id = "comp-results-fail"
        mock_job.prompt = "Test prompt"
        mock_job.model = "o3"
        mock_job.provider_job_id = "pj"

        mock_resp = MagicMock()
        mock_resp.output = [{"type": "message", "content": [{"text": "Result text"}]}]
        mock_resp.usage = MagicMock(cost=2.0, total_tokens=10000)

        poller.queue.update_results.return_value = False

        await poller._handle_completion(mock_job, mock_resp)

        poller.queue.update_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_failure_logs_when_status_not_persisted(self, poller, caplog):
        """A failed status write should emit an explicit error log."""
        mock_job = MagicMock()
        mock_job.id = "fail-persist"

        poller.queue.update_status.return_value = False

        with caplog.at_level("ERROR"):
            await poller._handle_failure(mock_job, "Test error")

        assert "Failed to persist FAILED status for job fail-persist" in caplog.text
