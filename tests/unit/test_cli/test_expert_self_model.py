"""Tests for `deepr expert self-model`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from deepr.cli.commands.semantic.expert_self_model import (
    expert_monitor,
    expert_promote_monitor,
    expert_propose_self_model,
    expert_self_model,
)
from deepr.cli.main import cli
from deepr.core.contracts import Claim, ExpertManifest, Gap
from deepr.experts.profile import ExpertProfile


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
    profile.get_manifest = lambda: manifest  # type: ignore[method-assign]
    return profile


def _patch_store(profile):
    return patch(
        "deepr.cli.commands.semantic.expert_self_model.ExpertStore",
        return_value=MagicMock(load=MagicMock(return_value=profile)),
    )


def test_self_model_registered_in_expert_help():
    result = CliRunner().invoke(cli, ["expert", "self-model", "--help"])

    assert result.exit_code == 0
    assert "read-only self-model" in result.output.lower()


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
