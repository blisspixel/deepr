"""Paid endpoint and outbound model identity fail-closed contracts."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from anthropic import AsyncAnthropic
from azure.ai.projects import AIProjectClient
from google import genai
from openai import AsyncAzureOpenAI, AsyncOpenAI

from deepr.providers.base import ToolConfig
from deepr.providers.dispatch_authority import (
    PaidDispatchAuthorityError,
    _mint_attended_paid_client_attestation,
    default_paid_endpoint,
    paid_client_endpoint,
    require_bounded_paid_request_payload,
    require_exact_provider_model,
    require_no_unaccounted_paid_webhook,
    require_official_paid_client,
    require_official_paid_endpoint,
    require_unproxied_paid_transport,
)
from tests.unit.test_providers._provider_authority import submit_adapter


class _NoNetworkTokenCredential:
    def get_token(self, *_scopes: str, **_kwargs: object) -> object:
        raise AssertionError("SDK construction must not request a live token")

    def close(self) -> None:
        return None


@pytest.mark.parametrize(
    ("provider", "endpoint", "expected"),
    [
        ("openai", "https://api.openai.com/v1/", "https://api.openai.com/v1"),
        ("anthropic", "https://api.anthropic.com/", "https://api.anthropic.com"),
        ("xai", "https://api.x.ai/v1", "https://api.x.ai/v1"),
        ("gemini", "https://generativelanguage.googleapis.com/", "https://generativelanguage.googleapis.com"),
        ("azure", "https://research.openai.azure.com/", "https://research.openai.azure.com"),
        ("azure", "https://research.openai.azure.us/openai/v1/", "https://research.openai.azure.us"),
        (
            "azure-foundry",
            "https://research.services.ai.azure.com/api/projects/deepr/",
            "https://research.services.ai.azure.com/api/projects/deepr",
        ),
    ],
)
def test_official_paid_endpoints_are_normalized(provider: str, endpoint: str, expected: str) -> None:
    assert require_official_paid_endpoint(provider, endpoint) == expected


@pytest.mark.parametrize(
    ("provider", "endpoint"),
    [
        ("openai", "https://gateway.example/v1"),
        ("openai", "http://api.openai.com/v1"),
        ("anthropic", "https://api.anthropic.com/v1"),
        ("xai", "https://api.x.ai/v1?account=other"),
        ("gemini", "https://generativelanguage.googleapis.com:8443"),
        ("azure", "https://openai.azure.com"),
        ("azure", "https://research.openai.azure.com/other"),
        ("azure-foundry", "https://research.services.ai.azure.com/api/projects/a/other"),
    ],
)
def test_custom_or_ambiguous_paid_endpoints_fail_closed(provider: str, endpoint: str) -> None:
    with pytest.raises(PaidDispatchAuthorityError, match=r"official|priced"):
        require_official_paid_endpoint(provider, endpoint)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("OPENAI_BASE_URL", "https://gateway.example/v1"),
        ("ANTHROPIC_BASE_URL", "https://gateway.example"),
        ("GOOGLE_GEMINI_BASE_URL", "https://gateway.example"),
        ("AZURE_OPENAI_ENDPOINT", "https://gateway.example"),
        ("AZURE_PROJECT_ENDPOINT", "https://gateway.example/api/projects/p"),
        ("GOOGLE_GENAI_USE_VERTEXAI", "true"),
        ("GOOGLE_GENAI_USE_ENTERPRISE", "1"),
        ("GOOGLE_VERTEX_BASE_URL", "https://aiplatform.googleapis.com"),
        ("OPENAI_CUSTOM_HEADERS", "OpenAI-Project: other"),
        ("OPENAI_ORG_ID", "org-unbound"),
        ("OPENAI_PROJECT_ID", "proj-unbound"),
        ("ANTHROPIC_CUSTOM_HEADERS", "x-api-key: other"),
    ],
)
def test_ambient_endpoint_or_identity_overrides_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(PaidDispatchAuthorityError):
        require_unproxied_paid_transport()


def test_false_google_mode_switches_are_not_treated_as_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "false")
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "0")
    require_unproxied_paid_transport()


@pytest.mark.asyncio
async def test_recognized_sdk_endpoint_can_be_inspected_but_generic_paid_client_stays_frozen() -> None:
    transport = httpx.AsyncClient(trust_env=False, follow_redirects=False)
    client = AsyncOpenAI(
        api_key="test-key",
        base_url=default_paid_endpoint("openai"),
        max_retries=0,
        http_client=transport,
    )
    try:
        assert paid_client_endpoint(client, "openai") == default_paid_endpoint("openai")
        with pytest.raises(PaidDispatchAuthorityError, match="opaque Deepr-minted attestation"):
            require_official_paid_client(client, "openai")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_deepr_minted_attended_client_binds_wallet_model_and_transport() -> None:
    from deepr.core.spend_wallet import create_wallet, save_wallet
    from deepr.experts.research_reservation_store import ResearchReservationStore
    from deepr.observability.cost_ledger import current_cost_state_id

    save_wallet(
        create_wallet(
            amount_usd=50.0,
            cost_state_id=current_cost_state_id(),
            settled_cost_baseline_usd=ResearchReservationStore().exposure_snapshot().total_settled_cost,
        )
    )
    transport = httpx.AsyncClient(trust_env=False, follow_redirects=False)
    client = AsyncOpenAI(
        api_key="test-key",
        base_url=default_paid_endpoint("openai"),
        max_retries=0,
        http_client=transport,
    )
    try:
        assert _mint_attended_paid_client_attestation(client, "openai", "gpt-5-mini") == default_paid_endpoint("openai")
        attestation = vars(client)["_deepr_attended_paid_client_attestation"]
        assert attestation.credential_fingerprint != hashlib.sha256(b"test-key").hexdigest()
        assert "test-key" not in repr(attestation)
        assert require_official_paid_client(client, "openai", "gpt-5-mini") == default_paid_endpoint("openai")
        with pytest.raises(PaidDispatchAuthorityError, match="model changed"):
            require_official_paid_client(client, "openai", "gpt-5")
        client.api_key = "changed-key"
        with pytest.raises(PaidDispatchAuthorityError, match="credential changed"):
            require_official_paid_client(client, "openai", "gpt-5-mini")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_live_sdk_endpoint_inspection_covers_every_paid_provider_family() -> None:
    anthropic = AsyncAnthropic(
        api_key="test-key",
        base_url=default_paid_endpoint("anthropic"),
        max_retries=0,
        http_client=httpx.AsyncClient(trust_env=False, follow_redirects=False),
    )
    xai = AsyncOpenAI(
        api_key="test-key",
        base_url=default_paid_endpoint("xai"),
        max_retries=0,
        http_client=httpx.AsyncClient(trust_env=False, follow_redirects=False),
    )
    azure = AsyncAzureOpenAI(
        api_key="test-key",
        azure_endpoint="https://research.openai.azure.com",
        api_version="2024-10-21",
        max_retries=0,
        http_client=httpx.AsyncClient(trust_env=False, follow_redirects=False),
    )
    gemini = genai.Client(
        api_key="test-key",
        vertexai=False,
        http_options={
            "base_url": default_paid_endpoint("gemini"),
            "client_args": {"trust_env": False, "follow_redirects": False},
            "async_client_args": {"trust_env": False, "follow_redirects": False},
        },
    )
    foundry = AIProjectClient(
        endpoint="https://research.services.ai.azure.com/api/projects/deepr",
        credential=_NoNetworkTokenCredential(),
    )
    try:
        assert paid_client_endpoint(anthropic, "anthropic") == default_paid_endpoint("anthropic")
        assert paid_client_endpoint(xai, "xai") == default_paid_endpoint("xai")
        assert paid_client_endpoint(azure, "azure") == "https://research.openai.azure.com"
        assert paid_client_endpoint(gemini, "gemini") == default_paid_endpoint("gemini")
        assert paid_client_endpoint(foundry, "azure-foundry") == (
            "https://research.services.ai.azure.com/api/projects/deepr"
        )
    finally:
        await anthropic.close()
        await xai.close()
        await azure.close()
        gemini.close()
        foundry.close()


@pytest.mark.asyncio
async def test_custom_endpoints_on_recognized_sdk_clients_fail_closed() -> None:
    anthropic = AsyncAnthropic(api_key="test-key", base_url="https://gateway.example", max_retries=0)
    xai = AsyncOpenAI(api_key="test-key", base_url="https://gateway.example/v1", max_retries=0)
    azure = AsyncAzureOpenAI(
        api_key="test-key",
        azure_endpoint="https://gateway.example",
        api_version="2024-10-21",
        max_retries=0,
    )
    gemini = genai.Client(
        api_key="test-key",
        vertexai=False,
        http_options={"base_url": "https://gateway.example"},
    )
    foundry = AIProjectClient(
        endpoint="https://gateway.example/api/projects/deepr",
        credential=_NoNetworkTokenCredential(),
    )
    try:
        for client, provider in (
            (anthropic, "anthropic"),
            (xai, "xai"),
            (azure, "azure"),
            (gemini, "gemini"),
            (foundry, "azure-foundry"),
        ):
            with pytest.raises(PaidDispatchAuthorityError, match=r"official|priced"):
                paid_client_endpoint(client, provider)
    finally:
        await anthropic.close()
        await xai.close()
        await azure.close()
        gemini.close()
        foundry.close()


def test_forged_endpoint_attribute_is_not_a_supported_sdk_client() -> None:
    fake = SimpleNamespace(base_url=default_paid_endpoint("openai"))
    with pytest.raises(PaidDispatchAuthorityError, match="recognized provider SDK client"):
        paid_client_endpoint(fake, "openai")


def test_exact_outbound_model_identity_is_required() -> None:
    exact = SimpleNamespace(get_model_name=lambda model: model)
    mapped = SimpleNamespace(get_model_name=lambda _model: "more-expensive-model")

    assert require_exact_provider_model(exact, "reserved-model") == "reserved-model"
    with pytest.raises(PaidDispatchAuthorityError, match="does not share the priced contract"):
        require_exact_provider_model(mapped, "reserved-model")


def test_registered_alias_may_resolve_only_to_the_same_priced_contract() -> None:
    provider = SimpleNamespace(get_model_name=lambda _model: "grok-4.20-0309-reasoning")

    assert require_exact_provider_model(provider, "grok-4-20-reasoning") == "grok-4.20-0309-reasoning"


def test_paid_provider_webhook_is_rejected_without_separate_cost_authority() -> None:
    request = SimpleNamespace(webhook_url="https://callback.example/research-complete")
    with pytest.raises(PaidDispatchAuthorityError, match="callback compute"):
        require_no_unaccounted_paid_webhook(request)

    require_no_unaccounted_paid_webhook(SimpleNamespace(webhook_url=None))


@pytest.mark.parametrize(
    "research_request",
    [
        SimpleNamespace(previous_response_id="resp_existing", tools=[]),
        SimpleNamespace(
            previous_response_id=None,
            tools=[SimpleNamespace(type="code_interpreter", container={"type": "auto", "memory_limit": "1g"})],
        ),
        SimpleNamespace(
            previous_response_id=None,
            tools=[SimpleNamespace(type="code_interpreter", container={"type": "auto", "memory_limit": "64g"})],
        ),
    ],
)
def test_unbounded_context_and_code_interpreter_payloads_fail_closed(research_request: object) -> None:
    with pytest.raises(PaidDispatchAuthorityError, match=r"input-token ceiling|billable 20-minute sessions"):
        require_bounded_paid_request_payload(research_request)


def test_plain_bounded_paid_payload_is_allowed() -> None:
    require_bounded_paid_request_payload(
        SimpleNamespace(previous_response_id=None, tools=[SimpleNamespace(type="web_search_preview")])
    )


@pytest.mark.parametrize("provider", ["openai", "azure"])
def test_unpriced_openai_compatible_long_context_fails_closed(provider: str) -> None:
    research_request = SimpleNamespace(
        previous_response_id=None,
        tools=[],
        max_input_tokens=128_001,
    )
    with pytest.raises(PaidDispatchAuthorityError, match="above 128,000"):
        require_bounded_paid_request_payload(research_request, provider=provider)


@pytest.mark.parametrize("attribute", ["service_tier", "processing_tier", "sku"])
def test_unpriced_openai_account_tier_fails_closed(attribute: str) -> None:
    research_request = SimpleNamespace(
        previous_response_id=None,
        tools=[],
        max_input_tokens=128_000,
        **{attribute: "priority"},
    )
    with pytest.raises(PaidDispatchAuthorityError, match="account SKU"):
        require_bounded_paid_request_payload(research_request, provider="openai")


def test_provider_with_explicit_tiered_pricing_is_not_subject_to_openai_threshold() -> None:
    require_bounded_paid_request_payload(
        SimpleNamespace(previous_response_id=None, tools=[], max_input_tokens=200_001),
        provider="gemini",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("previous_response_id", "tools", "message"),
    [
        ("resp_existing", [], "input-token ceiling"),
        (None, [ToolConfig(type="code_interpreter", container={"memory_limit": "1g"})], "20-minute"),
    ],
)
async def test_unbounded_payload_never_reaches_provider_sdk(
    previous_response_id: str | None,
    tools: list[object],
    message: str,
) -> None:
    from deepr.providers.base import ResearchRequest
    from deepr.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider(api_key="test-key")
    create = AsyncMock()
    provider.client.responses.create = create
    request = ResearchRequest(
        prompt="question",
        system_message="system",
        model="o4-mini-deep-research",
        previous_response_id=previous_response_id,
        tools=tools,
    )
    try:
        with pytest.raises(PaidDispatchAuthorityError, match=message):
            await submit_adapter(provider, request)
        create.assert_not_awaited()
    finally:
        await provider.client.close()


@pytest.mark.asyncio
async def test_unbound_openai_billing_scope_never_reaches_provider_sdk() -> None:
    from deepr.providers.base import ResearchRequest
    from deepr.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider(api_key="test-key", organization="org-unbound")
    create = AsyncMock()
    provider.client.responses.create = create
    request = ResearchRequest(
        prompt="question",
        system_message="system",
        model="o4-mini-deep-research",
    )
    try:
        with pytest.raises(PaidDispatchAuthorityError, match="billing organization scope"):
            await submit_adapter(provider, request)
        create.assert_not_awaited()
    finally:
        await provider.client.close()


@pytest.mark.asyncio
async def test_unpriced_openai_long_context_never_reaches_provider_sdk() -> None:
    from deepr.providers.base import ResearchRequest
    from deepr.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider(api_key="test-key")
    create = AsyncMock()
    provider.client.responses.create = create
    request = ResearchRequest(
        prompt="question",
        system_message="system",
        model="o4-mini-deep-research",
        max_input_tokens=128_001,
    )
    try:
        with pytest.raises(PaidDispatchAuthorityError, match="above 128,000"):
            await submit_adapter(provider, request)
        create.assert_not_awaited()
    finally:
        await provider.client.close()


@pytest.mark.asyncio
async def test_anthropic_dispatch_uses_the_exact_reserved_request_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from deepr.providers import anthropic_provider as module
    from deepr.providers.base import ResearchRequest

    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="report")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    sdk_client = MagicMock()
    sdk_client.messages.create.return_value = response
    monkeypatch.setattr(module, "ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(module, "Anthropic", MagicMock(return_value=sdk_client), raising=False)
    monkeypatch.setattr(module.ToolRegistry, "create_executor", MagicMock(return_value=MagicMock()))
    provider = module.AnthropicProvider(api_key="test-key", model="claude-opus-4-8")
    request = ResearchRequest(
        prompt="question",
        system_message="system",
        model="claude-haiku-4-5",
        max_provider_requests=1,
    )

    await submit_adapter(provider, request)

    assert sdk_client.messages.create.call_args.kwargs["model"] == "claude-haiku-4-5"
    response_record = next(iter(provider._jobs.values()))
    assert response_record.model == "claude-haiku-4-5"
