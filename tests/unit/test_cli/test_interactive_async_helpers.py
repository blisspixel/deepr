"""Tests for interactive async helper utilities."""

from deepr.cli.commands.interactive import _resolve_maybe_awaitable


async def _answer() -> int:
    return 42


def test_resolve_maybe_awaitable_with_plain_value():
    assert _resolve_maybe_awaitable(7) == 7


def test_resolve_maybe_awaitable_with_coroutine():
    assert _resolve_maybe_awaitable(_answer()) == 42
