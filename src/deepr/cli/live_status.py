"""Live shimmer status line for CLI operations."""

from __future__ import annotations

import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import replace

from rich.console import Console, RenderableType
from rich.live import Live
from rich.text import Text

from deepr.cli.effects import resolve_animation_policy, shimmer_text, synchronized_output


class LiveShimmerStatus:
    """Animated single-line shimmer status renderer."""

    def __init__(
        self,
        console: Console,
        message: str,
        enabled: bool = True,
        *,
        renderer: Callable[[str, float], RenderableType] | None = None,
        max_fps: int | None = None,
    ):
        self.console = console
        self.message = message
        self._policy = resolve_animation_policy(console)
        if self._policy.enabled and max_fps is not None:
            fps = max(1, min(self._policy.fps, max_fps))
            self._policy = replace(self._policy, fps=fps, frame_delay=1.0 / fps)
        self._renderer = renderer
        self._enabled = enabled and self._policy.enabled
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._phase = 0.0
        self._live: Live | None = None

    def _render(self) -> RenderableType:
        with self._lock:
            current = self.message
        if self._renderer is not None:
            return self._renderer(current, self._phase)
        if not self._enabled:
            return Text(current, style="muted")
        return shimmer_text(
            current,
            phase=self._phase,
            base_color=self._policy.base_color,
            highlight_color=self._policy.highlight_color,
            sweep_width=self._policy.sweep_width,
        )

    def start(self) -> None:
        """Start the live shimmer renderer."""
        if not self._enabled:
            return
        self._live = Live(
            self._render(),
            console=self.console,
            auto_refresh=False,
            transient=True,
            refresh_per_second=max(self._policy.fps, 1),
        )
        with synchronized_output(self.console):
            self._live.start(refresh=self._renderer is not None)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        if self._live is None:
            return
        cycle_seconds = 3.2
        while not self._stop.wait(self._policy.frame_delay):
            self._phase = (self._phase + (self._policy.frame_delay / cycle_seconds)) % 1.0
            with synchronized_output(self.console):
                self._live.update(self._render(), refresh=True)

    def update(self, message: str) -> None:
        """Update current status message."""
        with self._lock:
            self.message = message
        if self._enabled and self._live is not None and self._renderer is None:
            with synchronized_output(self.console):
                self._live.update(self._render(), refresh=True)

    def stop(self) -> None:
        """Stop renderer and clean resources."""
        if not self._enabled:
            return
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        if self._live is not None:
            with synchronized_output(self.console):
                self._live.stop()


@contextmanager
def shimmer_status(
    message: str,
    *,
    console: Console,
    enabled: bool = True,
    renderer: Callable[[str, float], RenderableType] | None = None,
    max_fps: int | None = None,
) -> Generator[LiveShimmerStatus, None, None]:
    """Context manager for a live shimmer status line."""
    status = LiveShimmerStatus(console, message, enabled=enabled, renderer=renderer, max_fps=max_fps)
    status.start()
    try:
        yield status
    finally:
        status.stop()
