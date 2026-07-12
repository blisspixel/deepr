"""Durable, idempotent accounting for plan-quota CLI attempts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from deepr.backends.plan_quota.adapters import PlanQuotaAdapter
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedger,
    QuotaLedgerEvent,
)

DEFAULT_PLAN_ACCOUNTING_LOCK_TIMEOUT_SECONDS = 0.25


@dataclass(frozen=True)
class AttemptAccountingStatus:
    """Which canonical ledgers accepted one attempt observation."""

    quota_recorded: bool
    cost_recorded: bool


class AttemptAccountingError(RuntimeError):
    """One or both attempt ledgers could not durably accept an event."""

    def __init__(
        self,
        backend_id: str,
        *,
        status: AttemptAccountingStatus,
        failures: tuple[tuple[str, BaseException], ...],
    ) -> None:
        kinds = " and ".join(f"{kind} ledger write failed ({type(error).__name__})" for kind, error in failures)
        super().__init__(f"plan-quota accounting failed for {backend_id}: {kinds}")
        self.status = status
        self.failures = failures
        self.primary_cause = _root_cause(failures[-1][1])


def _root_cause(error: BaseException) -> BaseException:
    current = error
    seen: set[int] = set()
    while current.__cause__ is not None and id(current) not in seen:
        seen.add(id(current))
        current = current.__cause__
    return current


def record_plan_quota_attempt(
    adapter: PlanQuotaAdapter,
    *,
    attempt_id: str,
    operation: str,
    model: str | None,
    account_id: str = "",
    quota_ledger_path: Path | None = None,
    cost_ledger_path: Path | None = None,
    outcome: str,
    quota_event_type: QuotaEventType | None,
    quota_units: float | None,
    vendor_dispatched: bool,
    detail: str,
    reset_at: datetime | None = None,
    lock_timeout_seconds: float | None = None,
) -> AttemptAccountingStatus:
    """Append matching quota and canonical cost events for one attempt.

    Both writes are attempted even when the first fails. A shared idempotency
    key makes exact replay safe, while either storage failure remains visible to
    the caller instead of masquerading as complete accounting.
    """
    metadata = {
        "attempt_id": attempt_id,
        "backend_id": adapter.backend_id,
        "cost_model": adapter.cost_model.value,
        "quota_units": quota_units,
        "unit_name": adapter.unit_name,
        "outcome": outcome,
        "vendor_dispatched": vendor_dispatched,
        "attempted_quota_units": 1 if vendor_dispatched else 0,
        "quota_usage_observed": quota_units is not None,
    }
    quota_recorded = False
    cost_recorded = False
    failures: list[tuple[str, BaseException]] = []
    resolved_lock_timeout = (
        DEFAULT_PLAN_ACCOUNTING_LOCK_TIMEOUT_SECONDS if lock_timeout_seconds is None else lock_timeout_seconds
    )

    if quota_event_type is not None:
        try:
            QuotaLedger(
                quota_ledger_path,
                lock_timeout_seconds=resolved_lock_timeout,
            ).record_event(
                QuotaLedgerEvent(
                    backend_id=adapter.backend_id,
                    event_type=quota_event_type,
                    account_id=account_id,
                    cost_model=adapter.cost_model,
                    window_kind=adapter.window_kind,
                    units_used=quota_units,
                    unit_name=adapter.unit_name,
                    remaining_confidence=QuotaConfidence.UNKNOWN,
                    reset_at=reset_at,
                    overage_enabled=False,
                    detail=detail,
                    idempotency_key=attempt_id,
                    metadata={
                        key: value
                        for key, value in metadata.items()
                        if key not in {"backend_id", "cost_model", "quota_units", "unit_name"}
                    },
                ),
                require_fsync=True,
            )
            quota_recorded = True
        except Exception as error:
            failures.append(("quota", error))

    try:
        from deepr.observability.cost_ledger import CostLedger

        CostLedger(
            cost_ledger_path,
            lock_timeout_seconds=resolved_lock_timeout,
        ).record_event(
            operation=operation,
            provider=f"plan_quota:{adapter.backend_id}",
            cost_usd=0.0,
            model=model or adapter.exe,
            source="plan_quota",
            idempotency_key=attempt_id,
            metadata=metadata,
            lock_timeout_seconds=resolved_lock_timeout,
            require_fsync=True,
        )
        cost_recorded = True
    except Exception as error:
        failures.append(("cost", error))

    status = AttemptAccountingStatus(
        quota_recorded=quota_recorded,
        cost_recorded=cost_recorded,
    )
    if failures:
        raise AttemptAccountingError(
            adapter.backend_id,
            status=status,
            failures=tuple(failures),
        ) from failures[-1][1]
    return status
