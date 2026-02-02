"""Tests for research API service."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from deepr.queue.base import JobStatus


@pytest.mark.asyncio
class TestResearchAPI:
    """Test ResearchAPI job management."""

    @pytest.fixture
    def mock_queue(self):
        q = AsyncMock()
        return q

    @pytest.fixture
    def api(self, mock_queue):
        with patch("deepr.services.research_api.SQLiteQueue", return_value=mock_queue):
            from deepr.services.research_api import ResearchAPI
            mock_config = MagicMock()
            return ResearchAPI(config=mock_config)

    async def test_init_stores_config(self):
        """config attribute is set."""
        with patch("deepr.services.research_api.SQLiteQueue"):
            from deepr.services.research_api import ResearchAPI
            config = MagicMock()
            api = ResearchAPI(config=config)
            assert api.config is config

    async def test_submit_focus_mode_default_model(self, api, mock_queue):
        """focus mode defaults to o4-mini."""
        job_id = await api.submit_research("Test prompt", mode="focus")
        enqueued_job = mock_queue.enqueue.call_args[0][0]
        assert enqueued_job.model == "o4-mini-deep-research"

    async def test_submit_team_mode_default_model(self, api, mock_queue):
        """team mode defaults to o3."""
        job_id = await api.submit_research("Test prompt", mode="team")
        enqueued_job = mock_queue.enqueue.call_args[0][0]
        assert enqueued_job.model == "o3-deep-research"

    async def test_submit_docs_mode_default_model(self, api, mock_queue):
        """docs mode defaults to o4-mini."""
        job_id = await api.submit_research("Test prompt", mode="docs")
        enqueued_job = mock_queue.enqueue.call_args[0][0]
        assert enqueued_job.model == "o4-mini-deep-research"

    async def test_submit_custom_model_override(self, api, mock_queue):
        """Explicit model overrides mode default."""
        await api.submit_research("Test", model="custom-model")
        enqueued_job = mock_queue.enqueue.call_args[0][0]
        assert enqueued_job.model == "custom-model"

    async def test_submit_returns_job_id(self, api, mock_queue):
        """Returns a string job ID."""
        job_id = await api.submit_research("Test")
        assert isinstance(job_id, str)
        assert job_id.startswith("research-")

    async def test_submit_enqueues_job(self, api, mock_queue):
        """queue.enqueue is called."""
        await api.submit_research("Test prompt")
        mock_queue.enqueue.assert_called_once()

    async def test_get_job_status_found(self, api, mock_queue):
        """Returns status dict when job exists."""
        mock_job = MagicMock()
        mock_job.id = "test-123"
        mock_job.status = JobStatus.QUEUED
        mock_job.prompt = "Test"
        mock_job.model = "o4-mini"
        mock_job.provider = "openai"
        mock_job.submitted_at = None
        mock_job.started_at = None
        mock_job.completed_at = None
        mock_job.cost = 0.0
        mock_job.last_error = None
        mock_queue.get_job.return_value = mock_job

        result = await api.get_job_status("test-123")
        assert result["id"] == "test-123"
        assert result["status"] == "queued"

    async def test_get_job_status_not_found(self, api, mock_queue):
        """Raises ValueError when job not found."""
        mock_queue.get_job.return_value = None
        with pytest.raises(ValueError, match="Job not found"):
            await api.get_job_status("nonexistent")

    async def test_get_job_result_completed(self, api, mock_queue):
        """Returns result dict for completed job."""
        mock_job = MagicMock()
        mock_job.id = "done-123"
        mock_job.status = JobStatus.COMPLETED
        mock_job.prompt = "Test"
        mock_job.report_paths = {"markdown": "reports/done-123/report.md"}
        mock_job.cost = 1.50
        mock_job.tokens_used = 5000
        mock_job.completed_at = None
        mock_queue.get_job.return_value = mock_job

        result = await api.get_job_result("done-123")
        assert result["id"] == "done-123"
        assert result["cost"] == 1.50

    async def test_get_job_result_not_completed(self, api, mock_queue):
        """Raises ValueError for non-completed job."""
        mock_job = MagicMock()
        mock_job.status = JobStatus.PROCESSING
        mock_queue.get_job.return_value = mock_job
        with pytest.raises(ValueError, match="Job not completed"):
            await api.get_job_result("pending-123")

    async def test_cancel_job_delegates(self, api, mock_queue):
        """cancel_job delegates to queue.cancel."""
        await api.cancel_job("cancel-123")
        mock_queue.cancel.assert_called_once_with("cancel-123")
