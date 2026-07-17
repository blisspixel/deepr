from __future__ import annotations

from typing import Any

import pytest

from deepr.experts.chat_backends import ExpertChatRequest, ExpertChatUnsupportedFeature
from deepr.experts.investigation.ollama_backend import NativeOllamaInvestigationBackend


@pytest.mark.asyncio
async def test_native_ollama_backend_enforces_json_and_context_options() -> None:
    captured: dict[str, Any] = {}

    async def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        captured.update(url=url, payload=payload, timeout=timeout)
        return {
            "message": {"role": "assistant", "content": '{"answer":"ok"}'},
            "prompt_eval_count": 12,
            "eval_count": 5,
            "done_reason": "stop",
        }

    backend = NativeOllamaInvestigationBackend(
        model="expert:14b",
        base_url="http://127.0.0.1:11434/",
        timeout=30.0,
        post_json=post_json,
    )
    result = await backend.complete(
        ExpertChatRequest(
            model="review:30b",
            messages=[{"role": "user", "content": "Return JSON"}],
            extra={
                "max_tokens": 1024,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "num_ctx": 32_768,
            },
        )
    )

    assert result.text == '{"answer":"ok"}'
    assert result.usage.prompt_tokens == 12
    assert result.usage.completion_tokens == 5
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["model"] == "review:30b"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["format"] == "json"
    assert captured["payload"]["options"] == {
        "num_ctx": 32_768,
        "num_predict": 1024,
        "temperature": 0.2,
    }


@pytest.mark.asyncio
async def test_native_ollama_backend_rejects_unpinned_context() -> None:
    async def post_json(_url: str, _payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        raise AssertionError("request must not be dispatched")

    backend = NativeOllamaInvestigationBackend(model="fixture", post_json=post_json)

    with pytest.raises(ExpertChatUnsupportedFeature, match="require num_ctx"):
        await backend.complete(
            ExpertChatRequest(
                model="fixture",
                messages=[{"role": "user", "content": "Question"}],
            )
        )
