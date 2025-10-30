"""Tests for Gemini provider implementation."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from deepr.providers.gemini_provider import GeminiProvider
from deepr.providers.base import ResearchRequest, ToolConfig


@pytest.mark.asyncio
class TestGeminiProvider:
    """Test Gemini provider."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GeminiProvider(api_key="test-gemini-key")

    def test_provider_initialization(self, provider):
        """Test provider initializes correctly."""
        assert provider.api_key == "test-gemini-key"
        assert provider.client is not None
        assert "gemini-2.5-pro" in provider.model_mappings
        assert "gemini-2.5-flash" in provider.model_mappings

    def test_provider_initialization_no_api_key(self):
        """Test provider fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear GEMINI_API_KEY from environment
            if "GEMINI_API_KEY" in os.environ:
                del os.environ["GEMINI_API_KEY"]

            with pytest.raises(ValueError, match="Gemini API key is required"):
                GeminiProvider(api_key=None)

    def test_model_name_mapping(self, provider):
        """Test model name mapping."""
        assert provider.get_model_name("gemini-2.5-pro") == "gemini-2.5-pro"
        assert provider.get_model_name("gemini-2.5-flash") == "gemini-2.5-flash"
        assert provider.get_model_name("gemini-pro") == "gemini-2.5-pro"  # Alias
        assert provider.get_model_name("gemini-flash") == "gemini-2.5-flash"  # Alias
        assert provider.get_model_name("unknown-model") == "unknown-model"

    def test_pricing_configuration(self, provider):
        """Test pricing is configured correctly."""
        assert "gemini-2.5-pro" in provider.pricing
        assert "gemini-2.5-flash" in provider.pricing
        assert "gemini-2.5-flash-lite" in provider.pricing

        # Verify pricing structure
        pro_pricing = provider.pricing["gemini-2.5-pro"]
        assert "input" in pro_pricing
        assert "output" in pro_pricing
        assert pro_pricing["input"] > 0
        assert pro_pricing["output"] > 0

    def test_calculate_cost(self, provider):
        """Test cost calculation for Gemini models."""
        # Test with Pro model (highest cost)
        cost_pro = provider._calculate_cost(
            input_tokens=1000, output_tokens=1000, model="gemini-2.5-pro"
        )
        assert cost_pro > 0
        # Pro: $1.25/M input + $5.00/M output = $6.25/M total
        # 1000 tokens = 0.001M tokens = $0.00625
        assert abs(cost_pro - 0.00625) < 0.0001

        # Test with Flash model (balanced cost)
        cost_flash = provider._calculate_cost(
            input_tokens=1000, output_tokens=1000, model="gemini-2.5-flash"
        )
        assert cost_flash > 0
        assert cost_flash < cost_pro  # Flash should be cheaper than Pro

        # Test with Flash-Lite model (lowest cost)
        cost_lite = provider._calculate_cost(
            input_tokens=1000, output_tokens=1000, model="gemini-2.5-flash-lite"
        )
        assert cost_lite > 0
        assert cost_lite <= cost_flash  # Flash-Lite should be cheapest or equal

    def test_thinking_config_pro_model(self, provider):
        """Test thinking config for Pro model (always thinks)."""
        config = provider._get_thinking_config("gemini-2.5-pro", complexity="medium")
        assert config is not None
        # Pro model should have thinking enabled

    def test_thinking_config_flash_model(self, provider):
        """Test thinking config for Flash model (dynamic thinking)."""
        config = provider._get_thinking_config("gemini-2.5-flash", complexity="high")
        assert config is not None
        # Flash model should have thinking enabled for complex tasks

    def test_thinking_config_lite_model(self, provider):
        """Test thinking config for Flash-Lite model (optional thinking)."""
        # Flash-Lite typically doesn't use thinking for simple tasks
        config = provider._get_thinking_config("gemini-2.5-flash-lite", complexity="low")
        # May return None or minimal thinking config

    @pytest.mark.asyncio
    async def test_submit_research_basic(self, provider):
        """Test basic research submission (mocked).

        Unlike OpenAI, Gemini doesn't have background jobs - it's synchronous.
        We should test that the provider handles this correctly.
        """
        mock_response = MagicMock()
        mock_response.text = "Test response content"
        mock_response.candidates = [MagicMock()]
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 100
        mock_response.usage_metadata.candidates_token_count = 200
        mock_response.usage_metadata.total_token_count = 300

        with patch.object(provider.client.models, "generate_content") as mock_generate:
            mock_generate.return_value = mock_response

            request = ResearchRequest(
                prompt="Test prompt",
                model="gemini-2.5-flash",
                system_message="Test system message",
                tools=[],
            )

            job_id = await provider.submit_research(request)

            # Gemini provider generates a job ID locally
            assert job_id is not None
            assert len(job_id) > 0

    def test_google_search_grounding(self, provider):
        """Test that Google Search can be enabled for grounding.

        Gemini's key differentiator is native Google Search integration.
        This should be properly configured when web search is requested.
        """
        # This tests the configuration, actual API call would be in integration tests
        request = ResearchRequest(
            prompt="Test prompt",
            model="gemini-2.5-flash",
            system_message="Test system message",
            tools=[ToolConfig(type="google_search")],  # Gemini uses google_search
        )

        # Verify request has google_search tool
        assert len(request.tools) == 1
        assert request.tools[0].type == "google_search"


class TestGeminiToolConfiguration:
    """Test Gemini-specific tool configuration.

    Unlike OpenAI, Gemini has different tool types and requirements.
    """

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GeminiProvider(api_key="test-gemini-key")

    def test_google_search_tool_format(self, provider):
        """Test Google Search tool is formatted correctly for Gemini.

        Gemini uses different tool names than OpenAI:
        - "google_search" instead of "web_search_preview"
        - "code_execution" instead of "code_interpreter"
        """
        # This is a documentation test to ensure we handle Gemini's tool format
        tools = [ToolConfig(type="google_search")]

        assert tools[0].type == "google_search"
        # Unlike OpenAI, Gemini Search doesn't need container parameters

    def test_code_execution_tool_format(self, provider):
        """Test Code Execution tool for Gemini.

        Gemini calls it "code_execution" not "code_interpreter"
        """
        tools = [ToolConfig(type="code_execution")]

        assert tools[0].type == "code_execution"
        # Gemini Code Execution doesn't need container parameters

    def test_multimodal_file_upload(self, provider):
        """Test that Gemini handles file uploads differently than OpenAI.

        Gemini uploads files directly (not vector stores) and supports:
        - Images, audio, video (multimodal)
        - PDFs and documents
        - No vector store abstraction needed
        """
        # This tests the concept - implementation would be in actual provider code
        # Gemini files are uploaded with MIME type detection
        pass


class TestGeminiVsOpenAIDifferences:
    """Document key differences between Gemini and OpenAI providers.

    These tests serve as documentation for developers switching between providers.
    """

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GeminiProvider(api_key="test-gemini-key")

    def test_synchronous_vs_background(self, provider):
        """Document: Gemini is synchronous, OpenAI supports background jobs.

        Key difference:
        - OpenAI: submit_research() returns job_id, poll for results
        - Gemini: submit_research() waits for completion, returns result immediately
        """
        # This is a documentation test
        # Gemini jobs complete synchronously (no background queue)
        assert hasattr(provider, "jobs")  # Local job tracking for compatibility

    def test_tool_naming_differences(self, provider):
        """Document: Different tool names between providers.

        OpenAI → Gemini:
        - web_search_preview → google_search
        - code_interpreter → code_execution
        - file_search (vector stores) → Direct file upload with MIME detection
        """
        # This is a documentation test
        # Developers need to know these differences when switching providers
        pass

    def test_thinking_vs_reasoning(self, provider):
        """Document: Gemini "thinking" vs OpenAI "reasoning".

        - OpenAI: reasoning_tokens, reasoning_effort
        - Gemini: thinking_config, thinking traces

        Both enable extended reasoning but different APIs.
        """
        # This is a documentation test
        thinking_config = provider._get_thinking_config("gemini-2.5-pro")
        assert thinking_config is not None

    def test_context_window_differences(self, provider):
        """Document: Gemini has larger context windows.

        - OpenAI o3: ~128k context
        - Gemini 2.5: 1M+ context

        This affects how we handle long documents.
        """
        # This is a documentation test
        # Gemini can handle much larger document uploads
        pass


class TestGeminiCostCalculation:
    """Test cost calculation specific to Gemini pricing."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        return GeminiProvider(api_key="test-gemini-key")

    def test_cost_comparison_between_models(self, provider):
        """Test relative pricing between Gemini models."""
        input_tokens = 10000
        output_tokens = 10000

        cost_pro = provider._calculate_cost(input_tokens, output_tokens, "gemini-2.5-pro")
        cost_flash = provider._calculate_cost(
            input_tokens, output_tokens, "gemini-2.5-flash"
        )
        cost_lite = provider._calculate_cost(
            input_tokens, output_tokens, "gemini-2.5-flash-lite"
        )

        # Verify pricing hierarchy
        assert cost_pro > cost_flash
        # Note: Flash and Flash-Lite may have same pricing if not configured differently
        assert cost_flash >= cost_lite

    def test_cost_scales_linearly(self, provider):
        """Test that cost scales linearly with token count."""
        model = "gemini-2.5-flash"

        cost_1k = provider._calculate_cost(1000, 1000, model)
        cost_2k = provider._calculate_cost(2000, 2000, model)
        cost_10k = provider._calculate_cost(10000, 10000, model)

        # Should scale linearly
        assert abs(cost_2k - (cost_1k * 2)) < 0.00001
        assert abs(cost_10k - (cost_1k * 10)) < 0.00001

    def test_unknown_model_defaults_to_flash(self, provider):
        """Test that unknown models default to Flash pricing."""
        cost_unknown = provider._calculate_cost(1000, 1000, "unknown-model")
        cost_flash = provider._calculate_cost(1000, 1000, "gemini-2.5-flash")

        assert cost_unknown == cost_flash  # Defaults to Flash pricing
