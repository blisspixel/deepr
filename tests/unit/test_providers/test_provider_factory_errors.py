"""Tests for provider factory optional import error reporting."""

import pytest

import deepr.providers as providers


def test_create_provider_includes_optional_import_root_cause(monkeypatch):
    monkeypatch.setattr(providers, "GeminiProvider", None)
    monkeypatch.setitem(providers._OPTIONAL_PROVIDER_IMPORT_ERRORS, "gemini", RuntimeError("sdk mismatch"))

    with pytest.raises(ImportError) as excinfo:
        providers.create_provider("gemini")

    message = str(excinfo.value)
    assert "Gemini provider requires" in message
    assert "Root cause: sdk mismatch" in message


def test_create_provider_supports_anthropic(monkeypatch):
    calls = {}

    class FakeAnthropicProvider:
        def __init__(self, **kwargs):
            calls["kwargs"] = kwargs

    monkeypatch.setattr(providers, "AnthropicProvider", FakeAnthropicProvider)

    provider = providers.create_provider("anthropic", api_key="***", model="claude-sonnet-5")

    assert isinstance(provider, FakeAnthropicProvider)
    assert calls["kwargs"] == {"api_key": None, "model": "claude-sonnet-5"}
