from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deepr.backends.local_capacity import LocalCapacityObservation, LocalCapacityState
from deepr.experts.loop_runs import (
    ExpertLoopRun,
    ExpertLoopRunStore,
    LoopRunStatus,
    LoopStopReason,
)
from deepr.experts.scheduled_local_capacity import record_scheduled_local_capacity_wait

T0 = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)
BUSY = LocalCapacityObservation(
    state=LocalCapacityState.BUSY,
    source="nvidia-smi",
    detail="local GPU capacity is busy",
    gpu_utilization_percent=(87.0,),
)
SYNC_ARGV = ["deepr", "expert", "sync", "GPU Expert", "--local", "--scheduled"]


def test_busy_wait_records_typed_capacity_outcome_and_retry(tmp_path):
    store = ExpertLoopRunStore("GPU Expert", path=tmp_path / "loop_runs.jsonl")

    wait = record_scheduled_local_capacity_wait(
        expert_name="GPU Expert",
        loop_type="sync",
        goal="Sync due subscriptions for GPU Expert",
        observation=BUSY,
        command_argv=SYNC_ARGV,
        budget_limit=0.5,
        now=T0,
        store=store,
    )

    assert wait.retry_after_seconds == 1800
    assert wait.retry_at == T0 + timedelta(minutes=30)
    assert wait.loop_run.status == LoopRunStatus.WAITING
    assert wait.loop_run.stop_reason == LoopStopReason.CAPACITY_UNAVAILABLE
    assert wait.loop_run.capacity_source == "local"
    assert wait.loop_run.budget_spent == 0.0
    assert wait.loop_run.run_context["capacity_unavailable_reason"] == "local_gpu_busy"
    assert wait.loop_run.run_context["local_capacity"]["state"] == "busy"
    assert wait.loop_run.next_action["retry_after_seconds"] == 1800
    assert wait.loop_run.next_action["command_argv"] == [SYNC_ARGV]
    assert wait.requested_operation["command_argv"] == SYNC_ARGV
    assert store.latest() == wait.loop_run


def test_busy_wait_adapts_30m_then_2h_then_6h_and_caps(tmp_path):
    store = ExpertLoopRunStore("GPU Expert", path=tmp_path / "loop_runs.jsonl")

    waits = [
        record_scheduled_local_capacity_wait(
            expert_name="GPU Expert",
            loop_type="sync",
            goal="Sync due subscriptions",
            observation=BUSY,
            command_argv=SYNC_ARGV,
            now=T0 + timedelta(minutes=index),
            store=store,
        )
        for index in range(4)
    ]

    assert [wait.retry_after_seconds for wait in waits] == [1800, 7200, 21600, 21600]
    assert [wait.consecutive_busy_waits for wait in waits] == [1, 2, 3, 4]


def test_nonbusy_loop_outcome_resets_adaptive_delay(tmp_path):
    store = ExpertLoopRunStore("GPU Expert", path=tmp_path / "loop_runs.jsonl")
    first = record_scheduled_local_capacity_wait(
        expert_name="GPU Expert",
        loop_type="sync",
        goal="Sync due subscriptions",
        observation=BUSY,
        command_argv=SYNC_ARGV,
        now=T0,
        store=store,
    )
    assert first.retry_after_seconds == 1800
    store.append(
        ExpertLoopRun(
            run_id="loop_completed",
            expert_name="GPU Expert",
            loop_type="sync",
            goal="Sync due subscriptions",
            trigger="scheduled",
            status=LoopRunStatus.COMPLETED,
            started_at=T0 + timedelta(minutes=1),
            updated_at=T0 + timedelta(minutes=1),
            finished_at=T0 + timedelta(minutes=1),
            stop_reason=LoopStopReason.NO_DUE_WORK,
        )
    )

    after_reset = record_scheduled_local_capacity_wait(
        expert_name="GPU Expert",
        loop_type="sync",
        goal="Sync due subscriptions",
        observation=BUSY,
        command_argv=SYNC_ARGV,
        now=T0 + timedelta(minutes=2),
        store=store,
    )

    assert after_reset.retry_after_seconds == 1800
    assert after_reset.consecutive_busy_waits == 1


def test_nonbusy_observation_cannot_be_recorded_as_busy_wait(tmp_path):
    store = ExpertLoopRunStore("GPU Expert", path=tmp_path / "loop_runs.jsonl")
    free = LocalCapacityObservation(
        state=LocalCapacityState.FREE,
        source="nvidia-smi",
        detail="free",
    )

    try:
        record_scheduled_local_capacity_wait(
            expert_name="GPU Expert",
            loop_type="sync",
            goal="Sync due subscriptions",
            observation=free,
            command_argv=SYNC_ARGV,
            now=T0,
            store=store,
        )
    except ValueError as exc:
        assert "busy observation" in str(exc)
    else:
        raise AssertionError("expected ValueError")
