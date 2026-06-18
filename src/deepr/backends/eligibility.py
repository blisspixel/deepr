"""Eligibility decisions for capacity-aware backend routing.

This module is the safety gate between visibility and execution. It consumes
normalized backend profiles plus the latest observed quota state and returns a
pure decision the scheduler can log before any adapter runs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from deepr.backends.quota_ledger import QuotaConfidence, QuotaLedgerEvent, QuotaState
from deepr.backends.research_backend import ResearchBackend


class BackendEligibilityStatus(str, Enum):
    """Why a backend can or cannot receive work right now."""

    ELIGIBLE = "eligible"
    UNAVAILABLE = "unavailable"
    TASK_UNSUPPORTED = "task_unsupported"
    METERED_REQUIRES_BUDGET = "metered_requires_budget"
    QUOTA_UNKNOWN = "quota_unknown"
    QUOTA_EXHAUSTED = "quota_exhausted"
    QUOTA_QUARANTINED = "quota_quarantined"
    QUOTA_OVERAGE_ENABLED = "quota_overage_enabled"
    RESERVE_FLOOR_REACHED = "reserve_floor_reached"


@dataclass(frozen=True)
class BackendEligibility:
    """A routing decision for one backend and optional account."""

    backend_id: str
    status: BackendEligibilityStatus
    reason: str
    quota_state: QuotaState | None = None

    @property
    def eligible(self) -> bool:
        return self.status == BackendEligibilityStatus.ELIGIBLE

    @property
    def account_id(self) -> str:
        return self.quota_state.account_id if self.quota_state else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "account_id": self.account_id,
            "eligible": self.eligible,
            "status": self.status.value,
            "reason": self.reason,
            "quota_state": self.quota_state.to_dict() if self.quota_state else None,
        }


_BLOCK_PRIORITY = {
    BackendEligibilityStatus.QUOTA_QUARANTINED: 0,
    BackendEligibilityStatus.QUOTA_OVERAGE_ENABLED: 1,
    BackendEligibilityStatus.QUOTA_EXHAUSTED: 2,
    BackendEligibilityStatus.RESERVE_FLOOR_REACHED: 3,
    BackendEligibilityStatus.QUOTA_UNKNOWN: 4,
}


def evaluate_backend_eligibility(
    backend: ResearchBackend,
    *,
    quota_states: Iterable[QuotaState] = (),
    task_class: str = "",
    allow_metered: bool = False,
    require_observed_quota: bool = True,
) -> BackendEligibility:
    """Return the current routing eligibility for ``backend``.

    ``allow_metered`` means the caller has already performed the explicit
    budget gate for a metered backend. Plan-quota overage remains blocked here;
    callers should choose the separate metered backend when they intentionally
    want paid fallback.
    """
    if not backend.available:
        return _decision(
            backend,
            BackendEligibilityStatus.UNAVAILABLE,
            f"{backend.backend_id} is not available: {backend.detail or 'no availability signal'}",
        )

    if task_class and not backend.supports_task(task_class):
        return _decision(
            backend,
            BackendEligibilityStatus.TASK_UNSUPPORTED,
            f"{backend.backend_id} is not admitted for task class {task_class!r}",
        )

    if backend.is_metered and not allow_metered:
        return _decision(
            backend,
            BackendEligibilityStatus.METERED_REQUIRES_BUDGET,
            f"{backend.backend_id} is metered and requires an explicit budget gate",
        )

    if not backend.requires_quota_ledger:
        return _decision(backend, BackendEligibilityStatus.ELIGIBLE, f"{backend.backend_id} is eligible")

    matching_states = sorted(
        (state for state in quota_states if state.backend_id == backend.backend_id),
        key=lambda state: state.key,
    )
    if not matching_states:
        if require_observed_quota:
            return _decision(
                backend,
                BackendEligibilityStatus.QUOTA_UNKNOWN,
                f"{backend.backend_id} has no observed quota state",
            )
        return _decision(
            backend,
            BackendEligibilityStatus.ELIGIBLE,
            f"{backend.backend_id} is eligible without an observed quota gate",
        )

    decisions = [
        _decision_for_quota_state(backend, state, require_observed_quota=require_observed_quota)
        for state in matching_states
    ]
    eligible = [decision for decision in decisions if decision.eligible]
    if eligible:
        return eligible[0]
    return min(decisions, key=lambda decision: _BLOCK_PRIORITY.get(decision.status, 99))


def _decision(
    backend: ResearchBackend,
    status: BackendEligibilityStatus,
    reason: str,
    quota_state: QuotaState | None = None,
) -> BackendEligibility:
    return BackendEligibility(
        backend_id=backend.backend_id,
        status=status,
        reason=reason,
        quota_state=quota_state,
    )


def _decision_for_quota_state(
    backend: ResearchBackend,
    state: QuotaState,
    *,
    require_observed_quota: bool,
) -> BackendEligibility:
    event = state.latest_event
    label = state.key

    if state.quarantined:
        return _decision(
            backend,
            BackendEligibilityStatus.QUOTA_QUARANTINED,
            f"{label} is quarantined: {event.detail or 'adapter marked it unsafe'}",
            state,
        )

    if event.overage_enabled is True:
        return _decision(
            backend,
            BackendEligibilityStatus.QUOTA_OVERAGE_ENABLED,
            f"{label} reports overage enabled; paid fallback must be explicit",
            state,
        )

    if state.exhausted:
        return _decision(
            backend,
            BackendEligibilityStatus.QUOTA_EXHAUSTED,
            f"{label} quota is exhausted",
            state,
        )

    if _reserve_floor_reached(event):
        return _decision(
            backend,
            BackendEligibilityStatus.RESERVE_FLOOR_REACHED,
            f"{label} is at or below its reserve floor",
            state,
        )

    if require_observed_quota and _quota_remaining_unknown(event):
        return _decision(
            backend,
            BackendEligibilityStatus.QUOTA_UNKNOWN,
            f"{label} has no trusted remaining-quota observation",
            state,
        )

    return _decision(
        backend,
        BackendEligibilityStatus.ELIGIBLE,
        f"{label} has observed quota available",
        state,
    )


def _quota_remaining_unknown(event: QuotaLedgerEvent) -> bool:
    return event.units_remaining is None or event.remaining_confidence == QuotaConfidence.UNKNOWN


def _reserve_floor_reached(event: QuotaLedgerEvent) -> bool:
    if event.units_remaining is None:
        return False

    reserve_units = _number_from_metadata(event.metadata, "reserve_floor_units")
    if reserve_units is not None:
        return event.units_remaining <= reserve_units

    if event.reserve_floor_fraction is None:
        return False

    total_units = _number_from_metadata(event.metadata, "units_total")
    if total_units is None:
        total_units = _number_from_metadata(event.metadata, "quota_units_total")
    if total_units is None:
        return False

    return event.units_remaining <= total_units * event.reserve_floor_fraction


def _number_from_metadata(metadata: dict[str, Any], key: str) -> float | None:
    value = metadata.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
