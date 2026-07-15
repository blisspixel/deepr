"""Tests for the zero-cost durable expert-conversation evaluator."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.evals.conversation import (
    CONVERSATION_EVAL_KIND,
    CONVERSATION_EVAL_SCHEMA_VERSION,
    DEFAULT_MAX_CONTEXT_BYTES,
    DEFAULT_RETENTION_DAYS,
    FROZEN_COMPARISON_MANIFEST,
    MAX_RECENT_TURNS,
    MAX_RETENTION_DAYS,
    conversation_contract_fixtures,
    run_conversation_eval,
    write_conversation_eval_report,
)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _isolate_runtime(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runtime = root / "runtime"
    monkeypatch.setenv("DEEPR_DATA_DIR", str(runtime))
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(runtime / "experts"))
    monkeypatch.setenv("DEEPR_REPORTS_PATH", str(runtime / "reports"))
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(runtime / "costs"))
    monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(runtime / "capacity"))
    monkeypatch.setenv("DEEPR_QUEUE_DB_PATH", str(runtime / "queue" / "research_queue.db"))
    monkeypatch.setenv("HOME", str(root / "home"))
    monkeypatch.setenv("USERPROFILE", str(root / "home"))
    return runtime


def test_conversation_eval_structural_cases_pass() -> None:
    report = run_conversation_eval()
    data = report.to_dict()

    assert data["schema_version"] == CONVERSATION_EVAL_SCHEMA_VERSION
    assert data["kind"] == CONVERSATION_EVAL_KIND
    assert data["cost_usd"] == 0.0
    assert data["semantic_review_status"] == "unreviewed"
    assert data["contract"] == {
        "execution_mode": "frozen_fixture",
        "capacity_mode": "local_only",
        "provider_calls": 0,
        "backend_calls": 0,
        "expert_store_reads": 0,
        "network_access": False,
        "fallback_policy": "none",
        "live_metered_fallback": False,
        "cost_usd": 0.0,
        "writes_runtime_state": False,
        "semantic_verdict": False,
    }
    assert data["policy"] == {
        "default_retention_days": DEFAULT_RETENTION_DAYS,
        "maximum_retention_days": MAX_RETENTION_DAYS,
        "maximum_recent_turns": MAX_RECENT_TURNS,
        "default_max_context_bytes": DEFAULT_MAX_CONTEXT_BYTES,
        "content_deletion": "immediate_logical_removal",
        "audit_event_retention": "hashes_and_lifecycle_only",
    }
    assert report.total_cases == 12
    assert report.failed_cases == 0
    assert report.score == 1.0
    assert all(outcome.to_dict()["semantic_verdict"] is False for outcome in report.outcomes)


def test_conversation_comparison_is_structural_and_context_bounded() -> None:
    one_shot = FROZEN_COMPARISON_MANIFEST["repeated_one_shot"]
    durable = FROZEN_COMPARISON_MANIFEST["durable_conversation"]

    assert len(one_shot["calls"]) == len(durable["turns"]) == 2
    assert one_shot["application_context_carried"] is False
    assert durable["application_context_carried"] is True
    assert durable["turns"][1]["visible_prior_turn_ids"] == [durable["turns"][0]["turn_id"]]
    assert FROZEN_COMPARISON_MANIFEST["comparison_status"] == "structural_only"
    assert FROZEN_COMPARISON_MANIFEST["semantic_quality_review"] == "unreviewed"


def test_contract_fixtures_are_fresh_copies() -> None:
    first = conversation_contract_fixtures()
    second = conversation_contract_fixtures()

    first["conversation"]["expert_names"].append("mutated")
    first["context_snapshot"]["expert_snapshots"][0]["packet"]["gaps"].append("mutated")

    assert second["conversation"]["expert_names"] == ["reliability_engineering"]
    assert second["context_snapshot"]["expert_snapshots"][0]["packet"]["gaps"] == ["Outcome calibration is pending."]


def test_conversation_eval_does_not_write_or_open_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runtime = _isolate_runtime(tmp_path, monkeypatch)
    marker = tmp_path / "existing.txt"
    marker.write_text("preserve", encoding="utf-8")
    before = _snapshot(tmp_path)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("frozen evaluator must not open network connections")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)

    run_conversation_eval()

    assert _snapshot(tmp_path) == before
    assert not runtime.exists()


def test_conversation_report_write_is_explicit_and_confined(tmp_path: Path) -> None:
    output_dir = tmp_path / "allowed" / "benchmarks"
    marker = tmp_path / "existing.txt"
    marker.write_text("preserve", encoding="utf-8")
    before = _snapshot(tmp_path)

    path = write_conversation_eval_report(run_conversation_eval(), output_dir=output_dir)
    after = _snapshot(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert set(after) - set(before) == {path.relative_to(tmp_path).as_posix()}
    assert all(after[name] == content for name, content in before.items())
    assert path.parent == output_dir
    assert path.name.startswith("conversation_eval_")
    assert payload["schema_version"] == CONVERSATION_EVAL_SCHEMA_VERSION


def test_eval_conversation_cli_json_is_zero_cost_and_does_not_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runtime = _isolate_runtime(tmp_path, monkeypatch)

    result = CliRunner().invoke(cli, ["eval", "conversation", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["failed_cases"] == 0
    assert payload["cost_usd"] == 0.0
    assert "saved_to" not in payload
    assert not runtime.exists()


def test_eval_conversation_cli_save_uses_runtime_benchmarks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runtime = _isolate_runtime(tmp_path, monkeypatch)

    result = CliRunner().invoke(cli, ["eval", "conversation", "--json", "--save"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    saved = Path(payload["saved_to"])
    assert saved.parent == runtime / "benchmarks"
    assert saved.exists()
