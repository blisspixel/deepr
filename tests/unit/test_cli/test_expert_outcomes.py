"""CLI tests for operator-attested expert outcomes."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.outcomes import ExpertOutcomeStore


def _patch_stores(monkeypatch, tmp_path) -> ExpertOutcomeStore:
    profile_store = MagicMock()
    profile_store.load.return_value = SimpleNamespace(name="Platform Expert")
    outcome_store = ExpertOutcomeStore(tmp_path / "experts")
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_outcomes.ExpertStore",
        lambda: profile_store,
    )
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_outcomes.ExpertOutcomeStore",
        lambda: outcome_store,
    )
    return outcome_store


def test_outcome_commands_are_registered() -> None:
    runner = CliRunner()

    assert runner.invoke(cli, ["expert", "record-outcome", "--help"]).exit_code == 0
    assert runner.invoke(cli, ["expert", "outcomes", "--help"]).exit_code == 0


def test_record_and_list_outcome_json(tmp_path, monkeypatch) -> None:
    store = _patch_stores(monkeypatch, tmp_path)
    runner = CliRunner()
    recorded = runner.invoke(
        cli,
        [
            "expert",
            "record-outcome",
            "Platform Expert",
            "--decision-id",
            "migration-2026",
            "--summary",
            "Choose the migration architecture",
            "--result",
            "mixed",
            "--observation",
            "The cutover succeeded but exceeded its recovery target.",
            "--observed-at",
            "2026-07-15T12:00:00+00:00",
            "--attested-by",
            "operator",
            "--trace-id",
            "trace:123",
            "--belief-id",
            "belief-1",
            "--evidence-ref",
            "postmortem-42",
            "--outcome-id",
            "outcome-1",
            "--json",
        ],
    )

    assert recorded.exit_code == 0, recorded.output
    recorded_payload = json.loads(recorded.output)
    assert recorded_payload["outcome_id"] == "outcome-1"
    assert recorded_payload["contract"]["operator_attested"] is True
    assert recorded_payload["contract"]["reviewer_identity_verified"] is False
    assert len(store.load_all("Platform Expert")) == 1

    listed = runner.invoke(cli, ["expert", "outcomes", "Platform Expert", "--json"])
    assert listed.exit_code == 0, listed.output
    payload = json.loads(listed.output)
    assert payload["total_outcomes"] == 1
    assert payload["result_counts"]["mixed"] == 1
    assert payload["contract"]["semantic_quality_verdict"] is False


def test_record_outcome_requires_an_existing_expert(monkeypatch) -> None:
    profile_store = MagicMock()
    profile_store.load.return_value = None
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_outcomes.ExpertStore",
        lambda: profile_store,
    )

    result = CliRunner().invoke(
        cli,
        [
            "expert",
            "record-outcome",
            "Missing",
            "--decision-id",
            "decision-1",
            "--summary",
            "A decision",
            "--result",
            "unresolved",
            "--observation",
            "No result yet.",
            "--attested-by",
            "operator",
        ],
    )

    assert result.exit_code != 0
    assert "not found" in result.output
