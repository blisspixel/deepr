"""Regression tests for CLI entry behavior and shell completion.

Covers two mid-2026 CLI best-practice refinements (clig.dev):
- no-args on a non-TTY stdin prints help and exits cleanly, instead of
  launching interactive mode that a script/CI/agent cannot drive;
- a discoverable `deepr completion <shell>` emits a completion script to
  stdout (the install hint goes to stderr so redirection stays clean).
"""

from __future__ import annotations

import io

import pytest
from click.testing import CliRunner

from deepr.cli.commands.completion import completion
from deepr.cli.main import cli


class _FakeStdin(io.StringIO):
    def __init__(self, tty: bool):
        super().__init__("")
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class TestNoArgsEntry:
    def _run_main(self, monkeypatch, *, tty: bool) -> list[str]:
        """Invoke main() with no CLI args and a stdin of the given TTY-ness."""
        calls: list[str] = []

        monkeypatch.setattr("sys.argv", ["deepr"])
        monkeypatch.setattr("sys.stdin", _FakeStdin(tty=tty))

        # Stub cli.main so we observe which args the entrypoint dispatches
        # without actually running interactive mode or the help pager.
        def fake_cli_main(args=None, **kwargs):
            calls.append(args[0] if args else "")

        monkeypatch.setattr(cli, "main", fake_cli_main)

        from deepr.cli.main import main

        main()
        return calls

    def test_non_tty_no_args_shows_help_not_interactive(self, monkeypatch):
        assert self._run_main(monkeypatch, tty=False) == ["--help"]

    def test_tty_no_args_launches_interactive(self, monkeypatch):
        assert self._run_main(monkeypatch, tty=True) == ["interactive"]


class TestCompletion:
    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_emits_script_for_each_shell(self, shell):
        result = CliRunner().invoke(completion, [shell])
        assert result.exit_code == 0
        assert result.stdout.strip()  # a non-empty completion script
        # Install hint is guidance, not script: must be on stderr only.
        assert "_DEEPR_COMPLETE" not in result.stderr
        assert "To install" in result.stderr

    def test_rejects_unknown_shell(self):
        result = CliRunner().invoke(completion, ["powershell"])
        assert result.exit_code != 0
