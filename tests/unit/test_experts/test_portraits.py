"""Tests for expert portrait prompt building and the consistent style preference.

Pure prompt/style logic only - no image provider is called (those paths need a
key and cost money, so they stay out of the unit suite).
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.experts import portraits as P
from deepr.experts.portraits import (
    DEFAULT_PORTRAIT_STYLE,
    PORTRAIT_COST_ESTIMATE_USD,
    PORTRAIT_STYLE_ENV,
    _build_prompt,
    detect_provider,
    portrait_cost,
    portrait_style,
)


class TestLocalImageProvider:
    def test_detect_prefers_local_when_url_set(self, monkeypatch):
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", "http://localhost:8188")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")  # local still wins (cheapest-first)
        assert detect_provider() == "local"

    def test_detect_falls_back_to_metered_without_local(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_IMAGE_URL", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert detect_provider() == "openai"

    def test_local_is_free_metered_is_not(self):
        assert portrait_cost("local") == 0.0
        assert portrait_cost("openai") == PORTRAIT_COST_ESTIMATE_USD
        assert portrait_cost(None) == PORTRAIT_COST_ESTIMATE_USD

    @pytest.mark.asyncio
    async def test_generate_local_hits_configured_endpoint(self, monkeypatch):
        monkeypatch.setenv("DEEPR_LOCAL_IMAGE_URL", "http://localhost:8188")
        captured: dict = {}
        fake_result = MagicMock()
        fake_result.data = [MagicMock(b64_json=base64.b64encode(b"IMGBYTES").decode())]
        fake_client = MagicMock()
        fake_client.images.generate = AsyncMock(return_value=fake_result)

        def fake_ctor(*_a, **kwargs):
            captured.update(kwargs)
            return fake_client

        with patch("openai.AsyncOpenAI", fake_ctor):
            out = await P._generate_local("a prompt")

        assert out == b"IMGBYTES"
        assert captured["base_url"].endswith("/v1")  # /v1 appended if missing
        assert captured["api_key"] == "local"  # nothing billed

    @pytest.mark.asyncio
    async def test_generate_local_requires_url(self, monkeypatch):
        monkeypatch.delenv("DEEPR_LOCAL_IMAGE_URL", raising=False)
        with pytest.raises(RuntimeError, match="DEEPR_LOCAL_IMAGE_URL"):
            await P._generate_local("a prompt")


def test_portrait_command_registered_on_expert_group():
    # Guards the extraction into expert_portrait.py: importing the expert group
    # must pull in and register the portrait subcommand.
    from deepr.cli.commands.semantic.experts import expert

    assert "portrait" in expert.commands


class TestPortraitStyle:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv(PORTRAIT_STYLE_ENV, raising=False)
        assert portrait_style() == DEFAULT_PORTRAIT_STYLE

    def test_env_preference_overrides_default(self, monkeypatch):
        monkeypatch.setenv(PORTRAIT_STYLE_ENV, "flat vector, muted palette")
        assert portrait_style() == "flat vector, muted palette"

    def test_explicit_override_beats_env(self, monkeypatch):
        monkeypatch.setenv(PORTRAIT_STYLE_ENV, "from env")
        assert portrait_style("explicit style") == "explicit style"

    def test_blank_override_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv(PORTRAIT_STYLE_ENV, "from env")
        assert portrait_style("   ") == "from env"


class TestBuildPrompt:
    def test_includes_style_and_domain(self, monkeypatch):
        monkeypatch.delenv(PORTRAIT_STYLE_ENV, raising=False)
        prompt = _build_prompt("Coffee Expert", domain="coffee brewing", description=None)
        assert DEFAULT_PORTRAIT_STYLE in prompt
        assert "coffee brewing" in prompt
        assert "No text or watermarks" in prompt

    def test_custom_style_is_used(self):
        prompt = _build_prompt("X", domain="y", description=None, style="woodcut print")
        assert "woodcut print" in prompt
        assert DEFAULT_PORTRAIT_STYLE not in prompt

    def test_style_is_consistent_across_experts(self, monkeypatch):
        # Same style clause for different experts -> a coherent library look.
        monkeypatch.setenv(PORTRAIT_STYLE_ENV, "isometric, pastel")
        a = _build_prompt("Expert A", domain="alpha", description=None)
        b = _build_prompt("Expert B", domain="beta", description=None)
        assert "isometric, pastel" in a
        assert "isometric, pastel" in b

    def test_subject_is_deterministic_per_name(self, monkeypatch):
        monkeypatch.delenv(PORTRAIT_STYLE_ENV, raising=False)
        assert _build_prompt("Stable Name", domain="d", description=None) == _build_prompt(
            "Stable Name", domain="d", description=None
        )
