"""Dated, preview-only OpenRouter model and exact-upstream catalog.

Prices are proposed request caps for one pinned upstream endpoint per model,
checked against OpenRouter's public endpoint metadata on 2026-09-01.
OpenRouter dispatch is not implemented.
"""

from .model_capability import ModelCapability

OPENROUTER_CAPABILITIES: dict[str, ModelCapability] = {
    "openrouter/openai/gpt-5.6-sol": ModelCapability(
        provider="openrouter",
        model="openai/gpt-5.6-sol",
        cost_per_query=0.20,
        latency_ms=2500,
        context_window=1_050_000,
        specializations=["reasoning", "coding", "agentic", "synthesis", "large_context"],
        strengths=["Exact OpenRouter slug", "OpenAI frontier model through one gateway"],
        weaknesses=["Preview only", "Catalog price and upstream availability can change"],
        input_cost_per_1m=2.00,
        output_cost_per_1m=10.00,
        cached_input_cost_per_1m=0.20,
        cache_write_cost_per_1m=2.50,
        max_output_tokens=128_000,
        preview_only=True,
    ),
    "openrouter/anthropic/claude-sonnet-5": ModelCapability(
        provider="openrouter",
        model="anthropic/claude-sonnet-5",
        cost_per_query=0.20,
        latency_ms=2200,
        context_window=1_000_000,
        specializations=["reasoning", "coding", "agentic", "synthesis", "large_context"],
        strengths=["Exact OpenRouter slug", "Anthropic model through one gateway"],
        weaknesses=["Preview only", "Catalog price and upstream availability can change"],
        input_cost_per_1m=2.00,
        output_cost_per_1m=10.00,
        cache_write_cost_per_1m=4.00,
        preview_only=True,
    ),
    "openrouter/google/gemini-3.6-flash": ModelCapability(
        provider="openrouter",
        model="google/gemini-3.6-flash",
        cost_per_query=0.075,
        latency_ms=1200,
        context_window=1_048_576,
        specializations=["speed", "coding", "agentic", "multimodal", "large_context"],
        strengths=["Exact OpenRouter slug", "Google model through one gateway"],
        weaknesses=["Preview only", "Catalog price and upstream availability can change"],
        input_cost_per_1m=0.75,
        output_cost_per_1m=3.75,
        cached_input_cost_per_1m=0.075,
        cache_write_cost_per_1m=0.0416666666666667,
        max_output_tokens=65_536,
        preview_only=True,
    ),
    "openrouter/x-ai/grok-4.6": ModelCapability(
        provider="openrouter",
        model="x-ai/grok-4.6",
        cost_per_query=0.10,
        latency_ms=1800,
        context_window=500_000,
        specializations=["reasoning", "coding", "knowledge", "multimodal"],
        strengths=["Exact OpenRouter slug", "xAI model through one gateway"],
        weaknesses=["Preview only", "Catalog price and upstream availability can change"],
        input_cost_per_1m=2.00,
        output_cost_per_1m=6.00,
        cached_input_cost_per_1m=0.50,
        cache_write_cost_per_1m=0.0,
        preview_only=True,
    ),
    "openrouter/qwen/qwen3.8-flash": ModelCapability(
        provider="openrouter",
        model="qwen/qwen3.8-flash",
        cost_per_query=0.015,
        latency_ms=1400,
        context_window=1_000_000,
        specializations=["reasoning", "coding", "agentic", "multimodal", "cost"],
        strengths=["Exact OpenRouter slug", "Open-weight model family through one gateway"],
        weaknesses=["Preview only", "Catalog price and upstream availability can change"],
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.47,
        cached_input_cost_per_1m=0.016,
        cache_write_cost_per_1m=0.20,
        max_output_tokens=131_072,
        preview_only=True,
    ),
    "openrouter/moonshotai/kimi-k3": ModelCapability(
        provider="openrouter",
        model="moonshotai/kimi-k3",
        cost_per_query=0.30,
        latency_ms=1900,
        context_window=1_048_576,
        specializations=["reasoning", "coding", "agentic", "multimodal", "large_context"],
        strengths=["Exact OpenRouter slug", "Open-weight model family through one gateway"],
        weaknesses=["Preview only", "Catalog price and upstream availability can change"],
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
        cached_input_cost_per_1m=0.30,
        cache_write_cost_per_1m=0.0,
        max_output_tokens=943_718,
        preview_only=True,
    ),
    "openrouter/deepseek/deepseek-v4-flash-0731": ModelCapability(
        provider="openrouter",
        model="deepseek/deepseek-v4-flash-0731",
        cost_per_query=0.044,
        latency_ms=1500,
        context_window=1_048_576,
        specializations=["reasoning", "coding", "agentic", "cost", "large_context"],
        strengths=["Exact OpenRouter slug", "Open-weight model family through one gateway"],
        weaknesses=["Preview only", "Catalog price and upstream availability can change"],
        input_cost_per_1m=0.44,
        output_cost_per_1m=1.32,
        cached_input_cost_per_1m=0.014,
        cache_write_cost_per_1m=0.44,
        max_output_tokens=384_000,
        preview_only=True,
    ),
}

# Exact upstream endpoint tags proposed for the future gateway request. These
# are not dispatch authority. The live write-free catalog check must prove the
# endpoint still exists and fits the registered finite envelope.
OPENROUTER_UPSTREAM_TAGS: dict[str, str] = {
    "openai/gpt-5.6-sol": "openai",
    "anthropic/claude-sonnet-5": "anthropic",
    "google/gemini-3.6-flash": "google-ai-studio",
    "x-ai/grok-4.6": "xai/zdr",
    "qwen/qwen3.8-flash": "alibaba",
    "moonshotai/kimi-k3": "moonshotai/mxfp4",
    "deepseek/deepseek-v4-flash-0731": "deepseek",
}

# OpenRouter endpoint metadata currently reports explicit cache-write rates for
# four routes. Its official prompt-caching guide documents free writes for xAI
# and Moonshot and prompt-rate writes for DeepSeek. Missing or changed evidence
# fails the live check instead of silently becoming a zero-cost component.
OPENROUTER_CACHE_WRITE_PRICE_SOURCES: dict[str, str] = {
    "openai/gpt-5.6-sol": "endpoint_metadata",
    "anthropic/claude-sonnet-5": "endpoint_metadata",
    "google/gemini-3.6-flash": "endpoint_metadata",
    "x-ai/grok-4.6": "official_free",
    "qwen/qwen3.8-flash": "endpoint_metadata",
    "moonshotai/kimi-k3": "official_free",
    "deepseek/deepseek-v4-flash-0731": "prompt_equivalent",
}
