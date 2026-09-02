"""Pricing lookup helpers for the provider model registry."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .registry import MODEL_CAPABILITIES, ModelCapability

logger = logging.getLogger(__name__)

_MODEL_ALIASES: dict[str, str] = {
    "gpt-5.6": "gpt-5.6-sol",
    "grok-build": "grok-build-0.1",
    "grok-code-fast": "grok-build-0.1",
    "grok-code-fast-1": "grok-build-0.1",
    "grok-code-fast-1-0825": "grok-build-0.1",
    "gemini-deep-research": "deep-research-pro-preview-12-2025",
    "deep-research": "deep-research-pro-preview-12-2025",
    "gemini-pro": "gemini-3.1-pro-preview",
    "gemini-3.1-pro": "gemini-3.1-pro-preview",
    "gemini-flash": "gemini-3.6-flash",
    "gemini-flash-lite": "gemini-3.5-flash-lite",
}


@dataclass(frozen=True)
class _TokenPricingTier:
    threshold: int
    input_multiplier: float
    output_multiplier: float
    inclusive: bool


_TIERED_PRICING: dict[str, _TokenPricingTier] = {
    # GPT-5.6 applies the long-context rate only above 272K input tokens.
    "gpt-5.6-sol": _TokenPricingTier(272_000, 2.0, 1.5, inclusive=False),
    "gpt-5.6-terra": _TokenPricingTier(272_000, 2.0, 1.5, inclusive=False),
    "gpt-5.6-luna": _TokenPricingTier(272_000, 2.0, 1.5, inclusive=False),
    # Google keeps the base tier through 200K prompt tokens and applies the
    # long-context tier only above 200K.
    "gemini-2.5-pro": _TokenPricingTier(200_000, 2.0, 1.5, inclusive=False),
    "gemini-3.1-pro-preview": _TokenPricingTier(200_000, 2.0, 1.5, inclusive=False),
    "gemini-3-pro-preview": _TokenPricingTier(200_000, 2.0, 1.5, inclusive=False),
    # xAI applies these Grok long-context rates at 200K prompt tokens and above.
    "grok-4-6": _TokenPricingTier(200_000, 2.0, 2.0, inclusive=True),
    "grok-build-0-1": _TokenPricingTier(200_000, 2.0, 2.0, inclusive=True),
    "grok-4-5": _TokenPricingTier(200_000, 2.0, 2.0, inclusive=True),
    "grok-4-3": _TokenPricingTier(200_000, 2.0, 2.0, inclusive=True),
    "grok-4-20-reasoning": _TokenPricingTier(200_000, 2.0, 2.0, inclusive=True),
    "grok-4-20-non-reasoning": _TokenPricingTier(200_000, 2.0, 2.0, inclusive=True),
    "grok-4-20-multi-agent": _TokenPricingTier(200_000, 2.0, 2.0, inclusive=True),
}

# Specialized input-only models stay outside the chat/research capability
# roster so generic cheapest-model routing cannot select an embedding model.
# Source: official OpenAI model pricing, checked 2026-07-12.
_SPECIALIZED_TOKEN_PRICING: dict[str, dict[str, float]] = {
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}
_SPECIALIZED_MODEL_PROVIDERS: dict[str, str] = {
    "text-embedding-3-small": "openai",
}


def _canonical_provider_name(provider: str) -> str:
    """Normalize only recognized provider identities used by model contracts."""
    normalized = provider.strip().casefold().replace("_", "-")
    collapsed = normalized.replace("-", "").replace(" ", "")
    aliases = {
        "anthropic": "anthropic",
        "azure": "azure",
        "azureopenai": "azure",
        "azurefoundry": "azure-foundry",
        "claude": "anthropic",
        "gemini": "gemini",
        "google": "gemini",
        "googleai": "gemini",
        "googlegenai": "gemini",
        "grok": "xai",
        "openai": "openai",
        "openrouter": "openrouter",
        "xai": "xai",
    }
    return aliases.get(collapsed, normalized)


def provider_matches_model_contract(provider: str, model_provider: str) -> bool:
    """Return whether a provider may use a registry model contract.

    Azure OpenAI deployments reuse OpenAI token and context contracts. Other
    providers must match the registry owner exactly after finite alias
    normalization. In particular, Azure Foundry is not treated as Azure
    OpenAI because its deployment pricing is a separate account boundary.
    """
    provider_key = _canonical_provider_name(provider)
    model_provider_key = _canonical_provider_name(model_provider)
    if not provider_key or not model_provider_key:
        return False
    if provider_key == model_provider_key:
        return True
    return provider_key == "azure" and model_provider_key == "openai"


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


def _token_tier_applies(input_tokens: int, tier: _TokenPricingTier) -> bool:
    """Evaluate one provider's documented long-context boundary."""
    return input_tokens >= tier.threshold if tier.inclusive else input_tokens > tier.threshold


def _with_token_tier(model: str, prices: dict[str, float], input_tokens: int | None) -> dict[str, float]:
    """Apply prompt-size token tiers to a rate dictionary."""
    if input_tokens is None:
        return prices
    needle = _resolved_model_needle(model)
    for tiered_model, tier in _TIERED_PRICING.items():
        if _model_matches(_normalize_model_name(tiered_model), needle) and _token_tier_applies(input_tokens, tier):
            tiered = dict(prices)
            if "input" in tiered:
                tiered["input"] = round(tiered["input"] * tier.input_multiplier, 6)
            if "output" in tiered:
                tiered["output"] = round(tiered["output"] * tier.output_multiplier, 6)
            if "cached_input" in tiered:
                tiered["cached_input"] = round(tiered["cached_input"] * tier.input_multiplier, 6)
            return tiered
    return prices


def get_token_pricing(model: str, input_tokens: int | None = None) -> dict[str, float]:
    """Get input and output pricing per 1M tokens for a model."""
    resolved = get_resolved_token_pricing(model, input_tokens=input_tokens)
    if resolved is not None:
        return resolved

    logger.warning(
        "No registry pricing for model %r; defaulting to o4-mini rates ($1.10/$4.40 per 1M). "
        "Add the model to deepr/providers/registry.py to bill it correctly.",
        model,
    )
    default = MODEL_CAPABILITIES.get("openai/o4-mini")
    if default:
        return {"input": default.input_cost_per_1m, "output": default.output_cost_per_1m}
    return {"input": 1.10, "output": 4.40}


def get_resolved_token_pricing(model: str, input_tokens: int | None = None) -> dict[str, float] | None:
    """Return trusted registered token pricing, without an estimation fallback."""
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
    return None


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
        for tiered_model, tier in _TIERED_PRICING.items():
            if _model_matches(_normalize_model_name(tiered_model), needle) and _token_tier_applies(input_tokens, tier):
                return base * tier.input_multiplier

    return base


def get_resolved_model_capability(model: str) -> ModelCapability | None:
    """Return the exact registry pricing/context contract for a model alias."""
    return _find_model_capability(model, require_token_pricing=True)


def get_resolved_model_contract_identity(model: str) -> tuple[str, str] | None:
    """Return the canonical provider and model identity for priced usage.

    Chat and research models resolve through their registry capability.
    Specialized input-only contracts are included even though generic model
    routing intentionally excludes them.
    """
    normalized = _resolved_model_needle(model)
    for model_name, provider in _SPECIALIZED_MODEL_PROVIDERS.items():
        if _normalize_model_name(model_name) == normalized:
            return provider, model_name
    capability = _find_model_capability(model, require_token_pricing=True)
    if capability is None:
        return None
    return capability.provider, capability.model
