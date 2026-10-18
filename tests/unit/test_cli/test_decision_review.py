"""Exercise the installed command shape against real, read-only record stores."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.consult_traces import build_consult_trace
from deepr.experts.outcomes import ExpertOutcomeDraft, ExpertOutcomeStore
from deepr.experts.profile import ExpertProfile, ExpertStore


def _snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() if path.is_file() else None for path in root.rglob("*")}


def test_decision_review_cli_preserves_legacy_profile_and_record_bytes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(tmp_path / "experts"))
    trace_path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("DEEPR_CONSULT_TRACE_PATH", str(trace_path))
    store = ExpertStore()
    profile = ExpertProfile(name="Platform Expert", vector_store_id="", domain="platform")
    store.save(profile)
    profile_path = store._get_profile_path(profile.name)
    old_profile = json.loads(profile_path.read_text())
    old_profile["schema_version"] = 4
    profile_path.write_text(json.dumps(old_profile))
    ExpertOutcomeStore().record(
        ExpertOutcomeDraft(
            expert_name=profile.name,
            decision_id="migration",
            decision_summary="Move the service",
            result="mixed",
            observation="Rollback was needed.",
            observed_at="2026-10-01T00:00:00Z",
            attested_by="maintainer",
            consult_trace_id="first-trace",
        ),
        outcome_id="first",
    )
    record = build_consult_trace(
        trace_id="first-trace",
        question="Should we move?",
        requested_experts=[profile.name],
        max_experts=1,
        budget=0,
        payload={"experts_consulted": [profile.name], "answer": "Retain rollback.", "synthesis_status": "completed"},
    )
    trace_path.write_text(json.dumps(record) + "\n")
    before = _snapshot(tmp_path)
    runner = CliRunner()
    arguments = ["expert", "review-decision", profile.name, "--outcome-id", "first"]
    machine = runner.invoke(cli, [*arguments, "--json"])
    assert machine.exit_code == 0, machine.output
    packet = json.loads(machine.stdout)
    human = runner.invoke(cli, arguments)
    assert human.exit_code == 0, human.output
    assert packet["snapshot_sha256"] in human.stdout
    assert "Retain rollback." in human.stdout
    assert "Rollback was needed." in human.stdout
    assert packet["cases"][0]["consultation"]["record"] == record
    assert _snapshot(tmp_path) == before


def test_review_missing_expert_creates_no_roots(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(tmp_path / "experts"))
    result = CliRunner().invoke(cli, ["expert", "review-decision", "Missing", "--outcome-id", "first"])
    assert result.exit_code != 0
    assert "not found" in result.output
    assert not list(tmp_path.iterdir())
