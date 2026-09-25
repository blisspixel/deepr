"""Rehearsal to strict workbook: recorded execution plus bound labels, never invented labels."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from deepr.evals.expert_value import ExpertValueReview, build_expert_value_report
from deepr.evals.expert_value_blinding import bind_review_labels, build_blind_assignment, reviewer_criteria
from deepr.evals.expert_value_rehearsal import PLAN_SCHEMA, RehearsalPlan, RehearsalRun
from deepr.evals.expert_value_rehearsal_workbook import assemble_workbook, label_fields, world_label_context
from deepr.experts.blueprint import ExpertBlueprint, ExpertBlueprintDraft, ExpertBlueprintStore
from tests.unit.test_eval.test_expert_value_rehearsal import FakeLauncher, make_policy
from tests.unit.test_eval.test_expert_value_sources import Bundle

CASES = {
    "initial-case": ("world-1", "initial", False, "What is supported initially?"),
    "hard-negative-case": ("world-1", "hard_negative", True, "Should the false premise be declined?"),
    "retention-case": ("world-2", "retention", False, "What remained correct?"),
    "update-case": ("world-2", "update", False, "What changed?"),
    "transfer-case": ("world-2", "forward_transfer", False, "How does it apply to a new case?"),
}
PLACEMENT = {
    "cases": [
        {
            "acceptance_case_id": case_id,
            "source_world_id": world,
            "evaluation_role_draft": role,
            "expected_abstention_draft": abstain,
        }
        for case_id, (world, role, abstain, _) in CASES.items()
    ]
}
WORLD_CLAIMS = {
    "source_worlds": [
        {
            "source_world_id": "world-1",
            "as_of": "2026-01-20T00:00:00Z",
            "predecessor_source_world_id": None,
            "supporting_source_count": 1,
            "distractor_source_count": 1,
            "noise_source_count": 1,
            "introduced_claim_refs": ["a1"],
            "invalidated_claim_refs": [],
        },
        {
            "source_world_id": "world-2",
            "as_of": "2026-02-20T00:00:00Z",
            "predecessor_source_world_id": "world-1",
            "supporting_source_count": 2,
            "distractor_source_count": 1,
            "noise_source_count": 1,
            "introduced_claim_refs": ["a2"],
            "invalidated_claim_refs": ["a1"],
        },
    ]
}


def _blueprint(store_root: Path) -> ExpertBlueprint:
    draft = ExpertBlueprintDraft.model_validate(
        {
            "schema_version": "deepr-expert-blueprint-draft-v1",
            "kind": "deepr.expert.blueprint_draft",
            "expert_name": "Rehearsal Expert",
            "mission": "Rehearse the four-arm protocol.",
            "non_goals": ["Authorize production changes"],
            "decision_use_cases": [
                {"id": "choice", "question": "Which choice fits?", "success_criteria": ["Uses the sources"]}
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
                for case_id, (_, _, _, question) in CASES.items()
            ],
        }
    )
    return (
        ExpertBlueprintStore(store_root)
        .apply(draft, attested_by="blueprint operator", now=datetime(2026, 1, 1, tzinfo=UTC))
        .blueprint
    )


def _executed(tmp_path: Path, launcher: FakeLauncher | None = None) -> Path:
    bundle = Bundle(tmp_path / "organizer")
    plan = RehearsalPlan.model_validate(
        {
            "schema_version": PLAN_SCHEMA,
            "cases": [
                {"case_id": case_id, "source_world_id": world, "question": question}
                for case_id, (world, _, _, question) in CASES.items()
            ],
        }
    )
    RehearsalRun(
        policy=make_policy(),
        plan=plan,
        index_path=bundle.index_path,
        artifact_root=bundle.root,
        run_root=tmp_path / "run",
        launcher=launcher or FakeLauncher(),
    ).execute()
    return tmp_path / "run"


def _label_value(field: str, now: str) -> Any:
    if field in ("correctness", "source_relevance", "factual_support", "uncertainty_calibration"):
        return 3
    if field == "rationale":
        return "Uses the frozen sources."
    if field == "attested_at":
        return now
    if field == "reviewer_minutes":
        return 2
    return False


def _review(tmp_path: Path, blueprint: ExpertBlueprint, **run_kwargs: Any) -> tuple[Path, bytes, dict[str, Any]]:
    run_root = _executed(tmp_path, **run_kwargs)
    blueprint_payload = {"acceptance_cases": [case.model_dump() for case in blueprint.acceptance_cases]}
    cutoffs = {w["source_world_id"]: w["as_of"] for w in WORLD_CLAIMS["source_worlds"]}
    criteria = reviewer_criteria(blueprint_payload, PLACEMENT, cutoffs, WORLD_CLAIMS)
    packet, key = build_blind_assignment(run_root, criteria)
    now = datetime.now(UTC).isoformat()
    labels = []
    for case in json.loads(packet)["cases"]:
        for answer in case["answers"]:
            fields = {name: _label_value(name, now) for name in case["case"]["label_fields"]}
            labels.append({"opaque_id": answer["opaque_id"], **fields})
    binding = bind_review_labels(
        run_root, key, packet, json.dumps({"reviewer": {"id": "reviewer-1"}, "labels": labels}).encode()
    )
    return run_root, key, binding


def test_label_fields_follow_the_workbook_role_rules() -> None:
    context = world_label_context(WORLD_CLAIMS)
    assert context == {
        "world-1": {"later_world": False, "invalidation_applies": False},
        "world-2": {"later_world": True, "invalidation_applies": True},
    }
    assert "retained_correctness" in label_fields("retention", **context["world-2"])
    assert "forward_transfer_observed" in label_fields("forward_transfer", **context["world-2"])
    first = label_fields("initial", **context["world-1"])
    assert "negative_transfer_observed" not in first and "invalidated_belief_reused" not in first


def test_workbook_validates_and_its_hashes_verify_under_the_run_root(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path / "store")
    run_root, key, binding = _review(tmp_path, blueprint)
    workbook = assemble_workbook(
        run_root,
        blueprint=blueprint,
        placement=PLACEMENT,
        world_claims=WORLD_CLAIMS,
        key_bytes=key,
        binding=binding,
        review_set_id="rehearsal-1",
        protocol_attested_by="operator",
    )
    review = ExpertValueReview.model_validate(workbook)
    assert len(review.trials) == 20
    report = build_expert_value_report(review, blueprint, artifact_root=run_root)
    assert report["kind"]
    updates = {t.arm: t.measurements.update_completed for t in review.trials if t.acceptance_case_id == "update-case"}
    assert updates == {
        "fresh_research": True,
        "static_history": True,
        "compiled_expert": False,
        "maintained_expert": True,
    }
    assert (run_root / "review" / "assignment-key.json").read_bytes() == key
    assert all(t.semantic_attestation.attested_by == "reviewer-1" for t in review.trials)


def test_without_operator_attestation_the_protocol_fields_stay_open(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path / "store")
    run_root, key, binding = _review(tmp_path, blueprint)
    workbook = assemble_workbook(
        run_root,
        blueprint=blueprint,
        placement=PLACEMENT,
        world_claims=WORLD_CLAIMS,
        key_bytes=key,
        binding=binding,
        review_set_id="rehearsal-1",
    )
    attestation = workbook["protocol_attestation"]
    assert attestation["attested_by"] == "" and attestation["arm_isolation_confirmed"] is False
    with pytest.raises(ValueError):
        ExpertValueReview.model_validate(workbook)


def test_failed_maintenance_is_an_incomplete_update(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path / "store")
    launcher = FakeLauncher(lambda spec, _cwd: "fail" if spec["worker_id"] == "maintain-world-2" else None)
    run_root, key, binding = _review(tmp_path, blueprint, launcher=launcher)
    workbook = assemble_workbook(
        run_root,
        blueprint=blueprint,
        placement=PLACEMENT,
        world_claims=WORLD_CLAIMS,
        key_bytes=key,
        binding=binding,
        review_set_id="rehearsal-1",
        protocol_attested_by="operator",
    )
    maintained = next(
        t for t in workbook["trials"] if t["acceptance_case_id"] == "update-case" and t["arm"] == "maintained_expert"
    )
    assert maintained["measurements"]["update_completed"] is False
    assert maintained["measurements"]["update_latency_hours"] is None


def test_workbook_refusals(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path / "store")
    run_root, key, binding = _review(tmp_path, blueprint)
    common: dict[str, Any] = {
        "blueprint": blueprint,
        "placement": PLACEMENT,
        "world_claims": WORLD_CLAIMS,
        "review_set_id": "r",
    }
    with pytest.raises(ValueError, match="different assignment key"):
        assemble_workbook(run_root, key_bytes=key + b" ", binding=binding, **common)
    missing_field = json.loads(json.dumps(binding))
    missing_field["bound"][0]["label"].pop("rationale")
    with pytest.raises(ValueError, match="missing: rationale"):
        assemble_workbook(run_root, key_bytes=key, binding=missing_field, **common)
    other = _blueprint(tmp_path / "other-store").model_copy(update={"acceptance_cases": blueprint.acceptance_cases[:2]})
    with pytest.raises(ValueError, match="apply the reviewed blueprint"):
        assemble_workbook(run_root, key_bytes=key, binding=binding, **{**common, "blueprint": other})
    (run_root / "review" / "assignment-key.json").write_bytes(b"another key")
    with pytest.raises(ValueError, match="already stored"):
        assemble_workbook(run_root, key_bytes=key, binding=binding, **common)


def test_workbook_refuses_a_run_with_unanswered_cells(tmp_path: Path) -> None:
    blueprint = _blueprint(tmp_path / "store")
    launcher = FakeLauncher(
        lambda spec, _cwd: "fail" if spec["worker_id"] == "answer-update-case-static_history" else None
    )
    run_root, key, binding = _review(tmp_path, blueprint, launcher=launcher)
    with pytest.raises(ValueError, match="update-case/static_history"):
        assemble_workbook(
            run_root,
            blueprint=blueprint,
            placement=PLACEMENT,
            world_claims=WORLD_CLAIMS,
            key_bytes=key,
            binding=binding,
            review_set_id="r",
        )
