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
    execute_reserved_async_call,
    execute_reserved_sync_call,
)


def test_sync_call_settles_reported_token_cost_and_releases_ceiling() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(input_tokens=1000, output_tokens=500))
    settled: list[float] = []

    def call() -> object:
        database = default_cost_data_dir() / "research_reservations.db"
        with sqlite3.connect(database) as connection:
            marked = connection.execute("SELECT provider_work_may_have_run FROM research_cost_reservations").fetchone()
        assert marked == (1,)
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
    assert events[0].cost_usd == pytest.approx(5.0)


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
    assert events[0].cost_usd == pytest.approx(5.0)
    assert events[0].metadata["metered_call_settlement_reason"] == "provider_call_failed"
    assert settled == [pytest.approx(5.0)]


def test_sync_call_conservatively_settles_malformed_usage_and_propagates() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens="unknown", completion_tokens=10))

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
    assert events[0].cost_usd == pytest.approx(5.0)
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
    assert events[0].cost_usd == pytest.approx(5.0)
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
    assert CostLedger().get_events()[0].cost_usd == pytest.approx(5.0)


def test_sync_call_conservatively_settles_nonfinite_calculated_cost() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2))

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
    assert CostLedger().get_events()[0].cost_usd == pytest.approx(5.0)


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

    assert ResearchReservationStore().active_cost() == pytest.approx(5.0)
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
    assert events[0].cost_usd == pytest.approx(5.0)
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

    def delayed_mark(reservation: object) -> None:
        entered.set()
        assert release.wait(timeout=2)
        real_mark(reservation)  # type: ignore[arg-type]

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
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=-1, completion_tokens=2))

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
    assert events[0].cost_usd == pytest.approx(5.0)
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
    assert ResearchReservationStore().active_cost() == pytest.approx(5.0)
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
    assert ResearchReservationStore().active_cost() == pytest.approx(5.0)
    assert CostLedger().get_events() == []
