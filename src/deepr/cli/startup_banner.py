"""Palette-based startup signature for interactive CLI sessions."""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

from rich.color import ColorSystem
from rich.console import Console
from rich.style import Style
from rich.text import Text

from deepr.cli.colors import ROLE_STYLES
from deepr.cli.effects import (
    _SYNC_END,
    resolve_animation_policy,
    synchronized_output,
)
from deepr.cli.effects import (
    screen_reader_enabled as _screen_reader_enabled,
)

_BANNER_SENTINEL = "banner_seen_v1"
_ANSI_HIDE_CURSOR = "\033[?25l"
_ANSI_SHOW_CURSOR = "\033[?25h"
# Derived from public/deepr.svg's three path segments; see the validation recipe.
_MARK_ART = (
    "   ⢠⡄   ",
    "   ⢸⡟⢦  ",
    "   ⢸⡇   ",
    "  ⣠⢿⡇   ",
    "  ⠁⢸⡇   ",
    "   ⠘⠃   ",
)
_WORDMARK = (
    "██████╗ ███████╗███████╗██████╗ ██████╗ ",
    "██╔══██╗██╔════╝██╔════╝██╔══██╗██╔══██╗",
    "██║  ██║█████╗  █████╗  ██████╔╝██████╔╝",
    "██║  ██║██╔══╝  ██╔══╝  ██╔═══╝ ██╔══██╗",
    "██████╔╝███████╗███████╗██║     ██║  ██║",
    "╚═════╝ ╚══════╝╚══════╝╚═╝     ╚═╝  ╚═╝",
)
_BANNER_ART = "\n".join(mark + "  " + word for mark, word in zip(_MARK_ART, _WORDMARK, strict=True))


@dataclass(frozen=True)
class BannerPlan:
    """Resolved presentation policy, independent of routing or execution."""

    show: bool
    mode: str
    mark_seen: bool


def _banner_seen_path(state_dir: Path) -> Path:
    return state_dir / _BANNER_SENTINEL


def _supports_full_banner(console: Console, width: int) -> bool:
    encoding = (getattr(console.file, "encoding", "") or "utf-8").lower()
    return width >= 54 and not console.legacy_windows and "utf" in encoding and not _screen_reader_enabled()


def _duration_for_mode(mode: str) -> float:
    try:
        value = float(os.getenv("DEEPR_BANNER_DURATION", "0.6"))
    except ValueError:
        return 0.6
    return min(6.0, max(0.3, value)) if math.isfinite(value) else 0.6


def _fps_for_banner() -> int:
    try:
        value = int(os.getenv("DEEPR_BANNER_FPS", "12"))
    except ValueError:
        return 12
    return max(1, min(12, value))


def resolve_banner_plan(console: Console, override: str | None = None, state_dir: Path | None = None) -> BannerPlan:
    """Only a first interactive encounter animates; all policy vetoes remain final."""
    from deepr.config import default_data_dir

    state_dir = state_dir if state_dir is not None else default_data_dir()
    env_mode = os.getenv("DEEPR_BANNER_MODE", "").strip().lower()
    if override == "off" or env_mode == "off" or not console.is_terminal:
        return BannerPlan(False, "off", False)
    if os.getenv("DEEPR_BRANDING", "").strip().lower() == "off":
        return BannerPlan(False, "off", False)
    seen = _banner_seen_path(state_dir).exists()
    reduced = (
        seen
        or env_mode == "static"
        or _screen_reader_enabled()
        or console.no_color
        or console.color_system is None
        or not resolve_animation_policy(console).enabled
        or not _supports_full_banner(console, console.width)
    )
    return BannerPlan(True, "static" if reduced else "full", not seen)


def _render_ansi_frame(art: str, progress: float) -> str:
    accent = Style.parse(ROLE_STYLES["accent"])
    lines = art.splitlines()
    output = []
    for index, line in enumerate(lines):
        fill = (len(lines) - index) / len(lines)
        intensity = (
            Style(dim=True)
            if progress <= 0 or progress < fill - 0.2
            else Style()
            if progress < fill
            else Style(bold=True)
        )
        output.append((accent + intensity).render(line, color_system=ColorSystem.STANDARD))
    return "\n".join(output)


def _render_static(console: Console, version: str) -> None:
    if not _supports_full_banner(console, console.width):
        console.print(Text(f"deepr {version}"))
        return
    style = "" if console.no_color or console.color_system is None else ROLE_STYLES["accent"]
    console.print(Text(_BANNER_ART, style=style))
    console.print(Text(f"deepr {version}"))
    console.print()


def _animate(console: Console) -> None:
    out = console.file
    lines = _BANNER_ART.count("\n") + 1
    duration, fps = _duration_for_mode("full"), _fps_for_banner()
    count = max(2, math.ceil(duration * fps))
    interval = max(1 / fps, duration / count)
    try:
        out.write(_ANSI_HIDE_CURSOR)
        for index in range(count):
            cursor = "" if index == 0 else f"\033[{lines - 1}A\r"
            with synchronized_output(console):
                out.write(cursor + _render_ansi_frame(_BANNER_ART, index / (count - 1)))
            time.sleep(interval)
        out.write("\n")
    finally:
        out.write(_SYNC_END + _ANSI_SHOW_CURSOR + "\033[0m")
        out.flush()


def _mark_seen(state_dir: Path) -> None:
    path = _banner_seen_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("seen\n", encoding="utf-8")


def show_startup_banner(
    console: Console, *, version: str, override: str | None = None, state_dir: Path | None = None
) -> None:
    """Render a bounded reveal or static signature without changing command policy."""
    from deepr.config import default_data_dir

    state_dir = state_dir if state_dir is not None else default_data_dir()
    plan = resolve_banner_plan(console, override=override, state_dir=state_dir)
    if not plan.show:
        return
    if plan.mode == "static":
        _render_static(console, version)
    else:
        try:
            _animate(console)
        except Exception:
            _render_static(console, version)
        else:
            console.print(Text(f"deepr {version}"))
            console.print()
    if plan.mark_seen:
        _mark_seen(state_dir)
