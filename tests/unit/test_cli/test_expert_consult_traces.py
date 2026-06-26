"""Tests for consult trace review command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.commands.semantic.expert_consult_traces import expert_consult_traces
from deepr.experts.consult_traces import record_consult_trace


def _write_failed_trace(path):
    record_consult_trace(
        path=path,
        question="How should Deepr recover from low-context consults?",
        requested_experts=["A"],
        max_experts=3,
        budget=0.0,
        failure={"stage": "run_consult", "error_type": "RuntimeError", "message": "boom"},
        trace_id="consult_abcdef123456",
    )


def test_consult_traces_json_outputs_sanitized_candidates(tmp_path):
    path = tmp_path / "consult_traces.jsonl"
    _write_failed_trace(path)

    result = CliRunner().invoke(expert_consult_traces, ["--trace-path", str(path), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-consult-trace-candidates-v1"
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["trace_id"] == "consult_abcdef123456"
    assert payload["candidates"][0]["reason"] == "failed_consult"
    assert str(path) not in result.output
    assert "RuntimeError" not in result.output


def test_consult_traces_text_summary(tmp_path):
    path = tmp_path / "consult_traces.jsonl"
    _write_failed_trace(path)

    result = CliRunner().invoke(expert_consult_traces, ["--trace-path", str(path)])

    assert result.exit_code == 0
    assert "Consult Trace Candidates" in result.output
    assert "failed_consult" in result.output
