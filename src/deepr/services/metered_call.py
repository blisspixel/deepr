"""Durable admission for metered model calls."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import math
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, NoReturn, TypeVar

from deepr.core.costs import CostEstimator
from deepr.experts.research_cost_gate import (
    ResearchCostReservation,
    refund_research_cost,
    reserve_configured_cost_ceiling,
    settle_research_cost,
)
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.providers.dispatch_authority import canonical_provider_key, require_unproxied_paid_transport
from deepr.providers.registry_pricing import (
    get_resolved_model_contract_identity,
    provider_matches_model_contract,
)
from deepr.services.provider_receipts import (
    ProviderReceiptIdentifiers as _ProviderReceiptIdentifiers,
)
from deepr.services.provider_receipts import (
    extract_provider_receipt_identifiers as _provider_receipt_identifiers,
)
from deepr.services.provider_receipts import (
    merge_provider_receipt_identifiers as _merge_receipt_identifiers,
)
from deepr.services.provider_receipts import provider_receipt_settlement_fields

T = TypeVar("T")


class MeteredCallAccountingError(RuntimeError):
    """Raised when durable admission or settlement state cannot be updated."""


class ProviderModelIdentityError(ValueError):
    """Provider response identity cannot be reconciled to the reserved model."""


_METERED_DISPATCH_SEAL = object()


@dataclass
class _MeteredDispatchAuthority:
    provider: str
    model: str
    request_envelope: Mapping[str, Any] = field(repr=False)
    request_sha256: str
    call_identity: int
    seal: object = field(repr=False)
    marked: bool = False
    consumed: bool = False


def _canonical_request_envelope(
    *,
    provider: str,
    model: str,
    request_envelope: Mapping[str, Any] | None,
) -> str:
    if not isinstance(request_envelope, Mapping) or not request_envelope:
        raise MeteredCallAccountingError("Metered call requires a non-empty exact request envelope")
    try:
        return json.dumps(
            {
                "provider": canonical_provider_key(provider),
                "model": model,
                "request": dict(request_envelope),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise MeteredCallAccountingError("Metered call request envelope must be deterministic JSON") from exc


def _bind_dispatch_authority(
    *,
    provider: str,
    model: str,
    request_envelope: Mapping[str, Any] | None,
    call: object,
) -> _MeteredDispatchAuthority:
    if not callable(call):
        raise MeteredCallAccountingError("Metered call dispatch closure is not callable")
    if not isinstance(request_envelope, Mapping):
        raise MeteredCallAccountingError("Metered call requires a non-empty exact request envelope")
    canonical = _canonical_request_envelope(
        provider=provider,
        model=model,
        request_envelope=request_envelope,
    )
    return _MeteredDispatchAuthority(
        provider=canonical_provider_key(provider),
        model=model,
        request_envelope=request_envelope,
        request_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        call_identity=id(call),
        seal=_METERED_DISPATCH_SEAL,
    )


def _validate_dispatch_authority(
    authority: _MeteredDispatchAuthority,
    *,
    reservation: ResearchCostReservation,
    call: object,
) -> None:
    if authority.seal is not _METERED_DISPATCH_SEAL:
        raise MeteredCallAccountingError("Metered dispatch authority was not minted by the wrapper")
    if authority.marked or authority.consumed:
        raise MeteredCallAccountingError("Metered dispatch authority has already been used")
    if authority.call_identity != id(call):
        raise MeteredCallAccountingError("Metered dispatch closure changed after reservation")
    if authority.provider != canonical_provider_key(reservation.provider) or authority.model != reservation.model:
        raise MeteredCallAccountingError("Metered dispatch provider or model does not match its reservation")
    canonical = _canonical_request_envelope(
        provider=reservation.provider,
        model=reservation.model,
        request_envelope=authority.request_envelope,
    )
    current_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if current_sha256 != authority.request_sha256:
        raise MeteredCallAccountingError("Metered dispatch request changed after reservation")


def _consume_dispatch_authority(authority: _MeteredDispatchAuthority, call: object) -> None:
    if not authority.marked or authority.consumed or authority.call_identity != id(call):
        raise MeteredCallAccountingError("Metered dispatch lacks exact marked closure authority")
    canonical = _canonical_request_envelope(
        provider=authority.provider,
        model=authority.model,
        request_envelope=authority.request_envelope,
    )
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != authority.request_sha256:
        raise MeteredCallAccountingError("Metered dispatch request changed after its durable mark")
    authority.consumed = True


def _required_call_ceiling(value: float | None) -> float:
    """Reject opaque paid calls that rely on a process-wide default hold."""
    if value is None:
        raise MeteredCallAccountingError("Metered call requires an explicit provider-enforced maximum cost ceiling")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("max_cost_per_job must be a positive finite number")
    ceiling = float(value)
    if not math.isfinite(ceiling) or ceiling <= 0:
        raise ValueError("max_cost_per_job must be a positive finite number")
    return ceiling


def _require_token_model_contract(provider: str, model: str) -> tuple[str, str]:
    """Bind a token-priced call to one known provider-owned model contract."""
    identity = get_resolved_model_contract_identity(model)
    if identity is None:
        raise MeteredCallAccountingError(f"Metered call model {model!r} has no trusted pricing identity")
    model_provider, canonical_model = identity
    if not provider_matches_model_contract(provider, model_provider):
        raise MeteredCallAccountingError(
            f"Metered provider {provider!r} cannot execute model {model!r}; "
            f"the pricing contract belongs to {model_provider!r}"
        )
    return model_provider, canonical_model


def _optional_declared_attribute(value: object, name: str) -> object | None:
    try:
        inspect.getattr_static(value, name)
    except AttributeError:
        return None
    try:
        return getattr(value, name, None)
    except Exception:
        return None


def _receipt_settlement_fields(
    reservation: ResearchCostReservation,
    identifiers: _ProviderReceiptIdentifiers,
) -> tuple[str, dict[str, str]]:
    return provider_receipt_settlement_fields(
        client_correlation_id=reservation.job_id,
        identifiers=identifiers,
    )


def _usage_tokens(usage: object, primary: str, fallback: str) -> int:
    value = _optional_declared_attribute(usage, primary)
    if value is None:
        value = _optional_declared_attribute(usage, fallback)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Provider usage field {primary} must be a non-negative integer")
    return value


def _response_cost(response: object, provider: str, model: str) -> tuple[float | None, int]:
    requested_identity = _require_token_model_contract(provider, model)
    observed_model = _optional_declared_attribute(response, "model")
    if not isinstance(observed_model, str) or not observed_model.strip():
        # Usage without an observed model cannot safely be priced. Returning
        # no actual cost consumes the full reservation conservatively.
        return None, 0
    observed_identity = get_resolved_model_contract_identity(observed_model)
    if observed_identity != requested_identity:
        raise ProviderModelIdentityError(
            f"Provider returned model {observed_model!r}, which does not match reserved model {model!r}"
        )
    usage = _optional_declared_attribute(response, "usage")
    if usage is None:
        return None, 0
    input_tokens = _usage_tokens(usage, "input_tokens", "prompt_tokens")
    output_tokens = _usage_tokens(usage, "output_tokens", "completion_tokens")
    if input_tokens <= 0 and output_tokens <= 0:
        return None, 0
    actual_cost = CostEstimator.calculate_actual_cost(model, input_tokens, output_tokens)
    if not math.isfinite(actual_cost) or actual_cost < 0:
        raise ValueError("Calculated provider usage cost must be finite and non-negative")
    return actual_cost, output_tokens


def _mark_provider_dispatch(
    reservation: ResearchCostReservation,
    authority: _MeteredDispatchAuthority,
    call: object,
) -> None:
    require_unproxied_paid_transport()
    _validate_dispatch_authority(authority, reservation=reservation, call=call)
    ResearchReservationStore().mark_provider_work_may_have_run(
        reservation.reservation_id,
        provider=canonical_provider_key(reservation.provider),
        model=reservation.model,
        job_id=reservation.job_id,
        reserved_cost=reservation.estimated_cost,
        dispatch_binding_id=reservation.dispatch_binding_id,
        request_envelope_sha256=authority.request_sha256,
    )
    object.__setattr__(reservation, "request_envelope_sha256", authority.request_sha256)
    authority.marked = True


def _refund_before_dispatch(reservation: ResearchCostReservation) -> None:
    refund_research_cost(reservation, provider_work_did_not_run=True)


def _settle_conservative(
    reservation: ResearchCostReservation,
    *,
    source: str,
    reason: str,
    on_settled: Callable[[float], None] | None,
    identifiers: _ProviderReceiptIdentifiers | None = None,
) -> None:
    request_id, metadata = _receipt_settlement_fields(
        reservation,
        identifiers or _ProviderReceiptIdentifiers(),
    )
    metadata["metered_call_settlement_reason"] = reason
    settle_research_cost(
        reservation,
        actual_cost=None,
        request_id=request_id,
        source=f"{source}.conservative",
        actual_cost_reported=False,
        settlement_metadata=metadata,
    )
    if on_settled is not None:
        on_settled(reservation.estimated_cost)


def _settle_response(
    reservation: ResearchCostReservation,
    *,
    actual_cost: float | None,
    output_tokens: int,
    source: str,
    on_settled: Callable[[float], None] | None,
    identifiers: _ProviderReceiptIdentifiers | None = None,
) -> None:
    request_id, metadata = _receipt_settlement_fields(
        reservation,
        identifiers or _ProviderReceiptIdentifiers(),
    )
    settle_research_cost(
        reservation,
        actual_cost=actual_cost,
        tokens=output_tokens,
        request_id=request_id,
        source=source,
        settlement_metadata=metadata,
    )
    if on_settled is not None:
        on_settled(actual_cost if actual_cost is not None else reservation.estimated_cost)


def _accounting_error(message: str, cause: BaseException) -> MeteredCallAccountingError:
    error = MeteredCallAccountingError(message)
    error.__cause__ = cause
    return error


def _settle_sync_failure(
    reservation: ResearchCostReservation,
    *,
    source: str,
    reason: str,
    on_settled: Callable[[float], None] | None,
    operation_error: BaseException | None = None,
    identifiers: _ProviderReceiptIdentifiers | None = None,
) -> None:
    receipt_identifiers = identifiers or _ProviderReceiptIdentifiers()
    if operation_error is not None:
        receipt_identifiers = _merge_receipt_identifiers(
            receipt_identifiers,
            _provider_receipt_identifiers(operation_error),
        )
    try:
        _settle_conservative(
            reservation,
            source=source,
            reason=reason,
            on_settled=on_settled,
            identifiers=receipt_identifiers,
        )
    except BaseException as accounting_error:
        raise _accounting_error("Post-dispatch metered call cost settlement failed", accounting_error)


def execute_reserved_sync_call(
    *,
    operation_prefix: str,
    provider: str,
    model: str,
    source: str,
    call: Callable[[], T],
    request_envelope: Mapping[str, Any] | None = None,
    max_cost_per_job: float | None = None,
    on_settled: Callable[[float], None] | None = None,
) -> T:
    """Run one metered call under a cross-process ceiling and settle its usage."""
    _require_token_model_contract(provider, model)
    authority = _bind_dispatch_authority(
        provider=provider,
        model=model,
        request_envelope=request_envelope,
        call=call,
    )
    ceiling = _required_call_ceiling(max_cost_per_job)
    job_id = f"{operation_prefix}-{uuid.uuid4().hex}"
    try:
        reservation = reserve_configured_cost_ceiling(
            job_id=job_id,
            provider=provider,
            model=model,
            max_cost_per_job=ceiling,
        )
    except ValueError:
        raise
    except Exception as exc:
        raise MeteredCallAccountingError("Metered call cost reservation failed") from exc

    try:
        _mark_provider_dispatch(reservation, authority, call)
    except BaseException as mark_error:
        try:
            _refund_before_dispatch(reservation)
        except BaseException as refund_error:
            raise _accounting_error("Metered call dispatch mark and refund failed", refund_error)
        raise _accounting_error("Metered call dispatch mark failed", mark_error)

    try:
        _consume_dispatch_authority(authority, call)
        response = call()
    except BaseException as operation_error:
        _settle_sync_failure(
            reservation,
            source=source,
            reason="provider_call_failed",
            on_settled=on_settled,
            operation_error=operation_error,
        )
        raise

    identifiers = _provider_receipt_identifiers(response)
    try:
        actual_cost, output_tokens = _response_cost(response, provider, model)
    except BaseException as usage_error:
        _settle_sync_failure(
            reservation,
            source=source,
            reason=(
                "provider_model_identity_mismatch"
                if isinstance(usage_error, ProviderModelIdentityError)
                else "malformed_or_unpriceable_usage"
            ),
            on_settled=on_settled,
            identifiers=identifiers,
        )
        raise

    try:
        _settle_response(
            reservation,
            actual_cost=actual_cost,
            output_tokens=output_tokens,
            source=source,
            on_settled=on_settled,
            identifiers=identifiers,
        )
    except BaseException as exc:
        raise _accounting_error("Metered call cost settlement failed", exc)
    return response


async def _finish_thread_task(task: asyncio.Task[T], cancellation: asyncio.CancelledError) -> T:
    repeated_cancellations = 0
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            repeated_cancellations += 1
    if repeated_cancellations:
        cancellation.__dict__["metered_call_repeated_cancellations"] = repeated_cancellations
    return task.result()


def _attach_accounting_failure(
    cancellation: asyncio.CancelledError,
    *,
    stage: str,
    error: BaseException,
) -> None:
    accounting_error = _accounting_error(f"Metered call {stage} failed during cancellation", error)
    cancellation.__dict__["metered_call_accounting_error"] = accounting_error
    cancellation.__dict__["metered_call_accounting_stage"] = stage
    cancellation.add_note(f"Metered call {stage} failed while cancellation was pending.")


async def _refund_after_cancellation(
    reservation: ResearchCostReservation,
    cancellation: asyncio.CancelledError,
) -> bool:
    task = asyncio.create_task(
        asyncio.to_thread(_refund_before_dispatch, reservation),
        name=f"metered-call-refund-{reservation.job_id}",
    )
    try:
        await _finish_thread_task(task, cancellation)
    except BaseException as error:
        _attach_accounting_failure(cancellation, stage="predispatch refund", error=error)
        return False
    return True


async def _reserve_async(
    *,
    job_id: str,
    provider: str,
    model: str,
    max_cost_per_job: float | None,
) -> ResearchCostReservation:
    task = asyncio.create_task(
        asyncio.to_thread(
            reserve_configured_cost_ceiling,
            job_id=job_id,
            provider=provider,
            model=model,
            max_cost_per_job=max_cost_per_job,
        ),
        name=f"metered-call-reserve-{job_id}",
    )
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            reservation = await _finish_thread_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage="reservation", error=error)
        else:
            cleaned = await _refund_after_cancellation(
                reservation,
                cancellation,
            )
            cancellation.__dict__["metered_call_predispatch_reservation_cleaned"] = cleaned
        raise


async def _mark_dispatch_async(
    reservation: ResearchCostReservation,
    authority: _MeteredDispatchAuthority,
    call: object,
) -> None:
    task = asyncio.create_task(
        asyncio.to_thread(_mark_provider_dispatch, reservation, authority, call),
        name=f"metered-call-dispatch-mark-{reservation.job_id}",
    )
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_thread_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage="dispatch mark", error=error)
        cleaned = await _refund_after_cancellation(
            reservation,
            cancellation,
        )
        cancellation.__dict__["metered_call_predispatch_reservation_cleaned"] = cleaned
        raise


async def _refund_async(reservation: ResearchCostReservation) -> None:
    task = asyncio.create_task(
        asyncio.to_thread(_refund_before_dispatch, reservation),
        name=f"metered-call-refund-{reservation.job_id}",
    )
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_thread_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage="predispatch refund", error=error)
        raise


async def _settle_after_async_error(
    reservation: ResearchCostReservation,
    *,
    source: str,
    reason: str,
    on_settled: Callable[[float], None] | None,
    operation_error: BaseException,
    identifiers: _ProviderReceiptIdentifiers | None = None,
) -> NoReturn:
    receipt_identifiers = identifiers or _ProviderReceiptIdentifiers()
    receipt_identifiers = _merge_receipt_identifiers(
        receipt_identifiers,
        _provider_receipt_identifiers(operation_error),
    )
    task = asyncio.create_task(
        asyncio.to_thread(
            _settle_conservative,
            reservation,
            source=source,
            reason=reason,
            on_settled=on_settled,
            identifiers=receipt_identifiers,
        ),
        name=f"metered-call-conservative-settle-{reservation.job_id}",
    )
    if isinstance(operation_error, asyncio.CancelledError):
        try:
            await _finish_thread_task(task, operation_error)
        except BaseException as error:
            _attach_accounting_failure(operation_error, stage="conservative settlement", error=error)
        raise operation_error
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_thread_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage="conservative settlement", error=error)
        cancellation.__dict__["metered_call_interrupted_error_type"] = type(operation_error).__name__
        cancellation.add_note("Cancellation replaced a metered call error after conservative settlement started.")
        raise
    except BaseException as error:
        raise _accounting_error("Post-dispatch metered call cost settlement failed", error)
    raise operation_error


async def _settle_response_async(
    reservation: ResearchCostReservation,
    *,
    actual_cost: float | None,
    output_tokens: int,
    source: str,
    on_settled: Callable[[float], None] | None,
    identifiers: _ProviderReceiptIdentifiers | None = None,
) -> None:
    task = asyncio.create_task(
        asyncio.to_thread(
            _settle_response,
            reservation,
            actual_cost=actual_cost,
            output_tokens=output_tokens,
            source=source,
            on_settled=on_settled,
            identifiers=identifiers,
        ),
        name=f"metered-call-settle-{reservation.job_id}",
    )
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _finish_thread_task(task, cancellation)
        except BaseException as error:
            _attach_accounting_failure(cancellation, stage="settlement", error=error)
        raise
    except BaseException as error:
        raise _accounting_error("Metered call cost settlement failed", error)


async def execute_reserved_async_call(
    *,
    operation_prefix: str,
    provider: str,
    model: str,
    source: str,
    call: Callable[[], Awaitable[T]],
    request_envelope: Mapping[str, Any] | None = None,
    max_cost_per_job: float | None = None,
    on_settled: Callable[[float], None] | None = None,
) -> T:
    """Run one async metered call under a durable ceiling and settle usage."""
    _require_token_model_contract(provider, model)
    authority = _bind_dispatch_authority(
        provider=provider,
        model=model,
        request_envelope=request_envelope,
        call=call,
    )
    ceiling = _required_call_ceiling(max_cost_per_job)
    job_id = f"{operation_prefix}-{uuid.uuid4().hex}"
    try:
        reservation = await _reserve_async(
            job_id=job_id,
            provider=provider,
            model=model,
            max_cost_per_job=ceiling,
        )
    except asyncio.CancelledError:
        raise
    except ValueError:
        raise
    except Exception as exc:
        raise MeteredCallAccountingError("Metered call cost reservation failed") from exc

    try:
        await _mark_dispatch_async(reservation, authority, call)
    except asyncio.CancelledError:
        raise
    except BaseException as mark_error:
        try:
            await _refund_async(reservation)
        except asyncio.CancelledError:
            raise
        except BaseException as refund_error:
            raise _accounting_error("Metered call dispatch mark and refund failed", refund_error)
        raise _accounting_error("Metered call dispatch mark failed", mark_error)

    try:
        _consume_dispatch_authority(authority, call)
        response = await call()
    except BaseException as operation_error:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason="provider_call_cancelled"
            if isinstance(operation_error, asyncio.CancelledError)
            else "provider_call_failed",
            on_settled=on_settled,
            operation_error=operation_error,
        )

    identifiers = _provider_receipt_identifiers(response)
    try:
        actual_cost, output_tokens = _response_cost(response, provider, model)
    except BaseException as usage_error:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason=(
                "provider_model_identity_mismatch"
                if isinstance(usage_error, ProviderModelIdentityError)
                else "malformed_or_unpriceable_usage"
            ),
            on_settled=on_settled,
            operation_error=usage_error,
            identifiers=identifiers,
        )

    await _settle_response_async(
        reservation,
        actual_cost=actual_cost,
        output_tokens=output_tokens,
        source=source,
        on_settled=on_settled,
        identifiers=identifiers,
    )
    return response


async def _reserve_and_mark_async(
    *,
    job_id: str,
    provider: str,
    model: str,
    max_cost_per_job: float | None,
    authority: _MeteredDispatchAuthority,
    call: object,
) -> ResearchCostReservation:
    try:
        reservation = await _reserve_async(
            job_id=job_id,
            provider=provider,
            model=model,
            max_cost_per_job=max_cost_per_job,
        )
    except asyncio.CancelledError:
        raise
    except ValueError:
        raise
    except Exception as exc:
        raise MeteredCallAccountingError("Metered call cost reservation failed") from exc
    try:
        await _mark_dispatch_async(reservation, authority, call)
    except asyncio.CancelledError:
        raise
    except BaseException as mark_error:
        try:
            await _refund_async(reservation)
        except asyncio.CancelledError:
            raise
        except BaseException as refund_error:
            raise _accounting_error("Metered call dispatch mark and refund failed", refund_error)
        raise _accounting_error("Metered call dispatch mark failed", mark_error)
    return reservation


async def _settle_stream_usage_async(
    reservation: ResearchCostReservation,
    *,
    provider: str,
    model: str,
    source: str,
    final_usage: object | None,
    observed_model: object | None,
    on_settled: Callable[[float], None] | None,
    identifiers: _ProviderReceiptIdentifiers,
) -> None:
    identifiers = _merge_receipt_identifiers(
        identifiers,
        _provider_receipt_identifiers(final_usage) if final_usage is not None else _ProviderReceiptIdentifiers(),
    )
    if final_usage is None:
        await asyncio.to_thread(
            _settle_conservative,
            reservation,
            source=source,
            reason="stream_missing_usage",
            on_settled=on_settled,
            identifiers=identifiers,
        )
        return
    try:
        actual_cost, output_tokens = _response_cost(
            SimpleNamespace(usage=final_usage, model=observed_model),
            provider,
            model,
        )
    except BaseException as usage_error:
        await asyncio.to_thread(
            _settle_conservative,
            reservation,
            source=source,
            reason=(
                "provider_model_identity_mismatch"
                if isinstance(usage_error, ProviderModelIdentityError)
                else "malformed_or_unpriceable_usage"
            ),
            on_settled=on_settled,
            identifiers=identifiers,
        )
        return
    if actual_cost is None and output_tokens <= 0:
        await asyncio.to_thread(
            _settle_conservative,
            reservation,
            source=source,
            reason="stream_missing_usage",
            on_settled=on_settled,
            identifiers=identifiers,
        )
        return
    await _settle_response_async(
        reservation,
        actual_cost=actual_cost,
        output_tokens=output_tokens,
        source=source,
        on_settled=on_settled,
        identifiers=identifiers,
    )


async def execute_reserved_async_stream(
    *,
    operation_prefix: str,
    provider: str,
    model: str,
    source: str,
    events: Callable[[], AsyncIterator[tuple[T, object | None]]],
    request_envelope: Mapping[str, Any] | None = None,
    max_cost_per_job: float | None = None,
    on_settled: Callable[[float], None] | None = None,
) -> AsyncIterator[T]:
    """Stream one metered call under durable admission and settle final usage.

    ``events`` yields ``(item, usage)`` pairs. The last non-``None`` usage wins
    for settlement. If the stream ends without usable usage, the held ceiling is
    consumed conservatively after dispatch was marked.
    """
    _require_token_model_contract(provider, model)
    authority = _bind_dispatch_authority(
        provider=provider,
        model=model,
        request_envelope=request_envelope,
        call=events,
    )
    ceiling = _required_call_ceiling(max_cost_per_job)
    reservation = await _reserve_and_mark_async(
        job_id=f"{operation_prefix}-{uuid.uuid4().hex}",
        provider=provider,
        model=model,
        max_cost_per_job=ceiling,
        authority=authority,
        call=events,
    )

    final_usage: object | None = None
    observed_model: object | None = None
    identifiers = _ProviderReceiptIdentifiers()
    try:
        _consume_dispatch_authority(authority, events)
        async for item, usage in events():
            identifiers = _merge_receipt_identifiers(identifiers, _provider_receipt_identifiers(item))
            item_model = _optional_declared_attribute(item, "model")
            if item_model is not None:
                if observed_model is not None:
                    current_identity = get_resolved_model_contract_identity(str(observed_model))
                    item_identity = get_resolved_model_contract_identity(str(item_model))
                    if current_identity != item_identity:
                        raise ProviderModelIdentityError("Provider stream changed model identity between chunks")
                observed_model = item_model
            if usage is not None:
                final_usage = usage
            yield item
    except BaseException as operation_error:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason="provider_call_cancelled"
            if isinstance(operation_error, asyncio.CancelledError)
            else "provider_call_failed",
            on_settled=on_settled,
            operation_error=operation_error,
            identifiers=identifiers,
        )

    await _settle_stream_usage_async(
        reservation,
        provider=provider,
        model=model,
        source=source,
        final_usage=final_usage,
        observed_model=observed_model,
        on_settled=on_settled,
        identifiers=identifiers,
    )


async def execute_reserved_fixed_cost_async_call(
    *,
    operation_prefix: str,
    provider: str,
    model: str,
    source: str,
    max_cost_per_job: float,
    call: Callable[[], Awaitable[T]],
    cost_from_result: Callable[[T], float],
    request_envelope: Mapping[str, Any] | None = None,
    on_settled: Callable[[float], None] | None = None,
) -> T:
    """Run one non-token-priced work unit under durable reserve/mark/settle.

    Skill tools and similar side effects have explicit maximum envelopes.
    ``cost_from_result`` returns the amount to settle after success. Exceptions
    or usage above the authorized envelope consume the full hold conservatively.
    """
    authority = _bind_dispatch_authority(
        provider=provider,
        model=model,
        request_envelope=request_envelope,
        call=call,
    )
    if isinstance(max_cost_per_job, bool) or not isinstance(max_cost_per_job, (int, float)):
        raise ValueError("max_cost_per_job must be a positive finite number")
    ceiling = float(max_cost_per_job)
    if not math.isfinite(ceiling) or ceiling <= 0:
        raise ValueError("max_cost_per_job must be a positive finite number")

    reservation = await _reserve_and_mark_async(
        job_id=f"{operation_prefix}-{uuid.uuid4().hex}",
        provider=provider,
        model=model,
        max_cost_per_job=ceiling,
        authority=authority,
        call=call,
    )

    try:
        _consume_dispatch_authority(authority, call)
        result = await call()
    except BaseException as operation_error:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason="provider_call_cancelled"
            if isinstance(operation_error, asyncio.CancelledError)
            else "provider_call_failed",
            on_settled=on_settled,
            operation_error=operation_error,
        )

    identifiers = _provider_receipt_identifiers(result)
    if isinstance(result, Mapping) and "error" in result:
        raw_cost = reservation.estimated_cost
    else:
        try:
            raw_cost = float(cost_from_result(result))
        except BaseException as cost_error:
            await _settle_after_async_error(
                reservation,
                source=source,
                reason="malformed_or_unpriceable_usage",
                on_settled=on_settled,
                operation_error=cost_error,
                identifiers=identifiers,
            )

    if not math.isfinite(raw_cost) or raw_cost < 0:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason="malformed_or_unpriceable_usage",
            on_settled=on_settled,
            operation_error=ValueError("cost_from_result must return a finite non-negative number"),
            identifiers=identifiers,
        )

    if raw_cost > reservation.estimated_cost:
        await _settle_after_async_error(
            reservation,
            source=source,
            reason="reported_cost_exceeds_reserved_ceiling",
            on_settled=on_settled,
            operation_error=ValueError("reported cost exceeds reserved ceiling"),
            identifiers=identifiers,
        )

    settled = raw_cost
    await _settle_response_async(
        reservation,
        actual_cost=settled,
        output_tokens=0,
        source=source,
        on_settled=on_settled,
        identifiers=identifiers,
    )
    return result


__all__ = [
    "MeteredCallAccountingError",
    "ProviderModelIdentityError",
    "execute_reserved_async_call",
    "execute_reserved_async_stream",
    "execute_reserved_fixed_cost_async_call",
    "execute_reserved_sync_call",
]
