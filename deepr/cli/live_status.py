"""Live shimmer status line for CLI operations."""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.text import Text

from deepr.cli.effects import resolve_animation_policy, shimmer_text


class LiveShimmerStatus:
    """Animated single-line shimmer status renderer."""

    def __init__(self, console: Console, message: str, enabled: bool = True):
        self.console = console
        self.message = message
        self._policy = resolve_animation_policy(console)
        self._enabled = enabled and self._policy.enabled
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._phase = 0.0
        self._live: Optional[Live] = None

    def _render(self) -> Text:
        with self._lock:
            current = self.message
        if not self._enabled:
            return Text(current, style="dim")
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
        self._live.start()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        assert self._live is not None
        cycle_seconds = 3.2
        while not self._stop.wait(self._policy.frame_delay):
            self._phase = (self._phase + (self._policy.frame_delay / cycle_seconds)) % 1.0
            self._live.update(self._render(), refresh=True)

    def update(self, message: str) -> None:
        """Update current status message."""
        with self._lock:
            self.message = message
        if self._enabled and self._live is not None:
            self._live.update(self._render(), refresh=True)

    def stop(self) -> None:
        """Stop renderer and clean resources."""
        if not self._enabled:
            return
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        if self._live is not None:
            self._live.stop()


@contextmanager
def shimmer_status(
    message: str,
    *,
    console: Console,
    enabled: bool = True,
) -> Generator[LiveShimmerStatus, None, None]:
    """Context manager for a live shimmer status line."""
    status = LiveShimmerStatus(console, message, enabled=enabled)
    status.start()
    try:
        yield status
    finally:
        status.stop()
