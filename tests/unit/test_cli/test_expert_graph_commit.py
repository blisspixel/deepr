"""Tests for `deepr expert apply-graph-commit`."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.beliefs import BeliefStore
from deepr.experts.profile import ExpertProfile, ExpertStore
from tests.unit.graph_commit_helpers import graph_commit_envelope, graph_commit_operation


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
