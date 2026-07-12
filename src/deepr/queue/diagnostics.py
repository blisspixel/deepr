"""Read-only diagnostics for the local research queue."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class QueueDiagnostics:
    """A non-mutating snapshot of local queue lifecycle state."""

    path: Path
    initialized: bool
    total: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    stale_queued_candidates: int = 0
    stale_with_reservation_metadata: int = 0
    oldest_stale_submitted_at: str | None = None


def inspect_queue(
    db_path: str | Path,
    *,
    stale_after: timedelta = timedelta(hours=24),
    now: datetime | None = None,
) -> QueueDiagnostics:
    """Inspect a queue without creating, migrating, or updating its database.

    A stale candidate is a queued, zero-attempt row older than ``stale_after``.
    This is a lifecycle signal only. It does not prove that a job is abandoned,
    and this function never changes a job or cost reservation.
    """
    if stale_after.total_seconds() <= 0:
        raise ValueError("stale_after must be positive")

    path = Path(db_path)
    if not path.exists():
        return QueueDiagnostics(path=path, initialized=False)

    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("research_queue",),
        ).fetchone()
        if table is None:
            return QueueDiagnostics(path=path, initialized=False)

        status_rows = connection.execute("SELECT status, COUNT(*) FROM research_queue GROUP BY status").fetchall()
        by_status = {str(status): int(count) for status, count in status_rows}
        total = sum(by_status.values())

        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(research_queue)").fetchall()}
        required = {"status", "attempts", "submitted_at", "metadata"}
        if not required.issubset(columns):
            return QueueDiagnostics(path=path, initialized=True, total=total, by_status=by_status)

        observed_now = now or datetime.now(UTC)
        if observed_now.tzinfo is None:
            observed_now = observed_now.replace(tzinfo=UTC)
        cutoff = (observed_now.astimezone(UTC) - stale_after).isoformat()
        stale_rows = connection.execute(
            """
            SELECT submitted_at, metadata
            FROM research_queue
            WHERE status = 'queued'
              AND COALESCE(attempts, 0) = 0
              AND submitted_at < ?
            ORDER BY submitted_at ASC
            """,
            (cutoff,),
        ).fetchall()

        reservation_refs = 0
        for _submitted_at, raw_metadata in stale_rows:
            try:
                metadata = json.loads(raw_metadata) if raw_metadata else {}
            except (json.JSONDecodeError, TypeError):
                metadata = {}
            if isinstance(metadata, dict) and metadata.get("cost_reservation_id"):
                reservation_refs += 1

        oldest = str(stale_rows[0][0]) if stale_rows else None
        return QueueDiagnostics(
            path=path,
            initialized=True,
            total=total,
            by_status=by_status,
            stale_queued_candidates=len(stale_rows),
            stale_with_reservation_metadata=reservation_refs,
            oldest_stale_submitted_at=oldest,
        )
    finally:
        connection.close()
