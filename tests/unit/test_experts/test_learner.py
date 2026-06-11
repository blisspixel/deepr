"""Unit tests for the Autonomous Learner module - no API calls.

Tests the learning execution system including progress tracking,
pause/resume functionality, and budget protection.
"""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deepr.experts.curriculum import LearningCurriculum, LearningTopic
from deepr.experts.learner import AutonomousLearner, LearningProgress


class TestLearningProgress:
    """Test LearningProgress dataclass."""

    @pytest.fixture
    def sample_curriculum(self):
        """Create a sample curriculum for testing."""
        return LearningCurriculum(
            expert_name="Test Expert",
            domain="Testing",
            topics=[
                LearningTopic(
                    title="Topic 1",
                    description="Description 1",
                    research_prompt="Research topic 1",
                    research_mode="focus",
                    research_type="research",
                    estimated_cost=0.10,
                    estimated_minutes=5,
                    priority=1,
                ),
                LearningTopic(
                    title="Topic 2",
                    description="Description 2",
                    research_prompt="Research topic 2",
                    research_mode="focus",
                    research_type="research",
                    estimated_cost=0.10,
                    estimated_minutes=5,
                    priority=2,
                ),
                LearningTopic(
                    title="Topic 3",
                    description="Description 3",
                    research_prompt="Research topic 3",
                    research_mode="campaign",
                    research_type="research",
                    estimated_cost=0.50,
                    estimated_minutes=15,
                    priority=3,
                ),
            ],
            total_estimated_cost=0.70,
            total_estimated_minutes=25,
            generated_at=datetime.now(UTC),
        )

    def test_create_progress(self, sample_curriculum):
        """Test creating learning progress."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=[],
            failed_topics=[],
            total_cost=0.0,
            started_at=datetime.now(UTC),
        )
        assert progress.total_cost == 0.0
        assert len(progress.completed_topics) == 0
        assert progress.completed_at is None

    def test_is_complete_empty(self, sample_curriculum):
        """Test is_complete with no progress."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=[],
            failed_topics=[],
            total_cost=0.0,
            started_at=datetime.now(UTC),
        )
        assert progress.is_complete() is False

    def test_is_complete_partial(self, sample_curriculum):
        """Test is_complete with partial progress."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=["Topic 1"],
            failed_topics=[],
            total_cost=0.10,
            started_at=datetime.now(UTC),
        )
        assert progress.is_complete() is False

    def test_is_complete_all_completed(self, sample_curriculum):
        """Test is_complete when all topics completed."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=["Topic 1", "Topic 2", "Topic 3"],
            failed_topics=[],
            total_cost=0.70,
            started_at=datetime.now(UTC),
        )
        assert progress.is_complete() is True

    def test_is_complete_mixed(self, sample_curriculum):
        """Test is_complete with mix of completed and failed."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=["Topic 1", "Topic 2"],
            failed_topics=["Topic 3"],
            total_cost=0.20,
            started_at=datetime.now(UTC),
        )
        assert progress.is_complete() is True

    def test_success_rate_empty(self, sample_curriculum):
        """Test success rate with no progress."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=[],
            failed_topics=[],
            total_cost=0.0,
            started_at=datetime.now(UTC),
        )
        assert progress.success_rate() == 0.0

    def test_success_rate_all_success(self, sample_curriculum):
        """Test success rate with all completed."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=["Topic 1", "Topic 2", "Topic 3"],
            failed_topics=[],
            total_cost=0.70,
            started_at=datetime.now(UTC),
        )
        assert progress.success_rate() == 1.0

    def test_success_rate_all_failed(self, sample_curriculum):
        """Test success rate with all failed."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=[],
            failed_topics=["Topic 1", "Topic 2", "Topic 3"],
            total_cost=0.0,
            started_at=datetime.now(UTC),
        )
        assert progress.success_rate() == 0.0

    def test_success_rate_mixed(self, sample_curriculum):
        """Test success rate with mixed results."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=["Topic 1", "Topic 2"],
            failed_topics=["Topic 3"],
            total_cost=0.20,
            started_at=datetime.now(UTC),
        )
        assert progress.success_rate() == pytest.approx(2 / 3, rel=0.01)


class TestAutonomousLearnerProgressPersistence:
    """Test pause/resume functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        config = MagicMock()
        config.provider = MagicMock()
        config.provider.openai_api_key = "test-key"
        config.storage = MagicMock()
        config.storage.local_path = "output"
        return config

    @pytest.fixture
    def mock_expert_store(self):
        """Create a mock ExpertStore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MagicMock()
            knowledge_dir = Path(tmpdir) / "knowledge"
            knowledge_dir.mkdir(parents=True)
            store.get_knowledge_dir.return_value = knowledge_dir
            yield store, knowledge_dir

    def test_save_learning_progress(self, mock_config, mock_expert_store):
        """Test saving learning progress."""
        store, knowledge_dir = mock_expert_store

        with (
            patch("deepr.experts.learner.create_provider"),
            patch("deepr.experts.learner.create_storage"),
            patch("deepr.experts.learner.ExpertStore", return_value=store),
        ):
            learner = AutonomousLearner(mock_config)

            # Create mock expert and progress
            expert = MagicMock()
            expert.name = "Test Expert"

            curriculum = LearningCurriculum(
                expert_name="Test Expert",
                domain="Testing",
                topics=[
                    LearningTopic(
                        title="Topic 1",
                        description="Description 1",
                        research_prompt="Research 1",
                        research_mode="focus",
                        research_type="research",
                        estimated_cost=0.10,
                        estimated_minutes=5,
                        priority=1,
                    ),
                    LearningTopic(
                        title="Topic 2",
                        description="Description 2",
                        research_prompt="Research 2",
                        research_mode="focus",
                        research_type="research",
                        estimated_cost=0.10,
                        estimated_minutes=5,
                        priority=2,
                    ),
                ],
                total_estimated_cost=0.20,
                total_estimated_minutes=10,
                generated_at=datetime.now(UTC),
            )

            progress = LearningProgress(
                curriculum=curriculum,
                completed_topics=["Topic 1"],
                failed_topics=[],
                total_cost=0.10,
                started_at=datetime.now(UTC),
            )

            remaining_topics = [curriculum.topics[1]]  # Topic 2 remaining

            # Save progress
            learner._save_learning_progress(expert, progress, remaining_topics)

            # Verify file was created
            progress_file = knowledge_dir / "learning_progress.json"
            assert progress_file.exists()

            # Verify content
            with open(progress_file) as f:
                saved_data = json.load(f)

            assert saved_data["expert_name"] == "Test Expert"
            assert saved_data["completed_topics"] == ["Topic 1"]
            assert len(saved_data["remaining_topics"]) == 1
            assert saved_data["remaining_topics"][0]["title"] == "Topic 2"

    def test_load_learning_progress(self, mock_config, mock_expert_store):
        """Test loading saved learning progress."""
        store, knowledge_dir = mock_expert_store

        # Create progress file
        progress_data = {
            "expert_name": "Test Expert",
            "paused_at": datetime.now(UTC).isoformat(),
            "completed_topics": ["Topic 1"],
            "failed_topics": [],
            "remaining_topics": [
                {
                    "title": "Topic 2",
                    "research_prompt": "Research 2",
                    "research_mode": "focus",
                    "research_type": "research",
                    "estimated_cost": 0.10,
                    "estimated_minutes": 5,
                }
            ],
            "total_cost_so_far": 0.10,
            "started_at": datetime.now(UTC).isoformat(),
            "reason": "daily_or_monthly_limit",
        }

        progress_file = knowledge_dir / "learning_progress.json"
        with open(progress_file, "w") as f:
            json.dump(progress_data, f)

        with (
            patch("deepr.experts.learner.create_provider"),
            patch("deepr.experts.learner.create_storage"),
            patch("deepr.experts.learner.ExpertStore", return_value=store),
        ):
            learner = AutonomousLearner(mock_config)

            # Load progress
            loaded = learner.load_learning_progress("Test Expert")

            assert loaded is not None
            assert loaded["expert_name"] == "Test Expert"
            assert loaded["completed_topics"] == ["Topic 1"]
            assert len(loaded["remaining_topics"]) == 1

    def test_load_learning_progress_not_found(self, mock_config, mock_expert_store):
        """Test loading when no saved progress exists."""
        store, _knowledge_dir = mock_expert_store

        with (
            patch("deepr.experts.learner.create_provider"),
            patch("deepr.experts.learner.create_storage"),
            patch("deepr.experts.learner.ExpertStore", return_value=store),
        ):
            learner = AutonomousLearner(mock_config)

            # Load progress (should return None)
            loaded = learner.load_learning_progress("Nonexistent Expert")

            assert loaded is None

    def test_clear_learning_progress(self, mock_config, mock_expert_store):
        """Test clearing saved learning progress."""
        store, knowledge_dir = mock_expert_store

        # Create progress file
        progress_file = knowledge_dir / "learning_progress.json"
        progress_file.write_text('{"test": "data"}')
        assert progress_file.exists()

        with (
            patch("deepr.experts.learner.create_provider"),
            patch("deepr.experts.learner.create_storage"),
            patch("deepr.experts.learner.ExpertStore", return_value=store),
        ):
            learner = AutonomousLearner(mock_config)

            # Clear progress
            learner.clear_learning_progress("Test Expert")

            # Verify file was deleted
            assert not progress_file.exists()

    def test_clear_learning_progress_not_found(self, mock_config, mock_expert_store):
        """Test clearing when no saved progress exists (should not error)."""
        store, _knowledge_dir = mock_expert_store

        with (
            patch("deepr.experts.learner.create_provider"),
            patch("deepr.experts.learner.create_storage"),
            patch("deepr.experts.learner.ExpertStore", return_value=store),
        ):
            learner = AutonomousLearner(mock_config)

            # Should not raise error
            learner.clear_learning_progress("Nonexistent Expert")


class TestLearningProgressEdgeCases:
    """Test edge cases in learning progress."""

    def test_progress_with_empty_curriculum(self):
        """Test progress with empty curriculum."""
        curriculum = LearningCurriculum(
            expert_name="Empty Expert",
            domain="Empty",
            topics=[],
            total_estimated_cost=0.0,
            total_estimated_minutes=0,
            generated_at=datetime.now(UTC),
        )
        progress = LearningProgress(
            curriculum=curriculum, completed_topics=[], failed_topics=[], total_cost=0.0, started_at=datetime.now(UTC)
        )
        # Empty curriculum is technically complete
        assert progress.is_complete() is True
        assert progress.success_rate() == 0.0

    def test_progress_completed_at_set(self):
        """Test progress with completed_at timestamp."""
        curriculum = LearningCurriculum(
            expert_name="Test",
            domain="Test",
            topics=[
                LearningTopic(
                    title="Topic",
                    description="Description",
                    research_prompt="Research",
                    research_mode="focus",
                    research_type="research",
                    estimated_cost=0.10,
                    estimated_minutes=5,
                    priority=1,
                )
            ],
            total_estimated_cost=0.10,
            total_estimated_minutes=5,
            generated_at=datetime.now(UTC),
        )
        now = datetime.now(UTC)
        progress = LearningProgress(
            curriculum=curriculum,
            completed_topics=["Topic"],
            failed_topics=[],
            total_cost=0.10,
            started_at=now - timedelta(minutes=5),
            completed_at=now,
        )
        assert progress.completed_at is not None
        assert progress.is_complete() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestDurableJobTracking:
    """Learner research jobs must be recoverable and correctly credited.

    Live-validation findings: submitted jobs lived only at the provider
    (orphaned if the run was interrupted), and the final summary always
    said "Completed: 0 topics" because the poll loop never credited
    progress with the topics it completed.
    """

    def _topic(self, title="Topic 1"):
        from deepr.experts.curriculum import LearningTopic

        return LearningTopic(
            title=title,
            description="d",
            research_prompt="Research it",
            research_mode="focus",
            research_type="research",
            estimated_cost=0.10,
            estimated_minutes=5,
            priority=1,
        )

    def _learner(self, tmp_path):
        config = {
            "openai_api_key": "test-key",
            "storage_path": str(tmp_path / "out"),
            "queue_db_path": str(tmp_path / "queue" / "q.db"),
        }
        return AutonomousLearner(config)

    @pytest.mark.asyncio
    async def test_record_job_in_queue_creates_processing_job(self, tmp_path):
        from deepr.queue import create_queue
        from deepr.queue.base import JobStatus

        learner = self._learner(tmp_path)
        expert = MagicMock()
        expert.name = "Test Expert"

        local_id = await learner._record_job_in_queue("resp_abc123", self._topic(), expert)

        assert local_id is not None
        assert local_id.startswith("learn-")
        queue = create_queue("local", db_path=str(tmp_path / "queue" / "q.db"))
        job = await queue.get_job(local_id)
        assert job is not None
        assert job.status is JobStatus.PROCESSING
        assert job.provider_job_id == "resp_abc123"
        assert job.metadata["expert_name"] == "Test Expert"
        assert job.metadata["source"] == "expert_learn"

    @pytest.mark.asyncio
    async def test_sync_marks_completed_with_cost(self, tmp_path):
        from deepr.queue import create_queue
        from deepr.queue.base import JobStatus

        learner = self._learner(tmp_path)
        expert = MagicMock()
        expert.name = "Test Expert"
        local_id = await learner._record_job_in_queue("resp_done", self._topic(), expert)

        await learner._sync_job_status_in_queue("resp_done", "completed", 0.04)

        queue = create_queue("local", db_path=str(tmp_path / "queue" / "q.db"))
        job = await queue.get_job(local_id)
        assert job.status is JobStatus.COMPLETED
        assert job.cost == 0.04

    @pytest.mark.asyncio
    async def test_sync_unknown_job_is_noop(self, tmp_path):
        learner = self._learner(tmp_path)
        # No queue record exists - must not raise
        await learner._sync_job_status_in_queue("resp_never_recorded", "completed", 0.01)

    @pytest.mark.asyncio
    async def test_poll_credits_completed_topics(self, tmp_path):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from deepr.experts.curriculum import LearningCurriculum

        learner = self._learner(tmp_path)
        learner.research = MagicMock()
        learner.research.provider.get_status = AsyncMock(
            return_value=SimpleNamespace(status="completed", usage=SimpleNamespace(cost=0.05))
        )
        learner._integrate_reports = AsyncMock()
        learner.cost_safety = MagicMock()

        expert = MagicMock()
        expert.name = "Test Expert"
        session = MagicMock()
        session.is_circuit_open = False
        session.session_id = "s1"

        curriculum = LearningCurriculum(
            expert_name="Test Expert",
            domain="t",
            topics=[self._topic()],
            total_estimated_cost=0.10,
            total_estimated_minutes=5,
            generated_at=datetime.now(UTC),
        )
        progress = LearningProgress(
            curriculum=curriculum,
            completed_topics=[],
            failed_topics=[],
            total_cost=0.0,
            started_at=datetime.now(UTC),
            job_topics={"resp_1": "Topic 1"},
        )

        await learner._poll_and_integrate_reports(expert, ["resp_1"], session, None, progress)

        assert progress.completed_topics == ["Topic 1"]
        assert progress.failed_topics == []
        assert progress.success_rate() == 1.0
        learner._integrate_reports.assert_awaited()

    @pytest.mark.asyncio
    async def test_poll_credits_failed_topics(self, tmp_path):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from deepr.experts.curriculum import LearningCurriculum

        learner = self._learner(tmp_path)
        learner.research = MagicMock()
        learner.research.provider.get_status = AsyncMock(return_value=SimpleNamespace(status="failed", usage=None))
        learner._integrate_reports = AsyncMock()
        learner.cost_safety = MagicMock()

        expert = MagicMock()
        expert.name = "Test Expert"
        session = MagicMock()
        session.is_circuit_open = False
        session.session_id = "s1"

        curriculum = LearningCurriculum(
            expert_name="Test Expert",
            domain="t",
            topics=[self._topic()],
            total_estimated_cost=0.10,
            total_estimated_minutes=5,
            generated_at=datetime.now(UTC),
        )
        progress = LearningProgress(
            curriculum=curriculum,
            completed_topics=[],
            failed_topics=[],
            total_cost=0.0,
            started_at=datetime.now(UTC),
            job_topics={"resp_1": "Topic 1"},
        )

        await learner._poll_and_integrate_reports(expert, ["resp_1"], session, None, progress)

        assert progress.failed_topics == ["Topic 1"]
        assert progress.completed_topics == []
        learner._integrate_reports.assert_not_awaited()
