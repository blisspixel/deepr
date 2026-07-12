"""Loop-run recording for explicit health-check mutations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepr.experts.loop_runs import ExpertLoopRun


def record_completed_health_archive(expert_name: str, *, archived_count: int, cancelled: bool = False) -> ExpertLoopRun:
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    if cancelled:
        status = LoopRunStatus.CANCELLED
        stop_reason = LoopStopReason.CANCELLED
    else:
        status = LoopRunStatus.COMPLETED
        stop_reason = LoopStopReason.VERIFIER_PASSED if archived_count else LoopStopReason.NO_DUE_WORK

    return record_loop_run(
        expert_name=expert_name,
        loop_type="health_check",
        goal=f"Archive stale beliefs for {expert_name}",
        trigger="manual",
        status=status,
        stop_reason=stop_reason,
        budget_spent=0.0,
        capacity_source="local",
        accepted_changes=max(archived_count, 0),
    )
