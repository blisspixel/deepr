"""Tests for eval CLI commands."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner

from deepr.cli.main import cli


def test_eval_new_invokes_benchmark_with_safe_defaults():
    runner = CliRunner()

    with patch("deepr.cli.commands.eval.subprocess.run", return_value=SimpleNamespace(returncode=0)) as mock_run:
        result = runner.invoke(cli, ["eval", "new"])

    assert result.exit_code == 0
    cmd = mock_run.call_args.args[0]
    assert "--new-models" in cmd
    assert "--max-estimated-cost" in cmd
    assert "1.0" in cmd
    assert "--save" in cmd


def test_eval_new_passes_through_flags():
    runner = CliRunner()

    with patch("deepr.cli.commands.eval.subprocess.run", return_value=SimpleNamespace(returncode=0)) as mock_run:
        result = runner.invoke(
            cli,
            [
                "eval",
                "new",
                "--tier",
                "news",
                "--dry-run",
                "--quick",
                "--no-judge",
                "--max-estimated-cost",
                "2.5",
                "--no-save",
            ],
        )

    assert result.exit_code == 0
    cmd = mock_run.call_args.args[0]
    assert "news" in cmd
    assert "--dry-run" in cmd
    assert "--quick" in cmd
    assert "--no-judge" in cmd
    assert "2.5" in cmd
    assert "--save" not in cmd


def test_eval_all_requires_approve_expensive_for_execution():
    runner = CliRunner()

    with patch("deepr.cli.commands.eval.subprocess.run") as mock_run:
        result = runner.invoke(cli, ["eval", "all"])

    assert result.exit_code != 0
    assert "--approve-expensive" in result.output
    mock_run.assert_not_called()


def test_eval_all_dry_run_does_not_require_approval():
    runner = CliRunner()

    with patch("deepr.cli.commands.eval.subprocess.run", return_value=SimpleNamespace(returncode=0)) as mock_run:
        result = runner.invoke(cli, ["eval", "all", "--dry-run", "--no-judge"])

    assert result.exit_code == 0
    cmd = mock_run.call_args.args[0]
    assert "--tier" in cmd and "all" in cmd
    assert "--dry-run" in cmd
    assert "--no-judge" in cmd


def test_eval_red_team_outputs_zero_cost_json_report():
    runner = CliRunner()

    result = runner.invoke(cli, ["eval", "red-team", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["cost_usd"] == 0.0
    assert data["attack_success_rate"] == 0.0
    assert data["total_cases"] == 13


def test_eval_red_team_save_writes_json_artifact():
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["eval", "red-team", "--json", "--save"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        path = Path(data["saved_to"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert path.name.startswith("red_team_")
        assert saved["attack_success_rate"] == 0.0
        assert saved["total_cases"] == 13


def test_eval_red_team_outputs_text_summary():
    runner = CliRunner()

    result = runner.invoke(cli, ["eval", "red-team"])

    assert result.exit_code == 0
    assert "Agentic red-team report" in result.output
    assert "Attack success rate: 0.0%" in result.output


def test_eval_consult_outputs_zero_cost_json_report():
    runner = CliRunner()

    result = runner.invoke(cli, ["eval", "consult", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["suite_name"] == "consult-harness"
    assert data["cost_usd"] == 0.0
    assert data["total_cases"] == 8
    assert data["failed_cases"] == 0


def test_eval_consult_save_writes_json_artifact():
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["eval", "consult", "--json", "--save"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        path = Path(data["saved_to"])
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert path.name.startswith("consult_eval_")
        assert saved["suite_name"] == "consult-harness"
        assert saved["failed_cases"] == 0


def test_eval_consult_outputs_text_summary():
    runner = CliRunner()

    result = runner.invoke(cli, ["eval", "consult"])

    assert result.exit_code == 0
    assert "Consult harness eval" in result.output
    assert "Score: 100.0%" in result.output
