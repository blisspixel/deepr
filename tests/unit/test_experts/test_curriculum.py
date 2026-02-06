"""Unit tests for autonomous learning curriculum generation.

Requirements: 1.3 - Test Coverage
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from deepr.experts.curriculum import (
    CurriculumGenerationProgress,
    CurriculumGenerator,
    LearningCurriculum,
    LearningTopic,
    SourceReference,
)


class TestSourceReference:
    """Tests for SourceReference dataclass."""

    def test_create_with_all_fields(self):
        """Should create source reference with all fields."""
        source = SourceReference(
            url="https://docs.example.com",
            title="Example Docs",
            source_type="documentation",
            description="Official documentation",
        )

        assert source.url == "https://docs.example.com"
        assert source.title == "Example Docs"
        assert source.source_type == "documentation"
        assert source.description == "Official documentation"

    def test_auto_title_from_url(self):
        """Should extract title from URL if not provided."""
        source = SourceReference(url="https://example.com/api/v2")

        assert source.title == "v2"

    def test_auto_title_from_url_no_path(self):
        """Should extract last component from URL."""
        source = SourceReference(url="https://example.com")

        # When no trailing path, splits on / and takes last component
        assert source.title == "example.com"

    def test_default_source_type(self):
        """Should default to unknown source type."""
        source = SourceReference(url="https://example.com")

        assert source.source_type == "unknown"

    def test_no_url_no_auto_title(self):
        """Should not auto-title if no URL."""
        source = SourceReference(title="Manual Title")

        assert source.title == "Manual Title"
        assert source.url is None

    def test_various_source_types(self):
        """Should accept various source types."""
        types = ["documentation", "paper", "guide", "blog", "video"]
        for source_type in types:
            source = SourceReference(url="https://example.com", source_type=source_type)
            assert source.source_type == source_type


class TestCurriculumGenerationProgress:
    """Tests for CurriculumGenerationProgress class."""

    def test_init_without_callback(self):
        """Should initialize without callback."""
        progress = CurriculumGenerationProgress()

        assert progress.callback is None
        assert progress.start_time is None
        assert progress.current_step is None

    def test_init_with_callback(self):
        """Should initialize with callback."""
        callback = MagicMock()
        progress = CurriculumGenerationProgress(callback=callback)

        assert progress.callback is callback

    def test_start_sets_step(self):
        """Should set current step and start time."""
        callback = MagicMock()
        progress = CurriculumGenerationProgress(callback=callback)

        progress.start("Test step")

        assert progress.current_step == "Test step"
        assert progress.start_time is not None
        callback.assert_called_once()

    def test_update_calls_callback(self):
        """Should call callback with indented message."""
        callback = MagicMock()
        progress = CurriculumGenerationProgress(callback=callback)

        progress.update("Progress update")

        callback.assert_called_with("  Progress update")

    def test_complete_with_elapsed_time(self):
        """Should include elapsed time in completion message."""
        callback = MagicMock()
        progress = CurriculumGenerationProgress(callback=callback)

        progress.start("Test step")
        progress.complete("Done")

        # Should have two calls: start and complete
        assert callback.call_count == 2
        # Complete message should include time
        complete_call = callback.call_args_list[1]
        assert "Done" in complete_call[0][0]

    def test_complete_without_start_time(self):
        """Should complete without error if no start time."""
        callback = MagicMock()
        progress = CurriculumGenerationProgress(callback=callback)

        progress.complete("Done")

        callback.assert_called_once()

    def test_error_calls_callback(self):
        """Should call callback with error message."""
        callback = MagicMock()
        progress = CurriculumGenerationProgress(callback=callback)

        progress.error("Something failed")

        callback.assert_called_once()
        assert "Something failed" in callback.call_args[0][0]

    def test_notify_prints_when_no_callback(self, capsys):
        """Should print to console when no callback."""
        progress = CurriculumGenerationProgress()

        progress.update("Test message")

        captured = capsys.readouterr()
        assert "Test message" in captured.out

    def test_timestamp_format(self):
        """Should return HH:MM:SS format."""
        progress = CurriculumGenerationProgress()

        timestamp = progress._timestamp()

        # Should match HH:MM:SS pattern
        assert len(timestamp) == 8
        assert timestamp[2] == ":"
        assert timestamp[5] == ":"


class TestLearningTopic:
    """Test LearningTopic dataclass."""

    def test_learning_topic_initialization(self):
        """Test basic topic creation with research_mode and research_type."""
        topic = LearningTopic(
            title="Azure Architecture Basics",
            description="Learn Azure Landing Zone patterns",
            research_mode="focus",
            research_type="documentation",
            estimated_cost=0.20,
            estimated_minutes=10,
            priority=1,
            research_prompt="Research Azure Landing Zone best practices 2025",
        )

        assert topic.title == "Azure Architecture Basics"
        assert topic.research_mode == "focus"
        assert topic.research_type == "documentation"
        assert topic.estimated_cost == 0.20
        assert topic.priority == 1
        assert topic.dependencies == []

    def test_learning_topic_campaign_mode(self):
        """Test campaign mode with academic research type."""
        topic = LearningTopic(
            title="Deep Learning Foundations",
            description="Comprehensive academic study",
            research_mode="campaign",
            research_type="academic",
            estimated_cost=2.00,
            estimated_minutes=50,
            priority=1,
            research_prompt="Survey deep learning research papers",
        )

        assert topic.research_mode == "campaign"
        assert topic.research_type == "academic"
        assert topic.estimated_cost == 2.00

    def test_learning_topic_with_dependencies(self):
        """Test topic with dependencies."""
        topic = LearningTopic(
            title="Advanced Patterns",
            description="Advanced patterns",
            research_mode="focus",
            research_type="best-practices",
            estimated_cost=0.25,
            estimated_minutes=12,
            priority=2,
            research_prompt="Research advanced patterns",
            dependencies=["Basics", "Fundamentals"],
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
                research_mode="focus",
                research_type="documentation",
                estimated_cost=0.15,
                estimated_minutes=8,
                priority=1,
                research_prompt="Research topic 1",
            ),
            LearningTopic(
                title="Topic 2",
                description="Second topic",
                research_mode="focus",
                research_type="best-practices",
                estimated_cost=0.20,
                estimated_minutes=10,
                priority=2,
                research_prompt="Research topic 2",
            ),
        ]

        curriculum = LearningCurriculum(
            expert_name="Test Expert",
            domain="Testing",
            topics=topics,
            total_estimated_cost=0.35,
            total_estimated_minutes=18,
            generated_at=datetime.utcnow(),
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
                research_mode="focus",
                research_type="documentation",
                estimated_cost=0.15,
                estimated_minutes=8,
                priority=1,
                research_prompt="Research 1",
            )
        ]

        original = LearningCurriculum(
            expert_name="Test",
            domain="Domain",
            topics=topics,
            total_estimated_cost=0.15,
            total_estimated_minutes=8,
            generated_at=datetime.utcnow(),
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
        """Create mock config with required expert cost attributes."""
        config = MagicMock()
        config.get.return_value = "test-api-key"
        # Mock the expert config with cost values
        config.expert = MagicMock()
        config.expert.quick_research_cost = 0.002
        config.expert.deep_research_cost = 1.0
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
            budget_limit=5.0,
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
        """Test parsing GPT response into curriculum with research_mode and research_type."""
        response = """```json
{
  "topics": [
    {
      "title": "Azure Basics",
      "description": "Learn fundamentals",
      "research_mode": "focus",
      "research_type": "documentation",
      "estimated_cost": 0.15,
      "estimated_minutes": 8,
      "priority": 1,
      "research_prompt": "Research Azure basics 2025",
      "dependencies": []
    },
    {
      "title": "Advanced Patterns",
      "description": "Learn advanced patterns",
      "research_mode": "campaign",
      "research_type": "technical-deep-dive",
      "estimated_cost": 0.25,
      "estimated_minutes": 12,
      "priority": 2,
      "research_prompt": "Research advanced patterns 2025",
      "dependencies": ["Azure Basics"]
    }
  ]
}
```"""

        curriculum = generator._parse_curriculum_response(response, expert_name="Test Expert", domain="Testing")

        assert curriculum.expert_name == "Test Expert"
        assert len(curriculum.topics) == 2
        assert curriculum.topics[0].research_mode == "focus"
        assert curriculum.topics[0].research_type == "documentation"
        assert curriculum.topics[1].research_mode == "campaign"
        assert curriculum.topics[1].research_type == "technical-deep-dive"
        assert curriculum.total_estimated_cost == 0.40
        assert curriculum.total_estimated_minutes == 20
        assert curriculum.topics[1].dependencies == ["Azure Basics"]

    def test_parse_curriculum_backwards_compatibility(self, generator):
        """Test parsing curriculum without research_mode/type (backwards compatibility)."""
        response = """```json
{
  "topics": [
    {
      "title": "Legacy Topic",
      "description": "Created before research_mode was added",
      "estimated_cost": 0.20,
      "estimated_minutes": 10,
      "priority": 1,
      "research_prompt": "Old format topic",
      "dependencies": []
    }
  ]
}
```"""

        curriculum = generator._parse_curriculum_response(response, expert_name="Legacy Expert", domain="Legacy")

        # Should get default values
        assert curriculum.topics[0].research_mode == "focus"
        assert curriculum.topics[0].research_type == "best-practices"

    def test_truncate_to_budget(self, generator):
        """Test curriculum truncation to fit budget."""
        topics = [
            LearningTopic(
                title="Critical 1",
                description="Important",
                research_mode="focus",
                research_type="documentation",
                estimated_cost=1.0,
                estimated_minutes=10,
                priority=1,
                research_prompt="Research 1",
            ),
            LearningTopic(
                title="Critical 2",
                description="Important",
                research_mode="focus",
                research_type="documentation",
                estimated_cost=1.0,
                estimated_minutes=10,
                priority=1,
                research_prompt="Research 2",
            ),
            LearningTopic(
                title="Optional",
                description="Nice to have",
                research_mode="focus",
                research_type="documentation",
                estimated_cost=2.0,
                estimated_minutes=20,
                priority=5,
                research_prompt="Research 3",
            ),
        ]

        curriculum = LearningCurriculum(
            expert_name="Test",
            domain="Test",
            topics=topics,
            total_estimated_cost=4.0,
            total_estimated_minutes=40,
            generated_at=datetime.utcnow(),
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
                research_mode="focus",
                research_type="documentation",
                estimated_cost=0.15,
                estimated_minutes=8,
                priority=1,
                research_prompt="Research 1",
                dependencies=[],
            ),
            LearningTopic(
                title="Topic 2",
                description="Second",
                research_mode="focus",
                research_type="documentation",
                estimated_cost=0.20,
                estimated_minutes=10,
                priority=1,
                research_prompt="Research 2",
                dependencies=[],
            ),
        ]

        curriculum = LearningCurriculum(
            expert_name="Test",
            domain="Test",
            topics=topics,
            total_estimated_cost=0.35,
            total_estimated_minutes=18,
            generated_at=datetime.utcnow(),
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
                research_mode="focus",
                research_type="documentation",
                estimated_cost=0.15,
                estimated_minutes=8,
                priority=1,
                research_prompt="Research foundation",
                dependencies=[],
            ),
            LearningTopic(
                title="Intermediate",
                description="Intermediate",
                research_mode="focus",
                research_type="documentation",
                estimated_cost=0.20,
                estimated_minutes=10,
                priority=2,
                research_prompt="Research intermediate",
                dependencies=["Foundation"],
            ),
            LearningTopic(
                title="Advanced",
                description="Advanced",
                research_mode="focus",
                research_type="documentation",
                estimated_cost=0.25,
                estimated_minutes=12,
                priority=3,
                research_prompt="Research advanced",
                dependencies=["Intermediate"],
            ),
        ]

        curriculum = LearningCurriculum(
            expert_name="Test",
            domain="Test",
            topics=topics,
            total_estimated_cost=0.60,
            total_estimated_minutes=30,
            generated_at=datetime.utcnow(),
        )

        phases = generator.get_execution_order(curriculum)

        # Should have 3 phases (sequential dependencies)
        assert len(phases) == 3
        assert phases[0][0].title == "Foundation"
        assert phases[1][0].title == "Intermediate"
        assert phases[2][0].title == "Advanced"


class TestLearningCurriculumAdvanced:
    """Additional tests for LearningCurriculum."""

    def test_to_dict_includes_sources(self):
        """Should include sources in topic dict."""
        sources = [
            SourceReference(
                url="https://example.com", title="Example", source_type="documentation", description="Example docs"
            )
        ]
        topics = [
            LearningTopic(
                title="Topic",
                description="Description",
                research_mode="focus",
                research_type="documentation",
                estimated_cost=0.25,
                estimated_minutes=10,
                priority=2,
                research_prompt="Research topic",
                sources=sources,
            )
        ]

        curriculum = LearningCurriculum(
            expert_name="test",
            domain="Test",
            topics=topics,
            total_estimated_cost=0.25,
            total_estimated_minutes=10,
            generated_at=datetime.now(timezone.utc),
        )

        result = curriculum.to_dict()

        assert len(result["topics"][0]["sources"]) == 1
        assert result["topics"][0]["sources"][0]["url"] == "https://example.com"
        assert result["topics"][0]["sources"][0]["source_type"] == "documentation"

    def test_from_dict_restores_sources(self):
        """Should restore sources from dict."""
        data = {
            "expert_name": "test",
            "domain": "Test",
            "topics": [
                {
                    "title": "Topic",
                    "description": "Description",
                    "research_mode": "focus",
                    "research_type": "documentation",
                    "estimated_cost": 0.25,
                    "estimated_minutes": 10,
                    "priority": 2,
                    "research_prompt": "Research",
                    "dependencies": [],
                    "sources": [
                        {
                            "url": "https://example.com",
                            "title": "Example",
                            "source_type": "documentation",
                            "description": "Docs",
                        }
                    ],
                }
            ],
            "total_estimated_cost": 0.25,
            "total_estimated_minutes": 10,
            "generated_at": "2026-01-15T12:00:00+00:00",
        }

        curriculum = LearningCurriculum.from_dict(data)

        assert len(curriculum.topics[0].sources) == 1
        assert curriculum.topics[0].sources[0].url == "https://example.com"

    def test_roundtrip_json_serialization(self):
        """Should survive JSON serialization roundtrip."""
        topics = [
            LearningTopic(
                title="Test",
                description="Test",
                research_mode="campaign",
                research_type="academic",
                estimated_cost=2.0,
                estimated_minutes=45,
                priority=1,
                research_prompt="Research",
            )
        ]

        original = LearningCurriculum(
            expert_name="test",
            domain="Test",
            topics=topics,
            total_estimated_cost=2.0,
            total_estimated_minutes=45,
            generated_at=datetime.now(timezone.utc),
        )

        # Serialize to JSON and back
        json_str = json.dumps(original.to_dict())
        restored_data = json.loads(json_str)
        restored = LearningCurriculum.from_dict(restored_data)

        assert restored.expert_name == original.expert_name
        assert restored.topics[0].title == original.topics[0].title


class TestCurriculumGeneratorAdvanced:
    """Additional tests for CurriculumGenerator."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = MagicMock()
        config.provider.openai_api_key = "test-key"
        config.expert.quick_research_cost = 0.25
        config.expert.deep_research_cost = 2.0
        return config

    @pytest.fixture
    def generator(self, mock_config):
        """Create curriculum generator."""
        return CurriculumGenerator(mock_config)

    def test_parse_json_in_generic_code_block(self, generator):
        """Should extract JSON from generic code block."""
        response = """Here's the curriculum:

```
{
    "topics": [
        {
            "title": "Test",
            "description": "Test",
            "research_mode": "focus",
            "research_type": "documentation",
            "estimated_cost": 0.25,
            "estimated_minutes": 10,
            "priority": 2,
            "research_prompt": "Test"
        }
    ]
}
```
"""

        result = generator._parse_curriculum_response(response, "test", "Test")

        assert len(result.topics) == 1
        assert result.topics[0].title == "Test"

    def test_parse_invalid_json_raises(self, generator):
        """Should raise ValueError for invalid JSON."""
        response = "This is not valid JSON"

        with pytest.raises(ValueError, match="Failed to parse curriculum JSON"):
            generator._parse_curriculum_response(response, "test", "Test")

    def test_parse_calculates_totals(self, generator):
        """Should calculate total cost and minutes."""
        response = json.dumps(
            {
                "topics": [
                    {
                        "title": "Topic 1",
                        "description": "Test",
                        "research_mode": "campaign",
                        "research_type": "academic",
                        "estimated_cost": 2.0,
                        "estimated_minutes": 45,
                        "priority": 1,
                        "research_prompt": "Test",
                    },
                    {
                        "title": "Topic 2",
                        "description": "Test",
                        "research_mode": "focus",
                        "research_type": "documentation",
                        "estimated_cost": 0.25,
                        "estimated_minutes": 10,
                        "priority": 2,
                        "research_prompt": "Test",
                    },
                ]
            }
        )

        result = generator._parse_curriculum_response(response, "test", "Test")

        assert result.total_estimated_cost == 2.25
        assert result.total_estimated_minutes == 55

    def test_truncate_to_budget_with_overage_for_critical(self, generator):
        """Should allow 10% overage for priority 1-2 topics."""
        topics = [
            LearningTopic(
                title="Critical",
                description="Very important",
                research_mode="campaign",
                research_type="academic",
                estimated_cost=2.2,  # Just over 2.0 budget
                estimated_minutes=45,
                priority=1,
                research_prompt="Research",
            ),
        ]

        curriculum = LearningCurriculum(
            expert_name="test",
            domain="Test",
            topics=topics,
            total_estimated_cost=2.2,
            total_estimated_minutes=45,
            generated_at=datetime.now(timezone.utc),
        )

        # Budget is 2.0, but topic costs 2.2
        # Since it's priority 1, allow 10% overage (2.2 <= 2.0 * 1.1)
        truncated = generator._truncate_to_budget(curriculum, budget_limit=2.0)

        assert len(truncated.topics) == 1

    def test_get_execution_order_parallel_branches(self, generator):
        """Should parallelize topics with same dependency."""
        topics = [
            LearningTopic(
                title="Base",
                description="Base",
                research_mode="campaign",
                research_type="academic",
                estimated_cost=2.0,
                estimated_minutes=45,
                priority=1,
                research_prompt="Research base",
            ),
            LearningTopic(
                title="Branch A",
                description="Branch A",
                research_mode="focus",
                research_type="documentation",
                estimated_cost=0.25,
                estimated_minutes=10,
                priority=2,
                research_prompt="Research branch A",
                dependencies=["Base"],
            ),
            LearningTopic(
                title="Branch B",
                description="Branch B",
                research_mode="focus",
                research_type="documentation",
                estimated_cost=0.25,
                estimated_minutes=10,
                priority=2,
                research_prompt="Research branch B",
                dependencies=["Base"],
            ),
        ]

        curriculum = LearningCurriculum(
            expert_name="test",
            domain="Test",
            topics=topics,
            total_estimated_cost=2.5,
            total_estimated_minutes=65,
            generated_at=datetime.now(timezone.utc),
        )

        phases = generator.get_execution_order(curriculum)

        assert len(phases) == 2
        assert len(phases[0]) == 1  # Base
        assert len(phases[1]) == 2  # Branch A and B in parallel

    def test_build_curriculum_prompt_with_discovered_sources(self, generator):
        """Should include discovered sources in prompt."""
        sources = [
            SourceReference(
                url="https://docs.example.com",
                title="Example Docs",
                source_type="documentation",
                description="Official documentation",
            )
        ]

        prompt = generator._build_curriculum_prompt(
            expert_name="Test Expert",
            domain="Test Domain",
            initial_documents=["doc1.md"],
            target_topics=5,
            budget_limit=None,
            discovered_sources=sources,
        )

        assert "DISCOVERED SOURCES" in prompt
        assert "https://docs.example.com" in prompt
        assert "Example Docs" in prompt

    def test_build_curriculum_prompt_with_explicit_counts(self, generator):
        """Should include explicit counts in prompt."""
        prompt = generator._build_curriculum_prompt(
            expert_name="Test Expert",
            domain="Test Domain",
            initial_documents=["doc1.md"],
            target_topics=5,
            budget_limit=None,
            docs_count=2,
            quick_count=2,
            deep_count=1,
        )

        assert "EXPLICIT TOPIC COUNTS" in prompt
        assert "2 documentation topics" in prompt
        assert "2 quick research topics" in prompt
        assert "1 deep research topics" in prompt

    def test_init_with_dict_config(self):
        """Should initialize with dict config."""
        config = {"api_key": "test-key"}

        generator = CurriculumGenerator(config)

        assert generator.config == config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
