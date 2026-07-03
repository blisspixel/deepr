"""Tests for `deepr eval grounding-correctness`."""

from __future__ import annotations

import json
from types import SimpleNamespace

from click.testing import CliRunner

from deepr.cli.main import cli


def _credulous_checker():
    async def checker(claim, evidence):
        return SimpleNamespace(supported=True)  # always "supported" - the theater case

    return checker, "local:fake"


def test_grounding_correctness_help():
    result = CliRunner().invoke(cli, ["eval", "grounding-correctness", "--help"])
    assert result.exit_code == 0
    assert "precision" in result.output.lower()


def test_grounding_correctness_json_scores_credulous_checker(monkeypatch):
    monkeypatch.setattr(
        "deepr.cli.commands.eval_grounding_correctness._build_checker",
        lambda checker_plan, checker_plan_model, model: _credulous_checker(),
    )
    result = CliRunner().invoke(cli, ["eval", "grounding-correctness", "--json"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["schema_version"] == "deepr-grounding-correctness-v1"
    # Built-in golden set: 30 cases, 10 genuinely supported. A credulous checker
    # stamps SUPPORTED for all -> precision 10/30, false-support total.
    assert report["case_count"] == 30
    assert report["support_precision"] == round(10 / 30, 4)
    assert report["false_support_rate"] == 1.0


def test_grounding_correctness_custom_cases(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "deepr.cli.commands.eval_grounding_correctness._build_checker",
        lambda checker_plan, checker_plan_model, model: _credulous_checker(),
    )
    cases_file = tmp_path / "cases.json"
    cases_file.write_text(
        json.dumps([{"case_id": "x", "claim": "c", "evidence": "e", "label": "contradicted"}]),
        encoding="utf-8",
    )
    result = CliRunner().invoke(cli, ["eval", "grounding-correctness", "--cases", str(cases_file), "--json"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["case_count"] == 1
    # One contradicted case, checker says supported -> a false support.
    assert report["false_support_rate"] == 1.0


def test_grounding_correctness_no_local_model_exits_2(monkeypatch):
    # No plan checker and no local model available -> clean exit 2, not a traceback.
    monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: None)
    result = CliRunner().invoke(cli, ["eval", "grounding-correctness"])
    assert result.exit_code == 2
    assert "No local model available" in result.output
