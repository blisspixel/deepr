"""Live integration tests for Azure AI Foundry provider.

These tests require Azure credentials and are skipped when
AZURE_PROJECT_ENDPOINT is not set.

Run with: pytest tests/integration/test_azure_foundry_live.py -v
"""

import os

import pytest

AZURE_ENDPOINT = os.getenv("AZURE_PROJECT_ENDPOINT")
SKIP_REASON = "AZURE_PROJECT_ENDPOINT not set — skipping live Azure Foundry tests"


@pytest.mark.skipif(not AZURE_ENDPOINT, reason=SKIP_REASON)
class TestAzureFoundryLive:
    """Live tests against Azure AI Foundry Agent Service."""

    @pytest.fixture
    def provider(self):
        from deepr.providers.azure_foundry_provider import AzureFoundryProvider

        p = AzureFoundryProvider()
        yield p
        p.close()

    @pytest.mark.asyncio
    async def test_submit_regular_research(self, provider):
        """Submit a simple GPT-4.1 research job and verify completion."""
        from deepr.providers.base import ResearchRequest

        request = ResearchRequest(
            prompt="What is the capital of France? Answer in one sentence.",
            model="gpt-4.1",
            system_message="You are a helpful research assistant.",
        )

        job_id = await provider.submit_research(request)
        assert job_id is not None

        response = await provider.get_status(job_id)
        assert response.status == "completed"
        assert response.output is not None
        assert response.usage is not None
        assert response.usage.cost >= 0

    @pytest.mark.asyncio
    async def test_submit_deep_research(self, provider):
        """Submit an o3-deep-research job with Bing grounding."""
        from deepr.providers.base import ResearchRequest

        request = ResearchRequest(
            prompt="What are the latest developments in quantum computing? Provide a brief summary.",
            model="o3-deep-research",
            system_message="You are a research analyst.",
        )

        job_id = await provider.submit_research(request)
        assert job_id is not None

        # Deep research is async — check initial status
        response = await provider.get_status(job_id)
        assert response.status in ("in_progress", "completed")

    def test_model_discovery(self, provider):
        """list_available_models should return all registered Foundry models."""
        models = provider.list_available_models()
        assert len(models) >= 7  # 7 models registered

        model_names = [m["model"] for m in models]
        assert "o3-deep-research" in model_names
        assert "gpt-4.1" in model_names

        # Check structure
        for m in models:
            assert "cost_per_query" in m
            assert "context_window" in m
            assert "specializations" in m

    def test_vector_stores_unsupported(self, provider):
        """Foundry uses Bing grounding, not vector stores."""
        import asyncio

        stores = asyncio.get_event_loop().run_until_complete(provider.list_vector_stores())
        assert stores == []
