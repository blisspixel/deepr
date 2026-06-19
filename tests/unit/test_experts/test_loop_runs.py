"""Tests for durable ExpertLoopRun records."""

from __future__ import annotations

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
    )


def test_loop_run_round_trips_metrics():
    run = _run()

    payload = run.to_dict()
    restored = ExpertLoopRun.from_dict(payload)

    assert restored == run
    assert payload["acceptance_rate"] == 0.6667
    assert payload["cost_per_accepted_change"] == 0.0
    assert payload["stop_reason"] == "capacity_unavailable"


def test_loop_run_validates_required_fields():
    with pytest.raises(ValueError, match="goal is required"):
        ExpertLoopRun(
            run_id="loop_1",
            expert_name="Platform Expert",
            loop_type="sync",
            goal=" ",
            trigger="scheduled",
        )


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
    assert run.budget_spent == 0.25
    assert run.accepted_changes == 2
    assert run.rejected_changes == 1
    assert run.verifier_id == "reflection"
    assert run.verifier_version == "gpt-5-mini"
    assert run.verifier_outcome == "accept"
    assert run.verifier_score == 0.84
    store_class.assert_called_once_with("Platform Expert")
    store.append.assert_called_once_with(run)
