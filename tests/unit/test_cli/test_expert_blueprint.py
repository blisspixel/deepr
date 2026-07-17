"""CLI tests for expert blueprints."""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.commands.semantic.local_expert import create_local_expert_profile
from deepr.cli.main import cli
from deepr.experts.blueprint import ExpertBlueprintStore


def _completed_template(path) -> None:
    payload = {
        "schema_version": "deepr-expert-blueprint-draft-v1",
        "kind": "deepr.expert.blueprint_draft",
        "expert_name": "Platform Expert",
        "mission": "Support evidence-backed platform decisions.",
        "non_goals": ["Approve production changes"],
        "decision_use_cases": [
            {
                "id": "architecture-choice",
                "question": "Which architecture fits the constraints?",
                "success_criteria": ["States tradeoffs"],
            }
        ],
        "source_policy": {
            "primary_sources_required": True,
            "preferred_source_types": ["Official documentation"],
            "excluded_sources": [],
        },
        "volatility": "medium",
        "update_cadence_days": 30,
        "initial_questions": ["What decisions recur?"],
        "acceptance_cases": [
            {
                "id": "held-out-choice",
                "question": "Recommend an architecture.",
                "success_criteria": ["Cites evidence"],
                "failure_conditions": ["Invents constraints"],
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_blueprint_help_is_registered() -> None:
    result = CliRunner().invoke(cli, ["expert", "blueprint", "--help"])

    assert result.exit_code == 0
    assert "purpose and acceptance contract" in result.output


def test_template_writes_an_intentionally_incomplete_file(tmp_path) -> None:
    output = tmp_path / "blueprint.json"

    result = CliRunner().invoke(
        cli,
        ["expert", "blueprint", "Platform Expert", "--template", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["expert_name"] == "Platform Expert"
    assert payload["mission"] == ""
    assert payload["schema_version"] == "deepr-expert-blueprint-draft-v1"


def test_preview_is_read_only_and_apply_is_idempotent(tmp_path, monkeypatch) -> None:
    source = tmp_path / "blueprint.json"
    _completed_template(source)
    store = ExpertBlueprintStore(tmp_path / "experts")
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_blueprint.ExpertBlueprintStore",
        lambda: store,
    )

    preview = CliRunner().invoke(
        cli,
        ["expert", "blueprint", "Platform Expert", "--from-file", str(source)],
    )
    assert preview.exit_code == 0, preview.output
    assert "Structurally valid but unreviewed" in preview.output
    assert "No human review is claimed" in preview.output
    assert store.load_all("Platform Expert") == []

    first = CliRunner().invoke(
        cli,
        [
            "expert",
            "blueprint",
            "Platform Expert",
            "--from-file",
            str(source),
            "--apply",
            "--attested-by",
            "operator",
            "--json",
        ],
    )
    second = CliRunner().invoke(
        cli,
        [
            "expert",
            "blueprint",
            "Platform Expert",
            "--from-file",
            str(source),
            "--apply",
            "--attested-by",
            "operator",
        ],
    )

    assert first.exit_code == 0, first.output
    first_payload = json.loads(first.output)
    assert first_payload["revision"] == 1
    assert first_payload["attestation"]["status"] == "operator_attested"
    assert first_payload["contract"]["human_authorship_claimed"] is False
    assert second.exit_code == 0, second.output
    assert "already matches" in second.output
    assert len(store.load_all("Platform Expert")) == 1


def test_blueprint_name_must_match_command_name(tmp_path) -> None:
    source = tmp_path / "blueprint.json"
    _completed_template(source)

    result = CliRunner().invoke(
        cli,
        ["expert", "blueprint", "Another Expert", "--from-file", str(source)],
    )

    assert result.exit_code != 0
    assert "does not match" in result.output


def test_attested_blueprint_can_precede_local_profile_creation(tmp_path, monkeypatch) -> None:
    experts_root = tmp_path / "experts"
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(experts_root))
    source = tmp_path / "blueprint.json"
    _completed_template(source)

    applied = CliRunner().invoke(
        cli,
        [
            "expert",
            "blueprint",
            "Platform Expert",
            "--from-file",
            str(source),
            "--apply",
            "--attested-by",
            "operator",
        ],
    )
    profile = create_local_expert_profile(
        name="Platform Expert",
        files=(),
        description="Platform decisions",
        local_model="test-model",
    )

    assert applied.exit_code == 0, applied.output
    assert profile.name == "Platform Expert"
    assert ExpertBlueprintStore().load_latest("Platform Expert") is not None


def test_preflight_can_be_saved_without_canonical_write(tmp_path, monkeypatch) -> None:
    source = tmp_path / "blueprint.json"
    output = tmp_path / "preflight.json"
    _completed_template(source)
    store = ExpertBlueprintStore(tmp_path / "experts")
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_blueprint.ExpertBlueprintStore",
        lambda: store,
    )

    result = CliRunner().invoke(
        cli,
        [
            "expert",
            "blueprint",
            "Platform Expert",
            "--from-file",
            str(source),
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    preflight = json.loads(output.read_text(encoding="utf-8"))
    assert json.loads(result.output) == preflight
    assert preflight["status"] == "structurally_valid_unreviewed"
    assert preflight["contract"]["authoritative_for_scope"] is False
    assert store.load_all("Platform Expert") == []


def test_preflight_cannot_overwrite_unreviewed_draft(tmp_path) -> None:
    source = tmp_path / "blueprint.json"
    _completed_template(source)
    original = source.read_text(encoding="utf-8")

    result = CliRunner().invoke(
        cli,
        [
            "expert",
            "blueprint",
            "Platform Expert",
            "--from-file",
            str(source),
            "--output",
            str(source),
        ],
    )

    assert result.exit_code != 0
    assert "must not overwrite" in result.output
    assert source.read_text(encoding="utf-8") == original
