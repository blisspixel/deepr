"""No-proxy transport regressions for external provider clients."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from deepr.providers.dispatch_authority import PaidDispatchAuthorityError


@pytest.mark.asyncio
async def test_openai_client_ignores_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from deepr.providers.openai_provider import OpenAIProvider

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    provider = OpenAIProvider(api_key="test-key")
    try:
        transport = provider.client._client
        assert transport.trust_env is False
        assert transport.follow_redirects is False
    finally:
        await provider.client.close()


@pytest.mark.asyncio
async def test_grok_client_ignores_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from deepr.providers.grok_provider import GrokProvider

    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:8080")
    provider = GrokProvider(api_key="test-key")
    try:
        transport = provider.client._client
        assert transport.trust_env is False
        assert transport.follow_redirects is False
    finally:
        await provider.client.close()


def test_anthropic_client_ignores_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from deepr.providers import anthropic_provider as module

    captured: dict[str, object] = {}

    def fake_anthropic(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setattr(module, "ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(module, "Anthropic", fake_anthropic, raising=False)
    monkeypatch.setattr(module.ToolRegistry, "create_executor", MagicMock(return_value=MagicMock()))

    module.AnthropicProvider(api_key="test-key")

    transport = captured["http_client"]
    try:
        assert transport.trust_env is False
        assert transport.follow_redirects is False
    finally:
        transport.close()


@pytest.mark.asyncio
async def test_azure_openai_client_ignores_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("azure.identity.aio")
    from deepr.providers.azure_provider import AzureProvider

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    provider = AzureProvider(api_key="test-key", endpoint="https://example.openai.azure.com/")
    try:
        transport = provider.client._client
        assert transport.trust_env is False
        assert transport.follow_redirects is False
    finally:
        await provider.client.close()


def test_foundry_rejects_proxy_before_reusing_external_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from deepr.providers.azure_foundry_provider import AzureFoundryProvider

    provider = AzureFoundryProvider(project_endpoint="https://example.services.ai.azure.com/api/projects/test")
    project_client = MagicMock()
    agents_client = MagicMock()
    provider._project_client = project_client
    provider._agents_client = agents_client
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")

    with pytest.raises(PaidDispatchAuthorityError, match="refuses unaccounted proxy"):
        provider._get_project_client()
    with pytest.raises(PaidDispatchAuthorityError, match="refuses unaccounted proxy"):
        provider._get_agents_client()
