"""API backend construction for expert chat sessions."""

from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI

from deepr.experts.chat_backends import (
    AnthropicExpertChatBackend,
    ExpertChatBackend,
    OpenAIExpertChatBackend,
)

DEFAULT_ANTHROPIC_EXPERT_CHAT_MODEL = "claude-sonnet-4-6"

try:
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover - optional extra may be absent
    AsyncAnthropic = None  # type: ignore[assignment]


def build_api_expert_chat_backend(
    *,
    provider: str | None,
    model: str | None,
    expert_model: str,
    agentic: bool,
) -> tuple[str, str, Any, ExpertChatBackend]:
    """Build the explicit API chat backend for one expert-chat session."""
    chat_provider = (provider or "openai").strip().lower()
    chat_model = model or (DEFAULT_ANTHROPIC_EXPERT_CHAT_MODEL if chat_provider == "anthropic" else expert_model)

    if chat_provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        client = AsyncOpenAI(api_key=api_key)
        return chat_provider, chat_model, client, OpenAIExpertChatBackend(client)

    if chat_provider == "anthropic":
        if agentic:
            raise ValueError("Anthropic expert chat is non-agentic only for now")
        if AsyncAnthropic is None:
            raise ImportError("Anthropic SDK not installed. Run: pip install anthropic")
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        client = AsyncAnthropic(api_key=api_key)
        return chat_provider, chat_model, client, AnthropicExpertChatBackend(client, model=chat_model)

    raise ValueError("expert chat provider must be one of: openai, anthropic")


def estimate_chat_model_cost(model_name: str) -> float:
    """Estimate one metered expert-chat model turn from the model registry."""
    try:
        from deepr.providers.registry import get_cost_estimate

        return float(get_cost_estimate(model_name))
    except Exception:
        return 0.20
