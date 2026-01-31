"""Unit tests for the Autonomous Learner module - no API calls.

Tests the learning execution system including progress tracking,
pause/resume functionality, and budget protection.
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from deepr.experts.learner import LearningProgress, AutonomousLearner
from deepr.experts.curriculum import LearningCurriculum, LearningTopic


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
                    priority=1
                ),
                LearningTopic(
                    title="Topic 2",
                    description="Description 2",
                    research_prompt="Research topic 2",
                    research_mode="focus",
                    research_type="research",
                    estimated_cost=0.10,
                    estimated_minutes=5,
                    priority=2
                ),
                LearningTopic(
                    title="Topic 3",
                    description="Description 3",
                    research_prompt="Research topic 3",
                    research_mode="campaign",
                    research_type="research",
                    estimated_cost=0.50,
                    estimated_minutes=15,
                    priority=3
                )
            ],
            total_estimated_cost=0.70,
            total_estimated_minutes=25,
            generated_at=datetime.utcnow()
        )

    def test_create_progress(self, sample_curriculum):
        """Test creating learning progress."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=[],
            failed_topics=[],
            total_cost=0.0,
            started_at=datetime.utcnow()
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
            started_at=datetime.utcnow()
        )
        assert progress.is_complete() is False

    def test_is_complete_partial(self, sample_curriculum):
        """Test is_complete with partial progress."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=["Topic 1"],
            failed_topics=[],
            total_cost=0.10,
            started_at=datetime.utcnow()
        )
        assert progress.is_complete() is False

    def test_is_complete_all_completed(self, sample_curriculum):
        """Test is_complete when all topics completed."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=["Topic 1", "Topic 2", "Topic 3"],
            failed_topics=[],
            total_cost=0.70,
            started_at=datetime.utcnow()
        )
        assert progress.is_complete() is True

    def test_is_complete_mixed(self, sample_curriculum):
        """Test is_complete with mix of completed and failed."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=["Topic 1", "Topic 2"],
            failed_topics=["Topic 3"],
            total_cost=0.20,
            started_at=datetime.utcnow()
        )
        assert progress.is_complete() is True

    def test_success_rate_empty(self, sample_curriculum):
        """Test success rate with no progress."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=[],
            failed_topics=[],
            total_cost=0.0,
            started_at=datetime.utcnow()
        )
        assert progress.success_rate() == 0.0

    def test_success_rate_all_success(self, sample_curriculum):
        """Test success rate with all completed."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=["Topic 1", "Topic 2", "Topic 3"],
            failed_topics=[],
            total_cost=0.70,
            started_at=datetime.utcnow()
        )
        assert progress.success_rate() == 1.0

    def test_success_rate_all_failed(self, sample_curriculum):
        """Test success rate with all failed."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=[],
            failed_topics=["Topic 1", "Topic 2", "Topic 3"],
            total_cost=0.0,
            started_at=datetime.utcnow()
        )
        assert progress.success_rate() == 0.0

    def test_success_rate_mixed(self, sample_curriculum):
        """Test success rate with mixed results."""
        progress = LearningProgress(
            curriculum=sample_curriculum,
            completed_topics=["Topic 1", "Topic 2"],
            failed_topics=["Topic 3"],
            total_cost=0.20,
            started_at=datetime.utcnow()
        )
        assert progress.success_rate() == pytest.approx(2/3, rel=0.01)


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
        
        with patch('deepr.experts.learner.create_provider'), \
             patch('deepr.experts.learner.create_storage'), \
             patch('deepr.experts.learner.ExpertStore', return_value=store):
            
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
                        priority=1
                    ),
                    LearningTopic(
                        title="Topic 2",
                        description="Description 2",
                        research_prompt="Research 2",
                        research_mode="focus",
                        research_type="research",
                        estimated_cost=0.10,
                        estimated_minutes=5,
                        priority=2
                    )
                ],
                total_estimated_cost=0.20,
                total_estimated_minutes=10,
                generated_at=datetime.utcnow()
            )
            
            progress = LearningProgress(
                curriculum=curriculum,
                completed_topics=["Topic 1"],
                failed_topics=[],
                total_cost=0.10,
                started_at=datetime.utcnow()
            )
            
            remaining_topics = [curriculum.topics[1]]  # Topic 2 remaining
            
            # Save progress
            learner._save_learning_progress(expert, progress, remaining_topics)
            
            # Verify file was created
            progress_file = knowledge_dir / "learning_progress.json"
            assert progress_file.exists()
            
            # Verify content
            with open(progress_file, 'r') as f:
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
            "paused_at": datetime.utcnow().isoformat(),
            "completed_topics": ["Topic 1"],
            "failed_topics": [],
            "remaining_topics": [
                {
                    "title": "Topic 2",
                    "research_prompt": "Research 2",
                    "research_mode": "focus",
                    "research_type": "research",
                    "estimated_cost": 0.10,
                    "estimated_minutes": 5
                }
            ],
            "total_cost_so_far": 0.10,
            "started_at": datetime.utcnow().isoformat(),
            "reason": "daily_or_monthly_limit"
        }
        
        progress_file = knowledge_dir / "learning_progress.json"
        with open(progress_file, 'w') as f:
            json.dump(progress_data, f)
        
        with patch('deepr.experts.learner.create_provider'), \
             patch('deepr.experts.learner.create_storage'), \
             patch('deepr.experts.learner.ExpertStore', return_value=store):
            
            learner = AutonomousLearner(mock_config)
            
            # Load progress
            loaded = learner.load_learning_progress("Test Expert")
            
            assert loaded is not None
            assert loaded["expert_name"] == "Test Expert"
            assert loaded["completed_topics"] == ["Topic 1"]
            assert len(loaded["remaining_topics"]) == 1

    def test_load_learning_progress_not_found(self, mock_config, mock_expert_store):
        """Test loading when no saved progress exists."""
        store, knowledge_dir = mock_expert_store
        
        with patch('deepr.experts.learner.create_provider'), \
             patch('deepr.experts.learner.create_storage'), \
             patch('deepr.experts.learner.ExpertStore', return_value=store):
            
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
        
        with patch('deepr.experts.learner.create_provider'), \
             patch('deepr.experts.learner.create_storage'), \
             patch('deepr.experts.learner.ExpertStore', return_value=store):
            
            learner = AutonomousLearner(mock_config)
            
            # Clear progress
            learner.clear_learning_progress("Test Expert")
            
            # Verify file was deleted
            assert not progress_file.exists()

    def test_clear_learning_progress_not_found(self, mock_config, mock_expert_store):
        """Test clearing when no saved progress exists (should not error)."""
        store, knowledge_dir = mock_expert_store
        
        with patch('deepr.experts.learner.create_provider'), \
             patch('deepr.experts.learner.create_storage'), \
             patch('deepr.experts.learner.ExpertStore', return_value=store):
            
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
            generated_at=datetime.utcnow()
        )
        progress = LearningProgress(
            curriculum=curriculum,
            completed_topics=[],
            failed_topics=[],
            total_cost=0.0,
            started_at=datetime.utcnow()
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
                    priority=1
                )
            ],
            total_estimated_cost=0.10,
            total_estimated_minutes=5,
            generated_at=datetime.utcnow()
        )
        now = datetime.utcnow()
        progress = LearningProgress(
            curriculum=curriculum,
            completed_topics=["Topic"],
            failed_topics=[],
            total_cost=0.10,
            started_at=now - timedelta(minutes=5),
            completed_at=now
        )
        assert progress.completed_at is not None
        assert progress.is_complete() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
