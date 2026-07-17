"""Tests for the operator-attested longitudinal expert-value evaluator."""

from __future__ import annotations

import copy
import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from deepr.evals.expert_value import (
    ARM_ORDER,
    ExpertValueReview,
    build_expert_value_report,
    expert_value_review_hash,
    expert_value_review_template,
    load_expert_value_review,
)
from deepr.experts.blueprint import ExpertBlueprint, ExpertBlueprintDraft, ExpertBlueprintStore

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64
_HASH_D = "d" * 64


def _blueprint(tmp_path: Path, *, mission: str = "Support repeated platform decisions.") -> ExpertBlueprint:
    draft = ExpertBlueprintDraft.model_validate(
        {
            "schema_version": "deepr-expert-blueprint-draft-v1",
            "kind": "deepr.expert.blueprint_draft",
            "expert_name": "Value Expert",
            "mission": mission,
            "non_goals": ["Authorize production changes"],
            "decision_use_cases": [
                {
                    "id": "platform-choice",
                    "question": "Which platform choice fits the evidence?",
                    "success_criteria": ["Separates evidence from recommendation"],
                }
            ],
            "source_policy": {
                "primary_sources_required": True,
                "preferred_source_types": ["Primary evidence"],
                "excluded_sources": [],
            },
            "volatility": "fast",
            "update_cadence_days": 14,
            "initial_questions": ["Which decisions recur?"],
            "acceptance_cases": [
                {
                    "id": case_id,
                    "question": question,
                    "success_criteria": ["Uses the frozen source world"],
                    "failure_conditions": ["Invents evidence"],
                }
                for case_id, question in (
                    ("initial-case", "What is supported initially?"),
                    ("retention-case", "What remained correct?"),
                    ("update-case", "What changed?"),
                    ("transfer-case", "How does the evidence apply to a new case?"),
                    ("hard-negative-case", "Should the system decline the false premise?"),
                )
            ],
        }
    )
    return (
        ExpertBlueprintStore(tmp_path)
        .apply(draft, attested_by="blueprint operator", now=datetime(2026, 1, 1, tzinfo=UTC))
        .blueprint
    )


def _review_payload(blueprint: ExpertBlueprint) -> dict[str, object]:
    roles = {
        "initial-case": ("source-world-1", "initial", False),
        "retention-case": ("source-world-2", "retention", False),
        "update-case": ("source-world-2", "update", False),
        "transfer-case": ("source-world-3", "forward_transfer", False),
        "hard-negative-case": ("source-world-3", "hard_negative", True),
    }
    cases = []
    for case in blueprint.acceptance_cases:
        source_world_id, role, expected_abstention = roles[case.id]
        observed_outcome = None
        if case.id == "update-case":
            observed_outcome = {
                "deployed_arm": "maintained_expert",
                "outcome_id": "outcome_update_1",
                "outcome_record_ref": "outcomes/value-expert.jsonl#outcome_update_1",
                "outcome_record_sha256": _HASH_D,
                "result": "succeeded",
            }
        cases.append(
            {
                "acceptance_case_id": case.id,
                "source_world_id": source_world_id,
                "evaluation_role": role,
                "expected_abstention": expected_abstention,
                "observed_outcome": observed_outcome,
            }
        )

    arm_scores = {
        "fresh_research": 3,
        "static_history": 2,
        "compiled_expert": 3,
        "maintained_expert": 4,
    }
    trials = []
    for case in blueprint.acceptance_cases:
        source_world_id, role, expected_abstention = roles[case.id]
        for arm_index, arm in enumerate(ARM_ORDER, start=1):
            score = arm_scores[arm]
            is_static_failure = arm == "static_history" and case.id in {"update-case", "hard-negative-case"}
            trials.append(
                {
                    "acceptance_case_id": case.id,
                    "arm": arm,
                    "executed_at": "2026-04-01T12:00:00+00:00",
                    "run_artifact_ref": f"runs/{case.id}/{arm}.json",
                    "run_artifact_sha256": _HASH_A,
                    "answer_artifact_ref": f"answers/{case.id}/{arm}.md",
                    "answer_artifact_sha256": _HASH_B,
                    "measurements": {
                        "retrieval_cost_usd": round(arm_index * 0.01, 2),
                        "generation_cost_usd": round(arm_index * 0.02, 2),
                        "other_execution_cost_usd": 0.01,
                        "response_latency_seconds": float(arm_index * 10),
                        "reviewer_minutes": 2.0,
                        "update_completed": True if role == "update" else None,
                        "update_latency_hours": float(arm_index * 6) if role == "update" else None,
                    },
                    "semantic_attestation": {
                        "attested_by": "blinded reviewer",
                        "attested_at": "2026-04-02T12:00:00+00:00",
                        "identity_verified": False,
                        "human_authorship_claimed": False,
                        "correctness": score,
                        "source_relevance": score,
                        "factual_support": score,
                        "uncertainty_calibration": score,
                        "abstained": expected_abstention and arm != "static_history",
                        "false_support_observed": is_static_failure,
                        "invalidated_belief_reused": arm == "static_history" and case.id == "update-case"
                        if source_world_id == "source-world-2"
                        else None,
                        "negative_transfer_observed": is_static_failure if role != "initial" else None,
                        "retained_correctness": arm != "static_history" if role == "retention" else None,
                        "forward_transfer_observed": arm in {"compiled_expert", "maintained_expert"}
                        if role == "forward_transfer"
                        else None,
                        "rationale": "Reviewed against the frozen evidence manifest and acceptance criteria.",
                    },
                }
            )

    return {
        "schema_version": "deepr-expert-value-review-v1",
        "kind": "deepr.eval.expert_value_review",
        "methodology_version": "1.0",
        "rubric_version": "expert-value-rubric-v1",
        "review_set_id": "value-review-2026-q1",
        "expert_name": blueprint.expert_name,
        "blueprint_revision": blueprint.revision,
        "blueprint_content_hash": blueprint.content_hash,
        "source_worlds": [
            {
                "source_world_id": "source-world-1",
                "as_of": "2026-01-01T00:00:00+00:00",
                "predecessor_source_world_id": None,
                "manifest_ref": "worlds/1.json",
                "manifest_sha256": _HASH_A,
                "supporting_source_count": 3,
                "distractor_source_count": 2,
                "noise_source_count": 1,
                "introduced_claim_refs": ["claim:initial"],
                "invalidated_claim_refs": [],
            },
            {
                "source_world_id": "source-world-2",
                "as_of": "2026-02-01T00:00:00+00:00",
                "predecessor_source_world_id": "source-world-1",
                "manifest_ref": "worlds/2.json",
                "manifest_sha256": _HASH_B,
                "supporting_source_count": 4,
                "distractor_source_count": 2,
                "noise_source_count": 2,
                "introduced_claim_refs": ["claim:new"],
                "invalidated_claim_refs": ["claim:initial"],
            },
            {
                "source_world_id": "source-world-3",
                "as_of": "2026-03-01T00:00:00+00:00",
                "predecessor_source_world_id": "source-world-2",
                "manifest_ref": "worlds/3.json",
                "manifest_sha256": _HASH_C,
                "supporting_source_count": 4,
                "distractor_source_count": 3,
                "noise_source_count": 2,
                "introduced_claim_refs": ["claim:transfer"],
                "invalidated_claim_refs": [],
            },
        ],
        "cases": cases,
        "arm_configurations": [
            {
                "arm": arm,
                "run_policy_ref": f"policies/{arm}.json",
                "run_policy_sha256": _HASH_C,
                "construction_cost_usd": float(index),
                "maintenance_cost_usd": 1.0 if arm == "maintained_expert" else 0.0,
                "construction_reviewer_minutes": float(index * 5),
                "maintenance_reviewer_minutes": 5.0 if arm == "maintained_expert" else 0.0,
            }
            for index, arm in enumerate(ARM_ORDER)
        ],
        "trials": trials,
        "protocol_attestation": {
            "attested_by": "protocol owner",
            "attested_at": "2026-04-03T12:00:00+00:00",
            "identity_verified": False,
            "human_authorship_claimed": False,
            "review_blinding": "blinded",
            "review_order_randomized": True,
            "review_assignment_ref": "review/assignment.json",
            "review_assignment_sha256": _HASH_D,
            "same_cases_confirmed": True,
            "source_worlds_frozen": True,
            "arm_isolation_confirmed": True,
            "artifact_hashes_verified": True,
        },
    }


def _review(blueprint: ExpertBlueprint) -> ExpertValueReview:
    return ExpertValueReview.model_validate(_review_payload(blueprint))


def test_template_is_bound_to_blueprint_and_intentionally_incomplete(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path)
    template = expert_value_review_template(blueprint)

    assert template["blueprint_revision"] == blueprint.revision
    assert template["blueprint_content_hash"] == blueprint.content_hash
    assert len(template["trials"]) == len(blueprint.acceptance_cases) * 4
    assert [item["arm"] for item in template["arm_configurations"]] == list(ARM_ORDER)
    assert template["protocol_attestation"]["same_cases_confirmed"] is False
    assert template["protocol_attestation"]["identity_verified"] is False
    assert template["protocol_attestation"]["human_authorship_claimed"] is False
    with pytest.raises(ValidationError):
        ExpertValueReview.model_validate(template)


def test_report_keeps_quality_risk_cost_and_effort_dimensions_separate(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path)
    review = _review(blueprint)
    report = build_expert_value_report(review, blueprint, now=datetime(2026, 4, 4, tzinfo=UTC))

    assert report["review_input_sha256"] == expert_value_review_hash(review)
    assert report["protocol"]["arms"] == list(ARM_ORDER)
    assert report["protocol"]["attested_trial_count"] == 20
    assert report["protocol"]["protocol_attested_by"] == "protocol owner"
    assert report["protocol"]["missing_evaluation_roles"] == []
    maintained = next(item for item in report["arm_results"] if item["arm"] == "maintained_expert")
    static = next(item for item in report["arm_results"] if item["arm"] == "static_history")
    assert maintained["dimensions"]["correctness"]["mean_score"] == 4.0
    assert maintained["dimensions"]["factual_support"]["mean_score"] == 4.0
    assert static["false_support"]["observed_trials"] == 2
    assert static["invalidated_belief_reuse"]["eligible_trials"] == 2
    assert static["invalidated_belief_reuse"]["observed_trials"] == 1
    assert static["invalidated_belief_reuse"]["rate"] == 0.5
    assert static["negative_transfer"]["eligible_trials"] == 4
    assert static["negative_transfer"]["observed_trials"] == 2
    assert static["negative_transfer"]["rate"] == 0.5
    assert static["expected_abstention_match"]["rate"] == 0.8
    assert maintained["retained_correctness"]["rate"] == 1.0
    assert maintained["forward_transfer"]["rate"] == 1.0
    assert maintained["update_latency_hours"] == {
        "eligible_trials": 1,
        "completed_trials": 1,
        "completion_rate": 1.0,
        "mean_completed": 24.0,
        "maximum_completed": 24.0,
    }
    assert maintained["costs_usd"]["total_observed"] == 4.65
    assert maintained["reviewer_effort_minutes"]["total"] == 30.0
    assert report["observed_outcomes"]["linked_case_count"] == 1
    assert report["observed_outcomes"]["causal_attribution"] is False
    assert report["artifact_verification"]["mode"] == "operator_attested"
    assert report["artifact_verification"]["independently_verified"] is False
    assert report["artifact_verification"]["all_matched"] is None
    assert report["contract"]["artifact_references_opened"] is False
    assert report["contract"]["winner_selected"] is False
    assert report["contract"]["changes_defaults"] is False
    assert report["contract"]["semantic_verdict"] is False
    assert report["protocol"]["review_assignment_sha256"] == _HASH_D
    fresh_comparison = next(item for item in report["comparisons"] if item["comparator_arm"] == "fresh_research")
    correctness_interval = fresh_comparison["paired_bootstrap"]["metrics"]["correctness"]
    assert fresh_comparison["paired_bootstrap"]["method"] == "paired_percentile_bootstrap"
    assert fresh_comparison["paired_bootstrap"]["resamples"] == 9999
    assert correctness_interval["case_count"] == 5
    assert correctness_interval["mean_difference"] == 1.0
    assert correctness_interval["confidence_interval"] == {"lower": 1.0, "upper": 1.0}
    assert "superiority_supported" not in correctness_interval
    assert "score" not in report
    assert "winner" not in report


def test_report_rejects_stale_blueprint_binding(tmp_path: Path) -> None:
    original = _blueprint(tmp_path)
    review = _review(original)
    changed = _blueprint(tmp_path, mission="Support changed repeated platform decisions.")

    with pytest.raises(ValueError, match="revision is stale"):
        build_expert_value_report(review, changed)


def test_break_even_is_cost_only_and_uses_mean_consultation_cost(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path)
    payload = _review_payload(blueprint)
    for trial in payload["trials"]:
        trial["measurements"]["retrieval_cost_usd"] = 0.0
        trial["measurements"]["other_execution_cost_usd"] = 0.0
        trial["measurements"]["generation_cost_usd"] = 1.0 if trial["arm"] == "fresh_research" else 0.0
    report = build_expert_value_report(ExpertValueReview.model_validate(payload), blueprint)
    estimate = next(item for item in report["break_even_estimates"] if item["comparator_arm"] == "fresh_research")

    assert estimate["status"] == "estimable"
    assert estimate["fixed_cost_delta_usd"] == 4.0
    assert estimate["marginal_savings_usd_per_consultation"] == 1.0
    assert estimate["break_even_consultations"] == 4
    assert estimate["cost_only"] is True
    assert estimate["quality_considered"] is False


def test_failed_update_stays_in_completion_denominator_without_fake_latency(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path)
    payload = _review_payload(blueprint)
    static_update = next(
        trial
        for trial in payload["trials"]
        if trial["acceptance_case_id"] == "update-case" and trial["arm"] == "static_history"
    )
    static_update["measurements"]["update_completed"] = False
    static_update["measurements"]["update_latency_hours"] = None

    report = build_expert_value_report(ExpertValueReview.model_validate(payload), blueprint)
    static = next(item for item in report["arm_results"] if item["arm"] == "static_history")

    assert static["update_latency_hours"] == {
        "eligible_trials": 1,
        "completed_trials": 0,
        "completion_rate": 0.0,
        "mean_completed": None,
        "maximum_completed": None,
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload["trials"].pop(), "complete four-arm matrix"),
        (
            lambda payload: payload["source_worlds"][1].update({"predecessor_source_world_id": None}),
            "ordered predecessor chain",
        ),
        (
            lambda payload: payload["trials"][0]["semantic_attestation"].update({"retained_correctness": True}),
            "set only for retention",
        ),
        (
            lambda payload: payload["trials"][0]["measurements"].update({"generation_cost_usd": float("nan")}),
            "finite number",
        ),
    ],
)
def test_review_rejects_protocol_corruption(tmp_path: Path, mutation, message: str) -> None:
    payload = _review_payload(_blueprint(tmp_path))
    mutation(payload)

    with pytest.raises(ValidationError, match=message):
        ExpertValueReview.model_validate(payload)


def test_load_and_aggregate_open_no_network_and_write_no_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blueprint = _blueprint(tmp_path / "experts")
    source = tmp_path / "review.json"
    source.write_text(json.dumps(_review_payload(blueprint)), encoding="utf-8")
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("expert-value aggregation must not open a network connection")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    review = load_expert_value_review(source)
    report = build_expert_value_report(review, blueprint)
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    assert report["contract"]["evaluator_network_access"] is False
    assert after == before


def test_review_hash_ignores_json_whitespace(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path)
    payload = _review_payload(blueprint)
    first = ExpertValueReview.model_validate(copy.deepcopy(payload))
    second = ExpertValueReview.model_validate(json.loads(json.dumps(payload, indent=4)))

    assert expert_value_review_hash(first) == expert_value_review_hash(second)
