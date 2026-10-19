"""Cross-process belief store write transactions.

Regression for the ROADMAP finding that different write verbs (absorb, sync,
graph-commit apply, learning apply) could overwrite one another's beliefs from
stale whole-store snapshots. Real stores on a tmp dir; no model calls.
"""

from __future__ import annotations

import json
import multiprocessing
from datetime import UTC, datetime

import pytest

from deepr.experts.beliefs import Belief, BeliefChange, BeliefStore, BeliefStoreConflictError


def _store(tmp_path) -> BeliefStore:
    return BeliefStore("Race Expert", storage_dir=tmp_path / "beliefs")


def _claims(store: BeliefStore) -> set[str]:
    return {belief.claim for belief in store.beliefs.values()}


def test_reading_creates_no_files(tmp_path):
    """Regression (agent-plugin smoke): read-only launches must leave expert data byte-identical."""
    seed = _store(tmp_path)
    seed.add_belief(Belief(claim="Seeded fact", confidence=0.8), check_conflicts=False)
    (tmp_path / "beliefs" / "beliefs.lock").unlink(missing_ok=True)
    before = sorted(p.name for p in (tmp_path / "beliefs").iterdir())

    reader = _store(tmp_path)
    assert _claims(reader) == {"Seeded fact"}
    assert sorted(p.name for p in (tmp_path / "beliefs").iterdir()) == before


def test_stale_store_reloads_instead_of_overwriting_another_commit(tmp_path):
    absorb = _store(tmp_path)
    sync = _store(tmp_path)  # loaded before absorb commits, like a concurrent verb

    absorb.add_belief(Belief(claim="Absorbed fact about queues", confidence=0.8), check_conflicts=False)
    sync.add_belief(Belief(claim="Synced fact about caching layers", confidence=0.7), check_conflicts=False)

    fresh = _store(tmp_path)
    assert fresh._unreadable is False
    assert _claims(fresh) == {"Absorbed fact about queues", "Synced fact about caching layers"}
    assert len(fresh.iter_events()) == 2


def test_stale_store_dedups_against_the_concurrent_commit(tmp_path):
    first = _store(tmp_path)
    second = _store(tmp_path)
    claim = "Durable state is required for a minimum viable expert loop"

    original, _ = first.add_belief(Belief(claim=claim, confidence=0.8), check_conflicts=False)
    stored, _change = second.add_belief(Belief(claim=claim, confidence=0.8), check_conflicts=False)

    assert stored.id == original.id
    fresh = _store(tmp_path)
    assert list(fresh.beliefs) == [original.id]


def test_unsaved_edits_are_not_reloaded_away(tmp_path):
    seed = _store(tmp_path)
    a, _ = seed.add_belief(Belief(claim="Alpha systems use queues", confidence=0.8), check_conflicts=False)
    b, _ = seed.add_belief(Belief(claim="Beta systems use caches", confidence=0.8), check_conflicts=False)

    batch = _store(tmp_path)
    batch.add_edge(a.id, b.id, "supports", provenance="batch", save=False)
    other = _store(tmp_path)
    other.add_belief(Belief(claim="Gamma systems use logs", confidence=0.8), check_conflicts=False)

    with pytest.raises(BeliefStoreConflictError, match="unsaved edits"):
        batch.add_belief(Belief(claim="Delta systems use locks", confidence=0.8), check_conflicts=False)
    with pytest.raises(BeliefStoreConflictError, match="refusing to overwrite"):
        batch._save()

    fresh = _store(tmp_path)
    assert "Gamma systems use logs" in _claims(fresh)
    assert "Delta systems use locks" not in _claims(fresh)


def test_direct_save_over_an_unseen_snapshot_fails_closed(tmp_path):
    stale = _store(tmp_path)
    _store(tmp_path).add_belief(Belief(claim="Committed elsewhere", confidence=0.8), check_conflicts=False)
    stale.beliefs["manual"] = Belief(claim="Direct in-memory edit", confidence=0.5)

    with pytest.raises(BeliefStoreConflictError):
        stale._save()
    assert _claims(_store(tmp_path)) == {"Committed elsewhere"}


def test_multi_step_writer_holds_one_transaction(tmp_path):
    from deepr.experts.world_validity import close_claim

    writer = _store(tmp_path)
    belief, _ = writer.add_belief(Belief(claim="Service X is in force", confidence=0.8), check_conflicts=False)
    _store(tmp_path).add_belief(Belief(claim="Unrelated concurrent fact", confidence=0.8), check_conflicts=False)

    close_claim(
        writer,
        belief.id,
        ended_at=datetime(2026, 10, 1, tzinfo=UTC),
        basis="observed",
        evidence="Retired in the 2026-10-01 notice.",
    )

    fresh = _store(tmp_path)
    assert "Unrelated concurrent fact" in _claims(fresh)
    assert belief.id not in fresh.beliefs


def test_legacy_migration_keeps_the_change_window(tmp_path):
    """Regression: the contradictions_with migration saved before changes loaded."""
    store = _store(tmp_path)
    a, _ = store.add_belief(Belief(claim="Old claim one", confidence=0.8), check_conflicts=False)
    b, _ = store.add_belief(Belief(claim="Old claim two", confidence=0.8), check_conflicts=False)
    data = json.loads(store.storage_path.read_text(encoding="utf-8"))
    data["edges"] = []
    data["beliefs"][a.id]["contradictions_with"] = [b.id]
    store.storage_path.write_text(json.dumps(data), encoding="utf-8")
    changes_before = len(data["changes"])

    migrated = _store(tmp_path)
    assert migrated._unreadable is False
    assert [edge.edge_type for edge in migrated.edges_for(a.id)] == ["contradicts"]
    assert migrated.edges_for(a.id)[0].touches(b.id)
    assert len(migrated.changes) == changes_before

    reopened = _store(tmp_path)
    assert reopened._unreadable is False
    assert len(reopened.changes) == changes_before


def _add_many(storage_dir: str, prefix: str, count: int) -> None:
    from pathlib import Path

    store = BeliefStore("Race Expert", storage_dir=Path(storage_dir))
    for index in range(count):
        store.add_belief(
            Belief(claim=f"{prefix} distinct observation number {index}", confidence=0.8),
            check_conflicts=False,
            dedup=False,
        )


def test_concurrent_processes_lose_no_beliefs(tmp_path):
    storage_dir = tmp_path / "beliefs"
    BeliefStore("Race Expert", storage_dir=storage_dir)
    context = multiprocessing.get_context("spawn")
    workers = [context.Process(target=_add_many, args=(str(storage_dir), f"worker{n}", 15)) for n in range(3)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=120)
        assert worker.exitcode == 0

    fresh = BeliefStore("Race Expert", storage_dir=storage_dir)
    assert fresh._unreadable is False
    assert len(fresh.beliefs) == 45
    events = fresh.iter_events()
    assert len(events) == 45
    assert all(isinstance(event, BeliefChange) for event in events)


def test_failed_mutation_rolls_back_memory_and_clears_unsaved_flag(tmp_path, monkeypatch):
    """Regression (2.50.40 review): a raise mid-mutation left edits in memory and the store marked dirty."""
    store = _store(tmp_path)
    a, _ = store.add_belief(Belief(claim="Alpha systems use queues", confidence=0.8), check_conflicts=False)
    b, _ = store.add_belief(Belief(claim="Beta systems use caches", confidence=0.8), check_conflicts=False)

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("deepr.experts.beliefs.append_jsonl_durable", fail)
    with pytest.raises(OSError):
        store.add_contested_belief(Belief(claim="Alpha systems avoid queues", confidence=0.6), [a])
    monkeypatch.undo()

    assert store._snapshot.dirty is False
    assert all(not edge.touches(a.id) or edge.touches(b.id) for edge in store.edges.values())
    assert len(store.beliefs) == 2
    _store(tmp_path).add_belief(Belief(claim="Gamma systems use logs", confidence=0.8), check_conflicts=False)
    store.add_belief(Belief(claim="Delta systems use locks", confidence=0.8), check_conflicts=False)
    assert len(_store(tmp_path).beliefs) == 4


def test_migration_defers_instead_of_raising_from_the_constructor(tmp_path, monkeypatch):
    """Regression (2.50.40 review): a concurrent write during legacy migration raised out of BeliefStore()."""
    store = _store(tmp_path)
    a, _ = store.add_belief(Belief(claim="Old claim one", confidence=0.8), check_conflicts=False)
    b, _ = store.add_belief(Belief(claim="Old claim two", confidence=0.8), check_conflicts=False)
    data = json.loads(store.storage_path.read_text(encoding="utf-8"))
    data["edges"] = []
    data["beliefs"][a.id]["contradictions_with"] = [b.id]
    store.storage_path.write_text(json.dumps(data), encoding="utf-8")

    from deepr.experts import belief_snapshot

    def raced(self):
        raise BeliefStoreConflictError("simulated concurrent write")

    monkeypatch.setattr(belief_snapshot.SnapshotGuard, "check_unchanged", raced)
    loaded = _store(tmp_path)
    monkeypatch.undo()

    assert [edge.edge_type for edge in loaded.edges_for(a.id)] == ["contradicts"]
    loaded.add_belief(Belief(claim="New fact after deferral", confidence=0.8), check_conflicts=False)
    persisted = json.loads(loaded.storage_path.read_text(encoding="utf-8"))
    assert persisted["edges"]
