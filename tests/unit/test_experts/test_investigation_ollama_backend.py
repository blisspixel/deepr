from __future__ import annotations

from typing import Any

import pytest

from deepr.experts.chat_backends import ExpertChatRequest, ExpertChatUnsupportedFeature
from deepr.experts.investigation.ollama_backend import (
    NativeOllamaInvestigationBackend,
    validate_owned_local_ollama_url,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("localhost:11434", "http://127.0.0.1:11434"),
        ("http://127.0.0.1:11434/", "http://127.0.0.1:11434"),
        ("http://[::1]:11434", "http://[::1]:11434"),
    ],
)
def test_owned_local_ollama_url_is_canonical_and_dns_free(value: str, expected: str) -> None:
    assert validate_owned_local_ollama_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://ollama.example.com:11434",
        "http://192.168.1.2:11434",
        "http://0.0.0.0:11434",
        "http://user:secret@127.0.0.1:11434",
        "http://127.0.0.1:11434/proxy",
    ],
)
def test_owned_local_ollama_url_rejects_remote_or_ambiguous_authority(value: str) -> None:
    with pytest.raises(ValueError, match="Owned local Ollama"):
        validate_owned_local_ollama_url(value)


def test_native_backend_rejects_remote_environment_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "https://ollama.example.com:11434")

    with pytest.raises(ValueError, match="literal loopback"):
        NativeOllamaInvestigationBackend(model="fixture")


@pytest.mark.parametrize("timeout", [0.0, float("nan"), float("inf")])
def test_native_backend_rejects_non_finite_or_non_positive_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="finite positive"):
        NativeOllamaInvestigationBackend(model="fixture", timeout=timeout)


@pytest.mark.asyncio
async def test_native_ollama_backend_enforces_json_context_and_disables_thinking() -> None:
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
    assert captured["payload"]["think"] is False
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
