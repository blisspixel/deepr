"""Shared model capability contract for provider registries."""

from dataclasses import dataclass


@dataclass
class ModelCapability:
    """Capability and pricing specification for one model route."""

    provider: str
    model: str
    cost_per_query: float
    latency_ms: int
    context_window: int
    specializations: list[str]
    strengths: list[str]
    weaknesses: list[str]
    input_cost_per_1m: float = 0.0
    output_cost_per_1m: float = 0.0
    cached_input_cost_per_1m: float | None = None
    cache_write_cost_per_1m: float | None = None
    max_output_tokens: int | None = None
    deprecated: bool = False
    successor: str | None = None
    preview_only: bool = False
