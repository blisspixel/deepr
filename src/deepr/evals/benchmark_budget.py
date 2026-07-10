"""Durable spend reservations for provider-backed benchmark calls."""

from __future__ import annotations

import math
import threading
import uuid
from dataclasses import dataclass

from deepr.config import load_config
from deepr.experts.research_reservation_store import (
    ResearchReservationLimitExceeded,
    ResearchReservationStore,
)
from deepr.observability.cost_ledger import CostLedger


class BenchmarkBudgetExceeded(ValueError):
    """Raised before a benchmark call would exceed a spend ceiling."""


@dataclass(frozen=True)
class BenchmarkCostReservation:
    """One durable hold for a benchmark provider or judge call."""

    reservation_id: str
    job_id: str
    provider: str
    model: str
    cost_ceiling: float
    operation: str
    sequence: int
    metadata: dict[str, object]


class BenchmarkSpendGuard:
    """Reserve, settle, and ledger every call under one finite run ceiling."""

    def __init__(
        self,
        budget: float,
        *,
        run_id: str | None = None,
        ledger: CostLedger | None = None,
        reservation_store: ResearchReservationStore | None = None,
    ) -> None:
        if not math.isfinite(budget) or budget <= 0:
            raise BenchmarkBudgetExceeded("Benchmark runtime budget must be finite and greater than zero")
        config = load_config()
        self.budget = float(budget)
        self.run_id = run_id or uuid.uuid4().hex
        self._ledger = ledger or CostLedger()
        self._store = reservation_store or ResearchReservationStore()
        self._max_daily = float(config.get("max_daily_cost", 25.0))
        self._max_monthly = float(config.get("max_monthly_cost", 200.0))
        self._lock = threading.Lock()
        self._scheduled_cost = 0.0
        self._sequence = 0
        if not self._ledger.get_health()["writable"]:
            raise BenchmarkBudgetExceeded("Canonical cost ledger is not writable")

    @property
    def scheduled_cost(self) -> float:
        """Return the conservative cost committed by this run."""
        with self._lock:
            return self._scheduled_cost

    def reserve(
        self,
        *,
        provider: str,
        model: str,
        cost_ceiling: float,
        operation: str,
        metadata: dict[str, object] | None = None,
    ) -> BenchmarkCostReservation:
        """Durably reserve one call before it is submitted."""
        if not math.isfinite(cost_ceiling) or cost_ceiling < 0:
            raise BenchmarkBudgetExceeded("Benchmark call ceiling must be finite and non-negative")
        with self._lock:
            projected = self._scheduled_cost + cost_ceiling
            if projected > self.budget + 1e-12:
                raise BenchmarkBudgetExceeded(
                    f"Benchmark budget ${self.budget:.2f} would be exceeded "
                    f"(scheduled ${self._scheduled_cost:.2f}, next ${cost_ceiling:.2f})"
                )
            self._sequence += 1
            sequence = self._sequence
            self._scheduled_cost = projected

        reservation_id = uuid.uuid4().hex[:16]
        job_id = f"benchmark-{self.run_id}-{sequence}"
        try:
            self._store.reserve(
                reservation_id=reservation_id,
                job_id=job_id,
                reserved_cost=cost_ceiling,
                max_daily_cost=self._max_daily,
                max_monthly_cost=self._max_monthly,
            )
        except ResearchReservationLimitExceeded as exc:
            with self._lock:
                self._scheduled_cost -= cost_ceiling
            raise BenchmarkBudgetExceeded(str(exc)) from exc
        except Exception:
            with self._lock:
                self._scheduled_cost -= cost_ceiling
            raise

        return BenchmarkCostReservation(
            reservation_id=reservation_id,
            job_id=job_id,
            provider=provider,
            model=model,
            cost_ceiling=cost_ceiling,
            operation=operation,
            sequence=sequence,
            metadata=dict(metadata or {}),
        )

    def settle(self, reservation: BenchmarkCostReservation, *, status: str) -> None:
        """Append the conservative ledger event before closing its hold."""
        event_metadata = {
            **reservation.metadata,
            "run_id": self.run_id,
            "sequence": reservation.sequence,
            "status": status,
            "cost_basis": "conservative_call_ceiling",
            "actual_cost_reported": False,
        }
        idempotency_key = f"job:{reservation.job_id}:completion"

        def record() -> None:
            self._ledger.record_event(
                operation=reservation.operation,
                provider=reservation.provider,
                model=reservation.model,
                cost_usd=reservation.cost_ceiling,
                task_id=reservation.job_id,
                session_id=f"benchmark_{self.run_id}",
                source=f"benchmark_models.{reservation.operation}",
                metadata=event_metadata,
                idempotency_key=idempotency_key,
            )

        outcome = self._store.settle(reservation.reservation_id, reservation.cost_ceiling, record)
        if outcome == "missing":
            record()

    def refund(self, reservation: BenchmarkCostReservation) -> None:
        """Release a call that was definitively not submitted."""
        if self._store.refund(reservation.reservation_id):
            with self._lock:
                self._scheduled_cost = max(0.0, self._scheduled_cost - reservation.cost_ceiling)


__all__ = [
    "BenchmarkBudgetExceeded",
    "BenchmarkCostReservation",
    "BenchmarkSpendGuard",
]
