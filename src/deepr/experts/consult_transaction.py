"""Shared durable execution wrapper for one-shot expert consults."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, TypeVar

from deepr.experts.consult_lifecycle import (
    ConsultLifecycle,
    ConsultLifecycleElapsedLimitError,
    ConsultLifecycleJournalError,
    ConsultLifecycleLockTimeoutError,
    ConsultLifecycleStorageError,
    LifecyclePhase,
    LifecycleState,
)
from deepr.experts.consult_traces import (
    ConsultTraceLockTimeoutError,
    ConsultTraceStorageError,
    new_consult_trace_id,
    record_consult_trace,
)
from deepr.experts.consult_transaction_errors import (
    ConsultElapsedLimitError,
    ConsultStorageError,
    ConsultStorageIOError,
    ConsultStorageLockTimeoutError,
)

DEFAULT_CONSULT_MAX_ELAPSED_SECONDS = 600.0
MAX_CONSULT_MAX_ELAPSED_SECONDS = 21_600.0
DEFAULT_CONSULT_HEARTBEAT_SECONDS = 30.0
_SUCCESSFUL_SYNTHESIS_STATES = frozenset({"completed", "skipped_no_valid_perspectives"})
logger = logging.getLogger(__name__)
_T = TypeVar("_T")
_RunConsultFn = Callable[..., Awaitable[dict[str, Any]]]
_BackendFactory = Callable[[], Any | Awaitable[Any]]


class _ConsultDeadlineReached(Exception):
    """Internal marker that distinguishes the host ceiling from provider timeouts."""


@dataclass(frozen=True)
class _ConsultRequest:
    question: str
    requested_experts: list[str]
    max_experts: int
    budget: float
    backend_mode: str
    trace_id: str
    trace_path: Path | None
    max_elapsed_seconds: float


@dataclass
class _TransactionState:
    lifecycle: ConsultLifecycle
    bounds: Mapping[str, int | float | str]
    final_capacity: Mapping[str, object]
    phase: LifecyclePhase = LifecyclePhase.PREFLIGHT
    final_trace_recorded: bool = False
    lifecycle_terminal_recorded: bool = False
    observed_cost_usd: float = 0.0
    completed_work_items: set[str] = field(default_factory=set)
    provider_work_started: bool = False
    progress_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def progress(self) -> dict[str, int | float]:
        return {
            "cost_usd_observed": self.observed_cost_usd,
            "dispatches_completed": min(
                len(self.completed_work_items),
                int(self.bounds["max_dispatches"]),
            ),
        }

    async def record_progress(self, name: str, status: str) -> None:
        async with self.progress_lock:
            if name == "__synthesis__":
                self.phase = LifecyclePhase.SYNTHESIS
            if status in {"done", "failed"}:
                self.completed_work_items.add(name)
            await _run_sync_durable(partial(self.lifecycle.heartbeat, phase=self.phase, progress=self.progress()))

    def settle_result(self, payload: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        self.observed_cost_usd = float(payload.get("cost_usd", 0.0) or 0.0)
        perspectives = result.get("perspectives", []) or []
        for perspective in perspectives:
            if not isinstance(perspective, dict):
                continue
            expert_name = str(perspective.get("expert_name", ""))
            if expert_name:
                self.completed_work_items.add(expert_name)
        if perspectives:
            self.completed_work_items.add("__synthesis__")

    def settle_cancelled_cost(self, error: BaseException) -> bool:
        """Import a finite cost that the canonical ledger already settled."""
        settlement = error.__dict__.get("council_synthesis_settlement")
        if not isinstance(settlement, Mapping) or settlement.get("settled") is not True:
            return False
        value = settlement.get("cost")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        cost = float(value)
        if not math.isfinite(cost) or cost < 0:
            return False
        self.observed_cost_usd = max(self.observed_cost_usd, cost)
        return True

    def cost_bound_exceeded(self) -> bool:
        """Return whether actual settled spend exceeded the requested ceiling."""
        return self.observed_cost_usd > float(self.bounds["max_cost_usd"])


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def one_shot_consult_bounds(
    *, requested_experts: list[str], max_experts: int, budget: float = 0.0
) -> dict[str, int | float | str]:
    """Return the one-shot logical-work and spend bounds Deepr can observe."""
    from deepr.experts.consult import MAX_CONSULT_EXPERTS

    if isinstance(max_experts, bool) or not isinstance(max_experts, int) or not 1 <= max_experts <= MAX_CONSULT_EXPERTS:
        raise ValueError(f"max_experts must be between 1 and {MAX_CONSULT_EXPERTS}")
    if len(requested_experts) > MAX_CONSULT_EXPERTS:
        raise ValueError(f"Consult roster cannot exceed {MAX_CONSULT_EXPERTS} experts")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget < 0:
        raise ValueError("budget must be finite and non-negative")
    roster_size = len(requested_experts) if requested_experts else max_experts
    if roster_size < 1:
        raise ValueError("A consult requires at least one possible expert.")
    work_items = roster_size + 1
    return {
        "dispatch_scope": "council_work_item",
        "max_cost_usd": float(budget),
        "max_dispatches": work_items,
    }


def requested_consult_capacity(
    *,
    backend_mode: str,
    provider: str = "",
    model: str = "",
) -> dict[str, object]:
    """Build pre-dispatch capacity metadata without constructing a backend."""
    normalized_mode = backend_mode.strip().lower()
    if normalized_mode not in {"api", "local", "plan"}:
        raise ValueError("backend_mode must be api, local, or plan")
    return {
        "source": normalized_mode,
        "backend": normalized_mode,
        "provider": provider,
        "model": model,
        "admission": "unknown",
        "live_metered_fallback": False,
    }


def _final_trace_capacity(requested: Mapping[str, object]) -> dict[str, object]:
    return {
        "synthesis_backend": str(requested["backend"]),
        "provider": str(requested["provider"]),
        "model": str(requested["model"]),
        "live_metered_fallback": bool(requested["live_metered_fallback"]),
    }


def _resolved_capacity(backend_mode: str, backend: Any) -> dict[str, object]:
    return {
        "synthesis_backend": backend_mode,
        "provider": str(backend.provider),
        "model": str(backend.model or ""),
        "live_metered_fallback": False,
    }


def _resolved_lifecycle_capacity(requested: Mapping[str, object], backend: Any) -> dict[str, object]:
    return {
        **dict(requested),
        "provider": str(backend.provider),
        "model": str(backend.model or ""),
        "admission": "admitted",
    }


def _lineage(question: str, requested_experts: list[str], max_experts: int) -> dict[str, str]:
    roster = (
        {"selection": "explicit", "experts": requested_experts}
        if requested_experts
        else {"selection": "automatic", "max_experts": max_experts}
    )
    roster_json = json.dumps(roster, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return {
        "operation": "one_shot",
        "question_hash": _sha256(question),
        "roster_hash": _sha256(roster_json),
    }


async def _wait_for_durable_task(task: asyncio.Task[_T], cancellation: asyncio.CancelledError) -> _T:
    """Wait through repeated cancellation so a synchronous write never becomes hidden."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancellation.add_note("A repeated cancellation waited for the active durable consult operation.")
    return task.result()


def _attach_durable_completion_failure(cancellation: asyncio.CancelledError, error: BaseException) -> None:
    if isinstance(error, ConsultLifecycleElapsedLimitError | ConsultElapsedLimitError):
        code = "elapsed_limit_terminal"
        cancellation.__dict__["consult_lifecycle_terminal"] = "elapsed_limit"
    elif isinstance(error, ConsultLifecycleLockTimeoutError | ConsultTraceLockTimeoutError):
        code = "storage_lock_timeout"
    elif isinstance(error, ConsultLifecycleStorageError | ConsultTraceStorageError):
        code = "storage_io_error"
    elif isinstance(error, ConsultLifecycleJournalError):
        code = "lifecycle_journal_error"
    else:
        code = "durable_completion_error"
    cancellation.__dict__["consult_durable_completion_failure"] = code
    cancellation.add_note(f"Consult durable completion reported {code} while cancellation was pending.")


async def _run_sync_durable(function: Callable[[], _T]) -> _T:
    """Run synchronous durable work off-loop and never abandon it after cancellation."""
    task = asyncio.create_task(asyncio.to_thread(function))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await _wait_for_durable_task(task, cancellation)
        except BaseException as completion_error:
            _attach_durable_completion_failure(cancellation, completion_error)
        raise


def _transfer_settled_cancellation(source: BaseException, target: BaseException) -> bool:
    settlement = source.__dict__.get("council_synthesis_settlement")
    if not isinstance(settlement, Mapping) or settlement.get("settled") is not True:
        return False
    cost = settlement.get("cost")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        return False
    if not math.isfinite(float(cost)) or float(cost) < 0:
        return False
    target.__dict__["council_synthesis_settlement"] = dict(settlement)
    return True


async def _run_with_heartbeats(
    operation: Awaitable[_T],
    *,
    lifecycle: ConsultLifecycle,
    phase: Callable[[], LifecyclePhase],
    interval_seconds: float,
) -> _T:
    async def heartbeat_loop() -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            await _run_sync_durable(partial(lifecycle.heartbeat, phase=phase()))

    operation_task = asyncio.ensure_future(operation)
    heartbeat_task = asyncio.create_task(heartbeat_loop())
    pending_error: BaseException | None = None
    try:
        await asyncio.sleep(0)
        done, _pending = await asyncio.wait(
            {operation_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if heartbeat_task in done:
            await heartbeat_task
            raise RuntimeError("Consult heartbeat loop ended unexpectedly")
        return await operation_task
    except BaseException as error:
        pending_error = error
        raise
    finally:
        for task in (operation_task, heartbeat_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(operation_task, heartbeat_task, return_exceptions=True)
        if pending_error is not None and operation_task.cancelled():
            try:
                operation_task.result()
            except asyncio.CancelledError as operation_cancellation:
                _transfer_settled_cancellation(operation_cancellation, pending_error)


async def _invoke_with_heartbeats(
    function: Callable[[], Any | Awaitable[Any]],
    *,
    lifecycle: ConsultLifecycle,
    phase: Callable[[], LifecyclePhase],
    interval_seconds: float,
) -> Any:
    """Invoke a callable without letting synchronous setup block the event loop."""
    operation: Awaitable[Any]
    if inspect.iscoroutinefunction(function):
        operation = function()
    else:
        operation = asyncio.to_thread(function)
    result = await _run_with_heartbeats(
        operation,
        lifecycle=lifecycle,
        phase=phase,
        interval_seconds=interval_seconds,
    )
    if inspect.isawaitable(result):
        return await _run_with_heartbeats(
            result,
            lifecycle=lifecycle,
            phase=phase,
            interval_seconds=interval_seconds,
        )
    return result


def _record_failed_trace(
    *,
    trace_id: str,
    trace_path: Path | None,
    question: str,
    requested_experts: list[str],
    max_experts: int,
    budget: float,
    capacity: Mapping[str, object],
    stage: str,
    error: BaseException,
    lock_timeout_seconds: float,
) -> None:
    record_consult_trace(
        path=trace_path,
        question=question,
        requested_experts=requested_experts,
        max_experts=max_experts,
        budget=budget,
        capacity=dict(capacity),
        failure={"stage": stage, "error_type": type(error).__name__, "message": str(error)},
        trace_id=trace_id,
        lock_timeout_seconds=lock_timeout_seconds,
    )


def _record_failed_trace_without_masking(**kwargs: Any) -> None:
    """Keep lifecycle termination authoritative if final trace storage also fails."""
    try:
        _record_failed_trace(**kwargs)
    except Exception as exc:
        logger.warning(
            "Could not finalize failed consult trace %s (%s)",
            kwargs.get("trace_id", ""),
            type(exc).__name__,
        )


def _attach_trace_id(error: BaseException, trace_id: str) -> None:
    try:
        error.__dict__["consult_trace_id"] = trace_id
    except Exception as exc:
        logger.debug("Could not attach consult trace id to %s: %s", type(error).__name__, exc)


def _attach_settlement_failure(
    error: BaseException,
    settlement_error: ConsultLifecycleLockTimeoutError | ConsultLifecycleJournalError | ConsultLifecycleStorageError,
    *,
    trace_id: str,
) -> None:
    code = _lifecycle_storage_failure_code(settlement_error)
    _attach_trace_id(error, trace_id)
    try:
        error.__dict__["consult_settlement_failure"] = code
    except Exception:
        logger.warning("Consult %s settlement failed (%s)", trace_id, code)
        return
    logger.warning("Consult %s settlement failed (%s)", trace_id, code)


def _lifecycle_storage_failure_code(
    error: ConsultLifecycleLockTimeoutError | ConsultLifecycleJournalError | ConsultLifecycleStorageError,
) -> str:
    if isinstance(error, ConsultLifecycleLockTimeoutError):
        return "lifecycle_lock_timeout"
    if isinstance(error, ConsultLifecycleStorageError):
        return "lifecycle_storage_io_error"
    return "lifecycle_journal_error"


def _validate_max_elapsed(max_elapsed_seconds: float) -> None:
    if isinstance(max_elapsed_seconds, bool) or not math.isfinite(max_elapsed_seconds):
        raise ValueError("max_elapsed_seconds must be finite, greater than zero, and no more than 21600")
    if max_elapsed_seconds <= 0 or max_elapsed_seconds > MAX_CONSULT_MAX_ELAPSED_SECONDS:
        raise ValueError("max_elapsed_seconds must be finite, greater than zero, and no more than 21600")


def _validate_budget(budget: float) -> None:
    if isinstance(budget, bool) or not isinstance(budget, (int, float)):
        raise ValueError("budget must be finite and non-negative")
    if not math.isfinite(budget) or budget < 0:
        raise ValueError("budget must be finite and non-negative")


def _validate_heartbeat_interval(heartbeat_interval_seconds: float) -> None:
    if not math.isfinite(heartbeat_interval_seconds) or heartbeat_interval_seconds <= 0:
        raise ValueError("heartbeat_interval_seconds must be finite and greater than zero")


def _start_transaction_state(
    request: _ConsultRequest,
    *,
    requested_capacity: Mapping[str, object],
    max_elapsed_seconds: float,
    lifecycle_path: Path | None,
) -> _TransactionState:
    bounds = one_shot_consult_bounds(
        requested_experts=request.requested_experts,
        max_experts=request.max_experts,
        budget=request.budget,
    )
    lifecycle = ConsultLifecycle.start(
        trace_id=request.trace_id,
        path=lifecycle_path,
        max_elapsed_seconds=max_elapsed_seconds,
        capacity=requested_capacity,
        bounds=bounds,
        lineage=_lineage(request.question, request.requested_experts, request.max_experts),
    )
    return _TransactionState(
        lifecycle=lifecycle,
        bounds=bounds,
        final_capacity=_final_trace_capacity(requested_capacity),
    )


async def _construct_backend(
    backend_factory: _BackendFactory,
    *,
    state: _TransactionState,
    requested_capacity: Mapping[str, object],
    backend_mode: str,
    heartbeat_interval_seconds: float,
    on_backend_ready: Callable[[Any], Any | Awaitable[Any]] | None,
) -> Any:
    backend = await _invoke_with_heartbeats(
        backend_factory,
        lifecycle=state.lifecycle,
        phase=lambda: state.phase,
        interval_seconds=heartbeat_interval_seconds,
    )
    state.final_capacity = _resolved_capacity(backend_mode, backend)
    await _run_sync_durable(
        partial(
            state.lifecycle.heartbeat,
            phase=LifecyclePhase.PREFLIGHT,
            capacity=_resolved_lifecycle_capacity(requested_capacity, backend),
        )
    )
    if on_backend_ready is not None:
        await _invoke_with_heartbeats(
            partial(on_backend_ready, backend),
            lifecycle=state.lifecycle,
            phase=lambda: state.phase,
            interval_seconds=heartbeat_interval_seconds,
        )
    return backend


def _selected_run_consult(run_consult_fn: _RunConsultFn | None) -> _RunConsultFn:
    if run_consult_fn is not None:
        return run_consult_fn
    from deepr.experts.consult import run_consult

    return run_consult


async def _run_generation(
    request: _ConsultRequest,
    *,
    backend: Any,
    state: _TransactionState,
    run_consult_fn: _RunConsultFn | None,
    heartbeat_interval_seconds: float,
) -> dict[str, Any]:
    state.phase = LifecyclePhase.PERSPECTIVES
    await _run_sync_durable(partial(state.lifecycle.heartbeat, phase=state.phase))
    selected_run_consult = _selected_run_consult(run_consult_fn)
    state.provider_work_started = True
    operation = selected_run_consult(
        request.question,
        request.requested_experts,
        request.max_experts,
        request.budget,
        synthesis_client=backend.client,
        synthesis_model=backend.model,
        synthesis_provider=backend.provider,
        allow_live_fallback=backend.allow_live_fallback,
        progress_callback=state.record_progress,
    )
    return await _run_with_heartbeats(
        operation,
        lifecycle=state.lifecycle,
        phase=lambda: state.phase,
        interval_seconds=heartbeat_interval_seconds,
    )


async def _run_inside_deadline(
    request: _ConsultRequest,
    *,
    state: _TransactionState,
    backend_factory: _BackendFactory,
    requested_capacity: Mapping[str, object],
    max_elapsed_seconds: float,
    heartbeat_interval_seconds: float,
    run_consult_fn: _RunConsultFn | None,
    on_started: Callable[[str], Any | Awaitable[Any]] | None,
    on_backend_ready: Callable[[Any], Any | Awaitable[Any]] | None,
) -> dict[str, Any]:
    remaining_seconds = min(max_elapsed_seconds, state.lifecycle.remaining_elapsed_seconds())
    if remaining_seconds <= 0:
        raise _ConsultDeadlineReached("consult elapsed before cancellable work began")
    deadline = asyncio.timeout(remaining_seconds)
    try:
        async with deadline:
            if on_started is not None:
                await _invoke_with_heartbeats(
                    partial(on_started, request.trace_id),
                    lifecycle=state.lifecycle,
                    phase=lambda: state.phase,
                    interval_seconds=heartbeat_interval_seconds,
                )
                await _run_sync_durable(partial(state.lifecycle.heartbeat, phase=LifecyclePhase.PREFLIGHT))
            backend = await _construct_backend(
                backend_factory,
                state=state,
                requested_capacity=requested_capacity,
                backend_mode=request.backend_mode,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                on_backend_ready=on_backend_ready,
            )
            return await _run_generation(
                request,
                backend=backend,
                state=state,
                run_consult_fn=run_consult_fn,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
            )
    except TimeoutError as exc:
        if deadline.expired():
            reached = _ConsultDeadlineReached("consult preflight or generation elapsed-time ceiling reached")
            source = exc.__cause__ if isinstance(exc.__cause__, BaseException) else exc
            _transfer_settled_cancellation(source, reached)
            raise reached from exc
        raise


def _finalize_result(
    request: _ConsultRequest,
    *,
    state: _TransactionState,
    result: dict[str, Any],
) -> dict[str, Any]:
    state.phase = LifecyclePhase.TRACE_FINALIZE
    from deepr.experts.consult import build_consult_payload, record_consult_payload_trace

    payload = build_consult_payload(request.question, result)
    payload["capacity"] = dict(state.final_capacity)
    state.settle_result(payload, result)
    cost_bound_exceeded = state.cost_bound_exceeded()
    if cost_bound_exceeded:
        payload["cost_bound_exceeded"] = True
        payload["cost_bound_usd"] = float(state.bounds["max_cost_usd"])
        payload["synthesis_status"] = "failed"
        payload["synthesis_error_type"] = "CostBoundExceeded"
    else:
        state.lifecycle.heartbeat(phase=state.phase, progress=state.progress())
    lock_timeout_seconds = state.lifecycle.remaining_elapsed_seconds()
    if lock_timeout_seconds <= 0:
        raise ConsultTraceLockTimeoutError(
            "Consult elapsed before trace finalization",
            path=request.trace_path,
            timeout_seconds=0.0,
        )
    record_consult_payload_trace(
        payload,
        question=request.question,
        requested_experts=request.requested_experts,
        max_experts=request.max_experts,
        budget=request.budget,
        result=result,
        capacity=dict(state.final_capacity),
        trace_id=request.trace_id,
        path=request.trace_path,
        lock_timeout_seconds=lock_timeout_seconds,
    )
    state.final_trace_recorded = True
    synthesis_status = str(payload.get("synthesis_status", "failed"))
    successful = synthesis_status in _SUCCESSFUL_SYNTHESIS_STATES and not cost_bound_exceeded
    terminal_state = LifecycleState.COMPLETED if successful else LifecycleState.FAILED
    if successful:
        reason_code = "consult_completed"
    elif cost_bound_exceeded:
        reason_code = "cost_bound_exceeded"
    else:
        reason_code = "synthesis_incomplete"
    state.lifecycle.finish(
        terminal_state,
        reason_code=reason_code,
        progress=state.progress(),
    )
    state.lifecycle_terminal_recorded = True
    return payload


async def _execute_started_transaction(
    request: _ConsultRequest,
    *,
    state: _TransactionState,
    backend_factory: _BackendFactory,
    requested_capacity: Mapping[str, object],
    max_elapsed_seconds: float,
    heartbeat_interval_seconds: float,
    run_consult_fn: _RunConsultFn | None,
    on_started: Callable[[str], Any | Awaitable[Any]] | None,
    on_backend_ready: Callable[[Any], Any | Awaitable[Any]] | None,
) -> dict[str, Any]:
    result = await _run_inside_deadline(
        request,
        state=state,
        backend_factory=backend_factory,
        requested_capacity=requested_capacity,
        max_elapsed_seconds=max_elapsed_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        run_consult_fn=run_consult_fn,
        on_started=on_started,
        on_backend_ready=on_backend_ready,
    )
    task = asyncio.create_task(asyncio.to_thread(_finalize_result, request, state=state, result=result))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            payload = await _wait_for_durable_task(task, cancellation)
        except BaseException as completion_error:
            _attach_durable_completion_failure(cancellation, completion_error)
            raise cancellation from None
        cancellation.add_note("Consult completion became durable before cancellation could take effect.")
        return payload


def _record_transaction_failure(
    request: _ConsultRequest,
    state: _TransactionState,
    *,
    stage: str,
    error: BaseException,
) -> None:
    if state.lifecycle_terminal_recorded:
        return
    _record_failed_trace_without_masking(
        trace_id=request.trace_id,
        trace_path=request.trace_path,
        question=request.question,
        requested_experts=request.requested_experts,
        max_experts=request.max_experts,
        budget=request.budget,
        capacity=state.final_capacity,
        stage=stage,
        error=error,
        lock_timeout_seconds=state.lifecycle.remaining_elapsed_seconds(),
    )


def _finish_exception(
    request: _ConsultRequest,
    state: _TransactionState,
    *,
    error: BaseException,
    stage: str,
    terminal_state: LifecycleState,
    reason_code: str,
    attach_trace_id: bool,
) -> None:
    if attach_trace_id:
        _attach_trace_id(error, request.trace_id)
    if state.final_trace_recorded:
        return
    try:
        state.lifecycle.finish(
            terminal_state,
            phase=state.phase,
            reason_code=reason_code,
            progress=state.progress(),
        )
    except ConsultLifecycleElapsedLimitError as exc:
        raise _settle_elapsed_limit(request, state) from exc
    except (ConsultLifecycleLockTimeoutError, ConsultLifecycleJournalError, ConsultLifecycleStorageError) as exc:
        _attach_settlement_failure(error, exc, trace_id=request.trace_id)
    _record_transaction_failure(request, state, stage=stage, error=error)


def _settle_elapsed_limit(request: _ConsultRequest, state: _TransactionState) -> ConsultElapsedLimitError:
    elapsed_error = ConsultElapsedLimitError(
        request.trace_id,
        request.max_elapsed_seconds,
        retryable=not state.provider_work_started,
    )
    _record_transaction_failure(request, state, stage="elapsed_limit", error=elapsed_error)
    try:
        state.lifecycle.stop_elapsed_limit(phase=state.phase, progress=state.progress())
    except (ConsultLifecycleLockTimeoutError, ConsultLifecycleJournalError, ConsultLifecycleStorageError) as exc:
        _attach_settlement_failure(elapsed_error, exc, trace_id=request.trace_id)
    return elapsed_error


def _settle_trace_lock_timeout(request: _ConsultRequest, state: _TransactionState) -> ConsultStorageLockTimeoutError:
    storage_error = ConsultStorageLockTimeoutError(request.trace_id, "consult trace", retryable=False)
    try:
        if state.lifecycle.remaining_elapsed_seconds() <= 0:
            state.lifecycle.stop_elapsed_limit(phase=state.phase, progress=state.progress())
            storage_error.consult_lifecycle_terminal = "elapsed_limit"
        else:
            state.lifecycle.finish(LifecycleState.FAILED, phase=state.phase, reason_code="storage_lock_timeout")
    except ConsultLifecycleElapsedLimitError:
        storage_error.consult_lifecycle_terminal = "elapsed_limit"
    except (ConsultLifecycleLockTimeoutError, ConsultLifecycleJournalError, ConsultLifecycleStorageError) as exc:
        _attach_settlement_failure(storage_error, exc, trace_id=request.trace_id)
    return storage_error


def _settle_trace_storage_error(
    request: _ConsultRequest,
    state: _TransactionState,
    error: ConsultTraceStorageError,
) -> ConsultStorageIOError:
    storage_error = ConsultStorageIOError(
        request.trace_id,
        "consult trace",
        retryable=False,
        partial_write_possible=error.partial_write_possible,
    )
    try:
        state.lifecycle.finish(
            LifecycleState.FAILED,
            phase=state.phase,
            reason_code="storage_io_error",
            progress=state.progress(),
        )
    except ConsultLifecycleElapsedLimitError:
        storage_error.consult_lifecycle_terminal = "elapsed_limit"
    except (ConsultLifecycleLockTimeoutError, ConsultLifecycleJournalError, ConsultLifecycleStorageError) as exc:
        _attach_settlement_failure(storage_error, exc, trace_id=request.trace_id)
    return storage_error


def _public_lifecycle_storage_error(
    trace_id: str,
    error: ConsultLifecycleLockTimeoutError | ConsultLifecycleJournalError | ConsultLifecycleStorageError,
    *,
    provider_work_started: bool,
) -> ConsultStorageError:
    if isinstance(error, ConsultLifecycleLockTimeoutError):
        return ConsultStorageLockTimeoutError(
            trace_id,
            "lifecycle",
            retryable=not provider_work_started,
            settlement_failure=_lifecycle_storage_failure_code(error),
        )
    partial_write_possible = isinstance(error, ConsultLifecycleStorageError) and error.partial_write_possible
    return ConsultStorageIOError(
        trace_id,
        "lifecycle",
        retryable=not provider_work_started
        and not partial_write_possible
        and not isinstance(error, ConsultLifecycleJournalError),
        partial_write_possible=partial_write_possible,
        settlement_failure=_lifecycle_storage_failure_code(error),
    )


async def _start_transaction_state_durable(
    request: _ConsultRequest,
    *,
    requested_capacity: Mapping[str, object],
    max_elapsed_seconds: float,
    lifecycle_path: Path | None,
) -> _TransactionState:
    task = asyncio.create_task(
        asyncio.to_thread(
            _start_transaction_state,
            request,
            requested_capacity=requested_capacity,
            max_elapsed_seconds=max_elapsed_seconds,
            lifecycle_path=lifecycle_path,
        )
    )
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            state = await _wait_for_durable_task(task, cancellation)
        except BaseException as completion_error:
            _attach_durable_completion_failure(cancellation, completion_error)
            raise cancellation from None
        _attach_trace_id(cancellation, request.trace_id)
        try:
            await _run_sync_durable(
                partial(
                    _finish_exception,
                    request,
                    state,
                    error=cancellation,
                    stage="cancelled",
                    terminal_state=LifecycleState.CANCELLED,
                    reason_code="cancelled",
                    attach_trace_id=False,
                )
            )
        except BaseException as completion_error:
            _attach_durable_completion_failure(cancellation, completion_error)
            raise cancellation from None
        raise


async def execute_consult_transaction(
    *,
    question: str,
    requested_experts: list[str],
    max_experts: int,
    budget: float,
    backend_mode: str,
    backend_factory: Callable[[], Any | Awaitable[Any]],
    requested_capacity: Mapping[str, object],
    max_elapsed_seconds: float = DEFAULT_CONSULT_MAX_ELAPSED_SECONDS,
    heartbeat_interval_seconds: float = DEFAULT_CONSULT_HEARTBEAT_SECONDS,
    trace_id: str | None = None,
    lifecycle_path: Path | None = None,
    trace_path: Path | None = None,
    run_consult_fn: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    on_started: Callable[[str], Any | Awaitable[Any]] | None = None,
    on_backend_ready: Callable[[Any], Any | Awaitable[Any]] | None = None,
) -> dict[str, Any]:
    """Execute one consult with pre-dispatch state, heartbeats, and one terminal event."""
    _validate_max_elapsed(max_elapsed_seconds)
    _validate_budget(budget)
    _validate_heartbeat_interval(heartbeat_interval_seconds)
    shared_trace_id = trace_id or new_consult_trace_id()
    request = _ConsultRequest(
        question=question,
        requested_experts=requested_experts,
        max_experts=max_experts,
        budget=budget,
        backend_mode=backend_mode,
        trace_id=shared_trace_id,
        trace_path=trace_path,
        max_elapsed_seconds=max_elapsed_seconds,
    )
    try:
        state = await _start_transaction_state_durable(
            request,
            requested_capacity=requested_capacity,
            max_elapsed_seconds=max_elapsed_seconds,
            lifecycle_path=lifecycle_path,
        )
    except (ConsultLifecycleLockTimeoutError, ConsultLifecycleJournalError, ConsultLifecycleStorageError) as exc:
        raise _public_lifecycle_storage_error(
            shared_trace_id,
            exc,
            provider_work_started=False,
        ) from None
    try:
        return await _execute_started_transaction(
            request,
            state=state,
            backend_factory=backend_factory,
            requested_capacity=requested_capacity,
            max_elapsed_seconds=max_elapsed_seconds,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            run_consult_fn=run_consult_fn,
            on_started=on_started,
            on_backend_ready=on_backend_ready,
        )
    except ConsultLifecycleElapsedLimitError as exc:
        state.settle_cancelled_cost(exc)
        raise await _run_sync_durable(partial(_settle_elapsed_limit, request, state)) from exc
    except ConsultTraceLockTimeoutError:
        raise await _run_sync_durable(partial(_settle_trace_lock_timeout, request, state)) from None
    except ConsultTraceStorageError as exc:
        raise await _run_sync_durable(partial(_settle_trace_storage_error, request, state, exc)) from None
    except (ConsultLifecycleLockTimeoutError, ConsultLifecycleJournalError, ConsultLifecycleStorageError) as exc:
        raise _public_lifecycle_storage_error(
            shared_trace_id,
            exc,
            provider_work_started=state.provider_work_started,
        ) from None
    except _ConsultDeadlineReached as exc:
        state.settle_cancelled_cost(exc)
        raise await _run_sync_durable(partial(_settle_elapsed_limit, request, state)) from exc
    except asyncio.CancelledError as exc:
        state.settle_cancelled_cost(exc)
        cost_bound_exceeded = state.cost_bound_exceeded()
        try:
            await _run_sync_durable(
                partial(
                    _finish_exception,
                    request,
                    state,
                    error=exc,
                    stage="cancelled",
                    terminal_state=LifecycleState.FAILED if cost_bound_exceeded else LifecycleState.CANCELLED,
                    reason_code="cost_bound_exceeded" if cost_bound_exceeded else "cancelled",
                    attach_trace_id=True,
                )
            )
        except BaseException as completion_error:
            _attach_durable_completion_failure(exc, completion_error)
            raise exc from None
        raise
    except Exception as exc:
        state.settle_cancelled_cost(exc)
        cost_bound_exceeded = state.cost_bound_exceeded()
        await _run_sync_durable(
            partial(
                _finish_exception,
                request,
                state,
                error=exc,
                stage="run_consult",
                terminal_state=LifecycleState.FAILED,
                reason_code="cost_bound_exceeded" if cost_bound_exceeded else "consult_failed",
                attach_trace_id=True,
            )
        )
        raise


__all__ = [
    "DEFAULT_CONSULT_HEARTBEAT_SECONDS",
    "DEFAULT_CONSULT_MAX_ELAPSED_SECONDS",
    "MAX_CONSULT_MAX_ELAPSED_SECONDS",
    "ConsultElapsedLimitError",
    "ConsultStorageError",
    "ConsultStorageIOError",
    "ConsultStorageLockTimeoutError",
    "execute_consult_transaction",
    "one_shot_consult_bounds",
    "requested_consult_capacity",
]
