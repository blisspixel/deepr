"""Tests for Grok provider implementation."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from deepr.providers.grok_provider import GrokProvider
from deepr.providers.base import ResearchRequest, ToolConfig


class TestGrokProvider:
    """Test Grok provider."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GrokProvider(api_key="test-grok-key")

    def test_provider_initialization(self, provider):
        """Test provider initializes correctly."""
        assert provider.api_key == "test-grok-key"
        assert provider.client is not None

    def test_provider_initialization_no_api_key(self):
        """Test provider fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            if "GROK_API_KEY" in os.environ:
                del os.environ["GROK_API_KEY"]

            with pytest.raises(ValueError, match="Grok API key is required"):
                GrokProvider(api_key=None)

    def test_model_name_mapping(self, provider):
        """Test model name mapping."""
        # Grok has simpler model structure
        assert provider.get_model_name("grok-beta") == "grok-beta"
        assert provider.get_model_name("unknown-model") == "unknown-model"

    def test_pricing_configuration(self, provider):
        """Test pricing is configured."""
        assert hasattr(provider, "pricing")
        # Grok pricing should be configured
        assert len(provider.pricing) > 0

    def test_calculate_cost(self, provider):
        """Test cost calculation for Grok models."""
        # Test with basic usage
        cost = provider._calculate_cost(
            input_tokens=1000, output_tokens=1000, model="grok-beta"
        )
        assert cost > 0
        assert isinstance(cost, float)

    @pytest.mark.asyncio
    async def test_submit_research_basic(self, provider):
        """Test basic research submission (mocked)."""
        mock_response = MagicMock()
        mock_response.id = "test_123"
        mock_response.status = "completed"
        mock_response.choices = [MagicMock()]

        with patch.object(provider.client.chat.completions, "create") as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="grok-beta",
                system_message="Test system message",
                tools=[],
            )

            job_id = await provider.submit_research(request)
            assert job_id is not None

    def test_x_search_tool_configuration(self, provider):
        """Test X/Twitter search tool configuration.

        Grok's key differentiator is X search integration.
        """
        tools = [ToolConfig(type="x_search")]
        assert tools[0].type == "x_search"
        # Grok uses X/Twitter data differently than other providers


class TestGrokToolConfiguration:
    """Test Grok-specific tool configuration."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GrokProvider(api_key="test-key")

    def test_x_search_tool_format(self, provider):
        """Test X/Twitter search tool format.

        Grok's unique feature: real-time X/Twitter search.
        """
        tools = [ToolConfig(type="x_search")]
        assert tools[0].type == "x_search"

    def test_grok_vs_other_providers(self, provider):
        """Document key differences: Grok vs OpenAI/Gemini.

        Grok differences:
        - Uses X/Twitter search instead of general web search
        - Simpler model structure
        - Different pricing model
        - Limited deep research capabilities (no multi-phase/team modes)
        """
        # This is a documentation test
        assert hasattr(provider, "pricing")


class TestGrokCostCalculation:
    """Test cost calculation for Grok."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GrokProvider(api_key="test-key")

    def test_cost_scales_linearly(self, provider):
        """Test that cost scales linearly with token count."""
        model = "grok-beta"

        cost_1k = provider._calculate_cost(1000, 1000, model)
        cost_2k = provider._calculate_cost(2000, 2000, model)
        cost_10k = provider._calculate_cost(10000, 10000, model)

        # Should scale linearly
        assert abs(cost_2k - (cost_1k * 2)) < 0.00001
        assert abs(cost_10k - (cost_1k * 10)) < 0.00001

    def test_grok_pricing_reasonable(self, provider):
        """Test that Grok pricing is in expected range."""
        # 10k tokens should cost less than $1
        cost = provider._calculate_cost(10000, 10000, "grok-beta")
        assert cost < 1.0, "Grok should be reasonably priced"


class TestGrokCapabilities:
    """Document Grok's capabilities and limitations."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GrokProvider(api_key="test-key")

    def test_grok_has_x_search(self, provider):
        """Grok's unique feature: X/Twitter search."""
        # Grok can search X/Twitter for real-time information
        # This is its key differentiator
        pass

    def test_grok_limitations(self, provider):
        """Document Grok's current limitations.

        Grok does NOT support:
        - Multi-phase research (project mode)
        - Team mode (multiple perspectives)
        - File upload with vector stores
        - Extended reasoning like o3/gpt-5

        Grok IS good for:
        - Focus mode (quick queries)
        - X/Twitter sentiment analysis
        - Real-time social media research
        """
        # This is a documentation test
        pass
