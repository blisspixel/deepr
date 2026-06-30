"""Expert chat backend contract tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.chat_backends import ExpertChatRequest, OpenAIExpertChatBackend


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
