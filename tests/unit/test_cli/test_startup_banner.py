"""Tests for startup banner policy and defaults."""

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from deepr.cli.startup_banner import (
    _BANNER_ART,
    _banner_end_hold_seconds,
    _duration_for_mode,
    _ease_in_out_cubic,
    _fps_for_banner,
    _is_truthy,
    _mark_seen,
    _precompute_gradient,
    _render_ansi_frame,
    _render_static,
    _supports_full_banner,
    _terminal_width,
    colorize_banner,
    resolve_banner_plan,
    show_startup_banner,
)


def _interactive_console() -> Console:
    return Console(force_terminal=True, force_interactive=True, width=100)


@pytest.fixture(autouse=True)
def _isolate_banner_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Banner policy is env-sensitive; keep hermetic under dumb/CI shells."""
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DEEPR_BRANDING", raising=False)
    monkeypatch.delenv("DEEPR_ANIMATIONS", raising=False)
    monkeypatch.delenv("DEEPR_BANNER_MODE", raising=False)
    monkeypatch.delenv("DEEPR_SCREEN_READER", raising=False)


def test_banner_defaults_to_full_on_first_run(tmp_path: Path):
    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is True
    assert plan.mode == "full"
    assert plan.mark_seen is True


def test_banner_defaults_to_full_after_seen(tmp_path: Path):
    (tmp_path / "banner_seen_v1").write_text("seen\n", encoding="utf-8")
    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is True
    assert plan.mode == "full"


def test_banner_disabled_in_ci_unless_forced(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CI", "1")

    default_plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)
    forced_plan = resolve_banner_plan(_interactive_console(), override="on", state_dir=tmp_path)

    assert default_plan.show is False
    assert forced_plan.show is True


def test_banner_respects_branding_off(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DEEPR_BRANDING", "off")

    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is False
    assert plan.mode == "off"


def test_banner_static_when_animations_off(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DEEPR_ANIMATIONS", "off")

    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is True
    assert plan.mode == "static"


def test_banner_disabled_for_screen_reader(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DEEPR_SCREEN_READER", "true")

    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is False
    assert plan.mode == "off"


def test_banner_override_off_always_disables(tmp_path: Path):
    plan = resolve_banner_plan(_interactive_console(), override="off", state_dir=tmp_path)

    assert plan.show is False
    assert plan.mode == "off"


def test_banner_mode_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DEEPR_BANNER_MODE", "static")

    plan = resolve_banner_plan(_interactive_console(), state_dir=tmp_path)

    assert plan.show is True
    assert plan.mode == "static"


def test_banner_mode_env_off(monkeypatch, tmp_path: Path):
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


def test_is_truthy_and_fps_and_hold(monkeypatch):
    assert _is_truthy("YES")
    assert not _is_truthy("no")
    monkeypatch.setenv("DEEPR_BANNER_FPS", "12")
    assert _fps_for_banner() == 12
    monkeypatch.setenv("DEEPR_BANNER_FPS", "bad")
    assert _fps_for_banner() == 60
    monkeypatch.setenv("DEEPR_BANNER_HOLD", "1.5")
    assert _banner_end_hold_seconds() == 1.5
    monkeypatch.setenv("DEEPR_BANNER_HOLD", "nope")
    assert _banner_end_hold_seconds() == 0.0


def test_ease_gradient_and_ansi_frame():
    assert _ease_in_out_cubic(0.0) == 0.0
    assert _ease_in_out_cubic(1.0) == 1.0
    assert _ease_in_out_cubic(0.25) < 0.5
    codes = _precompute_gradient(4)
    assert len(codes) == 4
    assert codes[0].startswith("\033[1;38;2;")
    frame = _render_ansi_frame(["AB", "  "], 2, 1.0, codes[:2], "\033[38;2;96;96;96m")
    assert "A" in frame
    assert "B" in frame


def test_supports_full_banner_and_width():
    wide = Console(force_terminal=True, width=80, file=StringIO(), legacy_windows=False)
    assert _terminal_width(wide) == 80
    assert _supports_full_banner(wide, 80) is True
    assert _supports_full_banner(wide, 20) is False
    legacy = Console(force_terminal=True, width=80, file=StringIO(), legacy_windows=True)
    assert _supports_full_banner(legacy, 80) is False


def test_colorize_and_static_render():
    markup = colorize_banner("DEEPR", sweep_progress=1.0)
    assert "D" in markup
    empty = colorize_banner("")
    assert empty == ""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, color_system=None, width=80)
    _render_static(console, "9.9.9")
    assert "9.9.9" in buf.getvalue()


def test_mark_seen_and_hidden_banner(tmp_path: Path):
    _mark_seen(tmp_path)
    assert (tmp_path / "banner_seen_v1").is_file()
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, force_interactive=False)
    show_startup_banner(console, version="1.0.0", override="off", state_dir=tmp_path)
    assert buf.getvalue() == ""


def test_show_static_banner_marks_seen(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DEEPR_BANNER_MODE", "static")
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, force_interactive=True, width=100)
    show_startup_banner(console, version="1.2.3", state_dir=tmp_path)
    output = buf.getvalue()
    assert "deepr" in output
    assert "1.2" in output
    assert not (tmp_path / "banner_seen_v1").is_file()


def test_show_full_banner_with_sleep_patched(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DEEPR_BANNER_DURATION", "0.3")
    monkeypatch.setenv("DEEPR_BANNER_FPS", "8")
    monkeypatch.setenv("DEEPR_BANNER_HOLD", "0")
    monkeypatch.setattr("deepr.cli.startup_banner._precise_sleep", lambda _target: None)
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, force_interactive=True, width=100)
    show_startup_banner(console, version="2.50.18", override="on", state_dir=tmp_path)
    output = buf.getvalue()
    assert "deepr" in output
    assert "2.50" in output
    assert "█" in _BANNER_ART
    assert (tmp_path / "banner_seen_v1").is_file()
