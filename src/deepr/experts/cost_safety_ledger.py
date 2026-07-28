"""Canonical ledger commit helper for expert cost safety."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deepr.observability.cost_ledger import (
    CostLedger,
    CostLedgerDurabilityError,
    CostLedgerLockTimeout,
    CostLedgerReadError,
)

REQUIRED_COST_LEDGER_LOCK_TIMEOUT_SECONDS = 5.0


class DurableCostReservationError(RuntimeError):
    """A required cross-process cost reservation cannot be safely closed."""


@dataclass(frozen=True)
class CostRecord:
    session_id: str
    operation_type: str
    actual_cost: float
    details: str | None
    provider: str
    model: str
    tokens_input: int
    tokens_output: int
    request_id: str
    idempotency_key: str
    source: str
    metadata: dict[str, Any] | None
    agent_id: str
    reservation_id: str
    require_ledger: bool


class CostLedgerCommitError(RuntimeError):
    """Path-safe public failure retaining the original storage exception."""

    def __init__(self, *, error: BaseException, mode: str, mode_label: str) -> None:
        super().__init__(f"Cost ledger write failed in {mode_label}.")
        self.ledger_error = error
        errno = error.errno if isinstance(error, OSError) else None
        self.metadata: dict[str, str | int | None] = {
            "error_type": type(error).__name__,
            "errno": errno,
            "mode": mode,
        }


def append_cost_record(ledger: CostLedger, record: CostRecord) -> bool:
    """Append one fully shaped cost record to the canonical ledger."""
    return append_cost_event(
        ledger,
        session_id=record.session_id,
        operation_type=record.operation_type,
        actual_cost=record.actual_cost,
        details=record.details,
        provider=record.provider,
        model=record.model,
        tokens_input=record.tokens_input,
        tokens_output=record.tokens_output,
        request_id=record.request_id,
        idempotency_key=record.idempotency_key,
        source=record.source,
        metadata=record.metadata,
        agent_id=record.agent_id,
        require_ledger=record.require_ledger,
    )


def append_cost_event(
    ledger: CostLedger,
    *,
    session_id: str,
    operation_type: str,
    actual_cost: float,
    details: str | None,
    provider: str,
    model: str,
    tokens_input: int,
    tokens_output: int,
    request_id: str,
    idempotency_key: str,
    source: str,
    metadata: dict[str, Any] | None,
    agent_id: str,
    require_ledger: bool,
) -> bool:
    """Append one canonical event and fail if durable accounting is unavailable."""
    event_metadata = dict(metadata or {})
    if details:
        event_metadata["details"] = details
    try:
        ledger_result = ledger.record_event(
            operation=operation_type,
            provider=provider or "unknown",
            model=model or "",
            cost_usd=actual_cost,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            task_id=session_id,
            session_id=session_id,
            request_id=request_id,
            source=source,
            idempotency_key=idempotency_key,
            metadata=event_metadata,
            agent_id=agent_id,
            lock_timeout_seconds=REQUIRED_COST_LEDGER_LOCK_TIMEOUT_SECONDS,
            require_fsync=True,
        )
    except (OSError, CostLedgerDurabilityError, CostLedgerLockTimeout, CostLedgerReadError) as error:
        mode = "required_settlement" if require_ledger else "strict"
        mode_label = "required settlement" if require_ledger else "strict mode"
        raise CostLedgerCommitError(error=error, mode=mode, mode_label=mode_label) from error

    # Test doubles and legacy implementations may return no tuple, which
    # represents a normal successful append for backward compatibility.
    if isinstance(ledger_result, tuple) and len(ledger_result) == 2:
        return bool(ledger_result[1])
    return True


__all__ = [
    "CostLedgerCommitError",
    "CostRecord",
    "DurableCostReservationError",
    "append_cost_event",
    "append_cost_record",
    "seed_window_costs",
]


def seed_window_costs(ledger: CostLedger) -> tuple[float, float, float]:
    """Current (daily, weekly, monthly) canonical spend.

    An unreadable accounting source must not look like zero spend. Propagate the
    failure so paid admission stays disabled until the ledger is repaired.
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())

    def totals(events: list[Any]) -> tuple[float, float, float]:
        return (
            float(sum(event.cost_usd for event in events if event.timestamp >= day_start)),
            float(sum(event.cost_usd for event in events if event.timestamp >= week_start)),
            float(sum(event.cost_usd for event in events if event.timestamp >= month_start)),
        )

    return ledger.with_locked_accounting_events(totals)
