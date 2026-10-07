"""Reviewed releases have exact price contracts without automatic promotion."""

import pytest

from deepr.providers.registry import (
    get_cached_input_pricing,
    get_cheapest_model,
    get_fastest_model,
    get_largest_context_model,
    get_model_capability,
    get_models_by_specialization,
    get_token_pricing,
)
from deepr.providers.registry_pricing import get_resolved_model_contract_identity
from deepr.providers.reviewed_catalog import REVIEWED_CAPABILITIES
from deepr.routing.auto_mode import _enrich_with_provisional


@pytest.mark.parametrize(
    "model,input_rate,cached_rate,output_rate",
    [
        ("gpt-6-astra", 10.0, 1.0, 50.0),
        ("gpt-6.1-sol", 2.0, 0.1, 10.0),
        ("gpt-6-luna", 0.1, 0.01, 0.5),
        ("claude-fable-5-1", 10.0, 0.25, 50.0),
        ("claude-opus-5-5", 4.0, 0.2, 20.0),
        ("claude-sonnet-5-5", 2.0, 0.2, 10.0),
        ("gemini-3.8-flash", 1.5, 0.15, 7.5),
        ("grok-4.7", 2.0, 0.5, 6.0),
    ],
)
def test_reviewed_releases_resolve_exact_prices(model, input_rate, cached_rate, output_rate):
    assert get_token_pricing(model) == {"input": input_rate, "output": output_rate}
    assert get_cached_input_pricing(model) == pytest.approx(cached_rate)
    identity = get_resolved_model_contract_identity(model)
    assert identity is not None
    assert "/".join(identity) in REVIEWED_CAPABILITIES


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna"])
def test_reviewed_openai_long_context_boundary(model):
    base = get_token_pricing(model)
    cached = get_cached_input_pricing(model)
    assert cached is not None
    assert get_token_pricing(model, input_tokens=272_000) == base
    assert get_cached_input_pricing(model, input_tokens=272_000) == cached
    assert get_token_pricing(model, input_tokens=272_001) == {
        "input": base["input"] * 2,
        "output": base["output"] * 1.5,
    }
    assert get_cached_input_pricing(model, input_tokens=272_001) == pytest.approx(cached * 2)


def test_reviewed_grok_uses_conservative_long_context_cap():
    assert get_token_pricing("grok-4.7", input_tokens=199_999) == {"input": 2.0, "output": 6.0}
    assert get_token_pricing("grok-4.7", input_tokens=200_000) == {"input": 4.0, "output": 12.0}
    assert get_cached_input_pricing("grok-4.7", input_tokens=200_000) == 1.0


def test_reviewed_releases_cannot_enter_automatic_rankings_or_selectors():
    candidates = set(REVIEWED_CAPABILITIES)
    rankings = _enrich_with_provisional(None)
    assert rankings is not None
    assert candidates.isdisjoint(f"{provider}/{model}" for rows in rankings.values() for provider, model, _, _ in rows)
    for selector in (get_cheapest_model, get_fastest_model, get_largest_context_model):
        selected = selector()
        assert f"{selected.provider}/{selected.model}" not in candidates
    assert all(not model.preview_only for model in get_models_by_specialization("reasoning"))
    assert all(model.preview_only for model in REVIEWED_CAPABILITIES.values())


def test_currency_review_preserves_workload_aliases():
    assert get_resolved_model_contract_identity("gpt-5.6") == ("openai", "gpt-5.6-sol")
    assert get_resolved_model_contract_identity("gemini-flash") == ("gemini", "gemini-3.6-flash")


def test_deprecated_sonnet_retains_historical_pricing_without_provisional_promotion():
    capability = get_model_capability("anthropic", "claude-sonnet-4-5")
    assert capability is not None
    assert capability.deprecated
    assert capability.successor == "anthropic/claude-sonnet-5-5"
    assert get_token_pricing(capability.model) == {"input": 3.0, "output": 15.0}
    rankings = _enrich_with_provisional(None)
    assert rankings is not None
    assert all(model != capability.model for rows in rankings.values() for _, model, _, _ in rows)


def test_deprecated_entries_cannot_win_direct_selectors(monkeypatch):
    from dataclasses import replace

    from deepr.providers.registry import MODEL_CAPABILITIES

    active = get_model_capability("openai", "gpt-5.6-sol")
    assert active is not None
    retired = replace(
        active, model="retired", deprecated=True, cost_per_query=0, latency_ms=1, context_window=2_000_000
    )
    monkeypatch.setitem(MODEL_CAPABILITIES, "openai/retired", retired)
    for selector in (get_cheapest_model, get_fastest_model, get_largest_context_model):
        assert not selector().deprecated
    assert all(not model.deprecated for model in get_models_by_specialization("reasoning"))
