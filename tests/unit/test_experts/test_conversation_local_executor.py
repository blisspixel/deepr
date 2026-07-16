"""Tests for bounded local Ollama conversation turns."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from deepr.experts.chat_backends import ExpertChatRequest, ExpertChatResult
from deepr.experts.conversation.local_executor import LocalOllamaConversationExecutor
from deepr.experts.conversation.models import (
    HOST_ACTION_BOUNDARY,
    BackendSelection,
    ConsultationMode,
    ConversationBounds,
    ConversationExecutionContext,
    TurnState,
)


def _artifact(*, semantic_status: str = "answered", evidence_ref: str = "caller:turn_" + "b" * 32) -> dict[str, Any]:
    return {
        "direct_answer": "Keep the operation bounded and idempotent.",
        "experts_consulted": ["model-invented-expert"],
        "assumptions": [{"text": "The host owns downstream action.", "source": "host_supplied"}],
        "evidence": [
            {
                "evidence_ref": evidence_ref,
                "source_type": "caller_supplied",
                "expert_name": None,
                "citation": None,
            }
        ],
        "uncertainty": {
            "kind": "qualitative",
            "value": "low",
            "rationale": "The runtime contract is explicit.",
        },
        "agreements": [],
        "dissent": [],
        "decision_implications": [{"proposal": "Validate restart recovery.", "authority": "proposal_only"}],
        "change_conditions": ["A restart loses the recorded turn."],
        "unresolved_gaps": [],
        "recommended_next_question": "Which failure should be injected next?",
        "semantic_status": semantic_status,
        "host_action_boundary": "model attempted to widen authority",
    }


def _context(
    *,
    backend: BackendSelection | None = None,
    input_tokens: int = 200_000,
    output_tokens: int = 20_000,
) -> ConversationExecutionContext:
    return ConversationExecutionContext(
        conversation_id="conv_" + "a" * 32,
        turn_id="turn_" + "b" * 32,
        attempt_id="attempt_" + "c" * 32,
        mode=ConsultationMode.FOCUSED,
        expert_names=("reliability",),
        backend=backend or BackendSelection.local("fixture-model"),
        message="How should this be made reliable?",
        decision_brief="Decide whether the service is safe to expose.",
        context_snapshot={
            "snapshot_id": "snap_" + "d" * 32,
            "snapshot_sha256": "e" * 64,
            "expert_snapshots": [],
        },
        recent_turns=(),
        decision_ledger={},
        context_bytes=100,
        context_sha256="f" * 64,
        bounds=ConversationBounds(),
        remaining={
            "turns": 20,
            "model_calls": 40,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "elapsed_ms": 300_000,
            "cost_usd": 0.0,
        },
    )


class FakeBackend:
    provider = "local"
    model = "fixture-model"
    metered = False
    supports_tools = False
    supports_streaming = False
    supports_prompt_cache = False

    def __init__(
        self,
        payload: dict[str, Any] | str,
        *,
        stop_reason: str = "stop",
        usage: Any | None = None,
    ) -> None:
        self.payload = payload
        self.stop_reason = stop_reason
        self.usage = usage
        self.requests: list[ExpertChatRequest] = []

    async def complete(self, request: ExpertChatRequest) -> ExpertChatResult:
        self.requests.append(request)
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return ExpertChatResult(
            message=SimpleNamespace(content=text),
            usage=self.usage,
            stop_reason=self.stop_reason,
        )

    def stream(self, request: ExpertChatRequest):
        raise AssertionError("streaming is not allowed")


@pytest.mark.asyncio
async def test_completed_turn_pins_roster_authority_and_zero_cost() -> None:
    backend = FakeBackend(
        _artifact(),
        usage=SimpleNamespace(prompt_tokens=321, completion_tokens=123),
    )
    result = await LocalOllamaConversationExecutor(lambda _model: backend).execute(_context())

    assert result.state is TurnState.COMPLETED
    assert result.artifact is not None
    assert result.artifact["experts_consulted"] == ["reliability"]
    assert result.artifact["host_action_boundary"] == HOST_ACTION_BOUNDARY
    assert result.usage.model_calls == 1
    assert result.usage.input_tokens == 321
    assert result.usage.output_tokens == 123
    assert result.usage.cost_usd == 0.0
    assert backend.requests[0].tools is None
    assert backend.requests[0].extra["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_input_required_status_maps_to_resumable_turn() -> None:
    backend = FakeBackend(_artifact(semantic_status="input_required"))

    result = await LocalOllamaConversationExecutor(lambda _model: backend).execute(_context())

    assert result.state is TurnState.INPUT_REQUIRED
    assert result.retryable is True
    assert result.stop_reason == "input_required"


@pytest.mark.asyncio
async def test_unknown_evidence_reference_fails_closed() -> None:
    backend = FakeBackend(_artifact(evidence_ref="invented-reference"))

    result = await LocalOllamaConversationExecutor(lambda _model: backend).execute(_context())

    assert result.state is TurnState.VERIFIER_FAILED
    assert result.artifact is None
    assert result.usage.model_calls == 1


@pytest.mark.asyncio
async def test_invalid_json_and_output_limit_fail_closed() -> None:
    invalid = FakeBackend("not-json")
    limited = FakeBackend(_artifact(), stop_reason="length")

    invalid_result = await LocalOllamaConversationExecutor(lambda _model: invalid).execute(_context())
    limited_result = await LocalOllamaConversationExecutor(lambda _model: limited).execute(_context())

    assert invalid_result.state is TurnState.VERIFIER_FAILED
    assert limited_result.state is TurnState.VERIFIER_FAILED


@pytest.mark.asyncio
async def test_missing_provider_usage_is_conservatively_nonzero() -> None:
    backend = FakeBackend(_artifact())

    result = await LocalOllamaConversationExecutor(lambda _model: backend).execute(_context())

    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens >= len(json.dumps(_artifact()))


@pytest.mark.asyncio
async def test_input_capacity_rejects_before_backend_construction() -> None:
    constructed = False

    def factory(_model: str) -> FakeBackend:
        nonlocal constructed
        constructed = True
        return FakeBackend(_artifact())

    result = await LocalOllamaConversationExecutor(factory).execute(_context(input_tokens=1))

    assert result.state is TurnState.BUDGET_EXHAUSTED
    assert result.usage.model_calls == 0
    assert constructed is False


@pytest.mark.asyncio
async def test_nonlocal_backend_is_rejected_without_construction() -> None:
    executor = LocalOllamaConversationExecutor(lambda _model: FakeBackend(_artifact()))
    nonlocal_backend = BackendSelection(
        capacity_source="metered_api",
        backend_class="api",
        model="forbidden",
    )

    with pytest.raises(ValueError, match="local owned"):
        await executor.execute(_context(backend=nonlocal_backend))
