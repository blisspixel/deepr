"""Tests for the zero-cost consult harness regression suite."""

from __future__ import annotations

import json

from deepr.evals.consult import run_consult_eval, write_consult_eval_report


def test_consult_eval_builtin_cases_pass():
    report = run_consult_eval()

    assert report.cost_usd == 0.0
    assert report.total_cases == 6
    assert report.failed_cases == 0
    assert report.score == 1.0
    assert {outcome.case_id for outcome in report.outcomes} == {
        "explicit_slug_resolution",
        "stored_belief_context_packet",
        "synthesis_section_parser",
        "payload_context_preservation",
        "consult_trace_contract",
        "consult_trace_candidate_contract",
    }


def test_consult_eval_report_round_trips_to_json(tmp_path):
    report = run_consult_eval()

    path = write_consult_eval_report(report, output_dir=tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert path.name.startswith("consult_eval_")
    assert data["suite_name"] == "consult-harness"
    assert data["cost_usd"] == 0.0
    assert data["failed_cases"] == 0
