"""Startup banner rendering for interactive CLI sessions.

Provides a short, polished terminal intro with safe cross-terminal fallbacks.
The banner is enabled by default for interactive human sessions and suppressed
for CI/non-interactive environments.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from deepr.cli.effects import gradient_text, resolve_animation_policy

_BANNER_SENTINEL = "banner_seen_v1"
_PIXEL_WORDMARK = [
    "██████  ███████ ███████ ██████  ██████ ",
    "██   ██ ██      ██      ██   ██ ██   ██",
    "██   ██ █████   █████   ██████  ██████ ",
    "██   ██ ██      ██      ██      ██   ██",
    "██████  ███████ ███████ ██      ██   ██",
]


@dataclass(frozen=True)
class BannerPlan:
    """Resolved plan for startup banner behavior."""

    show: bool
    mode: str  # off | static | light | full
    mark_seen: bool


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _screen_reader_enabled() -> bool:
    """Detect common screen-reader mode signals."""
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
    """Check if runtime can safely render the full animated banner."""
    if width < 94:
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
    defaults = {"light": 0.45, "full": 0.95}
    base = defaults.get(mode, 0.75)

    raw = os.getenv("DEEPR_BANNER_DURATION", "").strip()
    if not raw:
        return base

    try:
        value = float(raw)
    except ValueError:
        return base

    # Keep startup motion short and predictable.
    return min(6.0, max(0.3, value))


def _fps_for_banner(policy_fps: int) -> int:
    raw = os.getenv("DEEPR_BANNER_FPS", "").strip()
    if not raw:
        # Prefer smoother startup by default; override with DEEPR_BANNER_FPS.
        return max(24, min(60, max(policy_fps, 48)))
    try:
        value = int(raw)
    except ValueError:
        return max(24, min(60, max(policy_fps, 48)))
    return max(8, min(60, value))


def _banner_renderer_mode() -> str:
    raw = os.getenv("DEEPR_BANNER_RENDERER", "auto").strip().lower()
    if raw in {"auto", "rich", "ansi"}:
        return raw
    return "auto"


def _banner_end_hold_seconds() -> float:
    raw = os.getenv("DEEPR_BANNER_HOLD", "").strip()
    if not raw:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        return 0.45
    return max(0.0, min(2.0, value))


def _supports_truecolor(console: Console) -> bool:
    color_system = str(getattr(console, "color_system", "") or "").lower()
    return color_system in {"truecolor", "windows"}


def _supports_unicode_blocks(console: Console) -> bool:
    encoding = (getattr(console.file, "encoding", "") or "").lower()
    return "utf" in encoding or encoding == ""


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

    # Default to full intro each launch for a consistent branded experience.
    return BannerPlan(show=True, mode="full", mark_seen=not seen)


def _build_route_line(phase: float, compact: bool, animated: bool) -> Text:
    stages = [("Fast", "grok"), ("Balanced", "gpt-5.4"), ("Deep", "o3")]

    active_idx = int(phase * len(stages)) % len(stages) if animated else -1
    route_line = Text("Routing: ", style="dim")

    for idx, (tier, model) in enumerate(stages):
        active = idx == active_idx
        prefix = "> " if active else "  "
        style = "bold cyan" if active else "dim"
        label = model if compact else f"{tier} {model}"
        route_line.append(prefix + label, style=style)
        if idx < len(stages) - 1:
            route_line.append(" -> ", style="dim")

    return route_line


def _build_route_note(compact: bool) -> Text:
    if compact:
        return Text("Typical spend/job: ~$0.01 / ~$0.30 / ~$0.50.", style="dim")
    return Text("Typical spend/job: grok ~$0.01 | gpt-5.4 ~$0.30 | o3 ~$0.50. Press 4 for live costs.", style="dim")


def _wordmark_line(line: str, *, phase: float = 0.0, reveal: float = 1.0) -> Text:
    visible_cols = int(max(0.0, min(1.0, reveal)) * len(line))
    text = Text()
    pulse = int(phase * 10) % 2 == 0
    body = "bright_cyan" if pulse else "cyan"
    for i, ch in enumerate(line):
        if i >= visible_cols:
            text.append(" ")
            continue
        if ch == " ":
            text.append(" ")
        else:
            # Copilot-like look: cyan body with white edge highlights.
            edge = i + 1 >= len(line) or line[i + 1] == " " or i == 0
            style = "bold white" if edge else f"bold {body}"
            text.append(ch, style=style)
    return text


def _hero_lines(phase: float, *, mode: str, width: int) -> list[Text]:
    _ = width
    lines: list[Text] = []
    reveal = phase if mode == "full" else 1.0
    for idx in range(len(_PIXEL_WORDMARK)):
        left = _PIXEL_WORDMARK[idx]
        row = Text()
        row.append_text(_wordmark_line(left, phase=phase + (idx * 0.07), reveal=reveal))
        lines.append(row)
    return lines


def _render_panel_to_ansi(console: Console, panel: Panel) -> tuple[str, int]:
    sink = StringIO()
    render_console = Console(
        file=sink,
        force_terminal=True,
        width=max(60, _terminal_width(console)),
        color_system=getattr(console, "color_system", "auto"),
        legacy_windows=bool(getattr(console, "legacy_windows", False)),
    )
    render_console.print(panel)
    rendered = sink.getvalue().rstrip("\n")
    line_count = rendered.count("\n") + 1
    return rendered, line_count


def _render_group_to_ansi(console: Console, group: Group) -> tuple[str, int]:
    sink = StringIO()
    render_console = Console(
        file=sink,
        force_terminal=True,
        width=max(60, _terminal_width(console)),
        color_system=getattr(console, "color_system", "auto"),
        legacy_windows=bool(getattr(console, "legacy_windows", False)),
    )
    render_console.print(group)
    rendered = sink.getvalue().rstrip("\n")
    line_count = rendered.count("\n") + 1
    return rendered, line_count


def _precise_sleep(target_time: float) -> None:
    remaining = target_time - time.perf_counter()
    if remaining <= 0:
        return
    if remaining > 0.002:
        time.sleep(remaining - 0.002)
    while time.perf_counter() < target_time:
        pass


def _clear_rendered_region(out: object, line_count: int) -> None:
    if line_count <= 0:
        return
    out.write(f"\x1b[{line_count}A\r")
    for i in range(line_count):
        out.write("\x1b[2K")
        if i < line_count - 1:
            out.write("\x1b[1B\r")
    out.write(f"\x1b[{max(line_count - 1, 0)}A\r")


def _play_ansi_frames(
    console: Console,
    frames: list[str],
    line_count: int,
    frame_delay: float,
    wipe_at_end: bool = False,
    end_hold_seconds: float = 0.0,
) -> None:
    if not frames:
        return
    out = console.file or sys.stdout
    hide_cursor = "\x1b[?25l"
    show_cursor = "\x1b[?25h"
    cursor_up = f"\x1b[{line_count}A\r"
    try:
        out.write(hide_cursor)
        out.write(frames[0])
        out.write("\n")
        if hasattr(out, "flush"):
            out.flush()
        start = time.perf_counter()
        for i, frame in enumerate(frames[1:], start=1):
            _precise_sleep(start + (i * frame_delay))
            out.write(cursor_up)
            out.write(frame)
            out.write("\n")
            if hasattr(out, "flush"):
                out.flush()
        if end_hold_seconds > 0:
            _precise_sleep(time.perf_counter() + end_hold_seconds)
        if wipe_at_end:
            _clear_rendered_region(out, line_count)
    finally:
        out.write(show_cursor)
        out.write("\n")
        if hasattr(out, "flush"):
            out.flush()


def _wordmark_rgb(phase: float, column: int) -> tuple[int, int, int]:
    # Smooth whole-word gradient: blue -> violet -> pink, with subtle drift.
    c0 = (78, 164, 245)   # blue
    c1 = (150, 126, 232)  # violet
    c2 = (222, 120, 176)  # pink
    width = max(1, len(_PIXEL_WORDMARK[0]) - 1)
    base_t = column / width
    drift = (phase - 0.5) * 0.10
    t = max(0.0, min(1.0, base_t + drift))
    if t < 0.5:
        u = t / 0.5
        return (
            int(c0[0] + (c1[0] - c0[0]) * u),
            int(c0[1] + (c1[1] - c0[1]) * u),
            int(c0[2] + (c1[2] - c0[2]) * u),
        )
    u = (t - 0.5) / 0.5
    return (
        int(c1[0] + (c2[0] - c1[0]) * u),
        int(c1[1] + (c2[1] - c1[1]) * u),
        int(c1[2] + (c2[2] - c1[2]) * u),
    )


def _shadow_rgb(phase: float, column: int) -> tuple[int, int, int]:
    base = _wordmark_rgb(phase, column)
    # Keep shadow subtle so gradient remains dominant.
    return (max(0, int(base[0] * 0.22)), max(0, int(base[1] * 0.22)), max(0, int(base[2] * 0.24)))


def _wordmark_ansi_frame(phase: float, width: int, truecolor: bool, unicode_blocks: bool) -> str:
    lines = list(_PIXEL_WORDMARK)
    fill_char = "█" if unicode_blocks else "#"
    shadow_char = "░" if unicode_blocks else "."
    enable_shadow = os.getenv("DEEPR_BANNER_SHADOW", "0").strip().lower() in {"1", "true", "yes", "on"}
    reveal = max(0.0, min(1.0, phase))
    visible_cols = int(len(lines[0]) * reveal)
    left_pad = 2
    pad = " " * left_pad
    reset = "\x1b[0m"
    h = len(lines) + 1
    w = len(lines[0]) + 1
    glyph: list[list[str]] = [[" " for _ in range(w)] for _ in range(h)]
    color: list[list[tuple[int, int, int] | None]] = [[None for _ in range(w)] for _ in range(h)]

    # Primary glyph.
    for r, row in enumerate(lines):
        for c, ch in enumerate(row):
            if c >= visible_cols or ch == " ":
                continue
            glyph[r][c] = fill_char
            color[r][c] = _wordmark_rgb(phase, c)

    # Optional dotted shadow pass (disabled by default to avoid noisy glyph artifacts).
    if enable_shadow:
        for r, row in enumerate(lines):
            for c, ch in enumerate(row):
                if c >= visible_cols or ch == " ":
                    continue
                rr = r + 1
                cc = c + 1
                # Keep shadow off the bottom-most text row to avoid heavy base thickness.
                if r >= len(lines) - 1:
                    continue
                if rr < h and cc < w and glyph[rr][cc] == " " and ((r + c) % 4 == 0):
                    glyph[rr][cc] = shadow_char
                    color[rr][cc] = _shadow_rgb(phase, c)

    chunks: list[str] = []
    for r in range(h):
        out = [pad]
        last_code = ""
        for c in range(w):
            ch = glyph[r][c]
            rgb = color[r][c]
            if ch == " " or rgb is None:
                if last_code:
                    out.append(reset)
                    last_code = ""
                out.append(" ")
                continue

            if truecolor:
                code = f"\x1b[1;38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"
            else:
                code = "\x1b[1;95m" if ch == shadow_char else "\x1b[1;96m"

            if code != last_code:
                out.append(code)
                last_code = code
            out.append(ch)

        if last_code:
            out.append(reset)
        chunks.append("".join(out))
    return "\n".join(chunks)


def _build_wordmark_frames(width: int, frame_count: int, truecolor: bool, unicode_blocks: bool) -> tuple[list[str], int]:
    if frame_count <= 0:
        return [], 0
    frames = []
    for i in range(frame_count):
        phase = i / max(frame_count - 1, 1)
        frames.append(_wordmark_ansi_frame(phase=phase, width=width, truecolor=truecolor, unicode_blocks=unicode_blocks))
    return frames, len(_PIXEL_WORDMARK) + 1


def _wordmark_group(phase: float, width: int) -> Group:
    compact = width < 94
    items: list[Text] = []
    if compact:
        items.append(gradient_text("DEEPR", hue_offset=phase * 0.2))
    else:
        items.extend(_hero_lines(phase, mode="full", width=width))
    return Group(*items)


def _build_panel(version: str, phase: float = 0.0, mode: str = "static", width: int = 100) -> Panel:
    compact = width < 94
    staged = mode == "full"

    title = f"[bold cyan]v{version}[/bold cyan]"
    content_items: list[Text] = []

    if compact:
        content_items.append(gradient_text("DEEPR", hue_offset=phase * 0.12))
    else:
        content_items.extend(_hero_lines(phase, mode=mode, width=width))
        content_items.append(Text(f"CLI Version {version}", style="bold white"))

    # Full intro: animate only the DEEPR wordmark first, then reveal everything else.
    if staged and phase < 0.98:
        spinner = "|/-\\"[int(phase * 32) % 4]
        content_items.append(Text(f"{spinner} Starting interactive menu...", style="bold magenta"))
        content = Group(*content_items)
        return Panel(
            content,
            title=title,
            border_style="cyan",
            padding=(0, 2),
            expand=False,
        )
    content_items.append(Text("[ready] Interactive menu", style="bold green"))

    content = Group(*content_items)

    return Panel(
        content,
        title=title,
        border_style="cyan",
        padding=(0, 2),
        expand=False,
    )


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
        console.print()
        console.print(_build_panel(version=version, mode="static", width=width))
        console.print()
    else:
        render_mode = plan.mode if _supports_full_banner(console, width) else "light"
        duration = _duration_for_mode(render_mode)
        policy = resolve_animation_policy(console)
        fps = _fps_for_banner(policy.fps)
        frame_delay = 1.0 / fps
        frames = max(1, int(duration * fps))
        renderer = _banner_renderer_mode()

        try:
            if render_mode in {"full", "light"}:
                truecolor = _supports_truecolor(console)
                unicode_blocks = _supports_unicode_blocks(console)
                pre_rendered, line_count = _build_wordmark_frames(
                    width=width,
                    frame_count=frames,
                    truecolor=truecolor,
                    unicode_blocks=unicode_blocks,
                )
                _play_ansi_frames(
                    console,
                    pre_rendered,
                    line_count=line_count,
                    frame_delay=frame_delay,
                    wipe_at_end=False,
                    end_hold_seconds=_banner_end_hold_seconds(),
                )
                if plan.mark_seen:
                    _mark_seen(state_dir)
                return

            use_ansi = renderer == "ansi" or (
                renderer == "auto" and bool(getattr(console, "is_terminal", False)) and not bool(getattr(console, "legacy_windows", False))
            )
            if use_ansi:
                pre_rendered: list[str] = []
                line_count = 0
                for frame in range(frames):
                    phase = frame / max(frames - 1, 1)
                    panel = _build_panel(version=version, phase=phase, mode=render_mode, width=width)
                    rendered, lc = _render_panel_to_ansi(console, panel)
                    pre_rendered.append(rendered)
                    line_count = max(line_count, lc)
                _play_ansi_frames(console, pre_rendered, line_count=line_count, frame_delay=frame_delay)
                console.print()
            else:
                console.print()
                with Live(
                    _build_panel(version=version, phase=0.0, mode=render_mode, width=width),
                    console=console,
                    auto_refresh=False,
                    transient=True,
                    refresh_per_second=fps,
                ) as live:
                    for frame in range(frames):
                        phase = frame / max(frames - 1, 1)
                        live.update(_build_panel(version=version, phase=phase, mode=render_mode, width=width), refresh=True)
                        _precise_sleep(time.perf_counter() + frame_delay)

                console.print(_build_panel(version=version, phase=1.0, mode=render_mode, width=width))
                console.print()
        except Exception:
            # Last-resort fallback for unexpected terminal behavior.
            console.print()
            console.print(_build_panel(version=version, mode="static", width=width))
            console.print()

    if plan.mark_seen:
        _mark_seen(state_dir)
