"""The one shared sync-to-async bridge for Deepr's interface layers.

CLI commands, the web dashboard, and the REST API all need to drive async
kernel coroutines from a synchronous context (Click handlers, Flask request
handlers). This module is the single home for that helper so there is one
implementation, not a per-surface copy that drifts (Phase Q1.3 - "one way to
do each thing").

The helper lives in ``utils`` (a low layer) rather than in any one interface,
so ``cli``, ``web``, and ``api`` can all import it without crossing into each
other. ``deepr.cli.async_runner`` re-exports it for back-compat.
"""

import asyncio
from typing import Any


def run_async_command(coro: Any, runner: Any = None) -> Any:
    """Run a coroutine to completion from a synchronous caller.

    Args:
        coro: The coroutine to run.
        runner: The function that actually drives the coroutine (defaults to
            ``asyncio.run``). Tests sometimes pass or mock this to assert calls
            without spinning a real loop.

    Returns:
        Whatever the coroutine returns.

    A mocked ``runner`` may not consume the coroutine, which leaves it
    unawaited and emits noisy ``RuntimeWarning``s. Closing an unconsumed
    coroutine in ``finally`` is safe and preserves runtime behavior.
    """
    if runner is None:
        runner = asyncio.run

    try:
        return runner(coro)
    finally:
        if asyncio.iscoroutine(coro) and getattr(coro, "cr_frame", None) is not None:
            coro.close()
