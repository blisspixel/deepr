"""Test two-phase curriculum generation and execution.

This module tests the complete two-phase workflow:
1. Discovery: Identify sources
2. Acquisition: Fetch and scrape sources
3. Synthesis: Generate curriculum and execute research
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from deepr.experts.curriculum import CurriculumGenerator, LearningCurriculum, LearningTopic, SourceReference
from deepr.experts.learner import AutonomousLearner
from deepr.experts.profile import ExpertProfile


@pytest.fixture
def mock_config():
    """Mock configuration."""
    return {"api_key": "test-key", "openai_api_key": "test-key", "storage_path": "test-output"}


@pytest.fixture
def mock_expert():
    """Mock expert profile."""
    return ExpertProfile(
        name="Test Expert",
        vector_store_id="vs_test123",
        description="Test domain expert",
        domain="Test Domain",
        source_files=[],
        total_documents=0,
        knowledge_cutoff_date=datetime.utcnow(),
        last_knowledge_refresh=datetime.utcnow(),
        system_message="Test system message",
        provider="openai",
    )


@pytest.fixture
def sample_sources():
    """Sample discovered sources."""
    return [
        SourceReference(
            url="https://docs.example.com/api",
            title="Example API Documentation",
            source_type="documentation",
            description="Official API documentation",
        ),
        SourceReference(
            url="https://arxiv.org/abs/2301.12345",
            title="Research Paper on Example Topic",
            source_type="paper",
            description="Academic paper on the topic",
        ),
        SourceReference(
            url="https://example.com/guide",
            title="Getting Started Guide",
            source_type="guide",
            description="Tutorial for beginners",
        ),
    ]


@pytest.fixture
def sample_curriculum(sample_sources):
    """Sample curriculum with sources."""
    topics = [
        LearningTopic(
            title="Example API Deep Dive",
            description="Learn the Example API",
            research_mode="focus",
            research_type="documentation",
            estimated_cost=0.25,
            estimated_minutes=10,
            priority=1,
            research_prompt="Study Example API docs. Extract key concepts.",
            dependencies=[],
            sources=[sample_sources[0]],  # References documentation
        ),
        LearningTopic(
            title="Research Paper Analysis",
            description="Analyze research paper",
            research_mode="campaign",
            research_type="academic",
            estimated_cost=2.00,
            estimated_minutes=45,
            priority=1,
            research_prompt="Analyze research paper on Example Topic.",
            dependencies=[],
            sources=[sample_sources[1]],  # References paper
        ),
    ]

    return LearningCurriculum(
        expert_name="Test Expert",
        domain="Test Domain",
        topics=topics,
        total_estimated_cost=2.25,
        total_estimated_minutes=55,
        generated_at=datetime.utcnow(),
    )


class TestDiscoveryPhase:
    """Test Phase 1: Discovery."""

    @pytest.mark.asyncio
    async def test_discover_sources(self, mock_config):
        """Test source discovery."""
        generator = CurriculumGenerator(mock_config)

        # Mock GPT-5 response
        mock_response = """```json
{
  "sources": [
    {
      "url": "https://docs.example.com/api",
      "title": "Example API Documentation",
      "source_type": "documentation",
      "description": "Official API documentation"
    },
    {
      "url": "https://arxiv.org/abs/2301.12345",
      "title": "Research Paper",
      "source_type": "paper",
      "description": "Academic paper"
    }
  ]
}
```"""

        with patch.object(generator, "_call_gpt5_with_retry", return_value=mock_response):
            sources = await generator._discover_sources(domain="Test Domain", timeout=120)

        # Verify sources were parsed correctly
        assert len(sources) == 2
        assert sources[0].url == "https://docs.example.com/api"
        assert sources[0].source_type == "documentation"
        assert sources[1].url == "https://arxiv.org/abs/2301.12345"
        assert sources[1].source_type == "paper"

    @pytest.mark.asyncio
    async def test_discover_sources_empty(self, mock_config):
        """Test discovery with no sources found."""
        generator = CurriculumGenerator(mock_config)

        # Mock empty response
        mock_response = '```json\n{"sources": []}\n```'

        with patch.object(generator, "_call_gpt5_with_retry", return_value=mock_response):
            sources = await generator._discover_sources(domain="Test Domain", timeout=120)

        assert len(sources) == 0

    @pytest.mark.asyncio
    async def test_discover_sources_malformed_json(self, mock_config):
        """Test discovery with malformed JSON."""
        generator = CurriculumGenerator(mock_config)

        # Mock malformed response
        mock_response = "```json\n{invalid json}\n```"

        with patch.object(generator, "_call_gpt5_with_retry", return_value=mock_response):
            sources = await generator._discover_sources(domain="Test Domain", timeout=120)

        # Should return empty list on parse error
        assert len(sources) == 0


class TestSynthesisPhase:
    """Test Phase 2: Synthesis (curriculum generation)."""

    @pytest.mark.asyncio
    async def test_generate_curriculum_with_sources(self, mock_config, sample_sources):
        """Test curriculum generation with discovered sources."""
        generator = CurriculumGenerator(mock_config)

        # Mock discovery
        with patch.object(generator, "_discover_sources", return_value=sample_sources):
            # Mock curriculum generation
            mock_response = """```json
{
  "topics": [
    {
      "title": "Example API Deep Dive",
      "description": "Learn the Example API",
      "research_mode": "focus",
      "research_type": "documentation",
      "estimated_cost": 0.25,
      "estimated_minutes": 10,
      "priority": 1,
      "research_prompt": "Study Example API docs",
      "dependencies": [],
      "sources": [
        {
          "url": "https://docs.example.com/api",
          "title": "Example API Documentation",
          "source_type": "documentation"
        }
      ]
    }
  ]
}
```"""

            with patch.object(generator, "_call_gpt5_with_retry", return_value=mock_response):
                curriculum = await generator.generate_curriculum(
                    expert_name="Test Expert",
                    domain="Test Domain",
                    initial_documents=[],
                    target_topics=1,
                    budget_limit=10.0,
                    enable_discovery=True,
                )

        # Verify curriculum has sources
        assert len(curriculum.topics) == 1
        assert len(curriculum.topics[0].sources) == 1
        assert curriculum.topics[0].sources[0].url == "https://docs.example.com/api"

    @pytest.mark.asyncio
    async def test_generate_curriculum_without_discovery(self, mock_config):
        """Test curriculum generation without discovery phase."""
        generator = CurriculumGenerator(mock_config)

        # Mock curriculum generation
        mock_response = """```json
{
  "topics": [
    {
      "title": "Generic Topic",
      "description": "Generic research",
      "research_mode": "focus",
      "research_type": "best-practices",
      "estimated_cost": 0.25,
      "estimated_minutes": 10,
      "priority": 1,
      "research_prompt": "Research generic topic",
      "dependencies": []
    }
  ]
}
```"""

        with patch.object(generator, "_call_gpt5_with_retry", return_value=mock_response):
            curriculum = await generator.generate_curriculum(
                expert_name="Test Expert",
                domain="Test Domain",
                initial_documents=[],
                target_topics=1,
                budget_limit=10.0,
                enable_discovery=False,  # Disable discovery
            )

        # Verify curriculum has no sources
        assert len(curriculum.topics) == 1
        assert len(curriculum.topics[0].sources) == 0


class TestAcquisitionPhase:
    """Test Phase 2a: Acquisition."""

    @pytest.mark.asyncio
    async def test_acquire_sources(self, mock_config, mock_expert, sample_curriculum):
        """Test source acquisition."""
        learner = AutonomousLearner(mock_config)

        # Mock scraping and fetching
        with patch.object(learner, "_scrape_source", return_value="Scraped content"):
            with patch.object(learner, "_fetch_paper", return_value="Paper content"):
                with patch.object(learner.research.provider, "upload_document", return_value="file_123"):
                    with patch.object(learner.research.provider.client.vector_stores.files, "create"):
                        await learner._acquire_sources(expert=mock_expert, curriculum=sample_curriculum, callback=None)

        # Verify expert metadata was updated
        assert mock_expert.total_documents > 0

    @pytest.mark.asyncio
    async def test_acquire_sources_no_sources(self, mock_config, mock_expert):
        """Test acquisition with no sources."""
        learner = AutonomousLearner(mock_config)

        # Create curriculum with no sources
        curriculum = LearningCurriculum(
            expert_name="Test Expert",
            domain="Test Domain",
            topics=[
                LearningTopic(
                    title="Generic Topic",
                    description="Generic research",
                    research_mode="focus",
                    research_type="best-practices",
                    estimated_cost=0.25,
                    estimated_minutes=10,
                    priority=1,
                    research_prompt="Research generic topic",
                    dependencies=[],
                    sources=[],  # No sources
                )
            ],
            total_estimated_cost=0.25,
            total_estimated_minutes=10,
            generated_at=datetime.utcnow(),
        )

        # Should skip acquisition
        await learner._acquire_sources(expert=mock_expert, curriculum=curriculum, callback=None)

        # Verify no documents were added
        assert mock_expert.total_documents == 0

    @pytest.mark.asyncio
    async def test_scrape_source(self, mock_config):
        """Test source scraping."""
        learner = AutonomousLearner(mock_config)

        source = SourceReference(
            url="https://docs.example.com/api", title="Example API Documentation", source_type="documentation"
        )

        # Mock scraping
        mock_results = {
            "success": True,
            "pages_scraped": 5,
            "scraped_data": {
                "https://docs.example.com/api": "Page 1 content",
                "https://docs.example.com/api/auth": "Page 2 content",
            },
        }

        with patch("deepr.experts.learner.scrape_website", return_value=mock_results):
            content = await learner._scrape_source(source)

        assert content is not None
        assert "Page 1 content" in content
        assert "Page 2 content" in content

    @pytest.mark.asyncio
    async def test_fetch_paper(self, mock_config):
        """Test paper fetching."""
        learner = AutonomousLearner(mock_config)

        source = SourceReference(url="https://arxiv.org/abs/2301.12345", title="Research Paper", source_type="paper")

        # Mock HTTP response
        mock_response = Mock()
        mock_response.text = "<html><body><p>Paper content</p></body></html>"
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            content = await learner._fetch_paper(source)

        assert content is not None
        assert "Paper content" in content


class TestIntegration:
    """Test full two-phase workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, mock_config, mock_expert, sample_sources):
        """Test complete two-phase workflow."""
        generator = CurriculumGenerator(mock_config)
        learner = AutonomousLearner(mock_config)

        # Mock discovery
        with patch.object(generator, "_discover_sources", return_value=sample_sources):
            # Mock curriculum generation
            mock_curriculum_response = """```json
{
  "topics": [
    {
      "title": "Example API Deep Dive",
      "description": "Learn the Example API",
      "research_mode": "focus",
      "research_type": "documentation",
      "estimated_cost": 0.25,
      "estimated_minutes": 10,
      "priority": 1,
      "research_prompt": "Study Example API docs",
      "dependencies": [],
      "sources": [
        {
          "url": "https://docs.example.com/api",
          "title": "Example API Documentation",
          "source_type": "documentation"
        }
      ]
    }
  ]
}
```"""

            with patch.object(generator, "_call_gpt5_with_retry", return_value=mock_curriculum_response):
                curriculum = await generator.generate_curriculum(
                    expert_name="Test Expert",
                    domain="Test Domain",
                    initial_documents=[],
                    target_topics=1,
                    budget_limit=10.0,
                    enable_discovery=True,
                )

        # Verify curriculum has sources
        assert len(curriculum.topics) == 1
        assert len(curriculum.topics[0].sources) == 1

        # Mock acquisition
        with patch.object(learner, "_scrape_source", return_value="Scraped content"):
            with patch.object(learner.research.provider, "upload_document", return_value="file_123"):
                with patch.object(learner.research.provider.client.vector_stores.files, "create"):
                    # Mock research execution
                    with patch.object(learner.research, "submit_research", return_value="resp_123"):
                        progress = await learner.execute_curriculum(
                            expert=mock_expert, curriculum=curriculum, budget_limit=10.0, dry_run=False
                        )

        # Verify progress
        assert progress is not None
        assert len(progress.completed_topics) > 0 or len(progress.failed_topics) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
