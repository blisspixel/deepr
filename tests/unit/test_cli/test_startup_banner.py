"""Startup presentation policy, palette, timing and interruption regressions."""

import math
import re
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

import deepr.cli.effects as effects
import deepr.cli.startup_banner as banner


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")
    for key in (
        "CI",
        "NO_COLOR",
        "DEEPR_BRANDING",
        "DEEPR_ANIMATIONS",
        "DEEPR_BANNER_MODE",
        "DEEPR_SCREEN_READER",
        "SCREENREADER",
        "TERM_SCREEN_READER",
        "DEEPR_BANNER_FPS",
        "DEEPR_BANNER_DURATION",
    ):
        monkeypatch.delenv(key, raising=False)


def terminal(width=100, **options):
    return Console(
        file=StringIO(), force_terminal=True, force_interactive=True, width=width, legacy_windows=False, **options
    )


def test_first_encounter_animates_then_seen_is_static(tmp_path):
    console = terminal()
    assert banner.resolve_banner_plan(console, state_dir=tmp_path) == banner.BannerPlan(True, "full", True)
    banner._mark_seen(tmp_path)
    assert banner.resolve_banner_plan(console, override="on", state_dir=tmp_path) == banner.BannerPlan(
        True, "static", False
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("CI", "1"),
        ("NO_COLOR", ""),
        ("TERM", "dumb"),
        ("DEEPR_ANIMATIONS", "off"),
        ("DEEPR_SCREEN_READER", "1"),
        ("SCREENREADER", "true"),
        ("TERM_SCREEN_READER", "yes"),
        ("DEEPR_BANNER_MODE", "static"),
    ],
)
def test_reduced_motion_is_static_even_when_requested(monkeypatch, tmp_path, key, value):
    monkeypatch.setenv(key, value)
    plan = banner.resolve_banner_plan(terminal(), override="on", state_dir=tmp_path)
    assert plan.show and plan.mode == "static"


@pytest.mark.parametrize("key", ["DEEPR_BANNER_MODE", "DEEPR_BRANDING"])
def test_environment_off_is_final(monkeypatch, tmp_path, key):
    monkeypatch.setenv(key, "off")
    assert not banner.resolve_banner_plan(terminal(), override="on", state_dir=tmp_path).show


@pytest.mark.parametrize("override", [None, "on", "off"])
def test_redirected_output_has_no_banner_or_marker(tmp_path, override):
    console = Console(file=StringIO(), force_terminal=False)
    banner.show_startup_banner(console, version="test", override=override, state_dir=tmp_path)
    assert console.file.getvalue() == "" and list(tmp_path.iterdir()) == []


def test_explicit_off_has_no_marker(tmp_path):
    console = terminal()
    banner.show_startup_banner(console, version="test", override="off", state_dir=tmp_path)
    assert console.file.getvalue() == "" and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("options", [{"no_color": True}, {"color_system": None}])
def test_console_capability_reduces_motion_without_environment(tmp_path, options):
    assert banner.resolve_banner_plan(terminal(**options), state_dir=tmp_path).mode == "static"


@pytest.mark.parametrize("value,expected", [("600", 12), ("12", 12), ("1", 1), ("0", 1), ("bad", 12)])
def test_frame_rate_is_bounded(monkeypatch, value, expected):
    monkeypatch.setenv("DEEPR_BANNER_FPS", value)
    assert banner._fps_for_banner() == expected


@pytest.mark.parametrize(
    "value,expected", [("3", 3.0), ("0", 0.3), ("99", 6.0), ("bad", 0.6), ("nan", 0.6), ("inf", 0.6)]
)
def test_duration_is_finite_and_bounded(monkeypatch, value, expected):
    monkeypatch.setenv("DEEPR_BANNER_DURATION", value)
    assert banner._duration_for_mode("full") == expected


def test_one_sleep_per_synchronized_frame_and_final_cursor_restore(tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(banner.time, "sleep", sleeps.append)
    console = terminal()
    banner.show_startup_banner(console, version="test", state_dir=tmp_path)
    output = console.file.getvalue()
    assert len(sleeps) == output.count(effects._SYNC_START) == 8
    assert all(delay >= 1 / 12 for delay in sleeps)
    assert 0.6 <= sum(sleeps) <= 0.75
    assert output.count(effects._SYNC_END) == 9
    assert banner._ANSI_SHOW_CURSOR in output
    assert (tmp_path / "banner_seen_v1").read_text() == "seen\n"
    for sequence in re.findall(r"\x1b\[([0-9;]*)m", output):
        assert all(int(code) in {0, 1, 2, 36} for code in sequence.split(";") if code)
    assert banner._render_ansi_frame("X", 0) == "\x1b[2;36mX\x1b[0m"
    assert banner._render_ansi_frame("X", 1) == "\x1b[1;36mX\x1b[0m"


def test_interrupt_restores_output_and_does_not_mark_seen(tmp_path, monkeypatch):
    def interrupt(_):
        raise KeyboardInterrupt()

    monkeypatch.setattr(banner.time, "sleep", interrupt)
    console = terminal()
    with pytest.raises(KeyboardInterrupt):
        banner.show_startup_banner(console, version="test", state_dir=tmp_path)
    assert console.file.getvalue().endswith(effects._SYNC_END + banner._ANSI_SHOW_CURSOR + "\x1b[0m")
    assert not (tmp_path / "banner_seen_v1").exists()


def test_render_failure_restores_cursor_before_static_fallback(tmp_path, monkeypatch):
    def fail(*_):
        raise RuntimeError("frame failed")

    monkeypatch.setattr(banner, "_render_ansi_frame", fail)
    console = terminal()
    banner.show_startup_banner(console, version="test", state_dir=tmp_path)
    text = console.file.getvalue()
    assert text.index(banner._ANSI_SHOW_CURSOR) < text.index("deepr test")
    assert (tmp_path / "banner_seen_v1").is_file()


@pytest.mark.parametrize("width,reader", [(30, False), (60, True)])
def test_accessible_compact_signature(monkeypatch, tmp_path, width, reader):
    monkeypatch.setenv("DEEPR_ANIMATIONS", "off")
    if reader:
        monkeypatch.setenv("DEEPR_SCREEN_READER", "1")
    console = terminal(width)
    banner.show_startup_banner(console, version="test", state_dir=tmp_path)
    assert console.file.getvalue() == "deepr test\n"


def test_no_color_retains_static_shape_and_version(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    console = terminal()
    banner.show_startup_banner(console, version="test", state_dir=tmp_path)
    text = console.file.getvalue()
    assert "\x1b" not in text and "█" in text and "deepr test" in text


def test_mark_is_projection_of_the_owning_dashboard_geometry():
    svg = (Path(__file__).resolve().parents[3] / "src/deepr/web/frontend/public/deepr.svg").read_text()
    assert 'd="M23 10L16 4V28"' in svg and 'd="M16 15L9 22"' in svg
    segments = [((23, 10), (16, 4)), ((16, 4), (16, 28)), ((16, 15), (9, 22))]

    def covered(x, y):
        for (ax, ay), (bx, by) in segments:
            t = max(0, min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
            if math.hypot(x - (ax + t * (bx - ax)), y - (ay + t * (by - ay))) <= 1.3:
                return True
        return False

    rows = []
    for row in range(6):
        cells = []
        for col in range(8):
            bits = sum(
                1 << bit
                for dx, dy, bit in [
                    (0, 0, 0),
                    (0, 1, 1),
                    (0, 2, 2),
                    (1, 0, 3),
                    (1, 1, 4),
                    (1, 2, 5),
                    (0, 3, 6),
                    (1, 3, 7),
                ]
                if covered((col * 2 + dx + 0.5) * 2, (row * 4 + dy + 0.5) * 32 / 24)
            )
            cells.append(chr(0x2800 + bits) if bits else " ")
        rows.append("".join(cells))
    assert tuple(rows) == banner._MARK_ART
    assert max(map(len, banner._BANNER_ART.splitlines())) <= 54


def test_default_marker_is_per_user_and_does_not_touch_cwd(tmp_path, monkeypatch):
    home = tmp_path / "user"
    cwd = tmp_path / "working"
    cwd.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("DEEPR_ANIMATIONS", "off")
    banner.show_startup_banner(terminal(60), version="test")
    assert (home / ".deepr/banner_seen_v1").read_text() == "seen\n"
    assert list(cwd.iterdir()) == []


def test_synchronized_output_does_not_escape_into_pipes():
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    with effects.synchronized_output(console):
        output.write("frame")
    assert output.getvalue() == "frame"


def test_legacy_encoding_uses_compact_plain_signature(tmp_path):
    class LegacyStream(StringIO):
        @property
        def encoding(self):
            return "cp1252"

    output = LegacyStream()
    console = Console(file=output, force_terminal=True, legacy_windows=False, width=100)
    banner.show_startup_banner(console, version="test", state_dir=tmp_path)
    assert output.getvalue() == "deepr test\n"


def test_init_requests_banner_only_after_noninteractive_refusal(monkeypatch, tmp_path):
    from click.testing import CliRunner
    from deepr.cli.main import cli

    calls = []
    monkeypatch.setattr(banner, "show_startup_banner", lambda *args, **kwargs: calls.append(kwargs))
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        refused = runner.invoke(cli, ["init", "--local-env"])
        assert refused.exit_code == 2 and not calls and not Path(".env").exists()
        completed = runner.invoke(cli, ["init", "--local-env", "--yes"])
        assert completed.exit_code == 0, completed.output
        assert len(calls) == 1 and calls[0]["version"]
