"""Tests for `deepr costs doctor` - paid-spend vs artifact reconciliation.

The command exists because a 30-job research campaign once billed $37.79 with
zero surviving report artifacts, and nothing surfaced the loss for 24 days.
Every settled dollar must map to an artifact, a durable disposition, or remain
unexplained with a nonzero exit so schedulers can alarm.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr.cli.commands.costs import costs
from deepr.observability.cost_ledger import CostLedger


def _seed(
    tmp_path: Path,
    events: list[tuple[str, float, str, str]],
    *,
    operation: str = "research_completion",
) -> Path:
    ledger_path = tmp_path / "cost_ledger.jsonl"
    ledger = CostLedger(ledger_path=ledger_path)
    for index, (task_id, cost, provider, model) in enumerate(events):
        ledger.record_event(
            operation=operation,
            provider=provider,
            cost_usd=cost,
            model=model,
            task_id=task_id,
            idempotency_key=f"seed-{index}-{task_id}",
        )
    return ledger_path


def test_doctor_matches_spend_with_artifacts(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    (reports / "2026-07-25_0943_some-topic_a7ae5c65").mkdir(parents=True)
    ledger_path = _seed(tmp_path, [("research_research-a7ae5c653d8c", 0.03, "xai", "grok-4-5")])

    result = CliRunner().invoke(
        costs,
        ["doctor", "--json", "--reports-dir", str(reports), "--ledger-path", str(ledger_path)],
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["matched_spend_usd"] == 0.03
    assert payload["orphaned_spend_usd"] == 0.0
    assert payload["unexplained_spend_usd"] == 0.0
    assert payload["disposed_spend_usd"] == 0.0


def test_doctor_flags_orphaned_spend_and_exits_nonzero(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    ledger_path = _seed(
        tmp_path,
        [
            ("research_research-deadbeef1234", 1.85, "openai", "o4-mini-deep-research"),
            ("campaign-task-uuid-no-fragment", 2.10, "openai", "o3-deep-research"),
        ],
    )

    result = CliRunner().invoke(
        costs,
        ["doctor", "--json", "--reports-dir", str(reports), "--ledger-path", str(ledger_path)],
    )

    payload = json.loads(result.output)
    # A job id with no matching report dir AND an event with no linkage key at
    # all are both unexplained until a durable disposition is recorded.
    assert payload["orphaned_spend_usd"] == 3.95
    assert payload["unexplained_spend_usd"] == 3.95
    assert payload["matched_spend_usd"] == 0.0
    assert payload["disposed_spend_usd"] == 0.0
    assert result.exit_code == 1


def test_doctor_treats_disposed_spend_as_explained(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    ledger_path = _seed(
        tmp_path,
        [("portrait_Demo Expert", 0.04, "auto", "")],
        operation="portrait_generation",
    )
    dry = CliRunner().invoke(
        costs,
        [
            "dispose-unexplained",
            "--json",
            "--apply",
            "--reports-dir",
            str(reports),
            "--ledger-path",
            str(ledger_path),
        ],
    )
    assert dry.exit_code == 0
    applied = json.loads(dry.output)
    assert applied["written"] == 1

    result = CliRunner().invoke(
        costs,
        ["doctor", "--json", "--reports-dir", str(reports), "--ledger-path", str(ledger_path)],
    )
    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["disposed_spend_usd"] == 0.04
    assert payload["unexplained_spend_usd"] == 0.0
    assert payload["orphaned_spend_usd"] == 0.0
    assert payload["disposed"][0]["disposition"] == "expected_non_report"


def test_doctor_ignores_zero_cost_events(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    ledger_path = _seed(tmp_path, [("research_research-abcd12345678", 0.0, "xai", "grok-4-5")])

    result = CliRunner().invoke(
        costs,
        ["doctor", "--json", "--reports-dir", str(reports), "--ledger-path", str(ledger_path)],
    )

    payload = json.loads(result.output)
    assert payload["matched"] == [] and payload["orphaned"] == [] and payload["disposed"] == []
    assert result.exit_code == 0


def test_doctor_uses_configured_reports_root_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = tmp_path / "configured-reports"
    (reports / "2026-07-25_0943_some-topic_a7ae5c65").mkdir(parents=True)
    ledger_path = _seed(tmp_path, [("research_research-a7ae5c653d8c", 0.03, "xai", "grok-4-5")])
    monkeypatch.setattr("deepr.config.load_config", lambda: {"results_dir": str(reports)})

    result = CliRunner().invoke(costs, ["doctor", "--json", "--ledger-path", str(ledger_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["matched_spend_usd"] == 0.03
    assert payload["orphaned_spend_usd"] == 0.0


def test_parent_budget_cli_lists_and_replays(tmp_path: Path) -> None:
    from deepr.experts.parent_budget_store import DurableParentBudget

    ledger_path = tmp_path / "cost_ledger.jsonl"
    ledger_path.write_text("", encoding="utf-8")
    journal = tmp_path / "parent_budget_transactions.jsonl"
    durable = DurableParentBudget.open(
        surface="fill_gaps",
        parent_ceiling_usd=0.5,
        run_id="run-cli-1",
        path=journal,
    )
    child = durable.admit_child(operation="gap", max_usd=0.2, child_id="c1")
    durable.settle_child(child.child_id, 0.1)
    durable.close()

    listed = CliRunner().invoke(
        costs,
        ["parent-budget", "--json", "--ledger-path", str(ledger_path)],
    )
    assert listed.exit_code == 0
    listed_payload = json.loads(listed.output)
    assert listed_payload["count"] >= 3

    replayed = CliRunner().invoke(
        costs,
        ["parent-budget", "--json", "--run-id", "run-cli-1", "--ledger-path", str(ledger_path)],
    )
    assert replayed.exit_code == 0
    replay_payload = json.loads(replayed.output)
    assert replay_payload["found"] is True
    assert replay_payload["transaction"]["state"] == "closed"
    assert replay_payload["transaction"]["settled_usd"] == 0.1


def test_doctor_fails_closed_on_malformed_canonical_ledger(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    ledger_path = tmp_path / "cost_ledger.jsonl"
    ledger_path.write_text('{"operation":', encoding="utf-8")

    result = CliRunner().invoke(
        costs,
        ["doctor", "--reports-dir", str(reports), "--ledger-path", str(ledger_path)],
    )

    assert result.exit_code == 1
    assert "integrity status is UNKNOWN" in result.output
