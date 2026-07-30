"""Atomic reservation and settlement for provider-backed research jobs."""

from __future__ import annotations

import threading
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hmac import compare_digest
from math import isfinite
from secrets import token_hex
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
_RESERVATION_AUTHORITY_VERSION = "provider-request-bound-v2"


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
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            def settled_totals(events: list[Any]) -> tuple[float, float]:
                return (
                    float(sum(event.cost_usd for event in events if event.timestamp >= day_start)),
                    float(sum(event.cost_usd for event in events if event.timestamp >= month_start)),
                )

            daily_settled, monthly_settled = ledger.with_locked_accounting_events(settled_totals)
            manager.daily_cost = max(
                manager.daily_cost,
                daily_settled,
            )
            manager.monthly_cost = max(
                manager.monthly_cost,
                monthly_settled,
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


class ResearchCostSettlementError(RuntimeError):
    """Provider spend could not close its exact durable reservation."""


@dataclass(frozen=True)
class ResearchCostReservation:
    """Serializable handle for one in-flight research cost reservation."""

    job_id: str
    provider: str
    model: str
    estimated_cost: float
    reservation_id: str
    manager: CostSafetyManager
    dispatch_binding_id: str = field(default="", repr=False)
    request_envelope_sha256: str | None = field(default=None, repr=False)

    def metadata(self) -> dict[str, Any]:
        return {
            "cost_reservation_authority_version": _RESERVATION_AUTHORITY_VERSION,
            "cost_reservation_id": self.reservation_id,
            "cost_reservation_estimated_usd": self.estimated_cost,
            "cost_reservation_provider": self.provider,
            "cost_reservation_model": self.model,
            "cost_reservation_dispatch_binding_id": self.dispatch_binding_id,
            "cost_reservation_request_envelope_sha256": self.request_envelope_sha256,
        }


def bind_research_request_digest(
    reservation: ResearchCostReservation,
    request: ResearchRequest,
) -> str:
    """Carry the exact paid request digest through dispatch and settlement."""
    from deepr.providers.dispatch_authority import research_request_sha256

    request_sha256 = research_request_sha256(request)
    current = reservation.request_envelope_sha256
    if current is not None and not compare_digest(current, request_sha256):
        raise ResearchCostBlocked("Research request does not match its cost reservation")
    object.__setattr__(reservation, "request_envelope_sha256", request_sha256)
    return request_sha256


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
    from deepr.core.cost_caps import paid_api_provider_scope

    with paid_api_provider_scope(provider):
        return _reserve_configured_research_cost_under_provider_scope(
            job_id=job_id,
            provider=provider,
            prompt=prompt,
            model=model,
            enable_web_search=enable_web_search,
            enable_code_interpreter=enable_code_interpreter,
            enable_file_search=enable_file_search,
            max_cost_per_job=max_cost_per_job,
            request=request,
        )


def _reserve_configured_research_cost_under_provider_scope(
    *,
    job_id: str,
    provider: str,
    prompt: str,
    model: str,
    enable_web_search: bool,
    enable_code_interpreter: bool,
    enable_file_search: bool,
    max_cost_per_job: float | None,
    request: ResearchRequest | None,
) -> tuple[CostEstimate, ResearchCostReservation]:
    """Reserve configured research after binding all nested cap reads."""
    from deepr.config import load_config
    from deepr.core.cost_caps import resolve_spend_caps

    config = load_config()
    spend_caps = resolve_spend_caps(provider=provider)
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
        max_daily_cost=float(config.get("max_daily_cost", 2.0)),
        max_weekly_cost=spend_caps["weekly"],
        max_monthly_cost=float(config.get("max_monthly_cost", 5.0)),
        request=request,
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
    from deepr.core.cost_caps import paid_api_provider_scope

    with paid_api_provider_scope(provider):
        return _reserve_configured_cost_ceiling_under_provider_scope(
            job_id=job_id,
            provider=provider,
            model=model,
            max_cost_per_job=max_cost_per_job,
        )


def _reserve_configured_cost_ceiling_under_provider_scope(
    *,
    job_id: str,
    provider: str,
    model: str,
    max_cost_per_job: float | None,
) -> ResearchCostReservation:
    """Reserve a full ceiling after binding all nested cap reads."""
    from deepr.config import load_config
    from deepr.core.cost_caps import resolve_spend_caps

    config = load_config()
    spend_caps = resolve_spend_caps(provider=provider)
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
        max_daily_cost=float(config.get("max_daily_cost", 2.0)),
        max_weekly_cost=spend_caps["weekly"],
        max_monthly_cost=float(config.get("max_monthly_cost", 5.0)),
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
    request: ResearchRequest | None = None,
) -> ResearchCostReservation:
    """Atomically reserve expected cost against cumulative safety limits."""
    from deepr.core.cost_caps import paid_api_provider_scope

    with paid_api_provider_scope(provider):
        return _reserve_research_cost_under_provider_scope(
            job_id=job_id,
            provider=provider,
            model=model,
            estimate=estimate,
            max_cost_per_job=max_cost_per_job,
            max_daily_cost=max_daily_cost,
            max_monthly_cost=max_monthly_cost,
            max_weekly_cost=max_weekly_cost,
            manager=manager,
            request=request,
        )


def _reserve_research_cost_under_provider_scope(
    *,
    job_id: str,
    provider: str,
    model: str,
    estimate: CostEstimate,
    max_cost_per_job: float,
    max_daily_cost: float,
    max_monthly_cost: float,
    max_weekly_cost: float | None,
    manager: CostSafetyManager | None,
    request: ResearchRequest | None,
) -> ResearchCostReservation:
    """Reserve after provider evidence has been bound to this context."""
    costs = (estimate.min_cost, estimate.expected_cost, estimate.max_cost)
    if not all(isfinite(cost) for cost in costs) or not 0 <= costs[0] <= costs[1] <= costs[2]:
        raise ResearchCostBlocked("Research cost estimate must be finite, non-negative, and ordered")
    weekly_limit = max_monthly_cost if max_weekly_cost is None else max_weekly_cost
    limits = (max_cost_per_job, max_daily_cost, weekly_limit, max_monthly_cost)
    if not all(isfinite(limit) and limit > 0 for limit in limits):
        raise ResearchCostBlocked("Research cost limits must be finite and positive")
    if estimate.max_cost > max_cost_per_job:
        raise ResearchCostBlocked(f"Job may cost ${estimate.max_cost:.2f}, exceeds limit of ${max_cost_per_job:.2f}.")
    if request is not None and request.model != model:
        raise ResearchCostBlocked("Research request model does not match its cost reservation")
    from deepr.providers.dispatch_authority import canonical_provider_key, research_request_sha256

    canonical_provider = canonical_provider_key(provider)
    dispatch_binding_id = token_hex(32)
    request_envelope_sha256 = research_request_sha256(request) if request is not None else None
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
            provider=canonical_provider,
            model=model,
            dispatch_binding_id=dispatch_binding_id,
            request_envelope_sha256=request_envelope_sha256,
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
        dispatch_binding_id=dispatch_binding_id,
        request_envelope_sha256=request_envelope_sha256,
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


def mark_research_provider_work(
    reservation: ResearchCostReservation,
    request: ResearchRequest | None = None,
) -> object:
    """Durably mark that the provider boundary is about to be crossed."""
    from deepr.core.cost_caps import paid_api_provider_scope
    from deepr.providers.dispatch_authority import (
        _mint_paid_dispatch_grant,
        canonical_provider_key,
        require_unproxied_paid_transport,
        research_request_sha256,
    )

    require_unproxied_paid_transport()
    store = ResearchReservationStore()
    if request is None:
        with paid_api_provider_scope(reservation.provider):
            store.mark_provider_work_may_have_run(reservation.reservation_id)
        return None
    if request.model != reservation.model:
        raise ResearchCostBlocked("Research request model does not match its durable reservation")
    request_sha256 = research_request_sha256(request)
    provider = canonical_provider_key(reservation.provider)
    with paid_api_provider_scope(reservation.provider):
        store.mark_provider_work_may_have_run(
            reservation.reservation_id,
            provider=provider,
            model=reservation.model,
            job_id=reservation.job_id,
            reserved_cost=reservation.estimated_cost,
            dispatch_binding_id=reservation.dispatch_binding_id,
            request_envelope_sha256=request_sha256,
        )
    bind_research_request_digest(reservation, request)
    return _mint_paid_dispatch_grant(
        provider=provider,
        model=reservation.model,
        reservation_id=reservation.reservation_id,
        job_id=reservation.job_id,
        request_sha256=request_sha256,
    )


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
    if metadata.get("cost_reservation_authority_version") != _RESERVATION_AUTHORITY_VERSION:
        return None
    reservation_id = metadata.get("cost_reservation_id")
    estimated_cost = metadata.get("cost_reservation_estimated_usd")
    dispatch_binding_id = metadata.get("cost_reservation_dispatch_binding_id")
    request_envelope_sha256 = metadata.get("cost_reservation_request_envelope_sha256")
    if not isinstance(reservation_id, str) or not reservation_id:
        return None
    if (
        isinstance(estimated_cost, bool)
        or not isinstance(estimated_cost, (int, float))
        or not isfinite(float(estimated_cost))
        or estimated_cost < 0
    ):
        return None
    if (
        not isinstance(dispatch_binding_id, str)
        or len(dispatch_binding_id) != 64
        or any(character not in "0123456789abcdef" for character in dispatch_binding_id)
    ):
        return None
    if request_envelope_sha256 is not None and (
        not isinstance(request_envelope_sha256, str)
        or len(request_envelope_sha256) != 64
        or any(character not in "0123456789abcdef" for character in request_envelope_sha256)
    ):
        return None
    return ResearchCostReservation(
        job_id=job_id,
        provider=str(metadata.get("cost_reservation_provider") or provider),
        model=str(metadata.get("cost_reservation_model") or model),
        estimated_cost=float(estimated_cost),
        reservation_id=reservation_id,
        manager=manager or get_cost_safety_manager(),
        dispatch_binding_id=dispatch_binding_id,
        request_envelope_sha256=request_envelope_sha256,
    )


def _validated_settlement_costs(
    reservation: ResearchCostReservation,
    actual_cost: float | None,
) -> tuple[float, float | None, bool]:
    """Validate money before exact identity matching or ledger mutation."""
    raw_ceiling = reservation.estimated_cost
    ceiling = (
        float(raw_ceiling)
        if not isinstance(raw_ceiling, bool)
        and isinstance(raw_ceiling, (int, float))
        and isfinite(float(raw_ceiling))
        and raw_ceiling >= 0
        else None
    )
    if actual_cost is not None and (isinstance(actual_cost, bool) or not isinstance(actual_cost, (int, float))):
        raise ValueError("actual_cost must be finite and non-negative")
    reported = float(actual_cost) if actual_cost is not None else ceiling if ceiling is not None else 0.0
    if not isfinite(reported) or reported < 0:
        raise ValueError("actual_cost must be finite and non-negative")
    settled_cost = max(0.0, reported)
    return settled_cost, ceiling, ceiling is not None and settled_cost > ceiling + 1e-9


def _settle_exact_durable_reservation(
    reservation: ResearchCostReservation,
    *,
    settled_cost: float,
    record: Callable[[], None],
) -> str:
    """Atomically match every handle identity field before closing its hold."""
    from deepr.providers.dispatch_authority import canonical_provider_key

    canonical_provider = canonical_provider_key(reservation.provider) if isinstance(reservation.provider, str) else ""
    return ResearchReservationStore().settle(
        reservation.reservation_id,
        settled_cost,
        record,
        job_id=reservation.job_id,
        reserved_cost=reservation.estimated_cost,
        provider=canonical_provider,
        model=reservation.model,
        dispatch_binding_id=reservation.dispatch_binding_id,
        request_envelope_sha256=reservation.request_envelope_sha256,
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
    settled_cost, validated_ceiling, ceiling_diverged = _validated_settlement_costs(reservation, actual_cost)
    event_metadata = dict(settlement_metadata or {})
    event_metadata.update(
        {
            "actual_cost_reported": actual_cost is not None if actual_cost_reported is None else actual_cost_reported,
            "cost_reservation_id": reservation.reservation_id,
            "cost_reservation_job_id": reservation.job_id,
        }
    )
    if validated_ceiling is not None:
        event_metadata["estimated_cost_usd"] = validated_ceiling
    else:
        event_metadata["estimated_cost_invalid"] = True
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

    def settle_durable() -> str:
        return _settle_exact_durable_reservation(
            reservation,
            settled_cost=settled_cost,
            record=record,
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
            _freeze_paid_api_unlocked(reason, target=budget_path, kind="cost_ceiling_divergence")
            outcome = settle_durable()
    else:
        outcome = settle_durable()
    if outcome != "settled":
        integrity_metadata = dict(event_metadata)
        integrity_metadata.pop("cost_reservation_id", None)
        integrity_metadata.pop("cost_reservation_job_id", None)
        integrity_metadata.update(
            {
                "durable_settlement_outcome": outcome,
                "accounting_integrity_failure": True,
                "attempted_cost_reservation_id": str(reservation.reservation_id),
                "attempted_cost_reservation_job_id": str(reservation.job_id),
            }
        )
        reason = (
            f"durable research reservation {reservation.reservation_id} was {outcome} "
            f"while settling provider spend for job {reservation.job_id}"
        )
        if not ceiling_diverged:
            from deepr.core.cost_caps import (
                _freeze_paid_api_unlocked,
                budget_file_path,
                spend_policy_lock,
            )

            budget_path = budget_file_path()
            with spend_policy_lock(budget_path):
                _freeze_paid_api_unlocked(reason, target=budget_path, kind="legacy")
        # Never label a forged or corrupted attempt as completion of the real
        # reservation. The full durable hold stays active while the attempted
        # provider spend is appended as a separate integrity event.
        CostLedger().record_event(
            operation="research_settlement_integrity",
            provider=str(reservation.provider),
            cost_usd=settled_cost,
            model=str(reservation.model),
            tokens_output=max(0, int(tokens)),
            task_id=f"research_{reservation.job_id}",
            session_id=f"research_{reservation.job_id}",
            request_id=request_id,
            source=source,
            metadata=integrity_metadata,
            idempotency_key=(
                f"research-settlement-integrity:{reservation.reservation_id}:{reservation.job_id}:{outcome}"
            ),
        )
        raise ResearchCostSettlementError(reason)
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
    """Record a legacy completion and freeze paid dispatch pending review."""
    from deepr.config import load_config

    configured_ceiling = float(load_config().get("max_cost_per_job", 5.0))
    if not isfinite(configured_ceiling) or configured_ceiling <= 0:
        raise ValueError("max_cost_per_job must be finite and positive")
    configured_ceiling = min(configured_ceiling, CostSafetyManager.ABSOLUTE_MAX_PER_OPERATION)
    missing_usage = actual_cost is None or (actual_cost == 0 and tokens <= 0)
    if missing_usage:
        settled_cost = configured_ceiling
        settlement_basis = "configured_ceiling"
    else:
        if actual_cost is None:  # pragma: no cover - guarded by missing_usage
            raise ValueError("actual_cost is required when usage is reported")
        settled_cost = max(float(actual_cost), configured_ceiling)
        settlement_basis = (
            "provider_reported_cost" if settled_cost == float(actual_cost) else "configured_ceiling_floor"
        )
    if not isfinite(settled_cost) or settled_cost < 0:
        raise ValueError("actual_cost must be finite and non-negative")

    from deepr.core.cost_caps import (
        _freeze_paid_api_unlocked,
        budget_file_path,
        spend_policy_lock,
    )

    budget_path = budget_file_path()
    reason = (
        "legacy unreserved paid API completion detected for job "
        f"{str(job_id)[:128]}; paid API frozen pending accounting review"
    )
    active_manager = manager or get_cost_safety_manager()
    with spend_policy_lock(budget_path):
        # Freeze first so even a required ledger failure leaves paid dispatch
        # disabled. The worker can retry the idempotent truth record later.
        _freeze_paid_api_unlocked(reason, target=budget_path, kind="legacy")
        active_manager.record_cost(
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
                "settlement_basis": settlement_basis,
            },
            require_ledger=True,
        )
    return settled_cost


__all__ = [
    "ResearchCostBlocked",
    "ResearchCostReservation",
    "ResearchCostSettlementError",
    "bind_research_request_digest",
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
