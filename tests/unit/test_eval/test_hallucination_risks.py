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
from deepr.experts.handoff import HANDOFF_KIND, HANDOFF_SCHEMA_VERSION
from deepr.experts.source_pack_compiler import build_source_pack_manifest


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
    assert payload["prompt_regression_candidate_count"] == 2
    assert {item["surface"] for item in payload["prompt_regression_candidates"]} == {
        "consult_trace",
        "consult_quality_review",
    }
    assert {item["semantic_verdict"] for item in payload["prompt_regression_candidates"]} == {False}
    assert {item["writes_state"] for item in payload["prompt_regression_candidates"]} == {False}
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


def test_hallucination_risk_report_summarizes_context_position_metadata(tmp_path):
    trace = build_consult_trace(
        question="How should a long-context consult preserve evidence placement?",
        requested_experts=["A", "B", "C"],
        max_experts=3,
        budget=0.0,
        payload={
            "schema_version": "deepr-consult-v1",
            "kind": "deepr.expert.consult",
            "question": "How should a long-context consult preserve evidence placement?",
            "answer": "Use traceable context placement metadata.",
            "experts_consulted": ["A", "B", "C"],
            "perspectives": [
                {
                    "expert": "A",
                    "confidence": 0.9,
                    "response": "first",
                    "context": {"source": "belief_store", "selection": "first"},
                },
                {
                    "expert": "B",
                    "confidence": 0.8,
                    "response": "middle",
                    "context": {"source": "belief_store", "selection": "middle"},
                },
                {
                    "expert": "C",
                    "confidence": 0.7,
                    "response": "last",
                    "context": {"source": "belief_store", "selection": "last"},
                },
            ],
            "agreements": [],
            "disagreements": [],
            "cost_usd": 0.0,
        },
        result={"perspectives": [{}, {}, {}], "synthesis_status": "completed"},
        trace_id="consult_111111111111",
        recorded_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
    )
    trace_path = tmp_path / "consult_traces.jsonl"
    trace_path.write_text(json.dumps(trace) + "\n", encoding="utf-8")

    payload = build_hallucination_risk_report(trace_path=trace_path, review_dir=tmp_path / "missing")

    assert payload["signal_count"] == 0
    metadata = payload["context_position_metadata"]
    assert metadata["source"] == "consult_trace_selected_order"
    assert metadata["trace_count_with_position_metadata"] == 1
    assert metadata["trace_count_with_middle_context"] == 1
    assert metadata["selected_context_slot_count"] == 3
    assert metadata["position_metadata_slot_count"] == 3
    assert metadata["middle_context_slot_count"] == 1
    assert metadata["semantic_verdict"] is False
    assert metadata["writes_state"] is False
    assert metadata["measures_long_context_middle_loss"] is False
    gap = next(item for item in payload["coverage_gaps"] if item["risk_label"] == "long_context_middle_loss")
    assert "calibrated long-context eval cases" in gap["reason"]


def test_hallucination_risk_report_maps_reviewed_false_premise_and_template_labels(tmp_path):
    trace = build_consult_trace(
        question="What changed after the nonexistent 2026 licensing rule took effect?",
        requested_experts=["AI Policy Expert"],
        max_experts=3,
        budget=0.0,
        failure={"error_type": "RuntimeError"},
        trace_id="consult_falsepremise",
        recorded_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
    )
    candidate = build_consult_trace_candidates([trace])["candidates"][0]
    review = build_consult_quality_review(
        expert_name="AI Policy Expert",
        case=candidate["semantic_eval_case"],
        scores=_scores(5.0),
        reviewer="operator",
        decision="accept",
        failure_labels=["false_premise_compliance", "template_order_sensitivity"],
        candidate=candidate,
    )
    review_dir = tmp_path / "benchmarks"
    review_dir.mkdir()
    (review_dir / f"consult_quality_review_{review['review_id']}.json").write_text(
        json.dumps(review),
        encoding="utf-8",
    )

    payload = build_hallucination_risk_report(trace_path=tmp_path / "missing.jsonl", review_dir=review_dir)

    assert payload["risk_label_counts"]["false_premise_compliance"] == 1
    assert payload["risk_label_counts"]["template_sensitivity"] == 1
    assert payload["risk_label_counts"]["overconfident_uncertainty_failure"] == 1
    assert payload["prompt_regression_candidate_count"] == 1
    assert set(payload["prompt_regression_candidates"][0]["prompt_focus"]) == {
        "tighten reviewed-answer remediation instructions",
        "challenge or qualify unsupported premises before answering",
        "surface uncertainty, stale context, and open questions",
        "check answer stability across prompt-template and example-order variants",
    }
    assert {
        "false_premise_compliance",
        "template_sensitivity",
    }.isdisjoint({item["risk_label"] for item in payload["coverage_gaps"]})


def test_hallucination_risk_report_maps_reviewed_middle_context_loss(tmp_path):
    trace = build_consult_trace(
        question="How should a consult preserve evidence from the middle packet?",
        requested_experts=["A", "B", "C"],
        max_experts=3,
        budget=0.0,
        payload={
            "schema_version": "deepr-consult-v1",
            "kind": "deepr.expert.consult",
            "question": "How should a consult preserve evidence from the middle packet?",
            "answer": "Use the edge packets.",
            "experts_consulted": ["A", "B", "C"],
            "perspectives": [
                {
                    "expert": "A",
                    "confidence": 0.9,
                    "response": "start",
                    "context": {"source": "belief_store", "selection": "start"},
                },
                {
                    "expert": "B",
                    "confidence": 0.8,
                    "response": "middle",
                    "context": {"source": "belief_store", "selection": "middle"},
                },
                {
                    "expert": "C",
                    "confidence": 0.7,
                    "response": "end",
                    "context": {"source": "belief_store", "selection": "end"},
                },
            ],
            "agreements": [],
            "disagreements": [],
            "cost_usd": 0.0,
        },
        result={"perspectives": [{}, {}, {}], "synthesis_status": "completed"},
        trace_id="consult_middlectx",
        recorded_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
    )
    candidate = build_consult_trace_candidates([trace])["candidates"][0]
    review = build_consult_quality_review(
        expert_name="AI Policy Expert",
        case=candidate["semantic_eval_case"],
        scores=_scores(5.0),
        reviewer="operator",
        decision="accept",
        failure_labels=["long_context_middle_loss"],
        candidate=candidate,
    )
    review_dir = tmp_path / "benchmarks"
    review_dir.mkdir()
    (review_dir / f"consult_quality_review_{review['review_id']}.json").write_text(
        json.dumps(review),
        encoding="utf-8",
    )

    payload = build_hallucination_risk_report(trace_path=tmp_path / "missing.jsonl", review_dir=review_dir)

    assert payload["risk_label_counts"]["long_context_middle_loss"] == 1
    assert payload["risk_label_counts"]["context_gap"] == 1
    assert payload["prompt_regression_candidate_count"] == 1
    assert (
        "preserve and explicitly use relevant middle-context evidence"
        in payload["prompt_regression_candidates"][0]["prompt_focus"]
    )
    assert "long_context_middle_loss" not in {item["risk_label"] for item in payload["coverage_gaps"]}
    assert payload["signals"][0]["semantic_verdict"] is False


def test_hallucination_risk_report_reads_handoff_and_source_pack_manifests(tmp_path):
    handoff_path = tmp_path / "handoff.json"
    handoff = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "kind": HANDOFF_KIND,
        "generated_at": "2026-06-30T12:00:00+00:00",
        "expert": {"name": "Policy Expert", "domain": "legal", "description": "Compliance research"},
        "summary": {
            "claim_count": 3,
            "contested_open_count": 1,
            "grounding_assurance": {
                "cross_vendor": 0,
                "same_vendor_fresh_context": 1,
                "unverified": 2,
            },
        },
        "limits": {"max_claims": 1},
    }
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    manifest = build_source_pack_manifest(
        {
            "schema_version": "deepr.sync_source_pack.v1",
            "query": "legal policy update",
            "topic": "legal policy",
            "source_pack": {
                "schema_version": "deepr.source_pack.v1",
                "mode": "fresh",
                "generated_at": "2026-06-30T12:00:00+00:00",
                "source_count": 2,
                "retrieved_source_count": 1,
                "search_queries": ["legal policy update"],
                "sources": [
                    {
                        "label": "source-1",
                        "title": "Policy release",
                        "url": "https://example.com/policy",
                        "source": "web",
                        "fetched": True,
                        "content_hash": "",
                        "excerpt": "Policy text.",
                    }
                ],
            },
        },
        source_pack_artifact="C:\\secret\\sync_artifacts\\source_packs\\pack.json",
    )
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    (manifest_dir / "source_pack_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    payload = build_hallucination_risk_report(
        trace_path=tmp_path / "missing_traces.jsonl",
        review_dir=tmp_path / "missing_reviews",
        handoff_paths=[handoff_path],
        source_pack_manifest_dir=manifest_dir,
    )

    assert payload["handoff_count"] == 1
    assert payload["source_pack_manifest_count"] == 1
    assert payload["risk_label_counts"]["grounding_assurance_gap"] == 1
    assert payload["risk_label_counts"]["dissent_review_needed"] == 1
    assert payload["risk_label_counts"]["handoff_truncation_review_needed"] == 1
    assert payload["risk_label_counts"]["citation_provenance_gap"] == 1
    assert payload["risk_label_counts"]["source_pack_compile_blocked"] == 1
    assert payload["risk_label_counts"]["context_gap"] == 1
    assert payload["prompt_regression_candidate_count"] == 0
    assert {signal["surface"] for signal in payload["signals"]} == {"expert_handoff", "source_pack_manifest"}
    assert {signal["judgment_source"] for signal in payload["signals"]} == {"deterministic_router"}
    rendered = json.dumps(payload)
    assert str(handoff_path) not in rendered
    assert "C:\\secret" not in rendered

    zero_limited = build_hallucination_risk_report(
        trace_path=tmp_path / "missing_traces.jsonl",
        review_dir=tmp_path / "missing_reviews",
        handoff_paths=[handoff_path],
        source_pack_manifest_dir=manifest_dir,
        handoff_limit=0,
        source_pack_limit=0,
    )
    assert zero_limited["handoff_count"] == 0
    assert zero_limited["source_pack_manifest_count"] == 0
