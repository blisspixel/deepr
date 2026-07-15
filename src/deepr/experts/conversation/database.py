"""SQLite connection and transaction lifecycle for expert conversations."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from deepr.experts.conversation.models import ConversationError, ErrorCode
from deepr.experts.conversation.schema import initialize_schema


def connect_database(path: Path, *, busy_timeout_ms: int) -> sqlite3.Connection:
    """Open one configured short-lived connection."""
    connection = sqlite3.connect(
        path,
        timeout=busy_timeout_ms / 1000,
        isolation_level=None,
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA secure_delete=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection
    except sqlite3.Error:
        connection.close()
        raise


def initialize_database(path: Path, *, busy_timeout_ms: int) -> None:
    """Create the parent and v1 schema, or fail with a safe typed error."""
    if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int) or busy_timeout_ms < 1:
        raise ConversationError(ErrorCode.INVALID_REQUEST, "Storage busy timeout must be a positive integer.")
    connection: sqlite3.Connection | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect_database(path, busy_timeout_ms=busy_timeout_ms)
        connection.execute("PRAGMA journal_mode=WAL")
        initialize_schema(connection)
        connection.commit()
        if os.name != "nt":
            path.chmod(0o600)
    except (OSError, sqlite3.Error) as exc:
        raise ConversationError(ErrorCode.STORAGE_FAILED, "Conversation storage could not be initialized.") from exc
    finally:
        if connection is not None:
            connection.close()


@contextmanager
def transaction(path: Path, *, busy_timeout_ms: int) -> Iterator[sqlite3.Connection]:
    """Own one short immediate transaction and translate storage failures."""
    connection: sqlite3.Connection | None = None
    try:
        connection = connect_database(path, busy_timeout_ms=busy_timeout_ms)
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.execute("COMMIT")
    except ConversationError:
        if connection is not None and connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    except sqlite3.Error as exc:
        if connection is not None and connection.in_transaction:
            connection.execute("ROLLBACK")
        raise ConversationError(ErrorCode.STORAGE_FAILED, "Conversation storage operation failed.") from exc
    finally:
        if connection is not None:
            connection.close()


@contextmanager
def reader(path: Path, *, busy_timeout_ms: int) -> Iterator[sqlite3.Connection]:
    """Own one read connection and translate storage failures."""
    connection: sqlite3.Connection | None = None
    try:
        connection = connect_database(path, busy_timeout_ms=busy_timeout_ms)
        yield connection
    except ConversationError:
        raise
    except sqlite3.Error as exc:
        raise ConversationError(ErrorCode.STORAGE_FAILED, "Conversation storage read failed.") from exc
    finally:
        if connection is not None:
            connection.close()
