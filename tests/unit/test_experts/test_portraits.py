"""Tests for expert portrait prompt building and the consistent style preference.

Pure prompt/style logic only - no image provider is called (those paths need a
key and cost money, so they stay out of the unit suite).
"""

from __future__ import annotations

from deepr.experts.portraits import (
    DEFAULT_PORTRAIT_STYLE,
    PORTRAIT_STYLE_ENV,
    _build_prompt,
    portrait_style,
)


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
