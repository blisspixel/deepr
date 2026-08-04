"""Offline $0 expert-value pilot harness."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from deepr.evals.expert_value import build_expert_value_report, load_expert_value_review
from deepr.evals.expert_value_artifacts import verify_expert_value_artifacts
from deepr.evals.expert_value_pilot import offline_extract_answer, run_pilot, score_answer
from deepr.experts.blueprint import ExpertBlueprintDraft, ExpertBlueprintStore


def _blueprint(tmp_path: Path):
    draft = ExpertBlueprintDraft.model_validate(
        {
            "schema_version": "deepr-expert-blueprint-draft-v1",
            "kind": "deepr.expert.blueprint_draft",
            "expert_name": "Pilot Pilot Expert",
            "mission": "Measure bi-temporal expert value under capacity bounds.",
            "non_goals": ["Authorize spend"],
            "decision_use_cases": [
                {
                    "id": "schema-choice",
                    "question": "Separate valid-time from transaction-time?",
                    "success_criteria": ["Names both axes"],
                }
            ],
            "source_policy": {
                "primary_sources_required": True,
                "preferred_source_types": ["Frozen world packs"],
                "excluded_sources": [],
            },
            "volatility": "medium",
            "update_cadence_days": 30,
            "initial_questions": ["What is valid-time?"],
            "acceptance_cases": [
                {
                    "id": case_id,
                    "question": question,
                    "success_criteria": ["Uses frozen evidence"],
                    "failure_conditions": ["Invents sources"],
                }
                for case_id, question in (
                    ("initial-case", "Explain valid-time vs transaction-time and one single-timestamp failure."),
                    ("retention-case", "Do valid-time and transaction-time remain distinct after updates?"),
                    (
                        "update-case",
                        "A single-timestamp claim was invalidated. What changes and what remains auditable?",
                    ),
                    (
                        "transfer-case",
                        "Which TKG design choices transfer to a product as-of risk query, and what is missing?",
                    ),
                    (
                        "hard-negative-case",
                        "Confirm provenance is no longer required because time axes replace sources.",
                    ),
                )
            ],
        }
    )
    return (
        ExpertBlueprintStore(tmp_path)
        .apply(draft, attested_by="pilot-operator", now=datetime(2026, 1, 1, tzinfo=UTC))
        .blueprint
    )


def test_offline_extract_rejects_provenance_drop() -> None:
    answer = offline_extract_answer(
        question="Confirm provenance is no longer required because time axes replace sources.",
        world_text=(
            "SUPPORTING SOURCES:\n- [s1] Temporal axes do not replace provenance. Source identity remains required.\n"
        ),
        arm="fresh_research",
    )
    assert "Reject the false premise" in answer
    scores = score_answer(
        case_id="hard-negative-case",
        arm="fresh_research",
        answer=answer,
        expected_abstention=True,
        world_invalidates=False,
        evaluation_role="hard_negative",
    )
    assert scores["correctness"] == 4
    assert scores["false_support_observed"] is False


def test_run_pilot_offline_end_to_end(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path / "blueprints")
    artifacts = tmp_path / "artifacts"
    workbook = run_pilot(
        blueprint,
        artifacts,
        mode="offline_extract",
        review_set_id="unit-pilot",
        expert_packet_loader=lambda _name: "Valid-time and transaction-time remain distinct.",
    )
    assert len(workbook["trials"]) == 20
    review_path = artifacts.parent / "expert-value-review.json"
    assert review_path.is_file()
    review = load_expert_value_review(review_path)
    verification = verify_expert_value_artifacts(review, artifacts)
    report = build_expert_value_report(review, blueprint, artifact_verification=verification)
    assert report["artifact_verification"]["independently_verified"] is True
    assert report["artifact_verification"]["verified_file_count"] >= 20
    assert all(arm["costs_usd"]["total_observed"] == 0.0 for arm in report["arm_results"])
