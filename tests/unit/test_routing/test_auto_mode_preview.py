"""Tests for auto mode routing preview and deprecation integration."""

from deepr.routing.auto_mode import AutoModeDecision


class TestAutoModeDecisionPreview:
    def test_preview_text_format(self):
        decision = AutoModeDecision(
            provider="openai",
            model="gpt-5.4",
            complexity="complex",
            task_type="reasoning",
            cost_estimate=0.30,
            confidence=0.85,
            reasoning="Benchmark: reasoning -> openai/gpt-5.4",
        )
        preview = decision.preview_text()

        assert "openai" in preview
        assert "gpt-5.4" in preview
        assert "complex" in preview
        assert "$0.30" in preview
        assert "85%" in preview
        assert "reasoning" in preview.lower()

    def test_preview_text_low_cost(self):
        decision = AutoModeDecision(
            provider="xai",
            model="grok-4-1-fast-non-reasoning",
            complexity="simple",
            task_type="factual",
            cost_estimate=0.001,
            confidence=0.72,
            reasoning="Cheapest available",
        )
        preview = decision.preview_text()
        assert "xai" in preview
        assert "$0.0010" in preview

    def test_to_dict_includes_all_fields(self):
        decision = AutoModeDecision(
            provider="gemini",
            model="gemini-3.1-pro-preview",
            complexity="moderate",
            task_type="analysis",
            cost_estimate=0.20,
            confidence=0.78,
            reasoning="Overall best",
        )
        d = decision.to_dict()
        assert d["provider"] == "gemini"
        assert d["model"] == "gemini-3.1-pro-preview"
        assert d["cost_estimate"] == 0.20
        assert d["confidence"] == 0.78


class TestDeprecationInRouting:
    def test_deprecated_models_in_registry_have_flag(self):
        """Models marked in deprecation registry should have entries."""
        from deepr.routing.deprecation import DEPRECATION_REGISTRY

        # Verify the registry has the key deprecated models
        assert "gpt-4o" in DEPRECATION_REGISTRY
        assert "gpt-4o-mini" in DEPRECATION_REGISTRY
        assert "grok-3" in DEPRECATION_REGISTRY

    def test_current_models_not_deprecated(self):
        """Current frontier models should pass deprecation check cleanly."""
        from deepr.routing.deprecation import check_deprecation

        assert check_deprecation("gpt-5.4") is None
        assert check_deprecation("gpt-4.1") is None
        assert check_deprecation("grok-4.20-0309-reasoning") is None
        assert check_deprecation("gemini-3.1-pro-preview") is None
        assert check_deprecation("o4-mini-deep-research") is None
