from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

from click.testing import CliRunner

from deepr.cli.main import cli


def test_investigate_help_exposes_durable_lifecycle() -> None:
    result = CliRunner().invoke(cli, ["expert", "investigate", "--help"])

    assert result.exit_code == 0
    for command in ("plan", "run", "status", "inspect", "pause", "resume", "cancel"):
        assert command in result.output


def test_plan_passes_explicit_inputs_to_zero_call_builder(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    payload = {
        "schema_version": "deepr-investigation-plan-v1",
        "kind": "deepr.expert.investigation_plan",
        "run_id": "inv_cli_test",
        "plan_sha256": "a" * 64,
    }

    def build(**kwargs):
        captured.update(kwargs)
        return payload

    monkeypatch.setattr("deepr.cli.commands.semantic.expert_investigate.build_investigation_plan", build)
    out = tmp_path / "plan.json"
    result = CliRunner().invoke(
        cli,
        [
            "expert",
            "investigate",
            "plan",
            "Question",
            "--expert",
            "Temporal Knowledge Graphs",
            "--expert",
            "Model Context Protocol",
            "--text",
            "Constraint",
            "--url",
            "https://example.com/spec",
            "--local-model",
            "qwen:32b",
            "--review-model",
            "strong:32b",
            "--context-window-tokens",
            "24576",
            "--review-context-window-tokens",
            "16384",
            "--protocol",
            "deep",
            "--learning",
            "stage",
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == payload
    assert json.loads(out.read_text(encoding="utf-8")) == payload
    assert captured["question"] == "Question"
    assert captured["expert_names"] == ("Temporal Knowledge Graphs", "Model Context Protocol")
    assert captured["inline_texts"] == ("Constraint",)
    assert captured["urls"] == ("https://example.com/spec",)
    assert captured["local_model"] == "qwen:32b"
    assert captured["review_model"] == "strong:32b"
    assert captured["context_window_tokens"] == 24_576
    assert captured["review_context_window_tokens"] == 16_384
    assert captured["protocol"] == "deep"
    assert captured["learning"] == "stage"


def test_plan_rejects_nonzero_local_budget_before_build(monkeypatch) -> None:
    build = Mock()
    monkeypatch.setattr("deepr.cli.commands.semantic.expert_investigate.build_investigation_plan", build)

    result = CliRunner().invoke(
        cli,
        [
            "expert",
            "investigate",
            "plan",
            "Question",
            "--expert",
            "Expert",
            "--budget-usd",
            "1",
        ],
    )

    assert result.exit_code == 2
    assert "support local capacity with --budget-usd 0 only" in result.output
    build.assert_not_called()


def test_run_requires_confirmation_before_backend_construction(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text("{}", encoding="utf-8")
    plan = {
        "run_id": "inv_cli_test",
        "bounds": {"max_generation_calls": 11, "max_page_fetches": 24},
    }
    execute = Mock()
    monkeypatch.setattr("deepr.cli.commands.semantic.expert_investigate.validate_plan", lambda payload: plan)
    monkeypatch.setattr("deepr.cli.commands.semantic.expert_investigate._execute_run", execute)

    result = CliRunner().invoke(cli, ["expert", "investigate", "run", str(path)])

    assert result.exit_code == 2
    assert "requires interactive confirmation or --yes" in result.output
    execute.assert_not_called()


def test_inspect_keeps_unreviewed_and_blocked_learning_labels_truthful(monkeypatch) -> None:
    payload = {
        "status": {
            "run_id": "inv_cli_test",
            "state": "completed",
            "phase": "complete",
            "usage": {
                "generation_calls": 4,
                "search_queries": 2,
                "page_fetches": 3,
                "cost_usd": 0.0,
            },
            "artifact_count": 8,
            "run_dir": "data/reports/investigations/inv_cli_test",
            "errors": [],
        },
        "plan": {},
        "result": {
            "semantic_review_status": "unreviewed",
            "answer": "A proposal that still needs semantic evaluation.",
            "expert_contributions": [],
        },
        "check": {},
        "learning_manifest": {
            "summary": {"automatic_verifier_accepted_count": 0},
            "entries": [
                {
                    "expert_name": "Temporal Knowledge Graphs",
                    "status": "blocked",
                    "ready_write_count": 0,
                    "graph_commit_envelope_artifact": "artifacts/learning/blocked.json",
                }
            ],
        },
        "positions": {},
        "events": [],
    }
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_investigate._inspection_payload",
        lambda store, run_id: payload,
    )

    result = CliRunner().invoke(cli, ["expert", "investigate", "inspect", "inv_cli_test"])

    assert result.exit_code == 0, result.output
    assert "Semantic quality: unreviewed" in result.output
    assert "Human reviewed: 0" in result.output
    assert "No applicable graph writes passed the automatic verifier." in result.output
    assert "Preview apply:" not in result.output
