"""Cross-expert fleet health rollup (read-only, $0).

Folds each expert's durable loop-run history (``loop_runs.jsonl``) and topic
subscription cadence (``subscriptions.json``) into one roster view: per expert,
the latest loop run's status, what it changed, what it cost on which capacity,
its most recent failure, whether knowledge refresh is due (overdue per the
configured cadence), and what (if anything) is waiting. Derived purely from
existing on-disk records - it never runs a loop, never spends, and never mutates
state. Unreadable durable state is a failed observation, never a healthy zero.

The per-expert ``loop_status_rollup`` and the plan-quota ``capacity fleet`` view
answer different questions; neither gives the operator one roster-wide answer to
"is my fleet healthy?". This module does, with no new storage.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from deepr.experts.loop_runs import ExpertLoopRun, ExpertLoopRunStore, LoopRunStatus, LoopStopReason
from deepr.experts.sync import SubscriptionStore
from deepr.security.output_safety import sanitize_host_facing_payload

FLEET_STATUS_SCHEMA_VERSION = "deepr-fleet-status-v2"
FLEET_STATUS_KIND = "deepr.expert.fleet_status"
_MAX_STATE_ERROR_REFS = 20

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
_READ_ERRORS = (OSError, OverflowError, RecursionError, TypeError, UnicodeError, ValueError)


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
    loop_store_factory: LoopStoreFactory,
    subscription_store_factory: SubscriptionStoreFactory,
    now: datetime,
    limit: int,
) -> dict[str, Any]:
    """One roster row: loop-run health + refresh cadence for a single expert."""
    run_error = False
    try:
        loop_store = loop_store_factory(expert_name)
        runs = loop_store.list_runs(limit=limit)
        run_error = bool(getattr(loop_store, "load_failed", False))
    except _READ_ERRORS:
        runs = []
        run_error = True

    subscription_error = False
    try:
        subscription_store = subscription_store_factory(expert_name)
        subscription_error = bool(getattr(subscription_store, "load_failed", False))
        due = [] if subscription_error else subscription_store.due(now)
        total_subscriptions = None if subscription_error else len(subscription_store.subscriptions)
    except _READ_ERRORS:
        due = []
        total_subscriptions = None
        subscription_error = True

    trusted_runs = [] if run_error else runs
    latest = trusted_runs[0] if trusted_runs else None
    last_failure = next((run for run in trusted_runs if _is_failure(run)), None)

    # "Attention" = the latest run failed: a human/fix is needed. A WAITING run
    # (capacity/confirmation) or a due refresh is normal operation the scheduler
    # handles, so neither raises attention on its own.
    attention = None if run_error else latest is not None and _is_failure(latest)
    waiting = None if run_error else latest is not None and latest.status == LoopRunStatus.WAITING
    state_errors = [
        code
        for failed, code in (
            (run_error, "runs_unreadable"),
            (subscription_error, "subscriptions_unreadable"),
        )
        if failed
    ]

    return {
        "expert": expert_name,
        "state_errors": state_errors,
        "has_runs": None if run_error else latest is not None,
        "last_run": _compact_run(latest) if latest else None,
        "last_failure": _compact_run(last_failure) if last_failure else None,
        "waiting_next_action": latest.next_action if (waiting and latest and latest.next_action) else None,
        "subscriptions": total_subscriptions,
        "refresh_due": None if subscription_error else len(due),
        "due_topics": None if subscription_error else [subscription.topic for subscription in due],
        "budget_spent_window": None if run_error else _round(sum(run.budget_spent for run in trusted_runs)),
        "attention": attention,
        "waiting": waiting,
    }


def _row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Sort unreadable, failed, waiting, due, and never-run rows first."""
    refresh_due = row["refresh_due"]
    return (
        not bool(row["state_errors"]),
        row["attention"] is not True,
        row["waiting"] is not True,
        not isinstance(refresh_due, int) or refresh_due == 0,
        row["has_runs"] is not False,
        row["expert"].lower(),
    )


def _discover_experts() -> tuple[list[str], list[dict[str, str]]]:
    """Return readable names and safe relative references for bad profiles."""
    from deepr.experts.profile_store import ExpertStore

    try:
        store = ExpertStore(create=False)
        profiles = store.list_all(log_errors=False)
    except _READ_ERRORS:
        return [], [{"kind": "profiles_unreadable", "source": "experts-root"}]

    refs = []
    for path, _reason in getattr(profiles, "errors", ()):
        try:
            source = path.relative_to(store.base_path).as_posix()
        except ValueError:
            source = "profile.json"
        refs.append({"kind": "profile_unreadable", "source": source})
    return [profile.name for profile in profiles], refs


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
    sub_factory = subscription_store_factory or (lambda name: SubscriptionStore(name, log_errors=False))

    profile_error_refs: list[dict[str, str]] = []
    if expert_names is None:
        expert_names, profile_error_refs = _discover_experts()

    rows = [
        _expert_row(
            name,
            loop_store_factory=loop_factory,
            subscription_store_factory=sub_factory,
            now=resolved_now,
            limit=limit,
        )
        for name in expert_names
    ]
    rows.sort(key=_row_sort_key)

    run_errors = sum("runs_unreadable" in row["state_errors"] for row in rows)
    subscription_errors = sum("subscriptions_unreadable" in row["state_errors"] for row in rows)
    state_errors = {
        "profiles": len(profile_error_refs),
        "runs": run_errors,
        "subscriptions": subscription_errors,
    }
    state_error_count = sum(state_errors.values())
    state_error_refs = list(profile_error_refs)
    for row in rows:
        if "runs_unreadable" in row["state_errors"]:
            state_error_refs.append({"kind": "runs_unreadable", "expert": row["expert"], "source": "loop_runs.jsonl"})
        if "subscriptions_unreadable" in row["state_errors"]:
            state_error_refs.append(
                {
                    "kind": "subscriptions_unreadable",
                    "expert": row["expert"],
                    "source": "knowledge/subscriptions.json",
                }
            )
    state_error_refs.sort(key=lambda ref: (ref["kind"], ref.get("expert", ""), ref["source"]))
    bounded_error_refs = state_error_refs[:_MAX_STATE_ERROR_REFS]
    observed = {
        "experts": len(rows),
        "attention": sum(row["attention"] is True for row in rows),
        "waiting": sum(row["waiting"] is True for row in rows),
        "refresh_due": sum(isinstance(row["refresh_due"], int) and row["refresh_due"] > 0 for row in rows),
        "never_run": sum(row["has_runs"] is False for row in rows),
        "budget_spent_window_total": _round(
            sum(row["budget_spent_window"] for row in rows if row["budget_spent_window"] is not None)
        ),
    }
    run_totals_known = state_errors["profiles"] == 0 and state_errors["runs"] == 0
    subscription_totals_known = state_errors["profiles"] == 0 and state_errors["subscriptions"] == 0
    summary = {
        "experts": len(rows),
        "attention": observed["attention"] if run_totals_known else None,
        "waiting": observed["waiting"] if run_totals_known else None,
        "refresh_due": observed["refresh_due"] if subscription_totals_known else None,
        "never_run": observed["never_run"] if run_totals_known else None,
        "state_errors": state_error_count,
        "budget_spent_window_total": observed["budget_spent_window_total"] if run_totals_known else None,
        "observed": observed,
    }
    status = (
        "blocked_storage_state" if state_error_count else "attention_required" if observed["attention"] else "completed"
    )

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
                "deprecation_policy": "Fields in this v2 payload are additive within v2; removals use a new schema.",
            },
        },
        "complete": state_error_count == 0,
        "status": status,
        "exit_code": 0 if status == "completed" else 1,
        "state_errors": state_errors,
        "state_error_refs": bounded_error_refs,
        "state_error_refs_omitted": len(state_error_refs) - len(bounded_error_refs),
        "next_action": (
            {
                "kind": "repair_local_expert_state",
                "source_field": "state_error_refs",
                "requires_manual_repair": True,
            }
            if state_error_count
            else None
        ),
        "generated_at": resolved_now.isoformat(),
        "window": {"limit": limit},
        "summary": summary,
        "experts": rows,
    }
    return cast(dict[str, Any], sanitize_host_facing_payload(payload, source_label="expert fleet status"))


def fleet_needs_attention(payload: dict[str, Any]) -> bool:
    """True when a latest run failed or the fleet observation is incomplete."""
    exit_code = payload.get("exit_code")
    if isinstance(exit_code, int):
        return exit_code != 0
    summary = payload.get("summary", {})
    return bool(summary.get("attention", 0) or summary.get("state_errors", 0))
