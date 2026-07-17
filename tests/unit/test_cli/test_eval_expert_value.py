"""CLI tests for the operator-attested longitudinal expert-value evaluator."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.evals.expert_value import ARM_ORDER
from deepr.experts.blueprint import ExpertBlueprint, ExpertBlueprintDraft, ExpertBlueprintStore

_HASH = "a" * 64


def _blueprint(store: ExpertBlueprintStore) -> ExpertBlueprint:
    draft = ExpertBlueprintDraft.model_validate(
        {
            "schema_version": "deepr-expert-blueprint-draft-v1",
            "kind": "deepr.expert.blueprint_draft",
            "expert_name": "CLI Value Expert",
            "mission": "Support repeated evidence-bound decisions.",
            "non_goals": ["Authorize changes"],
            "decision_use_cases": [
                {
                    "id": "choice",
                    "question": "Which option fits?",
                    "success_criteria": ["Uses operator-accepted evidence"],
                }
            ],
            "source_policy": {
                "primary_sources_required": True,
                "preferred_source_types": ["Primary sources"],
                "excluded_sources": [],
            },
            "volatility": "medium",
            "update_cadence_days": 30,
            "initial_questions": ["What recurs?"],
            "acceptance_cases": [
                {
                    "id": "initial-case",
                    "question": "What does the first source world support?",
                    "success_criteria": ["Answers from the frozen world"],
                    "failure_conditions": [],
                }
            ],
        }
    )
    return store.apply(draft, attested_by="operator", now=datetime(2026, 1, 1, tzinfo=UTC)).blueprint


def _review_payload(blueprint: ExpertBlueprint) -> dict[str, object]:
    return {
        "schema_version": "deepr-expert-value-review-v1",
        "kind": "deepr.eval.expert_value_review",
        "methodology_version": "1.0",
        "rubric_version": "expert-value-rubric-v1",
        "review_set_id": "cli-review-1",
        "expert_name": blueprint.expert_name,
        "blueprint_revision": blueprint.revision,
        "blueprint_content_hash": blueprint.content_hash,
        "source_worlds": [
            {
                "source_world_id": "world-1",
                "as_of": "2026-01-01T00:00:00+00:00",
                "predecessor_source_world_id": None,
                "manifest_ref": "worlds/1.json",
                "manifest_sha256": _HASH,
                "supporting_source_count": 1,
                "distractor_source_count": 1,
                "noise_source_count": 1,
                "introduced_claim_refs": [],
                "invalidated_claim_refs": [],
            },
            {
                "source_world_id": "world-2",
                "as_of": "2026-02-01T00:00:00+00:00",
                "predecessor_source_world_id": "world-1",
                "manifest_ref": "worlds/2.json",
                "manifest_sha256": _HASH,
                "supporting_source_count": 1,
                "distractor_source_count": 1,
                "noise_source_count": 1,
                "introduced_claim_refs": [],
                "invalidated_claim_refs": [],
            },
        ],
        "cases": [
            {
                "acceptance_case_id": "initial-case",
                "source_world_id": "world-1",
                "evaluation_role": "initial",
                "expected_abstention": False,
                "observed_outcome": None,
            }
        ],
        "arm_configurations": [
            {
                "arm": arm,
                "run_policy_ref": f"policies/{arm}.json",
                "run_policy_sha256": _HASH,
                "construction_cost_usd": 0.0,
                "maintenance_cost_usd": 0.0,
                "construction_reviewer_minutes": 0.0,
                "maintenance_reviewer_minutes": 0.0,
            }
            for arm in ARM_ORDER
        ],
        "trials": [
            {
                "acceptance_case_id": "initial-case",
                "arm": arm,
                "executed_at": "2026-02-01T12:00:00+00:00",
                "run_artifact_ref": f"runs/{arm}.json",
                "run_artifact_sha256": _HASH,
                "answer_artifact_ref": f"answers/{arm}.md",
                "answer_artifact_sha256": _HASH,
                "measurements": {
                    "retrieval_cost_usd": 0.0,
                    "generation_cost_usd": 0.0,
                    "other_execution_cost_usd": 0.0,
                    "response_latency_seconds": 1.0,
                    "reviewer_minutes": 1.0,
                    "update_completed": None,
                    "update_latency_hours": None,
                },
                "semantic_attestation": {
                    "attested_by": "reviewer",
                    "attested_at": "2026-02-02T00:00:00+00:00",
                    "identity_verified": False,
                    "human_authorship_claimed": False,
                    "correctness": 3,
                    "source_relevance": 3,
                    "factual_support": 3,
                    "uncertainty_calibration": 3,
                    "abstained": False,
                    "false_support_observed": False,
                    "invalidated_belief_reused": None,
                    "negative_transfer_observed": None,
                    "retained_correctness": None,
                    "forward_transfer_observed": None,
                    "rationale": "Reviewed against the frozen source world.",
                },
            }
            for arm in ARM_ORDER
        ],
        "protocol_attestation": {
            "attested_by": "protocol owner",
            "attested_at": "2026-02-03T00:00:00+00:00",
            "identity_verified": False,
            "human_authorship_claimed": False,
            "review_blinding": "blinded",
            "review_order_randomized": True,
            "review_assignment_ref": "review/assignment.json",
            "review_assignment_sha256": _HASH,
            "same_cases_confirmed": True,
            "source_worlds_frozen": True,
            "arm_isolation_confirmed": True,
            "artifact_hashes_verified": True,
        },
    }


def _patch_store(monkeypatch, store: ExpertBlueprintStore) -> None:
    monkeypatch.setattr("deepr.cli.commands.eval_expert_value.ExpertBlueprintStore", lambda: store)


def _materialize_artifacts(root: Path, payload: dict[str, object]) -> None:
    counter = 0

    def write(record, reference_field: str, hash_field: str) -> None:
        nonlocal counter
        counter += 1
        path = root / record[reference_field]
        path.parent.mkdir(parents=True, exist_ok=True)
        data = f"artifact {counter}".encode()
        path.write_bytes(data)
        record[hash_field] = hashlib.sha256(data).hexdigest()

    for world in payload["source_worlds"]:
        write(world, "manifest_ref", "manifest_sha256")
    for arm in payload["arm_configurations"]:
        write(arm, "run_policy_ref", "run_policy_sha256")
    for trial in payload["trials"]:
        write(trial, "run_artifact_ref", "run_artifact_sha256")
        write(trial, "answer_artifact_ref", "answer_artifact_sha256")
    write(payload["protocol_attestation"], "review_assignment_ref", "review_assignment_sha256")


def test_expert_value_help_is_registered() -> None:
    result = CliRunner().invoke(cli, ["eval", "expert-value", "--help"])

    assert result.exit_code == 0
    assert "frozen four-arm expert value review" in result.output


def test_template_write_is_explicit_and_incomplete(tmp_path: Path, monkeypatch) -> None:
    store = ExpertBlueprintStore(tmp_path / "experts")
    blueprint = _blueprint(store)
    _patch_store(monkeypatch, store)
    output = tmp_path / "review-template.json"

    result = CliRunner().invoke(
        cli,
        ["eval", "expert-value", blueprint.expert_name, "--template", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["blueprint_content_hash"] == blueprint.content_hash
    assert len(payload["trials"]) == 4
    assert payload["protocol_attestation"]["artifact_hashes_verified"] is False
    assert payload["protocol_attestation"]["identity_verified"] is False
    assert "incomplete" in result.output


def test_completed_review_emits_json_and_writes_only_on_request(tmp_path: Path, monkeypatch) -> None:
    store = ExpertBlueprintStore(tmp_path / "experts")
    blueprint = _blueprint(store)
    _patch_store(monkeypatch, store)
    source = tmp_path / "review.json"
    source.write_text(json.dumps(_review_payload(blueprint)), encoding="utf-8")
    output = tmp_path / "report.json"

    result = CliRunner().invoke(
        cli,
        [
            "eval",
            "expert-value",
            blueprint.expert_name,
            "--from-file",
            str(source),
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert report == saved
    assert report["schema_version"] == "deepr-expert-value-report-v1"
    assert report["artifact_verification"]["mode"] == "operator_attested"
    assert report["artifact_verification"]["independently_verified"] is False
    assert report["contract"]["evaluator_cost_usd"] == 0.0
    assert report["contract"]["winner_selected"] is False


def test_text_report_states_non_authority(tmp_path: Path, monkeypatch) -> None:
    store = ExpertBlueprintStore(tmp_path / "experts")
    blueprint = _blueprint(store)
    _patch_store(monkeypatch, store)
    source = tmp_path / "review.json"
    source.write_text(json.dumps(_review_payload(blueprint)), encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        ["eval", "expert-value", blueprint.expert_name, "--from-file", str(source)],
    )

    assert result.exit_code == 0, result.output
    assert "0 models, 0 providers, 0 network" in result.output
    assert "operator attested; referenced files were not independently opened" in result.output
    assert "No arm was ranked, no winner was selected, and no default changed" in result.output


def test_artifact_root_recomputes_every_digest_before_report(tmp_path: Path, monkeypatch) -> None:
    store = ExpertBlueprintStore(tmp_path / "experts")
    blueprint = _blueprint(store)
    _patch_store(monkeypatch, store)
    payload = _review_payload(blueprint)
    artifact_root = tmp_path / "artifacts"
    _materialize_artifacts(artifact_root, payload)
    source = tmp_path / "review.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "eval",
            "expert-value",
            blueprint.expert_name,
            "--from-file",
            str(source),
            "--artifact-root",
            str(artifact_root),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    verification = report["artifact_verification"]
    assert verification["mode"] == "local_filesystem_sha256"
    assert verification["reference_count"] == 15
    assert verification["verified_reference_count"] == 15
    assert verification["verified_file_count"] == 15
    assert verification["all_matched"] is True
    assert report["contract"]["artifact_references_opened"] is True


def test_artifact_mismatch_does_not_create_report(tmp_path: Path, monkeypatch) -> None:
    store = ExpertBlueprintStore(tmp_path / "experts")
    blueprint = _blueprint(store)
    _patch_store(monkeypatch, store)
    payload = _review_payload(blueprint)
    artifact_root = tmp_path / "artifacts"
    _materialize_artifacts(artifact_root, payload)
    first_ref = payload["source_worlds"][0]["manifest_ref"]
    (artifact_root / first_ref).write_text("changed after binding", encoding="utf-8")
    source = tmp_path / "review.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "must-not-exist.json"

    result = CliRunner().invoke(
        cli,
        [
            "eval",
            "expert-value",
            blueprint.expert_name,
            "--from-file",
            str(source),
            "--artifact-root",
            str(artifact_root),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code != 0
    assert "SHA-256 digest does not match" in result.output
    assert not output.exists()


def test_report_cannot_overwrite_review_input(tmp_path: Path, monkeypatch) -> None:
    store = ExpertBlueprintStore(tmp_path / "experts")
    blueprint = _blueprint(store)
    _patch_store(monkeypatch, store)
    source = tmp_path / "review.json"
    original = json.dumps(_review_payload(blueprint))
    source.write_text(original, encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "eval",
            "expert-value",
            blueprint.expert_name,
            "--from-file",
            str(source),
            "--output",
            str(source),
        ],
    )

    assert result.exit_code != 0
    assert "must not overwrite" in result.output
    assert source.read_text(encoding="utf-8") == original


def test_report_output_must_be_outside_artifact_root(tmp_path: Path, monkeypatch) -> None:
    store = ExpertBlueprintStore(tmp_path / "experts")
    blueprint = _blueprint(store)
    _patch_store(monkeypatch, store)
    payload = _review_payload(blueprint)
    artifact_root = tmp_path / "artifacts"
    _materialize_artifacts(artifact_root, payload)
    source = tmp_path / "review.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    output = artifact_root / "report.json"

    result = CliRunner().invoke(
        cli,
        [
            "eval",
            "expert-value",
            blueprint.expert_name,
            "--from-file",
            str(source),
            "--artifact-root",
            str(artifact_root),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code != 0
    assert "outside --artifact-root" in result.output
    assert not output.exists()


def test_artifact_root_is_rejected_for_template_mode() -> None:
    result = CliRunner().invoke(
        cli,
        ["eval", "expert-value", "Missing Expert", "--template", "--artifact-root", "."],
    )

    assert result.exit_code != 0
    assert "only valid with --from-file" in result.output


def test_invalid_review_does_not_create_requested_report(tmp_path: Path, monkeypatch) -> None:
    store = ExpertBlueprintStore(tmp_path / "experts")
    blueprint = _blueprint(store)
    _patch_store(monkeypatch, store)
    payload = _review_payload(blueprint)
    payload["trials"].pop()
    source = tmp_path / "invalid-review.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "must-not-exist.json"

    result = CliRunner().invoke(
        cli,
        [
            "eval",
            "expert-value",
            blueprint.expert_name,
            "--from-file",
            str(source),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code != 0
    assert "Invalid expert-value review" in result.output
    assert not output.exists()


def test_command_requires_exactly_one_mode() -> None:
    result = CliRunner().invoke(cli, ["eval", "expert-value", "Missing Expert"])

    assert result.exit_code != 0
    assert "exactly one" in result.output
