"""Provider-enforceable token and dollar envelopes for bounded model calls."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite

from deepr.providers.registry_pricing import (
    get_resolved_model_capability,
    get_resolved_token_pricing,
    get_token_pricing,
    provider_matches_model_contract,
)

CHAT_SERIALIZATION_TOKEN_ALLOWANCE = 2_048
EMBEDDING_SERIALIZATION_TOKEN_ALLOWANCE = 8


class MeteredEnvelopeError(ValueError):
    """A model call cannot be proven to fit inside its dollar ceiling."""


@dataclass(frozen=True)
class TokenCostEnvelope:
    """Conservative prompt/output bounds priced before provider dispatch."""

    input_tokens: int
    output_tokens: int
    cost_usd: float


def bounded_chat_envelope(
    *,
    provider: str,
    model: str,
    prompt_parts: tuple[str, ...],
    budget_usd: float,
    maximum_output_tokens: int,
    minimum_output_tokens: int = 1,
) -> TokenCostEnvelope:
    """Fit a chat call into a known-price ceiling using provider token caps.

    UTF-8 byte length is a conservative upper bound on text tokens. The fixed
    allowance covers message framing and provider-side chat serialization.
    """
    if not isfinite(budget_usd) or budget_usd <= 0:
        raise MeteredEnvelopeError("A finite positive paid-call budget is required")
    if maximum_output_tokens < 1 or minimum_output_tokens < 1:
        raise MeteredEnvelopeError("Output token limits must be positive")
    capability = get_resolved_model_capability(model)
    if capability is None:
        raise MeteredEnvelopeError(f"No trusted token pricing exists for model {model!r}")
    if not provider_matches_model_contract(provider, capability.provider):
        raise MeteredEnvelopeError(
            f"Provider {provider!r} cannot execute model {model!r}; the registry assigns it to {capability.provider!r}"
        )
    input_tokens = CHAT_SERIALIZATION_TOKEN_ALLOWANCE + sum(len(part.encode("utf-8")) for part in prompt_parts)
    context_remaining = capability.context_window - input_tokens
    if context_remaining < minimum_output_tokens:
        raise MeteredEnvelopeError(
            f"Bounded prompt leaves fewer than {minimum_output_tokens} output tokens "
            f"inside the {capability.context_window}-token context window"
        )
    pricing = get_token_pricing(model, input_tokens=input_tokens)
    input_cost = input_tokens * pricing["input"] / 1_000_000
    output_rate = pricing["output"] / 1_000_000
    if output_rate <= 0:
        raise MeteredEnvelopeError(f"No positive output-token price exists for model {model!r}")
    affordable_output = floor((budget_usd - input_cost) / output_rate)
    provider_output_limit = capability.max_output_tokens or maximum_output_tokens
    output_tokens = min(maximum_output_tokens, affordable_output, context_remaining, provider_output_limit)
    if output_tokens < minimum_output_tokens:
        raise MeteredEnvelopeError(
            f"Budget ${budget_usd:.6f} cannot cover the bounded prompt and "
            f"minimum {minimum_output_tokens} output tokens"
        )
    cost_usd = input_cost + output_tokens * output_rate
    return TokenCostEnvelope(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )


def bounded_embedding_envelope(
    *,
    model: str,
    inputs: tuple[str, ...],
) -> TokenCostEnvelope:
    """Price a bounded embedding request without an unknown-model fallback."""
    input_tokens = EMBEDDING_SERIALIZATION_TOKEN_ALLOWANCE + sum(len(value.encode("utf-8")) for value in inputs)
    pricing = get_resolved_token_pricing(model, input_tokens=input_tokens)
    if pricing is None or pricing.get("input", 0.0) <= 0 or pricing.get("output", 0.0) != 0:
        raise MeteredEnvelopeError(f"No trusted input-only token pricing exists for model {model!r}")
    cost_usd = input_tokens * pricing["input"] / 1_000_000
    if not isfinite(cost_usd) or cost_usd <= 0:
        raise MeteredEnvelopeError("Embedding cost ceiling must be finite and positive")
    return TokenCostEnvelope(input_tokens=input_tokens, output_tokens=0, cost_usd=cost_usd)


__all__ = [
    "MeteredEnvelopeError",
    "TokenCostEnvelope",
    "bounded_chat_envelope",
    "bounded_embedding_envelope",
]
