"""Expert chat backend contract tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.chat_backends import (
    AnthropicExpertChatBackend,
    ExpertChatRequest,
    ExpertChatUnsupportedFeature,
    LocalOllamaExpertChatBackend,
    OpenAIExpertChatBackend,
    PlanQuotaExpertChatBackend,
)


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
