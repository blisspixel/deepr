"""Helpers for safely running async CLI command coroutines."""

import asyncio
from typing import Any


def run_async_command(coro, runner=None) -> Any:
    """Run a coroutine and close it if a mocked runner doesn't consume it.

    In unit tests, `asyncio.run` is often mocked to assert calls. That can
    leave created coroutine objects unawaited, causing noisy RuntimeWarnings.
    Closing an unconsumed coroutine is safe and preserves runtime behavior.
    """
    if runner is None:
        runner = asyncio.run

    try:
        return runner(coro)
    finally:
        if asyncio.iscoroutine(coro) and getattr(coro, "cr_frame", None) is not None:
            coro.close()
