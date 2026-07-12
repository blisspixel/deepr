"""Pricing lookup helpers for the provider model registry."""

from __future__ import annotations

import logging

from .registry import MODEL_CAPABILITIES, ModelCapability

logger = logging.getLogger(__name__)

_MODEL_ALIASES: dict[str, str] = {
    "gemini-deep-research": "deep-research-pro-preview-12-2025",
    "deep-research": "deep-research-pro-preview-12-2025",
}

_TIERED_PRICING: dict[str, tuple[int, float, float]] = {
    "gemini-3.1-pro-preview": (200_000, 2.0, 1.5),
    "gemini-3-pro-preview": (200_000, 2.0, 1.5),
}

# Specialized input-only models stay outside the chat/research capability
# roster so generic cheapest-model routing cannot select an embedding model.
# Source: official OpenAI model pricing, checked 2026-07-12.
_SPECIALIZED_TOKEN_PRICING: dict[str, dict[str, float]] = {
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}


def _normalize_model_name(name: str) -> str:
    """Normalize a model name so dot/hyphen variants compare equal."""
    if not name:
        return name
    return name.replace(".", "-").lower()


def _resolved_model_needle(model: str) -> str:
    """Resolve caller aliases and normalize provider model IDs."""
    resolved = _MODEL_ALIASES.get(model, model)
    return _normalize_model_name(resolved)


def _find_model_capability(model: str, *, require_token_pricing: bool = False) -> ModelCapability | None:
    """Find the most specific registry entry for a provider model string."""
    needle = _resolved_model_needle(model)
    candidates = list(MODEL_CAPABILITIES.values())
    if require_token_pricing:
        candidates = [cap for cap in candidates if cap.input_cost_per_1m > 0]

    for cap in candidates:
        if _normalize_model_name(cap.model) == needle:
            return cap

    for cap in sorted(candidates, key=lambda c: len(c.model or ""), reverse=True):
        if _model_matches(_normalize_model_name(cap.model), needle):
            return cap

    return None


def _model_matches(cap_model: str, needle: str) -> bool:
    """Return true when a registry model matches a provider model id."""
    if cap_model in needle:
        return True
    for suffix in ("multi-agent", "non-reasoning", "reasoning"):
        marker = f"-{suffix}"
        if cap_model.endswith(marker):
            prefix = cap_model[: -len(marker)]
            return needle.startswith(f"{prefix}-") and needle.endswith(marker)
    return False


def _with_token_tier(model: str, prices: dict[str, float], input_tokens: int | None) -> dict[str, float]:
    """Apply prompt-size token tiers to a rate dictionary."""
    if input_tokens is None:
        return prices
    needle = _resolved_model_needle(model)
    for tiered_model, (threshold, input_mult, output_mult) in _TIERED_PRICING.items():
        if _normalize_model_name(tiered_model) in needle and input_tokens > threshold:
            tiered = dict(prices)
            tiered["input"] = round(tiered["input"] * input_mult, 6)
            if "output" in tiered:
                tiered["output"] = round(tiered["output"] * output_mult, 6)
            if "cached_input" in tiered:
                tiered["cached_input"] = round(tiered["cached_input"] * input_mult, 6)
            return tiered
    return prices


def get_token_pricing(model: str, input_tokens: int | None = None) -> dict[str, float]:
    """Get input and output pricing per 1M tokens for a model."""
    normalized = _resolved_model_needle(model)
    for model_name, pricing in _SPECIALIZED_TOKEN_PRICING.items():
        if _normalize_model_name(model_name) == normalized:
            return dict(pricing)
    cap = _find_model_capability(model, require_token_pricing=True)
    if cap is not None:
        return _with_token_tier(
            model,
            {"input": cap.input_cost_per_1m, "output": cap.output_cost_per_1m},
            input_tokens,
        )

    logger.warning(
        "No registry pricing for model %r; defaulting to o4-mini rates ($1.10/$4.40 per 1M). "
        "Add the model to deepr/providers/registry.py to bill it correctly.",
        model,
    )
    default = MODEL_CAPABILITIES.get("openai/o4-mini")
    if default:
        return {"input": default.input_cost_per_1m, "output": default.output_cost_per_1m}
    return {"input": 1.10, "output": 4.40}


def get_cached_input_pricing(model: str, input_tokens: int | None = None) -> float | None:
    """Get per-1M-token cached-input pricing for a model if documented."""
    cap = _find_model_capability(model, require_token_pricing=True)
    if cap is None or cap.cached_input_cost_per_1m is None:
        return None
    prices = _with_token_tier(model, {"cached_input": cap.cached_input_cost_per_1m}, input_tokens)
    return prices["cached_input"]


def get_cost_estimate(model: str, input_tokens: int | None = None) -> float:
    """Get the preflight per-query cost estimate for a model."""
    needle = _resolved_model_needle(model)
    cap = _find_model_capability(model)
    base = cap.cost_per_query if cap is not None else 0.20

    if input_tokens is not None:
        for tiered_model, (threshold, input_mult, _output_mult) in _TIERED_PRICING.items():
            if _normalize_model_name(tiered_model) in needle and input_tokens > threshold:
                return base * input_mult

    return base


def get_resolved_model_capability(model: str) -> ModelCapability | None:
    """Return the exact registry pricing/context contract for a model alias."""
    return _find_model_capability(model, require_token_pricing=True)
