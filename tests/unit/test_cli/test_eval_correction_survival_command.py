"""CLI coverage for the zero-cost correction-survival diagnostic."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from deepr.cli.main import cli


def test_writes_a_complete_mock_run_and_refuses_to_reuse_its_directory(tmp_path: Path) -> None:
    out = tmp_path / "run"
    result = CliRunner().invoke(cli, ["eval", "correction-survival", "--output-dir", str(out), "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["kind"] == "deepr.eval.correction-survival-report.v1"
    assert data["paid_calls"] == 0
    assert data["model_identity"] == "mock:no-inference"
    assert data["recorded_attempts"] == data["scheduled_attempts"]
    assert (out / "COMPLETE.json").is_file()
    assert json.loads((out / "report.json").read_text(encoding="utf-8"))["case_set_sha256"] == data["case_set_sha256"]
    assert "not answer quality" in (out / "report.md").read_text(encoding="utf-8")

    again = CliRunner().invoke(cli, ["eval", "correction-survival", "--output-dir", str(out)])
    assert again.exit_code != 0
    assert "never reused" in again.output


def test_default_location_is_the_configured_benchmarks_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path / "data"))
    result = CliRunner().invoke(cli, ["eval", "correction-survival", "--distractors", "5"])

    assert result.exit_code == 0, result.output
    assert "distractor sources per world: 5" in result.output
    runs = list((tmp_path / "data" / "benchmarks" / "correction-survival").iterdir())
    assert len(runs) == 1
    assert (runs[0] / "COMPLETE.json").is_file()
