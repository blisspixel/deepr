"""Cross-expert fleet health rollup (read-only, $0).

Folds each expert's durable loop-run history (``loop_runs.jsonl``) and topic
subscription cadence (``subscriptions.json``) into one roster view: per expert,
the latest loop run's status, what it changed, what it cost on which capacity,
its most recent failure, whether knowledge refresh is due (overdue per the
configured cadence), and what (if anything) is waiting. Derived purely from
existing on-disk records - it never runs a loop, never spends, and never mutates
state.

The per-expert ``loop_status_rollup`` and the plan-quota ``capacity fleet`` view
answer different questions; neither gives the operator one roster-wide answer to
"is my fleet healthy?". This module does, with no new storage.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from deepr.experts.loop_runs import ExpertLoopRun, ExpertLoopRunStore, LoopRunStatus, LoopStopReason
from deepr.experts.sync import SubscriptionStore
from deepr.security.output_safety import sanitize_host_facing_payload

FLEET_STATUS_SCHEMA_VERSION = "deepr-fleet-status-v1"
FLEET_STATUS_KIND = "deepr.expert.fleet_status"

# Runs whose terminal/stop state means a human or fix is needed, not just "wait".
_FAILURE_STOPS = frozenset(
    {
        LoopStopReason.TOOL_FAILURE,
        LoopStopReason.VERIFIER_FAILED,
        LoopStopReason.SCHEMA_ERROR,
        LoopStopReason.MAX_ITERATIONS,
    }
)

LoopStoreFactory = Callable[[str], ExpertLoopRunStore]
SubscriptionStoreFactory = Callable[[str], SubscriptionStore]


def _round(value: float) -> float:
    return round(value, 4)


def _is_failure(run: ExpertLoopRun) -> bool:
    return run.status == LoopRunStatus.FAILED or run.stop_reason in _FAILURE_STOPS


def _compact_run(run: ExpertLoopRun) -> dict[str, Any]:
    """The handful of fields the roster view needs, not the full record."""
    return {
        "run_id": run.run_id,
        "loop_type": run.loop_type,
        "status": run.status.value,
        "stop_reason": run.stop_reason.value if run.stop_reason else None,
        "trigger": run.trigger,
        "at": run.updated_at.isoformat(),
        "capacity_source": run.capacity_source or "unspecified",
        "budget_spent": _round(run.budget_spent),
        "accepted_changes": run.accepted_changes,
        "rejected_changes": run.rejected_changes,
        "acceptance_rate": _round(run.acceptance_rate),
        "failure_reason": run.failure_reason,
    }


def _expert_row(
    expert_name: str,
    *,
    loop_store: ExpertLoopRunStore,
    subscription_store: SubscriptionStore,
    now: datetime,
    limit: int,
) -> dict[str, Any]:
    """One roster row: loop-run health + refresh cadence for a single expert."""
    runs = loop_store.list_runs(limit=limit)
    latest = runs[0] if runs else None
    last_failure = next((run for run in runs if _is_failure(run)), None)

    due = subscription_store.due(now)
    total_subscriptions = len(subscription_store.subscriptions)

    # "Attention" = the latest run failed: a human/fix is needed. A WAITING run
    # (capacity/confirmation) or a due refresh is normal operation the scheduler
    # handles, so neither raises attention on its own.
    attention = latest is not None and _is_failure(latest)
    waiting = latest is not None and latest.status == LoopRunStatus.WAITING

    return {
        "expert": expert_name,
        "has_runs": latest is not None,
        "last_run": _compact_run(latest) if latest else None,
        "last_failure": _compact_run(last_failure) if last_failure else None,
        "waiting_next_action": latest.next_action if (waiting and latest and latest.next_action) else None,
        "subscriptions": total_subscriptions,
        "refresh_due": len(due),
        "due_topics": [s.topic for s in due],
        "budget_spent_window": _round(sum(run.budget_spent for run in runs)),
        "attention": attention,
        "waiting": waiting,
    }


def _row_sort_key(row: dict[str, Any]) -> tuple:
    """Anomalies float to the top; green is boring. Failed, then waiting, then
    refresh-due, then never-run, then alphabetical."""
    return (
        not row["attention"],
        not row["waiting"],
        row["refresh_due"] == 0,
        row["has_runs"],
        row["expert"].lower(),
    )


def build_fleet_status_rollup(
    *,
    expert_names: list[str] | None = None,
    now: datetime | None = None,
    limit: int = 20,
    loop_store_factory: LoopStoreFactory | None = None,
    subscription_store_factory: SubscriptionStoreFactory | None = None,
) -> dict[str, Any]:
    """Return a deterministic, read-only ``$0`` roster-health payload.

    ``expert_names`` and the two store factories are injectable for testing;
    they default to the real on-disk stores for the current data dir.
    """
    if limit < 1:
        raise ValueError("limit must be positive")

    resolved_now = now or datetime.now(UTC)
    loop_factory = loop_store_factory or (lambda name: ExpertLoopRunStore(name))
    sub_factory = subscription_store_factory or (lambda name: SubscriptionStore(name))

    if expert_names is None:
        from deepr.experts.profile_store import ExpertStore

        expert_names = [profile.name for profile in ExpertStore().list_all()]

    rows = [
        _expert_row(
            name,
            loop_store=loop_factory(name),
            subscription_store=sub_factory(name),
            now=resolved_now,
            limit=limit,
        )
        for name in expert_names
    ]
    rows.sort(key=_row_sort_key)

    summary = {
        "experts": len(rows),
        "attention": sum(1 for r in rows if r["attention"]),
        "waiting": sum(1 for r in rows if r["waiting"]),
        "refresh_due": sum(1 for r in rows if r["refresh_due"]),
        "never_run": sum(1 for r in rows if not r["has_runs"]),
        "budget_spent_window_total": _round(sum(r["budget_spent_window"] for r in rows)),
    }

    payload = {
        "schema_version": FLEET_STATUS_SCHEMA_VERSION,
        "kind": FLEET_STATUS_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "stability": "experimental",
            "compatibility": {
                "additive_fields": True,
                "breaking_changes_require_new_schema_version": True,
                "deprecation_policy": "Fields in this v1 payload are additive within v1; removals use a new schema.",
            },
        },
        "generated_at": resolved_now.isoformat(),
        "window": {"limit": limit},
        "summary": summary,
        "experts": rows,
    }
    return sanitize_host_facing_payload(payload, source_label="expert fleet status")


def fleet_needs_attention(payload: dict[str, Any]) -> bool:
    """True when any expert's latest run failed - lets a scheduler run
    ``deepr fleet status`` as a cheap watchdog and act on a non-zero exit."""
    summary = payload.get("summary", {})
    return bool(summary.get("attention", 0))
