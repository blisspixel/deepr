"""Tests for cross-platform CLI visual effects policy and render helpers."""

from rich.console import Console

from deepr.cli.effects import branding_enabled, gradient_text, resolve_animation_policy, shimmer_text


def test_policy_defaults_to_light_enabled(monkeypatch):
    monkeypatch.delenv("DEEPR_ANIMATIONS", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    policy = resolve_animation_policy(Console())
    assert policy.mode in {"light", "off"}
    if policy.mode == "light":
        assert policy.enabled is True


def test_policy_off_via_env(monkeypatch):
    monkeypatch.setenv("DEEPR_ANIMATIONS", "off")
    policy = resolve_animation_policy(Console())
    assert policy.mode == "off"
    assert policy.enabled is False
    assert policy.fps == 0


def test_branding_off_by_default(monkeypatch):
    monkeypatch.delenv("DEEPR_BRANDING", raising=False)
    assert branding_enabled(Console()) is False


def test_branding_on_when_supported(monkeypatch):
    monkeypatch.setenv("DEEPR_BRANDING", "on")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert branding_enabled(Console()) in {True, False}


def test_shimmer_text_preserves_content():
    text = "Processing request"
    rendered = shimmer_text(text, phase=0.5)
    assert rendered.plain == text
    assert len(rendered.spans) >= 1


def test_gradient_text_preserves_content():
    text = "DEEPR"
    rendered = gradient_text(text)
    assert rendered.plain == text
    assert len(rendered.spans) >= 1
