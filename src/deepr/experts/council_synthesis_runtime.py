"""Provider dispatch for one bounded council synthesis call."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deepr.experts.council_synthesis_costs import (
    SynthesisCostBound,
    anthropic_completion_usage,
    openai_completion_usage,
)
from deepr.experts.semantic_model_gate import require_zero_dollar_client


class MeteredCouncilSynthesisDisabledError(RuntimeError):
    """A paid council synthesis was refused before provider dispatch."""

    provider_work_dispatched = False


# Study's local backend uses this window. The OpenAI-compatible route cannot
# carry it, and Ollama then keeps a 4096-token context on CPU and iGPU hosts.
LOCAL_SYNTHESIS_CONTEXT_TOKENS = 16384


@dataclass(frozen=True)
class SynthesisProviderResponse:
    text: str
    usage: dict[str, Any]
    provider_request_id: str
    stop_reason: str


def _anthropic_text(response: Any) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(str(block.get("text", "") or ""))
            continue
        if getattr(block, "type", None) == "text":
            parts.append(str(getattr(block, "text", "") or ""))
    return "\n".join(part for part in parts if part).strip()


async def _anthropic_synthesis(
    messages_api: Any,
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    output_tokens: int,
    cost_bound: SynthesisCostBound,
) -> SynthesisProviderResponse:
    result = await messages_api.create(
        model=model,
        max_tokens=output_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if getattr(result, "stop_reason", None) == "refusal":
        details = getattr(result, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        suffix = f" (category: {category})" if category else ""
        raise RuntimeError(f"Anthropic safety classifiers declined council synthesis{suffix}")
    return SynthesisProviderResponse(
        text=_anthropic_text(result),
        usage=anthropic_completion_usage(getattr(result, "usage", None), cost_bound),
        provider_request_id=str(getattr(result, "id", "") or ""),
        stop_reason=str(getattr(result, "stop_reason", "") or ""),
    )


async def _openai_shape_synthesis(
    completions_api: Any,
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    output_tokens: int,
    cost_bound: SynthesisCostBound | None,
) -> SynthesisProviderResponse:
    params: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": output_tokens,
    }
    result = await completions_api.create(**params)
    choice = result.choices[0]
    owned = provider == "local" or provider.startswith("plan_quota:")
    if owned:
        usage = {
            "cost": 0.0,
            "tokens_input": 0,
            "tokens_output": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cost_estimated": False,
        }
    else:
        if cost_bound is None:
            raise RuntimeError("OpenAI synthesis reached dispatch without a metered cost bound")
        usage = openai_completion_usage(getattr(result, "usage", None), cost_bound)
    return SynthesisProviderResponse(
        text=choice.message.content or "",
        usage=usage,
        provider_request_id=str(getattr(result, "id", "") or ""),
        stop_reason=str(getattr(choice, "finish_reason", "") or ""),
    )


async def _local_native_synthesis(
    complete: Any,
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    output_tokens: int,
    context_tokens: int,
) -> SynthesisProviderResponse:
    """Send the full prompt through Ollama's native chat API at the study window.

    The selected model is the model on the request. This does not pick a
    smaller model and does not drop evidence to fit the 4096-token default.
    """
    from deepr.experts.chat_backends import ExpertChatRequest

    result = await complete(
        ExpertChatRequest(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            extra={
                "max_tokens": output_tokens,
                "num_ctx": context_tokens,
                "temperature": 0.3,
                "think": False,
            },
        )
    )
    usage = getattr(result, "usage", None)
    text = getattr(result, "text", None)
    if text is None:
        text = str(getattr(getattr(result, "message", None), "content", "") or "")
    return SynthesisProviderResponse(
        text=str(text or ""),
        usage={
            "cost": 0.0,
            "tokens_input": max(0, int(getattr(usage, "prompt_tokens", 0) or 0)),
            "tokens_output": max(0, int(getattr(usage, "completion_tokens", 0) or 0)),
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cost_estimated": False,
        },
        provider_request_id=str(getattr(result, "provider_request_id", "") or ""),
        stop_reason=str(getattr(result, "stop_reason", "") or ""),
    )


async def dispatch_synthesis(
    *,
    provider: str,
    model: str,
    client: Any,
    openai_client_factory: Any,
    system_prompt: str,
    user_prompt: str,
    output_tokens: int,
    cost_bound: SynthesisCostBound | None,
    pre_dispatch_callback: Any,
    context_tokens: int = LOCAL_SYNTHESIS_CONTEXT_TOKENS,
) -> SynthesisProviderResponse:
    """Resolve the provider shape, mark dispatch, and perform one call."""
    owned = provider == "local" or provider.startswith("plan_quota:")
    if not owned:
        raise MeteredCouncilSynthesisDisabledError(
            "Metered council synthesis is disabled until account identity and a provider-enforceable "
            "maximum charge are bound to the one-use dispatch grant. No provider request was sent."
        )
    require_zero_dollar_client(client, capacity_source=provider)
    del openai_client_factory
    if provider == "local":
        complete = getattr(client, "complete", None)
        if not callable(complete):
            raise RuntimeError(
                "Local consult synthesis requires the native Ollama runtime. "
                "The OpenAI-compatible endpoint cannot carry num_ctx."
            )
        if pre_dispatch_callback is not None:
            await pre_dispatch_callback()
        return await _local_native_synthesis(
            complete,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_tokens=output_tokens,
            context_tokens=context_tokens,
        )
    completions_api = client.chat.completions
    if pre_dispatch_callback is not None:
        await pre_dispatch_callback()
    return await _openai_shape_synthesis(
        completions_api,
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        output_tokens=output_tokens,
        cost_bound=cost_bound,
    )


__all__ = [
    "LOCAL_SYNTHESIS_CONTEXT_TOKENS",
    "MeteredCouncilSynthesisDisabledError",
    "SynthesisProviderResponse",
    "dispatch_synthesis",
]
