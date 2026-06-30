"""Backend contract for expert chat model turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


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
) -> ExpertChatResult:
    """Build and complete one expert chat turn through the configured backend."""
    return await backend.complete(
        ExpertChatRequest(
            model=selected_model.model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            reasoning_effort=_chat_reasoning_effort(selected_model),
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
        params.update(request.extra)

        response = await self.client.chat.completions.create(**params)
        choice = response.choices[0]
        return ExpertChatResult(
            message=choice.message,
            usage=getattr(response, "usage", None),
            raw_response=response,
            provider_request_id=str(getattr(response, "id", "") or ""),
            stop_reason=str(getattr(choice, "finish_reason", "") or ""),
        )
