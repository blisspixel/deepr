"""Durable one-shot consult transaction lifecycle tests."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from types import SimpleNamespace

import pytest

from deepr.experts import consult_lifecycle as lifecycle_module
from deepr.experts import consult_lifecycle_storage as lifecycle_storage_module
from deepr.experts import consult_traces as consult_traces_module
from deepr.experts import consult_transaction as consult_transaction_module
from deepr.experts.consult_lifecycle import (
    TERMINAL_STATES,
    ConsultLifecycle,
    ConsultLifecycleJournalError,
    ConsultLifecycleLockTimeoutError,
    LifecycleState,
    load_consult_lifecycle_events,
)
from deepr.experts.consult_traces import load_consult_traces
from deepr.experts.consult_transaction import (
    ConsultElapsedLimitError,
    ConsultStorageIOError,
    ConsultStorageLockTimeoutError,
    execute_consult_transaction,
    one_shot_consult_bounds,
    requested_consult_capacity,
)


def _backend():
    return SimpleNamespace(
        client=object(),
        model="fixture-model",
        provider="local",
        allow_live_fallback=False,
    )


def _api_backend():
    return SimpleNamespace(
        client=object(),
        model="fixture-model",
        provider="openai",
        allow_live_fallback=False,
    )


def _result(*, synthesis_status: str = "completed", total_cost: float = 0.0) -> dict:
    return {
        "query": "q",
        "perspectives": [
            {
                "expert_name": "Fixture Expert",
                "domain": "testing",
                "response": "SECRET ANSWER TEXT",
                "confidence": 0.8,
                "cost": 0.0,
                "context": {"source": "belief_store"},
            }
        ],
        "synthesis": "SECRET SYNTHESIS TEXT",
        "synthesis_status": synthesis_status,
        "agreements": [],
        "disagreements": ["A bounded dissent"],
        "requested_budget_usd": 0.0,
        "total_cost": total_cost,
    }


def _capacity():
    return requested_consult_capacity(backend_mode="local", provider="local", model="fixture-model")


@pytest.mark.asyncio
async def test_transaction_starts_before_backend_and_reuses_trace_id(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    trace_path = tmp_path / "traces.jsonl"
    observed: dict[str, object] = {}

    def backend_factory():
        events = load_consult_lifecycle_events(path=lifecycle_path)
        observed["events_before_backend"] = events
        return _backend()

    async def fake_run(*_args, **kwargs):
        await kwargs["progress_callback"]("__synthesis__", "querying")
        return _result()

    payload = await execute_consult_transaction(
        question="q",
        requested_experts=["Fixture Expert"],
        max_experts=3,
        budget=0.0,
        backend_mode="local",
        backend_factory=backend_factory,
        requested_capacity=_capacity(),
        lifecycle_path=lifecycle_path,
        trace_path=trace_path,
        run_consult_fn=fake_run,
        heartbeat_interval_seconds=0.01,
    )

    before_backend = observed["events_before_backend"]
    assert isinstance(before_backend, list)
    assert len(before_backend) == 1
    assert before_backend[0]["state"] == "running"
    assert before_backend[0]["phase"] == "preflight"

    events = load_consult_lifecycle_events(path=lifecycle_path)
    trace = load_consult_traces(path=trace_path, limit=10)[0]
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert events[-1]["state"] == "completed"
    assert events[-1]["reason_code"] == "consult_completed"
    assert payload["trace"]["trace_id"] == trace["trace_id"] == events[0]["trace_id"]
    assert "SECRET ANSWER TEXT" not in lifecycle_path.read_text(encoding="utf-8")
    assert "SECRET SYNTHESIS TEXT" not in lifecycle_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_transaction_progress_is_serialized_and_off_event_loop(tmp_path, monkeypatch):
    event_loop_thread = threading.get_ident()
    active = 0
    peak = 0
    callback_threads: list[int] = []
    guard = threading.Lock()
    original_heartbeat = ConsultLifecycle.heartbeat

    def observed_heartbeat(self, *args, **kwargs):
        nonlocal active, peak
        progress = kwargs.get("progress") or {}
        if int(progress.get("dispatches_completed", 0)) > 0:
            with guard:
                active += 1
                peak = max(peak, active)
                callback_threads.append(threading.get_ident())
            time.sleep(0.01)
            try:
                return original_heartbeat(self, *args, **kwargs)
            finally:
                with guard:
                    active -= 1
        return original_heartbeat(self, *args, **kwargs)

    async def concurrent_progress(*_args, **kwargs):
        callback = kwargs["progress_callback"]
        await asyncio.gather(*(callback("Fixture Expert", "done") for _index in range(4)))
        return _result()

    monkeypatch.setattr(ConsultLifecycle, "heartbeat", observed_heartbeat)
    await execute_consult_transaction(
        question="q",
        requested_experts=["Fixture Expert"],
        max_experts=3,
        budget=0.0,
        backend_mode="local",
        backend_factory=_backend,
        requested_capacity=_capacity(),
        lifecycle_path=tmp_path / "lifecycle.jsonl",
        trace_path=tmp_path / "traces.jsonl",
        run_consult_fn=concurrent_progress,
    )

    assert peak == 1
    assert callback_threads
    assert all(thread_id != event_loop_thread for thread_id in callback_threads)


@pytest.mark.asyncio
async def test_transaction_resolves_capacity_and_settles_observed_cost(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    requested = requested_consult_capacity(backend_mode="api", provider="openai", model="")
    backend = SimpleNamespace(
        client=object(),
        model="fixture-api-model",
        provider="openai",
        allow_live_fallback=False,
    )

    async def fake_run(*_args, **_kwargs):
        return _result(total_cost=0.25)

    await execute_consult_transaction(
        question="q",
        requested_experts=["Fixture Expert"],
        max_experts=3,
        budget=1.0,
        backend_mode="api",
        backend_factory=lambda: backend,
        requested_capacity=requested,
        lifecycle_path=lifecycle_path,
        trace_path=tmp_path / "traces.jsonl",
        run_consult_fn=fake_run,
    )

    events = load_consult_lifecycle_events(path=lifecycle_path)
    assert events[0]["capacity"]["model"] == ""
    assert events[1]["capacity"]["model"] == "fixture-api-model"
    assert events[1]["capacity"]["admission"] == "admitted"
    assert events[-1]["bounds"]["max_cost_usd"] == 1.0
    assert events[-1]["progress"]["cost_usd_observed"] == 0.25
    assert events[-1]["remaining"]["cost_usd"] == 0.75


@pytest.mark.asyncio
async def test_transaction_timeout_cancels_work_and_records_one_terminal_event(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    trace_path = tmp_path / "traces.jsonl"
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def ready_backend():
        return _backend()

    async def blocked(*_args, **_kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with pytest.raises(ConsultElapsedLimitError) as raised:
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=ready_backend,
            requested_capacity=_capacity(),
            max_elapsed_seconds=1.0,
            heartbeat_interval_seconds=0.005,
            lifecycle_path=lifecycle_path,
            trace_path=trace_path,
            run_consult_fn=blocked,
        )

    assert started.is_set()
    assert cancelled.is_set()
    assert raised.value.retryable is False
    events = load_consult_lifecycle_events(path=lifecycle_path)
    terminal = [event for event in events if LifecycleState(event["state"]) in TERMINAL_STATES]
    assert len(terminal) == 1
    assert terminal[0]["state"] == "failed"
    assert terminal[0]["reason_code"] == "elapsed_limit"
    trace = load_consult_traces(path=trace_path, limit=10)[0]
    assert trace["trace_id"] == events[0]["trace_id"]
    assert trace["failure"]["stage"] == "elapsed_limit"


@pytest.mark.asyncio
async def test_post_dispatch_elapsed_imports_settled_child_cancellation_cost(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    entered = asyncio.Event()

    async def metered_child(*_args, **_kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError as error:
            error.__dict__["council_synthesis_settlement"] = {"cost": 0.25, "settled": True}
            raise

    task = asyncio.create_task(
        execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=1.0,
            backend_mode="api",
            backend_factory=_api_backend,
            requested_capacity=requested_consult_capacity(
                backend_mode="api",
                provider="openai",
                model="fixture-model",
            ),
            max_elapsed_seconds=0.5,
            heartbeat_interval_seconds=1.0,
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=metered_child,
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    with pytest.raises(ConsultElapsedLimitError) as raised:
        await task

    terminal = load_consult_lifecycle_events(path=lifecycle_path)[-1]
    assert raised.value.retryable is False
    assert terminal["reason_code"] == "elapsed_limit"
    assert terminal["progress"]["cost_usd_observed"] == 0.25
    assert terminal["remaining"]["cost_usd"] == 0.75


@pytest.mark.asyncio
async def test_transaction_timeout_cancels_async_backend_preflight(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocked_backend():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def forbidden_run(*_args, **_kwargs):
        raise AssertionError("generation ran after preflight timeout")

    with pytest.raises(ConsultElapsedLimitError) as raised:
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=blocked_backend,
            requested_capacity=_capacity(),
            # Keep enough headroom for slow CI hosts to reach preflight before the
            # elapsed ceiling fires, while still short enough for a unit test.
            max_elapsed_seconds=0.2,
            heartbeat_interval_seconds=0.01,
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=forbidden_run,
        )

    assert entered.is_set(), "elapsed limit fired before async backend preflight started"
    try:
        await asyncio.wait_for(cancelled.wait(), timeout=1.0)
    except TimeoutError:
        pytest.fail("async backend preflight was not cancelled after elapsed limit")
    assert raised.value.retryable is True
    events = load_consult_lifecycle_events(path=lifecycle_path)
    assert events[-1]["phase"] == "preflight"
    assert events[-1]["state"] == "failed"
    assert events[-1]["reason_code"] == "elapsed_limit"


@pytest.mark.asyncio
async def test_lifecycle_start_persistence_consumes_transaction_deadline(tmp_path, monkeypatch):
    clock = {"now": 0.0}
    original_append = lifecycle_storage_module.append_jsonl_durable
    backend_called = False
    monkeypatch.setattr(lifecycle_module.time, "monotonic", lambda: clock["now"])

    def delayed_append(*args, **kwargs):
        clock["now"] = 0.1
        original_append(*args, **kwargs)

    def forbidden_backend():
        nonlocal backend_called
        backend_called = True
        return _backend()

    monkeypatch.setattr(lifecycle_storage_module, "append_jsonl_durable", delayed_append)
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    with pytest.raises(ConsultElapsedLimitError):
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=forbidden_backend,
            requested_capacity=_capacity(),
            max_elapsed_seconds=0.05,
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
        )

    assert backend_called is False
    events = load_consult_lifecycle_events(path=lifecycle_path)
    assert events[-1]["reason_code"] == "elapsed_limit"


@pytest.mark.asyncio
async def test_sync_backend_factory_does_not_block_cancellable_deadline(tmp_path):
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    finished = asyncio.Event()
    generation_called = False

    def blocked_backend():
        loop.call_soon_threadsafe(entered.set)
        release.wait(timeout=5.0)
        loop.call_soon_threadsafe(finished.set)
        return _backend()

    async def forbidden_generation(*_args, **_kwargs):
        nonlocal generation_called
        generation_called = True
        return _result()

    task = asyncio.create_task(
        execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=blocked_backend,
            requested_capacity=_capacity(),
            # Lifecycle persistence consumes the same total deadline. Leave
            # enough headroom for a loaded CI host to enter the backend thread,
            # while the five-second worker wait still outlasts this ceiling.
            max_elapsed_seconds=0.5,
            heartbeat_interval_seconds=1.0,
            lifecycle_path=tmp_path / "lifecycle.jsonl",
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=forbidden_generation,
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=2.0)
    except TimeoutError:
        pytest.fail("elapsed limit fired before the sync backend thread started")
    try:
        with pytest.raises(ConsultElapsedLimitError):
            await task
    finally:
        release.set()
        try:
            await asyncio.wait_for(finished.wait(), timeout=2.0)
        except TimeoutError:
            pytest.fail("sync backend thread did not finish after release")

    assert generation_called is False


@pytest.mark.asyncio
async def test_sync_started_callback_crossing_ceiling_stops_before_backend(tmp_path, monkeypatch):
    clock = {"now": 0.0}
    backend_called = False
    monkeypatch.setattr(lifecycle_module.time, "monotonic", lambda: clock["now"])

    def cross_ceiling(_trace_id):
        clock["now"] = 1.0

    def forbidden_backend():
        nonlocal backend_called
        backend_called = True
        return _backend()

    lifecycle_path = tmp_path / "lifecycle.jsonl"
    with pytest.raises(ConsultElapsedLimitError):
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=forbidden_backend,
            requested_capacity=_capacity(),
            max_elapsed_seconds=1.0,
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
            on_started=cross_ceiling,
        )

    assert backend_called is False
    events = load_consult_lifecycle_events(path=lifecycle_path)
    assert len([event for event in events if LifecycleState(event["state"]) in TERMINAL_STATES]) == 1
    assert events[-1]["reason_code"] == "elapsed_limit"


@pytest.mark.asyncio
async def test_lifecycle_heartbeat_elapsed_stop_surfaces_public_timeout_once(tmp_path, monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(lifecycle_module.time, "monotonic", lambda: clock["now"])
    lifecycle_path = tmp_path / "lifecycle.jsonl"

    async def cross_ceiling(*_args, **kwargs):
        clock["now"] = 1.0
        await kwargs["progress_callback"]("Fixture Expert", "done")
        raise AssertionError("elapsed heartbeat did not stop generation")

    with pytest.raises(ConsultElapsedLimitError):
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=_backend,
            requested_capacity=_capacity(),
            max_elapsed_seconds=1.0,
            heartbeat_interval_seconds=10.0,
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=cross_ceiling,
        )

    events = load_consult_lifecycle_events(path=lifecycle_path)
    terminal = [event for event in events if LifecycleState(event["state"]) in TERMINAL_STATES]
    assert len(terminal) == 1
    assert terminal[0]["reason_code"] == "elapsed_limit"


@pytest.mark.asyncio
async def test_cancellation_at_elapsed_ceiling_becomes_public_timeout_once(tmp_path, monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(lifecycle_module.time, "monotonic", lambda: clock["now"])
    lifecycle_path = tmp_path / "lifecycle.jsonl"

    async def cancelled_at_ceiling(*_args, **_kwargs):
        clock["now"] = 1.0
        raise asyncio.CancelledError

    with pytest.raises(ConsultElapsedLimitError):
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=_backend,
            requested_capacity=_capacity(),
            max_elapsed_seconds=1.0,
            heartbeat_interval_seconds=10.0,
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=cancelled_at_ceiling,
        )

    events = load_consult_lifecycle_events(path=lifecycle_path)
    terminal = [event for event in events if LifecycleState(event["state"]) in TERMINAL_STATES]
    assert len(terminal) == 1
    assert terminal[0]["reason_code"] == "elapsed_limit"


@pytest.mark.asyncio
async def test_trace_lock_at_elapsed_boundary_stays_nonretryable_after_provider_work(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    trace_path = tmp_path / "traces.jsonl"
    held_lock = consult_traces_module._shared_trace_path_lock(trace_path)
    held_lock.acquire()
    try:
        with pytest.raises(ConsultStorageLockTimeoutError) as raised:
            await execute_consult_transaction(
                question="q",
                requested_experts=["Fixture Expert"],
                max_experts=3,
                budget=0.0,
                backend_mode="local",
                backend_factory=_backend,
                requested_capacity=_capacity(),
                max_elapsed_seconds=0.2,
                heartbeat_interval_seconds=1.0,
                lifecycle_path=lifecycle_path,
                trace_path=trace_path,
                run_consult_fn=lambda *_args, **_kwargs: asyncio.sleep(0, result=_result()),
            )
    finally:
        if held_lock.locked():
            held_lock.release()

    events = load_consult_lifecycle_events(path=lifecycle_path)
    terminal = [event for event in events if LifecycleState(event["state"]) in TERMINAL_STATES]
    assert raised.value.retryable is False
    assert raised.value.consult_lifecycle_terminal == "elapsed_limit"
    assert len(terminal) == 1
    assert terminal[0]["reason_code"] == "elapsed_limit"
    assert not trace_path.exists()


@pytest.mark.asyncio
async def test_post_work_trace_lock_failure_checkpoints_cost_and_is_not_retryable(tmp_path, monkeypatch):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    trace_path = tmp_path / "traces.jsonl"
    monkeypatch.setattr(consult_traces_module, "_DEFAULT_TRACE_LOCK_TIMEOUT_SECONDS", 0.01)
    held_lock = consult_traces_module._shared_trace_path_lock(trace_path)
    held_lock.acquire()
    try:
        with pytest.raises(ConsultStorageLockTimeoutError) as raised:
            await execute_consult_transaction(
                question="q",
                requested_experts=["Fixture Expert"],
                max_experts=3,
                budget=1.0,
                backend_mode="local",
                backend_factory=_backend,
                requested_capacity=_capacity(),
                max_elapsed_seconds=1.0,
                heartbeat_interval_seconds=2.0,
                lifecycle_path=lifecycle_path,
                trace_path=trace_path,
                run_consult_fn=lambda *_args, **_kwargs: asyncio.sleep(0, result=_result(total_cost=0.25)),
            )
    finally:
        if held_lock.locked():
            held_lock.release()

    events = load_consult_lifecycle_events(path=lifecycle_path)
    assert raised.value.retryable is False
    assert raised.value.trace_id == events[0]["trace_id"]
    assert raised.value.__cause__ is None
    assert events[-1]["state"] == "failed"
    assert events[-1]["reason_code"] == "storage_lock_timeout"
    assert events[-1]["progress"]["cost_usd_observed"] == 0.25
    assert events[-1]["remaining"]["cost_usd"] == 0.75
    assert not trace_path.exists()


@pytest.mark.asyncio
async def test_post_work_trace_io_failure_is_path_safe_and_checkpoints_cost(tmp_path, monkeypatch):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    trace_path = tmp_path / "private" / "traces.jsonl"

    def fail_append(*_args, **_kwargs):
        raise OSError(f"fsync failed for {trace_path}")

    monkeypatch.setattr(consult_traces_module, "append_jsonl_durable", fail_append)
    with pytest.raises(ConsultStorageIOError) as raised:
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=1.0,
            backend_mode="local",
            backend_factory=_backend,
            requested_capacity=_capacity(),
            max_elapsed_seconds=1.0,
            lifecycle_path=lifecycle_path,
            trace_path=trace_path,
            run_consult_fn=lambda *_args, **_kwargs: asyncio.sleep(0, result=_result(total_cost=0.25)),
        )

    terminal = load_consult_lifecycle_events(path=lifecycle_path)[-1]
    assert raised.value.retryable is False
    assert raised.value.partial_write_possible is True
    assert raised.value.error_code == "CONSULT_STORAGE_IO_ERROR"
    assert str(trace_path) not in str(raised.value)
    assert str(trace_path) not in repr(vars(raised.value))
    assert terminal["state"] == "failed"
    assert terminal["reason_code"] == "storage_io_error"
    assert terminal["progress"]["cost_usd_observed"] == 0.25


@pytest.mark.asyncio
async def test_post_work_lifecycle_lock_failure_is_not_retryable(tmp_path, monkeypatch):
    lifecycle_path = tmp_path / "private" / "lifecycle.jsonl"
    monkeypatch.setattr(lifecycle_module, "_DEFAULT_LOCK_TIMEOUT_SECONDS", 0.01)
    held_lock = lifecycle_module._shared_path_lock(lifecycle_path)

    async def complete_while_locked(*_args, **_kwargs):
        held_lock.acquire()
        return _result(total_cost=0.25)

    try:
        with pytest.raises(ConsultStorageLockTimeoutError) as raised:
            await execute_consult_transaction(
                question="q",
                requested_experts=["Fixture Expert"],
                max_experts=3,
                budget=1.0,
                backend_mode="local",
                backend_factory=_backend,
                requested_capacity=_capacity(),
                max_elapsed_seconds=1.0,
                heartbeat_interval_seconds=2.0,
                lifecycle_path=lifecycle_path,
                trace_path=tmp_path / "traces.jsonl",
                run_consult_fn=complete_while_locked,
            )
    finally:
        if held_lock.locked():
            held_lock.release()

    assert raised.value.retryable is False
    assert raised.value.consult_settlement_failure == "lifecycle_lock_timeout"
    assert raised.value.__cause__ is None
    assert str(lifecycle_path) not in str(raised.value)
    assert str(lifecycle_path) not in repr(vars(raised.value))


@pytest.mark.asyncio
async def test_lifecycle_start_lock_timeout_is_retryable_and_has_trace_id(tmp_path, monkeypatch):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    monkeypatch.setattr(lifecycle_module, "_DEFAULT_LOCK_TIMEOUT_SECONDS", 0.01)
    held_lock = lifecycle_module._shared_path_lock(lifecycle_path)
    held_lock.acquire()
    try:
        with pytest.raises(ConsultStorageLockTimeoutError) as raised:
            await execute_consult_transaction(
                question="q",
                requested_experts=["Fixture Expert"],
                max_experts=3,
                budget=0.0,
                backend_mode="local",
                backend_factory=_backend,
                requested_capacity=_capacity(),
                max_elapsed_seconds=1.0,
                lifecycle_path=lifecycle_path,
                trace_path=tmp_path / "traces.jsonl",
            )
    finally:
        if held_lock.locked():
            held_lock.release()

    assert raised.value.retryable is True
    assert raised.value.trace_id.startswith("consult_")
    assert not lifecycle_path.exists()


@pytest.mark.asyncio
async def test_lifecycle_parent_io_failure_is_path_safe_and_retryable_before_write(tmp_path):
    private_parent = tmp_path / "private-parent"
    private_parent.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ConsultStorageIOError) as raised:
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=_backend,
            requested_capacity=_capacity(),
            lifecycle_path=private_parent / "lifecycle.jsonl",
            trace_path=tmp_path / "traces.jsonl",
        )

    assert raised.value.retryable is True
    assert raised.value.partial_write_possible is False
    assert raised.value.error_code == "CONSULT_STORAGE_IO_ERROR"
    assert str(private_parent) not in str(raised.value)
    assert str(private_parent) not in repr(vars(raised.value))


@pytest.mark.asyncio
async def test_lifecycle_partial_append_failure_is_path_safe_and_not_retryable(tmp_path, monkeypatch):
    lifecycle_path = tmp_path / "private" / "lifecycle.jsonl"
    original_append = lifecycle_storage_module.append_jsonl_durable

    def append_then_fail(*args, **kwargs):
        original_append(*args, **kwargs)
        raise OSError(f"fsync failed for {lifecycle_path}")

    monkeypatch.setattr(lifecycle_storage_module, "append_jsonl_durable", append_then_fail)
    with pytest.raises(ConsultStorageIOError) as raised:
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=_backend,
            requested_capacity=_capacity(),
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
        )

    assert raised.value.retryable is False
    assert raised.value.partial_write_possible is True
    assert str(lifecycle_path) not in str(raised.value)
    assert str(lifecycle_path) not in repr(vars(raised.value))


@pytest.mark.asyncio
async def test_provider_failure_preserves_public_error_when_lifecycle_settlement_locks(tmp_path, monkeypatch):
    lifecycle_path = tmp_path / "private" / "lifecycle.jsonl"
    monkeypatch.setattr(lifecycle_module, "_DEFAULT_LOCK_TIMEOUT_SECONDS", 0.01)
    held_lock = lifecycle_module._shared_path_lock(lifecycle_path)

    async def fail_while_locked(*_args, **_kwargs):
        held_lock.acquire()
        raise ValueError("provider failed")

    try:
        with pytest.raises(ValueError, match="provider failed") as raised:
            await execute_consult_transaction(
                question="q",
                requested_experts=["Fixture Expert"],
                max_experts=3,
                budget=0.0,
                backend_mode="local",
                backend_factory=_backend,
                requested_capacity=_capacity(),
                max_elapsed_seconds=1.0,
                lifecycle_path=lifecycle_path,
                trace_path=tmp_path / "traces.jsonl",
                run_consult_fn=fail_while_locked,
            )
    finally:
        if held_lock.locked():
            held_lock.release()

    assert str(lifecycle_path) not in str(raised.value)
    assert raised.value.consult_settlement_failure == "lifecycle_lock_timeout"
    assert str(lifecycle_path) not in repr(vars(raised.value))
    assert not hasattr(raised.value, "original_error")


@pytest.mark.asyncio
async def test_cancellation_lifecycle_lock_timeout_preserves_cancel_context(tmp_path, monkeypatch):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    monkeypatch.setattr(lifecycle_module, "_DEFAULT_LOCK_TIMEOUT_SECONDS", 0.01)
    held_lock = lifecycle_module._shared_path_lock(lifecycle_path)

    async def cancel_while_locked(*_args, **_kwargs):
        held_lock.acquire()
        raise asyncio.CancelledError

    try:
        with pytest.raises(asyncio.CancelledError) as raised:
            await execute_consult_transaction(
                question="q",
                requested_experts=["Fixture Expert"],
                max_experts=3,
                budget=0.0,
                backend_mode="local",
                backend_factory=_backend,
                requested_capacity=_capacity(),
                max_elapsed_seconds=1.0,
                lifecycle_path=lifecycle_path,
                trace_path=tmp_path / "traces.jsonl",
                run_consult_fn=cancel_while_locked,
            )
    finally:
        if held_lock.locked():
            held_lock.release()

    assert raised.value.consult_settlement_failure == "lifecycle_lock_timeout"
    assert str(lifecycle_path) not in repr(vars(raised.value))
    assert not hasattr(raised.value, "original_error")


@pytest.mark.parametrize(
    ("settlement_error", "expected_code"),
    [
        (ConsultLifecycleLockTimeoutError(r"locked C:\private\lifecycle.jsonl"), "lifecycle_lock_timeout"),
        (ConsultLifecycleJournalError(r"invalid C:\private\lifecycle.jsonl"), "lifecycle_journal_error"),
    ],
)
@pytest.mark.asyncio
async def test_elapsed_error_survives_sanitized_lifecycle_settlement_failure(
    tmp_path, monkeypatch, settlement_error, expected_code
):
    def fail_stop(_self, *, phase, progress=None):
        del phase, progress
        raise settlement_error

    async def blocked(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(ConsultLifecycle, "stop_elapsed_limit", fail_stop)
    with pytest.raises(ConsultElapsedLimitError) as raised:
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=_backend,
            requested_capacity=_capacity(),
            max_elapsed_seconds=0.02,
            heartbeat_interval_seconds=1.0,
            lifecycle_path=tmp_path / "lifecycle.jsonl",
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=blocked,
        )

    assert raised.value.consult_settlement_failure == expected_code
    assert "C:\\private" not in str(raised.value)
    assert "C:\\private" not in repr(vars(raised.value))
    assert not hasattr(raised.value, "original_error")


@pytest.mark.asyncio
async def test_trace_contention_preserves_nonretryable_error_when_terminal_journal_fails(tmp_path, monkeypatch):
    lifecycle_path = tmp_path / "private" / "lifecycle.jsonl"
    trace_path = tmp_path / "private" / "traces.jsonl"
    monkeypatch.setattr(consult_traces_module, "_DEFAULT_TRACE_LOCK_TIMEOUT_SECONDS", 0.01)
    held_lock = consult_traces_module._shared_trace_path_lock(trace_path)

    def fail_finish(_self, *_args, **_kwargs):
        raise ConsultLifecycleJournalError(f"could not write {lifecycle_path}")

    monkeypatch.setattr(ConsultLifecycle, "finish", fail_finish)
    held_lock.acquire()
    try:
        with pytest.raises(ConsultStorageLockTimeoutError) as raised:
            await execute_consult_transaction(
                question="q",
                requested_experts=["Fixture Expert"],
                max_experts=3,
                budget=1.0,
                backend_mode="local",
                backend_factory=_backend,
                requested_capacity=_capacity(),
                max_elapsed_seconds=1.0,
                heartbeat_interval_seconds=2.0,
                lifecycle_path=lifecycle_path,
                trace_path=trace_path,
                run_consult_fn=lambda *_args, **_kwargs: asyncio.sleep(0, result=_result(total_cost=0.25)),
            )
    finally:
        if held_lock.locked():
            held_lock.release()

    assert raised.value.retryable is False
    assert raised.value.consult_settlement_failure == "lifecycle_journal_error"
    assert raised.value.__cause__ is None
    assert str(lifecycle_path) not in str(raised.value)
    assert str(lifecycle_path) not in repr(vars(raised.value))
    events = load_consult_lifecycle_events(path=lifecycle_path)
    assert events[-1]["progress"]["cost_usd_observed"] == 0.25


@pytest.mark.asyncio
async def test_transaction_cancellation_is_recorded_and_reraised(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    trace_path = tmp_path / "traces.jsonl"
    entered = asyncio.Event()

    async def blocked(*_args, **_kwargs):
        entered.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(
        execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=_backend,
            requested_capacity=_capacity(),
            lifecycle_path=lifecycle_path,
            trace_path=trace_path,
            run_consult_fn=blocked,
        )
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    events = load_consult_lifecycle_events(path=lifecycle_path)
    assert events[-1]["state"] == "cancelled"
    assert events[-1]["reason_code"] == "cancelled"
    assert len([event for event in events if LifecycleState(event["state"]) in TERMINAL_STATES]) == 1


@pytest.mark.asyncio
async def test_transaction_cancellation_checkpoints_only_settled_bounded_cost(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"

    async def cancelled_with_settlement(*_args, **_kwargs):
        error = asyncio.CancelledError()
        error.__dict__["council_synthesis_settlement"] = {"cost": 0.25, "settled": True}
        raise error

    with pytest.raises(asyncio.CancelledError):
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=1.0,
            backend_mode="api",
            backend_factory=_api_backend,
            requested_capacity=requested_consult_capacity(
                backend_mode="api",
                provider="openai",
                model="fixture-model",
            ),
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=cancelled_with_settlement,
        )

    terminal = load_consult_lifecycle_events(path=lifecycle_path)[-1]
    assert terminal["state"] == "cancelled"
    assert terminal["progress"]["cost_usd_observed"] == 0.25
    assert terminal["remaining"]["cost_usd"] == 0.75


@pytest.mark.parametrize(
    "settlement",
    [
        {"cost": 0.25, "settled": False},
        {"cost": float("nan"), "settled": True},
        {"cost": True, "settled": True},
    ],
)
@pytest.mark.asyncio
async def test_transaction_cancellation_rejects_unsettled_or_unbounded_cost(tmp_path, settlement):
    lifecycle_path = tmp_path / f"lifecycle_{len(str(settlement))}.jsonl"

    async def cancelled_with_invalid_settlement(*_args, **_kwargs):
        error = asyncio.CancelledError()
        error.__dict__["council_synthesis_settlement"] = settlement
        raise error

    with pytest.raises(asyncio.CancelledError):
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=1.0,
            backend_mode="api",
            backend_factory=_api_backend,
            requested_capacity=requested_consult_capacity(
                backend_mode="api",
                provider="openai",
                model="fixture-model",
            ),
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=cancelled_with_invalid_settlement,
        )

    assert load_consult_lifecycle_events(path=lifecycle_path)[-1]["progress"]["cost_usd_observed"] == 0.0


@pytest.mark.asyncio
async def test_settled_cancellation_over_budget_records_actual_and_typed_violation(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"

    async def cancelled_with_overrun(*_args, **_kwargs):
        error = asyncio.CancelledError()
        error.__dict__["council_synthesis_settlement"] = {"cost": 1.68, "settled": True}
        raise error

    with pytest.raises(asyncio.CancelledError):
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=1.0,
            backend_mode="api",
            backend_factory=_api_backend,
            requested_capacity=requested_consult_capacity(
                backend_mode="api",
                provider="openai",
                model="fixture-model",
            ),
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=cancelled_with_overrun,
        )

    events = load_consult_lifecycle_events(path=lifecycle_path)
    terminal = events[-1]
    assert terminal["state"] == "failed"
    assert terminal["reason_code"] == "cost_bound_exceeded"
    assert terminal["progress"]["cost_usd_observed"] == 1.68
    assert terminal["remaining"]["cost_usd"] == 0.0
    assert not any(event["state"] == "running" and event["progress"]["cost_usd_observed"] > 1.0 for event in events)


@pytest.mark.asyncio
async def test_generic_provider_error_imports_already_settled_council_cost(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"

    async def failed_with_settlement(*_args, **_kwargs):
        error = RuntimeError("provider result could not be returned")
        error.__dict__["council_synthesis_settlement"] = {"cost": 0.25, "settled": True}
        raise error

    with pytest.raises(RuntimeError, match="provider result could not be returned"):
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=1.0,
            backend_mode="api",
            backend_factory=_api_backend,
            requested_capacity=requested_consult_capacity(
                backend_mode="api",
                provider="openai",
                model="fixture-model",
            ),
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=failed_with_settlement,
        )

    terminal = load_consult_lifecycle_events(path=lifecycle_path)[-1]
    assert terminal["state"] == "failed"
    assert terminal["reason_code"] == "consult_failed"
    assert terminal["progress"]["cost_usd_observed"] == 0.25
    assert terminal["remaining"]["cost_usd"] == 0.75


@pytest.mark.asyncio
async def test_successful_finalize_wins_racing_cancellation_and_returns_payload(tmp_path, monkeypatch):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    entered = threading.Event()
    release = threading.Event()
    original_finalize = consult_transaction_module._finalize_result

    def blocked_finalize(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=2.0)
        return original_finalize(*args, **kwargs)

    monkeypatch.setattr(consult_transaction_module, "_finalize_result", blocked_finalize)
    task = asyncio.create_task(
        execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=_backend,
            requested_capacity=_capacity(),
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=lambda *_args, **_kwargs: asyncio.sleep(0, result=_result()),
        )
    )
    assert await asyncio.to_thread(entered.wait, 2.0)
    task.cancel()
    release.set()

    payload = await task

    assert payload["synthesis_status"] == "completed"
    terminal = load_consult_lifecycle_events(path=lifecycle_path)[-1]
    assert terminal["state"] == "completed"
    assert terminal["reason_code"] == "consult_completed"


@pytest.mark.asyncio
async def test_successful_result_over_budget_is_a_failed_bound_violation_without_heartbeat(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"
    payload = await execute_consult_transaction(
        question="q",
        requested_experts=["Fixture Expert"],
        max_experts=3,
        budget=1.0,
        backend_mode="api",
        backend_factory=_api_backend,
        requested_capacity=requested_consult_capacity(
            backend_mode="api",
            provider="openai",
            model="fixture-model",
        ),
        lifecycle_path=lifecycle_path,
        trace_path=tmp_path / "traces.jsonl",
        run_consult_fn=lambda *_args, **_kwargs: asyncio.sleep(0, result=_result(total_cost=1.68)),
    )

    assert payload["cost_usd"] == 1.68
    assert payload["cost_bound_exceeded"] is True
    assert payload["synthesis_status"] == "failed"
    assert payload["synthesis_error_type"] == "CostBoundExceeded"
    events = load_consult_lifecycle_events(path=lifecycle_path)
    assert events[-1]["reason_code"] == "cost_bound_exceeded"
    assert events[-1]["remaining"]["cost_usd"] == 0.0
    assert not any(event["state"] == "running" and event["progress"]["cost_usd_observed"] > 1.0 for event in events)


@pytest.mark.asyncio
async def test_provider_timeout_is_not_mislabeled_as_host_elapsed_limit(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"

    async def provider_timeout(*_args, **_kwargs):
        raise TimeoutError("provider socket timeout")

    with pytest.raises(TimeoutError, match="provider socket timeout"):
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=_backend,
            requested_capacity=_capacity(),
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
            run_consult_fn=provider_timeout,
        )

    events = load_consult_lifecycle_events(path=lifecycle_path)
    assert events[-1]["state"] == "failed"
    assert events[-1]["reason_code"] == "consult_failed"


@pytest.mark.asyncio
async def test_incomplete_synthesis_is_a_failed_lifecycle_with_final_trace(tmp_path):
    async def incomplete(*_args, **_kwargs):
        return _result(synthesis_status="truncated")

    lifecycle_path = tmp_path / "lifecycle.jsonl"
    payload = await execute_consult_transaction(
        question="q",
        requested_experts=["Fixture Expert"],
        max_experts=3,
        budget=0.0,
        backend_mode="local",
        backend_factory=_backend,
        requested_capacity=_capacity(),
        lifecycle_path=lifecycle_path,
        trace_path=tmp_path / "traces.jsonl",
        run_consult_fn=incomplete,
    )

    assert payload["trace"]["status"] == "failed"
    events = load_consult_lifecycle_events(path=lifecycle_path)
    assert events[-1]["state"] == "failed"
    assert events[-1]["reason_code"] == "synthesis_incomplete"


def test_one_shot_bounds_report_only_observed_work_and_spend():
    assert one_shot_consult_bounds(requested_experts=["A", "B"], max_experts=9) == {
        "dispatch_scope": "council_work_item",
        "max_cost_usd": 0.0,
        "max_dispatches": 3,
    }
    assert one_shot_consult_bounds(requested_experts=[], max_experts=3)["max_dispatches"] == 4
    assert one_shot_consult_bounds(requested_experts=["A"], max_experts=3, budget=2.0)["max_cost_usd"] == 2.0
    with pytest.raises(ValueError, match="between 1 and 10"):
        one_shot_consult_bounds(requested_experts=[], max_experts=0)
    with pytest.raises(ValueError, match="finite and non-negative"):
        one_shot_consult_bounds(requested_experts=["A"], max_experts=3, budget=float("nan"))


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), 21_601, True])
@pytest.mark.asyncio
async def test_transaction_rejects_invalid_elapsed_ceiling_before_lifecycle_write(tmp_path, value):
    lifecycle_path = tmp_path / "lifecycle.jsonl"

    with pytest.raises(ValueError, match="max_elapsed_seconds"):
        await execute_consult_transaction(
            question="q",
            requested_experts=["Fixture Expert"],
            max_experts=3,
            budget=0.0,
            backend_mode="local",
            backend_factory=_backend,
            requested_capacity=_capacity(),
            max_elapsed_seconds=value,
            lifecycle_path=lifecycle_path,
            trace_path=tmp_path / "traces.jsonl",
        )

    assert not lifecycle_path.exists()


def test_lifecycle_json_is_bounded_metadata_only(tmp_path):
    lifecycle_path = tmp_path / "lifecycle.jsonl"

    lifecycle = ConsultLifecycle.start(
        path=lifecycle_path,
        max_elapsed_seconds=10,
        capacity=_capacity(),
        bounds=one_shot_consult_bounds(requested_experts=["A"], max_experts=3),
        lineage={
            "operation": "one_shot",
            "question_hash": "a" * 64,
            "roster_hash": "b" * 64,
        },
    )
    event = json.loads(lifecycle_path.read_text(encoding="utf-8"))

    assert event["contract"]["answer_text_allowed"] is False
    assert event["contract"]["private_reasoning_allowed"] is False
    assert "max_output_tokens" not in event["bounds"]
    assert "max_context_bytes" not in event["bounds"]
    assert "output_tokens_observed" not in event["progress"]
    assert "context_bytes_observed" not in event["progress"]
    assert "output_tokens" not in event["remaining"]
    assert "context_bytes" not in event["remaining"]
    assert "question" not in event
    assert "answer" not in event
    lifecycle.finish(LifecycleState.CANCELLED, reason_code="cancelled")
