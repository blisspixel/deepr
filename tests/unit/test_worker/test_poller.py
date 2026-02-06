"""Tests for job poller worker."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta


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
        with patch("deepr.worker.poller.load_config", return_value=mock_config), \
             patch("deepr.worker.poller.create_queue") as mock_cq, \
             patch("deepr.worker.poller.create_storage") as mock_cs, \
             patch("deepr.worker.poller.create_provider") as mock_cp, \
             patch("deepr.worker.poller.CostController"):
            mock_cq.return_value = AsyncMock()
            mock_cs.return_value = AsyncMock()
            mock_cp.return_value = AsyncMock()
            from deepr.worker.poller import JobPoller
            p = JobPoller(poll_interval=5)
            return p

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
        assert "Rate limit" in call_kwargs["error"]

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
        mock_job.submitted_at = datetime.now(timezone.utc) - timedelta(minutes=15)

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
    async def test_handle_failure_updates_queue(self, poller):
        """_handle_failure updates queue status to FAILED."""
        mock_job = MagicMock()
        mock_job.id = "fail-handle"

        await poller._handle_failure(mock_job, "Test error")
        poller.queue.update_status.assert_called_once()
        call_kwargs = poller.queue.update_status.call_args[1]
        assert call_kwargs["error"] == "Test error"

    @pytest.mark.asyncio
    async def test_completion_error_becomes_failure(self, poller):
        """Error during completion handling triggers failure path."""
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
        # Should call _handle_failure, which calls update_status
        poller.queue.update_status.assert_called()
