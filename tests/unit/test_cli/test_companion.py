"""Presentation capability, pixel projection and active-work lifecycle contracts."""

import asyncio
import copy
import importlib
import io
import os
import re
import threading
from pathlib import Path
from unittest.mock import MagicMock

import click
import pytest

from deepr.cli import colors, companion, effects, live_status
from deepr.cli.main import cli

STATES = ("idle", "working", "success", "skeptical", "error")
SNAPSHOTS = Path(__file__).with_name("snapshots") / "companion"


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "user"))
    monkeypatch.setenv("DEEPR_ENV_FILE", str(tmp_path / "startup.env"))
    monkeypatch.setattr("deepr.config._configuration_environment", None)
    for key in ("CI", "NO_COLOR", "DEEPR_COMPANION", "DEEPR_SCREEN_READER", "SCREENREADER", "TERM_SCREEN_READER"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("DEEPR_ANIMATIONS", "light")


def terminal(width=100, tty=True):
    return colors.make_console(
        file=io.StringIO(), force_terminal=tty, force_interactive=tty, width=width, legacy_windows=False
    )


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("ascii", [False, True])
def test_five_poses_with_words_in_block_and_ascii_snapshots(state, ascii):
    console = terminal(tty=False)
    console.print(companion.render_companion(state, console=console, ascii=ascii))
    output = console.file.getvalue()
    assert len(output.splitlines()) == 4
    assert state in output
    assert output == (SNAPSHOTS / f"{state}-{'ascii' if ascii else 'block'}.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("state", STATES)
def test_pixel_pairs_need_no_guessed_foreground_background(state):
    for frame in range(8):
        grid = companion._pixels(state, frame)
        assert len(grid) == 8 and all(len(row) == 16 for row in grid)
        for y in range(0, 8, 2):
            assert all(top == " " or bottom == " " or top == bottom for top, bottom in zip(grid[y], grid[y + 1]))


def test_every_still_pose_is_distinct_without_color():
    assert len({companion._figure(state, frame=0, ascii=False).plain for state in STATES}) == 5
    assert len({companion._figure(state, frame=0, ascii=True).plain for state in STATES}) == 5
    assert len({companion._figure("working", frame=i, ascii=False).plain for i in range(8)}) >= 3


@pytest.mark.parametrize(
    "key,value",
    [
        ("CI", "1"),
        ("TERM", "dumb"),
        ("DEEPR_COMPANION", "off"),
        ("DEEPR_SCREEN_READER", "1"),
        ("SCREENREADER", "yes"),
        ("TERM_SCREEN_READER", "true"),
    ],
)
def test_environment_veto_hides_every_pose_and_work(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    console = terminal()
    for state in STATES:
        companion.print_companion(state, console=console)
    with companion.companion_work("work", console=console) as status:
        assert status is None
    assert console.file.getvalue() == ""


@pytest.mark.parametrize("width,tty", [(79, True), (100, False)])
def test_capability_veto_hides_every_pose(width, tty):
    console = terminal(width, tty)
    for state in STATES:
        companion.print_companion(state, console=console)
    assert console.file.getvalue() == ""


@pytest.mark.parametrize("key", ["DEEPR_SCREEN_READER", "SCREENREADER", "TERM_SCREEN_READER"])
def test_shared_motion_policy_honors_screen_readers(monkeypatch, key):
    monkeypatch.setenv(key, "1")
    assert not effects.resolve_animation_policy(terminal()).enabled


@pytest.mark.parametrize("key,value", [("NO_COLOR", "1"), ("DEEPR_ANIMATIONS", "off")])
def test_reduced_motion_prints_once_and_starts_no_timer(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    start = MagicMock(side_effect=AssertionError("No animation allowed"))
    monkeypatch.setattr(companion, "shimmer_status", start)
    console = terminal()
    with companion.companion_work("Literal [source]", console=console) as status:
        assert status is None
    output = re.sub(r"\x1b\[[0-9;]*m", "", console.file.getvalue())
    assert output.count("working") == 1 and "Literal [source]" in output
    assert "?2026" not in output
    start.assert_not_called()


def test_idle_starts_no_thread(monkeypatch):
    start = MagicMock(side_effect=AssertionError("Idle must stay still"))
    monkeypatch.setattr(threading, "Thread", start)
    companion.print_companion("idle", console=terminal())
    start.assert_not_called()


def test_root_opt_out_survives_nested_invocation_then_resets(monkeypatch):
    from click.testing import CliRunner

    console = terminal()

    @click.command("pose-probe")
    def probe():
        companion.print_companion("idle", console=console)

    @click.command("nested-probe")
    def nested():
        cli.main(args=["pose-probe"], standalone_mode=False)

    monkeypatch.setitem(cli.commands, "pose-probe", probe)
    monkeypatch.setitem(cli.commands, "nested-probe", nested)
    runner = CliRunner()
    result = runner.invoke(cli, ["--no-companion", "nested-probe"])
    assert result.exit_code == 0, result.output
    assert console.file.getvalue() == ""
    result = runner.invoke(cli, ["pose-probe"])
    assert result.exit_code == 0 and "idle" in console.file.getvalue()
    assert "DEEPR_COMPANION" not in os.environ


def test_config_alias_persists_only_through_the_existing_environment_file(monkeypatch, tmp_path):
    from click.testing import CliRunner

    from deepr.config import read_configuration_env_file

    path = tmp_path / "private.env"
    monkeypatch.setenv("DEEPR_ENV_FILE", str(path))
    monkeypatch.setattr("deepr.config._configuration_environment", None)
    from deepr.config import configuration_env_path

    assert configuration_env_path() == path
    result = CliRunner().invoke(cli, ["config", "set", "cli.companion", "off"])
    assert result.exit_code == 0, result.output
    assert read_configuration_env_file(path)["DEEPR_COMPANION"] == "off"
    assert "DEEPR_COMPANION" not in os.environ


def test_work_updates_are_buffered_and_stop_leaves_no_refresh(monkeypatch):
    live = MagicMock()
    rendered = threading.Event()
    live.update.side_effect = lambda *args, **kwargs: rendered.set()
    monkeypatch.setattr(live_status, "Live", lambda *args, **kwargs: live)
    released = threading.Event()
    original_run = live_status.LiveShimmerStatus._run

    def paused_run(status):
        assert released.wait(timeout=3)
        original_run(status)

    monkeypatch.setattr(live_status.LiveShimmerStatus, "_run", paused_run)
    console = terminal()
    with companion.companion_work("starting", console=console) as status:
        assert status is not None and status._policy.fps <= 4 and status._policy.frame_delay >= 0.25
        for index in range(100):
            status.update(f"latest {index}")
        assert not live.update.called
        released.set()
        assert rendered.wait(timeout=3)
        assert status.message == "latest 99"
    assert status._thread is not None and not status._thread.is_alive()
    count = live.update.call_count
    threading.Event().wait(0.28)
    assert live.update.call_count == count
    live.stop.assert_called_once()
    live.start.assert_called_once_with(refresh=True)
    assert effects._SYNC_START in console.file.getvalue() and effects._SYNC_END in console.file.getvalue()


@pytest.mark.parametrize("exception", [RuntimeError, KeyboardInterrupt, asyncio.CancelledError])
def test_work_exception_stops_before_error_pose_and_preserves_exception(monkeypatch, exception):
    live = MagicMock()
    monkeypatch.setattr(live_status, "Live", lambda *args, **kwargs: live)
    console = terminal()
    with pytest.raises(exception):
        with companion.companion_work("starting", console=console) as status:
            raise exception("stopped")
    assert status._thread is not None and not status._thread.is_alive()
    live.stop.assert_called_once()
    assert "error" in console.file.getvalue()


def test_module_contains_no_fixed_rgb_or_256_color_escape():
    source = Path(companion.__file__).read_text(encoding="utf-8")
    assert not re.search(r"rgb\(|38;[25]|#[0-9a-fA-F]{6}", source)


@pytest.mark.parametrize(
    "status,experts,pushback,expected",
    [
        ("completed", ["Fixture"], False, "success"),
        ("completed", ["Fixture"], True, "skeptical"),
        ("partial", ["Fixture"], True, "error"),
        ("completed", [], False, "error"),
    ],
)
def test_consult_pose_uses_completion_and_the_actual_pushback_projection(
    monkeypatch, status, experts, pushback, expected
):
    from deepr.cli import consult_render

    payload = {
        "answer": "Synthetic presentation fixture.",
        "experts_consulted": experts,
        "synthesis_status": status,
        "perspectives": [{"expert": "Fixture", "context": {"unknown": ["Scope remains open"] if pushback else []}}],
        "agreements": ["A recorded agreement"],
        "cost_usd": 0,
    }
    before = copy.deepcopy(payload)
    seen = []
    original = consult_render.render_companion

    def render(state, *args, **kwargs):
        seen.append(state)
        return original(state, *args, **kwargs)

    monkeypatch.setattr(consult_render, "render_companion", render)
    consult_render.render_consult(payload, terminal())
    assert seen == [expected] and payload == before
    assert bool(consult_render.pushback_rows(payload)) == pushback


def test_consult_json_skips_work_figure_and_preserves_the_transaction(monkeypatch):
    module = importlib.import_module("deepr.cli.commands.semantic.expert_consult")
    console = terminal()
    monkeypatch.setattr(module, "console", console)
    calls = []
    payload = {"synthetic": True}

    async def execute(**kwargs):
        calls.append(kwargs)
        return payload

    monkeypatch.setattr(module, "execute_consult_transaction", execute)
    request = {"synthesis_backend": "local"}
    result = module._execute_cli_consult(
        question="fixture",
        experts=("Fixture",),
        max_experts=1,
        budget=0,
        backend_mode="local",
        backend_factory=None,
        capacity_request=request,
        max_elapsed_seconds=10,
        report_started=None,
        report_backend=None,
        json_output=True,
    )
    assert result is payload and len(calls) == 1
    assert calls[0]["requested_capacity"] is request and calls[0]["budget"] == 0
    assert console.file.getvalue() == ""


def test_pose_colors_only_the_state_and_keeps_adjacent_body_in_foreground():
    from rich.text import Text

    console = terminal()
    companion.print_companion("working", "Literal [source]", console=console)
    rendered = Text.from_ansi(console.file.getvalue())
    style = rendered.get_style_at_offset(console, rendered.plain.index("Literal"))
    assert style.color is None or style.color.name == "default"


def test_invalid_companion_preference_refuses_without_writing():
    from click.testing import CliRunner

    from deepr.config import configuration_env_path

    path = configuration_env_path()
    assert not path.exists()
    result = CliRunner().invoke(cli, ["config", "set", "cli.companion", "blink"])
    assert result.exit_code != 0 and "Allowed values: off, on" in result.output
    assert not path.exists()


def test_legacy_encoding_automatically_uses_the_colored_ascii_pose():
    class LegacyStream(io.StringIO):
        @property
        def encoding(self):
            return "cp1252"

    output = LegacyStream()
    console = colors.make_console(file=output, force_terminal=True, width=100, legacy_windows=False)
    companion.print_companion("idle", console=console)
    assert output.getvalue().isascii() and "idle" in output.getvalue()
    figure = companion._figure("idle", frame=0, ascii=True)
    style = figure.get_style_at_offset(console, figure.plain.index("o"))
    assert style.color.name == "cyan"


@pytest.mark.parametrize("width", [60, 80, 100])
def test_interactive_prompt_keeps_every_action_key_literal_and_visible(monkeypatch, width):
    from rich.text import Text

    module = importlib.import_module("deepr.cli.commands.interactive")
    console = terminal(width)
    monkeypatch.setattr(module, "console", console)
    monkeypatch.setattr(module, "_get_home_status", lambda: ("provider: fixture", "spent: $0.00", "queue: empty"))
    monkeypatch.setattr(module.click, "prompt", lambda *args, **kwargs: "q")
    assert module._print_main_menu() == "q"
    visible = Text.from_ansi(console.file.getvalue()).plain
    for key in ("1", "2", "3", "4", "5", "6", "q"):
        assert f"[{key}]" in visible
    assert max(map(len, visible.splitlines())) <= width


def test_interactive_fields_do_not_inherit_dim_from_their_labels(monkeypatch):
    from rich.text import Text

    module = importlib.import_module("deepr.cli.commands.interactive")
    console = terminal()
    monkeypatch.setattr(module, "console", console)
    monkeypatch.setattr(module, "_get_home_status", lambda: ("provider: fixture", "spent: $0.00", "queue: empty"))
    monkeypatch.setattr(module.click, "prompt", lambda *args, **kwargs: "q")
    module._print_main_menu()
    rendered = Text.from_ansi(console.file.getvalue())
    for field in ("provider: fixture", "spent: $0.00", "[r]"):
        assert not rendered.get_style_at_offset(console, rendered.plain.index(field)).dim
    assert rendered.get_style_at_offset(console, rendered.plain.index("spent: $0.00")).bold
