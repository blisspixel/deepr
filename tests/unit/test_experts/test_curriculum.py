"""Unit tests for autonomous learning curriculum generation."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from deepr.experts.curriculum import (
    LearningTopic,
    LearningCurriculum,
    CurriculumGenerator
)


class TestLearningTopic:
    """Test LearningTopic dataclass."""

    def test_learning_topic_initialization(self):
        """Test basic topic creation."""
        topic = LearningTopic(
            title="Azure Architecture Basics",
            description="Learn Azure Landing Zone patterns",
            estimated_cost=0.20,
            estimated_minutes=10,
            priority=1,
            research_prompt="Research Azure Landing Zone best practices 2025"
        )

        assert topic.title == "Azure Architecture Basics"
        assert topic.estimated_cost == 0.20
        assert topic.priority == 1
        assert topic.dependencies == []

    def test_learning_topic_with_dependencies(self):
        """Test topic with dependencies."""
        topic = LearningTopic(
            title="Advanced Patterns",
            description="Advanced patterns",
            estimated_cost=0.25,
            estimated_minutes=12,
            priority=2,
            research_prompt="Research advanced patterns",
            dependencies=["Basics", "Fundamentals"]
        )

        assert len(topic.dependencies) == 2
        assert "Basics" in topic.dependencies


class TestLearningCurriculum:
    """Test LearningCurriculum dataclass."""

    def test_curriculum_initialization(self):
        """Test curriculum creation."""
        topics = [
            LearningTopic(
                title="Topic 1",
                description="First topic",
                estimated_cost=0.15,
                estimated_minutes=8,
                priority=1,
                research_prompt="Research topic 1"
            ),
            LearningTopic(
                title="Topic 2",
                description="Second topic",
                estimated_cost=0.20,
                estimated_minutes=10,
                priority=2,
                research_prompt="Research topic 2"
            )
        ]

        curriculum = LearningCurriculum(
            expert_name="Test Expert",
            domain="Testing",
            topics=topics,
            total_estimated_cost=0.35,
            total_estimated_minutes=18,
            generated_at=datetime.utcnow()
        )

        assert curriculum.expert_name == "Test Expert"
        assert len(curriculum.topics) == 2
        assert curriculum.total_estimated_cost == 0.35

    def test_curriculum_serialization(self):
        """Test to_dict and from_dict."""
        topics = [
            LearningTopic(
                title="Topic 1",
                description="First",
                estimated_cost=0.15,
                estimated_minutes=8,
                priority=1,
                research_prompt="Research 1"
            )
        ]

        original = LearningCurriculum(
            expert_name="Test",
            domain="Domain",
            topics=topics,
            total_estimated_cost=0.15,
            total_estimated_minutes=8,
            generated_at=datetime.utcnow()
        )

        # Serialize and deserialize
        data = original.to_dict()
        restored = LearningCurriculum.from_dict(data)

        assert restored.expert_name == original.expert_name
        assert restored.domain == original.domain
        assert len(restored.topics) == len(original.topics)
        assert restored.topics[0].title == original.topics[0].title


class TestCurriculumGenerator:
    """Test CurriculumGenerator."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = MagicMock()
        config.get.return_value = "test-api-key"
        return config

    @pytest.fixture
    def generator(self, mock_config):
        """Create curriculum generator."""
        return CurriculumGenerator(mock_config)

    def test_build_curriculum_prompt(self, generator):
        """Test curriculum prompt generation."""
        prompt = generator._build_curriculum_prompt(
            expert_name="Azure Expert",
            domain="Azure Architecture",
            initial_documents=["doc1.md", "doc2.pdf"],
            target_topics=10,
            budget_limit=5.0
        )

        # Check key elements in prompt
        assert "Azure Expert" in prompt
        assert "Azure Architecture" in prompt
        assert "doc1.md" in prompt
        assert "doc2.pdf" in prompt
        assert "10" in prompt
        assert "$5.00" in prompt
        assert "2025" in prompt  # Should include current year

    def test_parse_curriculum_response(self, generator):
        """Test parsing GPT response into curriculum."""
        response = """```json
{
  "topics": [
    {
      "title": "Azure Basics",
      "description": "Learn fundamentals",
      "estimated_cost": 0.15,
      "estimated_minutes": 8,
      "priority": 1,
      "research_prompt": "Research Azure basics 2025",
      "dependencies": []
    },
    {
      "title": "Advanced Patterns",
      "description": "Learn advanced patterns",
      "estimated_cost": 0.25,
      "estimated_minutes": 12,
      "priority": 2,
      "research_prompt": "Research advanced patterns 2025",
      "dependencies": ["Azure Basics"]
    }
  ]
}
```"""

        curriculum = generator._parse_curriculum_response(
            response,
            expert_name="Test Expert",
            domain="Testing"
        )

        assert curriculum.expert_name == "Test Expert"
        assert len(curriculum.topics) == 2
        assert curriculum.total_estimated_cost == 0.40
        assert curriculum.total_estimated_minutes == 20
        assert curriculum.topics[1].dependencies == ["Azure Basics"]

    def test_truncate_to_budget(self, generator):
        """Test curriculum truncation to fit budget."""
        topics = [
            LearningTopic(
                title="Critical 1",
                description="Important",
                estimated_cost=1.0,
                estimated_minutes=10,
                priority=1,
                research_prompt="Research 1"
            ),
            LearningTopic(
                title="Critical 2",
                description="Important",
                estimated_cost=1.0,
                estimated_minutes=10,
                priority=1,
                research_prompt="Research 2"
            ),
            LearningTopic(
                title="Optional",
                description="Nice to have",
                estimated_cost=2.0,
                estimated_minutes=20,
                priority=5,
                research_prompt="Research 3"
            )
        ]

        curriculum = LearningCurriculum(
            expert_name="Test",
            domain="Test",
            topics=topics,
            total_estimated_cost=4.0,
            total_estimated_minutes=40,
            generated_at=datetime.utcnow()
        )

        # Truncate to $2.50 budget
        truncated = generator._truncate_to_budget(curriculum, budget_limit=2.5)

        # Should keep the two priority-1 topics
        assert len(truncated.topics) == 2
        assert all(t.priority == 1 for t in truncated.topics)
        assert truncated.total_estimated_cost <= 2.5

    def test_get_execution_order_no_dependencies(self, generator):
        """Test execution order with no dependencies."""
        topics = [
            LearningTopic(
                title="Topic 1",
                description="First",
                estimated_cost=0.15,
                estimated_minutes=8,
                priority=1,
                research_prompt="Research 1",
                dependencies=[]
            ),
            LearningTopic(
                title="Topic 2",
                description="Second",
                estimated_cost=0.20,
                estimated_minutes=10,
                priority=1,
                research_prompt="Research 2",
                dependencies=[]
            )
        ]

        curriculum = LearningCurriculum(
            expert_name="Test",
            domain="Test",
            topics=topics,
            total_estimated_cost=0.35,
            total_estimated_minutes=18,
            generated_at=datetime.utcnow()
        )

        phases = generator.get_execution_order(curriculum)

        # All topics can run in parallel (phase 1)
        assert len(phases) == 1
        assert len(phases[0]) == 2

    def test_get_execution_order_with_dependencies(self, generator):
        """Test execution order with dependencies."""
        topics = [
            LearningTopic(
                title="Foundation",
                description="Foundation",
                estimated_cost=0.15,
                estimated_minutes=8,
                priority=1,
                research_prompt="Research foundation",
                dependencies=[]
            ),
            LearningTopic(
                title="Intermediate",
                description="Intermediate",
                estimated_cost=0.20,
                estimated_minutes=10,
                priority=2,
                research_prompt="Research intermediate",
                dependencies=["Foundation"]
            ),
            LearningTopic(
                title="Advanced",
                description="Advanced",
                estimated_cost=0.25,
                estimated_minutes=12,
                priority=3,
                research_prompt="Research advanced",
                dependencies=["Intermediate"]
            )
        ]

        curriculum = LearningCurriculum(
            expert_name="Test",
            domain="Test",
            topics=topics,
            total_estimated_cost=0.60,
            total_estimated_minutes=30,
            generated_at=datetime.utcnow()
        )

        phases = generator.get_execution_order(curriculum)

        # Should have 3 phases (sequential dependencies)
        assert len(phases) == 3
        assert phases[0][0].title == "Foundation"
        assert phases[1][0].title == "Intermediate"
        assert phases[2][0].title == "Advanced"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
