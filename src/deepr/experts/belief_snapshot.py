"""Belief snapshot persistence and cross-process write transactions.

``BeliefStore`` keeps one whole-store ``beliefs.json`` snapshot. Writers in
different processes (absorb, sync, graph-commit apply, learning apply) must not
rewrite that snapshot from a stale copy, so every mutation runs under one
per-store file lock, reloads when another process committed since this store
last read or wrote, and refuses to save over a snapshot it has not seen.
See docs/design/belief-store-write-transactions.md.
"""

from __future__ import annotations

import functools
import json
import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, cast

from filelock import FileLock, Timeout

from deepr.experts.belief_edges import Edge
from deepr.experts.belief_event_wal import event_log_conflicts_with_snapshot
from deepr.utils.atomic_io import atomic_write_json

if TYPE_CHECKING:
    from deepr.experts.beliefs import BeliefStore

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 30.0
_MIGRATED_PROVENANCE = "migrated:contradictions_with"
_MAX_SNAPSHOT_BYTES = 50 * 1024 * 1024

_Method = TypeVar("_Method", bound=Callable[..., Any])
_Stat = tuple[int, int, int] | None


class BeliefStoreError(RuntimeError): ...


class BeliefStoreConflictError(BeliefStoreError):
    """Another process changed the snapshot under unsaved in-memory edits."""


def _stat(path: Path) -> _Stat:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_mtime_ns, stat.st_size, stat.st_ino)


class SnapshotGuard:
    """Per-store lock, last-seen fingerprint and unsaved-edit flag."""

    def __init__(self, store: BeliefStore, *, lock_timeout: float = LOCK_TIMEOUT_SECONDS) -> None:
        self._store = store
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._file_lock = (
            None if store.read_only else FileLock(str(store.storage_dir / "beliefs.lock"), timeout=lock_timeout)
        )
        self.seen: tuple[_Stat, _Stat] | None = None
        self.dirty = False

    def fingerprint(self) -> tuple[_Stat, _Stat]:
        return (_stat(self._store.storage_path), _stat(self._store.events_path))

    def mark_seen(self) -> None:
        self.seen = self.fingerprint()

    def note_own_event(self) -> None:
        """Record this store's own event append so it is not mistaken for another writer."""
        if self.seen is not None:
            self.seen = (self.seen[0], _stat(self._store.events_path))

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Hold the cross-process lock without reloading (reentrant)."""
        if self._file_lock is None:
            yield
            return
        with self._thread_lock:
            try:
                self._file_lock.acquire()
            except Timeout as exc:
                raise BeliefStoreError(
                    f"belief store for {self._store.expert_name!r} is busy; another write held it "
                    f"for over {LOCK_TIMEOUT_SECONDS:.0f}s. Retry the command."
                ) from exc
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                self._file_lock.release()

    @contextmanager
    def mutation(self) -> Iterator[None]:
        """Run one mutation against current on-disk state; roll back memory on failure."""
        with self.locked():
            outermost = self._file_lock is not None and self._depth == 1
            if outermost and self.fingerprint() != self.seen:
                if self.dirty:
                    raise BeliefStoreConflictError(
                        f"belief store for {self._store.expert_name!r} changed in another process while this "
                        "process held unsaved edits; nothing was overwritten. Retry the command."
                    )
                reload_snapshot(self._store)
            try:
                yield
            except BaseException:
                if outermost:
                    self._roll_back()
                raise

    def _roll_back(self) -> None:
        """Discard half-applied in-memory edits; disk holds the last commit."""
        try:
            reload_snapshot(self._store)
        except Exception:
            self._store._unreadable = True
            logger.exception("Belief store rollback failed for %s; refusing further writes.", self._store.expert_name)

    def check_unchanged(self) -> None:
        if self.seen is not None and _stat(self._store.storage_path) != self.seen[0]:
            raise BeliefStoreConflictError(
                f"belief store for {self._store.expert_name!r} changed in another process since it was loaded; "
                "refusing to overwrite it. Retry the command."
            )


def transactional(method: _Method) -> _Method:
    """Run a ``BeliefStore`` mutator inside its snapshot transaction."""

    @functools.wraps(method)
    def wrapper(self: BeliefStore, *args: Any, **kwargs: Any) -> Any:
        with self._snapshot.mutation():
            return method(self, *args, **kwargs)

    return cast(_Method, wrapper)


def save_snapshot(store: BeliefStore) -> None:
    if store.read_only:
        raise BeliefStoreError("read-only belief store cannot be saved")
    if store._unreadable:
        raise BeliefStoreError("refusing to overwrite unreadable belief store")
    guard = store._snapshot
    with guard.locked():
        guard.check_unchanged()
        atomic_write_json(
            store.storage_path,
            {
                "edges": [e.to_dict() for e in store.edges.values()],
                "beliefs": {bid: b.to_dict() for bid, b in store.beliefs.items()},
                "changes": [c.to_dict() for c in store.changes[-100:]],
            },
            fsync=True,
        )
        guard.mark_seen()
        guard.dirty = False


def reload_snapshot(store: BeliefStore) -> None:
    """Replace in-memory state with the current on-disk snapshot."""
    store.beliefs = {}
    store.domain_index = {}
    store.changes = []
    store.edges = {}
    store._snapshot.dirty = False
    load_snapshot(store)


def load_snapshot(store: BeliefStore) -> None:
    from deepr.experts.beliefs import Belief, BeliefChange

    store._unreadable = False
    store._snapshot.mark_seen()
    if not store.storage_path.exists():
        if event_log_conflicts_with_snapshot(store.events_path, snapshot_exists=False, latest_change=None):
            store._unreadable = True
        return
    try:
        if store.storage_path.stat().st_size > _MAX_SNAPSHOT_BYTES:
            store._unreadable = True
            logger.error("Belief store at %s exceeds 50 MB; refusing to load.", store.storage_path)
            return
        with open(store.storage_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        store._unreadable = True
        logger.error("Failed to load beliefs from %s: %s. Refusing writes.", store.storage_path, exc)
        return
    store.beliefs = {bid: Belief.from_dict(bdata) for bid, bdata in data.get("beliefs", {}).items()}
    for belief in store.beliefs.values():
        store._index_belief(belief)
    for edata in data.get("edges", []):
        try:
            edge = Edge.from_dict(edata)
        except (KeyError, TypeError, ValueError) as exc:
            store._unreadable = True
            logger.error("Malformed edge in %s: %s. Refusing writes.", store.storage_path, exc)
            return
        store.edges[edge.key()] = edge
    for cdata in data.get("changes", []):
        try:
            store.changes.append(BeliefChange.from_dict(cdata))
        except (KeyError, TypeError, ValueError) as exc:
            store._unreadable = True
            logger.error("Malformed change record in %s: %s. Refusing writes.", store.storage_path, exc)
            return
    latest = store.changes[-1].timestamp if store.changes else None
    if event_log_conflicts_with_snapshot(store.events_path, snapshot_exists=True, latest_change=latest):
        store._unreadable = True
        return
    # Migrate legacy contradictions_with lists to typed contradicts edges only
    # after the change window loads, so the migration save cannot drop it.
    migrated = 0
    for belief in store.beliefs.values():
        for other_id in belief.contradictions_with:
            probe = Edge(src_id=belief.id, dst_id=other_id, edge_type="contradicts")
            if probe.key() not in store.edges:
                probe.provenance.append(_MIGRATED_PROVENANCE)
                store.edges[probe.key()] = probe
                migrated += 1
    if migrated and not store.read_only:
        logger.info("Migrated %d contradictions_with pair(s) to typed edges for %s", migrated, store.expert_name)
        try:
            store._save()
        except BeliefStoreConflictError:
            # Another process wrote while this one loaded. The edges are derived
            # from stored lists, so the next write transaction reloads and migrates.
            logger.info("Deferred contradictions_with migration for %s to the next write", store.expert_name)
