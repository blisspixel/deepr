"""Expert chat backend contract tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from deepr.experts import chat_api_backends, chat_capacity
from deepr.experts.chat_backends import (
    AnthropicExpertChatBackend,
    ExpertChatRequest,
    ExpertChatResult,
    ExpertChatStreamChunk,
    ExpertChatUnsupportedFeature,
    LocalOllamaExpertChatBackend,
    OpenAIExpertChatBackend,
    PlanQuotaExpertChatBackend,
    complete_expert_chat_turn,
)
from deepr.experts.chat_capacity import MeteredExpertChatDisabledError


@pytest.fixture(autouse=True)
def _enable_metered_backend_shape_tests(monkeypatch):
    """Exercise request normalization without enabling production dispatch."""
    monkeypatch.setattr(chat_capacity, "METERED_EXPERT_CHAT_EXECUTION_ENABLED", True)


class RecordingChatBackend:
    metered = False
    supports_streaming = False
    supports_prompt_cache = False

    def __init__(self, *, supports_tools: bool, provider: str = "recording") -> None:
        self.supports_tools = supports_tools
        self.provider = provider
        self.model = None
        self.request: ExpertChatRequest | None = None

    async def complete(self, request: ExpertChatRequest) -> ExpertChatResult:
        self.request = request
        return ExpertChatResult(message=SimpleNamespace(content="ok", tool_calls=[]))

    def stream(self, request: ExpertChatRequest):
        raise AssertionError("stream should not be called")


@pytest.mark.asyncio
async def test_metered_backend_boundary_fails_before_client_dispatch(monkeypatch):
    calls = 0

    class FakeCompletions:
        async def create(self, **_kwargs):
            nonlocal calls
            calls += 1
            raise AssertionError("metered client must not dispatch")

    monkeypatch.setattr(chat_capacity, "METERED_EXPERT_CHAT_EXECUTION_ENABLED", False)
    backend = OpenAIExpertChatBackend(
        SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())),
        model="gpt-5.2",
    )
    request = ExpertChatRequest(model="gpt-5.2", messages=[{"role": "user", "content": "q"}])

    with pytest.raises(MeteredExpertChatDisabledError):
        await backend.complete(request)
    with pytest.raises(MeteredExpertChatDisabledError):
        _ = [chunk async for chunk in backend.stream(request)]

    assert calls == 0


def test_openai_chat_client_disables_hidden_sdk_retries(monkeypatch):
    client = SimpleNamespace()
    constructor = MagicMock(return_value=client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(chat_api_backends, "AsyncOpenAI", constructor)

    provider, model, built_client, _backend = chat_api_backends.build_api_expert_chat_backend(
        provider="openai",
        model="gpt-5.2",
        expert_model="qwen3:latest",
        agentic=True,
    )

    assert (provider, model, built_client) == ("openai", "gpt-5.2", client)
    constructor.assert_called_once_with(api_key="sk-test", max_retries=0)


def test_anthropic_chat_client_disables_hidden_sdk_retries(monkeypatch):
    client = SimpleNamespace()
    constructor = MagicMock(return_value=client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(chat_api_backends, "AsyncAnthropic", constructor)

    provider, model, built_client, _backend = chat_api_backends.build_api_expert_chat_backend(
        provider="anthropic",
        model="claude-sonnet-5",
        expert_model="qwen3:latest",
        agentic=False,
    )

    assert (provider, model, built_client) == ("anthropic", "claude-sonnet-5", client)
    constructor.assert_called_once_with(api_key="sk-ant-test", max_retries=0)


@pytest.mark.asyncio
async def test_complete_expert_chat_turn_omits_tool_choice_without_tools():
    backend = RecordingChatBackend(supports_tools=True)

    await complete_expert_chat_turn(
        backend,
        selected_model=SimpleNamespace(model="gpt-5.2", provider="openai", reasoning_effort="low"),
        messages=[{"role": "user", "content": "q"}],
    )

    assert backend.request is not None
    assert backend.request.tools is None
    assert backend.request.tool_choice is None
    assert backend.request.reasoning_effort == "low"


@pytest.mark.asyncio
async def test_complete_expert_chat_turn_rejects_tools_when_backend_does_not_support_them():
    backend = RecordingChatBackend(supports_tools=False, provider="local")

    with pytest.raises(ExpertChatUnsupportedFeature, match="does not support tools"):
        await complete_expert_chat_turn(
            backend,
            selected_model=SimpleNamespace(model="qwen3:latest", provider="local", reasoning_effort=None),
            messages=[{"role": "user", "content": "q"}],
            tools=[{"type": "function", "function": {"name": "lookup"}}],
        )

    assert backend.request is None


@pytest.mark.asyncio
async def test_complete_expert_chat_turn_preserves_tool_choice_when_tools_supported():
    backend = RecordingChatBackend(supports_tools=True)

    await complete_expert_chat_turn(
        backend,
        selected_model=SimpleNamespace(model="gpt-5.2", provider="openai", reasoning_effort=None),
        messages=[{"role": "user", "content": "q"}],
        tools=[{"type": "function", "function": {"name": "lookup"}}],
        tool_choice="auto",
    )

    assert backend.request is not None
    assert backend.request.tools == [{"type": "function", "function": {"name": "lookup"}}]
    assert backend.request.tool_choice == "auto"


@pytest.mark.asyncio
async def test_openai_chat_backend_passes_request_shape_and_normalizes_result():
    captured: dict[str, object] = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(content="answer", tool_calls=[])
            choice = SimpleNamespace(message=message, finish_reason="stop")
            return SimpleNamespace(id="chatcmpl_123", choices=[choice], usage=SimpleNamespace(prompt_tokens=7))

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    backend = OpenAIExpertChatBackend(client, model="gpt-5.2")

    result = await backend.complete(
        ExpertChatRequest(
            model="gpt-5.2",
            messages=[{"role": "user", "content": "q"}],
            tools=[{"type": "function", "function": {"name": "search"}}],
            tool_choice="auto",
            reasoning_effort="medium",
            extra={"temperature": 0.7, "max_tokens": 200},
        )
    )

    assert captured["model"] == "gpt-5.2"
    assert captured["messages"] == [{"role": "user", "content": "q"}]
    assert captured["tool_choice"] == "auto"
    assert captured["reasoning_effort"] == "medium"
    assert captured["temperature"] == 0.7
    assert captured["max_tokens"] == 200
    assert result.text == "answer"
    assert result.usage.prompt_tokens == 7
    assert result.provider_request_id == "chatcmpl_123"
    assert result.stop_reason == "stop"


@pytest.mark.asyncio
async def test_openai_chat_backend_streams_deltas_and_usage():
    captured: dict[str, object] = {}

    class FakeStream:
        def __init__(self):
            self._chunks = [
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hel"))], usage=None),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="lo"))], usage=None),
                SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=8, completion_tokens=2)),
            ]

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._chunks:
                raise StopAsyncIteration
            return self._chunks.pop(0)

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeStream()

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    backend = OpenAIExpertChatBackend(client, model="gpt-5.2")

    chunks = [
        chunk
        async for chunk in backend.stream(
            ExpertChatRequest(
                model="gpt-5.2",
                messages=[{"role": "user", "content": "q"}],
                reasoning_effort="low",
            )
        )
    ]

    assert captured == {
        "model": "gpt-5.2",
        "messages": [{"role": "user", "content": "q"}],
        "reasoning_effort": "low",
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    assert [chunk.text_delta for chunk in chunks] == ["hel", "lo", ""]
    assert isinstance(chunks[0], ExpertChatStreamChunk)
    assert chunks[-1].usage.prompt_tokens == 8


@pytest.mark.asyncio
async def test_anthropic_chat_backend_uses_native_messages_shape_and_usage():
    captured: dict[str, object] = {}

    class FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                _request_id="req_123",
                content=[SimpleNamespace(type="text", text="anthropic answer")],
                usage=SimpleNamespace(
                    input_tokens=11,
                    output_tokens=7,
                    cache_creation_input_tokens=3,
                    cache_read_input_tokens=2,
                ),
                stop_reason="end_turn",
            )

    client = SimpleNamespace(messages=FakeMessages())
    backend = AnthropicExpertChatBackend(client, model="claude-sonnet-4-6")

    result = await backend.complete(
        ExpertChatRequest(
            model="claude-sonnet-4-6",
            messages=[
                {"role": "system", "content": "You are careful."},
                {"role": "user", "content": "q"},
            ],
            tool_choice="auto",
            reasoning_effort="high",
            extra={"temperature": 0.2, "max_tokens": 123, "response_format": {"type": "json_object"}},
        )
    )

    assert backend.provider == "anthropic"
    assert backend.metered is True
    assert backend.supports_tools is False
    assert backend.supports_streaming is True
    assert captured == {
        "model": "claude-sonnet-4-6",
        "max_tokens": 123,
        "messages": [{"role": "user", "content": "q"}],
        "system": "You are careful.",
    }
    assert result.text == "anthropic answer"
    assert result.usage.input_tokens == 11
    assert result.provider_request_id == "req_123"
    assert result.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_anthropic_chat_backend_streams_text_and_final_usage():
    captured: dict[str, object] = {}

    class AsyncTextStream:
        def __init__(self, chunks):
            self._chunks = list(chunks)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._chunks:
                raise StopAsyncIteration
            return self._chunks.pop(0)

    class FakeStream:
        def __init__(self):
            self.text_stream = AsyncTextStream(["hel", "lo"])

        async def get_final_message(self):
            return SimpleNamespace(
                usage=SimpleNamespace(
                    input_tokens=9,
                    output_tokens=2,
                    cache_creation_input_tokens=1,
                    cache_read_input_tokens=3,
                )
            )

    class FakeStreamManager:
        async def __aenter__(self):
            return FakeStream()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeMessages:
        def stream(self, **kwargs):
            captured.update(kwargs)
            return FakeStreamManager()

    client = SimpleNamespace(messages=FakeMessages())
    backend = AnthropicExpertChatBackend(client, model="claude-sonnet-4-6")

    chunks = [
        chunk
        async for chunk in backend.stream(
            ExpertChatRequest(
                model="claude-sonnet-4-6",
                messages=[
                    {"role": "system", "content": "You are careful."},
                    {"role": "user", "content": "q"},
                ],
                extra={"temperature": 0.2, "max_tokens": 123},
            )
        )
    ]

    assert captured == {
        "model": "claude-sonnet-4-6",
        "max_tokens": 123,
        "messages": [{"role": "user", "content": "q"}],
        "system": "You are careful.",
    }
    assert [chunk.text_delta for chunk in chunks] == ["hel", "lo", ""]
    assert chunks[-1].usage.input_tokens == 9
    assert chunks[-1].usage.output_tokens == 2


@pytest.mark.asyncio
async def test_anthropic_chat_backend_rejects_tools():
    client = SimpleNamespace(messages=SimpleNamespace())
    backend = AnthropicExpertChatBackend(client, model="claude-sonnet-4-6")

    with pytest.raises(ExpertChatUnsupportedFeature, match="does not support tools"):
        await backend.complete(
            ExpertChatRequest(
                model="claude-sonnet-4-6",
                messages=[{"role": "user", "content": "q"}],
                tools=[{"type": "function", "function": {"name": "lookup"}}],
            )
        )


@pytest.mark.asyncio
async def test_anthropic_chat_backend_stream_rejects_tools():
    client = SimpleNamespace(messages=SimpleNamespace())
    backend = AnthropicExpertChatBackend(client, model="claude-sonnet-4-6")

    with pytest.raises(ExpertChatUnsupportedFeature, match="does not support tools"):
        chunks = [
            chunk
            async for chunk in backend.stream(
                ExpertChatRequest(
                    model="claude-sonnet-4-6",
                    messages=[{"role": "user", "content": "q"}],
                    tools=[{"type": "function", "function": {"name": "lookup"}}],
                )
            )
        ]
        assert chunks == []


@pytest.mark.asyncio
async def test_anthropic_chat_backend_surfaces_empty_refusal():
    class FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(
                content=[],
                usage=None,
                stop_reason="refusal",
                stop_details=SimpleNamespace(category="safety"),
            )

    backend = AnthropicExpertChatBackend(SimpleNamespace(messages=FakeMessages()), model="claude-sonnet-4-6")

    result = await backend.complete(
        ExpertChatRequest(model="claude-sonnet-4-6", messages=[{"role": "user", "content": "q"}])
    )

    assert result.text == "Anthropic safety classifiers declined the request (category: safety)."
    assert result.stop_reason == "refusal"


@pytest.mark.asyncio
async def test_local_ollama_chat_backend_omits_unsupported_features_and_sets_keep_alive():
    captured: dict[str, object] = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(content="local answer", tool_calls=[])
            choice = SimpleNamespace(message=message, finish_reason="stop")
            return SimpleNamespace(id="local_1", choices=[choice], usage=None)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    backend = LocalOllamaExpertChatBackend(client, model="qwen3:latest", keep_alive="5m")

    result = await backend.complete(
        ExpertChatRequest(
            model="qwen3:latest",
            messages=[{"role": "user", "content": "q"}],
            tool_choice="auto",
            reasoning_effort="high",
            extra={"temperature": 0.2},
        )
    )

    assert backend.provider == "local"
    assert backend.metered is False
    assert backend.supports_tools is False
    assert backend.supports_streaming is False
    assert captured == {
        "model": "qwen3:latest",
        "messages": [{"role": "user", "content": "q"}],
        "temperature": 0.2,
        "extra_body": {"keep_alive": "5m"},
    }
    assert result.text == "local answer"
    assert result.provider_request_id == "local_1"


@pytest.mark.asyncio
async def test_local_ollama_chat_backend_rejects_tools():
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace()))
    backend = LocalOllamaExpertChatBackend(client, model="qwen3:latest")

    with pytest.raises(ExpertChatUnsupportedFeature, match="does not support tools"):
        await backend.complete(
            ExpertChatRequest(
                model="qwen3:latest",
                messages=[{"role": "user", "content": "q"}],
                tools=[{"type": "function", "function": {"name": "lookup"}}],
            )
        )


@pytest.mark.asyncio
async def test_plan_quota_chat_backend_wraps_cli_client_without_metered_features():
    captured: dict[str, object] = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(content="plan answer", tool_calls=[])
            choice = SimpleNamespace(message=message, finish_reason="stop")
            return SimpleNamespace(choices=[choice], usage=None)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    backend = PlanQuotaExpertChatBackend(client, backend_id="codex", model="fast")

    result = await backend.complete(
        ExpertChatRequest(
            model="",
            messages=[{"role": "user", "content": "q"}],
            reasoning_effort="medium",
            extra={"response_format": {"type": "json_object"}},
        )
    )

    assert backend.provider == "plan_quota:codex"
    assert backend.backend_id == "codex"
    assert backend.metered is False
    assert backend.supports_tools is False
    assert backend.supports_streaming is False
    assert captured == {
        "model": "fast",
        "messages": [{"role": "user", "content": "q"}],
        "response_format": {"type": "json_object"},
    }
    assert result.text == "plan answer"
