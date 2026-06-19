"""Tests for the prior-research search CLI."""

import sys
from pathlib import Path

from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.cli.commands import search as search_mod
from deepr.cli.main import cli


def test_search_bare_query_dispatches_to_query_command(monkeypatch):
    """`deepr search "term"` is shorthand for `deepr search query "term"`."""
    seen: dict[str, object] = {}

    async def fake_search_query(query: str, top: int, threshold: float, keyword_only: bool, json_output: bool) -> None:
        seen.update(
            {
                "query": query,
                "top": top,
                "threshold": threshold,
                "keyword_only": keyword_only,
                "json_output": json_output,
            }
        )

    monkeypatch.setattr(search_mod, "_search_query", fake_search_query)

    result = CliRunner().invoke(
        cli,
        ["search", "agent memory", "--top", "7", "--threshold", "0.4", "--keyword-only", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert seen == {
        "query": "agent memory",
        "top": 7,
        "threshold": 0.4,
        "keyword_only": True,
        "json_output": True,
    }
