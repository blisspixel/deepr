"""Startup banner rendering for interactive CLI sessions.

Scribe-style animated gradient sweep for Deepr startup.
"""

from __future__ import annotations

import colorsys
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.text import Text

from deepr.cli.effects import resolve_animation_policy

_BANNER_SENTINEL = "banner_seen_v1"
_START_HUE = 200 / 360
_END_HUE = 320 / 360
_ANSI_RESET = "\033[0m"
_ANSI_HIDE_CURSOR = "\033[?25l"
_ANSI_SHOW_CURSOR = "\033[?25h"

_BANNER_ART = (
    "  ██████╗ ███████╗███████╗██████╗ ██████╗ \n"
    "  ██╔══██╗██╔════╝██╔════╝██╔══██╗██╔══██╗\n"
    "  ██║  ██║█████╗  █████╗  ██████╔╝██████╔╝\n"
    "  ██║  ██║██╔══╝  ██╔══╝  ██╔═══╝ ██╔══██╗\n"
    "  ██████╔╝███████╗███████╗██║     ██║  ██║\n"
    "  ╚═════╝ ╚══════╝╚══════╝╚═╝     ╚═╝  ╚═╝"
)


@dataclass(frozen=True)
class BannerPlan:
    """Resolved plan for startup banner behavior."""

    show: bool
    mode: str  # off | static | light | full
    mark_seen: bool


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _screen_reader_enabled() -> bool:
    for env_key in ("DEEPR_SCREEN_READER", "SCREENREADER", "TERM_SCREEN_READER"):
        raw = os.getenv(env_key)
        if raw and _is_truthy(raw):
            return True
    return False


def _banner_seen_path(state_dir: Path) -> Path:
    return state_dir / _BANNER_SENTINEL


def _terminal_width(console: Console) -> int:
    width = getattr(console, "width", 0) or 0
    if width > 0:
        return width
    return shutil.get_terminal_size((100, 30)).columns


def _supports_full_banner(console: Console, width: int) -> bool:
    if width < 50:
        return False
    if bool(getattr(console, "legacy_windows", False)):
        return False
    encoding = (getattr(console.file, "encoding", "") or "").lower()
    if encoding and "utf" not in encoding:
        return False
    return True


def _env_banner_mode_override() -> str | None:
    raw = os.getenv("DEEPR_BANNER_MODE", "").strip().lower()
    if raw in {"off", "static", "light", "full"}:
        return raw
    return None


def _duration_for_mode(mode: str) -> float:
    defaults = {"light": 0.8, "full": 1.5}
    base = defaults.get(mode, 1.0)

    raw = os.getenv("DEEPR_BANNER_DURATION", "").strip()
    if not raw:
        return base

    try:
        value = float(raw)
    except ValueError:
        return base

    return min(6.0, max(0.3, value))


def _fps_for_banner() -> int:
    raw = os.getenv("DEEPR_BANNER_FPS", "").strip()
    if not raw:
        return 60
    try:
        value = int(raw)
    except ValueError:
        return 60
    return max(8, min(60, value))


def _banner_end_hold_seconds() -> float:
    raw = os.getenv("DEEPR_BANNER_HOLD", "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return max(0.0, min(2.0, value))


def resolve_banner_plan(console: Console, override: str | None = None, state_dir: Path = Path(".deepr")) -> BannerPlan:
    """Resolve whether to show startup banner and which mode to use."""
    override_normalized = (override or "").strip().lower() or None
    if override_normalized not in {None, "on", "off"}:
        override_normalized = None

    interactive = bool(getattr(console, "is_terminal", False))
    dumb = bool(getattr(console, "is_dumb_terminal", False))
    in_ci = os.getenv("CI", "").strip().lower() in {"1", "true", "yes"}
    no_color = os.getenv("NO_COLOR") is not None

    if override_normalized == "off":
        return BannerPlan(show=False, mode="off", mark_seen=False)

    if not interactive or dumb:
        return BannerPlan(show=False, mode="off", mark_seen=False)

    if (in_ci or no_color or _screen_reader_enabled()) and override_normalized != "on":
        return BannerPlan(show=False, mode="off", mark_seen=False)

    env_mode = _env_banner_mode_override()
    if override_normalized is None and env_mode == "off":
        return BannerPlan(show=False, mode="off", mark_seen=False)

    branding_mode = os.getenv("DEEPR_BRANDING", "").strip().lower()
    if branding_mode == "off" and override_normalized != "on":
        return BannerPlan(show=False, mode="off", mark_seen=False)

    policy = resolve_animation_policy(console)
    seen = _banner_seen_path(state_dir).exists()

    if not policy.enabled:
        return BannerPlan(show=True, mode="static", mark_seen=not seen)

    if override_normalized == "on":
        return BannerPlan(show=True, mode="full", mark_seen=not seen)

    if override_normalized is None and env_mode in {"static", "light", "full"}:
        return BannerPlan(show=True, mode=env_mode, mark_seen=env_mode == "full" and not seen)

    return BannerPlan(show=True, mode="full", mark_seen=not seen)


def _ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def _precise_sleep(target_time: float) -> None:
    remaining = target_time - time.perf_counter()
    if remaining <= 0:
        return
    if remaining > 0.002:
        time.sleep(remaining - 0.002)
    while time.perf_counter() < target_time:
        pass


def _precompute_gradient(max_width: int) -> list[str]:
    codes: list[str] = []
    for col in range(max_width):
        col_ratio = col / max(1, max_width - 1)
        hue = _START_HUE + (_END_HUE - _START_HUE) * col_ratio
        r, g, b = [int(v * 255) for v in colorsys.hsv_to_rgb(hue % 1.0, 0.85, 0.92)]
        codes.append(f"\033[1;38;2;{r};{g};{b}m")
    return codes


def _render_ansi_frame(
    lines: list[str],
    max_width: int,
    sweep_progress: float,
    gradient_codes: list[str],
    muted_code: str,
) -> str:
    parts: list[str] = []
    for line_idx, line in enumerate(lines):
        if line_idx > 0:
            parts.append("\n")
        last_code: str | None = None
        for col, ch in enumerate(line):
            if ch == " ":
                parts.append(" ")
                last_code = None
                continue

            col_ratio = col / max(1, max_width - 1)
            code = gradient_codes[col] if col_ratio <= sweep_progress else muted_code

            if code != last_code:
                parts.append(code)
                last_code = code
            parts.append(ch)

        parts.append(_ANSI_RESET)

    return "".join(parts)


def colorize_banner(
    art: str,
    sweep_progress: float = 1.0,
    start_hue: float = _START_HUE,
    end_hue: float = _END_HUE,
    muted_color: str = "dim",
) -> str:
    lines = art.split("\n")
    if not lines:
        return ""

    max_width = max(len(line) for line in lines)
    if max_width == 0:
        return art

    result_lines: list[str] = []
    for line in lines:
        parts: list[str] = []
        for col, ch in enumerate(line):
            if ch == " ":
                parts.append(" ")
                continue

            col_ratio = col / max(1, max_width - 1)

            if col_ratio <= sweep_progress:
                hue = start_hue + (end_hue - start_hue) * col_ratio
                r, g, b = [int(v * 255) for v in colorsys.hsv_to_rgb(hue % 1.0, 0.85, 0.92)]
                parts.append(f"[bold rgb({r},{g},{b})]{escape(ch)}[/]")
            else:
                parts.append(f"[{muted_color}]{escape(ch)}[/{muted_color}]")

        result_lines.append("".join(parts))

    return "\n".join(result_lines)


def _render_static(console: Console, version: str) -> None:
    console.print()
    if getattr(console, "no_color", False):
        console.print(_BANNER_ART)
    else:
        console.print(Text.from_markup(colorize_banner(_BANNER_ART, sweep_progress=1.0)))
    console.print(f"[dim]deepr {version}[/dim]")
    console.print()


def _mark_seen(state_dir: Path) -> None:
    path = _banner_seen_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("seen\n", encoding="utf-8")


def show_startup_banner(
    console: Console,
    *,
    version: str,
    override: str | None = None,
    state_dir: Path = Path(".deepr"),
) -> None:
    """Render startup banner if allowed by runtime and policy."""
    plan = resolve_banner_plan(console, override=override, state_dir=state_dir)
    if not plan.show:
        return

    width = _terminal_width(console)
    if plan.mode == "static":
        _render_static(console, version)
        if plan.mark_seen:
            _mark_seen(state_dir)
        return

    render_mode = plan.mode if _supports_full_banner(console, width) else "light"

    # If colors are unavailable, degrade to plain static output.
    if getattr(console, "no_color", False):
        _render_static(console, version)
        if plan.mark_seen:
            _mark_seen(state_dir)
        return

    duration = _duration_for_mode(render_mode)
    fps = _fps_for_banner()
    frame_time = 1.0 / float(fps)

    try:
        lines = _BANNER_ART.split("\n")
        num_lines = len(lines)
        max_width = max(len(line) for line in lines)
        total_frames = max(2, int(duration * fps))

        gradient_codes = _precompute_gradient(max_width)
        muted_code = "\033[38;2;96;96;96m"

        frames: list[str] = []
        for f in range(total_frames + 1):
            progress = f / total_frames
            eased = _ease_in_out_cubic(progress)
            frames.append(_render_ansi_frame(lines, max_width, eased, gradient_codes, muted_code))

        out = console.file or sys.stdout
        cursor_up = f"\033[{num_lines - 1}A\r"

        out.write(_ANSI_HIDE_CURSOR)
        out.write(frames[0])
        if hasattr(out, "flush"):
            out.flush()

        start = time.perf_counter()
        for i in range(1, len(frames)):
            _precise_sleep(start + i * frame_time)
            out.write(cursor_up)
            out.write(frames[i])
            if hasattr(out, "flush"):
                out.flush()

        hold = _banner_end_hold_seconds()
        if hold > 0:
            _precise_sleep(time.perf_counter() + hold)

        out.write(_ANSI_SHOW_CURSOR + "\n")
        if hasattr(out, "flush"):
            out.flush()

        console.print(f"[dim]deepr {version}[/dim]")
        console.print()

    except Exception:
        try:
            out = console.file or sys.stdout
            out.write(_ANSI_SHOW_CURSOR + _ANSI_RESET + "\n")
            if hasattr(out, "flush"):
                out.flush()
        except Exception:
            pass
        _render_static(console, version)

    if plan.mark_seen:
        _mark_seen(state_dir)
