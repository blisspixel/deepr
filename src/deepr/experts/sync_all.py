"""Library-wide expert maintenance: sync every due expert in one pass.

`expert sync` keeps one expert current; this keeps the whole roster current as a
fleet. It is composition over existing parts (the per-expert `ExpertSyncEngine`,
the capacity waterfall, the overlap guard) - no new execution machinery and no
new datastore, per the "hosts own the schedule, Deepr owns the verbs" and
heavy-infra non-goals.

The orchestration here is pure and deterministic: it enumerates experts,
filters to those with due subscriptions, runs each under a per-expert budget
within a total ceiling, holds the per-(expert, sync) overlap lock so a roster
pass never collides with a manual sync or another pass, and continues after an
individual expert failure before reporting the aggregate failure. The actual
per-expert sync (backend selection, research, verified absorb, loop-run
recording) is the injected ``sync_one`` - so this loop is unit-testable at ``$0``
and the real work reuses the same path as ``expert sync``.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.loop_lock import expert_verb_lock
from deepr.experts.loop_runs import known_exception_cost
from deepr.experts.sync import MIN_PER_TOPIC_BUDGET, SubscriptionStore, SyncResult

# (expert_name, budget, dry_run) -> (per-expert SyncResult, capacity_source label)
SyncOneFn = Callable[[str, float, bool], Awaitable[tuple[SyncResult, str]]]
SubscriptionStoreFactory = Callable[[str], SubscriptionStore]

_PUBLIC_FAILURE_DETAIL = "Expert sync did not complete. Inspect durable loop status before retrying."
_SUMMARY_STATUSES = (
    "synced",
    "partial_failure",
    "failed",
    "would_sync",
    "no_changes",
    "not_due",
    "skipped",
    "locked",
)


def _failure_record(
    expert: str,
    *,
    topic: str | None,
    error_code: str,
    retryable: bool | None,
    no_metered_fallback: bool | None,
) -> dict[str, Any]:
    return {
        "topic": topic,
        "error_code": error_code,
        "retryable": retryable,
        "no_metered_fallback": no_metered_fallback,
        "inspect_command_argv": ["deepr", "expert", "loop-status", expert, "--json"],
    }


@dataclass
class ExpertSyncSummary:
    """One expert's outcome within a roster pass."""

    expert: str
    status: str
    topics_synced: int = 0
    absorbed: int = 0
    flagged: int = 0
    cost: float = 0.0
    capacity_source: str = ""
    detail: str = ""
    failed_topics: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert": self.expert,
            "status": self.status,
            "topics_synced": self.topics_synced,
            "absorbed": self.absorbed,
            "flagged": self.flagged,
            "cost": round(self.cost, 4),
            "capacity_source": self.capacity_source,
            "detail": self.detail,
            "failed_topics": self.failed_topics,
            "failures": list(self.failures),
        }


@dataclass
class LibrarySyncResult:
    """The roll-up over a roster maintenance pass."""

    started_at: datetime
    summaries: list[ExpertSyncSummary] = field(default_factory=list)
    total_cost: float = 0.0

    @property
    def synced_experts(self) -> int:
        return sum(1 for s in self.summaries if s.status == "synced")

    @property
    def failed_experts(self) -> int:
        return sum(1 for summary in self.summaries if summary.status in {"failed", "partial_failure"})

    @property
    def partial_failure_experts(self) -> int:
        return sum(1 for summary in self.summaries if summary.status == "partial_failure")

    @property
    def would_sync_experts(self) -> int:
        return sum(1 for summary in self.summaries if summary.status == "would_sync")

    @property
    def status(self) -> str:
        return "completed_with_failures" if self.failed_experts else "completed"

    @property
    def exit_code(self) -> int:
        return 1 if self.failed_experts else 0

    @property
    def status_counts(self) -> dict[str, int]:
        counts = dict.fromkeys(_SUMMARY_STATUSES, 0)
        for summary in self.summaries:
            counts[summary.status] = counts.get(summary.status, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "deepr-library-sync-v1",
            "kind": "deepr.expert.sync_all",
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at.isoformat(),
            "experts": len(self.summaries),
            "synced_experts": self.synced_experts,
            "failed_experts": self.failed_experts,
            "partial_failure_experts": self.partial_failure_experts,
            "would_sync_experts": self.would_sync_experts,
            "status_counts": self.status_counts,
            "total_cost": round(self.total_cost, 4),
            "summaries": [s.to_dict() for s in self.summaries],
        }


def _summarize(name: str, result: SyncResult, capacity_source: str) -> ExpertSyncSummary:
    """Fold a per-expert SyncResult into one roster row."""
    failed = [o for o in result.outcomes if o.status == "failed"]
    if failed and result.synced_count:
        status = "partial_failure"
    elif failed:
        status = "failed"
    elif result.synced_count:
        status = "synced"
    elif any(outcome.status == "would_sync" for outcome in result.outcomes):
        status = "would_sync"
    else:
        status = "no_changes"
    failures = [
        _failure_record(
            name,
            topic=outcome.topic,
            error_code="EXPERT_SYNC_TOPIC_FAILED",
            retryable=outcome.retryable,
            no_metered_fallback=outcome.no_metered_fallback,
        )
        for outcome in failed
    ]
    return ExpertSyncSummary(
        expert=name,
        status=status,
        topics_synced=result.synced_count,
        absorbed=sum(o.absorbed for o in result.outcomes),
        flagged=sum(o.flagged for o in result.outcomes),
        cost=result.total_cost,
        capacity_source=capacity_source,
        detail=_PUBLIC_FAILURE_DETAIL if failed else "",
        failed_topics=len(failed),
        failures=failures,
    )


async def _attempt_sync(name: str, sync_one: SyncOneFn, budget: float, dry_run: bool) -> ExpertSyncSummary:
    try:
        result, capacity_source = await sync_one(name, budget, dry_run)
    except Exception as exc:  # skip-not-fail: one expert never aborts the roster
        return ExpertSyncSummary(
            name,
            "failed",
            cost=known_exception_cost(exc),
            detail=_PUBLIC_FAILURE_DETAIL,
            failures=[
                _failure_record(
                    name,
                    topic=None,
                    error_code="EXPERT_SYNC_EXECUTION_FAILED",
                    retryable=None,
                    no_metered_fallback=None,
                )
            ],
        )
    return _summarize(name, result, capacity_source)


async def _sync_one_expert(
    name: str,
    sync_one: SyncOneFn,
    *,
    budget: float,
    dry_run: bool,
    lock_dir: Path | None,
) -> ExpertSyncSummary:
    # A dry run touches no state, so it does not take the lock (a preview must
    # not report "locked" or create lock files).
    if dry_run:
        return await _attempt_sync(name, sync_one, budget, dry_run)
    with expert_verb_lock(name, "sync", lock_dir=lock_dir) as acquired:
        if not acquired:
            return ExpertSyncSummary(name, "locked", detail="another sync for this expert is already running")
        return await _attempt_sync(name, sync_one, budget, dry_run)


async def run_library_sync(
    *,
    sync_one: SyncOneFn,
    expert_names: list[str],
    budget: float,
    per_expert_budget: float = 0.50,
    only_due: bool = True,
    dry_run: bool = False,
    now: datetime | None = None,
    lock_dir: Path | None = None,
    subscription_store_factory: SubscriptionStoreFactory | None = None,
) -> LibrarySyncResult:
    """Sync each due expert under a per-expert budget within a total ceiling.

    ``sync_one`` does the real per-expert work and is injected so this loop is
    testable without providers. Experts with no due subscriptions are reported
    ``not_due`` (skipped unless ``only_due`` is False). When the total budget is
    spent, the rest of the roster is reported ``skipped`` rather than failed.
    """
    if not math.isfinite(budget):
        raise ValueError("budget must be finite")
    if budget < 0:
        raise ValueError("budget must be non-negative")
    if not math.isfinite(per_expert_budget) or per_expert_budget < 0:
        raise ValueError("per_expert_budget must be finite and non-negative")
    started = now or datetime.now(UTC)
    sub_factory = subscription_store_factory or (lambda n: SubscriptionStore(n))
    result = LibrarySyncResult(started_at=started)

    remaining = budget
    for name in expert_names:
        subscription_store = sub_factory(name)
        if getattr(subscription_store, "load_failed", False):
            result.summaries.append(
                ExpertSyncSummary(
                    name,
                    "failed",
                    detail=_PUBLIC_FAILURE_DETAIL,
                    failures=[
                        _failure_record(
                            name,
                            topic=None,
                            error_code="EXPERT_SUBSCRIPTIONS_UNREADABLE",
                            retryable=False,
                            no_metered_fallback=True,
                        )
                    ],
                )
            )
            continue
        if not subscription_store.subscriptions:
            result.summaries.append(ExpertSyncSummary(name, "not_due" if only_due else "no_changes"))
            continue
        if only_due and not subscription_store.due(now):
            result.summaries.append(ExpertSyncSummary(name, "not_due"))
            continue
        if not dry_run and remaining < MIN_PER_TOPIC_BUDGET:
            result.summaries.append(
                ExpertSyncSummary(name, "skipped", detail=f"run budget exhausted (${remaining:.2f} left)")
            )
            continue
        summary = await _sync_one_expert(
            name,
            sync_one,
            budget=min(per_expert_budget, remaining),
            dry_run=dry_run,
            lock_dir=lock_dir,
        )
        result.summaries.append(summary)
        result.total_cost += summary.cost
        remaining -= summary.cost

    return result
