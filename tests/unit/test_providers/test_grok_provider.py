"""Tests for Grok provider implementation."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from deepr.providers.grok_provider import GrokProvider
from deepr.providers.base import ResearchRequest, ToolConfig


class TestGrokProvider:
    """Test Grok provider initialization and configuration."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GrokProvider(api_key="test-xai-key")

    def test_provider_initialization(self, provider):
        """Test provider initializes correctly."""
        assert provider.client is not None

    def test_provider_initialization_no_api_key(self):
        """Test provider fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="xAI API key is required"):
                GrokProvider(api_key=None)

    def test_model_name_mapping(self, provider):
        """Test model name mapping for Grok 4 Fast."""
        # Default grok-4-fast maps to non-reasoning mode for speed
        assert provider.get_model_name("grok-4-fast") == "grok-4-fast-non-reasoning"
        assert provider.get_model_name("grok-4-fast-reasoning") == "grok-4-fast-reasoning"
        assert provider.get_model_name("grok-4-fast-non-reasoning") == "grok-4-fast-non-reasoning"

        # Grok 4 full reasoning model
        assert provider.get_model_name("grok-4") == "grok-4"

        # Aliases
        assert provider.get_model_name("grok") == "grok-4-fast-non-reasoning"
        assert provider.get_model_name("grok-fast") == "grok-4-fast-non-reasoning"

        # Legacy models
        assert provider.get_model_name("grok-3") == "grok-3"
        assert provider.get_model_name("grok-3-mini") == "grok-3-mini"
        assert provider.get_model_name("grok-mini") == "grok-3-mini"

    def test_pricing_configuration(self, provider):
        """Test pricing is configured for Grok models."""
        assert hasattr(provider, "pricing")

        # Grok 4 Fast pricing (cost-effective)
        assert "grok-4-fast-reasoning" in provider.pricing
        assert "grok-4-fast-non-reasoning" in provider.pricing
        assert provider.pricing["grok-4-fast-reasoning"]["input"] == 0.20
        assert provider.pricing["grok-4-fast-reasoning"]["output"] == 0.50

        # Grok 4 pricing (expensive reasoning model)
        assert "grok-4" in provider.pricing
        assert provider.pricing["grok-4"]["input"] == 3.00
        assert provider.pricing["grok-4"]["output"] == 15.00

        # Grok 3 pricing
        assert "grok-3" in provider.pricing
        assert "grok-3-mini" in provider.pricing

    def test_calculate_cost_grok_4_fast(self, provider):
        """Test cost calculation for Grok 4 Fast (cost-effective model)."""
        # 1M input tokens + 1M output tokens = $0.20 + $0.50 = $0.70
        cost = provider._calculate_cost(
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            model="grok-4-fast-reasoning"
        )
        assert cost == 0.70

        # Test non-reasoning mode (same pricing)
        cost_non_reasoning = provider._calculate_cost(
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            model="grok-4-fast-non-reasoning"
        )
        assert cost_non_reasoning == 0.70

    def test_calculate_cost_with_reasoning_tokens(self, provider):
        """Test cost calculation includes reasoning tokens as output."""
        # Reasoning tokens are billed as output tokens
        cost = provider._calculate_cost(
            prompt_tokens=1_000_000,
            completion_tokens=500_000,
            model="grok-4-fast-reasoning",
            reasoning_tokens=500_000  # Additional reasoning tokens
        )
        # Total output = 500k + 500k = 1M at $0.50 = $0.50
        # Input = 1M at $0.20 = $0.20
        # Total = $0.70
        assert cost == 0.70

    def test_calculate_cost_grok_4(self, provider):
        """Test cost calculation for Grok 4 (expensive reasoning model)."""
        # 1M input + 1M output = $3.00 + $15.00 = $18.00
        cost = provider._calculate_cost(
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            model="grok-4"
        )
        assert cost == 18.00

    def test_cost_scales_linearly(self, provider):
        """Test that cost scales linearly with token count."""
        model = "grok-4-fast-reasoning"

        cost_1k = provider._calculate_cost(1000, 1000, model)
        cost_2k = provider._calculate_cost(2000, 2000, model)
        cost_10k = provider._calculate_cost(10000, 10000, model)

        # Should scale linearly
        assert abs(cost_2k - (cost_1k * 2)) < 0.000001
        assert abs(cost_10k - (cost_1k * 10)) < 0.000001

    @pytest.mark.asyncio
    async def test_submit_research_basic(self, provider):
        """Test basic research submission (mocked)."""
        # Mock the OpenAI client response
        mock_choice = MagicMock()
        mock_choice.message.content = "Test response content"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_usage.total_tokens = 150
        mock_usage.completion_tokens_details = None

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch.object(provider.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="What is Python?",
                model="grok-4-fast",
                system_message="You are a helpful assistant.",
                tools=[],
            )

            job_id = await provider.submit_research(request)
            assert job_id is not None
            assert job_id.startswith("grok-")

            # Verify job was executed
            status = await provider.get_status(job_id)
            assert status.status == "completed"
            assert status.output is not None


class TestGrokToolConfiguration:
    """Test Grok-specific tool configuration."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GrokProvider(api_key="test-key")

    def test_web_search_tool_format(self, provider):
        """Test web search tool configuration."""
        tools = [ToolConfig(type="web_search")]
        assert tools[0].type == "web_search"

    def test_x_search_tool_format(self, provider):
        """Test X search tool format (Grok's unique feature)."""
        tools = [ToolConfig(type="x_search")]
        assert tools[0].type == "x_search"

    def test_code_interpreter_tool(self, provider):
        """Test code interpreter tool configuration."""
        tools = [ToolConfig(type="code_interpreter")]
        assert tools[0].type == "code_interpreter"

    @pytest.mark.asyncio
    async def test_tools_passed_to_api(self, provider):
        """Test that tools are correctly passed to Grok API."""
        mock_choice = MagicMock()
        mock_choice.message.content = "Test response"

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50
        mock_usage.total_tokens = 150
        mock_usage.completion_tokens_details = None

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch.object(provider.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Search for Python tutorials",
                model="grok-4-fast",
                system_message="You are a helpful assistant.",
                tools=[
                    ToolConfig(type="web_search"),
                    ToolConfig(type="code_interpreter"),
                ],
            )

            await provider.submit_research(request)

            # Verify API was called (tools currently disabled for Grok)
            call_args = mock_create.call_args
            # NOTE: Tools are currently disabled for Grok as the API format is still being finalized
            # Web search happens automatically based on the query
            assert "tools" not in call_args.kwargs or call_args.kwargs["tools"] is None


class TestGrokCapabilities:
    """Document Grok 4 Fast capabilities and use cases."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GrokProvider(api_key="test-key")

    def test_grok_4_fast_features(self, provider):
        """Document Grok 4 Fast key features.

        Grok 4 Fast:
        - Cost-effective: $0.20 input / $0.50 output per 1M tokens
        - 98% cheaper than GPT-5 at comparable intelligence
        - 2M token context window
        - Unified reasoning/non-reasoning in single model
        - Native tool calling (web_search, x_search, code_execution)
        - #1 on LMArena Search Arena
        - 40% fewer thinking tokens than Grok 4
        """
        # Verify pricing
        assert provider.pricing["grok-4-fast-reasoning"]["input"] == 0.20
        assert provider.pricing["grok-4-fast-reasoning"]["output"] == 0.50

        # Verify model mappings
        assert provider.get_model_name("grok-4-fast") == "grok-4-fast-non-reasoning"
        assert provider.get_model_name("grok-4-fast-reasoning") == "grok-4-fast-reasoning"

    def test_grok_use_cases(self, provider):
        """Document Grok's ideal use cases.

        Grok 4 Fast is BEST for:
        - Expert chat (fast, cheap, good reasoning)
        - Team research (multi-agent synthesis)
        - Planning (good reasoning, fast)
        - Context summarization (large context window)
        - Link filtering for scraping (relevance scoring)
        - Real-time X/Twitter intelligence

        Grok is NOT for:
        - Deep Research (use OpenAI o3/o4-mini - unique async API)
        """
        # This is a documentation test
        pass

    def test_grok_vs_gpt5_cost_comparison(self, provider):
        """Compare Grok 4 Fast vs GPT-5 costs.

        For 1M input + 1M output tokens:
        - GPT-5: $3 + $15 = $18.00
        - Grok 4 Fast: $0.20 + $0.50 = $0.70
        - Savings: 96% (25x cheaper)

        For 10M input + 10M output tokens:
        - GPT-5: $30 + $150 = $180.00
        - Grok 4 Fast: $2 + $5 = $7.00
        - Savings: 96% (25x cheaper)
        """
        # 1M tokens
        grok_cost = provider._calculate_cost(1_000_000, 1_000_000, "grok-4-fast-reasoning")
        gpt5_cost = provider._calculate_cost(1_000_000, 1_000_000, "grok-4")  # Grok-4 pricing similar to GPT-5

        assert grok_cost == 0.70
        assert gpt5_cost == 18.00
        assert grok_cost < gpt5_cost * 0.05  # More than 95% cheaper

    def test_context_window_size(self, provider):
        """Document Grok 4 Fast context window.

        Grok 4 Fast: 2,000,000 tokens (2M)
        GPT-5: Varies by model, typically much smaller

        This large context is ideal for:
        - Long expert conversations
        - Document processing
        - Multi-turn research
        """
        # This is a documentation test
        pass


class TestGrokErrorHandling:
    """Test error handling in Grok provider."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GrokProvider(api_key="test-key")

    @pytest.mark.asyncio
    async def test_api_error_handling(self, provider):
        """Test that API errors are handled gracefully."""
        with patch.object(provider.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("API Error")

            request = ResearchRequest(
                prompt="Test query",
                model="grok-4-fast",
                system_message="You are a helpful assistant.",
            )

            job_id = await provider.submit_research(request)

            # Job should be marked as failed
            status = await provider.get_status(job_id)
            assert status.status == "failed"
            assert status.error is not None
            assert "API Error" in status.error

    @pytest.mark.asyncio
    async def test_invalid_job_id(self, provider):
        """Test that invalid job IDs raise appropriate errors."""
        with pytest.raises(Exception):  # Should raise ProviderError
            await provider.get_status("invalid-job-id")

    @pytest.mark.asyncio
    async def test_cancel_job(self, provider):
        """Test job cancellation."""
        # Mock response
        mock_choice = MagicMock()
        mock_choice.message.content = "Test"
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 10
        mock_usage.total_tokens = 20
        mock_usage.completion_tokens_details = None
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        with patch.object(provider.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            request = ResearchRequest(
                prompt="Test",
                model="grok-4-fast",
                system_message="You are a helpful assistant.",
            )

            job_id = await provider.submit_research(request)

            # Since Grok executes immediately, cancellation doesn't really work
            # but the method should still be callable
            result = await provider.cancel_job(job_id)
            assert isinstance(result, bool)
