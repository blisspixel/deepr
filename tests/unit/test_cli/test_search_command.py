"""Tests for the prior-research search CLI."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.cli.commands import search as search_mod
from deepr.cli.main import cli
from deepr.services.context_index import PaidSemanticOperationError


def test_search_bare_query_dispatches_to_query_command(monkeypatch):
    """`deepr search "term"` is shorthand for `deepr search query "term"`."""
    seen: dict[str, object] = {}

    async def fake_search_query(
        query: str,
        top: int,
        threshold: float,
        keyword_only: bool,
        json_output: bool,
        *,
        semantic_backend: str | None = None,
        max_total_cost: float | None = None,
    ) -> None:
        seen.update(
            {
                "query": query,
                "top": top,
                "threshold": threshold,
                "keyword_only": keyword_only,
                "json_output": json_output,
                "semantic_backend": semantic_backend,
                "max_total_cost": max_total_cost,
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
        "semantic_backend": None,
        "max_total_cost": None,
    }


def test_search_query_defaults_to_local_keyword(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_search_query(*_args, **kwargs) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(search_mod, "_search_query", fake_search_query)

    result = CliRunner().invoke(cli, ["search", "query", "agent memory"])

    assert result.exit_code == 0, result.output
    assert seen == {"semantic_backend": None, "max_total_cost": None}


def test_search_query_requires_explicit_aggregate_ceiling(monkeypatch):
    monkeypatch.setattr(
        search_mod,
        "_search_query",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not dispatch")),
    )

    result = CliRunner().invoke(
        cli,
        ["search", "query", "agent memory", "--semantic-backend", "openai", "--confirm-metered-cost"],
    )

    assert result.exit_code != 0
    assert "finite positive --max-total-cost" in result.output


def test_search_query_requires_explicit_cost_confirmation(monkeypatch):
    monkeypatch.setattr(
        search_mod,
        "_search_query",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not dispatch")),
    )

    result = CliRunner().invoke(
        cli,
        ["search", "query", "agent memory", "--semantic-backend", "openai", "--max-total-cost", "1"],
    )

    assert result.exit_code != 0
    assert "requires --confirm-metered-cost" in result.output


def test_search_query_explicit_semantic_consent_is_forwarded(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_search_query(*_args, **kwargs) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(search_mod, "_search_query", fake_search_query)

    result = CliRunner().invoke(
        cli,
        [
            "search",
            "query",
            "agent memory",
            "--semantic-backend",
            "openai",
            "--max-total-cost",
            "1",
            "--confirm-metered-cost",
        ],
    )

    assert result.exit_code == 0, result.output
    assert seen == {"semantic_backend": "openai", "max_total_cost": 1.0}


def test_search_query_rejects_ceiling_below_embedding_envelope(monkeypatch):
    monkeypatch.setattr(
        search_mod,
        "_search_query",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not dispatch")),
    )

    result = CliRunner().invoke(
        cli,
        [
            "search",
            "query",
            "agent memory",
            "--semantic-backend",
            "openai",
            "--max-total-cost",
            "0.000000000001",
            "--confirm-metered-cost",
        ],
    )

    assert result.exit_code != 0
    assert "above --max-total-cost" in result.output


def test_search_index_defaults_to_local_keyword(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_index(force: bool, **kwargs) -> None:
        seen.update({"force": force, **kwargs})

    monkeypatch.setattr(search_mod, "_index_reports", fake_index)

    result = CliRunner().invoke(cli, ["search", "index"])

    assert result.exit_code == 0, result.output
    assert seen == {"force": False, "semantic_backend": None, "max_total_cost": None}


def test_search_index_requires_and_forwards_metered_consent(monkeypatch):
    seen: dict[str, object] = {}

    async def fake_index(force: bool, **kwargs) -> None:
        seen.update({"force": force, **kwargs})

    monkeypatch.setattr(search_mod, "_index_reports", fake_index)

    blocked = CliRunner().invoke(
        cli,
        ["search", "index", "--semantic-backend", "openai", "--max-total-cost", "0.25"],
    )
    allowed = CliRunner().invoke(
        cli,
        [
            "search",
            "index",
            "--force",
            "--semantic-backend",
            "openai",
            "--max-total-cost",
            "0.25",
            "--confirm-metered-cost",
        ],
    )

    assert blocked.exit_code != 0
    assert "requires --confirm-metered-cost" in blocked.output
    assert allowed.exit_code == 0, allowed.output
    assert seen == {"force": True, "semantic_backend": "openai", "max_total_cost": 0.25}


def test_paid_semantic_query_failure_is_not_reported_as_empty_success():
    index = MagicMock()
    index.get_stats.return_value = {"indexed_reports": 1}
    index.search = AsyncMock(side_effect=PaidSemanticOperationError("Paid semantic search failed after accounting."))

    with patch("deepr.services.context_index.ContextIndex", return_value=index):
        result = CliRunner().invoke(
            cli,
            [
                "search",
                "query",
                "agent memory",
                "--semantic-backend",
                "openai",
                "--max-total-cost",
                "1",
                "--confirm-metered-cost",
            ],
        )

    assert result.exit_code != 0
    assert "Paid semantic search failed after accounting" in result.output
    assert "No matching reports found" not in result.output


def test_paid_semantic_index_failure_is_not_reported_as_success():
    index = MagicMock()
    index.index_reports = AsyncMock(
        side_effect=PaidSemanticOperationError("Paid semantic indexing stopped at its aggregate ceiling.")
    )

    with patch("deepr.services.context_index.ContextIndex", return_value=index):
        result = CliRunner().invoke(
            cli,
            [
                "search",
                "index",
                "--semantic-backend",
                "openai",
                "--max-total-cost",
                "1",
                "--confirm-metered-cost",
            ],
        )

    assert result.exit_code != 0
    assert "Paid semantic indexing stopped at its aggregate ceiling" in result.output
    assert "Indexed " not in result.output
