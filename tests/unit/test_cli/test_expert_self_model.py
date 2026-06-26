"""Tests for `deepr expert self-model`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from deepr.cli.commands.semantic.expert_self_model import expert_self_model
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
