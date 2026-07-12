"""Bounded locking and path-safe I/O for the consult lifecycle journal."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from filelock import FileLock
from filelock import Timeout as FileLockTimeout

from deepr.experts.consult_lifecycle_errors import (
    ConsultLifecycleLockTimeoutError,
    ConsultLifecycleStorageError,
)
from deepr.utils.atomic_io import append_jsonl_durable

_PATH_LOCKS: dict[Path, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _shared_path_lock(path: Path) -> threading.Lock:
    resolved = path.resolve()
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(resolved, threading.Lock())


def _lock_path(path: Path) -> Path:
    resolved = path.resolve()
    return resolved.with_name(f"{resolved.name}.lock")


def ensure_journal_parent(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConsultLifecycleStorageError("parent preparation", partial_write_possible=False) from exc


@contextmanager
def bounded_journal_lock(path: Path, timeout_seconds: float, *, maximum_seconds: float) -> Iterator[None]:
    timeout = min(maximum_seconds, max(0.0, timeout_seconds))
    started = time.perf_counter()
    try:
        local_lock = _shared_path_lock(path)
    except (OSError, RuntimeError) as exc:
        raise ConsultLifecycleStorageError("lock preparation", partial_write_possible=False) from exc
    if not local_lock.acquire(timeout=timeout):
        raise ConsultLifecycleLockTimeoutError("process lock")
    try:
        try:
            file_lock = FileLock(str(_lock_path(path)))
            remaining = max(0.0, timeout - (time.perf_counter() - started))
            file_lock.acquire(timeout=remaining)
        except FileLockTimeout as exc:
            raise ConsultLifecycleLockTimeoutError("file lock") from exc
        except (OSError, RuntimeError) as exc:
            raise ConsultLifecycleStorageError("lock preparation", partial_write_possible=False) from exc
        try:
            yield
        finally:
            try:
                file_lock.release()
            except OSError as exc:
                raise ConsultLifecycleStorageError("lock release", partial_write_possible=True) from exc
    finally:
        local_lock.release()


def read_journal_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConsultLifecycleStorageError("journal read", partial_write_possible=False) from exc


def append_journal_event(path: Path, event: Mapping[str, Any]) -> None:
    try:
        append_jsonl_durable(path, event, fsync=True)
    except OSError as exc:
        # A write or flush may have succeeded before the error became visible.
        raise ConsultLifecycleStorageError("journal append", partial_write_possible=True) from exc


__all__ = [
    "_lock_path",
    "_shared_path_lock",
    "append_journal_event",
    "bounded_journal_lock",
    "ensure_journal_parent",
    "read_journal_lines",
]
