"""Durable waits for scheduled local-capacity contention."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from subprocess import list2cmdline
from typing import Any

from deepr.backends.local_capacity import (
    LocalCapacityObservation,
    LocalCapacityUnavailableReason,
)
from deepr.experts.loop_runs import (
    ExpertLoopRun,
    ExpertLoopRunStore,
    LoopRunStatus,
    LoopStopReason,
    new_loop_run_id,
)

LOCAL_BUSY_RETRY_DELAYS_SECONDS = (30 * 60, 2 * 60 * 60, 6 * 60 * 60)


@dataclass(frozen=True)
class ScheduledLocalCapacityWait:
    loop_run: ExpertLoopRun
    retry_after_seconds: int
    retry_at: datetime
    consecutive_busy_waits: int
    requested_operation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "capacity_unavailable_reason": LocalCapacityUnavailableReason.GPU_BUSY.value,
            "retry_after_seconds": self.retry_after_seconds,
            "retry_at": self.retry_at.isoformat(),
            "consecutive_busy_waits": self.consecutive_busy_waits,
            "requested_operation": self.requested_operation,
            "loop_run": self.loop_run.to_dict(),
        }


def _is_local_busy_wait(run: ExpertLoopRun, *, loop_type: str) -> bool:
    return (
        run.loop_type == loop_type
        and run.trigger == "scheduled"
        and run.status == LoopRunStatus.WAITING
        and run.stop_reason == LoopStopReason.CAPACITY_UNAVAILABLE
        and run.run_context.get("capacity_unavailable_reason") == LocalCapacityUnavailableReason.GPU_BUSY.value
    )


def consecutive_local_busy_waits(
    store: ExpertLoopRunStore,
    *,
    loop_type: str,
    limit: int = 100,
) -> int:
    """Count the uninterrupted local-busy wait suffix for one expert loop."""
    count = 0
    for run in store.list_runs(loop_type=loop_type, limit=limit):
        if not _is_local_busy_wait(run, loop_type=loop_type):
            break
        count += 1
    return count


def local_busy_retry_delay_seconds(previous_busy_waits: int) -> int:
    if previous_busy_waits < 0:
        raise ValueError("previous_busy_waits must be non-negative")
    index = min(previous_busy_waits, len(LOCAL_BUSY_RETRY_DELAYS_SECONDS) - 1)
    return LOCAL_BUSY_RETRY_DELAYS_SECONDS[index]


def record_scheduled_local_capacity_wait(
    *,
    expert_name: str,
    loop_type: str,
    goal: str,
    observation: LocalCapacityObservation,
    command_argv: list[str],
    budget_limit: float | None = None,
    base_run_context: dict[str, Any] | None = None,
    capacity_source: str = "local",
    backend_profile_id: str = "",
    now: datetime | None = None,
    store: ExpertLoopRunStore | None = None,
) -> ScheduledLocalCapacityWait:
    """Append a typed local-busy WAITING outcome without sleeping or fallback."""
    from deepr.backends.local_capacity import LocalCapacityState

    if observation.state != LocalCapacityState.BUSY:
        raise ValueError("a scheduled local-capacity wait requires a busy observation")
    if not command_argv or any(not argument for argument in command_argv):
        raise ValueError("command_argv must contain non-empty arguments")
    observed_at = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    run_store = store or ExpertLoopRunStore(expert_name)
    previous_waits = consecutive_local_busy_waits(run_store, loop_type=loop_type)
    delay = local_busy_retry_delay_seconds(previous_waits)
    retry_at = observed_at + timedelta(seconds=delay)
    consecutive_waits = previous_waits + 1
    retry = {
        "capacity_unavailable_reason": LocalCapacityUnavailableReason.GPU_BUSY.value,
        "retry_after_seconds": delay,
        "retry_at": retry_at.isoformat(),
        "consecutive_busy_waits": consecutive_waits,
    }
    requested_operation = {
        "command_argv": list(command_argv),
        "capacity_source": capacity_source,
        "backend_profile_id": backend_profile_id,
    }
    run_context = dict(base_run_context or {})
    run_context.update(retry)
    run_context["local_capacity"] = observation.to_dict()
    run_context["requested_operation"] = requested_operation
    next_action = {
        "status": "waiting_for_local_capacity",
        "title": "Retry when the local GPU is less busy",
        "detail": observation.detail,
        "command": list2cmdline(command_argv),
        "command_argv": [list(command_argv)],
        **retry,
    }
    loop_run = ExpertLoopRun(
        run_id=new_loop_run_id(),
        expert_name=expert_name,
        loop_type=loop_type,
        goal=goal,
        trigger="scheduled",
        status=LoopRunStatus.WAITING,
        started_at=observed_at,
        updated_at=observed_at,
        stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
        next_action=next_action,
        budget_limit=budget_limit,
        budget_spent=0.0,
        capacity_source=capacity_source,
        backend_profile_id=backend_profile_id,
        run_context=run_context,
    )
    run_store.append(loop_run)
    return ScheduledLocalCapacityWait(
        loop_run=loop_run,
        retry_after_seconds=delay,
        retry_at=retry_at,
        consecutive_busy_waits=consecutive_waits,
        requested_operation=requested_operation,
    )


__all__ = [
    "LOCAL_BUSY_RETRY_DELAYS_SECONDS",
    "ScheduledLocalCapacityWait",
    "consecutive_local_busy_waits",
    "local_busy_retry_delay_seconds",
    "record_scheduled_local_capacity_wait",
]
