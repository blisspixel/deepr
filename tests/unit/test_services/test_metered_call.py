"""Contracts for durable metered-call admission."""

import asyncio
import sqlite3
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.observability.cost_ledger import CostLedger, default_cost_data_dir
from deepr.services.metered_call import (
    MeteredCallAccountingError,
)
from deepr.services.metered_call import (
    execute_reserved_async_call as _execute_reserved_async_call,
)
from deepr.services.metered_call import (
    execute_reserved_async_stream as _execute_reserved_async_stream,
)
from deepr.services.metered_call import (
    execute_reserved_fixed_cost_async_call as _execute_reserved_fixed_cost_async_call,
)
from deepr.services.metered_call import (
    execute_reserved_sync_call as _execute_reserved_sync_call,
)


def _test_request_envelope(kwargs: dict[str, object]) -> dict[str, object]:
    return {"operation": kwargs.get("operation_prefix", "test"), "test_call": True}


def execute_reserved_sync_call(**kwargs):
    kwargs.setdefault("max_cost_per_job", 1.0)
    kwargs.setdefault("request_envelope", _test_request_envelope(kwargs))
    return _execute_reserved_sync_call(**kwargs)


async def execute_reserved_async_call(**kwargs):
    kwargs.setdefault("max_cost_per_job", 1.0)
    kwargs.setdefault("request_envelope", _test_request_envelope(kwargs))
    return await _execute_reserved_async_call(**kwargs)


async def execute_reserved_async_stream(**kwargs):
    kwargs.setdefault("max_cost_per_job", 1.0)
    kwargs.setdefault("request_envelope", _test_request_envelope(kwargs))
    async for item in _execute_reserved_async_stream(**kwargs):
        yield item


async def execute_reserved_fixed_cost_async_call(**kwargs):
    kwargs.setdefault("request_envelope", _test_request_envelope(kwargs))
    return await _execute_reserved_fixed_cost_async_call(**kwargs)


def test_missing_request_envelope_is_rejected_before_reservation_or_dispatch() -> None:
    call = Mock()

    with (
        patch("deepr.services.metered_call.reserve_configured_cost_ceiling") as reserve,
        pytest.raises(MeteredCallAccountingError, match="exact request envelope"),
    ):
        _execute_reserved_sync_call(
            operation_prefix="missing-envelope",
            provider="openai",
            model="gpt-5",
            source="test.missing_envelope",
            max_cost_per_job=1.0,
            call=call,
        )

    reserve.assert_not_called()
    call.assert_not_called()


def test_request_mutation_after_reservation_refunds_before_dispatch() -> None:
    from deepr.services import metered_call as metered_call_module

    request_envelope = {"operation": "mutation", "messages": [{"content": "before"}]}
    call = Mock()
    reserve = metered_call_module.reserve_configured_cost_ceiling

    def reserve_then_mutate(**kwargs):
        reservation = reserve(**kwargs)
        request_envelope["messages"][0]["content"] = "after"
        return reservation

    with (
        patch.object(metered_call_module, "reserve_configured_cost_ceiling", side_effect=reserve_then_mutate),
        pytest.raises(MeteredCallAccountingError, match="dispatch mark failed"),
    ):
        _execute_reserved_sync_call(
            operation_prefix="mutated-envelope",
            provider="openai",
            model="gpt-5",
            source="test.mutated_envelope",
            max_cost_per_job=1.0,
            call=call,
            request_envelope=request_envelope,
        )

    call.assert_not_called()
    assert ResearchReservationStore().active_cost() == 0


def test_request_mutation_after_durable_mark_blocks_call_and_settles_ceiling() -> None:
    from deepr.services import metered_call as metered_call_module

    request_envelope = {"operation": "mutation", "messages": [{"content": "before"}]}
    call = Mock()
    mark = metered_call_module._mark_provider_dispatch

    def mark_then_mutate(*args, **kwargs):
        mark(*args, **kwargs)
        request_envelope["messages"][0]["content"] = "after"

    with (
        patch.object(metered_call_module, "_mark_provider_dispatch", side_effect=mark_then_mutate),
        pytest.raises(MeteredCallAccountingError, match="changed after its durable mark"),
    ):
        _execute_reserved_sync_call(
            operation_prefix="post-mark-mutated-envelope",
            provider="openai",
            model="gpt-5",
            source="test.post_mark_mutated_envelope",
            max_cost_per_job=1.0,
            call=call,
            request_envelope=request_envelope,
        )

    call.assert_not_called()
    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(1.0)
    assert events[0].metadata["metered_call_settlement_reason"] == "provider_call_failed"


def test_opaque_default_ceiling_is_rejected_before_provider_work() -> None:
    call = Mock()

    with pytest.raises(MeteredCallAccountingError, match="provider-enforced maximum"):
        _execute_reserved_sync_call(
            operation_prefix="opaque",
            provider="openai",
            model="gpt-5",
            source="test.opaque",
            call=call,
            request_envelope={"operation": "opaque"},
        )

    call.assert_not_called()
    assert ResearchReservationStore().active_cost() == 0


@pytest.mark.parametrize(
    ("provider", "model", "message"),
    [
        ("anthropic", "gpt-5", "cannot execute model"),
        ("openai", "unknown-paid-model", "no trusted pricing identity"),
    ],
)
def test_token_model_contract_is_validated_before_reservation(
    provider: str,
    model: str,
    message: str,
) -> None:
    call = Mock()

    with (
        patch("deepr.services.metered_call.reserve_configured_cost_ceiling") as reserve,
        pytest.raises(MeteredCallAccountingError, match=message),
    ):
        execute_reserved_sync_call(
            operation_prefix="identity",
            provider=provider,
            model=model,
            source="test.identity",
            call=call,
        )

    reserve.assert_not_called()
    call.assert_not_called()


def test_missing_response_model_identity_consumes_full_hold() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(input_tokens=100, output_tokens=20))

    result = execute_reserved_sync_call(
        operation_prefix="missing-model",
        provider="openai",
        model="gpt-5",
        source="test.missing_model",
        call=lambda: response,
    )

    assert result is response
    event = CostLedger().get_events()[0]
    assert event.cost_usd == pytest.approx(1.0)
    assert event.metadata["actual_cost_reported"] is False


def test_mismatched_response_model_consumes_hold_and_surfaces_error() -> None:
    response = SimpleNamespace(
        model="claude-sonnet-4-6",
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )

    with pytest.raises(ValueError, match="does not match reserved model"):
        execute_reserved_sync_call(
            operation_prefix="wrong-model",
            provider="openai",
            model="gpt-5",
            source="test.wrong_model",
            call=lambda: response,
        )

    event = CostLedger().get_events()[0]
    assert event.cost_usd == pytest.approx(1.0)
    assert event.metadata["metered_call_settlement_reason"] == "provider_model_identity_mismatch"


def test_sync_call_settles_reported_token_cost_and_releases_ceiling() -> None:
    response = SimpleNamespace(model="gpt-5", usage=SimpleNamespace(input_tokens=1000, output_tokens=500))
    settled: list[float] = []

    def call() -> object:
        database = default_cost_data_dir() / "research_reservations.db"
        with sqlite3.connect(database) as connection:
            marked = connection.execute(
                "SELECT provider_work_may_have_run, provider, model, request_envelope_sha256, "
                "dispatch_binding_id FROM research_cost_reservations"
            ).fetchone()
        assert marked is not None
        assert marked[:3] == (1, "openai", "gpt-5")
        assert isinstance(marked[3], str) and len(marked[3]) == 64
        assert isinstance(marked[4], str) and len(marked[4]) == 64
        return response

    result = execute_reserved_sync_call(
        operation_prefix="plan",
        provider="openai",
        model="gpt-5",
        source="test.metered",
        call=call,
        on_settled=settled.append,
    )

    assert result is response
    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd >= 0
    assert settled == [events[0].cost_usd]


def test_sync_call_preserves_http_and_object_receipt_identifiers() -> None:
    response = SimpleNamespace(
        _request_id="req-http-123",
        id="response-object-456",
        headers={"x-request-id": "req-header-lower-priority"},
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )

    execute_reserved_sync_call(
        operation_prefix="receipt",
        provider="openai",
        model="gpt-5",
        source="test.receipt",
        call=lambda: response,
    )

    event = CostLedger().get_events()[0]
    assert event.request_id == "req-http-123"
    assert event.metadata["provider_http_request_id"] == "req-http-123"
    assert event.metadata["provider_object_id"] == "response-object-456"
    assert event.metadata["client_correlation_id"].startswith("receipt-")


def test_sync_failure_preserves_nested_provider_request_id() -> None:
    provider_error = RuntimeError("provider rejected request")
    provider_error.request_id = "req-error-789"  # type: ignore[attr-defined]
    wrapper_error = RuntimeError("wrapped provider failure")
    wrapper_error.__cause__ = provider_error

    with pytest.raises(RuntimeError, match="wrapped provider failure"):
        execute_reserved_sync_call(
            operation_prefix="failure-receipt",
            provider="openai",
            model="gpt-5",
            source="test.failure_receipt",
            call=Mock(side_effect=wrapper_error),
        )

    event = CostLedger().get_events()[0]
    assert event.request_id == "req-error-789"
    assert event.metadata["provider_http_request_id"] == "req-error-789"
    assert event.metadata["metered_call_settlement_reason"] == "provider_call_failed"


def test_sync_call_does_not_probe_undeclared_dynamic_receipt_fields() -> None:
    class DynamicResponse:
        def __init__(self) -> None:
            self.usage = SimpleNamespace(input_tokens=100, output_tokens=20)
            self.dynamic_reads: list[str] = []

        def __getattr__(self, name: str) -> object:
            self.dynamic_reads.append(name)
            raise AssertionError(f"unexpected dynamic field read: {name}")

    response = DynamicResponse()
    execute_reserved_sync_call(
        operation_prefix="no-dynamic-receipt",
        provider="openai",
        model="gpt-5",
        source="test.no_dynamic_receipt",
        call=lambda: response,
    )

    assert response.dynamic_reads == []
    event = CostLedger().get_events()[0]
    assert event.request_id == ""
    assert "provider_http_request_id" not in event.metadata
    assert "provider_object_id" not in event.metadata


def test_sync_call_does_not_replay_ambiguous_failure() -> None:
    call = Mock(side_effect=TimeoutError("response lost"))

    with pytest.raises(TimeoutError, match="response lost"):
        execute_reserved_sync_call(
            operation_prefix="plan",
            provider="openai",
            model="gpt-5",
            source="test.metered",
            call=call,
        )

    call.assert_called_once_with()
    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(1.0)


def test_sync_call_conservatively_settles_every_post_mark_failure() -> None:
    settled: list[float] = []

    with pytest.raises(ValueError, match="invalid request"):
        execute_reserved_sync_call(
            operation_prefix="plan",
            provider="openai",
            model="gpt-5",
            source="test.metered",
            call=Mock(side_effect=ValueError("invalid request")),
            on_settled=settled.append,
        )

    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(1.0)
    assert events[0].metadata["metered_call_settlement_reason"] == "provider_call_failed"
    assert settled == [pytest.approx(1.0)]


def test_sync_call_conservatively_settles_malformed_usage_and_propagates() -> None:
    response = SimpleNamespace(
        model="gpt-5",
        usage=SimpleNamespace(prompt_tokens="unknown", completion_tokens=10),
    )

    with pytest.raises(ValueError, match="non-negative integer"):
        execute_reserved_sync_call(
            operation_prefix="plan",
            provider="openai",
            model="gpt-5",
            source="test.metered",
            call=lambda: response,
        )

    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(1.0)
    assert events[0].metadata["metered_call_settlement_reason"] == "malformed_or_unpriceable_usage"


def test_sync_call_treats_undeclared_usage_as_unreported() -> None:
    response = Mock()

    result = execute_reserved_sync_call(
        operation_prefix="plan",
        provider="openai",
        model="gpt-5",
        source="test.metered",
        call=lambda: response,
    )

    assert result is response
    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(1.0)
    assert events[0].metadata["actual_cost_reported"] is False


def test_sync_call_treats_declared_empty_usage_as_unreported() -> None:
    response = SimpleNamespace(usage=SimpleNamespace())

    result = execute_reserved_sync_call(
        operation_prefix="plan",
        provider="openai",
        model="gpt-5",
        source="test.metered",
        call=lambda: response,
    )

    assert result is response
    assert ResearchReservationStore().active_cost() == 0
    assert CostLedger().get_events()[0].cost_usd == pytest.approx(1.0)


def test_sync_call_conservatively_settles_nonfinite_calculated_cost() -> None:
    response = SimpleNamespace(model="gpt-5", usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2))

    with (
        patch("deepr.services.metered_call.CostEstimator.calculate_actual_cost", return_value=float("nan")),
        pytest.raises(ValueError, match="finite and non-negative"),
    ):
        execute_reserved_sync_call(
            operation_prefix="plan",
            provider="openai",
            model="gpt-5",
            source="test.metered",
            call=lambda: response,
        )

    assert ResearchReservationStore().active_cost() == 0
    assert CostLedger().get_events()[0].cost_usd == pytest.approx(1.0)


def test_sync_reservation_value_error_propagates() -> None:
    with (
        patch("deepr.services.metered_call.reserve_configured_cost_ceiling", side_effect=ValueError("blocked")),
        pytest.raises(ValueError, match="blocked"),
    ):
        execute_reserved_sync_call(
            operation_prefix="plan",
            provider="openai",
            model="gpt-5",
            source="test.metered",
            call=Mock(),
        )


def test_sync_reservation_storage_error_is_typed() -> None:
    with (
        patch("deepr.services.metered_call.reserve_configured_cost_ceiling", side_effect=OSError("unavailable")),
        pytest.raises(MeteredCallAccountingError, match="reservation failed"),
    ):
        execute_reserved_sync_call(
            operation_prefix="plan",
            provider="openai",
            model="gpt-5",
            source="test.metered",
            call=Mock(),
        )


def test_sync_dispatch_mark_failure_refunds_and_blocks_provider() -> None:
    call = Mock()

    with (
        patch("deepr.services.metered_call._mark_provider_dispatch", side_effect=OSError("mark unavailable")),
        pytest.raises(MeteredCallAccountingError, match="dispatch mark failed"),
    ):
        execute_reserved_sync_call(
            operation_prefix="plan",
            provider="openai",
            model="gpt-5",
            source="test.metered",
            call=call,
        )

    call.assert_not_called()
    assert ResearchReservationStore().active_cost() == 0
    assert CostLedger().get_events() == []


def test_sync_settlement_failure_is_typed_and_keeps_hold() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2))

    with (
        patch("deepr.services.metered_call.settle_research_cost", side_effect=OSError("ledger unavailable")),
        pytest.raises(MeteredCallAccountingError, match="settlement failed"),
    ):
        execute_reserved_sync_call(
            operation_prefix="plan",
            provider="openai",
            model="gpt-5",
            source="test.metered",
            call=lambda: response,
        )

    assert ResearchReservationStore().active_cost() == pytest.approx(1.0)
    assert CostLedger().get_events() == []


@pytest.mark.asyncio
async def test_async_call_settles_once_without_replay() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10))
    call = AsyncMock(return_value=response)

    result = await execute_reserved_async_call(
        operation_prefix="embedding",
        provider="openai",
        model="text-embedding-3-small",
        source="test.async_metered",
        call=call,
    )

    assert result is response
    call.assert_awaited_once_with()
    assert ResearchReservationStore().active_cost() == 0
    assert len(CostLedger().get_events()) == 1


@pytest.mark.asyncio
async def test_async_call_preserves_header_request_and_object_ids() -> None:
    response = SimpleNamespace(
        id="message-object-123",
        headers={"X-Request-ID": "req-async-123"},
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10),
    )

    await execute_reserved_async_call(
        operation_prefix="async-receipt",
        provider="openai",
        model="gpt-5",
        source="test.async_receipt",
        call=AsyncMock(return_value=response),
    )

    event = CostLedger().get_events()[0]
    assert event.request_id == "req-async-123"
    assert event.metadata["provider_http_request_id"] == "req-async-123"
    assert event.metadata["provider_object_id"] == "message-object-123"


@pytest.mark.asyncio
async def test_async_dispatch_mark_failure_refunds_and_blocks_provider() -> None:
    call = AsyncMock()

    with (
        patch("deepr.services.metered_call._mark_provider_dispatch", side_effect=OSError("mark unavailable")),
        pytest.raises(MeteredCallAccountingError, match="dispatch mark failed"),
    ):
        await execute_reserved_async_call(
            operation_prefix="mark-failed",
            provider="openai",
            model="gpt-5",
            source="test.async_mark_failed",
            call=call,
        )

    call.assert_not_awaited()
    assert ResearchReservationStore().active_cost() == 0
    assert CostLedger().get_events() == []


@pytest.mark.asyncio
async def test_async_cancellation_after_dispatch_settles_full_ceiling_before_returning() -> None:
    provider_started = asyncio.Event()
    provider_release = asyncio.Event()

    async def call() -> object:
        provider_started.set()
        await provider_release.wait()
        return SimpleNamespace(usage=None)

    task = asyncio.create_task(
        execute_reserved_async_call(
            operation_prefix="cancelled",
            provider="openai",
            model="gpt-5",
            source="test.async_cancelled",
            call=call,
        )
    )
    await asyncio.wait_for(provider_started.wait(), timeout=2)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    database = default_cost_data_dir() / "research_reservations.db"
    renamed = database.with_suffix(".moved")
    database.rename(renamed)
    renamed.rename(database)

    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(1.0)
    assert events[0].metadata["metered_call_settlement_reason"] == "provider_call_cancelled"


@pytest.mark.asyncio
async def test_async_cancellation_owns_reservation_then_refunds_before_returning() -> None:
    entered = threading.Event()
    release = threading.Event()
    from deepr.services import metered_call

    real_reserve = metered_call.reserve_configured_cost_ceiling

    def delayed_reserve(**kwargs: object) -> object:
        entered.set()
        assert release.wait(timeout=2)
        return real_reserve(**kwargs)

    with patch("deepr.services.metered_call.reserve_configured_cost_ceiling", side_effect=delayed_reserve):
        task = asyncio.create_task(
            execute_reserved_async_call(
                operation_prefix="cancelled-reserve",
                provider="openai",
                model="gpt-5",
                source="test.async_cancelled_reserve",
                call=AsyncMock(),
            )
        )
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError) as cancelled:
            await task

    assert cancelled.value.__dict__["metered_call_predispatch_reservation_cleaned"] is True
    assert ResearchReservationStore().active_cost() == 0
    assert CostLedger().get_events() == []


@pytest.mark.asyncio
async def test_async_cancellation_owns_dispatch_mark_then_refunds_before_call() -> None:
    entered = threading.Event()
    release = threading.Event()
    call = AsyncMock()
    from deepr.services import metered_call

    real_mark = metered_call._mark_provider_dispatch

    def delayed_mark(reservation: object, authority: object, dispatch_call: object) -> None:
        entered.set()
        assert release.wait(timeout=2)
        real_mark(reservation, authority, dispatch_call)  # type: ignore[arg-type]

    with patch("deepr.services.metered_call._mark_provider_dispatch", side_effect=delayed_mark):
        task = asyncio.create_task(
            execute_reserved_async_call(
                operation_prefix="cancelled-mark",
                provider="openai",
                model="gpt-5",
                source="test.async_cancelled_mark",
                call=call,
            )
        )
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError) as cancelled:
            await task

    call.assert_not_awaited()
    assert cancelled.value.__dict__["metered_call_predispatch_reservation_cleaned"] is True
    assert ResearchReservationStore().active_cost() == 0
    assert CostLedger().get_events() == []


@pytest.mark.asyncio
async def test_async_cancellation_finishes_normal_settlement_before_returning() -> None:
    entered = threading.Event()
    release = threading.Event()
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500))
    from deepr.services import metered_call

    real_settle = metered_call._settle_response

    def delayed_settle(*args: object, **kwargs: object) -> None:
        entered.set()
        assert release.wait(timeout=2)
        real_settle(*args, **kwargs)  # type: ignore[arg-type]

    with patch("deepr.services.metered_call._settle_response", side_effect=delayed_settle):
        task = asyncio.create_task(
            execute_reserved_async_call(
                operation_prefix="cancelled-settle",
                provider="openai",
                model="gpt-5",
                source="test.async_cancelled_settle",
                call=AsyncMock(return_value=response),
            )
        )
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert ResearchReservationStore().active_cost() == 0
    assert len(CostLedger().get_events()) == 1


@pytest.mark.asyncio
async def test_async_malformed_usage_settles_full_ceiling_and_propagates() -> None:
    response = SimpleNamespace(model="gpt-5", usage=SimpleNamespace(prompt_tokens=-1, completion_tokens=2))

    with pytest.raises(ValueError, match="non-negative integer"):
        await execute_reserved_async_call(
            operation_prefix="malformed",
            provider="openai",
            model="gpt-5",
            source="test.async_malformed",
            call=AsyncMock(return_value=response),
        )

    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(1.0)
    assert events[0].metadata["metered_call_settlement_reason"] == "malformed_or_unpriceable_usage"


@pytest.mark.asyncio
async def test_async_cancellation_surfaces_conservative_settlement_failure() -> None:
    provider_started = asyncio.Event()

    async def call() -> object:
        provider_started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    with patch("deepr.services.metered_call.settle_research_cost", side_effect=OSError("ledger unavailable")):
        task = asyncio.create_task(
            execute_reserved_async_call(
                operation_prefix="cancelled-failed-settle",
                provider="openai",
                model="gpt-5",
                source="test.async_cancelled_failed_settle",
                call=call,
            )
        )
        await asyncio.wait_for(provider_started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError) as cancelled:
            await task

    accounting_error = cancelled.value.__dict__["metered_call_accounting_error"]
    assert isinstance(accounting_error, MeteredCallAccountingError)
    assert cancelled.value.__dict__["metered_call_accounting_stage"] == "conservative settlement"
    assert ResearchReservationStore().active_cost() == pytest.approx(1.0)
    assert CostLedger().get_events() == []


@pytest.mark.asyncio
async def test_async_settlement_failure_is_fail_closed_and_keeps_hold() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10))
    call = AsyncMock(return_value=response)

    with (
        patch("deepr.services.metered_call.settle_research_cost", side_effect=OSError("ledger unavailable")),
        pytest.raises(MeteredCallAccountingError, match="settlement failed"),
    ):
        await execute_reserved_async_call(
            operation_prefix="absorb",
            provider="openai",
            model="gpt-5-mini",
            source="test.async_metered",
            call=call,
        )

    call.assert_awaited_once_with()
    assert ResearchReservationStore().active_cost() == pytest.approx(1.0)
    assert CostLedger().get_events() == []


@pytest.mark.asyncio
async def test_async_stream_settles_final_usage_and_releases_ceiling() -> None:
    settled: list[float] = []

    async def events():
        yield "hel", None
        yield "lo", SimpleNamespace(input_tokens=50, output_tokens=10)

    chunks = [
        item
        async for item in execute_reserved_async_stream(
            operation_prefix="stream",
            provider="openai",
            model="gpt-5",
            source="test.stream",
            events=events,
            max_cost_per_job=1.0,
            on_settled=settled.append,
        )
    ]

    assert chunks == ["hel", "lo"]
    assert ResearchReservationStore().active_cost() == 0
    assert settled
    assert settled[0] >= 0


@pytest.mark.asyncio
async def test_async_stream_preserves_receipt_identifiers_from_chunks() -> None:
    chunk = SimpleNamespace(_request_id="req-stream-123", id="chunk-object-123")

    async def events():
        yield chunk, SimpleNamespace(input_tokens=50, output_tokens=10)

    chunks = [
        item
        async for item in execute_reserved_async_stream(
            operation_prefix="stream-receipt",
            provider="openai",
            model="gpt-5",
            source="test.stream_receipt",
            events=events,
            max_cost_per_job=1.0,
        )
    ]

    assert chunks == [chunk]
    event = CostLedger().get_events()[0]
    assert event.request_id == "req-stream-123"
    assert event.metadata["provider_http_request_id"] == "req-stream-123"
    assert event.metadata["provider_object_id"] == "chunk-object-123"


@pytest.mark.asyncio
async def test_fixed_cost_call_settles_success_cost_and_releases_ceiling() -> None:
    settled: list[float] = []

    async def call() -> dict[str, object]:
        database = default_cost_data_dir() / "research_reservations.db"
        with sqlite3.connect(database) as connection:
            marked = connection.execute("SELECT provider_work_may_have_run FROM research_cost_reservations").fetchone()
        assert marked == (1,)
        return {"result": "ok", "cost": 0.05}

    result = await execute_reserved_fixed_cost_async_call(
        operation_prefix="skill-tool",
        provider="skill",
        model="recon:lookup",
        source="test.fixed_cost",
        max_cost_per_job=0.05,
        call=call,
        cost_from_result=lambda value: float(value["cost"]),
        on_settled=settled.append,
    )

    assert result == {"result": "ok", "cost": 0.05}
    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(0.05)
    assert settled == [pytest.approx(0.05)]


@pytest.mark.asyncio
async def test_fixed_cost_call_preserves_mapping_receipt_identifiers() -> None:
    result = await execute_reserved_fixed_cost_async_call(
        operation_prefix="fixed-receipt",
        provider="skill",
        model="recon:lookup",
        source="test.fixed_receipt",
        max_cost_per_job=0.05,
        call=AsyncMock(
            return_value={
                "request_id": "req-fixed-123",
                "id": "tool-object-123",
                "cost": 0.05,
            }
        ),
        cost_from_result=lambda value: float(value["cost"]),
    )

    assert result["id"] == "tool-object-123"
    event = CostLedger().get_events()[0]
    assert event.request_id == "req-fixed-123"
    assert event.metadata["provider_http_request_id"] == "req-fixed-123"
    assert event.metadata["provider_object_id"] == "tool-object-123"


@pytest.mark.asyncio
async def test_fixed_cost_call_settles_ceiling_on_ambiguous_soft_failure() -> None:
    settled: list[float] = []

    result = await execute_reserved_fixed_cost_async_call(
        operation_prefix="skill-tool",
        provider="skill",
        model="recon:lookup",
        source="test.fixed_cost_soft_fail",
        max_cost_per_job=0.20,
        call=AsyncMock(return_value={"error": "timeout", "cost": 0.0}),
        cost_from_result=lambda value: 0.0 if "error" in value else 0.20,
        on_settled=settled.append,
    )

    assert result["error"] == "timeout"
    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(0.20)
    assert settled == [pytest.approx(0.20)]


@pytest.mark.asyncio
async def test_fixed_cost_call_conservatively_settles_raised_failure() -> None:
    settled: list[float] = []

    with pytest.raises(RuntimeError, match="mcp blew up"):
        await execute_reserved_fixed_cost_async_call(
            operation_prefix="skill-tool",
            provider="skill",
            model="recon:lookup",
            source="test.fixed_cost_hard_fail",
            max_cost_per_job=0.10,
            call=AsyncMock(side_effect=RuntimeError("mcp blew up")),
            cost_from_result=lambda _value: 0.10,
            on_settled=settled.append,
        )

    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(0.10)
    assert settled == [pytest.approx(0.10)]


@pytest.mark.asyncio
async def test_fixed_cost_call_rejects_report_above_reserved_ceiling() -> None:
    settled: list[float] = []

    with pytest.raises(ValueError, match="exceeds reserved ceiling"):
        await execute_reserved_fixed_cost_async_call(
            operation_prefix="skill-tool",
            provider="skill",
            model="recon:lookup",
            source="test.fixed_cost_overrun",
            max_cost_per_job=0.10,
            call=AsyncMock(return_value={"result": "ok", "cost": 0.50}),
            cost_from_result=lambda value: float(value["cost"]),
            on_settled=settled.append,
        )

    assert CostLedger().get_events()[0].cost_usd == pytest.approx(0.10)
    assert settled == [pytest.approx(0.10)]
