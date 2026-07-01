"""Loop-run recording for completed expert reflection."""

from __future__ import annotations

from typing import Any


def _status_for_reflection(
    verdict: str,
    *,
    failed_count: int,
    skipped_count: int,
    cancelled_followups: bool,
):
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason

    if cancelled_followups:
        return LoopRunStatus.WAITING, LoopStopReason.HUMAN_GATE_REQUIRED
    if failed_count:
        return LoopRunStatus.FAILED, LoopStopReason.TOOL_FAILURE
    if skipped_count:
        return LoopRunStatus.WAITING, LoopStopReason.BUDGET_EXHAUSTED
    if verdict == "skipped":
        return LoopRunStatus.COMPLETED, LoopStopReason.NO_DUE_WORK
    if verdict == "accept":
        return LoopRunStatus.COMPLETED, LoopStopReason.VERIFIER_PASSED
    return LoopRunStatus.FAILED, LoopStopReason.VERIFIER_FAILED


def record_completed_reflection_loop(
    expert_name: str,
    report_id: str,
    report: Any,
    *,
    budget: float,
    execute_followups: bool,
    fill_result: Any | None = None,
    cancelled_followups: bool = False,
):
    from deepr.experts.loop_runs import LoopStopReason, record_loop_run

    outcomes = list(getattr(fill_result, "outcomes", []) or [])
    failed = [o for o in outcomes if getattr(o, "status", "") == "failed"]
    skipped = [o for o in outcomes if getattr(o, "status", "") == "skipped"]
    accepted = sum(
        max(int(getattr(o, "absorbed", 0) or 0), 0) + max(int(getattr(o, "flagged", 0) or 0), 0) for o in outcomes
    )
    verdict = str(getattr(report, "verdict", "") or "").strip().lower()
    score = float(getattr(report, "overall_score", 0.0) or 0.0)
    status, stop_reason = _status_for_reflection(
        verdict,
        failed_count=len(failed),
        skipped_count=len(skipped),
        cancelled_followups=cancelled_followups,
    )
    next_action: dict[str, Any] = {}
    if stop_reason == LoopStopReason.HUMAN_GATE_REQUIRED:
        next_action = {
            "status": "human_gate_required",
            "title": "Confirm reflection follow-ups",
            "command": f'deepr expert reflect "{expert_name}" "{report_id}" --execute-followups --budget {budget:.2f} -y',
        }
    elif stop_reason == LoopStopReason.TOOL_FAILURE:
        next_action = {
            "status": "inspect",
            "title": "Inspect failed reflection follow-ups",
            "detail": f"{len(failed)} follow-up query result(s) failed during absorption.",
        }
    elif stop_reason == LoopStopReason.BUDGET_EXHAUSTED:
        next_action = {
            "status": "increase_budget",
            "title": "Rerun follow-ups with enough budget",
            "detail": f"{len(skipped)} follow-up query result(s) were skipped after the budget was exhausted.",
        }
    elif stop_reason == LoopStopReason.VERIFIER_FAILED:
        next_action = {
            "status": "revise_or_research",
            "title": "Revise or re-research before absorbing",
            "detail": f"Reflection verdict was {verdict or 'unknown'} with score {score:.2f}.",
        }

    rejected = len(failed) + (1 if stop_reason == LoopStopReason.VERIFIER_FAILED else 0)
    return record_loop_run(
        expert_name=expert_name,
        loop_type="reflection_followups",
        goal=f"Reflect on report {report_id} and run follow-ups",
        trigger="manual",
        status=status,
        stop_reason=stop_reason,
        next_action=next_action,
        budget_limit=budget if execute_followups else None,
        budget_spent=float(getattr(fill_result, "total_cost", 0.0) or 0.0),
        capacity_source="none" if verdict == "skipped" and fill_result is None else "api_metered",
        accepted_changes=accepted,
        rejected_changes=rejected,
        verifier_id="reflection",
        verifier_version=str(getattr(report, "model", "") or ""),
        verifier_outcome=verdict,
        verifier_score=score,
    )


def record_reflection_overlap_loop(
    expert_name: str,
    report_id: str,
    *,
    budget: float,
    scheduled: bool = False,
):
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    return record_loop_run(
        expert_name=expert_name,
        loop_type="reflection_followups",
        goal=f"Reflect on report {report_id} and run follow-ups",
        trigger="scheduled" if scheduled else "manual",
        status=LoopRunStatus.WAITING,
        stop_reason=LoopStopReason.OVERLAP_LOCKED,
        next_action={
            "status": "wait",
            "title": "Wait for current reflection follow-ups",
            "detail": "Another reflection follow-up run for this expert already holds the overlap guard.",
        },
        budget_limit=budget,
        budget_spent=0.0,
        capacity_source="api_metered",
    )
