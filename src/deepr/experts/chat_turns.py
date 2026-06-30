"""Small helpers for expert chat turn accounting and routing traces."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from deepr.experts.router import ModelConfig
from deepr.experts.thought_stream import ThoughtType

logger = logging.getLogger(__name__)

_DEFAULT_CHAT_INPUT_PRICE_PER_1M = 1.25
_DEFAULT_CHAT_OUTPUT_PRICE_PER_1M = 10.00


def chat_token_cost(usage: Any, model_name: str) -> float:
    """Compute chat-completion cost from token usage using the model registry."""
    if not usage:
        return 0.0
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if input_tokens is not None or output_tokens is not None:
        try:
            from deepr.providers.anthropic_provider import ANTHROPIC_CACHE_PRICING
            from deepr.providers.registry import get_token_pricing

            regular_input = int(input_tokens or 0)
            output = int(output_tokens or 0)
            cache_creation = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
            cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            prices = get_token_pricing(model_name, input_tokens=regular_input + cache_creation + cache_read)
            input_price = prices.get("input", _DEFAULT_CHAT_INPUT_PRICE_PER_1M)
            output_price = prices.get("output", _DEFAULT_CHAT_OUTPUT_PRICE_PER_1M)
            cache_rates = next(
                (
                    rates
                    for model_prefix, rates in ANTHROPIC_CACHE_PRICING.items()
                    if model_name.startswith(model_prefix)
                ),
                {
                    "cache_write": round(input_price * 1.25, 6),
                    "cache_read": round(input_price * 0.10, 6),
                },
            )
            return (
                regular_input / 1_000_000 * input_price
                + output / 1_000_000 * output_price
                + cache_creation / 1_000_000 * cache_rates["cache_write"]
                + cache_read / 1_000_000 * cache_rates["cache_read"]
            )
        except Exception:
            logger.debug("Anthropic chat pricing lookup failed; using zero cost", exc_info=True)
            return 0.0
    try:
        from deepr.providers.registry import get_token_pricing

        prices = get_token_pricing(model_name)
        input_price = prices.get("input", _DEFAULT_CHAT_INPUT_PRICE_PER_1M)
        output_price = prices.get("output", _DEFAULT_CHAT_OUTPUT_PRICE_PER_1M)
    except Exception:
        input_price = _DEFAULT_CHAT_INPUT_PRICE_PER_1M
        output_price = _DEFAULT_CHAT_OUTPUT_PRICE_PER_1M
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0

    cached_tokens = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached_tokens = getattr(details, "cached_tokens", 0) or 0
    uncached_input = max(prompt_tokens - cached_tokens, 0)

    input_cost = (uncached_input / 1_000_000) * input_price + (cached_tokens / 1_000_000) * input_price * 0.5
    output_cost = (completion_tokens / 1_000_000) * output_price
    return input_cost + output_cost


def chat_usage_tokens(usage: Any | None) -> tuple[int, int]:
    if not usage:
        return 0, 0
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    if prompt_tokens or completion_tokens:
        return prompt_tokens, completion_tokens
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    cache_creation = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    return input_tokens + cache_creation + cache_read, output_tokens


def chat_generation_estimate(selected_model: ModelConfig) -> float:
    """Return a conservative preflight estimate for one expert chat turn."""
    estimate = float(getattr(selected_model, "cost_estimate", 0.0) or 0.0)
    if estimate <= 0:
        try:
            from deepr.providers.registry import get_cost_estimate

            estimate = float(get_cost_estimate(selected_model.model))
        except Exception:
            estimate = 0.05
    return max(estimate, 0.01)


def check_chat_generation_budget(
    cost_safety: Any,
    session_id: str,
    selected_model: ModelConfig,
) -> tuple[bool, str, float]:
    """Check cost safety before dispatching any metered chat-turn path."""
    estimated_cost = chat_generation_estimate(selected_model)
    allowed, reason, _needs_confirmation = cost_safety.check_operation(
        session_id=session_id,
        operation_type="expert_chat",
        estimated_cost=estimated_cost,
        require_confirmation=False,
    )
    return allowed, reason, estimated_cost


def chat_generation_budget_denial(
    selected_model: ModelConfig,
    reason: str,
    estimated_cost: float,
) -> dict[str, Any]:
    """Build the reasoning-trace record for a denied chat turn."""
    return {
        "step": "chat_generation_budget",
        "timestamp": datetime.now(UTC).isoformat(),
        "selected_provider": selected_model.provider,
        "selected_model": selected_model.model,
        "estimated_cost": estimated_cost,
        "allowed": False,
        "reason": reason,
    }


def record_named_chat_cost(
    *,
    cost_safety: Any,
    session_id: str,
    usage: Any | None,
    model_name: str,
    operation_type: str,
    fallback_cost: float,
    cost_calculator: Callable[[Any, str], float],
    provider: str = "openai",
    details: str = "",
) -> float:
    """Record cost for auxiliary chat calls that keep their own operation name."""
    cost = cost_calculator(usage, model_name) if usage else fallback_cost
    tokens_input, tokens_output = chat_usage_tokens(usage)
    cost_safety.record_cost(
        session_id=session_id,
        operation_type=operation_type,
        actual_cost=cost,
        provider=provider,
        model=model_name,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        details=details,
    )
    return cost


def record_model_routing(
    *,
    reasoning_trace: list[dict[str, Any]],
    thought_stream: Any,
    selected_model: ModelConfig,
    query: str,
) -> None:
    """Append the standard model-routing trace and thought-stream event."""
    reasoning_trace.append(
        {
            "step": "model_routing",
            "timestamp": datetime.now(UTC).isoformat(),
            "query": query[:100],
            "selected_provider": selected_model.provider,
            "selected_model": selected_model.model,
            "cost_estimate": selected_model.cost_estimate,
            "confidence": selected_model.confidence,
            "reasoning_effort": selected_model.reasoning_effort,
        }
    )
    thought_stream.emit(
        ThoughtType.PLAN_STEP,
        f"Selected model: {selected_model.model}",
        private_payload={
            "provider": selected_model.provider,
            "cost_estimate": selected_model.cost_estimate,
            "reasoning_effort": selected_model.reasoning_effort,
        },
        confidence=selected_model.confidence,
    )
