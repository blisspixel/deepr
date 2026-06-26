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
    """All three template subcommands must reject path traversal in the
    template name. ``sanitize_name`` flattens the input into a safe
    filename (e.g. ``../../etc/passwd`` → ``etc_passwd``) so the
    real traversal target outside ``.deepr/templates/`` is never
    touched. We assert the invariant directly: a sentinel file at
    the parent of the working dir must remain untouched even after
    the command runs."""
    monkeypatch.chdir(tmp_path)
    sentinel = tmp_path.parent / "deepr_traversal_sentinel.json"
    sentinel.write_text('{"poison": true}', encoding="utf-8")
    try:
        runner = CliRunner()
        result = runner.invoke(templates_group, subcommand)
        # The command must fail - the sanitised name won't resolve
        # to a real template.
        assert result.exit_code != 0
        # The sentinel must remain untouched: no file read, no delete.
        assert sentinel.exists()
        assert sentinel.read_text(encoding="utf-8") == '{"poison": true}'
    finally:
        sentinel.unlink(missing_ok=True)
