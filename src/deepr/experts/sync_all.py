"""Library-wide expert maintenance: sync every due expert in one pass.

`expert sync` keeps one expert current; this keeps the whole roster current as a
fleet. It is composition over existing parts (the per-expert `ExpertSyncEngine`,
the capacity waterfall, the overlap guard) - no new execution machinery and no
new datastore, per the "hosts own the schedule, Deepr owns the verbs" and
heavy-infra non-goals.

The orchestration here is pure and deterministic: it enumerates experts,
filters to those with due subscriptions, runs each under a per-expert budget
within a total ceiling, holds the per-(expert, sync) overlap lock so a roster
pass never collides with a manual sync or another pass, and is skip-not-fail (one
expert's failure never aborts the roster). The actual per-expert sync (backend
selection, research, verified absorb, loop-run recording) is the injected
``sync_one`` - so this loop is unit-testable at ``$0`` and the real work reuses
the same path as ``expert sync``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.loop_lock import expert_verb_lock
from deepr.experts.sync import MIN_PER_TOPIC_BUDGET, SubscriptionStore, SyncResult

# (expert_name, budget, dry_run) -> (per-expert SyncResult, capacity_source label)
SyncOneFn = Callable[[str, float, bool], Awaitable[tuple[SyncResult, str]]]
SubscriptionStoreFactory = Callable[[str], SubscriptionStore]


@dataclass
class ExpertSyncSummary:
    """One expert's outcome within a roster pass."""

    expert: str
    status: str  # "synced" | "no_changes" | "not_due" | "locked" | "skipped" | "failed"
    topics_synced: int = 0
    absorbed: int = 0
    flagged: int = 0
    cost: float = 0.0
    capacity_source: str = ""
    detail: str = ""

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
        return sum(1 for s in self.summaries if s.status == "failed")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "deepr-library-sync-v1",
            "kind": "deepr.expert.sync_all",
            "started_at": self.started_at.isoformat(),
            "experts": len(self.summaries),
            "synced_experts": self.synced_experts,
            "failed_experts": self.failed_experts,
            "total_cost": round(self.total_cost, 4),
            "summaries": [s.to_dict() for s in self.summaries],
        }


def _summarize(name: str, result: SyncResult, capacity_source: str) -> ExpertSyncSummary:
    """Fold a per-expert SyncResult into one roster row."""
    failed = [o for o in result.outcomes if o.status == "failed"]
    if result.synced_count:
        status = "synced"
    elif failed:
        status = "failed"
    else:
        status = "no_changes"
    detail = "; ".join(o.detail for o in failed if o.detail)[:160] if failed else ""
    return ExpertSyncSummary(
        expert=name,
        status=status,
        topics_synced=result.synced_count,
        absorbed=sum(o.absorbed for o in result.outcomes),
        flagged=sum(o.flagged for o in result.outcomes),
        cost=result.total_cost,
        capacity_source=capacity_source,
        detail=detail,
    )


async def _attempt_sync(name: str, sync_one: SyncOneFn, budget: float, dry_run: bool) -> ExpertSyncSummary:
    try:
        result, capacity_source = await sync_one(name, budget, dry_run)
    except Exception as exc:  # skip-not-fail: one expert never aborts the roster
        return ExpertSyncSummary(name, "failed", detail=str(exc))
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
    if budget < 0:
        raise ValueError("budget must be non-negative")
    started = now or datetime.now(UTC)
    sub_factory = subscription_store_factory or (lambda n: SubscriptionStore(n))
    result = LibrarySyncResult(started_at=started)

    remaining = budget
    for name in expert_names:
        if only_due and not sub_factory(name).due(now):
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
