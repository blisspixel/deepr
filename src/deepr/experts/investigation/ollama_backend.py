"""Native Ollama backend with per-request context and JSON enforcement."""

from __future__ import annotations

import ipaddress
import math
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit

from deepr.backends.capacity import _OLLAMA_DEFAULT_URL
from deepr.experts.chat_backends import (
    ExpertChatRequest,
    ExpertChatResult,
    ExpertChatStreamChunk,
    ExpertChatUnsupportedFeature,
)

PostJson = Callable[[str, dict[str, Any], float], Awaitable[dict[str, Any]]]


def validate_owned_local_ollama_url(value: str) -> str:
    """Return a canonical loopback-only Ollama endpoint."""
    raw = value.strip()
    if not raw:
        raise ValueError("Ollama URL cannot be empty")
    candidate = raw if "://" in raw else f"http://{raw}"
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Owned local Ollama capacity requires an http or https URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Owned local Ollama URL cannot contain credentials")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("Owned local Ollama URL cannot contain a path, query, or fragment")
    host = (parsed.hostname or "").lower()
    if host == "localhost":
        host = "127.0.0.1"
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("Owned local Ollama capacity requires a literal loopback host") from exc
    if not address.is_loopback:
        raise ValueError("Owned local Ollama capacity requires a loopback host")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Owned local Ollama URL has an invalid port") from exc
    rendered_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    return f"{parsed.scheme}://{rendered_host}{f':{port}' if port is not None else ''}"


async def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Ollama returned a non-object response")
    return data


class NativeOllamaInvestigationBackend:
    """Call Ollama's native chat API so the hash-bound context limit is real."""

    provider = "local"
    metered = False
    supports_tools = False
    supports_streaming = False
    supports_prompt_cache = False

    def __init__(
        self,
        *,
        model: str,
        base_url: str | None = None,
        timeout: float | None = None,
        keep_alive: str = "30m",
        post_json: PostJson | None = None,
    ) -> None:
        self.model: str | None = model
        self.base_url = validate_owned_local_ollama_url(base_url or os.getenv("OLLAMA_HOST") or _OLLAMA_DEFAULT_URL)
        self.timeout = timeout if timeout is not None else float(os.getenv("DEEPR_LOCAL_TIMEOUT", "3600"))
        if not math.isfinite(self.timeout) or self.timeout <= 0.0:
            raise ValueError("Ollama timeout must be a finite positive number")
        self.keep_alive = keep_alive
        self._post_json = post_json or _post_json

    async def complete(self, request: ExpertChatRequest) -> ExpertChatResult:
        if request.tools:
            raise ExpertChatUnsupportedFeature("native Ollama investigation backend does not support tools")
        model = (request.model or self.model or "").strip()
        if not model:
            raise ExpertChatUnsupportedFeature("native Ollama investigation backend requires a model")
        extra = dict(request.extra)
        max_tokens = int(extra.pop("max_tokens", 4096) or 4096)
        temperature = float(extra.pop("temperature", 0.2) or 0.0)
        response_format = extra.pop("response_format", None)
        num_ctx = int(extra.pop("num_ctx", 0) or 0)
        if num_ctx <= 0:
            raise ExpertChatUnsupportedFeature("native Ollama investigation calls require num_ctx")
        if extra:
            fields = ", ".join(sorted(extra))
            raise ExpertChatUnsupportedFeature(f"unsupported native Ollama options: {fields}")
        messages = [
            {
                "role": str(message.get("role", "user")),
                "content": str(message.get("content", "") or ""),
            }
            for message in request.messages
        ]
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": num_ctx,
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        if isinstance(response_format, dict) and response_format.get("type") == "json_object":
            payload["format"] = "json"
        data = await self._post_json(f"{self.base_url}/api/chat", payload, self.timeout)
        if data.get("error"):
            raise RuntimeError(f"Ollama chat failed: {data['error']}")
        message = data.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Ollama chat response is missing message")
        text = str(message.get("content", "") or "")
        usage = SimpleNamespace(
            prompt_tokens=max(0, int(data.get("prompt_eval_count", 0) or 0)),
            completion_tokens=max(0, int(data.get("eval_count", 0) or 0)),
        )
        return ExpertChatResult(
            message=SimpleNamespace(content=text, tool_calls=[]),
            usage=usage,
            raw_response=data,
            provider_request_id=str(data.get("id", "") or ""),
            stop_reason=str(data.get("done_reason", "") or ""),
        )

    def stream(self, request: ExpertChatRequest) -> AsyncIterator[ExpertChatStreamChunk]:
        raise ExpertChatUnsupportedFeature("native Ollama investigation backend does not support streaming")


__all__ = ["NativeOllamaInvestigationBackend", "PostJson", "validate_owned_local_ollama_url"]
