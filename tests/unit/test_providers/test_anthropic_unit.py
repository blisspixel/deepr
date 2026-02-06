"""Tests for Anthropic Claude provider.

Requirements: 1.3 - Test Coverage
"""

from unittest.mock import patch

import pytest

# Import only if anthropic is available
try:
    from anthropic import AnthropicError

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    AnthropicError = Exception


class TestAnthropicProviderPricing:
    """Tests for Anthropic pricing constants."""

    def test_pricing_dict_has_required_models(self):
        """Should have pricing for all supported models."""
        from deepr.providers.anthropic_provider import ANTHROPIC_PRICING

        required_models = [
            "claude-opus-4-5",
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
        ]

        for model in required_models:
            assert model in ANTHROPIC_PRICING
            assert "input" in ANTHROPIC_PRICING[model]
            assert "output" in ANTHROPIC_PRICING[model]

    def test_pricing_values_are_numeric(self):
        """Should have numeric pricing values."""
        from deepr.providers.anthropic_provider import ANTHROPIC_PRICING

        for model, prices in ANTHROPIC_PRICING.items():
            assert isinstance(prices["input"], (int, float))
            assert isinstance(prices["output"], (int, float))
            # thinking can be None (e.g., haiku)
            if prices.get("thinking") is not None:
                assert isinstance(prices["thinking"], (int, float))

    def test_tool_pricing_available(self):
        """Should have tool pricing."""
        from deepr.providers.anthropic_provider import ANTHROPIC_TOOL_PRICING

        assert "web_search" in ANTHROPIC_TOOL_PRICING
        assert ANTHROPIC_TOOL_PRICING["web_search"] == 10.00

    def test_cache_pricing_available(self):
        """Should have cache pricing."""
        from deepr.providers.anthropic_provider import ANTHROPIC_CACHE_PRICING

        assert "claude-opus-4-5" in ANTHROPIC_CACHE_PRICING
        assert "cache_write" in ANTHROPIC_CACHE_PRICING["claude-opus-4-5"]
        assert "cache_read" in ANTHROPIC_CACHE_PRICING["claude-opus-4-5"]


class TestAnthropicProviderConstants:
    """Tests for provider constants."""

    def test_supported_models_list(self):
        """Should have supported models list."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        assert len(AnthropicProvider.SUPPORTED_MODELS) > 0
        assert "claude-opus-4-5" in AnthropicProvider.SUPPORTED_MODELS
        assert "claude-sonnet-4-5" in AnthropicProvider.SUPPORTED_MODELS

    def test_recommended_models_dict(self):
        """Should have recommended models by use case."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        assert "research" in AnthropicProvider.RECOMMENDED_MODELS
        assert "balanced" in AnthropicProvider.RECOMMENDED_MODELS
        assert "fast" in AnthropicProvider.RECOMMENDED_MODELS


@pytest.mark.skipif(not ANTHROPIC_AVAILABLE, reason="Anthropic SDK not installed")
class TestAnthropicProviderInit:
    """Tests for AnthropicProvider initialization."""

    def test_init_fails_without_api_key(self):
        """Should fail without API key."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                AnthropicProvider()

    def test_init_with_env_key(self):
        """Should initialize with env var API key."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    provider = AnthropicProvider()
                    assert provider.api_key == "test-key"

    def test_init_with_explicit_key(self):
        """Should use explicit API key over env var."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    provider = AnthropicProvider(api_key="explicit-key")
                    assert provider.api_key == "explicit-key"

    def test_init_sets_defaults(self):
        """Should set default values."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    provider = AnthropicProvider()

                    assert provider.model == "claude-opus-4-5"
                    assert provider.thinking_budget >= 1024

    def test_init_custom_model(self):
        """Should accept custom model."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    provider = AnthropicProvider(model="claude-sonnet-4-5")
                    assert provider.model == "claude-sonnet-4-5"

    def test_thinking_budget_minimum(self):
        """Should enforce minimum thinking budget."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    provider = AnthropicProvider(thinking_budget=100)
                    assert provider.thinking_budget >= 1024


@pytest.mark.skipif(not ANTHROPIC_AVAILABLE, reason="Anthropic SDK not installed")
class TestAnthropicProviderModelMapping:
    """Tests for model name mapping."""

    @pytest.fixture
    def provider(self):
        """Create provider with mocked client."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    return AnthropicProvider()

    def test_map_opus(self, provider):
        """Should map opus variants."""
        assert provider.get_model_name("claude-opus") == "claude-opus-4-5"
        assert provider.get_model_name("claude-4-opus") == "claude-opus-4-5"

    def test_map_sonnet(self, provider):
        """Should map sonnet variants."""
        assert provider.get_model_name("claude-sonnet") == "claude-sonnet-4-5"

    def test_map_haiku(self, provider):
        """Should map haiku variants."""
        assert provider.get_model_name("claude-haiku") == "claude-haiku-4-5"

    def test_map_unknown_returns_default(self, provider):
        """Should return default model for unknown keys."""
        result = provider.get_model_name("unknown-model")
        assert result == provider.model


@pytest.mark.skipif(not ANTHROPIC_AVAILABLE, reason="Anthropic SDK not installed")
class TestAnthropicProviderHelpers:
    """Tests for private helper methods."""

    @pytest.fixture
    def provider(self):
        """Create provider with mocked client."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    return AnthropicProvider()

    def test_build_research_system_prompt(self, provider):
        """Should build system prompt."""
        from deepr.providers.base import ResearchRequest

        request = ResearchRequest(
            prompt="Test query", model="claude-opus-4-5", system_message="You are a helpful assistant"
        )

        prompt = provider._build_research_system_prompt(request)

        assert "deep research" in prompt.lower()
        assert "Extended Thinking" in prompt

    def test_build_research_prompt_minimal(self, provider):
        """Should build user prompt with minimal fields."""
        from deepr.providers.base import ResearchRequest

        request = ResearchRequest(
            prompt="What is machine learning?", model="claude-opus-4-5", system_message="You are a helpful assistant"
        )

        prompt = provider._build_research_prompt(request)

        assert "What is machine learning?" in prompt

    def test_format_research_report(self, provider):
        """Should format research report."""
        from deepr.providers.base import ResearchRequest

        request = ResearchRequest(
            prompt="Test query", model="claude-opus-4-5", system_message="You are a helpful assistant"
        )

        report = provider._format_research_report(
            thinking="Thought process here", findings="Research findings here", tool_calls=[], request=request
        )

        assert "# Research Report" in report
        assert "Test query" in report
        assert "Research findings here" in report

    def test_format_research_report_with_tools(self, provider):
        """Should include tool calls in report."""
        from deepr.providers.base import ResearchRequest

        request = ResearchRequest(
            prompt="Test query", model="claude-opus-4-5", system_message="You are a helpful assistant"
        )

        report = provider._format_research_report(
            thinking="",
            findings="Findings",
            tool_calls=[{"tool": "web_search", "input": {"query": "test"}, "success": True}],
            request=request,
        )

        assert "Tool Usage" in report
        assert "web_search" in report


@pytest.mark.skipif(not ANTHROPIC_AVAILABLE, reason="Anthropic SDK not installed")
class TestAnthropicProviderGetStatus:
    """Tests for get_status method."""

    @pytest.fixture
    def provider(self):
        """Create provider with mocked client."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    return AnthropicProvider()

    @pytest.mark.asyncio
    async def test_get_status_returns_completed(self, provider):
        """Should return completed status (Anthropic is synchronous)."""
        response = await provider.get_status("job-123")

        assert response.status == "completed"
        assert response.id == "job-123"


@pytest.mark.skipif(not ANTHROPIC_AVAILABLE, reason="Anthropic SDK not installed")
class TestAnthropicProviderCancel:
    """Tests for cancel_job method."""

    @pytest.fixture
    def provider(self):
        """Create provider with mocked client."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    return AnthropicProvider()

    @pytest.mark.asyncio
    async def test_cancel_returns_false(self, provider):
        """Should return False (not supported)."""
        result = await provider.cancel_job("job-123")

        assert result is False


@pytest.mark.skipif(not ANTHROPIC_AVAILABLE, reason="Anthropic SDK not installed")
class TestAnthropicProviderNotImplemented:
    """Tests for not implemented methods."""

    @pytest.fixture
    def provider(self):
        """Create provider with mocked client."""
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    return AnthropicProvider()

    @pytest.mark.asyncio
    async def test_upload_document_not_implemented(self, provider):
        """Should raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await provider.upload_document("test.txt")

    @pytest.mark.asyncio
    async def test_create_vector_store_not_implemented(self, provider):
        """Should raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await provider.create_vector_store("test", [])

    @pytest.mark.asyncio
    async def test_wait_for_vector_store_not_implemented(self, provider):
        """Should raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await provider.wait_for_vector_store("vs-123")

    @pytest.mark.asyncio
    async def test_delete_vector_store_not_implemented(self, provider):
        """Should raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await provider.delete_vector_store("vs-123")

    @pytest.mark.asyncio
    async def test_list_vector_stores_not_implemented(self, provider):
        """Should raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await provider.list_vector_stores()
