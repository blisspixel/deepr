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

                    assert provider.model == "claude-opus-4-8"
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
        assert provider.get_model_name("claude-opus") == "claude-opus-4-8"
        assert provider.get_model_name("claude-4-opus") == "claude-opus-4-8"

    def test_map_fable(self, provider):
        """Should map fable to the frontier model."""
        assert provider.get_model_name("claude-fable") == "claude-fable-5"

    def test_map_sonnet(self, provider):
        """Should map sonnet variants."""
        assert provider.get_model_name("claude-sonnet") == "claude-sonnet-4-6"

    def test_map_haiku(self, provider):
        """Should map haiku variants."""
        assert provider.get_model_name("claude-haiku") == "claude-haiku-4-5"

    def test_map_unknown_returns_default(self, provider):
        """Should return default model for unknown keys."""
        result = provider.get_model_name("unknown-model")
        assert result == provider.model


@pytest.mark.skipif(not ANTHROPIC_AVAILABLE, reason="Anthropic SDK not installed")
class TestAnthropicThinkingParam:
    """Tests for model-aware thinking configuration.

    Adaptive-only models reject ``budget_tokens`` with a 400, so the
    provider must select the thinking shape per model.
    """

    def _provider(self, model):
        from deepr.providers.anthropic_provider import AnthropicProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("deepr.providers.anthropic_provider.Anthropic"):
                with patch("deepr.providers.anthropic_provider.ToolRegistry"):
                    return AnthropicProvider(model=model)

    @pytest.mark.parametrize(
        "model",
        [
            "claude-fable-5",
            "claude-opus-4-8",
            "claude-opus-4-7",
            "claude-opus-4-6",
            "claude-sonnet-4-6",
        ],
    )
    def test_adaptive_models_use_adaptive(self, model):
        """4.6+/Fable must use adaptive thinking (budget_tokens 400s)."""
        provider = self._provider(model)
        assert provider._build_thinking_param() == {"type": "adaptive"}

    @pytest.mark.parametrize("model", ["claude-opus-4-5", "claude-sonnet-4-5", "claude-opus-4-1"])
    def test_legacy_models_use_budget(self, model):
        """Pre-4.6 models keep the enabled+budget form."""
        provider = self._provider(model)
        param = provider._build_thinking_param()
        assert param is not None
        assert param["type"] == "enabled"
        assert param["budget_tokens"] == provider.thinking_budget

    def test_haiku_omits_thinking(self):
        """Haiku has no Extended Thinking - param must be omitted."""
        provider = self._provider("claude-haiku-4-5")
        assert provider._build_thinking_param() is None


class TestFable5Pricing:
    """Claude Fable 5 must be priced everywhere money is calculated.

    An unregistered model silently falls back to o4-mini pricing
    ($1.10/$4.40), which would under-bill a $10/$50 model ~10x.
    """

    def test_fable_in_provider_pricing(self):
        from deepr.providers.anthropic_provider import ANTHROPIC_PRICING

        assert ANTHROPIC_PRICING["claude-fable-5"]["input"] == 10.00
        assert ANTHROPIC_PRICING["claude-fable-5"]["output"] == 50.00

    def test_fable_in_registry_token_pricing(self):
        from deepr.providers.registry import get_token_pricing

        prices = get_token_pricing("claude-fable-5")
        assert prices["input"] == 10.00
        assert prices["output"] == 50.00

    def test_current_anthropic_models_in_registry_pricing(self):
        """Every current Anthropic model must resolve to its own price."""
        from deepr.providers.registry import get_token_pricing

        expected = {
            "claude-fable-5": (10.00, 50.00),
            "claude-opus-4-8": (5.00, 25.00),
            "claude-opus-4-7": (5.00, 25.00),
            "claude-opus-4-6": (5.00, 25.00),
            "claude-sonnet-4-6": (3.00, 15.00),
            "claude-sonnet-4-5": (3.00, 15.00),
            "claude-haiku-4-5": (1.00, 5.00),
        }
        for model, (inp, out) in expected.items():
            prices = get_token_pricing(model)
            assert prices["input"] == inp, f"{model} input price wrong: {prices}"
            assert prices["output"] == out, f"{model} output price wrong: {prices}"


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
    async def test_get_status_unknown_job_returns_failed(self, provider):
        """Unknown job_id returns failed (the old behaviour returned completed
        with $0 cost for any string, masking provider spend in the cost ledger)."""
        response = await provider.get_status("unknown-job-id")

        assert response.status == "failed"
        assert response.id == "unknown-job-id"
        assert response.error and "Unknown Anthropic job id" in response.error

    @pytest.mark.asyncio
    async def test_get_status_returns_stored_completed(self, provider):
        """A job_id from a real submit_research returns the stored
        ResearchResponse, including accumulated usage and output."""
        from deepr.providers.base import ResearchResponse, UsageStats

        usage = UsageStats(input_tokens=100, output_tokens=200, reasoning_tokens=0)
        provider._jobs["job-real"] = ResearchResponse(
            id="job-real",
            status="completed",
            output=[{"type": "message", "content": [{"type": "text", "text": "ok"}]}],
            usage=usage,
        )

        response = await provider.get_status("job-real")

        assert response.status == "completed"
        assert response.id == "job-real"
        assert response.usage is not None and response.usage.input_tokens == 100


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


class TestCreateProviderRedactedKey:
    """create_provider must not pass load_config()'s "***" placeholder through.

    Live-validation regression: load_config() redacts api_key to "***" for
    safe logging, but ~30 CLI call sites pass that dict value into
    create_provider, which overrode every provider's env-var fallback with a
    masked string and 401'd at the first real API call.
    """

    def test_redacted_key_falls_back_to_env(self, monkeypatch):
        from deepr.providers import create_provider

        monkeypatch.setenv("OPENAI_API_KEY", "sk-real-from-env")
        provider = create_provider("openai", api_key="***")
        assert provider.api_key == "sk-real-from-env"

    def test_empty_key_falls_back_to_env(self, monkeypatch):
        from deepr.providers import create_provider

        monkeypatch.setenv("OPENAI_API_KEY", "sk-real-from-env")
        provider = create_provider("openai", api_key="")
        assert provider.api_key == "sk-real-from-env"

    def test_real_key_passes_through(self, monkeypatch):
        from deepr.providers import create_provider

        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-should-lose")
        provider = create_provider("openai", api_key="sk-explicit-wins")
        assert provider.api_key == "sk-explicit-wins"
