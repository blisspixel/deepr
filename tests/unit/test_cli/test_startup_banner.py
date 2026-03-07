"""Tests for startup banner policy and defaults."""

from pathlib import Path

from rich.console import Console

from deepr.cli.startup_banner import _duration_for_mode, resolve_banner_plan


def _interactive_console() -> Console:
    return Console(force_terminal=True, width=100)


def test_banner_defaults_to_full_on_first_run(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DEEPR_BRANDING", raising=False)
    monkeypatch.delenv("DEEPR_ANIMATIONS", raising=False)

    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is True
    assert plan.mode == "full"
    assert plan.mark_seen is True


def test_banner_defaults_to_full_after_seen(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DEEPR_BRANDING", raising=False)
    monkeypatch.delenv("DEEPR_ANIMATIONS", raising=False)

    (tmp_path / "banner_seen_v1").write_text("seen\n", encoding="utf-8")
    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is True
    assert plan.mode == "full"


def test_banner_disabled_in_ci_unless_forced(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CI", "1")
    monkeypatch.delenv("DEEPR_BRANDING", raising=False)

    default_plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)
    forced_plan = resolve_banner_plan(_interactive_console(), override="on", state_dir=tmp_path)

    assert default_plan.show is False
    assert forced_plan.show is True


def test_banner_respects_branding_off(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DEEPR_BRANDING", "off")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)

    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is False
    assert plan.mode == "off"


def test_banner_static_when_animations_off(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DEEPR_ANIMATIONS", "off")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DEEPR_BRANDING", raising=False)

    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is True
    assert plan.mode == "static"


def test_banner_disabled_for_screen_reader(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DEEPR_SCREEN_READER", "true")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)

    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is False
    assert plan.mode == "off"


def test_banner_override_off_always_disables(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DEEPR_BRANDING", raising=False)

    plan = resolve_banner_plan(_interactive_console(), override="off", state_dir=tmp_path)

    assert plan.show is False
    assert plan.mode == "off"


def test_banner_mode_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DEEPR_BRANDING", raising=False)
    monkeypatch.setenv("DEEPR_BANNER_MODE", "static")

    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is True
    assert plan.mode == "static"


def test_banner_mode_env_off(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DEEPR_BRANDING", raising=False)
    monkeypatch.setenv("DEEPR_BANNER_MODE", "off")

    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is False
    assert plan.mode == "off"


def test_duration_override_env(monkeypatch):
    monkeypatch.setenv("DEEPR_BANNER_DURATION", "3.0")
    assert _duration_for_mode("full") == 3.0


def test_duration_override_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("DEEPR_BANNER_DURATION", "not-a-number")
    assert _duration_for_mode("light") == 0.8

