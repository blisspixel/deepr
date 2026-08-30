"""CLI tests for operator-attested expert outcomes."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.outcomes import ExpertOutcomeDraft, ExpertOutcomeStore
from deepr.experts.position_ledger import PositionLedger, PositionVersion


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
    assert runner.invoke(cli, ["expert", "experience", "--help"]).exit_code == 0


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


def test_experience_command_joins_outcomes_and_predictions(tmp_path, monkeypatch) -> None:
    store = _patch_stores(monkeypatch, tmp_path)
    trace = {
        "trace_id": "trace:123",
        "status": "completed",
        "recorded_at": "2026-07-01T00:00:00+00:00",
        "input": {"question": "Which architecture?", "question_hash": "a" * 64},
        "output": {"experts_consulted": ["Platform Expert"]},
    }
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_outcomes.load_consult_traces_by_id",
        lambda trace_ids: [trace] if trace_ids == {"trace:123"} else [],
    )
    ledger_path = tmp_path / "hold" / "history.json"
    ledger_path.parent.mkdir(parents=True)
    ledger = PositionLedger(
        expert_name="Platform Expert",
        versions=[
            PositionVersion(
                thread_id="thread-1",
                version_id="version-1",
                question="Will it work?",
                stance="Likely.",
                would_change_my_mind="A failed deployment.",
                falsifier_resolution_criterion="The deployment fails its acceptance test.",
                falsifier_resolution_date="2027-01-01",
                recorded_at="2026-07-01T00:00:00+00:00",
            )
        ],
    )
    ledger_path.write_text(json.dumps(ledger.to_dict()), encoding="utf-8")
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_outcomes.hold_history_path",
        lambda _name: ledger_path,
    )
    store.record(
        ExpertOutcomeDraft.model_validate(
            {
                "expert_name": "Platform Expert",
                "decision_id": "decision-1",
                "decision_summary": "Choose the architecture",
                "result": "mixed",
                "observation": "The deployment worked with one recovery issue.",
                "observed_at": "2026-07-15T00:00:00+00:00",
                "attested_by": "operator",
                "consult_trace_id": "trace:123",
            }
        ),
        outcome_id="outcome-1",
    )

    result = CliRunner().invoke(cli, ["expert", "experience", "Platform Expert", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["cases"][0]["consult"]["status"] == "matched"
    assert payload["counts"]["registered_predictions"] == 1
    assert payload["contract"]["automatic_learning"] is False
