"""Tests for the Grok dot/hyphen alias normalization in registry pricing.

Regression: ``get_token_pricing`` previously did substring match with
no normalization, so the Grok provider's reported model
``grok-4.20-multi-agent-0309`` fell through to the o4-mini default
instead of the Grok registry entry.
"""

from __future__ import annotations

import pytest

from deepr.providers.registry import (
    get_cached_input_pricing,
    get_cost_estimate,
    get_token_pricing,
)
from deepr.providers.registry_pricing import (
    get_resolved_model_capability,
    get_resolved_model_contract_identity,
    provider_matches_model_contract,
)


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
        assert prices["input"] == 1.25
        assert prices["output"] == 2.5

    def test_reasoning_variant_dotted_form_matches(self):
        prices = get_token_pricing("grok-4.20-reasoning")
        assert prices["input"] == 1.25
        assert prices["output"] == 2.5
        assert get_cached_input_pricing("grok-4.20-reasoning") == pytest.approx(0.20)


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

    @pytest.mark.parametrize(
        ("alias", "model", "input_rate", "output_rate", "cached_rate"),
        [
            ("gemini-flash", "gemini-3.6-flash", 1.50, 7.50, 0.15),
            ("gemini-flash-lite", "gemini-3.5-flash-lite", 0.30, 2.50, 0.03),
        ],
    )
    def test_current_gemini_aliases_share_canonical_pricing(
        self,
        alias,
        model,
        input_rate,
        output_rate,
        cached_rate,
    ):
        capability = get_resolved_model_capability(alias)
        assert capability is not None
        assert capability.model == model
        assert get_token_pricing(alias) == {"input": input_rate, "output": output_rate}
        assert get_cached_input_pricing(alias) == pytest.approx(cached_rate)

    @pytest.mark.parametrize(
        ("alias", "model", "input_rate", "output_rate", "cached_rate"),
        [
            ("gpt-5.6", "gpt-5.6-sol", 5.00, 30.00, 0.50),
            ("grok-code-fast-1", "grok-build-0.1", 1.00, 2.00, 0.20),
            ("grok-code-fast-1-0825", "grok-build-0.1", 1.00, 2.00, 0.20),
        ],
    )
    def test_current_openai_and_xai_aliases_share_canonical_pricing(
        self,
        alias,
        model,
        input_rate,
        output_rate,
        cached_rate,
    ):
        capability = get_resolved_model_capability(alias)
        assert capability is not None
        assert capability.model == model
        assert get_token_pricing(alias) == {"input": input_rate, "output": output_rate}
        assert get_cached_input_pricing(alias) == pytest.approx(cached_rate)

    def test_contract_identity_resolves_chat_alias_to_registry_owner(self):
        assert get_resolved_model_contract_identity("gemini-flash") == ("gemini", "gemini-3.6-flash")

    def test_contract_identity_includes_specialized_input_only_model(self):
        assert get_resolved_model_contract_identity("text-embedding-3-small") == (
            "openai",
            "text-embedding-3-small",
        )

    def test_provider_matcher_keeps_azure_foundry_separate(self):
        assert provider_matches_model_contract("azure", "openai") is True
        assert provider_matches_model_contract("azure-foundry", "openai") is False


class TestPartialMatchOrdering:
    def test_flash_lite_does_not_match_flash(self):
        """``gemini-2.5-flash-lite`` should match its own entry, not the
        shorter ``gemini-2.5-flash`` prefix (which previously caused a
        ~3x overcharge on Flash-Lite requests)."""
        lite_prices = get_token_pricing("gemini-2.5-flash-lite")
        flash_prices = get_token_pricing("gemini-2.5-flash")
        # The two should be distinct: Flash-Lite is cheaper.
        assert lite_prices["input"] <= flash_prices["input"]
