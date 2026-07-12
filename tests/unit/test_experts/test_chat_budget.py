"""ExpertChatSession budget handling (no-surprise-bills).

Regression for a live-hunt finding (2026-06-14): `budget or 10.0` silently
turned an explicit budget=0.0 ("do not spend") into a $10 ceiling, because 0.0
is falsy. An agent or `--budget 0` caller meaning no spend got a real budget.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.experts.chat import ExpertChatSession
from deepr.experts.chat_backends import ExpertChatResult, ExpertChatStreamChunk
from deepr.experts.chat_capacity import MeteredExpertChatDisabledError
from deepr.experts.cost_safety import CostSafetyManager, reset_cost_safety_manager
from deepr.experts.profile import ExpertProfile
from deepr.observability.cost_ledger import CostLedger


def _session(monkeypatch, budget):
    reset_cost_safety_manager()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    expert = ExpertProfile(name="Budget Probe", vector_store_id="vs-x", domain="ai")
    return ExpertChatSession(expert, budget=budget, enable_router=False)


class RecordingChatBackend:
    provider = "openai"
    model = "gpt-5.2"
    metered = False
    supports_tools = True
    supports_streaming = True
    supports_prompt_cache = True

    def __init__(self, *contents) -> None:
        self.requests = []
        self.stream_requests = []
        self.stream_chunks = []
        self._contents = list(contents)

    async def complete(self, request):
        self.requests.append(request)
        content = self._contents.pop(0) if self._contents else "backend answer"
        return ExpertChatResult(
            message=SimpleNamespace(content=content, tool_calls=[]),
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )

    async def stream(self, request):
        self.stream_requests.append(request)
        for chunk in self.stream_chunks:
            yield chunk


class RecordingNoToolChatBackend(RecordingChatBackend):
    provider = "anthropic"
    model = "claude-sonnet-4-6"
    supports_tools = False
    supports_streaming = False
    supports_prompt_cache = False

    async def complete(self, request):
        self.requests.append(request)
        content = self._contents.pop(0) if self._contents else "anthropic answer"
        return ExpertChatResult(
            message=SimpleNamespace(content=content, tool_calls=[]),
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=20,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )


def test_unspecified_budget_defaults_to_ten(monkeypatch):
    assert _session(monkeypatch, None).budget == 10.0


def test_explicit_zero_budget_is_honored_not_coerced_to_default(monkeypatch):
    # budget=0.0 means "do not spend" - it must NOT become $10.
    assert _session(monkeypatch, 0.0).budget == 0.0


def test_positive_budget_passes_through(monkeypatch):
    assert _session(monkeypatch, 3.5).budget == 3.5


def test_session_circuit_breaker_blocks_manager_operations(monkeypatch):
    session = _session(monkeypatch, 1.0)

    for index in range(5):
        session.cost_safety.record_failure(session.session_id, "standard_research", f"failure-{index}")

    allowed, reason, needs_confirmation = session.cost_safety.check_operation(
        session_id=session.session_id,
        operation_type="standard_research",
        estimated_cost=0.002,
        require_confirmation=False,
    )

    assert allowed is False
    assert needs_confirmation is False
    assert reason.startswith("Session circuit breaker open: Too many failures")
    assert session.get_session_summary()["circuit_breaker_open"] is True


async def test_standard_research_fails_closed_before_any_provider_or_fallback(monkeypatch):
    session = _session(monkeypatch, 1.0)
    session.chat_backend = RecordingChatBackend("fallback must not dispatch")

    with pytest.raises(MeteredExpertChatDisabledError) as exc_info:
        await session._standard_research("latest ai news")

    assert exc_info.value.operation == "expert_chat_standard_research"
    assert exc_info.value.provider_work_dispatched is False
    assert session.chat_backend.requests == []
    assert session.cost_accumulated == 0.0


async def test_successful_research_document_write_advances_both_freshness_fields(monkeypatch):
    from deepr.experts.profile import ExpertStore

    session = _session(monkeypatch, 1.0)
    session.chat_backend = RecordingChatBackend()
    session.client.files.create = AsyncMock(return_value=SimpleNamespace(id="file-1"))
    session.client.vector_stores.files.create = AsyncMock(return_value=None)

    written = await session._add_research_to_knowledge_base(
        "What changed in the test domain?",
        "A verified research answer.",
        "standard_research",
    )

    assert written is True
    assert session.expert.knowledge_cutoff_date is not None
    assert session.expert.last_knowledge_refresh == session.expert.knowledge_cutoff_date
    loaded = ExpertStore().load(session.expert.name)
    assert loaded is not None
    assert loaded.knowledge_cutoff_date == session.expert.knowledge_cutoff_date


async def test_quick_lookup_uses_chat_backend(monkeypatch):
    session = _session(monkeypatch, 1.0)

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("legacy client should be behind chat_backend")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)
    backend = RecordingChatBackend("fresh cached answer")
    session.chat_backend = backend

    result = await session._quick_lookup("what changed in ai regulation?")

    assert result["answer"] == "fresh cached answer"
    assert result["mode"] == "quick_lookup_gpt52"
    assert len(backend.requests) == 1
    assert backend.requests[0].model == "gpt-5.5"
    assert backend.requests[0].reasoning_effort == "low"


async def test_standard_research_does_not_reach_owned_fallback_after_metered_gate(monkeypatch):
    session = _session(monkeypatch, 1.0)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("legacy client should be behind chat_backend")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)
    backend = RecordingChatBackend("fallback answer")
    session.chat_backend = backend

    with pytest.raises(MeteredExpertChatDisabledError):
        await session._standard_research("latest ai infrastructure funding")

    assert backend.requests == []


async def test_deep_research_fails_closed_before_provider_dispatch(monkeypatch):
    session = _session(monkeypatch, 0.0)

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("deep research provider call should not run after budget denial")

    monkeypatch.setattr(session.client.responses, "create", fail_if_called)
    monkeypatch.setattr(CostSafetyManager, "ABSOLUTE_MAX_PER_OPERATION", 10.0)

    with pytest.raises(MeteredExpertChatDisabledError) as exc_info:
        await session._deep_research("design a migration strategy")

    assert exc_info.value.operation == "expert_chat_deep_research"
    assert exc_info.value.provider_work_dispatched is False


async def test_metered_chat_generation_is_gated_before_budget_or_provider(monkeypatch):
    session = _session(monkeypatch, 0.0)
    session.should_use_tot = lambda _query: False

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("chat provider call should not run after budget denial")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)

    with pytest.raises(MeteredExpertChatDisabledError) as exc_info:
        await session.send_message("What should this expert improve next?")

    assert exc_info.value.operation == "expert_chat_turn"
    assert exc_info.value.to_dict()["status"] == "blocked"
    assert session.reasoning_trace == []


async def test_first_chat_generation_uses_chat_backend(monkeypatch):
    session = _session(monkeypatch, 1.0)
    session.should_use_tot = lambda _query: False

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("legacy client should be behind chat_backend")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)
    backend = RecordingChatBackend("backend answer")
    session.chat_backend = backend

    result = await session.send_message("What should this expert improve next?")

    assert result == "backend answer"
    assert len(backend.requests) == 1
    assert backend.requests[0].model == session.expert.model
    assert backend.requests[0].tool_choice == "auto"
    assert backend.requests[0].messages[0]["role"] == "system"


async def test_provider_exception_sets_typed_terminal_failure_state(monkeypatch):
    session = _session(monkeypatch, 1.0)
    session.should_use_tot = lambda _query: False

    class FailingBackend(RecordingChatBackend):
        async def complete(self, request):
            self.requests.append(request)
            raise RuntimeError("ambiguous provider failure")

    session.chat_backend = FailingBackend()

    result = await session.send_message("What should this expert improve next?")

    assert result.startswith("Error communicating with expert:")
    assert session.last_turn_failed is True


async def test_streaming_provider_exception_sets_typed_terminal_failure_state(monkeypatch):
    session = _session(monkeypatch, 1.0)
    session.should_use_tot = lambda _query: False

    class FailingBackend(RecordingChatBackend):
        async def complete(self, request):
            self.requests.append(request)
            raise RuntimeError("ambiguous provider failure")

    session.chat_backend = FailingBackend()

    result = await session.send_message_streaming("What should this expert improve next?")

    assert result.startswith("Error communicating with expert:")
    assert session.last_turn_failed is True


async def test_owned_no_tool_chat_omits_tools_and_stays_zero_cost(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-not-real")

    class FakeAsyncAnthropic:
        def __init__(self, *, api_key, max_retries):
            assert api_key == "anthropic-test-not-real"
            assert max_retries == 0

    monkeypatch.setattr("deepr.experts.chat_api_backends.AsyncAnthropic", FakeAsyncAnthropic)
    reset_cost_safety_manager()
    expert = ExpertProfile(name="Anthropic Probe", vector_store_id="vs-x", domain="ai")
    session = ExpertChatSession(
        expert,
        budget=1.0,
        agentic=False,
        provider="anthropic",
        model="claude-sonnet-4-6",
    )
    session.should_use_tot = lambda _query: False
    backend = RecordingNoToolChatBackend("anthropic answer")
    session.chat_backend = backend

    result = await session.send_message("What should this expert improve next?")

    assert result == "anthropic answer"
    assert len(backend.requests) == 1
    assert backend.requests[0].model == "claude-sonnet-4-6"
    assert backend.requests[0].tools is None
    assert backend.requests[0].tool_choice is None
    assert session.cost_accumulated == 0.0


async def test_anthropic_no_tool_chat_handles_complex_question_without_tool_round(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-not-real")
    monkeypatch.setattr("deepr.experts.chat_api_backends.AsyncAnthropic", lambda **_kwargs: SimpleNamespace())
    reset_cost_safety_manager()
    expert = ExpertProfile(name="Anthropic Probe", vector_store_id="vs-x", domain="ai")
    session = ExpertChatSession(
        expert,
        budget=1.0,
        agentic=False,
        provider="anthropic",
        model="claude-sonnet-4-6",
    )
    backend = RecordingNoToolChatBackend("complex answer")
    session.chat_backend = backend

    result = await session.send_message("Analyze the tradeoffs in this multi-step AI governance plan.")

    assert result == "complex answer"
    assert len(backend.requests) == 1
    assert backend.requests[0].tools is None


async def test_anthropic_agentic_chat_is_rejected(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-not-real")
    monkeypatch.setattr("deepr.experts.chat_api_backends.AsyncAnthropic", lambda **_kwargs: SimpleNamespace())
    reset_cost_safety_manager()
    expert = ExpertProfile(name="Anthropic Probe", vector_store_id="vs-x", domain="ai")

    try:
        ExpertChatSession(expert, budget=1.0, agentic=True, provider="anthropic")
    except ValueError as exc:
        assert "non-agentic only" in str(exc)
    else:
        raise AssertionError("Anthropic agentic chat should be rejected")


async def test_follow_up_generation_uses_chat_backend(monkeypatch):
    session = _session(monkeypatch, 1.0)

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("legacy client should be behind chat_backend")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)
    backend = RecordingChatBackend('["What evidence matters next?", "How should we validate this?"]')
    session.chat_backend = backend
    reserve = MagicMock(side_effect=AssertionError("owned calls must not reserve dollars"))
    record = MagicMock(side_effect=AssertionError("owned calls must not record dollar spend"))
    monkeypatch.setattr(session.cost_safety, "check_and_reserve", reserve)
    monkeypatch.setattr(session.cost_safety, "record_cost", record)

    follow_ups = await session._generate_follow_ups("What changed?", "The backend seam changed.")

    assert follow_ups == ["What evidence matters next?", "How should we validate this?"]
    assert len(backend.requests) == 1
    assert backend.requests[0].model == "gpt-4o-mini"
    assert backend.requests[0].extra == {"temperature": 0.7, "max_tokens": 200}
    reserve.assert_not_called()
    record.assert_not_called()
    assert session.cost_accumulated == 0.0


async def test_owned_follow_up_generation_ignores_dollar_budget(monkeypatch):
    session = _session(monkeypatch, 0.005)
    backend = RecordingChatBackend('["This must not dispatch"]')
    session.chat_backend = backend

    follow_ups = await session._generate_follow_ups("What changed?", "The backend seam changed.")

    assert follow_ups == ["This must not dispatch"]
    assert len(backend.requests) == 1
    assert session.cost_accumulated == 0.0


async def test_owned_follow_up_provider_failure_records_no_dollar_cost(monkeypatch):
    session = _session(monkeypatch, 1.0)

    class FailingBackend(RecordingChatBackend):
        async def complete(self, request):
            self.requests.append(request)
            raise RuntimeError("ambiguous provider failure")

    session.chat_backend = FailingBackend()
    record = MagicMock(wraps=session.cost_safety.record_cost)
    monkeypatch.setattr(session.cost_safety, "record_cost", record)

    follow_ups = await session._generate_follow_ups("What changed?", "The backend seam changed.")

    assert follow_ups == []
    assert len(session.chat_backend.requests) == 1
    record.assert_not_called()
    assert session.cost_accumulated == 0.0


async def test_compact_conversation_uses_chat_backend(monkeypatch):
    session = _session(monkeypatch, 1.0)
    session.messages = [
        {"role": "user", "content": f"question {index}"}
        if index % 2 == 0
        else {"role": "assistant", "content": f"answer {index}"}
        for index in range(8)
    ]

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("legacy client should be behind chat_backend")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)
    backend = RecordingChatBackend("KEY_FACTS: migrated support calls")
    session.chat_backend = backend

    result = await session.compact_conversation()

    assert result["status"] == "compacted"
    assert result["original_messages"] == 8
    assert len(backend.requests) == 1
    assert backend.requests[0].model == "gpt-4o-mini"
    assert backend.requests[0].extra == {"temperature": 0.3, "max_tokens": 500}
    assert session.messages[0]["role"] == "system"
    assert "KEY_FACTS: migrated support calls" in session.messages[0]["content"]


async def test_metered_streaming_chat_is_gated_before_budget_or_provider(monkeypatch):
    session = _session(monkeypatch, 0.0)
    session.should_use_tot = lambda _query: False

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("streaming chat provider call should not run after budget denial")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)

    with pytest.raises(MeteredExpertChatDisabledError) as exc_info:
        await session.send_message_streaming("What should this expert improve next?")

    assert exc_info.value.operation == "expert_chat_streaming_turn"
    assert session.reasoning_trace == []


async def test_streaming_first_chat_generation_uses_chat_backend(monkeypatch):
    session = _session(monkeypatch, 1.0)
    session.should_use_tot = lambda _query: False
    emitted = []

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("legacy client should be behind chat_backend before final streaming")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)
    backend = RecordingChatBackend("backend stream answer", "[]")
    session.chat_backend = backend

    result = await session.send_message_streaming(
        "What should this expert improve next?",
        token_callback=emitted.append,
    )

    assert result == "backend stream answer"
    assert "".join(emitted) == "backend stream answer"
    assert backend.requests[0].model == session.expert.model
    assert backend.requests[0].tool_choice == "auto"


async def test_streaming_final_response_accounts_stream_usage(monkeypatch):
    session = _session(monkeypatch, 1.0)
    session.should_use_tot = lambda _query: False
    accounted = []
    emitted = []

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("final streaming should run through chat_backend.stream")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)
    session._account_chat_cost = lambda usage, model: accounted.append(usage)
    backend = RecordingChatBackend(None, "[]")
    backend.stream_chunks = [
        ExpertChatStreamChunk(text_delta="hello"),
        ExpertChatStreamChunk(usage=SimpleNamespace(prompt_tokens=20, completion_tokens=7)),
    ]
    session.chat_backend = backend

    result = await session.send_message_streaming(
        "Stream a final answer",
        token_callback=emitted.append,
    )

    assert result == "hello"
    assert emitted == ["hello"]
    assert len(backend.stream_requests) == 1
    assert backend.stream_requests[0].model == session.expert.model
    assert [(u.prompt_tokens, u.completion_tokens) for u in accounted] == [(20, 7), (10, 5)]


async def test_concurrent_metered_turns_make_zero_provider_calls_and_zero_ledger_writes(monkeypatch):
    session = _session(monkeypatch, 1.0)
    session.should_use_tot = lambda _query: False
    backend = RecordingChatBackend("first", "second")
    backend.metered = True
    session.chat_backend = backend
    ledger_before = CostLedger().get_events()
    record = MagicMock(side_effect=AssertionError("metered chat gate must not write a cost event"))
    monkeypatch.setattr(session.cost_safety, "record_cost", record)

    results = await asyncio.gather(
        session.send_message("First concurrent $0.60 turn"),
        session.send_message_streaming("Second concurrent $0.60 turn"),
        return_exceptions=True,
    )

    assert all(isinstance(result, MeteredExpertChatDisabledError) for result in results)
    assert backend.requests == []
    assert backend.stream_requests == []
    assert CostLedger().get_events() == ledger_before
    assert session.cost_accumulated == 0.0
    assert session.cost_session.total_cost == 0.0
    record.assert_not_called()
    assert session.get_chat_capacity() == {
        "metered": True,
        "execution_enabled": False,
        "status": "blocked",
        "block_code": "metered_expert_chat_accounting_unavailable",
    }


async def test_all_auxiliary_metered_chat_paths_fail_before_dispatch(monkeypatch):
    session = _session(monkeypatch, 1.0)
    backend = RecordingChatBackend("must not dispatch")
    backend.metered = True
    session.chat_backend = backend
    session.messages = [{"role": "user", "content": str(index)} for index in range(8)]

    operations = [
        session._quick_lookup("q"),
        session._standard_research("q"),
        session._deep_research("q"),
        session.compact_conversation(),
        session._generate_follow_ups("q", "a"),
        session._trigger_background_synthesis(),
        session._search_knowledge_base("q"),
        session._add_research_to_knowledge_base("q", "a", "standard_research"),
    ]
    for operation in operations:
        with pytest.raises(MeteredExpertChatDisabledError):
            await operation

    assert backend.requests == []
    assert backend.stream_requests == []
    assert session.cost_accumulated == 0.0
