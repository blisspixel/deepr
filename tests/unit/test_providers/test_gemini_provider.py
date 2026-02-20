"""Tests for Gemini provider implementation."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.providers.gemini_provider import (
    DEEP_RESEARCH_AGENT,
    GeminiProvider,
    _is_deep_research_model,
)


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
        assert provider.get_model_name("gemini-3.1-pro-preview") == "gemini-3.1-pro-preview"
        assert provider.get_model_name("gemini-3.1-pro") == "gemini-3.1-pro-preview"  # Alias
        assert provider.get_model_name("gemini-2.5-pro") == "gemini-2.5-pro"
        assert provider.get_model_name("gemini-2.5-flash") == "gemini-2.5-flash"
        assert provider.get_model_name("gemini-pro") == "gemini-3.1-pro-preview"  # Default pro alias
        assert provider.get_model_name("gemini-flash") == "gemini-2.5-flash"  # Alias
        assert provider.get_model_name("unknown-model") == "unknown-model"

    def test_pricing_configuration(self, provider):
        """Test pricing is configured correctly."""
        assert "gemini-3.1-pro-preview" in provider.pricing
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
        cost_pro = provider._calculate_cost(input_tokens=1000, output_tokens=1000, model="gemini-2.5-pro")
        assert cost_pro > 0
        # Pro: $1.25/M input + $10.00/M output (includes thinking tokens)
        # 1000 tokens = 0.001M tokens = $0.01125
        assert abs(cost_pro - 0.01125) < 0.0001

        # Test with Flash model (balanced cost)
        cost_flash = provider._calculate_cost(input_tokens=1000, output_tokens=1000, model="gemini-2.5-flash")
        assert cost_flash > 0
        assert cost_flash < cost_pro  # Flash should be cheaper than Pro

        # Test with Flash-Lite model (lowest cost)
        cost_lite = provider._calculate_cost(input_tokens=1000, output_tokens=1000, model="gemini-2.5-flash-lite")
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

    def test_dual_mode_architecture(self, provider):
        """Document: Gemini supports both deep research and regular modes.

        Key difference from previous versions:
        - Deep research: submit_research() with deep-research model uses Interactions API (async background)
        - Regular models: submit_research() with gemini-2.5-* uses generate_content (synchronous)
        """
        assert hasattr(provider, "jobs")  # Regular job tracking
        assert hasattr(provider, "_deep_research_jobs")  # Deep research tracking

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
        cost_flash = provider._calculate_cost(input_tokens, output_tokens, "gemini-2.5-flash")
        cost_lite = provider._calculate_cost(input_tokens, output_tokens, "gemini-2.5-flash-lite")

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

    def test_deep_research_cost_returns_estimate(self, provider):
        """Test that deep research models return a flat cost estimate."""
        cost = provider._calculate_cost(0, 0, DEEP_RESEARCH_AGENT)
        assert cost == provider.deep_research_cost_estimate


class TestDeepResearchModelDetection:
    """Test deep research model detection and routing."""

    def test_is_deep_research_agent_id(self):
        """The agent ID itself is detected as deep research."""
        assert _is_deep_research_model(DEEP_RESEARCH_AGENT) is True

    def test_is_deep_research_alias(self):
        """Model names containing 'deep-research' are detected."""
        assert _is_deep_research_model("gemini-deep-research") is True
        assert _is_deep_research_model("deep-research") is True

    def test_regular_models_not_deep_research(self):
        """Regular Gemini models are not deep research."""
        assert _is_deep_research_model("gemini-2.5-pro") is False
        assert _is_deep_research_model("gemini-2.5-flash") is False
        assert _is_deep_research_model("gemini-2.5-flash-lite") is False

    def test_model_mapping_includes_deep_research(self):
        """Model mappings include deep research aliases."""
        provider = GeminiProvider(api_key="test-key")
        assert provider.get_model_name("gemini-deep-research") == DEEP_RESEARCH_AGENT
        assert provider.get_model_name("deep-research") == DEEP_RESEARCH_AGENT


@pytest.mark.asyncio
class TestDeepResearchSubmission:
    """Test deep research submission via Interactions API."""

    @pytest.fixture
    def provider(self):
        p = GeminiProvider(api_key="test-gemini-key")
        # Replace client with a full mock to avoid property descriptor issues
        p.client = MagicMock()
        return p

    async def test_submit_deep_research_creates_interaction(self, provider):
        """Deep research calls client.interactions.create with background=True."""
        mock_interaction = MagicMock()
        mock_interaction.id = "interaction-abc123"
        provider.client.interactions.create.return_value = mock_interaction

        request = ResearchRequest(
            prompt="Research quantum computing applications",
            model="gemini-deep-research",
            system_message="You are a research assistant",
            tools=[],
        )

        job_id = await provider.submit_research(request)

        assert job_id == "interaction-abc123"
        provider.client.interactions.create.assert_called_once()
        call_kwargs = provider.client.interactions.create.call_args[1]
        assert call_kwargs["agent"] == DEEP_RESEARCH_AGENT
        assert call_kwargs["background"] is True
        assert "You are a research assistant" in call_kwargs["input"]
        assert "Research quantum computing" in call_kwargs["input"]

    async def test_submit_deep_research_tracked(self, provider):
        """Deep research jobs are tracked in _deep_research_jobs."""
        mock_interaction = MagicMock()
        mock_interaction.id = "interaction-xyz"
        provider.client.interactions.create.return_value = mock_interaction

        request = ResearchRequest(prompt="Test", model="deep-research", system_message="", tools=[])
        job_id = await provider.submit_research(request)

        assert job_id in provider._deep_research_jobs
        assert provider._deep_research_jobs[job_id]["status"] == "in_progress"
        assert provider._deep_research_jobs[job_id]["model"] == DEEP_RESEARCH_AGENT

    async def test_regular_model_uses_generate_content(self, provider):
        """Non-deep-research models still use generate_content (regression test)."""
        mock_chunk = MagicMock()
        mock_part = MagicMock()
        mock_part.text = "Regular response"
        mock_part.thought = False
        mock_chunk.candidates = [MagicMock()]
        mock_chunk.candidates[0].content.parts = [mock_part]
        provider.client.models.generate_content_stream.return_value = [mock_chunk]

        request = ResearchRequest(
            prompt="Simple question",
            model="gemini-2.5-flash",
            system_message="",
            tools=[],
        )
        job_id = await provider.submit_research(request)

        assert job_id.startswith("gemini-")
        assert job_id not in provider._deep_research_jobs
        assert job_id in provider.jobs


@pytest.mark.asyncio
class TestDeepResearchStatus:
    """Test deep research status polling."""

    @pytest.fixture
    def provider(self):
        p = GeminiProvider(api_key="test-gemini-key")
        p.client = MagicMock()
        return p

    async def test_get_status_completed(self, provider):
        """Completed deep research returns content and citations."""
        provider._deep_research_jobs["int-123"] = {
            "status": "in_progress",
            "created_at": None,
            "model": DEEP_RESEARCH_AGENT,
            "file_store_name": None,
            "request": MagicMock(),
        }

        mock_interaction = MagicMock()
        mock_interaction.status = "completed"
        mock_output = MagicMock()
        mock_output.text = "Deep research findings..."
        mock_output.grounding_metadata = None
        mock_interaction.outputs = [mock_output]
        provider.client.interactions.get.return_value = mock_interaction

        response = await provider.get_status("int-123")

        assert response.status == "completed"
        assert response.model == DEEP_RESEARCH_AGENT
        assert response.output is not None
        assert response.output[0]["content"][0]["text"] == "Deep research findings..."

    async def test_get_status_failed(self, provider):
        """Failed deep research returns error."""
        provider._deep_research_jobs["int-fail"] = {
            "status": "in_progress",
            "created_at": None,
            "model": DEEP_RESEARCH_AGENT,
            "file_store_name": None,
            "request": MagicMock(),
        }

        mock_interaction = MagicMock()
        mock_interaction.status = "failed"
        mock_interaction.error = "Rate limit exceeded"
        provider.client.interactions.get.return_value = mock_interaction

        response = await provider.get_status("int-fail")

        assert response.status == "failed"
        assert "Rate limit" in response.error

    async def test_get_status_still_pending(self, provider):
        """Pending deep research returns in_progress status."""
        provider._deep_research_jobs["int-pending"] = {
            "status": "in_progress",
            "created_at": None,
            "model": DEEP_RESEARCH_AGENT,
            "file_store_name": None,
            "request": MagicMock(),
        }

        mock_interaction = MagicMock()
        mock_interaction.status = "pending"
        provider.client.interactions.get.return_value = mock_interaction

        response = await provider.get_status("int-pending")

        assert response.status == "in_progress"

    async def test_get_status_returns_cached_on_complete(self, provider):
        """Once completed, get_status returns cached result without API call."""
        provider._deep_research_jobs["int-cached"] = {
            "status": "completed",
            "created_at": None,
            "completed_at": None,
            "model": DEEP_RESEARCH_AGENT,
            "output": "Cached result",
            "citations": [],
            "search_queries_count": 5,
        }

        response = await provider.get_status("int-cached")

        # Should NOT have called interactions.get since already completed
        provider.client.interactions.get.assert_not_called()
        assert response.status == "completed"
        assert response.output[0]["content"][0]["text"] == "Cached result"


class TestAdaptivePolling:
    """Test adaptive polling interval."""

    def test_fast_interval_first_minute(self):
        """First 60 seconds polls every 5s."""
        assert GeminiProvider.get_poll_interval(0) == 5.0
        assert GeminiProvider.get_poll_interval(30) == 5.0
        assert GeminiProvider.get_poll_interval(59) == 5.0

    def test_normal_interval_one_to_five_minutes(self):
        """60-300 seconds polls every 10s."""
        assert GeminiProvider.get_poll_interval(60) == 10.0
        assert GeminiProvider.get_poll_interval(180) == 10.0
        assert GeminiProvider.get_poll_interval(299) == 10.0

    def test_slow_interval_after_five_minutes(self):
        """After 300 seconds polls every 20s."""
        assert GeminiProvider.get_poll_interval(300) == 20.0
        assert GeminiProvider.get_poll_interval(600) == 20.0
        assert GeminiProvider.get_poll_interval(1800) == 20.0


class TestCitationUrlResolution:
    """Test Google redirect URL resolution."""

    @pytest.mark.asyncio
    async def test_non_redirect_url_passes_through(self):
        """Non-redirect URLs are returned unchanged."""
        url = "https://example.com/article"
        result = await GeminiProvider.resolve_redirect_url(url)
        assert result == url

    @pytest.mark.asyncio
    async def test_redirect_url_resolved(self):
        """Google redirect URLs are resolved via httpx."""
        redirect_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc123"

        mock_response = MagicMock()
        mock_response.url = "https://real-source.com/article"

        mock_client = AsyncMock()
        mock_client.head.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await GeminiProvider.resolve_redirect_url(redirect_url)
            assert result == "https://real-source.com/article"

    @pytest.mark.asyncio
    async def test_redirect_url_fallback_on_error(self):
        """On error, returns original URL as fallback."""
        redirect_url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc123"

        with patch("httpx.AsyncClient", side_effect=httpx.NetworkError("Connection failed")):
            result = await GeminiProvider.resolve_redirect_url(redirect_url)
            assert result == redirect_url  # Falls back to original


@pytest.mark.asyncio
class TestDeepResearchWithFileStore:
    """Test file search store integration for deep research."""

    @pytest.fixture
    def provider(self):
        p = GeminiProvider(api_key="test-gemini-key")
        p.client = MagicMock()
        return p

    async def test_submit_with_documents_creates_file_store(self, provider):
        """Submitting with document_ids creates a file search store."""
        mock_store = MagicMock()
        mock_store.name = "stores/test-store"
        provider.client.file_search_stores.create.return_value = mock_store

        mock_interaction = MagicMock()
        mock_interaction.id = "int-with-docs"
        provider.client.interactions.create.return_value = mock_interaction

        request = ResearchRequest(
            prompt="Research with context",
            model="gemini-deep-research",
            system_message="",
            tools=[],
            document_ids=["file-1", "file-2"],
        )

        job_id = await provider.submit_research(request)

        assert job_id == "int-with-docs"
        provider.client.file_search_stores.create.assert_called_once()
        # Verify file_search tool was passed
        call_kwargs = provider.client.interactions.create.call_args[1]
        assert "tools" in call_kwargs
        assert call_kwargs["tools"][0]["type"] == "file_search"

    async def test_cleanup_on_completion(self, provider):
        """File search store is cleaned up when research completes."""
        provider._deep_research_jobs["int-cleanup"] = {
            "status": "in_progress",
            "created_at": None,
            "model": DEEP_RESEARCH_AGENT,
            "file_store_name": "stores/to-cleanup",
            "request": MagicMock(),
        }

        mock_interaction = MagicMock()
        mock_interaction.status = "completed"
        mock_output = MagicMock()
        mock_output.text = "Result"
        mock_output.grounding_metadata = None
        mock_interaction.outputs = [mock_output]
        provider.client.interactions.get.return_value = mock_interaction

        with patch.object(provider, "_cleanup_file_search_store", new_callable=AsyncMock) as mock_cleanup:
            await provider.get_status("int-cleanup")

            mock_cleanup.assert_called_once_with("stores/to-cleanup")
