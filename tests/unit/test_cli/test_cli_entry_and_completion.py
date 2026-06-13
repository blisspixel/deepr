"""Regression tests for the `deepr completion <shell>` command.

clig.dev: ship discoverable tab-completion. The script goes to stdout
(so `eval "$(deepr completion bash)"` works) and the install hint to
stderr (so redirection captures only the script).

The no-args TTY-routing behavior lives in test_main_entrypoint.py.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from deepr.cli.commands.completion import completion


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
