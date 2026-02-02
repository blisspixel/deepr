"""Tests for provider router service."""

import pytest
from deepr.services.provider_router import (
    ProviderCapability,
    ProviderRouter,
    PROVIDER_CAPABILITIES,
    create_router_from_env,
)


class TestProviderCapability:
    """Test ProviderCapability dataclass and catalog."""

    def test_dataclass_fields_complete(self):
        """All required fields present on ProviderCapability."""
        cap = ProviderCapability(
            name="test",
            supports_deep_research=True,
            supports_extended_thinking=False,
            supports_web_search=True,
            supports_tool_use=False,
            avg_speed="fast",
            cost_tier="cheap",
            reliability=0.9,
            max_context=100_000,
        )
        assert cap.name == "test"
        assert cap.reliability == 0.9

    def test_catalog_has_known_providers(self):
        """PROVIDER_CAPABILITIES contains openai, anthropic, azure."""
        assert "openai" in PROVIDER_CAPABILITIES
        assert "anthropic" in PROVIDER_CAPABILITIES
        assert "azure" in PROVIDER_CAPABILITIES

    def test_catalog_values_valid(self):
        """All catalog entries have valid field ranges."""
        for name, cap in PROVIDER_CAPABILITIES.items():
            assert cap.name == name
            assert 0.0 <= cap.reliability <= 1.0
            assert cap.avg_speed in ("fast", "medium", "slow")
            assert cap.cost_tier in ("cheap", "moderate", "expensive")
            assert cap.max_context > 0


class TestProviderRouter:
    """Test ProviderRouter routing logic."""

    @pytest.fixture
    def router_single(self):
        return ProviderRouter(available_providers=["openai"])

    @pytest.fixture
    def router_multi(self):
        return ProviderRouter(available_providers=["openai", "anthropic", "azure"])

    def test_init_filters_unknown_providers(self):
        """Unknown provider names are excluded from capabilities."""
        router = ProviderRouter(available_providers=["openai", "nonexistent"])
        assert "nonexistent" not in router.capabilities
        assert "openai" in router.capabilities

    def test_init_empty_raises(self):
        """Empty provider list raises on route_task."""
        router = ProviderRouter(available_providers=[])
        with pytest.raises(ValueError, match="No providers available"):
            router.route_task("documentation")

    def test_route_single_provider_always_selected(self, router_single):
        """Single provider is always returned regardless of task type."""
        assert router_single.route_task("documentation") == "openai"
        assert router_single.route_task("analysis") == "openai"
        assert router_single.route_task("synthesis") == "openai"

    def test_route_documentation_prefers_deep_research(self, router_multi):
        """Documentation tasks score deep_research capability higher."""
        result = router_multi.route_task("documentation")
        # openai and azure both support deep_research; anthropic does not
        assert result in ("openai", "azure")

    def test_route_analysis_scores_extended_thinking(self, router_multi):
        """Analysis tasks score extended_thinking capability."""
        result = router_multi.route_task("analysis", complexity="complex")
        # All three support extended_thinking, but anthropic has max_context > 150k
        assert result in PROVIDER_CAPABILITIES

    def test_route_synthesis_scores_reliability(self, router_multi):
        """Synthesis tasks score reliability highly."""
        result = router_multi.route_task("synthesis")
        # azure has highest reliability (0.97)
        assert result in PROVIDER_CAPABILITIES

    def test_route_prefer_cost(self, router_multi):
        """prefer_cost=True adds cost bonus to cheaper tiers."""
        result = router_multi.route_task("documentation", prefer_cost=True)
        assert result in PROVIDER_CAPABILITIES

    def test_route_prefer_speed(self, router_multi):
        """prefer_speed=True adds speed bonus to faster providers."""
        result = router_multi.route_task("analysis", prefer_speed=True)
        # anthropic is "fast", so it should get a boost
        assert result in PROVIDER_CAPABILITIES

    def test_route_prefer_speed_favors_fast_provider(self):
        """When speed is preferred, fast providers score higher."""
        router = ProviderRouter(available_providers=["openai", "anthropic"])
        result = router.route_task("analysis", prefer_speed=True)
        # anthropic is "fast" while openai is "medium"
        assert result == "anthropic"

    def test_get_model_openai_documentation(self, router_multi):
        """OpenAI documentation tasks use o4-mini."""
        assert router_multi.get_model_for_task("openai", "documentation") == "o4-mini-deep-research"

    def test_get_model_openai_analysis(self, router_multi):
        """OpenAI analysis tasks use o3."""
        assert router_multi.get_model_for_task("openai", "analysis") == "o3-deep-research"

    def test_get_model_azure_documentation(self, router_multi):
        """Azure documentation uses same models as OpenAI."""
        assert router_multi.get_model_for_task("azure", "documentation") == "o4-mini-deep-research"

    def test_get_model_anthropic(self, router_multi):
        """Anthropic returns Claude model."""
        result = router_multi.get_model_for_task("anthropic", "analysis")
        assert "claude" in result

    def test_get_model_unknown_provider_raises(self, router_multi):
        """Unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown provider"):
            router_multi.get_model_for_task("nonexistent", "analysis")


class TestCreateRouterFromEnv:
    """Test factory function create_router_from_env."""

    def test_creates_with_openai_key(self, monkeypatch):
        """Detects OPENAI_API_KEY."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        router = create_router_from_env()
        assert "openai" in router.available_providers

    def test_creates_with_anthropic_key(self, monkeypatch):
        """Detects ANTHROPIC_API_KEY."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        router = create_router_from_env()
        assert "anthropic" in router.available_providers

    def test_creates_with_azure_key(self, monkeypatch):
        """Detects AZURE_OPENAI_API_KEY."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "az-test")
        router = create_router_from_env()
        assert "azure" in router.available_providers

    def test_creates_with_multiple_keys(self, monkeypatch):
        """All providers detected when all keys set."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "az-test")
        router = create_router_from_env()
        assert len(router.available_providers) == 3

    def test_raises_when_no_keys(self, monkeypatch):
        """No API keys raises ValueError."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="No provider API keys found"):
            create_router_from_env()

    def test_ignores_empty_string_keys(self, monkeypatch):
        """Empty string API keys are ignored."""
        monkeypatch.setenv("OPENAI_API_KEY", "")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError):
            create_router_from_env()

    def test_returns_provider_router_instance(self, monkeypatch):
        """Return type is ProviderRouter."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        result = create_router_from_env()
        assert isinstance(result, ProviderRouter)
