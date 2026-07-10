"""Contracts for durable synchronous metered-call admission."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.observability.cost_ledger import CostLedger
from deepr.services.metered_call import execute_reserved_async_call, execute_reserved_sync_call


def test_sync_call_settles_reported_token_cost_and_releases_ceiling() -> None:
    response = SimpleNamespace(usage=SimpleNamespace(input_tokens=1000, output_tokens=500))

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
    assert events[0].cost_usd >= 0


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


def test_sync_call_refunds_definitive_pre_acceptance_failure() -> None:
    with pytest.raises(ValueError, match="invalid request"):
        execute_reserved_sync_call(
            operation_prefix="plan",
            provider="openai",
            model="gpt-5",
            source="test.metered",
            call=Mock(side_effect=ValueError("invalid request")),
        )

    assert ResearchReservationStore().active_cost() == 0
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
