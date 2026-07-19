"""Tests for `deepr expert apply-graph-commit`."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.beliefs import BeliefStore
from deepr.experts.graph_commit_provenance import write_sync_graph_commit_receipt
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.profile import ExpertProfile, ExpertStore
from tests.unit.graph_commit_helpers import (
    graph_commit_agenda_operation,
    graph_commit_concept_operation,
    graph_commit_envelope,
    graph_commit_gap_operation,
    graph_commit_hypothesis_operation,
    graph_commit_operation,
    graph_commit_original_idea_operation,
    graph_commit_stance_operation,
)


def _save_profile() -> ExpertProfile:
    profile = ExpertProfile(name="Compiler Expert", vector_store_id="local-only:compiler", domain="compiler")
    ExpertStore().save(profile)
    return profile


def _write_envelope(path, payload: dict):
    target = str(payload["target"]["expert_name"])
    root = ExpertStore().find_existing_dir(target)
    assert root is not None
    input_payload = payload["input"]
    extraction = {
        "schema_version": input_payload["claim_extraction_schema_version"],
        "kind": "deepr.expert.semantic_claim_extraction",
        "candidates": [],
    }
    verification = {
        "schema_version": input_payload["claim_verification_schema_version"],
        "kind": input_payload["claim_verification_kind"],
        "decisions": [],
    }
    extraction_path = root / input_payload["claim_extraction_artifact"]
    verification_path = root / input_payload["claim_verification_artifact"]
    envelope_path = root / "sync_artifacts" / "graph_commit_envelopes" / path.name
    for artifact_path, artifact in (
        (extraction_path, extraction),
        (verification_path, verification),
        (envelope_path, payload),
    ):
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    write_sync_graph_commit_receipt(
        root,
        envelope_artifact=envelope_path.relative_to(root).as_posix(),
        envelope=payload,
        claim_extraction=extraction,
        claim_verification=verification,
    )
    return envelope_path


def test_apply_graph_commit_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "apply-graph-commit", "--help"])

    assert result.exit_code == 0
    assert "Apply a verified graph commit envelope" in result.output


def test_apply_graph_commit_json_dry_run_does_not_write(tmp_path):
    profile = _save_profile()
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Release text changed the compiler behavior.", "a" * 64),
        expert_name=profile.name,
    )
    envelope_path = tmp_path / "envelope.json"
    envelope_path = _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(
        cli,
        ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "dry_run"
    assert payload["summary"]["planned_write_count"] == 1
    assert BeliefStore(profile.name).beliefs == {}
    unchanged = ExpertStore().load(profile.name)
    assert unchanged is not None
    assert unchanged.knowledge_cutoff_date is None
    assert unchanged.last_knowledge_refresh is None


def test_apply_graph_commit_json_apply_requires_yes_in_noninteractive_mode(tmp_path):
    profile = _save_profile()
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Release text changed the compiler behavior.", "a" * 64),
        expert_name=profile.name,
    )
    envelope_path = tmp_path / "envelope.json"
    envelope_path = _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(cli, ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--json"])

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["failure_reasons"] == ["confirmation_required"]
    assert BeliefStore(profile.name).beliefs == {}


def test_apply_graph_commit_rejects_unattested_caller_selected_json(tmp_path):
    profile = _save_profile()
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Caller-authored content must remain inert.", "a" * 64),
        expert_name=profile.name,
    )
    envelope_path = tmp_path / "forged-envelope.json"
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--yes", "--json"],
    )

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "blocked"
    assert "investigation_run_provenance_untrusted" in payload["summary"]["failure_reasons"]
    assert BeliefStore(profile.name).beliefs == {}


def test_apply_graph_commit_rejects_envelope_tampered_after_receipt(tmp_path):
    profile = _save_profile()
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Original producer output.", "a" * 64),
        expert_name=profile.name,
    )
    envelope_path = _write_envelope(tmp_path / "envelope.json", envelope)
    envelope["operations"][0]["belief"]["claim"] = "Tampered caller content."
    envelope_path.write_text(json.dumps(envelope), encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--yes", "--json"],
    )

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert "envelope_artifact_hash_mismatch" in payload["summary"]["failure_reasons"]
    assert BeliefStore(profile.name).beliefs == {}


def test_apply_graph_commit_json_apply_writes_with_yes(tmp_path):
    profile = _save_profile()
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Release text changed the compiler behavior.", "a" * 64),
        expert_name=profile.name,
    )
    envelope_path = tmp_path / "envelope.json"
    envelope_path = _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(
        cli, ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--yes", "--json"]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "applied"
    assert payload["summary"]["applied_write_count"] == 1
    assert BeliefStore(profile.name).beliefs["b1"].claim == "Release text changed the compiler behavior."
    updated = ExpertStore().load(profile.name)
    assert updated is not None
    assert updated.knowledge_cutoff_date is not None
    assert updated.last_knowledge_refresh == updated.knowledge_cutoff_date


def test_apply_graph_commit_json_apply_promotes_gap_with_yes(tmp_path):
    profile = _save_profile()
    topic = "Which unresolved verifier gaps should drive the next expert sync?"
    envelope = graph_commit_envelope(graph_commit_gap_operation(topic, "c" * 64), expert_name=profile.name)
    envelope_path = tmp_path / "envelope.json"
    envelope_path = _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(
        cli,
        ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--yes", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "applied"
    assert payload["summary"]["applied_write_count"] == 1
    assert payload["contract"]["writes_expert_state"] is True
    assert topic in MetaCognitionTracker(profile.name).knowledge_gaps
    unchanged = ExpertStore().load(profile.name)
    assert unchanged is not None
    assert unchanged.knowledge_cutoff_date is None
    assert unchanged.last_knowledge_refresh is None


def test_apply_graph_commit_json_apply_promotes_agenda_with_yes(tmp_path):
    profile = _save_profile()
    title = "Which agenda signals should guide the next expert sync?"
    envelope = graph_commit_envelope(graph_commit_agenda_operation(title, "e" * 64), expert_name=profile.name)
    envelope_path = tmp_path / "envelope.json"
    envelope_path = _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(
        cli,
        ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--yes", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "applied"
    assert payload["summary"]["applied_write_count"] == 1
    assert payload["contract"]["writes_expert_state"] is True
    assert title in MetaCognitionTracker(profile.name).exploration_agendas


def test_apply_graph_commit_json_apply_promotes_hypothesis_with_yes(tmp_path):
    profile = _save_profile()
    title = "Statistical traces improve expert council verification."
    envelope = graph_commit_envelope(graph_commit_hypothesis_operation(title, "1" * 64), expert_name=profile.name)
    envelope_path = tmp_path / "envelope.json"
    envelope_path = _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(
        cli,
        ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--yes", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "applied"
    assert payload["summary"]["applied_write_count"] == 1
    assert payload["contract"]["writes_expert_state"] is True
    assert title in MetaCognitionTracker(profile.name).hypotheses


def test_apply_graph_commit_json_apply_promotes_concept_with_yes(tmp_path):
    profile = _save_profile()
    name = "Statistical variable map for expert council plans"
    envelope = graph_commit_envelope(graph_commit_concept_operation(name, "3" * 64), expert_name=profile.name)
    envelope_path = tmp_path / "envelope.json"
    envelope_path = _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(
        cli,
        ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--yes", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "applied"
    assert payload["summary"]["applied_write_count"] == 1
    assert payload["contract"]["writes_expert_state"] is True
    assert name in MetaCognitionTracker(profile.name).concepts


def test_apply_graph_commit_json_apply_promotes_stance_with_yes(tmp_path):
    profile = _save_profile()
    title = "Prefer variable-first expert council plans"
    envelope = graph_commit_envelope(graph_commit_stance_operation(title, "5" * 64), expert_name=profile.name)
    envelope_path = tmp_path / "envelope.json"
    envelope_path = _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(
        cli,
        ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--yes", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "applied"
    assert payload["summary"]["applied_write_count"] == 1
    assert payload["contract"]["writes_expert_state"] is True
    assert title in MetaCognitionTracker(profile.name).stances


def test_apply_graph_commit_json_apply_promotes_original_idea_with_yes(tmp_path):
    profile = _save_profile()
    title = "Statistician council packets"
    envelope = graph_commit_envelope(graph_commit_original_idea_operation(title, "7" * 64), expert_name=profile.name)
    envelope_path = tmp_path / "envelope.json"
    envelope_path = _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(
        cli,
        ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--yes", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "applied"
    assert payload["summary"]["applied_write_count"] == 1
    assert payload["contract"]["writes_expert_state"] is True
    assert title in MetaCognitionTracker(profile.name).original_ideas
