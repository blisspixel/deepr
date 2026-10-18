"""Optional terminal companion: presentation of recorded workflow states only."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from deepr.cli.colors import ROLE_STYLES
from deepr.cli.effects import resolve_animation_policy, screen_reader_enabled
from deepr.cli.live_status import LiveShimmerStatus, shimmer_status

CompanionState = Literal["idle", "working", "success", "skeptical", "error"]
_DISABLED: ContextVar[bool] = ContextVar("deepr_companion_disabled", default=False)
_STATE_ROLES = {"idle": "text", "working": "live", "success": "success", "skeptical": "warning", "error": "error"}
_PIXEL_ROLES = {"x": "text", "o": "accent", "?": "warning"}
_ASCII = {
    "idle": ("    ^      ^    ", "   ( o  o )     ", "    (____)      ", "  ===/==\\====   "),
    "working": ("    ^      ^    ", "   ( >  > )     ", "    (____)      ", "  ===/==\\====   "),
    "success": ("    ^      ^    ", "   ( -  - )     ", "    (____)      ", "  ===/==\\====   "),
    "skeptical": ("    ^_     ^    ", "   ( o  - )     ", "    (____)      ", "  ===/==\\====   "),
    "error": ("   \\^    ^/     ", "   ( !  ! )     ", "    (____)      ", "  ===/==\\====   "),
}


def disable_companion_option(ctx: click.Context, _param: click.Option, value: bool) -> bool:
    """Scope an opt-out through nested commands without modifying caller environment."""
    if value:
        token = _DISABLED.set(True)
        ctx.call_on_close(lambda: _DISABLED.reset(token))
    return value


def companion_allowed(console: Console) -> bool:
    """Decide display capability only, never execution or answer quality."""
    return (
        console.is_terminal
        and console.width >= 80
        and not console.is_dumb_terminal
        and not screen_reader_enabled()
        and not _DISABLED.get()
        and os.getenv("DEEPR_COMPANION", "on").strip().lower() != "off"
        and os.getenv("CI", "").strip().lower() not in {"1", "true", "yes", "on"}
    )


def _pixels(state: CompanionState, frame: int) -> tuple[str, ...]:
    grid = [[" "] * 16 for _ in range(8)]
    silhouette = (
        [4, 11],
        [3, 4, 5, 10, 11, 12],
        range(2, 14),
        range(2, 14),
        range(3, 13),
        range(4, 12),
        [5, 6, 9, 10],
        range(2, 14),
    )
    for y, columns in enumerate(silhouette):
        for x in columns:
            grid[y][x] = "x"
    eyes = [6, 7, 10, 11] if state == "working" and frame % 8 in {0, 1, 2, 3} else [5, 6, 9, 10]
    closed = state == "success" or (state == "working" and frame % 8 == 6)
    for index, x in enumerate(eyes):
        lower = closed or index % 2 == 1
        grid[2][x], grid[3][x] = (" ", "o") if lower else ("o", " ")
    if state == "skeptical":
        grid[0][5], grid[1][5] = "?", " "
    if state == "error":
        for x in [2, 5, 10, 13]:
            grid[0][x] = "x"
    return tuple("".join(row) for row in grid)


def _figure(state: CompanionState, *, frame: int, ascii: bool) -> Text:
    if ascii:
        rows = _ASCII[state]
        if state == "working" and frame % 8 == 6:
            rows = _ASCII["success"]
        result = Text()
        for y, row in enumerate(rows):
            if y:
                result.append("\n")
            for x, character in enumerate(row):
                role = (
                    "accent"
                    if y == 1 and x in {5, 8}
                    else "warning"
                    if state == "skeptical" and y == 0 and x == 5
                    else "text"
                )
                result.append(character, style=ROLE_STYLES[role])
        return result
    grid = _pixels(state, frame)
    result = Text()
    for y in range(0, 8, 2):
        if y:
            result.append("\n")
        for x in range(16):
            top, bottom = grid[y][x], grid[y + 1][x]
            pixel = top if top != " " else bottom
            glyph = " " if pixel == " " else "█" if top == bottom else "▀" if top != " " else "▄"
            result.append(glyph, style=ROLE_STYLES[_PIXEL_ROLES[pixel]] if pixel != " " else None)
    return result


def render_companion(
    state: CompanionState, message: str | Text = "", *, console: Console, frame: int = 0, ascii: bool | None = None
) -> Table:
    """Project one still pose with its authoritative word and literal adjacent text."""
    if ascii is None:
        encoding = (getattr(console.file, "encoding", "") or "utf-8").lower()
        ascii = console.legacy_windows or "utf" not in encoding
    label = Text()
    label.append(state, style=ROLE_STYLES[_STATE_ROLES[state]])
    if message:
        label.append("\n")
        label.append_text(message if isinstance(message, Text) else Text(message, style=ROLE_STYLES["text"]))
    table = Table.grid(padding=(0, 1))
    table.add_column(width=16, no_wrap=True)
    table.add_column()
    table.add_row(_figure(state, frame=frame, ascii=ascii), label)
    return table


def print_companion(state: CompanionState, message: str | Text = "", *, console: Console) -> None:
    if companion_allowed(console):
        console.print(render_companion(state, message, console=console))


@contextmanager
def companion_work(
    message: str, *, console: Console, enabled: bool = True, report_error: bool = True
) -> Iterator[LiveShimmerStatus | None]:
    """Refresh only while work is active; reduced motion starts no timer."""
    if not enabled or not companion_allowed(console):
        yield None
        return

    def render(current: str, phase: float) -> Table:
        return render_companion("working", current, console=console, frame=int(phase * 8))

    try:
        if not resolve_animation_policy(console).enabled:
            print_companion("working", message, console=console)
            yield None
        else:
            with shimmer_status(message, console=console, renderer=render, max_fps=4) as status:
                yield status
    except BaseException:
        if report_error:
            print_companion("error", "stopped", console=console)
        raise
