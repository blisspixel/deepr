"""CLI-layer tests for `deepr fleet status`.

The rollup itself is unit-tested in test_fleet_status.py; here we exercise only
the command layer - rendering, --json, exit codes - by injecting the payload.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

import deepr.cli.commands.fleet as fleet_mod
from deepr.cli.commands.fleet import fleet


def _payload(
    experts,
    *,
    attention=0,
    waiting=0,
    refresh_due=0,
    never_run=0,
    state_errors=None,
):
    errors = state_errors or {"profiles": 0, "runs": 0, "subscriptions": 0}
    complete = not any(errors.values())
    status = "blocked_storage_state" if not complete else "attention_required" if attention else "completed"
    observed = {
        "experts": len(experts),
        "attention": attention,
        "waiting": waiting,
        "refresh_due": refresh_due,
        "never_run": never_run,
        "budget_spent_window_total": 0.0,
    }
    run_totals_known = errors["profiles"] == 0 and errors["runs"] == 0
    subscription_totals_known = errors["profiles"] == 0 and errors["subscriptions"] == 0
    return {
        "schema_version": "deepr-fleet-status-v2",
        "kind": "deepr.expert.fleet_status",
        "complete": complete,
        "status": status,
        "exit_code": 0 if complete and attention == 0 else 1,
        "state_errors": errors,
        "state_error_refs": [],
        "state_error_refs_omitted": 0,
        "next_action": None if complete else {"kind": "repair_local_expert_state", "requires_manual_repair": True},
        "summary": {
            "experts": len(experts),
            "attention": attention if run_totals_known else None,
            "waiting": waiting if run_totals_known else None,
            "refresh_due": refresh_due if subscription_totals_known else None,
            "never_run": never_run if run_totals_known else None,
            "state_errors": sum(errors.values()),
            "budget_spent_window_total": 0.0 if run_totals_known else None,
            "observed": observed,
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
        "state_errors": [],
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
    assert parsed["schema_version"] == "deepr-fleet-status-v2"


def test_status_human_empty_roster(monkeypatch):
    _patch(monkeypatch, _payload([]))
    result = CliRunner().invoke(fleet, ["status"])
    assert result.exit_code == 0
    assert "No experts yet" in result.output


def test_status_healthy_reports_no_attention(monkeypatch):
    _patch(monkeypatch, _payload([_row("Healthy")]))
    result = CliRunner().invoke(fleet, ["status"])
    assert result.exit_code == 0
    assert "No latest-run failures or unreadable expert state detected" in result.output


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


def test_status_incomplete_state_is_visible_and_nonzero(monkeypatch):
    row = _row(
        "Unreadable",
        has_runs=None,
        last_run=None,
        subscriptions=None,
        refresh_due=None,
        due_topics=None,
        attention=None,
        waiting=None,
        state_errors=["runs_unreadable", "subscriptions_unreadable"],
    )
    payload = _payload(
        [row],
        state_errors={"profiles": 1, "runs": 1, "subscriptions": 1},
    )
    _patch(monkeypatch, payload)

    human = CliRunner().invoke(fleet, ["status"])
    machine = CliRunner().invoke(fleet, ["status", "--json"])

    assert human.exit_code == 1
    assert "Fleet status is incomplete" in human.output
    assert "UNREADABLE" in human.output
    assert "Inspect the listed source under the configured experts root" in human.output
    assert "observed readable state" in human.output
    assert "No experts yet" not in human.output
    assert "No latest-run failures" not in human.output
    assert machine.exit_code == 1
    assert json.loads(machine.output)["status"] == "blocked_storage_state"


def test_status_human_neutralizes_stored_markup_and_controls(monkeypatch):
    row = _row(
        "[/red]\nFORGED",
        refresh_due=1,
        due_topics=["[bold]topic[/bold]\tNEXT"],
        attention=True,
        last_failure={"failure_reason": "[/green]\rREASON", "stop_reason": "tool_failure"},
    )
    _patch(monkeypatch, _payload([row], attention=1, refresh_due=1))

    result = CliRunner().invoke(fleet, ["status"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "[/red]\\nFORGED" in result.output
    assert "[bold]topic[/bold]\\tNEXT" in result.output
    assert "[/green]\\rREASON" in result.output
    assert "\nFORGED\n" not in result.output


def test_status_corrupt_only_roster_never_looks_empty(monkeypatch):
    payload = _payload([], state_errors={"profiles": 1, "runs": 0, "subscriptions": 0})
    _patch(monkeypatch, payload)

    result = CliRunner().invoke(fleet, ["status"])

    assert result.exit_code == 1
    assert "Fleet status is incomplete: 1 unreadable profile source" in result.output
    assert "0 readable experts" in result.output
    assert "No experts yet" not in result.output


def test_status_invalid_root_emits_clean_machine_envelope(tmp_path, monkeypatch):
    invalid_root = tmp_path / "experts"
    invalid_root.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(invalid_root))

    result = CliRunner().invoke(fleet, ["status", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "blocked_storage_state"
    assert payload["state_errors"]["profiles"] == 1
    assert payload["state_error_refs"] == [{"kind": "profiles_unreadable", "source": "experts-root"}]
    assert str(tmp_path) not in result.output


def test_status_rejects_nonpositive_limit():
    result = CliRunner().invoke(fleet, ["status", "--limit", "0"])
    assert result.exit_code == 2


class TestInstallSchedule:
    def test_prints_systemd_recipe_and_install_steps(self):
        result = CliRunner().invoke(fleet, ["install-schedule", "--platform", "systemd"])
        assert result.exit_code == 0
        assert "deepr-fleet.timer" in result.output
        assert "Persistent=true" in result.output
        assert "systemctl --user enable --now" in result.output

    def test_prints_windows_recipe(self):
        result = CliRunner().invoke(fleet, ["install-schedule", "--platform", "windows"])
        assert result.exit_code == 0
        assert "MultipleInstancesPolicy>IgnoreNew" in result.output
        assert "schtasks /Create" in result.output

    def test_custom_command_flows_into_recipe(self):
        result = CliRunner().invoke(
            fleet,
            ["install-schedule", "--platform", "cron", "--command", "deepr expert sync 'AI' --scheduled -y"],
        )
        assert result.exit_code == 0
        assert "deepr expert sync 'AI' --scheduled -y" in result.output

    def test_invalid_time_exits_two(self):
        result = CliRunner().invoke(fleet, ["install-schedule", "--platform", "cron", "--at", "9pm"])
        assert result.exit_code == 2
        assert "HH:MM" in result.output

    def test_output_dir_writes_files(self, tmp_path):
        result = CliRunner().invoke(
            fleet,
            ["install-schedule", "--platform", "systemd", "--output", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert (tmp_path / "deepr-fleet.service").exists()
        assert (tmp_path / "deepr-fleet.timer").exists()
        assert "Wrote" in result.output
