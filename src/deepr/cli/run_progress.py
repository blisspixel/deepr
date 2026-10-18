"""Periodic stderr heartbeats for long interactive local runs.

A healthy multi-minute local generation must be distinguishable from a stuck
one without inspecting processes or sockets. This reports the command-level
phase, elapsed time, durable trace reference and cancellation state on stderr,
so stdout and JSON output stay unchanged. It observes; it never shortens a
timeout, retries, or changes execution.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TextIO

DEFAULT_INTERVAL_SECONDS = 30.0


def format_elapsed(seconds: float) -> str:
    """Render elapsed seconds as ``45s``, ``2m 05s`` or ``1h 02m``."""
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


class RunProgress:
    """Mutable phase and trace shared with the heartbeat thread."""

    def __init__(self, label: str, phase: str, trace: str | None, clock: Callable[[], float]) -> None:
        self.label = label
        self._phase = phase
        self._trace = trace
        self._clock = clock
        self._started = clock()
        self._lock = threading.Lock()

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self._phase = phase

    def set_trace(self, trace: str) -> None:
        with self._lock:
            self._trace = trace

    def elapsed(self) -> float:
        return self._clock() - self._started

    def _suffix(self) -> str:
        with self._lock:
            trace = self._trace
        return f"; trace {trace}" if trace else ""

    def running_line(self) -> str:
        with self._lock:
            phase = self._phase
        return f"{self.label}: {phase}, {format_elapsed(self.elapsed())} elapsed{self._suffix()}. Ctrl+C cancels."

    def ending_line(self, outcome: str) -> str:
        return f"{self.label}: {outcome} after {format_elapsed(self.elapsed())}{self._suffix()}."


def _write(stream: TextIO | None, line: str) -> None:
    # Resolve stderr at write time: Rich Live swaps sys.stderr for a proxy that
    # prints above the active companion display.
    target = stream if stream is not None else sys.stderr
    try:
        target.write(line + "\n")
        target.flush()
    except (OSError, ValueError):
        pass


@contextmanager
def run_progress(
    label: str,
    *,
    phase: str = "starting",
    trace: str | None = None,
    enabled: bool = True,
    interval: float | None = None,
    stream: TextIO | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[RunProgress]:
    """Report a long run every ``interval`` seconds until it ends.

    Runs shorter than one interval print nothing, so fast refusals keep their
    own message. A run that reported progress ends with a finished or stopped
    line; interruption always says how long the run took before cancelling.
    """
    progress = RunProgress(label, phase, trace, clock)
    period = DEFAULT_INTERVAL_SECONDS if interval is None else interval
    if not enabled:
        yield progress
        return
    stop = threading.Event()
    reported = threading.Event()

    def beat() -> None:
        while not stop.wait(period):
            _write(stream, progress.running_line())
            reported.set()

    thread = threading.Thread(target=beat, name=f"deepr-progress-{label}", daemon=True)
    thread.start()
    outcome = "finished"
    try:
        yield progress
    except KeyboardInterrupt:
        outcome = "cancelled"
        raise
    except BaseException:
        outcome = "stopped"
        raise
    finally:
        stop.set()
        thread.join(timeout=1.0)
        if outcome == "cancelled" or reported.is_set():
            _write(stream, progress.ending_line(outcome))
