"""Tests for interactive helper utilities."""

from deepr.cli.commands.interactive import _resolve_maybe_awaitable, _run_direct_command


async def _answer() -> int:
    return 42


def test_resolve_maybe_awaitable_with_plain_value():
    assert _resolve_maybe_awaitable(7) == 7


def test_resolve_maybe_awaitable_with_coroutine():
    assert _resolve_maybe_awaitable(_answer()) == 42


def test_run_direct_command_handles_interactive_alias():
    assert _run_direct_command("interactive") is True
    assert _run_direct_command("deepr interactive") is True
