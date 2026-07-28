"""Durable cross-process reservations for provider-backed research spend."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path

from deepr.observability.cost_ledger import (
    CostLedger,
    CostLedgerEvent,
    default_cost_data_dir,
    registered_cost_artifact_paths,
    well_known_cost_data_dirs,
)


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
    provider_work_may_have_run: bool


@dataclass(frozen=True)
class ReconciledResearchExposure:
    """One locked view of settled spend and durable in-flight exposure."""

    daily_settled_cost: float
    weekly_settled_cost: float
    monthly_settled_cost: float
    total_settled_cost: float
    active_cost: float
    unresolved_cost: float
    unresolved_count: int


def _validated_money(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return numeric


class ResearchReservationStore:
    """Serialize research reservations across API, web, and worker processes."""

    def __init__(self, path: Path | None = None, *, lock_timeout_seconds: float = 5.0) -> None:
        using_default_path = path is None and not os.environ.get("DEEPR_COST_DATA_DIR", "").strip()
        self._using_default_path = using_default_path
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
        return self._connect_path(self.path)

    def _connect_path(self, path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path, timeout=self._lock_timeout_seconds)
        connection.execute(f"PRAGMA busy_timeout = {int(self._lock_timeout_seconds * 1000)}")
        return connection

    def _sibling_reservation_paths(self) -> tuple[Path, ...]:
        if not self._using_default_path:
            return ()
        siblings: list[Path] = []
        for root in well_known_cost_data_dirs():
            candidate = root / "research_reservations.db"
            try:
                if candidate.resolve() != self.path.resolve():
                    siblings.append(candidate)
            except OSError as error:
                raise ResearchReservationStoreError("legacy reservation state cannot be resolved") from error
        return tuple(siblings)

    def _reservation_paths(self) -> tuple[Path, ...]:
        """Rediscover stable reservation databases for every authority read."""
        paths = [self.path]
        required = (
            {path.resolve() for path in registered_cost_artifact_paths("research_reservations.db")}
            if self._using_default_path
            else set()
        )
        for candidate in self._sibling_reservation_paths():
            try:
                if candidate.exists():
                    paths.append(candidate)
                elif candidate.resolve() in required:
                    raise ResearchReservationStoreError("registered reservation state is missing")
            except ResearchReservationStoreError:
                raise
            except OSError as error:
                raise ResearchReservationStoreError("legacy reservation state cannot be located") from error
        return tuple(paths)

    def _validated_identity_state(
        self,
    ) -> tuple[tuple[Path, ...], dict[str, Path], dict[str, Path]]:
        """Load one fail-closed cross-root identity index."""
        paths = self._reservation_paths()
        reservation_locations: dict[str, Path] = {}
        job_locations: dict[str, Path] = {}
        for path in paths:
            try:
                with closing(self._connect_path(path)) as connection:
                    rows = connection.execute(
                        "SELECT reservation_id, job_id FROM research_cost_reservations"
                    ).fetchall()
            except (OSError, sqlite3.Error) as error:
                raise ResearchReservationStoreError("reservation identity state is unreadable") from error
            for reservation_id, job_id in rows:
                reservation_key = str(reservation_id)
                job_key = str(job_id)
                if reservation_key in reservation_locations:
                    raise ResearchReservationStoreError("reservation identity exists in multiple cost roots")
                if job_key in job_locations:
                    raise ResearchReservationStoreError("reservation job identity exists in multiple cost roots")
                reservation_locations[reservation_key] = path
                job_locations[job_key] = path
        return paths, reservation_locations, job_locations

    @staticmethod
    def _completion_indexes(
        events: list[CostLedgerEvent],
    ) -> tuple[dict[str, CostLedgerEvent], dict[str, CostLedgerEvent]]:
        # A reservation-bound event is authoritative only for that exact
        # reservation. Job-only matching remains a compatibility fallback for
        # older completion events that contain no reservation identity.
        completed_jobs = {
            event.idempotency_key.removeprefix("job:").removesuffix(":completion"): event
            for event in events
            if event.idempotency_key.startswith("job:")
            and event.idempotency_key.endswith(":completion")
            and not event.metadata.get("cost_reservation_id")
        }
        completed_reservations = {
            str(event.metadata.get("cost_reservation_id")): event
            for event in events
            if event.metadata.get("cost_reservation_id")
        }
        return completed_jobs, completed_reservations

    @classmethod
    def _unsettled_active_rows(
        cls,
        connection: sqlite3.Connection,
        events: list[CostLedgerEvent],
    ) -> list[ActiveResearchReservation]:
        completed_jobs, completed_reservations = cls._completion_indexes(events)
        rows = connection.execute(
            """
            SELECT reservation_id, job_id, reserved_cost, created_at, provider_work_may_have_run
            FROM research_cost_reservations
            WHERE state = 'active'
            """
        ).fetchall()
        active: list[ActiveResearchReservation] = []
        for reservation_id, job_id, reserved_cost, created_at, provider_work_may_have_run in rows:
            reservation_key = str(reservation_id)
            job_key = str(job_id)
            completion = completed_reservations.get(reservation_key)
            if completion is not None:
                event_job_id = str(completion.metadata.get("cost_reservation_job_id", "") or "")
                if not event_job_id or event_job_id == job_key:
                    continue
            if job_key in completed_jobs:
                continue
            active.append(
                ActiveResearchReservation(
                    reservation_id=reservation_key,
                    job_id=job_key,
                    reserved_cost=float(reserved_cost),
                    created_at=datetime.fromisoformat(str(created_at)),
                    provider_work_may_have_run=bool(provider_work_may_have_run),
                )
            )
        return active

    def _sibling_active_reservations(
        self,
        events: list[CostLedgerEvent],
        *,
        paths: tuple[Path, ...],
        exclude_path: Path | None = None,
    ) -> list[ActiveResearchReservation]:
        active: list[ActiveResearchReservation] = []
        for path in paths:
            if exclude_path is not None and path == exclude_path:
                continue
            try:
                with closing(self._connect_path(path)) as connection:
                    active.extend(self._unsettled_active_rows(connection, events))
            except (OSError, sqlite3.Error, TypeError, ValueError) as error:
                raise ResearchReservationStoreError("legacy reservation state is unreadable") from error
        return active

    def _reservation_path(self, reservation_id: str) -> Path:
        _paths, reservation_locations, _job_locations = self._validated_identity_state()
        return reservation_locations.get(reservation_id, self.path)

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
        max_weekly_cost: float | None = None,
    ) -> None:
        """Atomically hold cost after checking fresh ledger and active holds."""
        from deepr.core.cost_caps import resolve_spend_caps, spend_policy_lock

        reserved_cost = _validated_money(reserved_cost, field_name="reserved_cost")
        max_daily_cost = _validated_money(max_daily_cost, field_name="max_daily_cost")
        max_monthly_cost = _validated_money(max_monthly_cost, field_name="max_monthly_cost")
        caller_weekly = (
            max_monthly_cost
            if max_weekly_cost is None
            else _validated_money(
                max_weekly_cost,
                field_name="max_weekly_cost",
            )
        )
        with spend_policy_lock():
            authority = resolve_spend_caps()
            max_daily_cost = min(max_daily_cost, authority["daily"])
            max_weekly_cost = min(caller_weekly, authority["weekly"])
            max_monthly_cost = min(max_monthly_cost, authority["monthly"])
            now = datetime.now(UTC)
            paths, reservation_locations, job_locations = self._validated_identity_state()
            ledger = CostLedger()
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")

                def commit_hold(events: list[CostLedgerEvent]) -> None:
                    self._reconcile_rows(connection, events)
                    self._expire_stale_council_predispatch_rows(connection, now)
                    if reservation_id in reservation_locations or job_id in job_locations:
                        raise ResearchReservationStoreError("reservation identity already exists in cost state")
                    primary_active = float(
                        connection.execute(
                            "SELECT COALESCE(SUM(reserved_cost), 0) "
                            "FROM research_cost_reservations WHERE state = 'active'"
                        ).fetchone()[0]
                    )
                    sibling_active = sum(
                        row.reserved_cost
                        for row in self._sibling_active_reservations(
                            events,
                            paths=paths,
                            exclude_path=self.path,
                        )
                    )
                    active = primary_active + sibling_active
                    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    week_start = day_start - timedelta(days=day_start.weekday())
                    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    monthly = sum(event.cost_usd for event in events if event.timestamp >= month_start)
                    weekly = sum(event.cost_usd for event in events if event.timestamp >= week_start)
                    daily = sum(event.cost_usd for event in events if event.timestamp >= day_start)
                    if daily + active + reserved_cost > max_daily_cost:
                        raise ResearchReservationLimitExceeded(
                            f"Daily limit ${max_daily_cost:.2f} would be exceeded "
                            f"(spent ${daily:.2f}, reserved ${active:.2f}, +${reserved_cost:.2f})"
                        )
                    if weekly + active + reserved_cost > max_weekly_cost:
                        raise ResearchReservationLimitExceeded(
                            f"Weekly limit ${max_weekly_cost:.2f} would be exceeded "
                            f"(spent ${weekly:.2f}, reserved ${active:.2f}, +${reserved_cost:.2f})"
                        )
                    if monthly + active + reserved_cost > max_monthly_cost:
                        raise ResearchReservationLimitExceeded(
                            f"Monthly limit ${max_monthly_cost:.2f} would be exceeded "
                            f"(spent ${monthly:.2f}, reserved ${active:.2f}, +${reserved_cost:.2f})"
                        )
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
        job_completions, reservation_completions = ResearchReservationStore._completion_indexes(events)
        reconciled = 0
        rows = connection.execute(
            "SELECT reservation_id, job_id FROM research_cost_reservations WHERE state = 'active'"
        ).fetchall()
        for reservation_id, job_id in rows:
            event = reservation_completions.get(str(reservation_id)) or job_completions.get(str(job_id))
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
        """Revalidate aggregate authority and make a hold non-expiring."""
        from deepr.core.cost_caps import resolve_spend_caps, spend_policy_lock

        with spend_policy_lock():
            authority = resolve_spend_caps()
            now = datetime.now(UTC)
            ledger = CostLedger()
            paths, reservation_locations, _job_locations = self._validated_identity_state()
            reservation_path = reservation_locations.get(reservation_id, self.path)
            with closing(self._connect_path(reservation_path)) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")

                def commit_mark(events: list[CostLedgerEvent]) -> None:
                    self._reconcile_rows(connection, events)
                    self._expire_stale_council_predispatch_rows(connection, now)
                    row = connection.execute(
                        "SELECT reserved_cost FROM research_cost_reservations "
                        "WHERE reservation_id = ? AND state = 'active'",
                        (reservation_id,),
                    ).fetchone()
                    if row is None:
                        raise RuntimeError("durable reservation is not active")
                    reserved_cost = float(row[0])
                    target_active = float(
                        connection.execute(
                            "SELECT COALESCE(SUM(reserved_cost), 0) "
                            "FROM research_cost_reservations WHERE state = 'active'"
                        ).fetchone()[0]
                    )
                    other_active = sum(
                        row.reserved_cost
                        for row in self._sibling_active_reservations(
                            events,
                            paths=paths,
                            exclude_path=reservation_path,
                        )
                    )
                    active = target_active + other_active
                    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    week_start = day_start - timedelta(days=day_start.weekday())
                    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    daily = sum(event.cost_usd for event in events if event.timestamp >= day_start)
                    weekly = sum(event.cost_usd for event in events if event.timestamp >= week_start)
                    monthly = sum(event.cost_usd for event in events if event.timestamp >= month_start)
                    changed = (
                        reserved_cost > authority["per_job"]
                        or daily + active > authority["daily"]
                        or weekly + active > authority["weekly"]
                        or monthly + active > authority["monthly"]
                    )
                    if changed:
                        raise ResearchReservationLimitExceeded(
                            "Paid API aggregate authority changed before provider dispatch"
                        )
                    connection.execute(
                        """
                        UPDATE research_cost_reservations
                        SET provider_work_may_have_run = 1
                        WHERE reservation_id = ? AND state = 'active'
                        """,
                        (reservation_id,),
                    )
                    connection.commit()

                ledger.with_locked_accounting_events(
                    commit_mark,
                    lock_timeout_seconds=self._lock_timeout_seconds,
                )

    def refund(self, reservation_id: str, *, provider_work_did_not_run: bool = False) -> bool:
        """Close an active durable reservation without recording spend."""
        reservation_path = self._reservation_path(reservation_id)
        with closing(self._connect_path(reservation_path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE research_cost_reservations
                SET state = 'refunded', closed_at = ?
                WHERE reservation_id = ?
                  AND state = 'active'
                  AND (? = 1 OR provider_work_may_have_run = 0)
                """,
                (datetime.now(UTC).isoformat(), reservation_id, int(provider_work_did_not_run)),
            )
            return cursor.rowcount > 0

    def settle(self, reservation_id: str, actual_cost: float, record: Callable[[], None]) -> str:
        """Write the ledger event and close its hold under one process lock."""
        actual_cost = _validated_money(actual_cost, field_name="actual_cost")
        reservation_path = self._reservation_path(reservation_id)
        with closing(self._connect_path(reservation_path)) as connection, connection:
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
        paths, _reservation_locations, _job_locations = self._validated_identity_state()
        ledger = CostLedger()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")

            def reconcile_and_total(events: list[CostLedgerEvent]) -> float:
                self._reconcile_rows(connection, events)
                primary_total = float(
                    connection.execute(
                        "SELECT COALESCE(SUM(reserved_cost), 0) FROM research_cost_reservations WHERE state = 'active'"
                    ).fetchone()[0]
                )
                sibling_total = sum(
                    row.reserved_cost
                    for row in self._sibling_active_reservations(
                        events,
                        paths=paths,
                        exclude_path=self.path,
                    )
                )
                connection.commit()
                return primary_total + sibling_total

            return ledger.with_locked_accounting_events(
                reconcile_and_total,
                lock_timeout_seconds=self._lock_timeout_seconds,
            )

    def exposure_snapshot(self, *, now: datetime | None = None) -> ReconciledResearchExposure:
        """Return one strict snapshot without a settlement-to-hold race."""
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        day_start = observed_at.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = day_start - timedelta(days=day_start.weekday())
        month_start = observed_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        paths, _reservation_locations, _job_locations = self._validated_identity_state()
        ledger = CostLedger()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")

            def reconcile_and_snapshot(events: list[CostLedgerEvent]) -> ReconciledResearchExposure:
                self._reconcile_rows(connection, events)
                primary_active, primary_unresolved, primary_unresolved_count = connection.execute(
                    """
                    SELECT
                        COALESCE(SUM(reserved_cost), 0),
                        COALESCE(SUM(CASE WHEN provider_work_may_have_run = 1 THEN reserved_cost ELSE 0 END), 0),
                        COALESCE(SUM(CASE WHEN provider_work_may_have_run = 1 THEN 1 ELSE 0 END), 0)
                    FROM research_cost_reservations
                    WHERE state = 'active'
                    """
                ).fetchone()
                sibling_active = self._sibling_active_reservations(
                    events,
                    paths=paths,
                    exclude_path=self.path,
                )
                active_cost = float(primary_active) + sum(row.reserved_cost for row in sibling_active)
                unresolved_cost = float(primary_unresolved) + sum(
                    row.reserved_cost for row in sibling_active if row.provider_work_may_have_run
                )
                unresolved_count = int(primary_unresolved_count) + sum(
                    1 for row in sibling_active if row.provider_work_may_have_run
                )
                daily_settled = sum(event.cost_usd for event in events if event.timestamp >= day_start)
                weekly_settled = sum(event.cost_usd for event in events if event.timestamp >= week_start)
                monthly_settled = sum(event.cost_usd for event in events if event.timestamp >= month_start)
                total_settled = sum(event.cost_usd for event in events)
                connection.commit()
                return ReconciledResearchExposure(
                    daily_settled_cost=float(daily_settled),
                    weekly_settled_cost=float(weekly_settled),
                    monthly_settled_cost=float(monthly_settled),
                    total_settled_cost=float(total_settled),
                    active_cost=float(active_cost),
                    unresolved_cost=float(unresolved_cost),
                    unresolved_count=int(unresolved_count),
                )

            return ledger.with_locked_accounting_events(
                reconcile_and_snapshot,
                lock_timeout_seconds=self._lock_timeout_seconds,
            )

    def active_reservations(self) -> list[ActiveResearchReservation]:
        """Return active holds for queue-backed orphan reconciliation."""
        paths, _reservation_locations, _job_locations = self._validated_identity_state()
        reservations: dict[str, ActiveResearchReservation] = {}
        for path in paths:
            try:
                with closing(self._connect_path(path)) as connection:
                    rows = connection.execute(
                        """
                        SELECT reservation_id, job_id, reserved_cost, created_at, provider_work_may_have_run
                        FROM research_cost_reservations
                        WHERE state = 'active'
                        ORDER BY created_at, reservation_id
                        """
                    ).fetchall()
            except (OSError, sqlite3.Error) as error:
                raise ResearchReservationStoreError("reservation state is unreadable") from error
            for reservation_id, job_id, reserved_cost, created_at, provider_work_may_have_run in rows:
                key = str(reservation_id)
                item = ActiveResearchReservation(
                    reservation_id=key,
                    job_id=str(job_id),
                    reserved_cost=float(reserved_cost),
                    created_at=datetime.fromisoformat(str(created_at)),
                    provider_work_may_have_run=bool(provider_work_may_have_run),
                )
                if key in reservations and reservations[key] != item:
                    raise ResearchReservationStoreError("reservation identity conflicts across cost roots")
                reservations[key] = item
        return sorted(reservations.values(), key=lambda item: (item.created_at, item.reservation_id))

    def is_active(self, reservation_id: str) -> bool:
        """Return whether provider work may still consume this hold."""
        reservation_path = self._reservation_path(reservation_id)
        with closing(self._connect_path(reservation_path)) as connection, connection:
            row = connection.execute(
                "SELECT 1 FROM research_cost_reservations WHERE reservation_id = ? AND state = 'active'",
                (reservation_id,),
            ).fetchone()
        return row is not None

    def state(self, reservation_id: str) -> str | None:
        """Return the durable reservation state for terminal accounting UX."""
        reservation_path = self._reservation_path(reservation_id)
        with closing(self._connect_path(reservation_path)) as connection, connection:
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
        reservation_path = self._reservation_path(reservation_id)
        with closing(self._connect_path(reservation_path)) as connection, connection:
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
    "ReconciledResearchExposure",
    "ResearchReservationLimitExceeded",
    "ResearchReservationStore",
    "ResearchReservationStoreError",
]
