"""Tests for the library-wide roster sync orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deepr.experts.loop_lock import expert_verb_lock
from deepr.experts.sync import SyncOutcome, SyncResult
from deepr.experts.sync_all import ExpertSyncSummary, _summarize, run_library_sync


def _result(*outcomes: SyncOutcome, cost: float = 0.0) -> SyncResult:
    return SyncResult(
        expert_name="x",
        started_at=datetime.now(UTC),
        outcomes=list(outcomes),
        total_cost=cost,
    )


def _sync_one(behaviors: dict, calls: list | None = None):
    """Injected per-expert sync: maps name -> (SyncResult, source) or an Exception."""

    async def sync_one(name, budget, dry_run):
        if calls is not None:
            calls.append((name, round(budget, 4), dry_run))
        outcome = behaviors[name]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return sync_one


def _subs(due_map: dict):
    class _FakeSub:
        def __init__(self, name):
            self._due = due_map.get(name, True)

        def due(self, now=None):
            return [object()] if self._due else []

    return _FakeSub


class TestSummarize:
    def test_synced_when_any_topic_synced(self):
        r = _result(SyncOutcome("t1", "synced", absorbed=2, flagged=1), SyncOutcome("t2", "no_changes"), cost=0.03)
        s = _summarize("E", r, "local")
        assert s.status == "synced"
        assert s.topics_synced == 1 and s.absorbed == 2 and s.flagged == 1
        assert s.cost == 0.03 and s.capacity_source == "local"

    def test_no_changes_when_nothing_synced_or_failed(self):
        s = _summarize("E", _result(SyncOutcome("t1", "no_changes")), "local")
        assert s.status == "no_changes"

    def test_failed_when_an_outcome_failed_and_none_synced(self):
        s = _summarize("E", _result(SyncOutcome("t1", "failed", detail="boom")), "api_metered")
        assert s.status == "failed"
        assert "boom" in s.detail


class TestRunLibrarySync:
    async def test_syncs_due_experts_and_skips_not_due(self):
        behaviors = {
            "Alpha": (_result(SyncOutcome("t", "synced", absorbed=1), cost=0.02), "local"),
            "Gamma": (_result(SyncOutcome("t", "synced", absorbed=1), cost=0.02), "local"),
        }
        result = await run_library_sync(
            sync_one=_sync_one(behaviors),
            expert_names=["Alpha", "Beta", "Gamma"],
            budget=5.0,
            subscription_store_factory=_subs({"Beta": False}),
        )
        by_name = {s.expert: s.status for s in result.summaries}
        assert by_name == {"Alpha": "synced", "Beta": "not_due", "Gamma": "synced"}
        assert result.synced_experts == 2
        assert result.total_cost == pytest.approx(0.04)

    async def test_per_expert_budget_caps_each_call(self):
        calls: list = []
        behaviors = {n: (_result(cost=0.0), "local") for n in ("A", "B")}
        await run_library_sync(
            sync_one=_sync_one(behaviors, calls),
            expert_names=["A", "B"],
            budget=5.0,
            per_expert_budget=0.25,
            subscription_store_factory=_subs({}),
        )
        assert [c[1] for c in calls] == [0.25, 0.25]  # each capped at per_expert_budget

    async def test_total_budget_exhaustion_skips_the_rest(self):
        behaviors = {
            "A": (_result(SyncOutcome("t", "synced"), cost=0.98), "local"),
            "B": (_result(SyncOutcome("t", "synced"), cost=0.0), "local"),
        }
        result = await run_library_sync(
            sync_one=_sync_one(behaviors),
            expert_names=["A", "B"],
            budget=1.0,
            per_expert_budget=1.0,
            subscription_store_factory=_subs({}),
        )
        statuses = {s.expert: s.status for s in result.summaries}
        assert statuses["A"] == "synced"
        assert statuses["B"] == "skipped"
        assert "budget exhausted" in next(s.detail for s in result.summaries if s.expert == "B")

    async def test_one_expert_failure_does_not_abort_the_roster(self):
        behaviors = {
            "A": RuntimeError("provider down"),
            "B": (_result(SyncOutcome("t", "synced"), cost=0.0), "local"),
        }
        result = await run_library_sync(
            sync_one=_sync_one(behaviors),
            expert_names=["A", "B"],
            budget=5.0,
            subscription_store_factory=_subs({}),
        )
        statuses = {s.expert: s.status for s in result.summaries}
        assert statuses["A"] == "failed"
        assert statuses["B"] == "synced"
        assert "provider down" in next(s.detail for s in result.summaries if s.expert == "A")

    async def test_overlap_lock_reports_locked(self, tmp_path):
        behaviors = {"A": (_result(SyncOutcome("t", "synced"), cost=0.0), "local")}
        # Hold A's sync lock for the duration of the pass.
        with expert_verb_lock("A", "sync", lock_dir=tmp_path) as held:
            assert held
            result = await run_library_sync(
                sync_one=_sync_one(behaviors),
                expert_names=["A"],
                budget=5.0,
                lock_dir=tmp_path,
                subscription_store_factory=_subs({}),
            )
        assert result.summaries[0].status == "locked"

    async def test_dry_run_takes_no_lock_and_passes_flag_through(self, tmp_path):
        calls: list = []
        behaviors = {"A": (_result(SyncOutcome("t", "would_sync"), cost=0.0), "local")}
        # Even while the lock is held, a dry run is not blocked (it touches nothing).
        with expert_verb_lock("A", "sync", lock_dir=tmp_path):
            result = await run_library_sync(
                sync_one=_sync_one(behaviors, calls),
                expert_names=["A"],
                budget=5.0,
                dry_run=True,
                lock_dir=tmp_path,
                subscription_store_factory=_subs({}),
            )
        assert result.summaries[0].status != "locked"
        assert calls == [("A", 0.5, True)]

    async def test_only_due_false_includes_not_due_experts(self):
        behaviors = {"A": (_result(SyncOutcome("t", "no_changes"), cost=0.0), "local")}
        result = await run_library_sync(
            sync_one=_sync_one(behaviors),
            expert_names=["A"],
            budget=5.0,
            only_due=False,
            subscription_store_factory=_subs({"A": False}),  # not due, but forced
        )
        assert result.summaries[0].status == "no_changes"

    async def test_negative_budget_rejected(self):
        with pytest.raises(ValueError, match="budget must be non-negative"):
            await run_library_sync(
                sync_one=_sync_one({}),
                expert_names=[],
                budget=-1.0,
            )

    def test_rollup_to_dict_is_versioned(self):
        result = run_library_sync_sync_helper()
        payload = result.to_dict()
        assert payload["schema_version"] == "deepr-library-sync-v1"
        assert payload["kind"] == "deepr.expert.sync_all"
        assert payload["experts"] == 1


def run_library_sync_sync_helper():
    """Build a LibrarySyncResult without awaiting (for the pure to_dict test)."""
    from deepr.experts.sync_all import LibrarySyncResult

    res = LibrarySyncResult(started_at=datetime.now(UTC))
    res.summaries.append(ExpertSyncSummary("E", "synced", topics_synced=1, cost=0.01))
    res.total_cost = 0.01
    return res
