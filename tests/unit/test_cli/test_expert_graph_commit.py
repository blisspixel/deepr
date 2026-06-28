"""Tests for `deepr expert apply-graph-commit`."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.beliefs import BeliefStore
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


def _write_envelope(path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


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
    _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(
        cli,
        ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "dry_run"
    assert payload["summary"]["planned_write_count"] == 1
    assert BeliefStore(profile.name).beliefs == {}


def test_apply_graph_commit_json_apply_requires_yes_in_noninteractive_mode(tmp_path):
    profile = _save_profile()
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Release text changed the compiler behavior.", "a" * 64),
        expert_name=profile.name,
    )
    envelope_path = tmp_path / "envelope.json"
    _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(cli, ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--json"])

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["failure_reasons"] == ["confirmation_required"]
    assert BeliefStore(profile.name).beliefs == {}


def test_apply_graph_commit_json_apply_writes_with_yes(tmp_path):
    profile = _save_profile()
    envelope = graph_commit_envelope(
        graph_commit_operation("b1", "Release text changed the compiler behavior.", "a" * 64),
        expert_name=profile.name,
    )
    envelope_path = tmp_path / "envelope.json"
    _write_envelope(envelope_path, envelope)

    result = CliRunner().invoke(
        cli, ["expert", "apply-graph-commit", profile.name, str(envelope_path), "--yes", "--json"]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["summary"]["status"] == "applied"
    assert payload["summary"]["applied_write_count"] == 1
    assert BeliefStore(profile.name).beliefs["b1"].claim == "Release text changed the compiler behavior."


def test_apply_graph_commit_json_apply_promotes_gap_with_yes(tmp_path):
    profile = _save_profile()
    topic = "Which unresolved verifier gaps should drive the next expert sync?"
    envelope = graph_commit_envelope(graph_commit_gap_operation(topic, "c" * 64), expert_name=profile.name)
    envelope_path = tmp_path / "envelope.json"
    _write_envelope(envelope_path, envelope)

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


def test_apply_graph_commit_json_apply_promotes_agenda_with_yes(tmp_path):
    profile = _save_profile()
    title = "Which agenda signals should guide the next expert sync?"
    envelope = graph_commit_envelope(graph_commit_agenda_operation(title, "e" * 64), expert_name=profile.name)
    envelope_path = tmp_path / "envelope.json"
    _write_envelope(envelope_path, envelope)

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
    _write_envelope(envelope_path, envelope)

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
    _write_envelope(envelope_path, envelope)

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
    _write_envelope(envelope_path, envelope)

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
    _write_envelope(envelope_path, envelope)

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
