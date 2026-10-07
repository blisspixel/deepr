"""Public releases reviewed 2026-10-06, pending Deepr adapter validation.

Owning sources and promotion limits: docs/design/provider-currency-2026-10.md.
Metadata does not prove account access, request compatibility, or answer quality.
"""

from .model_capability import ModelCapability


def _candidate(
    provider: str,
    model: str,
    context: int,
    output_limit: int | None,
    input_rate: float,
    cached_rate: float,
    output_rate: float,
    cache_write_rate: float | None,
    qualification: str,
) -> ModelCapability:
    return ModelCapability(
        provider=provider,
        model=model,
        cost_per_query=round(input_rate * 0.01 + output_rate * 0.001, 6),
        latency_ms=2500,
        context_window=context,
        specializations=["reasoning", "coding", "large_context"],
        strengths=["Public API model listed by its provider on 2026-10-06"],
        weaknesses=[
            "Preview only: request and settlement compatibility pending",
            "Latency placeholder (2500 ms), not benchmarked",
            "Per-query estimate assumes 10K input and 1K output tokens",
            qualification,
        ],
        input_cost_per_1m=input_rate,
        output_cost_per_1m=output_rate,
        cached_input_cost_per_1m=cached_rate,
        cache_write_cost_per_1m=cache_write_rate,
        max_output_tokens=output_limit,
        preview_only=True,
    )


REVIEWED_CAPABILITIES: dict[str, ModelCapability] = {
    "openai/gpt-6-astra": _candidate(
        "openai",
        "gpt-6-astra",
        1_050_000,
        128_000,
        10.0,
        1.0,
        50.0,
        12.5,
        "922K max input; long-context rates above 272K; reasoning none unsupported",
    ),
    "openai/gpt-6.1-sol": _candidate(
        "openai",
        "gpt-6.1-sol",
        1_050_000,
        128_000,
        2.0,
        0.1,
        10.0,
        2.5,
        "922K max input; long-context rates above 272K; tools require Responses",
    ),
    "openai/gpt-6-luna": _candidate(
        "openai",
        "gpt-6-luna",
        1_050_000,
        128_000,
        0.1,
        0.01,
        0.5,
        0.125,
        "922K max input; long-context rates above 272K; Chat tools require reasoning none",
    ),
    "anthropic/claude-fable-5-1": _candidate(
        "anthropic",
        "claude-fable-5-1",
        1_000_000,
        128_000,
        10.0,
        0.25,
        50.0,
        12.5,
        "Adaptive thinking; cache write is 5-minute price; 1-hour writes cost more",
    ),
    "anthropic/claude-opus-5-5": _candidate(
        "anthropic",
        "claude-opus-5-5",
        1_000_000,
        128_000,
        4.0,
        0.2,
        20.0,
        5.0,
        "Adaptive thinking; cache write is 5-minute price; 1-hour writes cost more",
    ),
    "anthropic/claude-sonnet-5-5": _candidate(
        "anthropic",
        "claude-sonnet-5-5",
        1_000_000,
        128_000,
        2.0,
        0.2,
        10.0,
        2.5,
        "Adaptive thinking; cache write is 5-minute price; 1-hour writes cost more",
    ),
    "gemini/gemini-3.8-flash": _candidate(
        "gemini",
        "gemini-3.8-flash",
        1_048_576,
        65_536,
        1.5,
        0.15,
        7.5,
        None,
        "January 2027 price caps; temporary discount through 2026-12-31; cache storage extra",
    ),
    "xai/grok-4-7": _candidate(
        "xai",
        "grok-4-7",
        500_000,
        None,
        2.0,
        0.5,
        6.0,
        None,
        "Conservative long-context cap from 200K; encrypted reasoning needs adapter review",
    ),
}
