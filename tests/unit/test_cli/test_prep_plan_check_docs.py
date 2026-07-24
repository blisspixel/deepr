"""Regression test for `deepr prep plan --check-docs`.

The command called `DocReviewer.generate_enhanced_plan_context`, a method that
does not exist, so `--check-docs` raised AttributeError before it could plan. The
planner context is now built inline from the review dict. Both collaborators are
faked here so the path runs without any live model call.
"""

from typing import Any

import pytest
from click.testing import CliRunner

from deepr.cli.commands.prep import plan


class _FakeReviewer:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def review_docs(self, scenario: str, context: str | None = None, **_kwargs: Any) -> dict[str, Any]:
        return {
            "sufficient": [{"name": "auth.md"}],
            "needs_update": [{"name": "api.md", "what_to_update": "add rate limits"}],
            "gaps": ["billing edge cases"],
        }


class _FakePlanner:
    """Records the context it is handed so the test can prove it was built."""

    received_context: str | None = None

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def plan_research(self, *, scenario: str, max_tasks: int, context: str | None) -> list[dict[str, Any]]:
        _FakePlanner.received_context = context
        return [{"title": "Investigate billing edge cases", "prompt": "Research billing edge cases.", "phase": 1}]


def test_plan_check_docs_builds_context_without_missing_method(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("deepr.services.doc_reviewer.DocReviewer", _FakeReviewer)
    monkeypatch.setattr("deepr.services.research_planner.ResearchPlanner", _FakePlanner)

    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(plan, ["Design a billing system", "--check-docs", "--topics", "1"])

    assert result.exit_code == 0, result.output
    if result.exception is not None:
        assert isinstance(result.exception, SystemExit)
    # The doc analysis must reach the planner as context; an AttributeError here
    # would mean the missing-method regression came back.
    assert _FakePlanner.received_context is not None
    assert "Existing documentation analysis" in _FakePlanner.received_context
    assert "billing edge cases" in _FakePlanner.received_context
