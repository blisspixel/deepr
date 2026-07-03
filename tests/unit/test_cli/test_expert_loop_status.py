"""Tests for `deepr expert loop-status`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.loop_runs import ExpertLoopRun, LoopRunStatus, LoopStopReason


def _run() -> ExpertLoopRun:
    return ExpertLoopRun(
        run_id="loop_123",
        expert_name="Platform Expert",
        loop_type="health-check",
        goal="audit and action stale beliefs",
        trigger="scheduled",
        status=LoopRunStatus.WAITING,
        updated_at=datetime(2026, 6, 19, tzinfo=UTC),
        stop_reason=LoopStopReason.HUMAN_GATE_REQUIRED,
        next_action={"status": "confirm", "title": "Archive stale beliefs"},
    )


def test_loop_status_help():
    result = CliRunner().invoke(cli, ["expert", "loop-status", "--help"])

    assert result.exit_code == 0
    assert "loop" in result.output.lower()


def test_loop_status_missing_expert():
    with patch("deepr.experts.profile.ExpertStore") as mock_store_class:
        mock_store = MagicMock()
        mock_store.load.return_value = None
        mock_store_class.return_value = mock_store

        result = CliRunner().invoke(cli, ["expert", "loop-status", "Ghost"])

    assert result.exit_code == 2
    assert "not found" in result.output.lower()


def test_loop_status_renders_capacity_outlook():
    profile = SimpleNamespace(name="Platform Expert")
    payload = {
        "runs": [],
        "next_run_outlook": {
            "task_classes": {
                "sync": {
                    "local_capacity_admitted": True,
                    "plan_capacity_admitted": False,
                    "admitted_local_models": ["qwen-local"],
                    "admitted_plan_backends": [],
                },
                "reflect": {
                    "local_capacity_admitted": False,
                    "plan_capacity_admitted": False,
                    "admitted_local_models": [],
                    "admitted_plan_backends": [],
                },
            },
        },
    }
    with (
        patch("deepr.experts.profile.ExpertStore") as mock_store_class,
        patch("deepr.experts.loop_status_rollup.build_loop_status_rollup", return_value=payload),
    ):
        mock_store = MagicMock()
        mock_store.load.return_value = profile
        mock_store_class.return_value = mock_store

        result = CliRunner().invoke(cli, ["expert", "loop-status", "Platform Expert"])

    assert result.exit_code == 0
    assert "Next-run capacity" in result.output
    # sync has local capacity admitted; reflect falls to metered.
    assert "qwen-local" in result.output
    assert "metered budget" in result.output


def test_loop_status_escapes_markup_in_model_names():
    # A model name with Rich-special characters must not crash the render or be
    # swallowed as console markup; it is escaped and shown literally.
    profile = SimpleNamespace(name="Platform Expert")
    payload = {
        "runs": [],
        "next_run_outlook": {
            "task_classes": {
                "sync": {
                    "local_capacity_admitted": True,
                    "plan_capacity_admitted": False,
                    "admitted_local_models": ["weird[/]tag:q4"],
                    "admitted_plan_backends": [],
                },
            },
        },
    }
    with (
        patch("deepr.experts.profile.ExpertStore") as mock_store_class,
        patch("deepr.experts.loop_status_rollup.build_loop_status_rollup", return_value=payload),
    ):
        mock_store = MagicMock()
        mock_store.load.return_value = profile
        mock_store_class.return_value = mock_store

        result = CliRunner().invoke(cli, ["expert", "loop-status", "Platform Expert"])

    assert result.exit_code == 0, result.output
    assert "weird[/]tag:q4" in result.output


def test_loop_status_shows_due_subscriptions_with_escaped_topics():
    profile = SimpleNamespace(name="Platform Expert")
    payload = {
        "runs": [],
        "due_subscriptions": {"count": 2, "topics": ["Model routing", "weird[/]topic"]},
    }
    with (
        patch("deepr.experts.profile.ExpertStore") as mock_store_class,
        patch("deepr.experts.loop_status_rollup.build_loop_status_rollup", return_value=payload),
    ):
        mock_store = MagicMock()
        mock_store.load.return_value = profile
        mock_store_class.return_value = mock_store

        result = CliRunner().invoke(cli, ["expert", "loop-status", "Platform Expert"])

    assert result.exit_code == 0, result.output
    assert "Due subscriptions: 2" in result.output
    assert "Model routing" in result.output
    # Operator-controlled topic with markup chars renders literally, not stripped.
    assert "weird[/]topic" in result.output


def test_loop_status_shows_no_due_subscriptions():
    profile = SimpleNamespace(name="Platform Expert")
    payload = {"runs": [], "due_subscriptions": {"count": 0, "topics": []}}
    with (
        patch("deepr.experts.profile.ExpertStore") as mock_store_class,
        patch("deepr.experts.loop_status_rollup.build_loop_status_rollup", return_value=payload),
    ):
        mock_store = MagicMock()
        mock_store.load.return_value = profile
        mock_store_class.return_value = mock_store

        result = CliRunner().invoke(cli, ["expert", "loop-status", "Platform Expert"])

    assert result.exit_code == 0, result.output
    assert "Due subscriptions: none" in result.output


def test_loop_status_json_reads_latest_runs():
    with (
        patch("deepr.experts.profile.ExpertStore") as mock_store_class,
        patch("deepr.experts.loop_status_rollup.ExpertLoopRunStore") as mock_store_type,
    ):
        profile = MagicMock()
        profile.name = "Platform Expert"
        mock_expert_store = MagicMock()
        mock_expert_store.load.return_value = profile
        mock_store_class.return_value = mock_expert_store
        mock_loop_store = MagicMock()
        mock_loop_store.list_runs.return_value = [_run()]
        mock_store_type.return_value = mock_loop_store

        result = CliRunner().invoke(cli, ["expert", "loop-status", "Platform Expert", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "deepr-loop-status-v1"
    assert payload["kind"] == "deepr.expert.loop_status"
    assert payload["expert_name"] == "Platform Expert"
    assert payload["count"] == 1
    assert payload["window"]["limit"] == 5
    assert payload["status_counts"]["waiting"] == 1
    assert payload["next_scheduled_action"]["run_id"] == "loop_123"
    assert payload["runs"][0]["run_id"] == "loop_123"
    assert payload["runs"][0]["stop_reason"] == "human_gate_required"
