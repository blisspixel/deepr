from __future__ import annotations

from typing import Any

import pytest

from deepr.experts.chat_backends import ExpertChatRequest, ExpertChatUnsupportedFeature
from deepr.experts.investigation.ollama_backend import (
    NativeOllamaInvestigationBackend,
    validate_owned_local_ollama_url,
)


def _local_model(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "model": name,
        "size": 1_000_000,
        "digest": "a" * 64,
        "details": {"format": "gguf"},
    }


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

    async def get_json(url: str, timeout: float) -> dict[str, Any]:
        captured.setdefault("preflight", []).append((url, timeout))
        if url.endswith("/api/status"):
            return {"cloud": {"disabled": True, "source": "config"}}
        return {"models": [_local_model("review:30b")]}

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
        get_json=get_json,
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
    assert captured["preflight"] == [
        ("http://127.0.0.1:11434/api/status", 5.0),
        ("http://127.0.0.1:11434/api/tags", 5.0),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        {},
        {"cloud": {"disabled": False, "source": "config"}},
        {"cloud": {"disabled": True, "source": "environment"}},
    ],
)
async def test_native_backend_requires_stable_cloud_disabled_proof(status: dict[str, Any]) -> None:
    calls: list[str] = []

    async def get_json(url: str, _timeout: float) -> dict[str, Any]:
        calls.append(url)
        return status

    async def post_json(_url: str, _payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        raise AssertionError("request must not be dispatched")

    backend = NativeOllamaInvestigationBackend(model="fixture:14b", get_json=get_json, post_json=post_json)
    with pytest.raises(ExpertChatUnsupportedFeature, match=r"cloud\.disabled=true"):
        await backend.complete(
            ExpertChatRequest(
                model="fixture:14b",
                messages=[{"role": "user", "content": "Question"}],
                extra={"num_ctx": 8_192},
            )
        )

    assert calls == ["http://127.0.0.1:11434/api/status"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry",
    [
        _local_model("fixture:cloud"),
        {**_local_model("fixture:14b"), "remote": True},
        {**_local_model("fixture:14b"), "size": 0},
        {**_local_model("fixture:14b"), "digest": "not-a-digest"},
    ],
)
async def test_native_backend_rejects_unmaterialized_or_remote_model(entry: dict[str, Any]) -> None:
    chat_dispatched = False

    async def get_json(url: str, _timeout: float) -> dict[str, Any]:
        if url.endswith("/api/status"):
            return {"cloud": {"disabled": True, "source": "config"}}
        return {"models": [entry]}

    async def post_json(_url: str, _payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        nonlocal chat_dispatched
        chat_dispatched = True
        return {}

    requested = str(entry["name"])
    backend = NativeOllamaInvestigationBackend(model=requested, get_json=get_json, post_json=post_json)
    with pytest.raises(ExpertChatUnsupportedFeature, match="zero-cost authority gate"):
        await backend.complete(
            ExpertChatRequest(
                model=requested,
                messages=[{"role": "user", "content": "Question"}],
                extra={"num_ctx": 8_192},
            )
        )

    assert chat_dispatched is False


@pytest.mark.asyncio
async def test_native_backend_rejects_request_model_missing_from_exact_inventory() -> None:
    async def get_json(url: str, _timeout: float) -> dict[str, Any]:
        if url.endswith("/api/status"):
            return {"cloud": {"disabled": True, "source": "config"}}
        return {"models": [_local_model("other:14b")]}

    async def post_json(_url: str, _payload: dict[str, Any], _timeout: float) -> dict[str, Any]:
        raise AssertionError("request must not be dispatched")

    backend = NativeOllamaInvestigationBackend(model="fixture:14b", get_json=get_json, post_json=post_json)
    with pytest.raises(ExpertChatUnsupportedFeature, match="not an exact entry"):
        await backend.complete(
            ExpertChatRequest(
                model="fixture:14b",
                messages=[{"role": "user", "content": "Question"}],
                extra={"num_ctx": 8_192},
            )
        )


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
