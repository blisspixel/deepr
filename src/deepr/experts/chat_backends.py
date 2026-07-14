"""Backend contract for expert chat model turns."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Protocol

from deepr.experts.chat_capacity import require_expert_chat_dispatch


@dataclass(frozen=True)
class ExpertChatRequest:
    """Normalized request for one expert chat model turn."""

    model: str
    messages: list[Any]
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | None = None
    reasoning_effort: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExpertChatResult:
    """Normalized result for one expert chat model turn."""

    message: Any
    usage: Any | None = None
    raw_response: Any | None = None
    provider_request_id: str = ""
    stop_reason: str = ""

    @property
    def text(self) -> str:
        return str(getattr(self.message, "content", "") or "")


@dataclass(frozen=True)
class ExpertChatStreamChunk:
    """Normalized stream event for one expert chat text delta or usage update."""

    text_delta: str = ""
    usage: Any | None = None
    raw_chunk: Any | None = None


class ExpertChatUnsupportedFeature(ValueError):
    """Raised when a backend is asked to use a feature it does not declare."""


class ExpertChatBackend(Protocol):
    """Provider-neutral backend for expert chat model turns."""

    provider: str
    model: str | None
    metered: bool
    supports_tools: bool
    supports_streaming: bool
    supports_prompt_cache: bool

    async def complete(self, request: ExpertChatRequest) -> ExpertChatResult:
        """Complete one chat turn."""

    def stream(self, request: ExpertChatRequest) -> AsyncIterator[ExpertChatStreamChunk]:
        """Stream one chat turn."""


def _chat_reasoning_effort(model: Any) -> str | None:
    if getattr(model, "reasoning_effort", None) and getattr(model, "provider", None) == "openai":
        return str(model.reasoning_effort)
    return None


async def complete_expert_chat_turn(
    backend: ExpertChatBackend,
    *,
    selected_model: Any,
    messages: list[Any],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = "auto",
    max_cost_per_job: float | None = None,
    extra: dict[str, Any] | None = None,
) -> ExpertChatResult:
    """Build and complete one expert chat turn through the configured backend."""
    if tools and not backend.supports_tools:
        raise ExpertChatUnsupportedFeature(f"{backend.provider} expert-chat backend does not support tools")
    effective_tool_choice = tool_choice if tools else None
    request_extra = dict(extra or {})
    if max_cost_per_job is not None:
        request_extra["max_cost_per_job"] = max_cost_per_job
    return await backend.complete(
        ExpertChatRequest(
            model=selected_model.model,
            messages=messages,
            tools=tools,
            tool_choice=effective_tool_choice,
            reasoning_effort=_chat_reasoning_effort(selected_model),
            extra=request_extra,
        )
    )


def stream_expert_chat_turn(
    backend: ExpertChatBackend,
    *,
    selected_model: Any,
    messages: list[Any],
    max_cost_per_job: float | None = None,
    extra: dict[str, Any] | None = None,
) -> AsyncIterator[ExpertChatStreamChunk]:
    """Build and stream one expert chat turn through the configured backend."""
    if not backend.supports_streaming:
        raise ExpertChatUnsupportedFeature(f"{backend.provider} expert-chat backend does not support streaming")
    request_extra = dict(extra or {})
    if max_cost_per_job is not None:
        request_extra["max_cost_per_job"] = max_cost_per_job
    return backend.stream(
        ExpertChatRequest(
            model=selected_model.model,
            messages=messages,
            reasoning_effort=_chat_reasoning_effort(selected_model),
            extra=request_extra,
        )
    )


class OpenAIExpertChatBackend:
    """OpenAI chat-completions backend preserving the legacy chat path."""

    provider = "openai"
    metered = True
    supports_tools = True
    supports_streaming = True
    supports_prompt_cache = True

    def __init__(self, client: Any, *, model: str | None = None) -> None:
        self.client = client
        self.model = model

    async def complete(self, request: ExpertChatRequest) -> ExpertChatResult:
        require_expert_chat_dispatch(self, "expert_chat_completion")
        from deepr.experts.chat_metered import execute_metered_chat_provider_call, split_accounting_extra

        provider_extra, max_cost_per_job = split_accounting_extra(request.extra)
        params = self._build_params(request, extra=provider_extra)
        response = await execute_metered_chat_provider_call(
            provider=self.provider,
            model=request.model,
            source="expert_chat.completion",
            max_cost_per_job=max_cost_per_job,
            call=lambda: self.client.chat.completions.create(**params),
        )
        choice = response.choices[0]
        return ExpertChatResult(
            message=choice.message,
            usage=getattr(response, "usage", None),
            raw_response=response,
            provider_request_id=str(getattr(response, "id", "") or ""),
            stop_reason=str(getattr(choice, "finish_reason", "") or ""),
        )

    async def stream(self, request: ExpertChatRequest) -> AsyncIterator[ExpertChatStreamChunk]:
        require_expert_chat_dispatch(self, "expert_chat_stream")
        from deepr.experts.chat_metered import (
            execute_metered_chat_provider_stream,
            split_accounting_extra,
        )

        provider_extra, max_cost_per_job = split_accounting_extra(request.extra)
        params = self._build_params(request, extra=provider_extra)
        params["stream"] = True
        params["stream_options"] = {"include_usage": True}

        async def events() -> AsyncIterator[tuple[ExpertChatStreamChunk, object | None]]:
            stream = await self.client.chat.completions.create(**params)
            async for chunk in stream:
                usage = getattr(chunk, "usage", None)
                delta = chunk.choices[0].delta if getattr(chunk, "choices", None) else None
                text_delta = str(getattr(delta, "content", "") or "") if delta else ""
                yield ExpertChatStreamChunk(text_delta=text_delta, usage=usage, raw_chunk=chunk), usage

        async for item in execute_metered_chat_provider_stream(
            provider=self.provider,
            model=request.model,
            source="expert_chat.stream",
            max_cost_per_job=max_cost_per_job,
            events=events,
        ):
            yield item

    def _build_params(self, request: ExpertChatRequest, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
        }
        if request.tools is not None:
            params["tools"] = request.tools
        if request.tool_choice is not None:
            params["tool_choice"] = request.tool_choice
        if request.reasoning_effort:
            params["reasoning_effort"] = request.reasoning_effort
        params.update(request.extra if extra is None else extra)
        return params


class AnthropicExpertChatBackend:
    """Anthropic Messages API backend for non-agentic expert-chat turns."""

    provider = "anthropic"
    metered = True
    supports_tools = False
    supports_streaming = True
    supports_prompt_cache = False

    def __init__(self, client: Any, *, model: str) -> None:
        self.client = client
        self.model: str | None = model

    async def complete(self, request: ExpertChatRequest) -> ExpertChatResult:
        require_expert_chat_dispatch(self, "expert_chat_completion")
        if request.tools:
            raise ExpertChatUnsupportedFeature("anthropic expert-chat backend does not support tools yet")

        from deepr.experts.chat_metered import execute_metered_chat_provider_call, split_accounting_extra

        model = request.model if request.model.startswith("claude-") else self.model or request.model
        provider_extra, max_cost_per_job = split_accounting_extra(request.extra)
        params = self._build_params(request, model=model, extra=provider_extra)
        response = await execute_metered_chat_provider_call(
            provider=self.provider,
            model=model,
            source="expert_chat.completion",
            max_cost_per_job=max_cost_per_job,
            call=lambda: self.client.messages.create(**params),
        )
        text = _anthropic_response_text(response)
        stop_reason = str(getattr(response, "stop_reason", "") or "")
        if stop_reason == "refusal" and not text:
            text = _anthropic_refusal_text(response)
        return ExpertChatResult(
            message=SimpleNamespace(content=text, tool_calls=[]),
            usage=getattr(response, "usage", None),
            raw_response=response,
            provider_request_id=str(getattr(response, "_request_id", "") or getattr(response, "id", "") or ""),
            stop_reason=stop_reason,
        )

    async def stream(self, request: ExpertChatRequest) -> AsyncIterator[ExpertChatStreamChunk]:
        require_expert_chat_dispatch(self, "expert_chat_stream")
        if request.tools:
            raise ExpertChatUnsupportedFeature("anthropic expert-chat backend does not support tools yet")

        from deepr.experts.chat_metered import (
            execute_metered_chat_provider_stream,
            split_accounting_extra,
        )

        model = request.model if request.model.startswith("claude-") else self.model or request.model
        provider_extra, max_cost_per_job = split_accounting_extra(request.extra)
        params = self._build_params(request, model=model, extra=provider_extra)

        async def events() -> AsyncIterator[tuple[ExpertChatStreamChunk, object | None]]:
            async with self.client.messages.stream(**params) as stream:
                async for text_delta in stream.text_stream:
                    yield ExpertChatStreamChunk(text_delta=str(text_delta), raw_chunk=text_delta), None
                final_message = await stream.get_final_message()
                usage = getattr(final_message, "usage", None)
                if usage is not None:
                    yield ExpertChatStreamChunk(usage=usage, raw_chunk=final_message), usage

        async for item in execute_metered_chat_provider_stream(
            provider=self.provider,
            model=model,
            source="expert_chat.stream",
            max_cost_per_job=max_cost_per_job,
            events=events,
        ):
            yield item

    def _build_params(
        self,
        request: ExpertChatRequest,
        *,
        model: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(request.extra if extra is None else extra)
        max_tokens = int(payload.pop("max_tokens", 4096) or 4096)
        payload.pop("temperature", None)
        payload.pop("top_p", None)
        payload.pop("top_k", None)
        payload.pop("response_format", None)

        system_parts: list[str] = []
        messages: list[dict[str, str]] = []
        for raw in request.messages:
            role = str(raw.get("role", "user")) if isinstance(raw, dict) else "user"
            content = _message_content_text(raw)
            if role == "system":
                system_parts.append(content)
            elif role in {"user", "assistant"}:
                messages.append({"role": role, "content": content})
            elif role == "tool":
                raise ExpertChatUnsupportedFeature("anthropic expert-chat backend does not support tool messages yet")
            else:
                messages.append({"role": "user", "content": content})

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages or [{"role": "user", "content": ""}],
        }
        if system_parts:
            params["system"] = "\n\n".join(part for part in system_parts if part)
        if "thinking" in payload:
            params["thinking"] = payload["thinking"]
        return params


def _message_content_text(message: Any) -> str:
    if isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(getattr(item, "text", "") or getattr(item, "content", "") or ""))
        return "\n".join(part for part in parts if part)
    return str(content or "")


def _anthropic_response_text(response: Any) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text" or hasattr(block, "text"):
            text = getattr(block, "text", "")
            if text:
                parts.append(str(text))
    return "\n".join(parts).strip()


def _anthropic_refusal_text(response: Any) -> str:
    details = getattr(response, "stop_details", None)
    category = getattr(details, "category", None) if details else None
    if category:
        return f"Anthropic safety classifiers declined the request (category: {category})."
    return "Anthropic safety classifiers declined the request."


class _OpenAIShapeNoToolExpertChatBackend:
    """Adapter for OpenAI-compatible owned-capacity clients without tool support."""

    metered = False
    supports_tools = False
    supports_streaming = False
    supports_prompt_cache = False

    def __init__(self, client: Any, *, provider: str, model: str | None = None) -> None:
        self.client = client
        self.provider = provider
        self.model = model

    async def complete(self, request: ExpertChatRequest) -> ExpertChatResult:
        if request.tools:
            raise ExpertChatUnsupportedFeature(f"{self.provider} expert-chat backend does not support tools")

        params = self._build_params(request)
        response = await self.client.chat.completions.create(**params)
        choice = response.choices[0]
        return ExpertChatResult(
            message=choice.message,
            usage=getattr(response, "usage", None),
            raw_response=response,
            provider_request_id=str(getattr(response, "id", "") or ""),
            stop_reason=str(getattr(choice, "finish_reason", "") or ""),
        )

    def stream(self, request: ExpertChatRequest) -> AsyncIterator[ExpertChatStreamChunk]:
        raise ExpertChatUnsupportedFeature(f"{self.provider} expert-chat backend does not support streaming")

    def _build_params(self, request: ExpertChatRequest) -> dict[str, Any]:
        model = request.model or self.model
        if not model:
            raise ExpertChatUnsupportedFeature(f"{self.provider} expert-chat backend requires a model")
        return {"model": model, "messages": request.messages, **request.extra}


class LocalOllamaExpertChatBackend(_OpenAIShapeNoToolExpertChatBackend):
    """Local Ollama expert-chat backend for read-only compiled-context turns."""

    def __init__(self, client: Any, *, model: str, keep_alive: str = "30m") -> None:
        super().__init__(client, provider="local", model=model)
        self.keep_alive = keep_alive

    def _build_params(self, request: ExpertChatRequest) -> dict[str, Any]:
        params = super()._build_params(request)
        extra_body = dict(params.pop("extra_body", {}) or {})
        extra_body.setdefault("keep_alive", self.keep_alive)
        params["extra_body"] = extra_body
        return params


class PlanQuotaExpertChatBackend(_OpenAIShapeNoToolExpertChatBackend):
    """Plan-quota expert-chat backend for explicit prepaid CLI turns."""

    def __init__(self, client: Any, *, backend_id: str, model: str | None = None) -> None:
        super().__init__(client, provider=f"plan_quota:{backend_id}", model=model or backend_id)
        self.backend_id = backend_id
