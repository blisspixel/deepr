"""Native Ollama backend with per-request context and JSON enforcement."""

from __future__ import annotations

import asyncio
import math
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from types import SimpleNamespace
from typing import Any

import httpx

from deepr.backends.capacity import (
    _OLLAMA_DEFAULT_URL,
    OwnedLocalCapacityRefused,
    select_materialized_local_ollama_model,
    validate_owned_local_ollama_cloud_status,
    validate_owned_local_ollama_url,
)
from deepr.experts.chat_backends import (
    ExpertChatRequest,
    ExpertChatResult,
    ExpertChatStreamChunk,
    ExpertChatUnsupportedFeature,
)
from deepr.observability.local_attempts import LocalGenerationAttempt

PostJson = Callable[[str, dict[str, Any], float], Awaitable[dict[str, Any]]]
GetJson = Callable[[str, float], Awaitable[dict[str, Any]]]


async def _get_json(url: str, timeout: float) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
        headers={"Accept": "application/json", "User-Agent": "deepr-local-investigation/1"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Ollama returned a non-object preflight response")
    return data


async def _post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "deepr-local-investigation/1",
        },
    ) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Ollama returned a non-object response")
    return data


def _generation_fields(request_extra: dict[str, Any]) -> dict[str, Any]:
    """Validate supported generation extras into native payload fields; refuse the rest."""
    extra = dict(request_extra)
    max_tokens = int(extra.pop("max_tokens", 4096) or 4096)
    temperature = float(extra.pop("temperature", 0.2) or 0.0)
    response_format = extra.pop("response_format", None)
    num_ctx = int(extra.pop("num_ctx", 0) or 0)
    seed = extra.pop("seed", None)
    think = extra.pop("think", None)
    if seed is not None and type(seed) is not int:
        raise ExpertChatUnsupportedFeature("native Ollama seed must be an integer")
    if think is not None and type(think) is not bool:
        raise ExpertChatUnsupportedFeature("native Ollama think must be a boolean")
    if num_ctx <= 0:
        raise ExpertChatUnsupportedFeature("native Ollama investigation calls require num_ctx")
    if extra:
        fields = ", ".join(sorted(extra))
        raise ExpertChatUnsupportedFeature(f"unsupported native Ollama options: {fields}")
    options: dict[str, Any] = {"num_ctx": num_ctx, "num_predict": max_tokens, "temperature": temperature}
    fields_out: dict[str, Any] = {"options": options}
    if seed is not None:
        options["seed"] = seed
    if think is not None:
        fields_out["think"] = think
    if isinstance(response_format, dict) and response_format.get("type") == "json_object":
        fields_out["format"] = "json"
    return fields_out


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
        get_json: GetJson | None = None,
        post_json: PostJson | None = None,
    ) -> None:
        self.model: str | None = model
        self.base_url = validate_owned_local_ollama_url(base_url or os.getenv("OLLAMA_HOST") or _OLLAMA_DEFAULT_URL)
        self.timeout = timeout if timeout is not None else float(os.getenv("DEEPR_LOCAL_TIMEOUT", "3600"))
        if not math.isfinite(self.timeout) or self.timeout <= 0.0:
            raise ValueError("Ollama timeout must be a finite positive number")
        self.keep_alive = keep_alive
        self._get_json = get_json or _get_json
        self._post_json = post_json or _post_json
        # Digest observed by the most recent per-dispatch attestation, so a
        # caller with a frozen model identity can bind each call to it.
        self.last_attested_digest = ""
        self.pinned_digest = ""

    async def _attest_model(self, model: str) -> str:
        self.last_attested_digest = ""
        preflight_timeout = min(self.timeout, 5.0)
        try:
            status = await self._get_json(f"{self.base_url}/api/status", preflight_timeout)
            validate_owned_local_ollama_cloud_status(status)
            inventory = await self._get_json(f"{self.base_url}/api/tags", preflight_timeout)
        except OwnedLocalCapacityRefused:
            raise
        except (ValueError, RuntimeError, OSError, httpx.HTTPError) as exc:
            raise OwnedLocalCapacityRefused(
                "Owned local Ollama cloud/model proof could not be read; check the daemon and `deepr capacity`.",
                reason="proof_unavailable",
            ) from exc
        entries = inventory.get("models")
        if not isinstance(entries, list):
            raise OwnedLocalCapacityRefused(
                "Owned local Ollama model inventory is malformed", reason="model_unavailable"
            )
        try:
            selected = select_materialized_local_ollama_model(entries, requested=model)
        except ValueError as exc:
            raise OwnedLocalCapacityRefused(str(exc), reason="model_unavailable") from exc
        if selected.get("name") != model:
            raise OwnedLocalCapacityRefused("Owned local Ollama model attestation did not bind the request")
        self.last_attested_digest = str(selected.get("digest", "") or "")
        if self.pinned_digest and self.last_attested_digest != self.pinned_digest:
            raise OwnedLocalCapacityRefused(
                "The selected local model changed after preflight; restart explicitly with the current model.",
                reason="model_identity_changed",
            )

        return self.last_attested_digest

    async def preflight(self) -> None:
        """Observe current capacity without caching authority for dispatch."""
        await self._attest_model(self.model or "")

    async def complete(self, request: ExpertChatRequest, *, correlation_id: str = "") -> ExpertChatResult:
        model = (request.model or self.model or "").strip()
        attempt = LocalGenerationAttempt(model, correlation_id=correlation_id)
        try:
            if request.tools:
                raise ExpertChatUnsupportedFeature("native Ollama investigation backend does not support tools")
            if not model:
                raise ExpertChatUnsupportedFeature("native Ollama investigation backend requires a model")
            generation = _generation_fields(request.extra)
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
                "keep_alive": self.keep_alive,
                **generation,
            }
            digest = await self._attest_model(model)
            attempt.dispatch(digest)
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
            result = ExpertChatResult(
                message=SimpleNamespace(content=text, tool_calls=[]),
                usage=usage,
                raw_response=data,
                provider_request_id=str(data.get("id", "") or ""),
                stop_reason=str(data.get("done_reason", "") or ""),
            )
        except BaseException as error:
            status = (
                "cancelled"
                if isinstance(error, asyncio.CancelledError)
                else "failed"
                if attempt.dispatched
                else "refused"
            )
            attempt.finish(status, error_type=type(error).__name__)
            raise
        attempt.finish("returned", tokens_input=usage.prompt_tokens, tokens_output=usage.completion_tokens)
        return result

    def stream(self, request: ExpertChatRequest) -> AsyncIterator[ExpertChatStreamChunk]:
        raise ExpertChatUnsupportedFeature("native Ollama investigation backend does not support streaming")


__all__ = ["GetJson", "NativeOllamaInvestigationBackend", "PostJson", "validate_owned_local_ollama_url"]
