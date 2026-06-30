"""Tests for advisory hallucination-pattern risk reports."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from deepr.evals.hallucination_risks import (
    HALLUCINATION_RISK_REPORT_KIND,
    HALLUCINATION_RISK_REPORT_SCHEMA_VERSION,
    build_hallucination_risk_report,
    write_hallucination_risk_report,
)
from deepr.experts.consult_quality import build_consult_quality_review
from deepr.experts.consult_traces import build_consult_trace, build_consult_trace_candidates


def _scores(value: float) -> dict[str, float]:
    return {
        "uses_expert_state": value,
        "surfaces_uncertainty": value,
        "preserves_dissent": value,
        "actionability": value,
        "grounded_when_factual": value,
        "original_thought": value,
    }


def test_hallucination_risk_report_uses_reviewed_scores_and_trace_routers(tmp_path):
    trace = build_consult_trace(
        question="What legal policy changed this week?",
        requested_experts=["AI Policy Expert"],
        max_experts=3,
        budget=0.0,
        payload={
            "schema_version": "deepr-consult-v1",
            "kind": "deepr.expert.consult",
            "question": "What legal policy changed this week?",
            "answer": "Current legal policy changed.",
            "experts_consulted": ["AI Policy Expert"],
            "perspectives": [{"expert": "AI Policy Expert", "confidence": 0.4, "response": "thin"}],
            "agreements": [],
            "disagreements": [],
            "cost_usd": 0.0,
        },
        result={"perspectives": [{}], "synthesis_status": "completed"},
        trace_id="consult_hallucination",
        recorded_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
    )
    trace_path = tmp_path / "consult_traces.jsonl"
    trace_path.write_text(json.dumps(trace) + "\n", encoding="utf-8")

    candidate = build_consult_trace_candidates([trace])["candidates"][0]
    review = build_consult_quality_review(
        expert_name="AI Policy Expert",
        case=candidate["semantic_eval_case"],
        scores={**_scores(5.0), "grounded_when_factual": 2.0, "surfaces_uncertainty": 2.0},
        reviewer="operator",
        decision="accept",
        failure_labels=["unsupported_factual_claim"],
        candidate=candidate,
    )
    review_dir = tmp_path / "benchmarks"
    review_dir.mkdir()
    (review_dir / f"consult_quality_review_{review['review_id']}.json").write_text(
        json.dumps(review),
        encoding="utf-8",
    )

    payload = build_hallucination_risk_report(trace_path=trace_path, review_dir=review_dir)

    assert payload["schema_version"] == HALLUCINATION_RISK_REPORT_SCHEMA_VERSION
    assert payload["kind"] == HALLUCINATION_RISK_REPORT_KIND
    assert payload["contract"]["semantic_verdict"] is False
    assert payload["contract"]["blocks_answers"] is False
    assert payload["contract"]["writes_beliefs"] is False
    assert payload["trace_count"] == 1
    assert payload["review_count"] == 1
    assert payload["risk_label_counts"]["high_stakes_review_needed"] == 1
    assert payload["risk_label_counts"]["unsupported_factual_claim"] == 1
    assert payload["risk_label_counts"]["citation_provenance_gap"] == 1
    assert payload["risk_label_counts"]["overconfident_uncertainty_failure"] == 1
    assert {signal["judgment_source"] for signal in payload["signals"]} == {
        "deterministic_router",
        "human_or_calibrated_model_review",
    }
    assert "false_premise_compliance" in {item["risk_label"] for item in payload["coverage_gaps"]}
    assert str(trace_path) not in json.dumps(payload)


def test_write_hallucination_risk_report_round_trips(tmp_path):
    payload = build_hallucination_risk_report(trace_path=tmp_path / "missing.jsonl", review_dir=tmp_path / "missing")

    path = write_hallucination_risk_report(payload, output_dir=tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert path.name.startswith("hallucination_risks_")
    assert data["schema_version"] == HALLUCINATION_RISK_REPORT_SCHEMA_VERSION
    assert data["signal_count"] == 0
