"""Tests for dashboard loop-status rollups."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deepr.experts.loop_runs import ExpertLoopRun, ExpertLoopRunStore, LoopRunStatus, LoopStopReason
from deepr.experts.loop_status_rollup import build_loop_status_rollup


BASE_TIME = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


def _run(
    run_id: str,
    *,
    loop_type: str,
    status: LoopRunStatus,
    minutes: int,
    stop_reason: LoopStopReason | None = None,
    trigger: str = "manual",
    next_action: dict | None = None,
    budget_spent: float = 0.0,
    accepted_changes: int = 0,
    rejected_changes: int = 0,
    capacity_source: str = "",
) -> ExpertLoopRun:
    return ExpertLoopRun(
        run_id=run_id,
        expert_name="Platform Expert",
        loop_type=loop_type,
        goal=f"{loop_type} goal",
        trigger=trigger,
        status=status,
        updated_at=BASE_TIME + timedelta(minutes=minutes),
        stop_reason=stop_reason,
        next_action=next_action or {},
        budget_spent=budget_spent,
        accepted_changes=accepted_changes,
        rejected_changes=rejected_changes,
        capacity_source=capacity_source,
    )


def test_rollup_summarizes_latest_window(tmp_path):
    store = ExpertLoopRunStore("Platform Expert", path=tmp_path / "loop_runs.jsonl")
    store.append(
        _run(
            "loop_sync",
            loop_type="sync",
            status=LoopRunStatus.COMPLETED,
            minutes=1,
            stop_reason=LoopStopReason.VERIFIER_PASSED,
            budget_spent=0.2,
            accepted_changes=2,
            rejected_changes=1,
            capacity_source="local-ollama",
        )
    )
    store.append(
        _run(
            "loop_health",
            loop_type="health-check",
            status=LoopRunStatus.WAITING,
            minutes=2,
            stop_reason=LoopStopReason.HUMAN_GATE_REQUIRED,
            trigger="scheduled",
            next_action={"title": "Confirm archive", "status": "waiting_for_confirmation"},
        )
    )
    store.append(
        _run(
            "loop_reflect",
            loop_type="reflection",
            status=LoopRunStatus.FAILED,
            minutes=3,
            stop_reason=LoopStopReason.VERIFIER_FAILED,
            budget_spent=0.1,
            accepted_changes=1,
            capacity_source="api",
        )
    )

    rollup = build_loop_status_rollup("Platform Expert", store=store, limit=10)

    assert rollup["count"] == 3
    assert rollup["latest_run"]["run_id"] == "loop_reflect"
    assert rollup["last_sync_result"]["run_id"] == "loop_sync"
    assert rollup["last_failure"]["run_id"] == "loop_reflect"
    assert rollup["next_scheduled_action"]["run_id"] == "loop_health"
    assert rollup["status_counts"]["completed"] == 1
    assert rollup["status_counts"]["waiting"] == 1
    assert rollup["loop_type_counts"] == {"reflection": 1, "health-check": 1, "sync": 1}
    assert rollup["stop_reason_counts"]["verifier_failed"] == 1
    assert rollup["capacity_source_counts"] == {"api": 1, "unspecified": 1, "local-ollama": 1}
    assert rollup["latest_capacity_source"] == "api"
    assert rollup["budget_spent_total"] == 0.3
    assert rollup["accepted_changes_total"] == 3
    assert rollup["rejected_changes_total"] == 1
    assert rollup["acceptance_rate"] == 0.75
    assert rollup["cost_per_accepted_change"] == 0.1
    assert rollup["verifier_failure_count"] == 1


def test_rollup_rejects_non_positive_limit(tmp_path):
    store = ExpertLoopRunStore("Platform Expert", path=tmp_path / "loop_runs.jsonl")

    with pytest.raises(ValueError, match="limit must be positive"):
        build_loop_status_rollup("Platform Expert", store=store, limit=0)
