"""CLI coverage for the frozen deliberation evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.evals.deliberation import DeliberationEvalOutcome, DeliberationEvalReport


def test_eval_deliberation_outputs_zero_cost_json_report() -> None:
    result = CliRunner().invoke(cli, ["eval", "deliberation", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["schema_version"] == "deepr-deliberation-eval-v1"
    assert data["kind"] == "deepr.eval.deliberation"
    assert data["cost_usd"] == 0.0
    assert data["failed_cases"] == 0
    assert data["semantic_review_status"] == "unreviewed"


def test_eval_deliberation_save_writes_json_artifact() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["eval", "deliberation", "--json", "--save"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        path = Path(data["saved_to"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert path.name.startswith("deliberation_eval_")
        assert saved["schema_version"] == "deepr-deliberation-eval-v1"
        assert saved["failed_cases"] == 0


def test_eval_deliberation_outputs_text_summary() -> None:
    result = CliRunner().invoke(cli, ["eval", "deliberation"])

    assert result.exit_code == 0
    assert "Bounded deliberation fixture eval" in result.output
    assert "Semantic review: unreviewed" in result.output
    assert "Score: 100.0%" in result.output


def test_eval_deliberation_fails_on_structural_regression_by_default() -> None:
    report = DeliberationEvalReport(outcomes=(DeliberationEvalOutcome("fixture_failure", "fixture", False),))

    with patch("deepr.evals.deliberation.run_deliberation_eval", return_value=report):
        result = CliRunner().invoke(cli, ["eval", "deliberation"])

    assert result.exit_code != 0
    assert "1 deliberation regression(s) failed" in result.output


def test_eval_deliberation_can_report_without_failing_exit() -> None:
    report = DeliberationEvalReport(outcomes=(DeliberationEvalOutcome("fixture_failure", "fixture", False),))

    with patch("deepr.evals.deliberation.run_deliberation_eval", return_value=report):
        result = CliRunner().invoke(cli, ["eval", "deliberation", "--no-fail-on-regression"])

    assert result.exit_code == 0
    assert "Score: 0.0%" in result.output
