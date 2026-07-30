"""Exact durable identity for CostSafetyManager reservation transitions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from secrets import token_hex

from deepr.experts.research_reservation_store import ResearchReservationStore


@dataclass(frozen=True)
class DurableReservationIdentity:
    """Store identity retained by the manager that minted a durable hold."""

    job_id: str
    reserved_cost: float
    provider: str
    model: str
    dispatch_binding_id: str

    @classmethod
    def mint(
        cls,
        *,
        job_id: str,
        reserved_cost: float,
        provider: str,
        model: str,
        operation_type: str,
    ) -> DurableReservationIdentity:
        return cls(
            job_id=job_id,
            reserved_cost=reserved_cost,
            provider=provider.strip() or "deepr-internal",
            model=model.strip() or operation_type,
            dispatch_binding_id=token_hex(32),
        )

    def reserve(
        self,
        store: ResearchReservationStore,
        *,
        reservation_id: str,
        max_daily_cost: float,
        max_weekly_cost: float,
        max_monthly_cost: float,
    ) -> None:
        store.reserve(
            reservation_id=reservation_id,
            job_id=self.job_id,
            reserved_cost=self.reserved_cost,
            max_daily_cost=max_daily_cost,
            max_weekly_cost=max_weekly_cost,
            max_monthly_cost=max_monthly_cost,
            provider=self.provider,
            model=self.model,
            dispatch_binding_id=self.dispatch_binding_id,
        )

    def mark_provider_work(self, store: ResearchReservationStore, *, reservation_id: str) -> None:
        store.mark_provider_work_may_have_run(
            reservation_id,
            provider=self.provider,
            model=self.model,
            job_id=self.job_id,
            reserved_cost=self.reserved_cost,
            dispatch_binding_id=self.dispatch_binding_id,
            request_envelope_sha256=None,
        )

    def settle(
        self,
        store: ResearchReservationStore,
        *,
        reservation_id: str,
        actual_cost: float,
        record: Callable[[], None],
    ) -> str:
        return store.settle(
            reservation_id,
            actual_cost,
            record,
            job_id=self.job_id,
            reserved_cost=self.reserved_cost,
            provider=self.provider,
            model=self.model,
            dispatch_binding_id=self.dispatch_binding_id,
            request_envelope_sha256=None,
        )


__all__ = ["DurableReservationIdentity"]
