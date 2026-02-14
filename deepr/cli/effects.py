"""Cross-platform CLI visual effects utilities.

Provides policy-driven animation settings and Rich-native shimmer/gradient
renderables with safe fallbacks for low-capability terminals.
"""

from __future__ import annotations

import colorsys
import os
import sys
import time
from dataclasses import dataclass

from rich.console import Console
from rich.text import Text


@dataclass(frozen=True)
class AnimationPolicy:
    """Resolved animation policy for the current terminal/runtime."""

    mode: str  # off | light | full
    enabled: bool
    fps: int
    frame_delay: float
    base_color: str
    highlight_color: str
    sweep_width: float


def get_branding_mode() -> str:
    """Get requested branding mode from environment.

    DEEPR_BRANDING supports: off, on, auto.
    Defaults to off for conservative cross-platform behavior.
    """
    raw = os.getenv("DEEPR_BRANDING", "off").strip().lower()
    if raw in {"off", "on", "auto"}:
        return raw
    return "off"


def get_animation_mode() -> str:
    """Get requested animation mode from environment.

    DEEPR_ANIMATIONS supports: off, light, full.
    """
    raw = os.getenv("DEEPR_ANIMATIONS", "light").strip().lower()
    if raw in {"off", "light", "full"}:
        return raw
    return "light"


def resolve_animation_policy(console: Console) -> AnimationPolicy:
    """Resolve a cross-platform animation policy for the given console."""
    requested = get_animation_mode()
    is_windows = sys.platform.startswith("win")
    in_ci = os.getenv("CI", "").lower() in {"1", "true", "yes"}
    no_color = os.getenv("NO_COLOR") is not None
    dumb = bool(getattr(console, "is_dumb_terminal", False))
    interactive = bool(getattr(console, "is_terminal", False))

    if requested == "off" or in_ci or no_color or dumb or not interactive:
        return AnimationPolicy(
            mode="off",
            enabled=False,
            fps=0,
            frame_delay=0.0,
            base_color="#6a6a6a",
            highlight_color="#cfcfff",
            sweep_width=0.0,
        )

    if requested == "full":
        fps = 8 if is_windows else 12
        sweep_width = 0.28 if is_windows else 0.35
    else:
        fps = 6 if is_windows else 8
        sweep_width = 0.22 if is_windows else 0.28

    return AnimationPolicy(
        mode=requested,
        enabled=True,
        fps=fps,
        frame_delay=1.0 / fps,
        base_color="#606060",
        highlight_color="#d0d0ff",
        sweep_width=sweep_width,
    )


def branding_enabled(console: Console) -> bool:
    """Determine whether gradient branding should be rendered."""
    mode = get_branding_mode()
    if mode == "off":
        return False

    policy = resolve_animation_policy(console)
    if not policy.enabled:
        return False

    if mode == "on":
        return True

    # auto: enable only for full animation tier
    return policy.mode == "full"


def shimmer_text(
    text: str,
    *,
    phase: float | None = None,
    base_color: str = "#606060",
    highlight_color: str = "#d0d0ff",
    sweep_width: float = 0.28,
    power: float = 2.2,
) -> Text:
    """Render text with a monochrome sweep highlight."""
    if not text:
        return Text("")

    now_phase = ((time.time() if phase is None else phase) % 1.0 + 1.0) % 1.0
    result = Text()
    n = max(len(text) - 1, 1)

    for i, ch in enumerate(text):
        pos = i / n
        dist = abs(pos - now_phase)
        intensity = max(0.0, 1.0 - (dist / max(sweep_width, 1e-6)))
        intensity = intensity**power
        color = highlight_color if intensity > 0.2 else base_color
        result.append(ch, style=color)

    return result


def gradient_text(
    text: str,
    *,
    start_hue: float = 200 / 360,
    end_hue: float = 320 / 360,
    saturation: float = 0.85,
    value: float = 0.92,
    hue_offset: float = 0.0,
) -> Text:
    """Render text with an HSV gradient suitable for branding headers."""
    if not text:
        return Text("")
    if len(text) == 1:
        return Text(text, style="rgb(235,235,255)")

    result = Text()
    span = len(text) - 1
    for i, ch in enumerate(text):
        hue = (start_hue + (end_hue - start_hue) * (i / span) + hue_offset) % 1.0
        r, g, b = (int(c * 255) for c in colorsys.hsv_to_rgb(hue, saturation, value))
        result.append(ch, style=f"rgb({r},{g},{b})")
    return result
