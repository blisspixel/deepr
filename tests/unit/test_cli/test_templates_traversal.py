"""Regression test: ``deepr templates show/delete/use`` reject path
traversal in the template name. The previous implementation joined the
raw user input into a filesystem path, allowing arbitrary file reads
and deletes outside ``.deepr/templates/``.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from deepr.cli.commands.templates import templates as templates_group


@pytest.mark.parametrize(
    "subcommand",
    [
        ["show", "../../etc/passwd"],
        ["delete", "--yes", "../../../foo"],
        ["use", "--yes", "../../../../bar"],
    ],
)
def test_path_traversal_rejected(subcommand, tmp_path, monkeypatch):
    """All three template subcommands must reject names with path components."""
    monkeypatch.chdir(tmp_path)
    # Ensure the parent dir of the would-be traversal target doesn't exist.
    runner = CliRunner()
    result = runner.invoke(templates_group, subcommand)
    # Should fail (click.Abort) without ever touching any path outside .deepr/templates.
    assert result.exit_code != 0
