"""No-network contracts for bounded paid research requests."""

from __future__ import annotations

import pytest

from deepr.providers.base import ResearchRequest, ToolConfig, UsageStats
from deepr.services.research_bounds import (
    ResearchRequestBoundsError,
    bounded_research_cost_estimate,
    request_bound_metadata,
    validate_persisted_request_bounds,
    validate_provider_payload_bytes,
    validate_research_request_bounds,
)


@pytest.fixture(autouse=True)
def _no_provider_keys(monkeypatch) -> None:
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_openai_envelope_includes_exact_token_and_web_ceilings() -> None:
    request = ResearchRequest(
        prompt="Research",
        model="o4-mini-deep-research",
        system_message="Test",
        tools=[
            ToolConfig(type="web_search_preview"),
        ],
        max_input_tokens=128_000,
        max_output_tokens=16_000,
        max_tool_calls=10,
        max_provider_requests=1,
    )

    estimate = bounded_research_cost_estimate(request=request, provider="openai")

    # $1/$4 per MTok + $0.025 per web call.
    assert estimate.max_cost == pytest.approx(0.442)
    assert estimate.expected_cost == estimate.max_cost


def test_code_interpreter_fails_closed_without_memory_and_session_envelope() -> None:
    request = ResearchRequest(
        prompt="Research",
        model="o4-mini-deep-research",
        system_message="Test",
        tools=[ToolConfig(type="code_interpreter", container={"type": "auto", "memory_limit": "4g"})],
        max_input_tokens=128_000,
        max_output_tokens=16_000,
        max_tool_calls=10,
        max_provider_requests=1,
    )

    with pytest.raises(ResearchRequestBoundsError) as raised:
        bounded_research_cost_estimate(request=request, provider="openai")

    assert raised.value.code == "research_code_interpreter_cost_unbounded"


def test_multiple_provider_requests_multiply_model_and_tool_ceiling() -> None:
    request = ResearchRequest(
        prompt="Research",
        model="o3-deep-research",
        system_message="Test",
        tools=[ToolConfig(type="web_search_preview")],
        max_input_tokens=128_000,
        max_output_tokens=16_000,
        max_tool_calls=16,
        max_provider_requests=2,
    )

    estimate = bounded_research_cost_estimate(request=request, provider="OpenAIProvider")

    # Each request: $0.64 input + $0.32 output + $0.40 maximum web calls.
    assert estimate.max_cost == pytest.approx(2.72)


def test_serialized_request_and_exact_provider_payload_have_hard_byte_limits() -> None:
    request = ResearchRequest(
        prompt="x" * 300,
        model="o4-mini-deep-research",
        system_message="Test",
        max_request_bytes=512,
    )
    with pytest.raises(ResearchRequestBoundsError) as raised:
        validate_research_request_bounds(request)
    assert raised.value.code == "research_request_bytes_exceeded"

    with pytest.raises(ResearchRequestBoundsError) as provider_raised:
        validate_provider_payload_bytes({"input": "x" * 600}, 512)
    assert provider_raised.value.code == "research_provider_payload_bytes_exceeded"


def test_invalid_boolean_bound_is_rejected() -> None:
    request = ResearchRequest(
        prompt="Research",
        model="o4-mini-deep-research",
        system_message="Test",
        max_provider_requests=True,  # type: ignore[arg-type]
    )
    with pytest.raises(ResearchRequestBoundsError) as raised:
        validate_research_request_bounds(request)
    assert raised.value.code == "invalid_research_request_bound"


def test_file_search_fails_before_spend_until_storage_is_bounded() -> None:
    request = ResearchRequest(
        prompt="Research",
        model="o4-mini-deep-research",
        system_message="Test",
        tools=[ToolConfig(type="file_search", vector_store_ids=["vs-1"])],
    )
    with pytest.raises(ResearchRequestBoundsError) as raised:
        bounded_research_cost_estimate(request=request, provider="openai")
    assert raised.value.code == "research_file_storage_unbounded"


def test_gemini_deep_research_explains_missing_provider_budget_control() -> None:
    request = ResearchRequest(
        prompt="Research",
        model="deep-research-pro-preview-12-2025",
        system_message="Test",
    )
    with pytest.raises(ResearchRequestBoundsError) as raised:
        bounded_research_cost_estimate(request=request, provider="gemini")
    assert raised.value.code == "gemini_deep_research_budget_unbounded"
    assert "autonomous tool loop" in str(raised.value)


@pytest.mark.parametrize(
    ("model", "expected_maximum"),
    [
        ("gemini-flash", 0.019788),
        ("gemini-flash-lite", 0.0049576),
    ],
)
def test_current_gemini_aliases_have_exact_bounded_pricing(model: str, expected_maximum: float) -> None:
    request = ResearchRequest(
        prompt="Research",
        model=model,
        system_message="Test",
        max_input_tokens=8_192,
        max_output_tokens=1_000,
        max_provider_requests=1,
    )

    estimate = bounded_research_cost_estimate(request=request, provider="gemini")

    assert estimate.max_cost == pytest.approx(expected_maximum)


@pytest.mark.parametrize("model", ["gemini-flash", "gemini-flash-lite"])
def test_current_gemini_aliases_enforce_provider_output_limit(model: str) -> None:
    request = ResearchRequest(
        prompt="Research",
        model=model,
        system_message="Test",
        max_input_tokens=8_192,
        max_output_tokens=65_537,
        max_provider_requests=1,
    )

    with pytest.raises(ResearchRequestBoundsError) as raised:
        bounded_research_cost_estimate(request=request, provider="gemini")

    assert raised.value.code == "research_output_bound_unsupported"
    assert "65,536" in str(raised.value)


@pytest.mark.parametrize(
    ("model", "provider", "max_input_tokens", "expected_maximum"),
    [
        ("gemini-2.5-pro", "gemini", 200_000, 0.7),
        ("gemini-2.5-pro", "gemini", 200_001, 1.300005),
        ("gemini-3.1-pro-preview", "gemini", 200_000, 1.04),
        ("gemini-3.1-pro-preview", "gemini", 200_001, 1.960008),
        ("gpt-5.6", "openai", 272_000, 3.32),
        ("gpt-5.6", "openai", 272_001, 6.34002),
        ("grok-4.6", "xai", 199_999, 0.919996),
        ("grok-4.6", "xai", 200_000, 1.84),
        ("grok-4.6", "xai", 200_001, 1.840008),
        ("grok-4.5", "xai", 199_999, 0.919996),
        ("grok-4.5", "xai", 200_000, 1.84),
        ("grok-4.5", "xai", 200_001, 1.840008),
        ("grok-4.3", "xai", 199_999, 0.5499975),
        ("grok-4.3", "xai", 200_000, 1.1),
        ("grok-4.3", "xai", 200_001, 1.100005),
        ("grok-build-0.1", "xai", 199_999, 0.439998),
        ("grok-build-0.1", "xai", 200_000, 0.88),
        ("grok-build-0.1", "xai", 200_001, 0.880004),
        ("grok-4.20-0309-reasoning", "xai", 199_999, 0.5499975),
        ("grok-4.20-0309-reasoning", "xai", 200_000, 1.1),
        ("grok-4.20-0309-reasoning", "xai", 200_001, 1.100005),
        ("grok-4.20-0309-non-reasoning", "xai", 199_999, 0.5499975),
        ("grok-4.20-0309-non-reasoning", "xai", 200_000, 1.1),
        ("grok-4.20-0309-non-reasoning", "xai", 200_001, 1.100005),
    ],
)
def test_tiered_research_reservation_covers_maximum_settlement(
    model: str,
    provider: str,
    max_input_tokens: int,
    expected_maximum: float,
) -> None:
    max_output_tokens = 10_000
    max_provider_requests = 2
    request = ResearchRequest(
        prompt="Research",
        model=model,
        system_message="Test",
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_output_tokens,
        max_provider_requests=max_provider_requests,
    )

    estimate = bounded_research_cost_estimate(request=request, provider=provider)
    maximum_settlement = (
        UsageStats.calculate_cost_with_cached_input(
            max_input_tokens,
            max_output_tokens,
            model,
            cached_input_tokens=0,
        )
        * max_provider_requests
    )

    assert maximum_settlement == pytest.approx(expected_maximum)
    assert estimate.max_cost >= maximum_settlement


def test_grok_multi_agent_boundary_remains_blocked_without_parent_reservation() -> None:
    request = ResearchRequest(
        prompt="Research",
        model="grok-4.20-multi-agent-0309",
        system_message="Test",
        max_input_tokens=200_000,
        max_output_tokens=10_000,
        max_provider_requests=2,
    )

    with pytest.raises(ResearchRequestBoundsError) as raised:
        bounded_research_cost_estimate(request=request, provider="xai")

    assert raised.value.code == "xai_multi_agent_research_budget_unbounded"


def test_provider_model_mismatch_fails_before_cost_admission() -> None:
    request = ResearchRequest(
        prompt="Research",
        model="gemini-3.6-flash",
        system_message="Test",
        max_input_tokens=8_192,
        max_output_tokens=1_000,
        max_provider_requests=1,
    )

    with pytest.raises(ResearchRequestBoundsError) as raised:
        bounded_research_cost_estimate(request=request, provider="xai")

    assert raised.value.code == "research_provider_model_mismatch"
    assert "gemini" in str(raised.value)
    assert "xai" in str(raised.value)


def test_azure_accepts_openai_model_contracts() -> None:
    request = ResearchRequest(
        prompt="Research",
        model="o4-mini-deep-research",
        system_message="Test",
        tools=[],
        max_input_tokens=8_192,
        max_output_tokens=1_000,
        max_provider_requests=1,
    )

    estimate = bounded_research_cost_estimate(request=request, provider="azure")

    assert estimate.max_cost > 0


@pytest.mark.parametrize("model", ["gemini-3-pro-preview", "gemini-3.1-flash-lite-preview"])
def test_deprecated_gemini_model_fails_before_cost_admission(model: str) -> None:
    request = ResearchRequest(
        prompt="Research",
        model=model,
        system_message="Test",
        max_input_tokens=8_192,
        max_output_tokens=1_000,
        max_provider_requests=1,
    )

    with pytest.raises(ResearchRequestBoundsError) as raised:
        bounded_research_cost_estimate(request=request, provider="gemini")

    assert raised.value.code == "research_model_deprecated"
    assert "successor" in str(raised.value)


def test_persisted_request_bounds_must_match_exactly() -> None:
    request = ResearchRequest(
        prompt="Research",
        model="o4-mini-deep-research",
        system_message="Test",
    )
    metadata = request_bound_metadata(request)
    validate_persisted_request_bounds(metadata, request)

    metadata["research_max_output_tokens"] += 1
    with pytest.raises(ResearchRequestBoundsError) as raised:
        validate_persisted_request_bounds(metadata, request)
    assert raised.value.code == "research_request_bounds_mismatch"
