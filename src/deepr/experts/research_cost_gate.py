"""Atomic reservation and settlement for provider-backed research jobs."""

from __future__ import annotations

import threading
import weakref
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from deepr.core.costs import CostEstimate
from deepr.experts.cost_safety import CostSafetyManager, get_cost_safety_manager
from deepr.experts.research_reservation_store import (
    ResearchReservationLimitExceeded,
    ResearchReservationStore,
)
from deepr.observability.cost_ledger import CostLedger
from deepr.providers.base import ResearchRequest, ToolConfig
from deepr.services.research_bounds import bounded_research_cost_estimate

_configuration_lock = threading.Lock()
_configured_managers: weakref.WeakKeyDictionary[CostSafetyManager, bool] = weakref.WeakKeyDictionary()


def _configure_manager(
    manager: CostSafetyManager,
    *,
    max_cost_per_job: float,
    max_daily_cost: float,
    max_weekly_cost: float,
    max_monthly_cost: float,
) -> None:
    """Hydrate canonical spend once and apply only stricter process limits."""
    with _configuration_lock:
        if manager not in _configured_managers:
            now = datetime.now(UTC)
            ledger = CostLedger()
            manager.daily_cost = max(
                manager.daily_cost,
                ledger.get_total_cost(start_date=now.replace(hour=0, minute=0, second=0, microsecond=0)),
            )
            manager.monthly_cost = max(
                manager.monthly_cost,
                ledger.get_total_cost(start_date=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)),
            )
            _configured_managers[manager] = True
        if max_cost_per_job >= 0:
            manager.max_per_operation = min(
                manager.max_per_operation,
                max_cost_per_job,
                manager.ABSOLUTE_MAX_PER_OPERATION,
            )
        if max_daily_cost >= 0:
            manager.max_daily = min(manager.max_daily, max_daily_cost, manager.ABSOLUTE_MAX_DAILY)
        if max_weekly_cost >= 0:
            manager.max_weekly = min(manager.max_weekly, max_weekly_cost, manager.ABSOLUTE_MAX_WEEKLY)
        if max_monthly_cost >= 0:
            manager.max_monthly = min(manager.max_monthly, max_monthly_cost, manager.ABSOLUTE_MAX_MONTHLY)


class ResearchCostBlocked(ValueError):
    """Raised when research spend cannot be reserved before provider work."""


class PaidCostCeilingDivergence(RuntimeError):
    """Provider-reported spend exceeded the amount authorized before dispatch."""


@dataclass(frozen=True)
class ResearchCostReservation:
    """Serializable handle for one in-flight research cost reservation."""

    job_id: str
    provider: str
    model: str
    estimated_cost: float
    reservation_id: str
    manager: CostSafetyManager

    def metadata(self) -> dict[str, Any]:
        return {
            "cost_reservation_id": self.reservation_id,
            "cost_reservation_estimated_usd": self.estimated_cost,
            "cost_reservation_provider": self.provider,
            "cost_reservation_model": self.model,
        }


def reserve_configured_research_cost(
    *,
    job_id: str,
    provider: str,
    prompt: str,
    model: str,
    enable_web_search: bool,
    enable_code_interpreter: bool = False,
    enable_file_search: bool = False,
    max_cost_per_job: float | None = None,
    request: ResearchRequest | None = None,
) -> tuple[CostEstimate, ResearchCostReservation]:
    """Estimate and reserve one research job under configured hard limits."""
    from deepr.config import load_config
    from deepr.core.cost_caps import resolve_spend_caps

    config = load_config()
    spend_caps = resolve_spend_caps()
    configured_per_job = float(config.get("max_cost_per_job", 5.0))
    per_job = min(configured_per_job, max_cost_per_job) if max_cost_per_job is not None else configured_per_job
    bounded_request = request
    if bounded_request is None:
        tools: list[ToolConfig] = []
        if enable_web_search:
            tools.append(ToolConfig(type="web_search_preview"))
        if enable_code_interpreter:
            tools.append(ToolConfig(type="code_interpreter", container={"type": "auto", "memory_limit": "1g"}))
        if enable_file_search:
            tools.append(ToolConfig(type="file_search"))
        bounded_request = ResearchRequest(
            prompt=prompt,
            model=model,
            system_message="Research request",
            tools=tools,
        )
    estimate = bounded_research_cost_estimate(request=bounded_request, provider=provider)
    reservation = reserve_research_cost(
        job_id=job_id,
        provider=provider,
        model=model,
        estimate=estimate,
        max_cost_per_job=per_job,
        max_daily_cost=float(config.get("max_daily_cost", 25.0)),
        max_weekly_cost=spend_caps["weekly"],
        max_monthly_cost=float(config.get("max_monthly_cost", 200.0)),
    )
    return estimate, reservation


def reserve_configured_cost_ceiling(
    *,
    job_id: str,
    provider: str,
    model: str,
    max_cost_per_job: float | None = None,
) -> ResearchCostReservation:
    """Reserve the full configured per-call ceiling when usage is not yet known."""
    from deepr.config import load_config
    from deepr.core.cost_caps import resolve_spend_caps

    config = load_config()
    spend_caps = resolve_spend_caps()
    configured_per_job = float(config.get("max_cost_per_job", 5.0))
    if max_cost_per_job is not None and (
        isinstance(max_cost_per_job, bool) or not isfinite(max_cost_per_job) or max_cost_per_job <= 0
    ):
        raise ResearchCostBlocked("Requested paid-call ceiling must be finite and positive")
    requested_ceiling = configured_per_job if max_cost_per_job is None else float(max_cost_per_job)
    estimate = CostEstimate(
        min_cost=requested_ceiling,
        max_cost=requested_ceiling,
        expected_cost=requested_ceiling,
        model=model,
        reasoning="Full configured ceiling reserved until provider usage is available",
    )
    return reserve_research_cost(
        job_id=job_id,
        provider=provider,
        model=model,
        estimate=estimate,
        max_cost_per_job=configured_per_job,
        max_daily_cost=float(config.get("max_daily_cost", 25.0)),
        max_weekly_cost=spend_caps["weekly"],
        max_monthly_cost=float(config.get("max_monthly_cost", 200.0)),
    )


def reserve_research_cost(
    *,
    job_id: str,
    provider: str,
    model: str,
    estimate: CostEstimate,
    max_cost_per_job: float,
    max_daily_cost: float,
    max_monthly_cost: float,
    max_weekly_cost: float | None = None,
    manager: CostSafetyManager | None = None,
) -> ResearchCostReservation:
    """Atomically reserve expected cost against cumulative safety limits."""
    costs = (estimate.min_cost, estimate.expected_cost, estimate.max_cost)
    if not all(isfinite(cost) for cost in costs) or not 0 <= costs[0] <= costs[1] <= costs[2]:
        raise ResearchCostBlocked("Research cost estimate must be finite, non-negative, and ordered")
    weekly_limit = max_monthly_cost if max_weekly_cost is None else max_weekly_cost
    limits = (max_cost_per_job, max_daily_cost, weekly_limit, max_monthly_cost)
    if not all(isfinite(limit) and limit > 0 for limit in limits):
        raise ResearchCostBlocked("Research cost limits must be finite and positive")
    if estimate.max_cost > max_cost_per_job:
        raise ResearchCostBlocked(f"Job may cost ${estimate.max_cost:.2f}, exceeds limit of ${max_cost_per_job:.2f}.")
    # Production reservations use a fresh local manager because the durable
    # store is authoritative across processes. Reusing the singleton would
    # leave an API process holding stale in-memory cost after a worker settles.
    active_manager = manager or CostSafetyManager()
    _configure_manager(
        active_manager,
        max_cost_per_job=max_cost_per_job,
        max_daily_cost=max_daily_cost,
        max_weekly_cost=weekly_limit,
        max_monthly_cost=max_monthly_cost,
    )
    allowed, reason, needs_confirmation, reservation_id = active_manager.check_and_reserve(
        session_id=f"research_{job_id}",
        operation_type="research_submission",
        estimated_cost=estimate.max_cost,
        require_confirmation=False,
    )
    if not allowed or needs_confirmation or not reservation_id:
        raise ResearchCostBlocked(reason or "Research cost reservation was denied")
    try:
        ResearchReservationStore().reserve(
            reservation_id=reservation_id,
            job_id=job_id,
            reserved_cost=estimate.max_cost,
            max_daily_cost=max_daily_cost,
            max_weekly_cost=weekly_limit,
            max_monthly_cost=max_monthly_cost,
        )
    except ResearchReservationLimitExceeded as exc:
        active_manager.refund_reservation(reservation_id)
        raise ResearchCostBlocked(str(exc)) from exc
    except Exception:
        active_manager.refund_reservation(reservation_id)
        raise
    return ResearchCostReservation(
        job_id=job_id,
        provider=provider,
        model=model,
        estimated_cost=estimate.max_cost,
        reservation_id=reservation_id,
        manager=active_manager,
    )


def refund_research_cost(
    reservation: ResearchCostReservation | None,
    *,
    provider_work_did_not_run: bool = False,
) -> None:
    """Release an in-flight reservation without recording provider spend."""
    if reservation is not None:
        store = ResearchReservationStore()
        refunded = store.refund(
            reservation.reservation_id,
            provider_work_did_not_run=provider_work_did_not_run,
        )
        if refunded or not store.is_active(reservation.reservation_id):
            reservation.manager.refund_reservation(
                reservation.reservation_id,
                provider_work_did_not_run=provider_work_did_not_run,
            )


def mark_research_provider_work(reservation: ResearchCostReservation) -> None:
    """Durably mark that the provider boundary is about to be crossed."""
    ResearchReservationStore().mark_provider_work_may_have_run(reservation.reservation_id)


def restore_research_cost_reservation(
    *,
    job_id: str,
    metadata: Any,
    provider: str,
    model: str,
    manager: CostSafetyManager | None = None,
) -> ResearchCostReservation | None:
    """Rebuild a durable reservation handle from queue metadata after restart."""
    if not isinstance(metadata, dict):
        return None
    reservation_id = metadata.get("cost_reservation_id")
    estimated_cost = metadata.get("cost_reservation_estimated_usd")
    if not isinstance(reservation_id, str) or not reservation_id:
        return None
    if isinstance(estimated_cost, bool) or not isinstance(estimated_cost, (int, float)) or estimated_cost < 0:
        return None
    return ResearchCostReservation(
        job_id=job_id,
        provider=str(metadata.get("cost_reservation_provider") or provider),
        model=str(metadata.get("cost_reservation_model") or model),
        estimated_cost=float(estimated_cost),
        reservation_id=reservation_id,
        manager=manager or get_cost_safety_manager(),
    )


def settle_research_cost(
    reservation: ResearchCostReservation,
    *,
    actual_cost: float | None,
    tokens: int = 0,
    request_id: str = "",
    source: str,
    actual_cost_reported: bool | None = None,
    settlement_metadata: dict[str, Any] | None = None,
) -> None:
    """Settle a reservation and append one idempotent canonical ledger event."""
    reported = float(actual_cost) if actual_cost is not None else reservation.estimated_cost
    if not isfinite(reported) or reported < 0:
        raise ValueError("actual_cost must be finite and non-negative")
    settled_cost = max(0.0, reported)
    ceiling_diverged = settled_cost > reservation.estimated_cost + 1e-9
    event_metadata = dict(settlement_metadata or {})
    event_metadata.update(
        {
            "estimated_cost_usd": reservation.estimated_cost,
            "actual_cost_reported": actual_cost is not None if actual_cost_reported is None else actual_cost_reported,
        }
    )
    if ceiling_diverged:
        event_metadata["cost_ceiling_diverged"] = True
    idempotency_key = f"job:{reservation.job_id}:completion"

    def record() -> None:
        reservation.manager.record_cost(
            session_id=f"research_{reservation.job_id}",
            operation_type="research_completion",
            actual_cost=settled_cost,
            provider=reservation.provider,
            model=reservation.model,
            tokens_output=max(0, int(tokens)),
            request_id=request_id,
            idempotency_key=idempotency_key,
            source=source,
            metadata=event_metadata,
            reservation_id=reservation.reservation_id,
        )
        # CostSafetyManager supports a non-strict compatibility mode that logs
        # ledger write failures. Research settlement is stricter: retry the
        # same idempotent event directly and propagate failure so the durable
        # reservation remains active instead of creating a silent-money path.
        CostLedger().record_event(
            operation="research_completion",
            provider=reservation.provider,
            cost_usd=settled_cost,
            model=reservation.model,
            tokens_output=max(0, int(tokens)),
            task_id=f"research_{reservation.job_id}",
            session_id=f"research_{reservation.job_id}",
            request_id=request_id,
            source=source,
            metadata=event_metadata,
            idempotency_key=idempotency_key,
        )

    if ceiling_diverged:
        from deepr.core.cost_caps import (
            _freeze_paid_api_unlocked,
            budget_file_path,
            spend_policy_lock,
        )

        budget_path = budget_file_path()
        reason = (
            f"reported cost ${settled_cost:.6f} exceeded authorized ceiling "
            f"${reservation.estimated_cost:.6f} for job {reservation.job_id}"
        )
        with spend_policy_lock(budget_path):
            # Persist the cross-process stop while reservations and dispatch
            # marks are excluded, then record the overrun truth. If ledger
            # settlement fails, the freeze remains in force and the hold stays.
            _freeze_paid_api_unlocked(reason, target=budget_path)
            outcome = ResearchReservationStore().settle(reservation.reservation_id, settled_cost, record)
    else:
        outcome = ResearchReservationStore().settle(reservation.reservation_id, settled_cost, record)
    if outcome == "missing":
        record()
    if ceiling_diverged:
        raise PaidCostCeilingDivergence(
            f"Paid API frozen: reported cost ${settled_cost:.6f} exceeded "
            f"authorized ceiling ${reservation.estimated_cost:.6f}"
        )


def reconcile_research_cost_from_ledger(reservation: ResearchCostReservation | None, *, job_id: str) -> bool:
    """Close a hold after another component durably wrote its completion."""
    if not CostLedger().has_idempotency_key(f"job:{job_id}:completion"):
        return False
    store = ResearchReservationStore()
    store.active_cost()
    if reservation is not None and not store.is_active(reservation.reservation_id):
        reservation.manager.refund_reservation(reservation.reservation_id)
    return True


def record_unreserved_research_cost(
    *,
    job_id: str,
    provider: str,
    model: str,
    actual_cost: float | None,
    tokens: int = 0,
    request_id: str = "",
    source: str,
    manager: CostSafetyManager | None = None,
) -> float:
    """Record a legacy completion, using a ceiling when usage is missing."""
    missing_usage = actual_cost is None or (actual_cost == 0 and tokens <= 0)
    if missing_usage:
        from deepr.config import load_config

        configured_ceiling = float(load_config().get("max_cost_per_job", 5.0))
        if not isfinite(configured_ceiling) or configured_ceiling <= 0:
            raise ValueError("max_cost_per_job must be finite and positive")
        settled_cost = min(configured_ceiling, CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION)
    else:
        if actual_cost is None:  # pragma: no cover - guarded by missing_usage
            raise ValueError("actual_cost is required when usage is reported")
        settled_cost = float(actual_cost)
    (manager or get_cost_safety_manager()).record_cost(
        session_id=f"research_{job_id}",
        operation_type="research_completion",
        actual_cost=settled_cost,
        provider=provider,
        model=model,
        tokens_output=max(0, int(tokens)),
        request_id=request_id,
        idempotency_key=f"job:{job_id}:completion",
        source=source,
        metadata={
            "legacy_unreserved_job": True,
            "actual_cost_reported": not missing_usage,
            "settlement_basis": "configured_ceiling" if missing_usage else "provider_reported_cost",
        },
        require_ledger=True,
    )
    return settled_cost


__all__ = [
    "ResearchCostBlocked",
    "ResearchCostReservation",
    "mark_research_provider_work",
    "reconcile_research_cost_from_ledger",
    "record_unreserved_research_cost",
    "refund_research_cost",
    "reserve_configured_cost_ceiling",
    "reserve_configured_research_cost",
    "reserve_research_cost",
    "restore_research_cost_reservation",
    "settle_research_cost",
]
