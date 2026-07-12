"""Read-only queue lifecycle diagnostics."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from deepr.queue.diagnostics import inspect_queue


def _create_queue_db(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE research_queue (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                submitted_at DATETIME NOT NULL,
                metadata TEXT
            )
            """
        )


def test_missing_queue_is_not_created(tmp_path):
    db_path = tmp_path / "missing" / "research_queue.db"

    diagnostics = inspect_queue(db_path)

    assert diagnostics.initialized is False
    assert not db_path.exists()


def test_stale_candidates_are_counted_without_mutating_queue(tmp_path):
    db_path = tmp_path / "research_queue.db"
    _create_queue_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO research_queue VALUES (?, ?, ?, ?, ?)",
            [
                ("stale-held", "queued", 0, "2026-07-09T00:00:00+00:00", '{"cost_reservation_id":"r1"}'),
                ("stale-no-hold", "queued", 0, "2026-07-09T01:00:00+00:00", "{}"),
                ("attempted", "queued", 1, "2026-07-09T00:00:00+00:00", "{}"),
                ("recent", "queued", 0, "2026-07-11T11:00:00+00:00", "{}"),
                ("done", "completed", 1, "2026-07-09T00:00:00+00:00", "{}"),
            ],
        )
    before = db_path.read_bytes()

    diagnostics = inspect_queue(
        db_path,
        stale_after=timedelta(hours=24),
        now=datetime(2026, 7, 11, 12, tzinfo=UTC),
    )

    assert diagnostics.initialized is True
    assert diagnostics.total == 5
    assert diagnostics.by_status == {"completed": 1, "queued": 4}
    assert diagnostics.stale_queued_candidates == 2
    assert diagnostics.stale_with_reservation_metadata == 1
    assert diagnostics.oldest_stale_submitted_at == "2026-07-09T00:00:00+00:00"
    assert db_path.read_bytes() == before


def test_non_positive_stale_window_is_rejected(tmp_path):
    try:
        inspect_queue(tmp_path / "queue.db", stale_after=timedelta())
    except ValueError as exc:
        assert str(exc) == "stale_after must be positive"
    else:
        raise AssertionError("expected ValueError")
