"""Fail-closed OpenRouter completion request and response contract."""

from __future__ import annotations

import json

import pytest

from deepr.providers.openrouter_completion import (
    OpenRouterCompletionError,
    build_openrouter_completion_request,
    complete_openrouter_chat,
)


def test_completion_request_pins_one_route_and_forbids_tools() -> None:
    body = build_openrouter_completion_request(
        model="qwen/qwen3.8-flash",
        system_message="sys",
        prompt="hello",
        max_tokens=64,
        prompt_max_price=0.15,
        completion_max_price=0.47,
    )
    assert body["model"] == "qwen/qwen3.8-flash"
    assert body["provider"]["allow_fallbacks"] is False
    assert body["provider"]["order"] == ["alibaba"]
    assert "tools" not in body
    assert "plugins" not in body
    assert "models" not in body
    assert body["stream"] is False
    assert body["provider"]["max_price"] == {"prompt": 0.15, "completion": 0.47}
    assert "max_price" not in body


def test_completion_rejects_cache_status_and_byok(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        status_code = 200
        headers = {"Content-Type": "application/json", "X-OpenRouter-Cache-Status": "HIT"}

        def iter_content(self, chunk_size: int = 16 * 1024):
            del chunk_size
            yield json.dumps({"id": "gen-1", "model": "qwen/qwen3.8-flash"}).encode()

    monkeypatch.setattr("deepr.providers.openrouter_completion.pinned_post", lambda *args, **kwargs: _Response())
    monkeypatch.setattr("deepr.providers.openrouter_completion.close_pinned_response", lambda value: None)
    with pytest.raises(OpenRouterCompletionError, match="cache status"):
        complete_openrouter_chat(
            api_key="sk-or-v1-" + "a" * 64,
            model="qwen/qwen3.8-flash",
            system_message="sys",
            prompt="hello",
            max_tokens=64,
            prompt_max_price=0.15,
            completion_max_price=0.47,
        )


def test_completion_requires_usage_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "id": "gen-1",
        "model": "qwen/qwen3.8-flash",
        "provider": "Alibaba",
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }

    class _Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}

        def iter_content(self, chunk_size: int = 16 * 1024):
            del chunk_size
            yield json.dumps(payload).encode()

    monkeypatch.setattr("deepr.providers.openrouter_completion.pinned_post", lambda *args, **kwargs: _Response())
    monkeypatch.setattr("deepr.providers.openrouter_completion.close_pinned_response", lambda value: None)
    with pytest.raises(OpenRouterCompletionError, match="usage.cost"):
        complete_openrouter_chat(
            api_key="sk-or-v1-" + "a" * 64,
            model="qwen/qwen3.8-flash",
            system_message="sys",
            prompt="hello",
            max_tokens=64,
            prompt_max_price=0.15,
            completion_max_price=0.47,
        )


def test_completion_settles_reported_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "id": "gen-1",
        "model": "qwen/qwen3.8-flash",
        "provider": "Alibaba",
        "choices": [{"message": {"content": "memo"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "cost": 0.0012, "is_byok": False},
    }

    class _Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}

        def iter_content(self, chunk_size: int = 16 * 1024):
            del chunk_size
            yield json.dumps(payload).encode()

    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return _Response()

    monkeypatch.setattr("deepr.providers.openrouter_completion.pinned_post", post)
    monkeypatch.setattr("deepr.providers.openrouter_completion.close_pinned_response", lambda value: None)
    result = complete_openrouter_chat(
        api_key="sk-or-v1-" + "a" * 64,
        model="qwen/qwen3.8-flash",
        system_message="sys",
        prompt="hello",
        max_tokens=64,
        prompt_max_price=0.15,
        completion_max_price=0.47,
    )
    assert result.content == "memo"
    assert result.cost_usd == 0.0012
    assert result.provider_name == "Alibaba"

    assert len(calls) == 1
    url, options = calls[0]
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    body = json.loads(options["data"])
    assert body["provider"]["max_price"] == {"prompt": 0.15, "completion": 0.47}
    assert "max_price" not in body
    assert options["headers"]["X-OpenRouter-Cache"] == "false"
    assert options["allow_redirects"] is False


def test_completion_accepts_list_content_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "id": "gen-2",
        "model": "qwen/qwen3.8-flash",
        "provider": "Alibaba",
        "choices": [
            {
                "message": {"content": [{"type": "text", "text": "part-a"}, {"type": "text", "text": "part-b"}]},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "cost": 0.0004, "is_byok": False},
    }

    class _Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}

        def iter_content(self, chunk_size: int = 16 * 1024):
            del chunk_size
            yield json.dumps(payload).encode()

    monkeypatch.setattr("deepr.providers.openrouter_completion.pinned_post", lambda *args, **kwargs: _Response())
    monkeypatch.setattr("deepr.providers.openrouter_completion.close_pinned_response", lambda value: None)
    result = complete_openrouter_chat(
        api_key="sk-or-v1-" + "a" * 64,
        model="qwen/qwen3.8-flash",
        system_message="sys",
        prompt="hello",
        max_tokens=64,
        prompt_max_price=0.15,
        completion_max_price=0.47,
    )
    assert result.content == "part-a\npart-b"


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -1.0, True])
def test_completion_rejects_invalid_price_limits_before_dispatch(price):
    with pytest.raises(OpenRouterCompletionError, match="provider.max_price.prompt"):
        build_openrouter_completion_request(
            model="qwen/qwen3.8-flash",
            system_message="sys",
            prompt="hello",
            max_tokens=64,
            prompt_max_price=price,
            completion_max_price=0.47,
        )
