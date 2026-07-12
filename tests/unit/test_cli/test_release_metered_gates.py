"""Fail-closed regressions for legacy metered command surfaces."""

from __future__ import annotations

import json
from types import SimpleNamespace

from click.testing import CliRunner

from deepr.cli.commands.eval import eval_calibrate
from deepr.cli.commands.prep import prep
from deepr.cli.commands.providers import benchmark
from deepr.cli.commands.run import METERED_PROVIDER_FALLBACK_ENABLED, run
from deepr.cli.commands.semantic.artifacts import agentic, make
from deepr.cli.commands.semantic.experts import chat_with_expert
from deepr.cli.commands.semantic.research import check
from deepr.cli.commands.vector import vector


def test_calibrate_corpus_is_gated_while_graded_file_remains_free(monkeypatch, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "report.md").write_text("A report", encoding="utf-8")
    monkeypatch.setattr(
        "deepr.cli.commands.eval._load_corpus",
        lambda *_args: (_ for _ in ()).throw(AssertionError("paid corpus must not load")),
    )

    blocked = CliRunner().invoke(eval_calibrate, ["--corpus", str(corpus), "--yes", "--json"])

    assert blocked.exit_code == 1
    assert "temporarily disabled" in blocked.output.lower()
    assert "--from" in blocked.output

    graded = tmp_path / "graded.jsonl"
    graded.write_text(
        "\n".join(
            [
                '{"confidence": 0.9, "grounded": true}',
                '{"confidence": 0.2, "grounded": false}',
            ]
        ),
        encoding="utf-8",
    )
    free = CliRunner().invoke(eval_calibrate, ["--from", str(graded), "--json"])

    assert free.exit_code == 0, free.output
    assert json.loads(free.output)["sample_size"] == 2


def test_provider_live_benchmark_is_gated_while_history_remains_readable(monkeypatch):
    blocked = CliRunner().invoke(benchmark, ["--quick"])

    assert blocked.exit_code == 1
    assert "temporarily disabled" in blocked.output.lower()
    assert "--history" in blocked.output

    history = {
        "benchmarks": [],
        "summary": {
            "total_providers": 0,
            "healthy_providers": 0,
            "unhealthy_providers": 0,
            "total_requests": 0,
            "total_cost_usd": 0.0,
        },
    }
    monkeypatch.setattr(
        "deepr.cli.commands.providers.AutonomousProviderRouter",
        lambda: SimpleNamespace(get_benchmark_data=lambda: history),
    )
    free = CliRunner().invoke(benchmark, ["--history", "--json"])

    assert free.exit_code == 0, free.output
    assert json.loads(free.output) == history


def test_cross_provider_metered_fallback_is_disabled_by_default():
    assert METERED_PROVIDER_FALLBACK_ENABLED is False


def test_multi_call_research_entrypoints_are_gated():
    runner = CliRunner()

    prepared = runner.invoke(prep, ["execute"])
    project = runner.invoke(run, ["project", "bounded campaign"])
    team = runner.invoke(run, ["team", "bounded perspectives"])

    for result in (prepared, project, team):
        assert result.exit_code == 1
        assert "research_parent_budget_unavailable" in result.output
        assert "one durable parent reservation" in result.output


def test_unaccounted_metered_interfaces_are_gated_before_provider_construction(monkeypatch):
    monkeypatch.setattr(
        "deepr.providers.create_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider must not be constructed")),
    )
    runner = CliRunner()

    results = (
        runner.invoke(make, ["docs", "bounded docs"]),
        runner.invoke(make, ["strategy", "bounded strategy"]),
        runner.invoke(agentic, ["research", "bounded topic", "--goal", "bounded goal"]),
        runner.invoke(check, ["bounded claim"]),
    )

    for result in results:
        assert result.exit_code == 1
        assert "accounting_unavailable" in result.output or "parent_budget_unavailable" in result.output


def test_vector_create_is_gated_before_provider_construction(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("local evidence", encoding="utf-8")

    result = CliRunner().invoke(vector, ["create", "--name", "blocked", "--files", str(source)])

    assert result.exit_code == 1
    assert "upload, indexing, retention, retrieval, and cleanup costs" in result.output
    assert "local source packs" in result.output


def test_interactive_expert_chat_is_gated_before_session_construction(monkeypatch):
    monkeypatch.setattr(
        "deepr.experts.chat.start_chat_session",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("session must not be constructed")),
    )

    result = CliRunner().invoke(chat_with_expert, ["Security Analyst"])

    assert result.exit_code == 1
    assert "temporarily disabled" in result.output.lower()
    assert "expert consult" in result.output
