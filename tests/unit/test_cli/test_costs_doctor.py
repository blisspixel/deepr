"""Tests for `deepr costs doctor` - paid-spend vs artifact reconciliation.

The command exists because a 30-job research campaign once billed $37.79 with
zero surviving report artifacts, and nothing surfaced the loss for 24 days.
Every settled dollar must map to an artifact on disk or be flagged as orphaned,
with a nonzero exit so schedulers can alarm.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr.cli.commands.costs import costs
from deepr.observability.cost_ledger import CostLedger


def _seed(tmp_path: Path, events: list[tuple[str, float, str, str]]) -> Path:
    ledger_path = tmp_path / "cost_ledger.jsonl"
    ledger = CostLedger(ledger_path=ledger_path)
    for task_id, cost, provider, model in events:
        ledger.record_event(
            operation="research_completion",
            provider=provider,
            cost_usd=cost,
            model=model,
            task_id=task_id,
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
    # all are both orphaned: unlinkable spend is the disease being surfaced.
    assert payload["orphaned_spend_usd"] == 3.95
    assert payload["matched_spend_usd"] == 0.0
    assert result.exit_code == 1


def test_doctor_ignores_zero_cost_events(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    ledger_path = _seed(tmp_path, [("research_research-abcd12345678", 0.0, "xai", "grok-4-5")])

    result = CliRunner().invoke(
        costs,
        ["doctor", "--json", "--reports-dir", str(reports), "--ledger-path", str(ledger_path)],
    )

    payload = json.loads(result.output)
    assert payload["matched"] == [] and payload["orphaned"] == []
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
