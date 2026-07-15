"""Orchestration tests for the injected durable conversation service."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest

from deepr.experts.conversation.models import (
    BackendSelection,
    ConsultationMode,
    ConversationBounds,
    ConversationBusy,
    ConversationContinueRequest,
    ConversationExecutionContext,
    ConversationOperationResult,
    ConversationResumeRequest,
    ConversationStartRequest,
    ExpertSnapshotInput,
    TurnExecutionResult,
    TurnLease,
    TurnUsage,
)
from deepr.experts.conversation.service import ExpertConversationService
from deepr.experts.conversation.store import ExpertConversationStore
from tests.unit.conversation_fixtures import CompletingExecutor, completed_result, start_request


@pytest.mark.asyncio
async def test_factory_is_constructed_only_after_durable_running_state(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    observed: list[tuple[str, str]] = []
    executor = CompletingExecutor()

    def factory() -> CompletingExecutor:
        with store._reader() as connection:
            row = connection.execute("SELECT state, current_turn_id FROM conversations").fetchone()
        observed.append((str(row["state"]), str(row["current_turn_id"])))
        return executor

    result = await ExpertConversationService(store, factory).start(start_request())

    assert observed == [("open", result.turn["turn_id"])]
    assert result.turn["state"] == "completed"
    assert len(executor.contexts) == 1


@pytest.mark.asyncio
async def test_duplicate_delivery_does_not_construct_or_dispatch_again(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    constructions = 0
    executor = CompletingExecutor()

    def factory() -> CompletingExecutor:
        nonlocal constructions
        constructions += 1
        return executor

    service = ExpertConversationService(store, factory)
    request = start_request()
    first = await service.start(request)
    replay = await service.start(request)

    assert constructions == 1
    assert len(executor.contexts) == 1
    assert replay.replayed is True
    assert replay.conversation == first.conversation
    assert replay.turn == first.turn


@pytest.mark.asyncio
async def test_executor_exception_is_redacted_and_durable(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")

    class FailingExecutor:
        async def execute(self, _context: ConversationExecutionContext) -> TurnExecutionResult:
            raise RuntimeError("secret-token and local path C:/private")

    result = await ExpertConversationService(store, FailingExecutor).start(start_request())
    events = store.list_events(owner_id="owner-a", conversation_id=result.conversation["conversation_id"])

    assert result.conversation["state"] == "failed"
    assert result.turn["state"] == "failed"
    assert result.conversation["usage"]["model_calls"] == 1
    serialized = str(result.to_dict()) + str(events)
    assert "secret-token" not in serialized
    assert "C:/private" not in serialized


@pytest.mark.asyncio
async def test_cancellation_records_terminal_state_before_propagating(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    entered = asyncio.Event()

    class BlockingExecutor:
        async def execute(self, _context: ConversationExecutionContext) -> TurnExecutionResult:
            entered.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    service = ExpertConversationService(store, BlockingExecutor)
    task = asyncio.create_task(service.start(start_request()))
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    with store._reader() as connection:
        conversation_id = str(connection.execute("SELECT conversation_id FROM conversations").fetchone()[0])
    state = store.get(owner_id="owner-a", conversation_id=conversation_id)
    assert state.conversation["state"] == "cancelled"
    assert state.turn["state"] == "cancelled"
    assert state.conversation["usage"]["model_calls"] == 1


@pytest.mark.asyncio
async def test_executor_factory_is_inside_elapsed_deadline() -> None:
    context = ConversationExecutionContext(
        conversation_id="conv_" + "a" * 32,
        turn_id="turn_" + "b" * 32,
        attempt_id="attempt_" + "c" * 32,
        mode=ConsultationMode.FOCUSED,
        expert_names=("expert",),
        message="question",
        decision_brief=None,
        context_snapshot={},
        recent_turns=(),
        decision_ledger={},
        context_bytes=100,
        context_sha256="d" * 64,
        bounds=ConversationBounds(),
        remaining={
            "turns": 1,
            "model_calls": 1,
            "input_tokens": 1,
            "output_tokens": 1,
            "elapsed_ms": 5,
            "cost_usd": 0.0,
        },
    )
    lease = TurnLease(context.conversation_id, context.turn_id, context.attempt_id, 1, True, False, context)

    class FakeStore:
        def __init__(self) -> None:
            self.finalized: TurnExecutionResult | None = None

        def finalize_turn(
            self,
            _lease: TurnLease,
            result: TurnExecutionResult,
        ) -> ConversationOperationResult:
            self.finalized = result
            return ConversationOperationResult({}, None, dispatch_status=result.state.value)

    fake = FakeStore()

    def slow_factory() -> CompletingExecutor:
        time.sleep(0.05)
        return CompletingExecutor()

    service = ExpertConversationService(cast(ExpertConversationStore, fake), slow_factory)
    result = await service._dispatch("owner", lease)

    assert fake.finalized is not None
    assert fake.finalized.state.value == "budget_exhausted"
    assert fake.finalized.usage.elapsed_ms == 5
    assert result.dispatch_status == "budget_exhausted"


@pytest.mark.asyncio
async def test_different_conversations_execute_in_parallel(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    all_entered = asyncio.Event()
    release = asyncio.Event()
    active = 0
    maximum_active = 0

    class ParallelExecutor:
        async def execute(self, _context: ConversationExecutionContext) -> TurnExecutionResult:
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            if active == 2:
                all_entered.set()
            await asyncio.wait_for(release.wait(), timeout=2)
            active -= 1
            return completed_result()

    service = ExpertConversationService(store, ParallelExecutor)
    first = asyncio.create_task(service.start(start_request(idempotency_key="parallel-1", message="first")))
    second = asyncio.create_task(service.start(start_request(idempotency_key="parallel-2", message="second")))
    await asyncio.wait_for(all_entered.wait(), timeout=2)
    release.set()
    results = await asyncio.gather(first, second)

    assert maximum_active == 2
    assert len({result.conversation["conversation_id"] for result in results}) == 2
    assert all(result.turn["state"] == "completed" for result in results)


@pytest.mark.asyncio
async def test_same_conversation_cannot_dispatch_overlapping_turns(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    initial = await ExpertConversationService(store, CompletingExecutor).start(start_request())
    entered = asyncio.Event()
    release = asyncio.Event()
    constructions = 0

    class BlockingExecutor:
        async def execute(self, _context: ConversationExecutionContext) -> TurnExecutionResult:
            entered.set()
            await release.wait()
            return completed_result()

    def factory() -> BlockingExecutor:
        nonlocal constructions
        constructions += 1
        return BlockingExecutor()

    service = ExpertConversationService(store, factory)
    conversation_id = initial.conversation["conversation_id"]
    first = asyncio.create_task(
        service.continue_conversation(ConversationContinueRequest("owner-a", conversation_id, 2, "overlap-1", "first"))
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    running = await service.get(owner_id="owner-a", conversation_id=conversation_id)

    with pytest.raises(ConversationBusy):
        await service.continue_conversation(
            ConversationContinueRequest(
                "owner-a",
                conversation_id,
                running.conversation["version"],
                "overlap-2",
                "second",
            )
        )

    release.set()
    await first
    assert constructions == 1


@pytest.mark.asyncio
async def test_factory_runs_off_event_loop_thread(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    loop_thread = threading.get_ident()
    factory_threads: list[int] = []

    def factory() -> CompletingExecutor:
        factory_threads.append(threading.get_ident())
        return CompletingExecutor()

    await ExpertConversationService(store, factory).start(start_request())
    assert factory_threads and factory_threads[0] != loop_thread


@pytest.mark.asyncio
async def test_invalid_executor_result_fails_closed(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")

    class InvalidExecutor:
        async def execute(self, _context: ConversationExecutionContext) -> Any:
            return {"state": "completed"}

    result = await ExpertConversationService(store, InvalidExecutor).start(start_request())

    assert result.conversation["state"] == "failed"
    assert result.turn["state"] == "failed"
    assert result.conversation["usage"]["model_calls"] == 1


@pytest.mark.asyncio
async def test_executor_cannot_attribute_answer_to_unpinned_expert(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")

    class WrongRosterExecutor:
        async def execute(self, _context: ConversationExecutionContext) -> TurnExecutionResult:
            artifact = completed_result().artifact
            assert artifact is not None
            artifact["experts_consulted"] = ["untrusted_expert"]
            artifact["evidence"][0]["expert_name"] = "untrusted_expert"
            artifact["dissent"][0]["expert_names"] = ["untrusted_expert"]
            return TurnExecutionResult.completed(artifact, usage=TurnUsage(model_calls=1))

    result = await ExpertConversationService(store, WrongRosterExecutor).start(start_request())

    assert result.conversation["state"] == "failed"
    assert result.turn["artifact"] is None


@pytest.mark.asyncio
async def test_service_accounts_for_measured_executor_elapsed_time(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")

    class SlowReportingExecutor:
        async def execute(self, _context: ConversationExecutionContext) -> TurnExecutionResult:
            await asyncio.sleep(0.02)
            return completed_result(usage=TurnUsage(model_calls=1, elapsed_ms=0))

    result = await ExpertConversationService(store, SlowReportingExecutor).start(start_request())

    assert result.turn["state"] == "completed"
    assert result.turn["capacity"]["turn"]["elapsed_ms"] >= 10


@pytest.mark.asyncio
async def test_service_lifecycle_methods_share_the_durable_core(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    executors: list[Any] = []

    class WaitingExecutor:
        async def execute(self, _context: ConversationExecutionContext) -> TurnExecutionResult:
            return TurnExecutionResult.waiting_capacity()

    def factory() -> Any:
        return executors.pop(0)

    executors.extend([WaitingExecutor(), CompletingExecutor()])
    service = ExpertConversationService(store, factory)
    waiting = await service.start(start_request())
    resumed = await service.resume(
        ConversationResumeRequest(
            "owner-a",
            waiting.conversation["conversation_id"],
            waiting.conversation["version"],
            "service-resume",
        )
    )
    inspected = await service.get(owner_id="owner-a", conversation_id=resumed.conversation["conversation_id"])
    closed = await service.close(
        owner_id="owner-a",
        conversation_id=resumed.conversation["conversation_id"],
        expected_version=resumed.conversation["version"],
    )
    deleted = await service.delete_content(
        owner_id="owner-a",
        conversation_id=closed.conversation["conversation_id"],
        expected_version=closed.conversation["version"],
    )

    assert inspected.turn["state"] == "completed"
    assert deleted.conversation["retention"]["content_deleted"] is True
    assert await service.recover() == 0
    assert await service.expire_due() == 0
