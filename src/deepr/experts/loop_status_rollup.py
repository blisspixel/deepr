"""Dashboard-ready summaries over durable expert loop-run records."""

from __future__ import annotations

from collections import Counter
from typing import Any

from deepr.experts.loop_runs import ExpertLoopRun, ExpertLoopRunStore, LoopRunStatus, LoopStopReason


def _round_metric(value: float) -> float:
    return round(value, 4)


def _run_or_none(run: ExpertLoopRun | None) -> dict[str, Any] | None:
    return run.to_dict() if run else None


def _first_run(runs: list[ExpertLoopRun], predicate) -> ExpertLoopRun | None:
    for run in runs:
        if predicate(run):
            return run
    return None


def build_loop_status_rollup(
    expert_name: str,
    *,
    limit: int = 20,
    store: ExpertLoopRunStore | None = None,
) -> dict[str, Any]:
    """Return a deterministic status rollup for dashboard and API consumers."""
    if limit < 1:
        raise ValueError("limit must be positive")

    loop_store = store or ExpertLoopRunStore(expert_name)
    runs = loop_store.list_runs(limit=limit)
    status_counts = Counter(run.status.value for run in runs)
    loop_type_counts = Counter(run.loop_type for run in runs)
    stop_reason_counts = Counter(run.stop_reason.value for run in runs if run.stop_reason)
    capacity_source_counts = Counter((run.capacity_source or "unspecified") for run in runs)
    accepted_total = sum(run.accepted_changes for run in runs)
    rejected_total = sum(run.rejected_changes for run in runs)
    attempted_total = accepted_total + rejected_total
    budget_spent_total = sum(run.budget_spent for run in runs)

    latest_capacity_source = next((run.capacity_source for run in runs if run.capacity_source), "")
    failure_stops = {
        LoopStopReason.TOOL_FAILURE,
        LoopStopReason.VERIFIER_FAILED,
        LoopStopReason.SCHEMA_ERROR,
    }
    last_failure = _first_run(
        runs,
        lambda run: run.status == LoopRunStatus.FAILED or run.stop_reason in failure_stops,
    )
    next_scheduled_action = _first_run(
        runs,
        lambda run: (
            run.trigger == "scheduled"
            and run.status in {LoopRunStatus.PENDING, LoopRunStatus.WAITING}
            and bool(run.next_action)
        ),
    )

    return {
        "expert_name": expert_name,
        "count": len(runs),
        "window": {"limit": limit, "summarized_runs": len(runs)},
        "latest_run": _run_or_none(runs[0] if runs else None),
        "last_sync_result": _run_or_none(_first_run(runs, lambda run: run.loop_type == "sync")),
        "last_failure": _run_or_none(last_failure),
        "next_scheduled_action": _run_or_none(next_scheduled_action),
        "latest_capacity_source": latest_capacity_source,
        "status_counts": {status.value: status_counts.get(status.value, 0) for status in LoopRunStatus},
        "loop_type_counts": dict(loop_type_counts),
        "stop_reason_counts": {reason.value: stop_reason_counts.get(reason.value, 0) for reason in LoopStopReason},
        "capacity_source_counts": dict(capacity_source_counts),
        "budget_spent_total": _round_metric(budget_spent_total),
        "accepted_changes_total": accepted_total,
        "rejected_changes_total": rejected_total,
        "acceptance_rate": _round_metric(accepted_total / attempted_total) if attempted_total else 0.0,
        "cost_per_accepted_change": _round_metric(budget_spent_total / accepted_total) if accepted_total else 0.0,
        "verifier_failure_count": stop_reason_counts.get(LoopStopReason.VERIFIER_FAILED.value, 0),
        "runs": [run.to_dict() for run in runs],
    }
