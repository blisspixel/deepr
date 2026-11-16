"""Prior-user access is distinct from shutdown and does not widen dispatch."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from deepr.providers.base import ResearchRequest
from deepr.providers.registry import MODEL_CAPABILITIES, get_models_by_specialization
from deepr.providers.registry_pricing import get_resolved_model_capability, get_token_pricing
from deepr.routing.deprecation import check_deprecation, is_shutdown, migrate_model, model_submission_error
from deepr.services.research_bounds import ResearchRequestBoundsError, bounded_research_cost_estimate


@pytest.mark.parametrize(
    ("model", "deprecated", "route"),
    [
        ("gemini-2.5-pro", True, "gemini-3.8-flash"),
        ("gemini-2.5-flash", True, "gemini-3.5-flash-lite"),
        ("gemini-2.5-flash-lite", False, None),
    ],
)
def test_explicit_identity_and_historical_pricing_survive_access_restriction(model, deprecated, route):
    cap = get_resolved_model_capability(model)
    assert cap is MODEL_CAPABILITIES[f"gemini/{model}"]
    assert cap.model == model
    assert cap.deprecated is deprecated
    assert cap.access_state == "legacy_access_only"
    assert "2026-11-16" in cap.access_note
    assert "https://ai.google.dev/gemini-api/docs/deprecations" in cap.access_note
    assert ("2026-12-01" in cap.access_note) is deprecated
    if route is None:
        assert "no announced shutdown" in cap.access_note
        assert check_deprecation(model) is None
    else:
        assert route in cap.access_note
        assert "no announced shutdown" not in cap.access_note
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
    if route is not None:
        assert "2026-12-01" in str(caught.value)
        assert route in str(caught.value)
    preview = bounded_research_cost_estimate(request=request, provider="gemini", allow_preview_only=True)
    assert preview.max_cost > 0
    assert request.model == model


def test_gemini_contract_refuses_unverified_access_before_any_client_call():
    from deepr.providers.base import ProviderError
    from deepr.providers.gemini_provider import GeminiProvider

    provider = GeminiProvider.__new__(GeminiProvider)
    provider._model_contracts = {"gemini-2.5-flash": MODEL_CAPABILITIES["gemini/gemini-2.5-flash"]}
    provider.client = MagicMock()
    with pytest.raises(ProviderError, match="prior users only") as refused:
        provider._require_model_contract("gemini-2.5-flash")
    assert "2026-12-01" in str(refused.value)
    assert "gemini-3.5-flash-lite" in str(refused.value)
    assert not provider.client.mock_calls


@pytest.mark.parametrize(
    ("model", "route", "recommendation"),
    [
        ("gemini-2.5-pro", "gemini-3.8-flash", "gemini-4-carbon"),
        ("gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash"),
    ],
)
def test_gemini_25_shutdown_is_named_and_not_silently_migrated(model, route, recommendation):
    entry = check_deprecation(model)
    assert entry is not None
    assert entry.new_model == route
    assert entry.sunset_date == "2026-12-01"
    assert entry.auto_migrate is False
    assert entry.match_prefix is False
    resolved, confidence, note = migrate_model(model, 0.7)
    assert resolved == model
    assert confidence == 0.7
    assert note is not None
    assert "2026-12-01" in note
    assert route in note
    assert recommendation in note
    assert not is_shutdown(model, today=date(2026, 11, 16))
    assert is_shutdown(model, today=date(2026, 12, 1))
    allowed = ["gpt-6.1-sol", model]
    assert model_submission_error(model, allowed, today=date(2026, 11, 16)) is None
    refused = model_submission_error(model, allowed, today=date(2026, 12, 1))
    assert refused is not None
    assert refused["error_code"] == "model_shut_down"
    assert model in refused["error"]


def test_gemini_25_flash_shutdown_does_not_capture_flash_lite():
    assert check_deprecation("gemini-2.5-flash-lite") is None
    assert not is_shutdown("gemini-2.5-flash-lite", today=date(2026, 12, 1))
    assert not is_shutdown("gemini-2.5-flash-preview-09-2025", today=date(2026, 12, 1))


@pytest.mark.parametrize("model", ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-mini-2025-08-07"])
def test_snapshot_notice_does_not_migrate_explicit_selection(model):
    resolved, confidence, note = migrate_model(model, 0.7)
    assert resolved == model
    assert confidence == 0.7
    assert "2026-12-11" in note
