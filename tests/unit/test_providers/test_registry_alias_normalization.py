"""Tests for the Grok dot/hyphen alias normalization in registry pricing.

Regression: ``get_token_pricing`` previously did substring match with
no normalization, so the Grok provider's reported model
``grok-4.20-multi-agent-0309`` fell through to the o4-mini default
(~80% undercharge).
"""

from __future__ import annotations

import pytest

from deepr.providers.registry import get_cost_estimate, get_token_pricing


class TestGrokAliasNormalization:
    @pytest.mark.parametrize(
        "model",
        [
            "grok-4-20-multi-agent",  # registry form
            "grok-4.20-multi-agent",  # provider-reported dotted form
            "grok-4.20-multi-agent-0309",  # full provider model id
        ],
    )
    def test_multi_agent_pricing_matches_registry(self, model):
        prices = get_token_pricing(model)
        # All three should hit the multi-agent entry, NOT fall through
        # to the o4-mini default ($1.10 input / $4.40 output).
        assert prices["input"] == 2.0
        assert prices["output"] == 6.0

    def test_reasoning_variant_dotted_form_matches(self):
        prices = get_token_pricing("grok-4.20-reasoning")
        assert prices["input"] == 2.0
        assert prices["output"] == 6.0


class TestAliasResolution:
    def test_gemini_deep_research_alias(self):
        # Caller-facing alias should resolve to the real deep-research
        # provider model's cost estimate, not the 0.20 default.
        est = get_cost_estimate("gemini-deep-research")
        # Deep-research-pro-preview should be substantially more than $0.20
        assert est > 1.0

    def test_unknown_model_returns_default(self):
        prices = get_token_pricing("totally-fake-model-xyz")
        # Falls back to o4-mini default rates
        assert prices["input"] == pytest.approx(1.10)
        assert prices["output"] == pytest.approx(4.40)


class TestPartialMatchOrdering:
    def test_flash_lite_does_not_match_flash(self):
        """``gemini-2.5-flash-lite`` should match its own entry, not the
        shorter ``gemini-2.5-flash`` prefix (which previously caused a
        ~3x overcharge on Flash-Lite requests)."""
        lite_prices = get_token_pricing("gemini-2.5-flash-lite")
        flash_prices = get_token_pricing("gemini-2.5-flash")
        # The two should be distinct — Flash-Lite is cheaper.
        assert lite_prices["input"] <= flash_prices["input"]
