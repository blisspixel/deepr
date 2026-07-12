"""Durable cross-process reservations for provider-backed research spend."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path

from deepr.observability.cost_ledger import CostLedger, CostLedgerEvent, default_cost_data_dir


class ResearchReservationLimitExceeded(ValueError):
    """Raised when a durable reservation would exceed a spend ceiling."""


class ResearchReservationStoreError(RuntimeError):
    """Path-safe failure from durable reservation storage."""


@dataclass(frozen=True)
class ActiveResearchReservation:
    """Minimal durable state needed to repair an orphaned cost hold."""

    reservation_id: str
    job_id: str
    reserved_cost: float
    created_at: datetime


class ResearchReservationStore:
    """Serialize research reservations across API, web, and worker processes."""

    def __init__(self, path: Path | None = None, *, lock_timeout_seconds: float = 5.0) -> None:
        self.path = path or default_cost_data_dir() / "research_reservations.db"
        if (
            isinstance(lock_timeout_seconds, bool)
            or not isinstance(lock_timeout_seconds, (int, float))
            or not isfinite(lock_timeout_seconds)
            or lock_timeout_seconds < 0
        ):
            raise ValueError("lock_timeout_seconds must be finite and non-negative")
        self._lock_timeout_seconds = float(lock_timeout_seconds)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
        except (OSError, sqlite3.Error) as error:
            raise ResearchReservationStoreError("durable reservation storage initialization failed") from error

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=self._lock_timeout_seconds)
        connection.execute(f"PRAGMA busy_timeout = {int(self._lock_timeout_seconds * 1000)}")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_cost_reservations (
                    reservation_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL UNIQUE,
                    reserved_cost REAL NOT NULL CHECK (reserved_cost >= 0),
                    state TEXT NOT NULL CHECK (state IN ('active', 'settled', 'refunded')),
                    created_at TEXT NOT NULL,
                    closed_at TEXT,
                    actual_cost REAL,
                    provider_work_may_have_run INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(research_cost_reservations)").fetchall()
            }
            if "provider_work_may_have_run" not in columns:
                connection.execute(
                    "ALTER TABLE research_cost_reservations "
                    "ADD COLUMN provider_work_may_have_run INTEGER NOT NULL DEFAULT 0"
                )

    def reserve(
        self,
        *,
        reservation_id: str,
        job_id: str,
        reserved_cost: float,
        max_daily_cost: float,
        max_monthly_cost: float,
    ) -> None:
        """Atomically hold cost after checking fresh ledger and active holds."""
        now = datetime.now(UTC)
        ledger = CostLedger()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")

            def commit_hold(events: list[CostLedgerEvent]) -> None:
                self._reconcile_rows(connection, events)
                self._expire_stale_council_predispatch_rows(connection, now)
                active = float(
                    connection.execute(
                        "SELECT COALESCE(SUM(reserved_cost), 0) FROM research_cost_reservations WHERE state = 'active'"
                    ).fetchone()[0]
                )
                day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                monthly = sum(event.cost_usd for event in events if event.timestamp >= month_start)
                daily = sum(event.cost_usd for event in events if event.timestamp >= day_start)
                if daily + active + reserved_cost > max_daily_cost:
                    raise ResearchReservationLimitExceeded(
                        f"Daily limit ${max_daily_cost:.2f} would be exceeded "
                        f"(spent ${daily:.2f}, reserved ${active:.2f}, +${reserved_cost:.2f})"
                    )
                if monthly + active + reserved_cost > max_monthly_cost:
                    raise ResearchReservationLimitExceeded(f"Monthly limit ${max_monthly_cost:.2f} would be exceeded")
                connection.execute(
                    """
                    INSERT INTO research_cost_reservations
                        (reservation_id, job_id, reserved_cost, state, created_at)
                    VALUES (?, ?, ?, 'active', ?)
                    """,
                    (reservation_id, job_id, reserved_cost, now.isoformat()),
                )
                connection.commit()

            ledger.with_locked_accounting_events(
                commit_hold,
                lock_timeout_seconds=self._lock_timeout_seconds,
            )

    @staticmethod
    def _reconcile_rows(connection: sqlite3.Connection, events: list[CostLedgerEvent]) -> int:
        """Close active holds whose canonical completion event already exists."""
        completions = {
            event.idempotency_key: event
            for event in events
            if event.idempotency_key.startswith("job:") and event.idempotency_key.endswith(":completion")
        }
        reservation_completions = {
            str(event.metadata.get("cost_reservation_id")): event
            for event in events
            if event.metadata.get("cost_reservation_id")
        }
        reconciled = 0
        rows = connection.execute(
            "SELECT reservation_id, job_id FROM research_cost_reservations WHERE state = 'active'"
        ).fetchall()
        for reservation_id, job_id in rows:
            event = completions.get(f"job:{job_id}:completion") or reservation_completions.get(str(reservation_id))
            if event is None:
                continue
            event_job_id = str(event.metadata.get("cost_reservation_job_id", "") or "")
            if event_job_id and event_job_id != str(job_id):
                continue
            connection.execute(
                """
                UPDATE research_cost_reservations
                SET state = 'settled', closed_at = ?, actual_cost = ?
                WHERE reservation_id = ? AND state = 'active'
                """,
                (datetime.now(UTC).isoformat(), event.cost_usd, reservation_id),
            )
            reconciled += 1
        return reconciled

    @staticmethod
    def _expire_stale_council_predispatch_rows(connection: sqlite3.Connection, now: datetime) -> None:
        cutoff = datetime.fromtimestamp(now.timestamp() - 3600.0, UTC).isoformat()
        connection.execute(
            """
            UPDATE research_cost_reservations
            SET state = 'refunded', closed_at = ?
            WHERE state = 'active'
              AND job_id GLOB 'council_*'
              AND provider_work_may_have_run = 0
              AND created_at < ?
            """,
            (now.isoformat(), cutoff),
        )

    def mark_provider_work_may_have_run(self, reservation_id: str) -> None:
        """Make a council hold non-expiring before provider dispatch."""
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE research_cost_reservations
                SET provider_work_may_have_run = 1
                WHERE reservation_id = ? AND state = 'active'
                """,
                (reservation_id,),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("durable reservation is not active")

    def refund(self, reservation_id: str) -> bool:
        """Close an active durable reservation without recording spend."""
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE research_cost_reservations
                SET state = 'refunded', closed_at = ?
                WHERE reservation_id = ? AND state = 'active'
                """,
                (datetime.now(UTC).isoformat(), reservation_id),
            )
            return cursor.rowcount > 0

    def settle(self, reservation_id: str, actual_cost: float, record: Callable[[], None]) -> str:
        """Write the ledger event and close its hold under one process lock."""
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM research_cost_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            if row is None:
                return "missing"
            if row[0] == "settled":
                record()
                return "settled"
            if row[0] != "active":
                return str(row[0])
            record()
            connection.execute(
                """
                UPDATE research_cost_reservations
                SET state = 'settled', closed_at = ?, actual_cost = ?
                WHERE reservation_id = ?
                """,
                (datetime.now(UTC).isoformat(), actual_cost, reservation_id),
            )
            return "settled"

    def active_cost(self) -> float:
        """Return active durable holds for diagnostics and tests."""
        ledger = CostLedger()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")

            def reconcile_and_total(events: list[CostLedgerEvent]) -> float:
                self._reconcile_rows(connection, events)
                total = float(
                    connection.execute(
                        "SELECT COALESCE(SUM(reserved_cost), 0) FROM research_cost_reservations WHERE state = 'active'"
                    ).fetchone()[0]
                )
                connection.commit()
                return total

            return ledger.with_locked_accounting_events(
                reconcile_and_total,
                lock_timeout_seconds=self._lock_timeout_seconds,
            )

    def active_reservations(self) -> list[ActiveResearchReservation]:
        """Return active holds for queue-backed orphan reconciliation."""
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT reservation_id, job_id, reserved_cost, created_at
                FROM research_cost_reservations
                WHERE state = 'active'
                ORDER BY created_at, reservation_id
                """
            ).fetchall()
        return [
            ActiveResearchReservation(
                reservation_id=str(reservation_id),
                job_id=str(job_id),
                reserved_cost=float(reserved_cost),
                created_at=datetime.fromisoformat(str(created_at)),
            )
            for reservation_id, job_id, reserved_cost, created_at in rows
        ]

    def is_active(self, reservation_id: str) -> bool:
        """Return whether provider work may still consume this hold."""
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT 1 FROM research_cost_reservations WHERE reservation_id = ? AND state = 'active'",
                (reservation_id,),
            ).fetchone()
        return row is not None

    def state(self, reservation_id: str) -> str | None:
        """Return the durable reservation state for terminal accounting UX."""
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT state FROM research_cost_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def is_active_for_job(
        self,
        *,
        reservation_id: str,
        job_id: str,
        reserved_cost: float,
    ) -> bool:
        """Return whether an exact job-owned hold is active.

        Dispatch must bind all three durable identifiers. Checking only the
        reservation ID could let stale or corrupted queue metadata borrow an
        unrelated job's active hold.
        """
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT 1
                FROM research_cost_reservations
                WHERE reservation_id = ?
                  AND job_id = ?
                  AND reserved_cost = ?
                  AND state = 'active'
                """,
                (reservation_id, job_id, reserved_cost),
            ).fetchone()
        return row is not None


__all__ = [
    "ActiveResearchReservation",
    "ResearchReservationLimitExceeded",
    "ResearchReservationStore",
    "ResearchReservationStoreError",
]
