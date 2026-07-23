"""Atomic file write helpers.

Crash-safe replacements for ``open(path, "w") + json.dump(...)``. Writes go to
a tempfile in the same directory and are then renamed onto the target path so
readers never observe a half-written file. Callers can also request atomic
no-replace creation, which links the complete tempfile only when the target is
still absent. On Windows replacement is retried because antivirus, indexer, or
open-handle races can produce transient ``PermissionError`` on ``os.replace``.

This module is the single source of truth for atomic writes across the
codebase. The pattern lives here so it stays consistent everywhere; see
``provider_router._save`` history for the original reference implementation.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Windows file-locking can race with indexer/AV; retry os.replace briefly.
_WINDOWS_RETRY_ATTEMPTS = 5
_WINDOWS_RETRY_BASE_SLEEP = 0.05


def _retry_attempts() -> int:
    return _WINDOWS_RETRY_ATTEMPTS if sys.platform == "win32" else 1


def _replace_tempfile(tmp_path: Path, target: Path) -> None:
    attempts = _retry_attempts()
    for attempt in range(attempts):
        try:
            os.replace(tmp_path, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(_WINDOWS_RETRY_BASE_SLEEP * (attempt + 1))


def _link_tempfile_without_replacement(tmp_path: Path, target: Path) -> None:
    # Linking a complete same-directory tempfile creates the target only if it
    # is still absent. Readers never observe a partially written destination.
    os.link(tmp_path, target)
    try:
        tmp_path.unlink()
    except OSError:
        logger.warning("Unable to remove temporary link after an atomic no-replace write")


def atomic_write_bytes(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    fsync: bool = False,
    overwrite: bool = True,
) -> None:
    """Atomically write ``data`` to ``path``.

    Writes to a tempfile in the same directory, then renames onto the target.
    If ``fsync`` is true the file is fsync'd before rename - slow, but the
    only way to survive a power-loss event without a corrupt or zero-byte
    file. Off by default; opt in for ledgers and other write-once records. If
    ``overwrite`` is false, atomically create the complete target or raise
    ``FileExistsError`` without changing the existing target.
    """
    target = Path(path)
    parent = target.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=parent, prefix=f".{target.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            if fsync:
                f.flush()
                os.fsync(f.fileno())

        if overwrite:
            _replace_tempfile(tmp_path, target)
        else:
            _link_tempfile_without_replacement(tmp_path, target)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def atomic_write_text(
    path: str | os.PathLike[str],
    text: str,
    *,
    encoding: str = "utf-8",
    fsync: bool = False,
    overwrite: bool = True,
) -> None:
    """Atomically write a text string to ``path``."""
    atomic_write_bytes(path, text.encode(encoding), fsync=fsync, overwrite=overwrite)


def atomic_write_json(
    path: str | os.PathLike[str],
    data: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
    default: Any = None,
    fsync: bool = False,
    overwrite: bool = True,
) -> None:
    """Atomically write ``data`` as JSON to ``path``.

    Serializes with ``json.dumps`` before the tempfile write so a serialization
    error (e.g. non-JSON-able value) raises before the tempfile is created and
    the target is left untouched.
    """
    payload = json.dumps(data, indent=indent, sort_keys=sort_keys, default=default)
    atomic_write_text(path, payload, fsync=fsync, overwrite=overwrite)


def append_jsonl_durable(
    path: str | os.PathLike[str],
    record: Any,
    *,
    encoding: str = "utf-8",
    fsync: bool = True,
    default: Any = None,
) -> None:
    """Append one JSON record to a JSONL file, flushed and fsync'd.

    Plain ``open(path, "a") + write(line)`` leaves the last record in the
    libc / kernel write buffer; a ``kill -9`` or power loss between ``write``
    and process exit truncates it. The cost ledger and routing log are
    declared canonical sources of truth - they need to survive crashes.

    The caller is responsible for any cross-process serialization (e.g. a
    lock around concurrent appenders).
    """
    target = Path(path)
    parent = target.parent
    if parent and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(record, default=default) + "\n"
    with open(target, "a", encoding=encoding) as f:
        f.write(line)
        if fsync:
            f.flush()
            os.fsync(f.fileno())


__all__ = [
    "append_jsonl_durable",
    "atomic_write_bytes",
    "atomic_write_json",
    "atomic_write_text",
]
