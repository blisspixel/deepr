"""Unit tests for the model capabilities registry (Phase 3a)."""

import pytest

from deepr.providers.registry import (
    MODEL_CAPABILITIES,
    ModelCapability,
    get_cheapest_model,
    get_fastest_model,
    get_largest_context_model,
    get_model_capability,
    get_models_by_specialization,
)


class TestModelCapabilities:
    """Test cases for model capabilities registry."""

    def test_registry_not_empty(self):
        """Test that registry contains model definitions."""
        assert len(MODEL_CAPABILITIES) > 0
        assert "openai/gpt-5.2" in MODEL_CAPABILITIES
        assert "xai/grok-4-fast" in MODEL_CAPABILITIES

    def test_all_capabilities_valid(self):
        """Test that all model capabilities have required fields."""
        for key, cap in MODEL_CAPABILITIES.items():
            assert isinstance(cap, ModelCapability)
            assert cap.provider is not None
            assert cap.model is not None
            assert cap.cost_per_query >= 0
            assert cap.latency_ms > 0
            assert cap.context_window > 0
            assert len(cap.specializations) > 0
            assert len(cap.strengths) > 0
            assert "/" in key  # Format: provider/model

    def test_get_model_capability(self):
        """Test getting model capability by provider and model."""
        # Valid model
        cap = get_model_capability("openai", "gpt-5.2")
        assert cap is not None
        assert cap.provider == "openai"
        assert cap.model == "gpt-5.2"

        # Invalid model
        cap = get_model_capability("invalid", "model")
        assert cap is None

    def test_get_models_by_specialization(self):
        """Test filtering models by specialization."""
        # Get fast models
        fast_models = get_models_by_specialization("speed")
        assert len(fast_models) > 0
        assert all("speed" in m.specializations for m in fast_models)

        # Results should be sorted by cost
        costs = [m.cost_per_query for m in fast_models]
        assert costs == sorted(costs)

        # Get reasoning models
        reasoning_models = get_models_by_specialization("reasoning")
        assert len(reasoning_models) > 0
        assert all("reasoning" in m.specializations for m in reasoning_models)

    def test_get_cheapest_model(self):
        """Test getting the cheapest model."""
        cheapest = get_cheapest_model()
        assert cheapest is not None

        # Should be cheaper than all other models
        for cap in MODEL_CAPABILITIES.values():
            assert cheapest.cost_per_query <= cap.cost_per_query

    def test_get_fastest_model(self):
        """Test getting the fastest model."""
        fastest = get_fastest_model()
        assert fastest is not None

        # Should be faster than all other models
        for cap in MODEL_CAPABILITIES.values():
            assert fastest.latency_ms <= cap.latency_ms

    def test_get_largest_context_model(self):
        """Test getting model with largest context window."""
        largest = get_largest_context_model()
        assert largest is not None

        # Should have largest context window
        for cap in MODEL_CAPABILITIES.values():
            assert largest.context_window >= cap.context_window

        # Gemini should have largest context (1M tokens)
        assert largest.provider == "gemini"
        assert largest.context_window >= 1_000_000

    def test_openai_models(self):
        """Test OpenAI model capabilities."""
        gpt5 = get_model_capability("openai", "gpt-5.2")
        assert gpt5 is not None
        assert "reasoning" in gpt5.specializations
        assert gpt5.context_window >= 128_000

        deep_research = get_model_capability("openai", "o4-mini-deep-research")
        assert deep_research is not None
        assert "research" in deep_research.specializations
        assert deep_research.cost_per_query > gpt5.cost_per_query  # More expensive

    def test_xai_models(self):
        """Test xAI (Grok) model capabilities."""
        grok = get_model_capability("xai", "grok-4-fast")
        assert grok is not None
        assert "speed" in grok.specializations
        assert grok.cost_per_query < 0.05  # Should be very cheap
        assert grok.latency_ms < 2000  # Should be fast

    def test_gemini_models(self):
        """Test Gemini model capabilities."""
        gemini_pro = get_model_capability("gemini", "gemini-3-pro")
        assert gemini_pro is not None
        assert "large_context" in gemini_pro.specializations
        assert gemini_pro.context_window >= 1_000_000

        gemini_flash = get_model_capability("gemini", "gemini-2.5-flash")
        assert gemini_flash is not None
        assert "speed" in gemini_flash.specializations
        assert gemini_flash.cost_per_query < 0.01  # Very cheap

    def test_cost_ordering(self):
        """Test that model costs make sense relative to capabilities."""
        cheapest = get_cheapest_model()
        deep_research = get_model_capability("openai", "o4-mini-deep-research")

        # Deep research should be much more expensive
        assert deep_research.cost_per_query > cheapest.cost_per_query * 10

    def test_specialization_coverage(self):
        """Test that all key specializations are covered."""
        required_specializations = [
            "speed",
            "reasoning",
            "research",
            "large_context",
        ]

        for spec in required_specializations:
            models = get_models_by_specialization(spec)
            assert len(models) > 0, f"No models found for specialization: {spec}"

    def test_weaknesses_documented(self):
        """Test that models have documented weaknesses."""
        for cap in MODEL_CAPABILITIES.values():
            assert len(cap.weaknesses) > 0, f"Model {cap.provider}/{cap.model} has no documented weaknesses"

    def test_cost_latency_tradeoff(self):
        """Test that there's a reasonable cost/latency tradeoff."""
        cheapest = get_cheapest_model()
        fastest = get_fastest_model()

        # Cheapest and fastest might be the same model (grok-4-fast)
        # But deep research should be expensive and slow
        deep_research = get_model_capability("openai", "o4-mini-deep-research")

        assert deep_research.cost_per_query > cheapest.cost_per_query
        assert deep_research.latency_ms > fastest.latency_ms


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
