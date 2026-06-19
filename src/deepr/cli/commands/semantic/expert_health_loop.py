"""Loop-run recording for completed expert health checks."""

from __future__ import annotations

from typing import Any


def record_completed_health_check(report: Any):
    from deepr.cli.commands.semantic.expert_health_schedule import scheduled_health_action_plan
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    plan = scheduled_health_action_plan(report)
    status = str(getattr(report, "status", "") or "")
    if status == "critical":
        loop_status = LoopRunStatus.FAILED
        stop_reason = LoopStopReason.VERIFIER_FAILED
    elif plan["status"] == "no_actions":
        loop_status = LoopRunStatus.COMPLETED
        stop_reason = LoopStopReason.NO_DUE_WORK
    elif plan["status"] == "waiting_for_confirmation":
        loop_status = LoopRunStatus.WAITING
        stop_reason = LoopStopReason.HUMAN_GATE_REQUIRED
    elif plan["status"] == "waiting_for_capacity":
        loop_status = LoopRunStatus.WAITING
        stop_reason = LoopStopReason.CAPACITY_UNAVAILABLE
    else:
        loop_status = LoopRunStatus.PENDING
        stop_reason = None

    return record_loop_run(
        expert_name=report.expert_name,
        loop_type="health_check",
        goal=f"Audit health-check actions for {report.expert_name}",
        trigger="manual",
        status=loop_status,
        stop_reason=stop_reason,
        next_action=plan["actions"][0] if plan["actions"] else {},
        capacity_source="local",
        rejected_changes=1 if stop_reason == LoopStopReason.VERIFIER_FAILED else 0,
        verifier_id="health_check",
        verifier_outcome=status,
    )


def record_completed_health_archive(expert_name: str, *, archived_count: int, cancelled: bool = False):
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
