"""Unit tests for the model capabilities registry (Phase 3a)."""

import pytest

from deepr.providers.registry import (
    MODEL_CAPABILITIES,
    ModelCapability,
    get_cached_input_pricing,
    get_cheapest_model,
    get_cost_estimate,
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
        assert "openai/gpt-5.4" in MODEL_CAPABILITIES
        assert "openai/gpt-5.4-pro" in MODEL_CAPABILITIES
        assert "xai/grok-4-20-reasoning" in MODEL_CAPABILITIES

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
        cap = get_model_capability("openai", "gpt-5.4")
        assert cap is not None
        assert cap.provider == "openai"
        assert cap.model == "gpt-5.4"

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

        # xAI Grok 4.1 has 2M context (largest in registry)
        assert largest.provider == "xai"
        assert largest.context_window >= 2_000_000

    def test_openai_models(self):
        """Test OpenAI model capabilities."""
        gpt54 = get_model_capability("openai", "gpt-5.4")
        assert gpt54 is not None
        assert "reasoning" in gpt54.specializations
        assert gpt54.context_window >= 1_000_000

        gpt54_pro = get_model_capability("openai", "gpt-5.4-pro")
        assert gpt54_pro is not None
        assert "reasoning" in gpt54_pro.specializations
        assert gpt54_pro.context_window >= 1_000_000

        deep_research = get_model_capability("openai", "o4-mini-deep-research")
        assert deep_research is not None
        assert "research" in deep_research.specializations
        assert deep_research.cost_per_query > gpt54.cost_per_query  # More expensive

    def test_xai_models(self):
        """Test xAI (Grok) model capabilities."""
        grok = get_model_capability("xai", "grok-4-1-fast-non-reasoning")
        assert grok is not None
        assert "speed" in grok.specializations
        assert grok.cost_per_query < 0.05  # Should be very cheap
        assert grok.latency_ms < 2000  # Should be fast

        grok_41_nr = get_model_capability("xai", "grok-4-1-fast-non-reasoning")
        assert grok_41_nr is not None
        assert "speed" in grok_41_nr.specializations

    def test_gemini_models(self):
        """Test Gemini model capabilities."""
        gemini_pro = get_model_capability("gemini", "gemini-3.1-pro-preview")
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

        # Cheapest and fastest might be the same model (grok-4-1-fast-non-reasoning)
        # But deep research should be expensive and slow
        deep_research = get_model_capability("openai", "o4-mini-deep-research")

        assert deep_research.cost_per_query > cheapest.cost_per_query
        assert deep_research.latency_ms > fastest.latency_ms


class TestCostEstimateMatching:
    """Regression tests: get_cost_estimate must resolve the most specific model.

    A prior first-substring-match fallback resolved snapshot/variant strings to
    the shorter, wrong family member — over-charging (mini -> full price) and,
    worse, under-charging (gpt-5.4-pro-<date> -> cheaper gpt-5.4), which lets
    budget pre-flight approve an expensive job against an underestimate.
    """

    def test_exact_keys(self):
        assert get_cost_estimate("gpt-5.4") == 0.30
        assert get_cost_estimate("gpt-5.4-mini") == 0.05
        assert get_cost_estimate("gpt-5.4-nano") == 0.01

    def test_snapshot_resolves_to_specific_model_not_prefix(self):
        # mini/nano snapshots must NOT resolve to the more expensive gpt-5.4
        assert get_cost_estimate("gpt-5.4-mini-2026-03-17") == 0.05
        assert get_cost_estimate("gpt-5.4-nano-2026-03-17") == 0.01

    def test_pro_snapshot_does_not_underestimate(self):
        # The dangerous direction: must resolve to the pro price, not gpt-5.4
        assert get_cost_estimate("gpt-5.4-pro-2026-03-05") == 0.90
        assert get_cost_estimate("gpt-5.5-pro-2026-04-23") == 1.50

    def test_dotted_and_hyphenated_grok_equivalent(self):
        # Normalization: dotted API form and hyphenated registry form match
        assert get_cost_estimate("grok-4.3") == get_cost_estimate("grok-4-3")

    def test_tiered_pricing_preserved(self):
        base = get_cost_estimate("gemini-3.1-pro-preview")
        tiered = get_cost_estimate("gemini-3.1-pro-preview", input_tokens=300_000)
        assert tiered == round(base * 2.0, 4)

    def test_unknown_model_returns_default(self):
        assert get_cost_estimate("totally-made-up-model-xyz") == 0.20


class TestTokenPricingTiers:
    """Settlement-side pricing must match what the provider actually bills.

    Tiered pricing (Gemini 3.x Pro above 200K input tokens: 2x input,
    1.5x output) previously applied only to pre-flight estimates; actual
    cost settlement silently used base rates, under-recording large jobs.
    """

    def test_base_rates_below_threshold(self):
        from deepr.providers.registry import get_token_pricing

        prices = get_token_pricing("gemini-3.1-pro-preview", input_tokens=100_000)
        assert prices == get_token_pricing("gemini-3.1-pro-preview")

    def test_tier_rates_above_threshold(self):
        from deepr.providers.registry import get_token_pricing

        base = get_token_pricing("gemini-3.1-pro-preview")
        tiered = get_token_pricing("gemini-3.1-pro-preview", input_tokens=300_000)
        assert tiered["input"] == round(base["input"] * 2.0, 6)
        assert tiered["output"] == round(base["output"] * 1.5, 6)

    def test_cached_input_pricing_uses_model_registry(self):
        assert get_cached_input_pricing("gpt-5") == pytest.approx(0.125)
        assert get_cached_input_pricing("grok-4.20-0309-reasoning") == pytest.approx(0.20)

    def test_settlement_uses_tier_rates(self):
        from deepr.providers.base import UsageStats

        small = UsageStats.calculate_cost(100_000, 10_000, "gemini-3.1-pro-preview")
        large = UsageStats.calculate_cost(300_000, 10_000, "gemini-3.1-pro-preview")
        # Large job must cost more than 3x the small one (3x tokens AND 2x rate)
        assert large > small * 3

    def test_settlement_uses_cached_input_rates(self):
        from deepr.providers.base import UsageStats

        cost = UsageStats.calculate_cost_with_cached_input(
            1000,
            500,
            "gpt-5",
            cached_input_tokens=400,
        )
        assert cost == pytest.approx(0.0058)

    def test_non_tiered_model_unaffected(self):
        from deepr.providers.registry import get_token_pricing

        assert get_token_pricing("claude-opus-4-8", input_tokens=500_000) == get_token_pricing("claude-opus-4-8")

    def test_unknown_model_fallback_warns(self, caplog):
        import logging

        from deepr.providers.registry import get_token_pricing

        with caplog.at_level(logging.WARNING, logger="deepr.providers.registry"):
            prices = get_token_pricing("totally-made-up-model-xyz")
        assert prices == {"input": 1.10, "output": 4.40}
        assert any("No registry pricing" in r.message for r in caplog.records)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
