"""Tests for `deepr expert self-model`."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from deepr.cli.commands.semantic.expert_self_model import (
    expert_accept_self_model,
    expert_monitor,
    expert_next,
    expert_promote_monitor,
    expert_propose_self_model,
    expert_self_model,
)
from deepr.cli.main import cli
from deepr.core.contracts import Claim, ExpertManifest, Gap
from deepr.experts.beliefs import Belief
from deepr.experts.profile import ExpertProfile
from deepr.experts.profile_store import ExpertStore


def _profile() -> ExpertProfile:
    profile = ExpertProfile(
        name="Agent Harness Expert",
        vector_store_id="vs-agent-harness",
        domain="agent harnesses",
        knowledge_cutoff_date=datetime(2026, 6, 26, tzinfo=UTC),
        installed_skills=["consult-review"],
    )
    manifest = ExpertManifest(
        expert_name="Agent Harness Expert",
        domain="agent harnesses",
        claims=[Claim.create("Trace failures into evals.", "agent harnesses", 0.9)],
        gaps=[Gap.create("semantic quality evals", questions=["Which answers failed?"], ev_cost_ratio=5.0)],
    )
    profile.get_manifest = lambda **_kwargs: manifest  # type: ignore[method-assign]
    return profile


def _patch_store(profile):
    expert_dir = Path("experts") / "agent_harness_expert"
    return patch(
        "deepr.cli.commands.semantic.expert_self_model.ExpertStore",
        return_value=MagicMock(
            load=MagicMock(return_value=profile),
            find_existing_dir=MagicMock(return_value=expert_dir),
        ),
    )


def test_self_model_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "self-model", "--help"])

    assert result.exit_code == 0
    assert "read-only self-model" in result.output.lower()


def test_next_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "next", "--help"])

    assert result.exit_code == 0
    assert "highest-value next actions" in result.output.lower()


def test_next_json_output(monkeypatch):
    profile = _profile()

    class FakeLoopStore:
        def __init__(self, name):
            assert name == profile.name

        def list_runs(self, *, limit):
            assert limit == 20
            return []

    monkeypatch.setattr("deepr.experts.loop_runs.ExpertLoopRunStore", FakeLoopStore)
    with _patch_store(profile):
        result = CliRunner().invoke(expert_next, [profile.name, "--limit", "2", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-expert-next-v1"
    assert payload["kind"] == "deepr.expert.next"
    assert len(payload["next_actions"]) == 2


def test_next_rejects_nonpositive_limit():
    with _patch_store(_profile()):
        result = CliRunner().invoke(expert_next, ["Agent Harness Expert", "--limit", "0"])

    assert result.exit_code != 0
    assert "max_actions must be positive" in result.output


def test_next_reports_missing_expert_storage():
    store = MagicMock(
        load=MagicMock(return_value=_profile()),
        find_existing_dir=MagicMock(return_value=None),
    )
    with patch("deepr.cli.commands.semantic.expert_self_model.ExpertStore", return_value=store):
        result = CliRunner().invoke(expert_next, ["Agent Harness Expert"])

    assert result.exit_code != 0
    assert "storage directory not found" in result.output


def test_next_human_output_preserves_rich_markup_literals():
    profile = _profile()
    profile.name = "[bold]Expert[/bold]"
    profile.domain = "[bold]literal[/bold]"
    profile.get_manifest = lambda **_kwargs: ExpertManifest(  # type: ignore[method-assign]
        expert_name=profile.name,
        domain=profile.domain,
    )

    with _patch_store(profile):
        result = CliRunner().invoke(expert_next, [profile.name])

    assert result.exit_code == 0, result.output
    assert "[bold]Expert[/bold]" in result.output
    assert "[bold]literal[/bold]" in result.output


def test_next_real_cli_does_not_mutate_expert_storage(monkeypatch, tmp_path):
    experts_dir = tmp_path / "experts"
    profile = _profile()
    ExpertStore(base_path=str(experts_dir)).save(profile)
    expert_dir = experts_dir / "agent_harness_expert"
    shutil.rmtree(expert_dir / "beliefs")
    profile_path = expert_dir / "profile.json"
    legacy_profile = json.loads(profile_path.read_text(encoding="utf-8"))
    legacy_profile["schema_version"] = 1
    legacy_profile["learning_budget"] = legacy_profile.pop("monthly_learning_budget")
    profile_path.write_text(json.dumps(legacy_profile, indent=2), encoding="utf-8")
    before = {path.relative_to(experts_dir): path.read_bytes() for path in experts_dir.rglob("*") if path.is_file()}
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(experts_dir))

    result = CliRunner().invoke(cli, ["expert", "next", profile.name, "--json"])

    assert result.exit_code == 0, result.output
    after = {path.relative_to(experts_dir): path.read_bytes() for path in experts_dir.rglob("*") if path.is_file()}
    assert after == before
    assert not (experts_dir / "agent_harness_expert" / "beliefs").exists()


def test_next_rejects_beliefs_symlink_that_escapes_expert_root(monkeypatch, tmp_path):
    experts_dir = tmp_path / "experts"
    profile = _profile()
    ExpertStore(base_path=str(experts_dir)).save(profile)
    beliefs_dir = experts_dir / "agent_harness_expert" / "beliefs"
    shutil.rmtree(beliefs_dir)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        beliefs_dir.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are not available on this platform")
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(experts_dir))

    result = CliRunner().invoke(cli, ["expert", "next", profile.name, "--json"])

    assert result.exit_code != 0
    assert "storage failed safety validation" in result.output


def test_next_rejects_expert_directory_symlink_that_escapes_root(monkeypatch, tmp_path):
    experts_dir = tmp_path / "experts"
    experts_dir.mkdir()
    outside_root = tmp_path / "outside"
    profile = _profile()
    ExpertStore(base_path=str(outside_root)).save(profile)
    outside_expert = outside_root / "agent_harness_expert"
    try:
        (experts_dir / "agent_harness_expert").symlink_to(outside_expert, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are not available on this platform")
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(experts_dir))

    result = CliRunner().invoke(cli, ["expert", "next", profile.name, "--json"])

    assert result.exit_code != 0
    assert "storage failed safety validation" in result.output


def test_next_rejects_belief_file_symlink_that_escapes_expert_root(monkeypatch, tmp_path):
    experts_dir = tmp_path / "experts"
    profile = _profile()
    ExpertStore(base_path=str(experts_dir)).save(profile)
    outside_file = tmp_path / "outside-beliefs.json"
    outside_file.write_text('{"beliefs": {}}', encoding="utf-8")
    beliefs_file = experts_dir / "agent_harness_expert" / "beliefs" / "beliefs.json"
    try:
        beliefs_file.symlink_to(outside_file)
    except OSError:
        pytest.skip("file symlinks are not available on this platform")
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(experts_dir))

    result = CliRunner().invoke(cli, ["expert", "next", profile.name, "--json"])

    assert result.exit_code != 0
    assert "storage failed safety validation" in result.output


def test_next_reads_exact_validated_file_when_symlink_changes_basename(monkeypatch, tmp_path):
    experts_dir = tmp_path / "experts"
    profile = _profile()
    ExpertStore(base_path=str(experts_dir)).save(profile)
    expert_dir = experts_dir / "agent_harness_expert"
    alt_dir = expert_dir / "alt"
    alt_dir.mkdir()
    safe_file = alt_dir / "safe.json"
    safe_file.write_text('{"beliefs": {}}', encoding="utf-8")
    outside_file = tmp_path / "outside-beliefs.json"
    belief = Belief(claim="Unvalidated claim", confidence=0.9, domain=profile.domain)
    outside_file.write_text(
        json.dumps({"beliefs": {belief.id: belief.to_dict()}}),
        encoding="utf-8",
    )
    try:
        (expert_dir / "beliefs" / "beliefs.json").symlink_to(safe_file)
        (alt_dir / "beliefs.json").symlink_to(outside_file)
    except OSError:
        pytest.skip("file symlinks are not available on this platform")
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(experts_dir))

    result = CliRunner().invoke(cli, ["expert", "next", profile.name, "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["evidence"]["claim_count"] == 0


def test_monitor_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "monitor", "--help"])

    assert result.exit_code == 0
    assert "metacognitive proposals" in result.output.lower()


def test_promote_monitor_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "promote-monitor", "--help"])

    assert result.exit_code == 0
    assert "reviewed metacognitive monitor proposal" in result.output.lower()


def test_propose_self_model_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "propose-self-model", "--help"])

    assert result.exit_code == 0
    assert "self-model update record" in result.output.lower()


def test_accept_self_model_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "accept-self-model", "--help"])

    assert result.exit_code == 0
    assert "acceptance for a self-model update record" in result.output.lower()


def test_self_model_json_output():
    with _patch_store(_profile()):
        result = CliRunner().invoke(expert_self_model, ["Agent Harness Expert", "--focus-limit", "1", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-expert-self-model-v1"
    assert payload["kind"] == "deepr.expert.self_model"
    assert payload["expert"]["name"] == "Agent Harness Expert"
    assert len(payload["current_focus_packet"]["selected_beliefs"]) == 1


def test_self_model_text_output():
    with _patch_store(_profile()):
        result = CliRunner().invoke(expert_self_model, ["Agent Harness Expert"])

    assert result.exit_code == 0, result.output
    assert "Expert Self-Model" in result.output
    assert "Current goals" in result.output
    assert "Unresolved risks" in result.output


def test_self_model_missing_expert_exits_nonzero():
    with _patch_store(None):
        result = CliRunner().invoke(expert_self_model, ["Ghost Expert"])

    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_monitor_json_output(monkeypatch):
    profile = _profile()
    payload = {
        "schema_version": "deepr-metacognitive-monitor-v1",
        "kind": "deepr.expert.metacognitive_monitor",
        "expert_name": profile.name,
        "proposal_count": 0,
        "signals": {
            "failed_loop_count": 0,
            "consult_trace_candidate_count": 0,
        },
        "proposals": [],
    }

    class FakeLoopStore:
        def __init__(self, name):
            assert name == profile.name

        def list_runs(self, *, limit):
            assert limit == 5
            return []

    monkeypatch.setattr("deepr.experts.loop_runs.ExpertLoopRunStore", FakeLoopStore)
    monkeypatch.setattr(
        "deepr.experts.metacognitive_monitor.build_consult_trace_candidates_for_expert",
        lambda expert_name, **kwargs: {"candidate_count": 0, "candidates": []},
    )
    monkeypatch.setattr(
        "deepr.experts.metacognitive_monitor.build_metacognitive_monitor_report",
        lambda loaded_profile, **kwargs: payload,
    )

    with _patch_store(profile):
        result = CliRunner().invoke(expert_monitor, [profile.name, "--limit", "5", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["kind"] == "deepr.expert.metacognitive_monitor"


def test_monitor_zero_limit_skips_loop_runs(monkeypatch):
    profile = _profile()
    captured = {}
    payload = {
        "schema_version": "deepr-metacognitive-monitor-v1",
        "kind": "deepr.expert.metacognitive_monitor",
        "expert_name": profile.name,
        "proposal_count": 0,
        "signals": {
            "failed_loop_count": 0,
            "consult_trace_candidate_count": 0,
        },
        "proposals": [],
    }

    class FakeLoopStore:
        def __init__(self, name):
            assert name == profile.name

        def list_runs(self, *, limit):
            raise AssertionError(f"zero limit should skip loop-run loading, got {limit}")

    def fake_candidates(expert_name, **kwargs):
        captured["candidate_kwargs"] = kwargs
        assert expert_name == profile.name
        return {"candidate_count": 0, "candidates": []}

    def fake_report(loaded_profile, **kwargs):
        captured["report_kwargs"] = kwargs
        assert loaded_profile is profile
        return payload

    monkeypatch.setattr("deepr.experts.loop_runs.ExpertLoopRunStore", FakeLoopStore)
    monkeypatch.setattr(
        "deepr.experts.metacognitive_monitor.build_consult_trace_candidates_for_expert",
        fake_candidates,
    )
    monkeypatch.setattr(
        "deepr.experts.metacognitive_monitor.build_metacognitive_monitor_report",
        fake_report,
    )

    with _patch_store(profile):
        result = CliRunner().invoke(expert_monitor, [profile.name, "--limit", "0", "--json"])

    assert result.exit_code == 0, result.output
    assert captured["candidate_kwargs"]["limit"] == 0
    assert captured["report_kwargs"]["loop_runs"] == []


def test_promote_monitor_json_output(monkeypatch):
    profile = _profile()
    captured = {}
    payload = {
        "schema_version": "deepr-metacognitive-promotion-v1",
        "kind": "deepr.expert.metacognitive_promotion",
        "expert_name": profile.name,
        "proposal_id": "meta_123",
        "proposal_type": "gap_or_eval_candidate",
        "target": "eval",
        "applied": True,
        "status": "promoted",
        "actions": [],
        "source": {"monitor_schema_version": "deepr-metacognitive-monitor-v1", "evidence_refs": []},
    }

    def fake_promote(loaded_profile, proposal_id, **kwargs):
        captured["proposal_id"] = proposal_id
        captured["kwargs"] = kwargs
        assert loaded_profile is profile
        return payload

    monkeypatch.setattr("deepr.experts.monitor_promotion.promote_monitor_proposal", fake_promote)

    with _patch_store(profile):
        result = CliRunner().invoke(
            expert_promote_monitor,
            [profile.name, "meta_123", "--target", "eval", "--apply", "--json"],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["kind"] == "deepr.expert.metacognitive_promotion"
    assert captured["proposal_id"] == "meta_123"
    assert captured["kwargs"]["target"] == "eval"
    assert captured["kwargs"]["apply"] is True


def test_propose_self_model_json_output(monkeypatch):
    profile = _profile()
    captured = {}
    payload = {
        "schema_version": "deepr-expert-self-model-update-v1",
        "kind": "deepr.expert.self_model_update",
        "expert_name": profile.name,
        "proposal_id": "meta_self",
        "proposal_type": "self_model_review",
        "target": "self_model.blocked_capabilities",
        "applied": True,
        "status": "recorded",
        "proposed_update": {
            "title": "Review blockers",
            "rationale": "Measured blockers require review.",
            "expected_effect": "Clarify next action.",
        },
        "verifier": {"status": "passed", "checks": []},
        "source": {"monitor_schema_version": "deepr-metacognitive-monitor-v1", "evidence_refs": ["self_model:v1"]},
        "actions": [],
    }

    def fake_propose(loaded_profile, proposal_id, **kwargs):
        captured["proposal_id"] = proposal_id
        captured["kwargs"] = kwargs
        assert loaded_profile is profile
        return payload

    monkeypatch.setattr("deepr.experts.self_model_updates.propose_self_model_update", fake_propose)

    with _patch_store(profile):
        result = CliRunner().invoke(
            expert_propose_self_model,
            [profile.name, "meta_self", "--apply", "--json", "--output-dir", "data/self_model_updates"],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["kind"] == "deepr.expert.self_model_update"
    assert captured["proposal_id"] == "meta_self"
    assert captured["kwargs"]["apply"] is True
    assert captured["kwargs"]["output_dir"].as_posix() == "data/self_model_updates"


def test_accept_self_model_json_output(monkeypatch, tmp_path):
    profile = _profile()
    captured = {}
    record_path = tmp_path / "record.json"
    payload = {
        "schema_version": "deepr-expert-self-model-update-acceptance-v1",
        "kind": "deepr.expert.self_model_update_acceptance",
        "expert_name": profile.name,
        "proposal_id": "meta_self",
        "proposal_type": "self_model_review",
        "target": "self_model.blocked_capabilities",
        "applied": True,
        "status": "accepted",
        "accepted_update": {
            "title": "Review blockers",
            "update_kind": "review_blockers_and_risks",
            "expected_effect": "Clarify next action.",
        },
        "policy_gate": {"status": "passed", "checks": []},
        "review": {"reviewer": "operator", "outcome_evidence_refs": ["loop_run:loop_123"]},
        "actions": [],
    }

    def fake_accept(path, **kwargs):
        captured["path"] = path
        captured["kwargs"] = kwargs
        return payload

    monkeypatch.setattr("deepr.experts.self_model_updates.accept_self_model_update_record", fake_accept)

    with _patch_store(profile):
        result = CliRunner().invoke(
            expert_accept_self_model,
            [
                profile.name,
                str(record_path),
                "--outcome-evidence",
                "loop_run:loop_123",
                "--reviewer",
                "operator",
                "--apply",
                "--json",
            ],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["kind"] == "deepr.expert.self_model_update_acceptance"
    assert captured["path"] == record_path
    assert captured["kwargs"]["expert_name"] == profile.name
    assert captured["kwargs"]["outcome_evidence_refs"] == ["loop_run:loop_123"]
    assert captured["kwargs"]["reviewer"] == "operator"
    assert captured["kwargs"]["apply"] is True
