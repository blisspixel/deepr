"""Regression tests for provider API key resolution.

load_config() deliberately redacts or omits provider credentials, but
get_api_key read only the config dict. Every non-OpenAI provider therefore
failed with "No API key found" even when the key was present in the
environment, and the failure surfaced downstream as a misleading
"authentication failed". The factory must honor config first (explicit
injection), then fall back to the environment, and treat the "***" redaction
placeholder as absent.
"""

import pytest

from deepr.cli.commands.provider_factory import get_api_key


def test_env_fallback_when_config_omits_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-env-key")
    # load_config() output carries no xai_api_key at all - the bug scenario.
    assert get_api_key("xai", {}) == "xai-env-key"


def test_explicit_config_key_takes_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-env-key")
    assert get_api_key("xai", {"xai_api_key": "xai-injected"}) == "xai-injected"


def test_redaction_placeholder_is_not_a_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
    # load_config() emits api_key="***"; that must never be sent to a provider.
    assert get_api_key("openai", {"api_key": "***"}) == "sk-env-key"


def test_grok_alias_resolves_the_xai_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-env-key")
    assert get_api_key("grok", {}) == "xai-env-key"


def test_missing_everywhere_raises_with_env_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        get_api_key("gemini", {})
