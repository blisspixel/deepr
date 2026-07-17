"""CLI coverage for the frozen investigation evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.evals.investigation import InvestigationEvalOutcome, InvestigationEvalReport


def test_eval_investigation_outputs_zero_cost_json_report() -> None:
    result = CliRunner().invoke(cli, ["eval", "investigation", "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["schema_version"] == "deepr-investigation-eval-v1"
    assert data["kind"] == "deepr.eval.investigation"
    assert data["cost_usd"] == 0.0
    assert data["failed_cases"] == 0
    assert data["semantic_review_status"] == "unreviewed"
    assert data["quality_claim"] is False


def test_eval_investigation_save_writes_json_artifact() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["eval", "investigation", "--json", "--save"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        path = Path(data["saved_to"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert path.name.startswith("investigation_eval_")
        assert saved["schema_version"] == "deepr-investigation-eval-v1"
        assert saved["failed_cases"] == 0


def test_eval_investigation_fails_on_structural_regression_by_default() -> None:
    report = InvestigationEvalReport(
        outcomes=(InvestigationEvalOutcome("fixture_failure", "fixture", False),)
    )

    with patch("deepr.evals.investigation.run_investigation_eval", return_value=report):
        result = CliRunner().invoke(cli, ["eval", "investigation"])

    assert result.exit_code != 0
    assert "1 investigation regression(s) failed" in result.output


def test_eval_investigation_can_report_without_failing_exit() -> None:
    report = InvestigationEvalReport(
        outcomes=(InvestigationEvalOutcome("fixture_failure", "fixture", False),)
    )

    with patch("deepr.evals.investigation.run_investigation_eval", return_value=report):
        result = CliRunner().invoke(
            cli,
            ["eval", "investigation", "--no-fail-on-regression"],
        )

    assert result.exit_code == 0
    assert "Score: 0.0%" in result.output
