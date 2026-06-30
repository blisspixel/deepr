"""ExpertChatSession budget handling (no-surprise-bills).

Regression for a live-hunt finding (2026-06-14): `budget or 10.0` silently
turned an explicit budget=0.0 ("do not spend") into a $10 ceiling, because 0.0
is falsy. An agent or `--budget 0` caller meaning no spend got a real budget.
"""

import sys
from types import ModuleType, SimpleNamespace

from deepr.experts.chat import ExpertChatSession
from deepr.experts.chat_backends import ExpertChatResult
from deepr.experts.cost_safety import CostSafetyManager, reset_cost_safety_manager
from deepr.experts.profile import ExpertProfile


def _session(monkeypatch, budget):
    reset_cost_safety_manager()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    expert = ExpertProfile(name="Budget Probe", vector_store_id="vs-x", domain="ai")
    return ExpertChatSession(expert, budget=budget, enable_router=False)


class RecordingChatBackend:
    provider = "openai"
    model = "gpt-5.2"
    metered = True
    supports_tools = True
    supports_streaming = True
    supports_prompt_cache = True

    def __init__(self, *contents) -> None:
        self.requests = []
        self._contents = list(contents)

    async def complete(self, request):
        self.requests.append(request)
        content = self._contents.pop(0) if self._contents else "backend answer"
        return ExpertChatResult(
            message=SimpleNamespace(content=content, tool_calls=[]),
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


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


async def test_standard_research_reports_blocked_when_session_circuit_is_open(monkeypatch):
    session = _session(monkeypatch, 1.0)

    for index in range(5):
        session.cost_session.record_failure("standard_research", f"failure-{index}")

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("provider fallback should not run when session circuit is open")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)

    result = await session._standard_research("latest ai news")

    assert result["status"] == "blocked"
    assert result["mode"] == "standard_research"
    assert result["error"].startswith("Research blocked: Session circuit breaker open")


async def test_standard_research_records_metered_grok_cost(monkeypatch):
    session = _session(monkeypatch, 1.0)
    monkeypatch.setenv("XAI_API_KEY", "xai-test-not-real")

    class FakeChat:
        def __init__(self):
            self.messages = []

        def append(self, message):
            self.messages.append(message)

        def sample(self):
            return SimpleNamespace(content="fresh answer", citations=["https://example.test/source"])

    class FakeChatFactory:
        def create(self, *, model, tools):
            assert model == "grok-4.3"
            assert len(tools) == 2
            return FakeChat()

    class FakeClient:
        def __init__(self, *, api_key, timeout):
            assert api_key == "xai-test-not-real"
            assert timeout > 0
            self.chat = FakeChatFactory()

    xai_sdk = ModuleType("xai_sdk")
    xai_sdk.Client = FakeClient
    xai_chat = ModuleType("xai_sdk.chat")
    xai_chat.system = lambda content: {"role": "system", "content": content}
    xai_chat.user = lambda content: {"role": "user", "content": content}
    xai_tools = ModuleType("xai_sdk.tools")
    xai_tools.web_search = lambda: {"type": "web_search"}
    xai_tools.x_search = lambda: {"type": "x_search"}

    monkeypatch.setitem(sys.modules, "xai_sdk", xai_sdk)
    monkeypatch.setitem(sys.modules, "xai_sdk.chat", xai_chat)
    monkeypatch.setitem(sys.modules, "xai_sdk.tools", xai_tools)

    async def ignore_knowledge_write(*_args, **_kwargs):
        return None

    session._add_research_to_knowledge_base = ignore_knowledge_write

    result = await session._standard_research("latest ai news")

    assert result["mode"] == "standard_research_grok_agentic"
    assert result["cost"] == 0.05
    assert session.cost_accumulated == 0.05
    assert "https://example.test/source" in result["answer"]


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


async def test_standard_research_fallback_uses_chat_backend(monkeypatch):
    session = _session(monkeypatch, 1.0)
    monkeypatch.delenv("XAI_API_KEY", raising=False)

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("legacy client should be behind chat_backend")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)
    backend = RecordingChatBackend("fallback answer")
    session.chat_backend = backend

    result = await session._standard_research("latest ai infrastructure funding")

    assert result["mode"] == "standard_research_fallback"
    assert "fallback answer" in result["answer"]
    assert "Grok web search unavailable" in result["answer"]
    assert len(backend.requests) == 1
    assert backend.requests[0].model == "gpt-5.5"
    assert backend.requests[0].reasoning_effort == "low"


async def test_deep_research_reports_blocked_when_session_budget_is_exhausted(monkeypatch):
    session = _session(monkeypatch, 0.0)

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("deep research provider call should not run after budget denial")

    monkeypatch.setattr(session.client.responses, "create", fail_if_called)
    monkeypatch.setattr(CostSafetyManager, "ABSOLUTE_MAX_PER_OPERATION", 10.0)

    result = await session._deep_research("design a migration strategy")

    assert result["status"] == "blocked"
    assert result["mode"] == "deep_research"
    assert result["session_budget"] == 0.0
    assert result["error"].startswith("Session budget exceeded: Insufficient budget")


async def test_first_chat_generation_is_preflight_budget_checked(monkeypatch):
    session = _session(monkeypatch, 0.0)
    session.should_use_tot = lambda _query: False

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("chat provider call should not run after budget denial")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)

    result = await session.send_message("What should this expert improve next?")

    assert result.startswith("Chat blocked: Insufficient budget")
    assert session.reasoning_trace[-1]["step"] == "chat_generation_budget"
    assert session.reasoning_trace[-1]["allowed"] is False


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


async def test_anthropic_non_agentic_chat_omits_tools_and_records_cost(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-not-real")

    class FakeAsyncAnthropic:
        def __init__(self, *, api_key):
            assert api_key == "anthropic-test-not-real"

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
    assert session.cost_accumulated > 0


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

    follow_ups = await session._generate_follow_ups("What changed?", "The backend seam changed.")

    assert follow_ups == ["What evidence matters next?", "How should we validate this?"]
    assert len(backend.requests) == 1
    assert backend.requests[0].model == "gpt-4o-mini"
    assert backend.requests[0].extra == {"temperature": 0.7, "max_tokens": 200}


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


async def test_streaming_first_chat_generation_is_preflight_budget_checked(monkeypatch):
    session = _session(monkeypatch, 0.0)
    session.should_use_tot = lambda _query: False

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("streaming chat provider call should not run after budget denial")

    monkeypatch.setattr(session.client.chat.completions, "create", fail_if_called)

    result = await session.send_message_streaming("What should this expert improve next?")

    assert result.startswith("Chat blocked: Insufficient budget")
    assert session.reasoning_trace[-1]["step"] == "chat_generation_budget"
    assert session.reasoning_trace[-1]["allowed"] is False


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

    class FakeStream:
        def __init__(self):
            self._chunks = [
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="hello"))],
                    usage=None,
                ),
                SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=20, completion_tokens=7)),
            ]

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._chunks:
                raise StopAsyncIteration
            return self._chunks.pop(0)

    async def fake_stream_create(**kwargs):
        assert kwargs["stream"] is True
        assert kwargs["stream_options"] == {"include_usage": True}
        return FakeStream()

    monkeypatch.setattr(session.client.chat.completions, "create", fake_stream_create)
    session._account_chat_cost = lambda usage, model: accounted.append(usage)
    session.chat_backend = RecordingChatBackend(None, "[]")

    result = await session.send_message_streaming(
        "Stream a final answer",
        token_callback=emitted.append,
    )

    assert result == "hello"
    assert emitted == ["hello"]
    assert [(u.prompt_tokens, u.completion_tokens) for u in accounted] == [(20, 7), (10, 5)]
