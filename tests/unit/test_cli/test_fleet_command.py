"""CLI-layer tests for `deepr fleet status`.

The rollup itself is unit-tested in test_fleet_status.py; here we exercise only
the command layer - rendering, --json, exit codes - by injecting the payload.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

import deepr.cli.commands.fleet as fleet_mod
from deepr.cli.commands.fleet import fleet


def _payload(experts, *, attention=0, waiting=0, refresh_due=0, never_run=0):
    return {
        "schema_version": "deepr-fleet-status-v1",
        "kind": "deepr.expert.fleet_status",
        "summary": {
            "experts": len(experts),
            "attention": attention,
            "waiting": waiting,
            "refresh_due": refresh_due,
            "never_run": never_run,
            "budget_spent_window_total": 0.0,
        },
        "experts": experts,
    }


def _row(name, **over):
    base = {
        "expert": name,
        "has_runs": True,
        "last_run": {
            "loop_type": "sync",
            "status": "completed",
            "accepted_changes": 2,
            "rejected_changes": 0,
            "budget_spent": 0.0,
            "capacity_source": "local",
        },
        "last_failure": None,
        "waiting_next_action": None,
        "subscriptions": 0,
        "refresh_due": 0,
        "due_topics": [],
        "budget_spent_window": 0.0,
        "attention": False,
        "waiting": False,
    }
    base.update(over)
    return base


def _patch(monkeypatch, payload):
    monkeypatch.setattr(fleet_mod, "build_fleet_status_rollup", lambda **_: payload)


def test_status_json_emits_versioned_payload(monkeypatch):
    _patch(monkeypatch, _payload([_row("Healthy")]))
    result = CliRunner().invoke(fleet, ["status", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["schema_version"] == "deepr-fleet-status-v1"


def test_status_human_empty_roster(monkeypatch):
    _patch(monkeypatch, _payload([]))
    result = CliRunner().invoke(fleet, ["status"])
    assert result.exit_code == 0
    assert "No experts yet" in result.output


def test_status_healthy_reports_no_attention(monkeypatch):
    _patch(monkeypatch, _payload([_row("Healthy")]))
    result = CliRunner().invoke(fleet, ["status"])
    assert result.exit_code == 0
    assert "No experts need attention" in result.output


def test_status_exits_nonzero_on_attention(monkeypatch):
    row = _row(
        "Broken",
        attention=True,
        last_run={
            "loop_type": "sync",
            "status": "failed",
            "accepted_changes": 0,
            "rejected_changes": 0,
            "budget_spent": 0.0,
            "capacity_source": "local",
        },
        last_failure={"failure_reason": "tool exploded", "stop_reason": "tool_failure"},
    )
    _patch(monkeypatch, _payload([row], attention=1))
    result = CliRunner().invoke(fleet, ["status"])
    assert result.exit_code == 1
    assert "FAILED" in result.output
    assert "tool exploded" in result.output


def test_status_renders_refresh_due_and_waiting(monkeypatch):
    rows = [
        _row("Stale", refresh_due=2, due_topics=["LLMs", "Chips"]),
        _row(
            "Paused",
            waiting=True,
            waiting_next_action={"title": "Wait for capacity"},
        ),
    ]
    _patch(monkeypatch, _payload(rows, waiting=1, refresh_due=1))
    result = CliRunner().invoke(fleet, ["status"])
    assert result.exit_code == 0
    assert "refresh due" in result.output
    assert "Wait for capacity" in result.output


def test_status_rejects_nonpositive_limit():
    result = CliRunner().invoke(fleet, ["status", "--limit", "0"])
    assert result.exit_code == 2
