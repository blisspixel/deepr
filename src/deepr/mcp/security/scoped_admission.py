"""Atomic admission state for scoped MCP rate and budget limits."""

from __future__ import annotations

import math
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from deepr.mcp.security.scoped_keys import (
    RemoteMCPAuditLog,
    ScopedMCPBudgetDecision,
    ScopedMCPKeyContext,
    ScopedMCPRateLimitDecision,
    authorize_scoped_mcp_budget,
    authorize_scoped_mcp_rate_limit,
    constrain_scoped_mcp_budget_arguments,
    estimate_scoped_mcp_tool_cost,
)

_RATE_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class ScopedMCPAdmission:
    """One admitted operation whose budget hold has not yet settled."""

    reservation_id: str
    key_id: str
    operation: str
    estimated_cost_usd: float


@dataclass(frozen=True)
class ScopedMCPAdmissionResult:
    """Atomic rate and budget decision for one scoped operation."""

    arguments: dict[str, Any]
    admission: ScopedMCPAdmission | None
    rate_decision: ScopedMCPRateLimitDecision
    budget_decision: ScopedMCPBudgetDecision | None = None


class ScopedMCPAdmissionStore:
    """SQLite-backed compare-and-reserve state shared by HTTP workers."""

    def __init__(self, audit_log: RemoteMCPAuditLog, path: Path | None = None) -> None:
        self._audit_log = audit_log
        self.path = path or audit_log.path.with_suffix(".admission.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5.0, isolation_level=None)
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS scoped_keys (
                    key_id TEXT PRIMARY KEY,
                    settled_usd REAL NOT NULL DEFAULT 0.0,
                    seeded_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS admissions (
                    reservation_id TEXT PRIMARY KEY,
                    key_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
                    admitted_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS admissions_key_idx
                    ON admissions(key_id);

                CREATE TABLE IF NOT EXISTS rate_events (
                    reservation_id TEXT PRIMARY KEY,
                    key_id TEXT NOT NULL,
                    admitted_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS rate_events_key_time_idx
                    ON rate_events(key_id, admitted_at);
                """
            )
        finally:
            connection.close()

    def _seed_key(self, connection: sqlite3.Connection, key_id: str, now: float) -> float:
        row = connection.execute(
            "SELECT settled_usd FROM scoped_keys WHERE key_id = ?",
            (key_id,),
        ).fetchone()
        if row is not None:
            settled = float(row[0])
            if not math.isfinite(settled) or settled < 0:
                raise ValueError("Scoped MCP settled spend is invalid")
            return settled

        events = [event for event in self._audit_log.read_recent(limit=1_000_000) if event.key_id == key_id]
        costs: list[float] = []
        for event in events:
            if event.cost_usd is None:
                continue
            cost = float(event.cost_usd)
            if not math.isfinite(cost) or cost < 0:
                raise ValueError("Scoped MCP audit cost is invalid")
            costs.append(cost)
        settled = round(math.fsum(costs), 10)
        connection.execute(
            "INSERT INTO scoped_keys (key_id, settled_usd, seeded_at) VALUES (?, ?, ?)",
            (key_id, settled, now),
        )
        threshold = datetime.now(UTC) - timedelta(seconds=_RATE_WINDOW_SECONDS)
        for event in events:
            timestamp = event.timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            if timestamp.astimezone(UTC) < threshold:
                continue
            connection.execute(
                "INSERT INTO rate_events (reservation_id, key_id, admitted_at) VALUES (?, ?, ?)",
                (f"seed_{uuid.uuid4().hex}", key_id, timestamp.timestamp()),
            )
        return settled

    @staticmethod
    def _begin(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        if connection.in_transaction:
            connection.rollback()

    def reserve(
        self,
        context: ScopedMCPKeyContext,
        *,
        operation: str,
        arguments: dict[str, Any],
        tool_name: str | None,
    ) -> ScopedMCPAdmissionResult:
        """Atomically authorize and reserve one rate slot and budget hold."""
        now = time.time()
        if context.budget_limit_usd is not None and (
            not math.isfinite(context.budget_limit_usd) or context.budget_limit_usd < 0
        ):
            raise ValueError("Scoped MCP budget limit is invalid")
        connection = self._connect()
        try:
            self._begin(connection)
            settled = self._seed_key(connection, context.key_id, now)
            connection.execute(
                "DELETE FROM rate_events WHERE admitted_at < ?",
                (now - _RATE_WINDOW_SECONDS,),
            )
            rate_row = connection.execute(
                "SELECT COUNT(*), MIN(admitted_at) FROM rate_events WHERE key_id = ?",
                (context.key_id,),
            ).fetchone()
            calls_in_window = int(rate_row[0]) if rate_row else 0
            oldest = float(rate_row[1]) if rate_row and rate_row[1] is not None else None
            retry_after = None
            if oldest is not None:
                retry_after = max(math.ceil(oldest + _RATE_WINDOW_SECONDS - now), 1)
            rate_decision = authorize_scoped_mcp_rate_limit(
                context,
                calls_in_window,
                window_seconds=_RATE_WINDOW_SECONDS,
                retry_after_seconds=retry_after,
            )
            if not rate_decision.allowed:
                connection.commit()
                return ScopedMCPAdmissionResult(
                    arguments=dict(arguments),
                    admission=None,
                    rate_decision=rate_decision,
                )

            constrained = dict(arguments)
            budget_decision: ScopedMCPBudgetDecision | None = None
            estimated_cost = 0.0
            if tool_name is not None:
                hold_row = connection.execute(
                    "SELECT COALESCE(SUM(estimated_cost_usd), 0.0) FROM admissions WHERE key_id = ?",
                    (context.key_id,),
                ).fetchone()
                active_holds = float(hold_row[0]) if hold_row else 0.0
                if not math.isfinite(active_holds) or active_holds < 0:
                    raise ValueError("Scoped MCP active budget holds are invalid")
                committed = round(settled + active_holds, 10)
                constrained = constrain_scoped_mcp_budget_arguments(
                    context,
                    tool_name,
                    constrained,
                    committed,
                )
                budget_decision = authorize_scoped_mcp_budget(
                    context,
                    tool_name,
                    constrained,
                    committed,
                )
                if not budget_decision.allowed:
                    connection.commit()
                    return ScopedMCPAdmissionResult(
                        arguments=constrained,
                        admission=None,
                        rate_decision=rate_decision,
                        budget_decision=budget_decision,
                    )
                estimate = estimate_scoped_mcp_tool_cost(tool_name, constrained)
                estimated_cost = max(float(estimate or 0.0), 0.0)
                if not math.isfinite(estimated_cost):
                    raise ValueError("Scoped MCP tool cost estimate is invalid")

            reservation_id = f"mcp_adm_{uuid.uuid4().hex}"
            connection.execute(
                """INSERT INTO admissions
                   (reservation_id, key_id, operation, estimated_cost_usd, admitted_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (reservation_id, context.key_id, operation, estimated_cost, now),
            )
            connection.execute(
                "INSERT INTO rate_events (reservation_id, key_id, admitted_at) VALUES (?, ?, ?)",
                (reservation_id, context.key_id, now),
            )
            connection.commit()
            return ScopedMCPAdmissionResult(
                arguments=constrained,
                admission=ScopedMCPAdmission(
                    reservation_id=reservation_id,
                    key_id=context.key_id,
                    operation=operation,
                    estimated_cost_usd=estimated_cost,
                ),
                rate_decision=rate_decision,
                budget_decision=budget_decision,
            )
        except BaseException:
            self._rollback(connection)
            raise
        finally:
            connection.close()

    def record_audit(self, key_id: str, recorder: Callable[[], None]) -> None:
        """Serialize a non-admitted audit event with admission transactions."""
        now = time.time()
        connection = self._connect()
        try:
            self._begin(connection)
            self._seed_key(connection, key_id, now)
            recorder()
            connection.commit()
        except BaseException:
            self._rollback(connection)
            raise
        finally:
            connection.close()

    def settle(
        self,
        admission: ScopedMCPAdmission,
        *,
        actual_cost_usd: float | None,
        recorder: Callable[[float | None], None],
    ) -> bool:
        """Audit and settle an admitted operation exactly once."""
        connection = self._connect()
        try:
            self._begin(connection)
            row = connection.execute(
                """SELECT estimated_cost_usd FROM admissions
                   WHERE reservation_id = ? AND key_id = ?""",
                (admission.reservation_id, admission.key_id),
            ).fetchone()
            if row is None:
                connection.commit()
                return False

            estimate = max(float(row[0]), 0.0)
            actual = None
            if actual_cost_usd is not None:
                candidate = float(actual_cost_usd)
                if math.isfinite(candidate) and candidate >= 0:
                    actual = candidate
            charge = actual if actual is not None else estimate if estimate > 0 else None
            recorder(charge)
            if charge is not None:
                connection.execute(
                    "UPDATE scoped_keys SET settled_usd = settled_usd + ? WHERE key_id = ?",
                    (charge, admission.key_id),
                )
            connection.execute(
                "DELETE FROM admissions WHERE reservation_id = ?",
                (admission.reservation_id,),
            )
            connection.commit()
            return True
        except BaseException:
            self._rollback(connection)
            raise
        finally:
            connection.close()


__all__ = [
    "ScopedMCPAdmission",
    "ScopedMCPAdmissionResult",
    "ScopedMCPAdmissionStore",
]
