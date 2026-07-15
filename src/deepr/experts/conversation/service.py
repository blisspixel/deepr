"""Protocol-neutral orchestration for durable expert conversations."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

from deepr.experts.conversation.models import (
    ConversationContinueRequest,
    ConversationError,
    ConversationExecutionContext,
    ConversationOperationResult,
    ConversationResumeRequest,
    ConversationStartRequest,
    ErrorCode,
    TurnExecutionResult,
    TurnLease,
    TurnState,
    TurnUsage,
)
from deepr.experts.conversation.store import ExpertConversationStore


class ExpertConversationTurnExecutor(Protocol):
    """One injected bounded turn executor.

    Implementations may call the existing one-shot consult transaction, but the
    Stage 1 core tests use fakes and never construct a model provider.
    """

    async def execute(self, context: ConversationExecutionContext) -> TurnExecutionResult:
        """Execute one already-reserved attempt."""
        ...


class ExpertConversationService:
    """Serialize durable state around an injected executor factory."""

    def __init__(
        self,
        store: ExpertConversationStore,
        executor_factory: Callable[[], ExpertConversationTurnExecutor],
    ) -> None:
        self.store = store
        self._executor_factory = executor_factory

    async def start(self, request: ConversationStartRequest) -> ConversationOperationResult:
        lease = await asyncio.to_thread(self.store.reserve_start, request)
        return await self._dispatch(request.owner_id, lease)

    async def continue_conversation(self, request: ConversationContinueRequest) -> ConversationOperationResult:
        lease = await asyncio.to_thread(self.store.reserve_continue, request)
        return await self._dispatch(request.owner_id, lease)

    async def resume(self, request: ConversationResumeRequest) -> ConversationOperationResult:
        lease = await asyncio.to_thread(self.store.reserve_resume, request)
        return await self._dispatch(request.owner_id, lease)

    async def get(
        self,
        *,
        owner_id: str,
        conversation_id: str,
        turn_id: str | None = None,
    ) -> ConversationOperationResult:
        return await asyncio.to_thread(
            self.store.get,
            owner_id=owner_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
        )

    async def close(
        self,
        *,
        owner_id: str,
        conversation_id: str,
        expected_version: int,
    ) -> ConversationOperationResult:
        return await asyncio.to_thread(
            self.store.close_conversation,
            owner_id=owner_id,
            conversation_id=conversation_id,
            expected_version=expected_version,
        )

    async def delete_content(
        self,
        *,
        owner_id: str,
        conversation_id: str,
        expected_version: int,
    ) -> ConversationOperationResult:
        return await asyncio.to_thread(
            self.store.delete_content,
            owner_id=owner_id,
            conversation_id=conversation_id,
            expected_version=expected_version,
        )

    async def recover(self) -> int:
        return await asyncio.to_thread(self.store.recover_expired_leases)

    async def expire_due(self) -> int:
        return await asyncio.to_thread(self.store.expire_due)

    async def _dispatch(self, owner_id: str, lease: TurnLease) -> ConversationOperationResult:
        if not lease.dispatch_required:
            return await asyncio.to_thread(
                self.store.get,
                owner_id=owner_id,
                conversation_id=lease.conversation_id,
                turn_id=lease.turn_id,
                replayed=True,
            )
        context = lease.execution_context
        if context is None:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Reserved turn is missing its execution context.")

        remaining_ms = max(1, int(context.remaining["elapsed_ms"]))
        started = time.monotonic()
        executor_invoked = False
        try:
            async with asyncio.timeout(remaining_ms / 1000):
                executor = await asyncio.to_thread(self._executor_factory)
                executor_invoked = True
                result = await executor.execute(context)
                if not isinstance(result, TurnExecutionResult):
                    raise TypeError("executor returned an invalid result")
                if result.artifact is not None and not set(result.artifact["experts_consulted"]).issubset(
                    context.expert_names
                ):
                    raise ValueError("executor referenced an unpinned expert")
        except asyncio.CancelledError:
            usage = _failure_usage(started, remaining_ms=remaining_ms, model_call_ambiguous=executor_invoked)
            await _finish_durable_call(self.store.record_executor_failure, lease, cancelled=True, usage=usage)
            raise
        except TimeoutError:
            usage = TurnUsage(model_calls=int(executor_invoked), elapsed_ms=remaining_ms)
            return await asyncio.to_thread(
                self.store.finalize_turn,
                lease,
                TurnExecutionResult(
                    state=TurnState.BUDGET_EXHAUSTED,
                    stop_reason=TurnState.BUDGET_EXHAUSTED.value,
                    retryable=False,
                    usage=usage,
                ),
            )
        except Exception:
            # Raw backend exception text is intentionally not copied into the
            # public error, audit event, or durable turn artifact.
            usage = _failure_usage(started, remaining_ms=remaining_ms, model_call_ambiguous=executor_invoked)
            return await asyncio.to_thread(self.store.record_executor_failure, lease, usage=usage)

        elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
        if elapsed_ms >= remaining_ms:
            result = TurnExecutionResult(
                state=TurnState.BUDGET_EXHAUSTED,
                stop_reason=TurnState.BUDGET_EXHAUSTED.value,
                retryable=False,
                usage=replace(result.usage, elapsed_ms=max(result.usage.elapsed_ms, remaining_ms)),
                consult_trace_id=result.consult_trace_id,
                consult_lifecycle_trace_id=result.consult_lifecycle_trace_id,
            )
        measured_ms = min(remaining_ms, elapsed_ms)
        if measured_ms > result.usage.elapsed_ms:
            result = replace(result, usage=replace(result.usage, elapsed_ms=measured_ms))
        return await asyncio.to_thread(self.store.finalize_turn, lease, result)


async def _finish_durable_call(function: Callable[..., object], *args: object, **kwargs: object) -> object:
    """Own a final durable write even when the parent task is cancelled."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


def _failure_usage(started: float, *, remaining_ms: int, model_call_ambiguous: bool) -> TurnUsage:
    measured_ms = min(remaining_ms, max(0, int((time.monotonic() - started) * 1000)))
    return TurnUsage(model_calls=int(model_call_ambiguous), elapsed_ms=measured_ms)
