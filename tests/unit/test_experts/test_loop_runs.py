"""Tests for durable ExpertLoopRun records."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from deepr.experts.loop_runs import (
    ExpertLoopRun,
    ExpertLoopRunStore,
    LoopRunStatus,
    LoopStopReason,
    record_loop_run,
)


def _run(run_id: str = "loop_1", *, status: LoopRunStatus = LoopRunStatus.WAITING) -> ExpertLoopRun:
    return ExpertLoopRun(
        run_id=run_id,
        expert_name="Platform Expert",
        loop_type="sync",
        goal="refresh subscribed topics",
        trigger="scheduled",
        status=status,
        updated_at=datetime(2026, 6, 19, tzinfo=UTC),
        budget_limit=2.0,
        budget_spent=0.0,
        capacity_source="local",
        accepted_changes=2,
        rejected_changes=1,
        stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
        next_action={"status": "wait", "title": "Wait for cheap capacity"},
        run_context={"self_model": {"status": "available"}},
    )


def test_loop_run_round_trips_metrics():
    run = _run()

    payload = run.to_dict()
    restored = ExpertLoopRun.from_dict(payload)

    assert restored == run
    assert payload["acceptance_rate"] == 0.6667
    assert payload["cost_per_accepted_change"] == 0.0
    assert payload["stop_reason"] == "capacity_unavailable"
    assert payload["run_context"] == {"self_model": {"status": "available"}}


def test_loop_run_validates_required_fields():
    with pytest.raises(ValueError, match="goal is required"):
        ExpertLoopRun(
            run_id="loop_1",
            expert_name="Platform Expert",
            loop_type="sync",
            goal=" ",
            trigger="scheduled",
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("schema_version", True),
        ("iteration_count", True),
        ("iteration_count", -1),
        ("max_iterations", 0),
        ("budget_limit", float("nan")),
        ("budget_spent", float("inf")),
        ("accepted_changes", 1.5),
        ("rejected_changes", True),
        ("verifier_score", float("nan")),
        ("verifier_threshold", float("inf")),
    ],
)
def test_loop_run_rejects_malformed_numeric_fields(field_name, value):
    with pytest.raises(ValueError, match=field_name):
        replace(_run(), **{field_name: value})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("schema_version", "1"),
        ("iteration_count", "1"),
        ("max_iterations", True),
        ("budget_limit", "2.0"),
        ("budget_spent", False),
        ("accepted_changes", "2"),
        ("rejected_changes", 1.5),
        ("verifier_score", "0.8"),
        ("verifier_threshold", float("nan")),
    ],
)
def test_loop_run_from_dict_does_not_coerce_malformed_numeric_fields(field_name, value):
    payload = _run().to_dict()
    payload[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        ExpertLoopRun.from_dict(payload)


@pytest.mark.parametrize("field_name", ["started_at", "updated_at", "finished_at"])
def test_loop_run_rejects_timezone_naive_timestamps(field_name):
    with pytest.raises(ValueError, match=field_name):
        replace(_run(), **{field_name: datetime(2026, 7, 15, 12, 0)})


def test_loop_run_from_dict_rejects_timezone_naive_timestamp():
    payload = _run().to_dict()
    payload["updated_at"] = "2026-07-15T12:00:00"

    with pytest.raises(ValueError, match="updated_at"):
        ExpertLoopRun.from_dict(payload)


def test_terminal_loop_run_requires_typed_stop_reason():
    with pytest.raises(ValueError, match="terminal loop runs require a typed stop_reason"):
        ExpertLoopRun(
            run_id="loop_1",
            expert_name="Platform Expert",
            loop_type="sync",
            goal="refresh subscribed topics",
            trigger="scheduled",
            status=LoopRunStatus.COMPLETED,
        )


def test_pending_loop_run_can_omit_stop_reason():
    run = ExpertLoopRun(
        run_id="loop_1",
        expert_name="Platform Expert",
        loop_type="sync",
        goal="refresh subscribed topics",
        trigger="scheduled",
        status=LoopRunStatus.PENDING,
    )

    assert run.stop_reason is None
    assert run.is_terminal is False


def test_completed_loop_run_rejects_wait_stop_reason():
    with pytest.raises(ValueError, match="completed loop runs cannot use stop_reason capacity_unavailable"):
        ExpertLoopRun(
            run_id="loop_1",
            expert_name="Platform Expert",
            loop_type="sync",
            goal="refresh subscribed topics",
            trigger="scheduled",
            status=LoopRunStatus.COMPLETED,
            stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
        )


def test_waiting_loop_run_rejects_completion_stop_reason():
    with pytest.raises(ValueError, match="waiting loop runs cannot use stop_reason verifier_passed"):
        ExpertLoopRun(
            run_id="loop_1",
            expert_name="Platform Expert",
            loop_type="sync",
            goal="refresh subscribed topics",
            trigger="scheduled",
            status=LoopRunStatus.WAITING,
            stop_reason=LoopStopReason.VERIFIER_PASSED,
        )


def test_waiting_loop_run_accepts_overlap_locked_stop_reason():
    run = ExpertLoopRun(
        run_id="loop_1",
        expert_name="Platform Expert",
        loop_type="sync",
        goal="refresh subscribed topics",
        trigger="scheduled",
        status=LoopRunStatus.WAITING,
        stop_reason=LoopStopReason.OVERLAP_LOCKED,
    )

    assert run.stop_reason == LoopStopReason.OVERLAP_LOCKED
    assert run.to_dict()["stop_reason"] == "overlap_locked"


def test_store_collapses_append_only_snapshots(tmp_path):
    path = tmp_path / "loop_runs.jsonl"
    store = ExpertLoopRunStore("Platform Expert", path=path)
    first = _run(status=LoopRunStatus.WAITING)
    second = replace(
        first,
        status=LoopRunStatus.COMPLETED,
        updated_at=first.updated_at + timedelta(minutes=5),
        stop_reason=LoopStopReason.NO_DUE_WORK,
    )

    store.append(first)
    store.append(second)

    runs = store.list_runs()
    assert len(runs) == 1
    assert runs[0].status == LoopRunStatus.COMPLETED
    assert runs[0].stop_reason == LoopStopReason.NO_DUE_WORK
    assert store.list_runs(status=LoopRunStatus.WAITING) == []


def test_store_ignores_corrupt_lines(tmp_path):
    path = tmp_path / "loop_runs.jsonl"
    store = ExpertLoopRunStore("Platform Expert", path=path)
    store.append(_run())
    path.write_text(path.read_text(encoding="utf-8") + "not json\n", encoding="utf-8")

    assert len(store.list_runs()) == 1


def test_store_ignores_snapshot_with_non_finite_metrics(tmp_path):
    path = tmp_path / "loop_runs.jsonl"
    store = ExpertLoopRunStore("Platform Expert", path=path)
    original = _run()
    store.append(original)
    malformed = original.to_dict()
    malformed["budget_spent"] = float("nan")
    path.write_text(path.read_text(encoding="utf-8") + json.dumps(malformed) + "\n", encoding="utf-8")

    assert store.list_runs() == [original]


@pytest.mark.parametrize("limit", [True, 0, -1, 1.5])
def test_store_rejects_non_positive_or_non_integer_limit(tmp_path, limit):
    store = ExpertLoopRunStore("Platform Expert", path=tmp_path / "loop_runs.jsonl")

    with pytest.raises(ValueError, match="limit"):
        store.list_runs(limit=limit)


def test_record_loop_run_appends_snapshot():
    with patch("deepr.experts.loop_runs.ExpertLoopRunStore") as store_class:
        store = MagicMock()
        store.append.side_effect = lambda run: run
        store_class.return_value = store

        run = record_loop_run(
            expert_name="Platform Expert",
            loop_type="sync",
            goal="Refresh subscribed topics",
            trigger="scheduled",
            status=LoopRunStatus.WAITING,
            stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
            next_action={"status": "wait"},
            run_context={"self_model": {"status": "available"}},
            budget_limit=1.5,
            budget_spent=0.25,
            capacity_source="owned/prepaid",
            accepted_changes=2,
            rejected_changes=1,
            verifier_id="reflection",
            verifier_version="gpt-5-mini",
            verifier_outcome="accept",
            verifier_score=0.84,
        )

    assert run.run_id.startswith("loop_")
    assert run.status == LoopRunStatus.WAITING
    assert run.stop_reason == LoopStopReason.CAPACITY_UNAVAILABLE
    assert run.next_action == {"status": "wait"}
    assert run.run_context == {"self_model": {"status": "available"}}
    assert run.budget_spent == 0.25
    assert run.accepted_changes == 2
    assert run.rejected_changes == 1
    assert run.verifier_id == "reflection"
    assert run.verifier_version == "gpt-5-mini"
    assert run.verifier_outcome == "accept"
    assert run.verifier_score == 0.84
    store_class.assert_called_once_with("Platform Expert")
    store.append.assert_called_once_with(run)
