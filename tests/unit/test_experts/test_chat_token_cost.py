"""Tests for the ``_chat_token_cost`` helper.

Covers:
- Registry-driven pricing (no more hard-coded GPT-5 rates).
- Cached-token discount (50% on cached prompt tokens).
- Graceful degradation when ``usage`` is missing or partial.
- Default fallback when the registry doesn't recognise the model.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.chat import _chat_token_cost


class TestChatTokenCost:
    def test_returns_zero_for_missing_usage(self):
        assert _chat_token_cost(None, "gpt-5.2") == 0.0
        assert _chat_token_cost(False, "gpt-5.2") == 0.0

    def test_basic_billing_uses_registry_pricing(self):
        """gpt-5.2 should bill at the registry rate, not the legacy
        GPT-5 hard-coded rate."""
        usage = SimpleNamespace(
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            prompt_tokens_details=None,
        )
        cost = _chat_token_cost(usage, "gpt-5.2")
        # gpt-5.2: $1.75 input + $14 output per 1M = $15.75 total
        assert cost == pytest.approx(15.75, rel=0.05)

    def test_cached_tokens_discount(self):
        """Cached prompt tokens should be billed at 50% of the input rate."""
        # All 1M prompt tokens cached. Output zero. At gpt-5.2 input rate ($1.75/MTok)
        # half rate -> $0.875.
        usage = SimpleNamespace(
            prompt_tokens=1_000_000,
            completion_tokens=0,
            prompt_tokens_details=SimpleNamespace(cached_tokens=1_000_000),
        )
        cost = _chat_token_cost(usage, "gpt-5.2")
        assert cost == pytest.approx(0.875, rel=0.05)

    def test_mixed_cached_uncached(self):
        """Half cached, half uncached prompt tokens."""
        usage = SimpleNamespace(
            prompt_tokens=2_000_000,
            completion_tokens=0,
            prompt_tokens_details=SimpleNamespace(cached_tokens=1_000_000),
        )
        cost = _chat_token_cost(usage, "gpt-5.2")
        # 1M uncached @ $1.75 + 1M cached @ $0.875 = $2.625
        assert cost == pytest.approx(2.625, rel=0.05)

    def test_missing_cached_tokens_attribute(self):
        """Old usage objects without prompt_tokens_details should still work
        (no cache discount, but no crash)."""
        usage = SimpleNamespace(
            prompt_tokens=1_000_000,
            completion_tokens=0,
        )
        cost = _chat_token_cost(usage, "gpt-5.2")
        assert cost == pytest.approx(1.75, rel=0.05)

    def test_falls_back_for_unknown_model(self):
        """Unknown model should fall back to default rates without raising."""
        usage = SimpleNamespace(
            prompt_tokens=1_000,
            completion_tokens=1_000,
            prompt_tokens_details=None,
        )
        cost = _chat_token_cost(usage, "model-that-does-not-exist")
        # Should return a non-negative number, not raise.
        assert cost >= 0.0

    def test_anthropic_usage_falls_back_to_conservative_pricing(self, monkeypatch):
        """Anthropic usage must not settle as zero when pricing lookup fails."""

        def fail_pricing_lookup(*args, **kwargs):
            raise RuntimeError("registry unavailable")

        monkeypatch.setattr("deepr.providers.registry.get_token_pricing", fail_pricing_lookup)
        usage = SimpleNamespace(
            input_tokens=1_000,
            output_tokens=100,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=300,
        )

        cost = _chat_token_cost(usage, "claude-sonnet-4-6")

        expected = (
            1_000 / 1_000_000 * 1.25 + 100 / 1_000_000 * 10.00 + 200 / 1_000_000 * 1.5625 + 300 / 1_000_000 * 0.125
        )
        assert cost == pytest.approx(expected)
