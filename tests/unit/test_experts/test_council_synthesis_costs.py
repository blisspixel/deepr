"""Cost-bound regressions for metered council synthesis."""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from anthropic.types import Usage

from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.consult import AnthropicConsultSynthesisClient
from deepr.experts.consult_lifecycle_errors import ConsultLifecycleError
from deepr.experts.cost_safety import get_cost_safety_manager, reset_cost_safety_manager
from deepr.experts.council import ExpertCouncil, ExpertPerspective
from deepr.experts.council_synthesis_costs import (
    anthropic_completion_usage,
    metered_synthesis_cost_bound,
    openai_completion_usage,
    record_synthesis_cost,
)
from deepr.observability.cost_ledger import CostLedger


def _perspectives() -> list[ExpertPerspective]:
    return [ExpertPerspective(expert_name="Cost Expert", domain="cost safety", response="Use exact bounds.")]


def _anthropic_bound():
    return metered_synthesis_cost_bound(
        provider="anthropic",
        model="claude-sonnet-4-6",
        system_prompt="system",
        user_prompt="question",
        output_token_ceiling=800,
        budget=1.0,
    )


def _openai_bound():
    return metered_synthesis_cost_bound(
        provider="openai",
        model="gpt-5-mini",
        system_prompt="system",
        user_prompt="question",
        output_token_ceiling=800,
        budget=1.0,
    )


def test_real_anthropic_usage_shape_treats_absent_optional_cache_fields_as_zero():
    usage = Usage(input_tokens=10, output_tokens=5)

    result = anthropic_completion_usage(usage, _anthropic_bound())

    assert result["cost"] == pytest.approx((10 / 1_000_000) * 3.0 + (5 / 1_000_000) * 15.0)
    assert result["tokens_input"] == 10
    assert result["tokens_output"] == 5
    assert result["cache_creation_input_tokens"] == 0
    assert result["cache_read_input_tokens"] == 0
    assert result["cost_estimated"] is False


@pytest.mark.parametrize(
    "usage",
    [
        SimpleNamespace(input_tokens=10),
        SimpleNamespace(output_tokens=5),
        SimpleNamespace(input_tokens=-1, output_tokens=5),
        SimpleNamespace(input_tokens=1.5, output_tokens=5),
        SimpleNamespace(input_tokens=10, output_tokens=float("nan")),
        SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=-1),
    ],
)
def test_anthropic_missing_or_invalid_required_usage_settles_full_bound(usage):
    bound = _anthropic_bound()

    result = anthropic_completion_usage(usage, bound)

    assert result["cost"] == bound.worst_case_cost_usd
    assert result["tokens_input"] == bound.input_token_ceiling
    assert result["tokens_output"] == bound.output_token_ceiling
    assert result["cost_estimated"] is True
    assert result["cost_estimate_reason"] in {"provider_usage_incomplete", "provider_usage_invalid"}


@pytest.mark.parametrize(
    "usage",
    [
        SimpleNamespace(prompt_tokens=10),
        SimpleNamespace(completion_tokens=5),
        SimpleNamespace(prompt_tokens=-1, completion_tokens=5),
        SimpleNamespace(prompt_tokens=1.5, completion_tokens=5),
        SimpleNamespace(prompt_tokens=10, completion_tokens=float("inf")),
    ],
)
def test_openai_missing_or_invalid_usage_settles_full_bound(usage):
    bound = _openai_bound()

    result = openai_completion_usage(usage, bound)

    assert result["cost"] == bound.worst_case_cost_usd
    assert result["tokens_input"] == bound.input_token_ceiling
    assert result["tokens_output"] == bound.output_token_ceiling
    assert result["cost_estimated"] is True
    assert result["cost_estimate_reason"] in {"provider_usage_incomplete", "provider_usage_invalid"}


def _stored_expert(name: str) -> list[dict[str, str]]:
    store = BeliefStore(name)
    store.add_belief(
        Belief(
            claim="Metered synthesis must settle ambiguous dispatches conservatively.",
            confidence=0.9,
            domain="cost safety",
        ),
        check_conflicts=False,
    )
    return [{"name": name, "domain": "cost safety"}]


def _paid_openai_response() -> SimpleNamespace:
    return SimpleNamespace(
        id="chatcmpl_settlement",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="### SYNTHESIS:\nUse durable settlement."),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=50,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
        ),
    )


@pytest.fixture(autouse=True)
def reset_cost_manager():
    reset_cost_safety_manager()
    yield
    reset_cost_safety_manager()


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [0.0, 0.000001])
async def test_metered_synthesis_rejects_unaffordable_slice_before_dispatch(budget):
    calls = 0

    class Completions:
        async def create(self, **_kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("unaffordable synthesis must not dispatch")

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    result = await ExpertCouncil(
        synthesis_client=client,
        synthesis_model="gpt-5-mini",
        synthesis_provider="openai",
    )._synthesise("q", _perspectives(), budget=budget)

    assert calls == 0
    assert result["cost"] == 0.0
    assert result["dispatch_status"] == "not_dispatched"
    assert result["synthesis_error_type"] == "CouncilSynthesisCostError"


@pytest.mark.asyncio
async def test_metered_synthesis_rejects_unknown_model_before_dispatch():
    calls = 0

    class Completions:
        async def create(self, **_kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("unknown pricing must not dispatch")

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    result = await ExpertCouncil(
        synthesis_client=client,
        synthesis_model="unknown-metered-model",
        synthesis_provider="openai",
    )._synthesise("q", _perspectives(), budget=1.0)

    assert calls == 0
    assert result["cost"] == 0.0
    assert result["synthesis_error_type"] == "CouncilSynthesisCostError"


@pytest.mark.asyncio
async def test_council_rejects_budget_above_absolute_ceiling_before_work_or_dispatch():
    calls = 0

    class Completions:
        async def create(self, **_kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("over-ceiling council must not dispatch")

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    manager = get_cost_safety_manager()
    budget = manager.ABSOLUTE_MAX_PER_OPERATION + 0.01
    result = await ExpertCouncil(
        synthesis_client=client,
        synthesis_model="gpt-4o-mini",
        synthesis_provider="openai",
    ).consult(
        "Do not bypass the absolute cost ceiling.",
        experts=[{"name": "Budget Ceiling Expert", "domain": "cost safety"}],
        budget=budget,
    )

    assert calls == 0
    assert result["requested_budget_usd"] == budget
    assert result["total_cost"] == 0.0
    assert "absolute per-op ceiling" in result["synthesis"]
    assert manager._reserved_daily == 0.0


@pytest.mark.asyncio
async def test_post_dispatch_failure_settles_reservation_and_canonical_ledger():
    class Completions:
        async def create(self, **_kwargs):
            raise RuntimeError("ambiguous provider failure")

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    council = ExpertCouncil(
        synthesis_client=client,
        synthesis_model="gpt-5-mini",
        synthesis_provider="openai",
    )
    result = await council.consult(
        "How should ambiguous synthesis settle?",
        experts=_stored_expert("Failed Synthesis Cost Expert"),
        budget=1.0,
    )

    events = CostLedger().get_events(source="expert_council.synthesis")
    assert result["synthesis_status"] == "failed"
    assert result["total_cost"] > 0
    assert len(events) == 1
    assert events[0].cost_usd > 0
    assert events[0].metadata["estimated"] is True
    assert events[0].metadata["cost_estimate_reason"] == "post_dispatch_failure"
    assert events[0].metadata["dispatch_status"] == "outcome_unknown"


@pytest.mark.asyncio
async def test_post_dispatch_cancellation_settles_once_and_propagates():
    started = asyncio.Event()

    class Completions:
        async def create(self, **_kwargs):
            started.set()
            await asyncio.Future()

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    council = ExpertCouncil(
        synthesis_client=client,
        synthesis_model="gpt-5-mini",
        synthesis_provider="openai",
    )
    task = asyncio.create_task(
        council.consult(
            "How should cancelled synthesis settle?",
            experts=_stored_expert("Cancelled Synthesis Cost Expert"),
            budget=1.0,
        )
    )
    await started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError) as exc_info:
        await task

    settlement = exc_info.value.__dict__["council_synthesis_settlement"]
    events = CostLedger().get_events(source="expert_council.synthesis")
    assert task.cancelled()
    assert settlement["settled"] is True
    assert settlement["cost_estimate_reason"] == "cancelled_after_dispatch"
    assert len(events) == 1
    assert events[0].cost_usd == settlement["cost"]
    assert events[0].idempotency_key == settlement["idempotency_key"]
    assert events[0].metadata["estimated"] is True
    assert events[0].metadata["cost_estimate_reason"] == "cancelled_after_dispatch"
    assert events[0].metadata["dispatch_status"] == "outcome_unknown"


@pytest.mark.asyncio
async def test_paid_response_settles_before_fallible_lifecycle_done_callback():
    provider_calls = 0

    class Completions:
        async def create(self, **_kwargs):
            nonlocal provider_calls
            provider_calls += 1
            return _paid_openai_response()

    async def progress(name: str, status: str) -> None:
        if name == "__synthesis__" and status == "done":
            raise ConsultLifecycleError("lifecycle done failed")

    manager = get_cost_safety_manager()
    council = ExpertCouncil(
        synthesis_client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
        synthesis_model="gpt-4o-mini",
        synthesis_provider="openai",
    )

    with pytest.raises(ConsultLifecycleError, match="lifecycle done failed") as exc_info:
        await council.consult(
            "Which operation must happen first?",
            experts=_stored_expert("Lifecycle Ordering Cost Expert"),
            budget=1.0,
            progress_callback=progress,
        )

    events = CostLedger().get_events(source="expert_council.synthesis")
    settlement = exc_info.value.__dict__["council_synthesis_settlement"]
    assert provider_calls == 1
    assert len(events) == 1
    assert events[0].cost_usd > 0
    assert manager.daily_cost == pytest.approx(events[0].cost_usd)
    assert manager.get_session_cost(events[0].session_id) == pytest.approx(events[0].cost_usd)
    assert manager._reserved_daily == 0.0
    assert settlement["settled"] is True
    assert settlement["idempotency_key"] == events[0].idempotency_key


@pytest.mark.asyncio
async def test_cancellation_during_durable_settlement_waits_for_writer_and_propagates(monkeypatch):
    class Completions:
        async def create(self, **_kwargs):
            return _paid_openai_response()

    manager = get_cost_safety_manager()
    real_record_event = manager._ledger.record_event
    settlement_entered = threading.Event()
    release_settlement = threading.Event()

    def blocked_record_event(*args, **kwargs):
        settlement_entered.set()
        assert release_settlement.wait(timeout=5)
        return real_record_event(*args, **kwargs)

    monkeypatch.setattr(manager._ledger, "record_event", blocked_record_event)
    council = ExpertCouncil(
        synthesis_client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
        synthesis_model="gpt-4o-mini",
        synthesis_provider="openai",
    )
    task = asyncio.create_task(
        council.consult(
            "How should cancellation preserve accounting?",
            experts=_stored_expert("Settlement Cancellation Cost Expert"),
            budget=1.0,
        )
    )
    assert await asyncio.to_thread(settlement_entered.wait, 5)

    task.cancel()
    await asyncio.sleep(0.02)
    assert task.done() is False
    release_settlement.set()
    with pytest.raises(asyncio.CancelledError) as exc_info:
        await task

    events = CostLedger().get_events(source="expert_council.synthesis")
    settlement = exc_info.value.__dict__["council_synthesis_settlement"]
    assert task.cancelled()
    assert settlement["settled"] is True
    assert len(events) == 1
    assert events[0].idempotency_key == settlement["idempotency_key"]
    assert manager.daily_cost == pytest.approx(events[0].cost_usd)
    assert manager._reserved_daily == 0.0


@pytest.mark.asyncio
async def test_durable_settlement_does_not_block_event_loop(monkeypatch):
    class Completions:
        async def create(self, **_kwargs):
            return _paid_openai_response()

    manager = get_cost_safety_manager()
    real_record_event = manager._ledger.record_event
    settlement_entered = threading.Event()
    settlement_finished = threading.Event()

    def slow_record_event(*args, **kwargs):
        settlement_entered.set()
        try:
            time.sleep(0.15)
            return real_record_event(*args, **kwargs)
        finally:
            settlement_finished.set()

    monkeypatch.setattr(manager._ledger, "record_event", slow_record_event)
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        assert await asyncio.to_thread(settlement_entered.wait, 5)
        while not settlement_finished.is_set():
            ticks += 1
            await asyncio.sleep(0.005)

    ticker_task = asyncio.create_task(ticker())
    result = await ExpertCouncil(
        synthesis_client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
        synthesis_model="gpt-4o-mini",
        synthesis_provider="openai",
    ).consult(
        "Can durable accounting stay responsive?",
        experts=_stored_expert("Responsive Settlement Cost Expert"),
        budget=1.0,
    )
    await ticker_task

    assert result["synthesis_status"] == "completed"
    assert len(CostLedger().get_events(source="expert_council.synthesis")) == 1
    assert ticks >= 5


@pytest.mark.asyncio
async def test_cancellation_after_reservation_commit_waits_and_refunds_predispatch(monkeypatch):
    manager = get_cost_safety_manager()
    council = ExpertCouncil(synthesis_provider="openai", synthesis_model="gpt-4o-mini")
    committed = threading.Event()
    release = threading.Event()
    real_check = manager.check_and_reserve

    def committed_then_blocked(**kwargs):
        result = real_check(**kwargs)
        committed.set()
        assert release.wait(timeout=2.0)
        return result

    monkeypatch.setattr(manager, "check_and_reserve", committed_then_blocked)
    task = asyncio.create_task(council._reserve_council_budget(manager, "council_reserve_cancel", 0.5))
    assert await asyncio.to_thread(committed.wait, 2.0)
    task.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await task

    assert exc_info.value.__dict__["council_predispatch_reservation_cleaned"] is True
    assert manager._reserved_daily == 0.0
    assert manager._get_reservation_store().active_cost() == 0.0


@pytest.mark.asyncio
async def test_cancellation_after_dispatch_mark_commit_waits_and_refunds_before_provider(monkeypatch):
    manager = get_cost_safety_manager()
    allowed, _, _, reservation_id = manager.check_and_reserve(
        "mark-cancel-session",
        "council_consult",
        0.5,
        durable_reservation=True,
        reservation_job_id="council_mark_cancel",
    )
    assert allowed
    council = ExpertCouncil(synthesis_provider="openai", synthesis_model="gpt-4o-mini")
    committed = threading.Event()
    release = threading.Event()
    real_mark = manager.mark_provider_work_may_have_run

    def committed_then_blocked(reservation: str) -> None:
        real_mark(reservation)
        committed.set()
        assert release.wait(timeout=2.0)

    monkeypatch.setattr(manager, "mark_provider_work_may_have_run", committed_then_blocked)
    task = asyncio.create_task(council._mark_provider_dispatch(manager, reservation_id))
    assert await asyncio.to_thread(committed.wait, 2.0)
    task.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await task

    assert exc_info.value.__dict__["council_predispatch_reservation_cleaned"] is True
    assert manager._reserved_daily == 0.0
    assert manager._get_reservation_store().active_cost() == 0.0


@pytest.mark.asyncio
async def test_cancellation_attaches_path_safe_ledger_failure_without_marking_settled(monkeypatch, tmp_path):
    started = asyncio.Event()

    class Completions:
        async def create(self, **_kwargs):
            started.set()
            await asyncio.Future()

    manager = get_cost_safety_manager()
    sensitive_path = tmp_path / "private" / "cost_ledger.jsonl"
    ledger_error = OSError(28, "No space left on device", str(sensitive_path))
    monkeypatch.setattr(manager._ledger, "record_event", MagicMock(side_effect=ledger_error))
    council = ExpertCouncil(
        synthesis_client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
        synthesis_model="gpt-4o-mini",
        synthesis_provider="openai",
    )
    task = asyncio.create_task(
        council.consult(
            "How should failed canonical settlement surface?",
            experts=_stored_expert("Ledger Failure Cancellation Expert"),
            budget=1.0,
        )
    )
    await started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError) as exc_info:
        await task

    settlement = exc_info.value.__dict__["council_synthesis_settlement"]
    settlement_error = exc_info.value.__dict__["council_synthesis_settlement_error"]
    recovery = exc_info.value.__dict__["council_synthesis_recovery"]
    assert task.cancelled()
    assert settlement.get("settled") is not True
    assert settlement["idempotency_key"].endswith(":synthesis")
    assert not {"text", "agreements", "disagreements"}.intersection(settlement)
    assert recovery == {
        "action": "retry_settlement_only",
        "do_not_retry_provider": True,
        "idempotency_key": settlement["idempotency_key"],
        "reservation_id": recovery["reservation_id"],
    }
    assert recovery["reservation_id"]
    assert isinstance(settlement_error, RuntimeError)
    assert str(settlement_error) == "Cost ledger write failed in required settlement."
    assert str(sensitive_path) not in str(settlement_error)
    assert settlement_error.__cause__ is ledger_error
    assert settlement_error.ledger_error is ledger_error
    assert settlement_error.metadata == {
        "error_type": "OSError",
        "errno": 28,
        "mode": "required_settlement",
    }
    notes = getattr(exc_info.value, "__notes__", [])
    assert "Council synthesis cancellation settlement failed: Cost ledger write failed in required settlement." in notes
    assert all(str(sensitive_path) not in note for note in notes)
    assert manager.daily_cost == 0.0
    assert manager._session_costs == {}
    assert manager._reserved_daily == 1.0
    assert manager._get_reservation_store().active_cost() == 1.0


@pytest.mark.asyncio
async def test_ordinary_post_dispatch_settlement_failure_is_path_safe(monkeypatch, tmp_path):
    class Completions:
        async def create(self, **_kwargs):
            raise RuntimeError("ambiguous provider failure")

    manager = get_cost_safety_manager()
    sensitive_path = tmp_path / "private" / "cost_ledger.jsonl"
    ledger_error = OSError(28, "No space left on device", str(sensitive_path))
    monkeypatch.setattr(manager._ledger, "record_event", MagicMock(side_effect=ledger_error))
    council = ExpertCouncil(
        synthesis_client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
        synthesis_model="gpt-4o-mini",
        synthesis_provider="openai",
    )

    with pytest.raises(RuntimeError) as exc_info:
        await council.consult(
            "How should ordinary settlement storage failure surface?",
            experts=_stored_expert("Ledger Failure Result Expert"),
            budget=1.0,
        )

    public_error = exc_info.value
    settlement = public_error.__dict__["council_synthesis_settlement"]
    recovery = public_error.__dict__["council_synthesis_recovery"]
    assert str(public_error) == "Cost ledger write failed in required settlement."
    assert str(sensitive_path) not in str(public_error)
    assert public_error.__cause__ is ledger_error
    assert public_error.ledger_error is ledger_error
    assert public_error.metadata == {
        "error_type": "OSError",
        "errno": 28,
        "mode": "required_settlement",
    }
    assert settlement["settled"] is False
    assert not {"text", "agreements", "disagreements"}.intersection(settlement)
    assert recovery["action"] == "retry_settlement_only"
    assert recovery["do_not_retry_provider"] is True
    assert recovery["idempotency_key"] == settlement["idempotency_key"]
    assert recovery["reservation_id"]
    assert manager.daily_cost == 0.0
    assert manager._session_costs == {}
    assert manager._reserved_daily == 1.0
    assert manager._get_reservation_store().active_cost() == 1.0


def test_repeated_synthesis_settlement_does_not_double_process_totals():
    manager = get_cost_safety_manager()
    session_id = "council_idempotent_settlement"
    allowed, _, _, reservation_id = manager.check_and_reserve(
        session_id=session_id,
        operation_type="council_consult",
        estimated_cost=1.0,
    )
    assert allowed
    synthesis = {
        "cost": 0.001,
        "tokens_input": 100,
        "tokens_output": 50,
        "cache_read_input_tokens": 40,
        "cost_estimated": False,
    }

    first = record_synthesis_cost(
        manager,
        council_session_id=session_id,
        reservation_id=reservation_id,
        synthesis=synthesis,
        provider="openai",
        model="gpt-4o-mini",
        expert_count=1,
        perspective_count=1,
    )
    second = record_synthesis_cost(
        manager,
        council_session_id=session_id,
        reservation_id="",
        synthesis=synthesis,
        provider="openai",
        model="gpt-4o-mini",
        expert_count=1,
        perspective_count=1,
    )

    events = CostLedger().get_events(source="expert_council.synthesis")
    assert first is True
    assert second is True
    assert len(events) == 1
    assert events[0].metadata["cache_read_input_tokens"] == 40
    assert manager.daily_cost == pytest.approx(0.001)
    assert manager.monthly_cost == pytest.approx(0.001)
    assert manager.get_session_cost(session_id) == pytest.approx(0.001)
    assert manager._reserved_daily == 0.0


@pytest.mark.asyncio
async def test_openai_cached_prompt_usage_uses_exact_registry_rate():
    class Completions:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                id="chatcmpl_cached",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="### SYNTHESIS:\nAnswer"),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=1_000,
                    completion_tokens=250,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=400),
                ),
            )

    result = await ExpertCouncil(
        synthesis_client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
        synthesis_model="gpt-4o-mini",
        synthesis_provider="openai",
    )._synthesise("q", _perspectives(), budget=1.0)

    expected = (600 / 1_000_000) * 0.15 + (400 / 1_000_000) * 0.075 + (250 / 1_000_000) * 0.60
    assert result["cost"] == pytest.approx(expected)
    assert result["tokens_input"] == 1_000
    assert result["cache_read_input_tokens"] == 400
    assert result["cost_estimated"] is False
    assert result["cost_estimate_reason"] == "provider_usage"


@pytest.mark.asyncio
async def test_openai_missing_cache_details_is_labeled_conservative():
    class Completions:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="### SYNTHESIS:\nAnswer"),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=1_000, completion_tokens=250),
            )

    result = await ExpertCouncil(
        synthesis_client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
        synthesis_model="gpt-4o-mini",
        synthesis_provider="openai",
    )._synthesise("q", _perspectives(), budget=1.0)

    expected_ceiling = (1_000 / 1_000_000) * 0.15 + (250 / 1_000_000) * 0.60
    assert result["cost"] == pytest.approx(expected_ceiling)
    assert result["cost_estimated"] is True
    assert result["cost_estimate_reason"] == "provider_usage_cache_details_unavailable"


@pytest.mark.asyncio
async def test_openai_malformed_cache_details_use_observed_full_rate_and_flag_bound():
    class Completions:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="### SYNTHESIS:\nAnswer"),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=50_000,
                    completion_tokens=900,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=50_001),
                ),
            )

    result = await ExpertCouncil(
        synthesis_client=SimpleNamespace(chat=SimpleNamespace(completions=Completions())),
        synthesis_model="gpt-4o-mini",
        synthesis_provider="openai",
    )._synthesise("q", _perspectives(), budget=1.0)

    assert result["synthesis_status"] == "failed"
    assert result["synthesis_error_type"] == "SynthesisCostBoundViolation"
    assert result["cost"] == pytest.approx((50_000 / 1_000_000) * 0.15 + (900 / 1_000_000) * 0.60)
    assert result["cost_estimated"] is True
    assert result["cost_estimate_reason"] == "provider_usage_cache_details_invalid"
    assert result["cost_bound_exceeded"] is True
    assert set(result["cost_bound_violation"].split(",")) == {"input_tokens", "output_tokens", "cost_usd"}


@pytest.mark.asyncio
async def test_provider_usage_above_bound_records_actual_and_flags_result():
    class Completions:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                id="chatcmpl_over_bound",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="### SYNTHESIS:\nAnswer"),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(prompt_tokens=50_000, completion_tokens=900),
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    council = ExpertCouncil(
        synthesis_client=client,
        synthesis_model="gpt-5-mini",
        synthesis_provider="openai",
    )
    result = await council.consult(
        "How should bound violations surface?",
        experts=_stored_expert("Synthesis Bound Violation Expert"),
        budget=1.0,
    )

    events = CostLedger().get_events(source="expert_council.synthesis")
    expected_actual = (50_000 / 1_000_000) * 0.25 + (900 / 1_000_000) * 2.0
    assert result["synthesis_status"] == "failed"
    assert result["synthesis_error_type"] == "SynthesisCostBoundViolation"
    assert len(events) == 1
    assert events[0].cost_usd == expected_actual
    assert events[0].metadata["cost_bound_exceeded"] is True
    assert set(events[0].metadata["cost_bound_violation"].split(",")) == {
        "input_tokens",
        "output_tokens",
        "cost_usd",
    }


@pytest.mark.asyncio
async def test_default_openai_client_disables_sdk_retries(monkeypatch):
    class Completions:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="### SYNTHESIS:\nAnswer"))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    constructor = MagicMock(return_value=fake_client)
    monkeypatch.setattr("deepr.experts.council.AsyncOpenAI", constructor)

    await ExpertCouncil(synthesis_model="gpt-5-mini")._synthesise("q", _perspectives(), budget=1.0)

    assert constructor.call_args.kwargs["max_retries"] == 0


def test_default_anthropic_client_disables_sdk_retries():
    messages = object()
    sdk_client = SimpleNamespace(messages=messages)
    with patch("anthropic.AsyncAnthropic", return_value=sdk_client) as constructor:
        client = AnthropicConsultSynthesisClient(api_key="test-key")

        assert client.messages is messages

    constructor.assert_called_once_with(max_retries=0, api_key="test-key")
