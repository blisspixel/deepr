"""Prior-user access is distinct from shutdown and does not widen dispatch."""

from unittest.mock import MagicMock

import pytest

from deepr.providers.base import ResearchRequest
from deepr.providers.registry import MODEL_CAPABILITIES, get_models_by_specialization
from deepr.providers.registry_pricing import get_resolved_model_capability, get_token_pricing
from deepr.routing.deprecation import migrate_model
from deepr.services.research_bounds import ResearchRequestBoundsError, bounded_research_cost_estimate


@pytest.mark.parametrize("model", ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"])
def test_explicit_identity_and_historical_pricing_survive_access_restriction(model):
    cap = get_resolved_model_capability(model)
    assert cap is MODEL_CAPABILITIES[f"gemini/{model}"]
    assert cap.model == model
    assert not cap.deprecated
    assert cap.access_state == "legacy_access_only"
    assert "2026-10-18" in cap.access_note
    assert "https://ai.google.dev/gemini-api/docs/deprecations" in cap.access_note
    assert get_token_pricing(model)["input"] > 0
    for specialization in cap.specializations:
        assert cap not in get_models_by_specialization(specialization)
    request = ResearchRequest(
        prompt="test",
        system_message="test",
        model=model,
        max_input_tokens=8192,
        max_output_tokens=1024,
        max_tool_calls=1,
        max_provider_requests=1,
    )
    with pytest.raises(ResearchRequestBoundsError, match="prior users only") as caught:
        bounded_research_cost_estimate(request=request, provider="gemini")
    assert caught.value.code == "research_model_access_unverified"
    preview = bounded_research_cost_estimate(request=request, provider="gemini", allow_preview_only=True)
    assert preview.max_cost > 0
    assert request.model == model


def test_gemini_contract_refuses_unverified_access_before_any_client_call():
    from deepr.providers.base import ProviderError
    from deepr.providers.gemini_provider import GeminiProvider

    provider = GeminiProvider.__new__(GeminiProvider)
    provider._model_contracts = {"gemini-2.5-flash": MODEL_CAPABILITIES["gemini/gemini-2.5-flash"]}
    provider.client = MagicMock()
    with pytest.raises(ProviderError, match="prior users only"):
        provider._require_model_contract("gemini-2.5-flash")
    assert not provider.client.mock_calls


@pytest.mark.parametrize("model", ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-mini-2025-08-07"])
def test_snapshot_notice_does_not_migrate_explicit_selection(model):
    resolved, confidence, note = migrate_model(model, 0.7)
    assert resolved == model
    assert confidence == 0.7
    assert "2026-12-11" in note
