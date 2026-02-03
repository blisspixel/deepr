"""Model capabilities registry for dynamic routing.

Defines capabilities, costs, and specializations for all supported models across providers.
Used by ModelRouter to make intelligent routing decisions.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ModelCapability:
    """Capability specification for a model."""
    provider: str
    model: str
    cost_per_query: float  # Average cost in USD
    latency_ms: int  # Average latency in milliseconds
    context_window: int  # Max context window in tokens
    specializations: List[str]  # Areas where this model excels
    strengths: List[str]  # Key strengths
    weaknesses: List[str]  # Known limitations
    input_cost_per_1m: float = 0.0  # Cost per 1M input tokens (USD)
    output_cost_per_1m: float = 0.0  # Cost per 1M output tokens (USD)


# Model capabilities registry
MODEL_CAPABILITIES: Dict[str, ModelCapability] = {
    # OpenAI Models
    "openai/gpt-5.2": ModelCapability(
        provider="openai",
        model="gpt-5.2",
        cost_per_query=0.25,
        latency_ms=2000,  # Fast for planning tasks
        context_window=128_000,
        specializations=["reasoning", "planning", "curriculum", "synthesis"],
        strengths=[
            "Enhanced reasoning capabilities",
            "Excellent at structured output (JSON)",
            "Fast curriculum/planning generation",
            "Better at complex multi-step problems",
            "Adaptive reasoning effort"
        ],
        weaknesses=[
            "Higher cost than gpt-4o",
            "Overkill for simple queries"
        ],
        input_cost_per_1m=2.50,
        output_cost_per_1m=10.00,
    ),

    "openai/o3-deep-research": ModelCapability(
        provider="openai",
        model="o3-deep-research",
        cost_per_query=0.50,
        latency_ms=120_000,
        context_window=128_000,
        specializations=["research", "analysis", "strategic_planning"],
        strengths=[
            "Extended reasoning chains",
            "Deep multi-step analysis",
            "High quality comprehensive research",
        ],
        weaknesses=[
            "Expensive",
            "Slow (2-5 minutes)",
        ],
        input_cost_per_1m=11.0,
        output_cost_per_1m=44.0,
    ),

    "openai/o4-mini-deep-research": ModelCapability(
        provider="openai",
        model="o4-mini-deep-research",
        cost_per_query=2.00,
        latency_ms=60_000,  # 60 seconds average
        context_window=128_000,
        specializations=["research", "analysis", "strategic_planning"],
        strengths=[
            "Extended reasoning chains",
            "Deep multi-step analysis",
            "High quality comprehensive research",
            "Excellent for strategic decisions"
        ],
        weaknesses=[
            "Expensive ($2 per query)",
            "Slow (30-60 seconds minimum)",
            "Overkill for simple queries"
        ],
        input_cost_per_1m=1.10,
        output_cost_per_1m=4.40,
    ),

    # xAI Models (Grok)
    "xai/grok-4-fast": ModelCapability(
        provider="xai",
        model="grok-4-fast",
        cost_per_query=0.01,
        latency_ms=1000,
        context_window=128_000,
        specializations=["speed", "factual", "news"],
        strengths=[
            "Very fast responses",
            "Very cheap ($0.01)",
            "Good for simple factual queries",
            "Real-time information access"
        ],
        weaknesses=[
            "Less capable at complex reasoning",
            "Not ideal for multi-step analysis",
            "Lower quality for strategic work"
        ],
        input_cost_per_1m=0.20,
        output_cost_per_1m=0.50,
    ),

    # Google Models (Gemini)
    "gemini/gemini-3-pro": ModelCapability(
        provider="gemini",
        model="gemini-3-pro",
        cost_per_query=0.15,
        latency_ms=4000,
        context_window=1_000_000,  # 1M tokens!
        specializations=["large_context", "document_analysis", "synthesis"],
        strengths=[
            "Massive 1M token context window",
            "Excellent for document analysis",
            "Good at synthesizing large amounts of info",
            "Reasonable cost for the context size"
        ],
        weaknesses=[
            "Slower than fast models",
            "Not as strong at pure reasoning",
            "Context size overkill for simple queries"
        ],
        input_cost_per_1m=1.25,
        output_cost_per_1m=5.00,
    ),

    "gemini/deep-research": ModelCapability(
        provider="gemini",
        model="deep-research-pro-preview-12-2025",
        cost_per_query=1.00,
        latency_ms=600_000,  # 5-20 minutes
        context_window=1_000_000,
        specializations=["research", "analysis", "synthesis"],
        strengths=[
            "Autonomous multi-step research with Google Search",
            "Structured reports with citations",
            "File grounding via File Search Stores",
            "Background async execution"
        ],
        weaknesses=[
            "Slow (5-20 minutes per job)",
            "~$1 per job",
            "Experimental API (may change)"
        ],
        input_cost_per_1m=1.25,
        output_cost_per_1m=5.00,
    ),

    "gemini/gemini-2.5-flash": ModelCapability(
        provider="gemini",
        model="gemini-2.5-flash",
        cost_per_query=0.002,
        latency_ms=1500,
        context_window=128_000,
        specializations=["speed", "cost", "general"],
        strengths=[
            "Very cheap ($0.002)",
            "Fast responses",
            "Good for general queries"
        ],
        weaknesses=[
            "Lower quality than premium models",
            "Not ideal for complex reasoning"
        ],
        input_cost_per_1m=0.075,
        output_cost_per_1m=0.30,
    ),

    # Anthropic Models
    # Note: Anthropic does NOT have a turnkey deep research API like OpenAI/Gemini.
    # Research capability is achieved via Extended Thinking + tool use + our orchestration.
    # For research, we recommend Opus 4.5 - best reasoning at ~$0.80/query.
    
    "anthropic/claude-opus-4-5": ModelCapability(
        provider="anthropic",
        model="claude-opus-4-5",
        cost_per_query=0.80,  # Estimated with 32K thinking budget
        latency_ms=15000,     # Slower due to extended thinking
        context_window=200_000,
        specializations=["research", "reasoning", "coding", "analysis", "complex_tasks"],
        strengths=[
            "Best Claude model for research",
            "Excellent at complex multi-step reasoning",
            "Strong synthesis and analysis",
            "Extended Thinking with high token budget",
            "66% cheaper than Opus 4 ($5 vs $15 input)"
        ],
        weaknesses=[
            "No native deep research API (requires orchestration)",
            "Slower than Sonnet (~15s vs ~3s)",
            "Higher cost than Sonnet (~$0.80 vs ~$0.48/query)"
        ],
        input_cost_per_1m=5.00,
        output_cost_per_1m=25.00,
    ),

    "anthropic/claude-sonnet-4-5": ModelCapability(
        provider="anthropic",
        model="claude-sonnet-4-5",
        cost_per_query=0.48,  # Estimated with 16K thinking budget
        latency_ms=3000,
        context_window=200_000,
        specializations=["reasoning", "coding", "analysis", "balanced"],
        strengths=[
            "Good balance of quality and cost",
            "Fast responses (~3s)",
            "Extended Thinking support",
            "Large context window"
        ],
        weaknesses=[
            "Less capable than Opus for complex research",
            "No native deep research API"
        ],
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
    ),

    "anthropic/claude-haiku-4-5": ModelCapability(
        provider="anthropic",
        model="claude-haiku-4-5",
        cost_per_query=0.05,
        latency_ms=1500,
        context_window=200_000,
        specializations=["speed", "cost", "general"],
        strengths=[
            "Very fast responses",
            "Lowest cost ($1/$5 per MTok)",
            "Good for simple queries",
            "Large context window"
        ],
        weaknesses=[
            "No Extended Thinking support",
            "Not suitable for deep research",
            "Less capable reasoning"
        ],
        input_cost_per_1m=1.00,
        output_cost_per_1m=5.00,
    ),
}


def get_token_pricing(model: str) -> Dict[str, float]:
    """Get per-token pricing for a model.

    Searches registry by model name across all providers.

    Args:
        model: Model name (e.g., "o3-deep-research", "grok-4-fast")

    Returns:
        Dict with "input" and "output" costs per 1M tokens.
        Returns default pricing if model not found.
    """
    # Try exact match first
    for cap in MODEL_CAPABILITIES.values():
        if cap.model == model and cap.input_cost_per_1m > 0:
            return {"input": cap.input_cost_per_1m, "output": cap.output_cost_per_1m}

    # Try partial match (e.g., "o4-mini-deep-research-2025-06-26" matches "o4-mini-deep-research")
    for cap in MODEL_CAPABILITIES.values():
        if cap.model in model and cap.input_cost_per_1m > 0:
            return {"input": cap.input_cost_per_1m, "output": cap.output_cost_per_1m}

    # Default to o4-mini pricing
    default = MODEL_CAPABILITIES.get("openai/o4-mini-deep-research")
    if default:
        return {"input": default.input_cost_per_1m, "output": default.output_cost_per_1m}
    return {"input": 1.10, "output": 4.40}


def get_cost_estimate(model: str) -> float:
    """Get per-query cost estimate for a model.

    Args:
        model: Model name

    Returns:
        Estimated cost per query in USD. Returns 0.20 if model not found.
    """
    for cap in MODEL_CAPABILITIES.values():
        if cap.model == model:
            return cap.cost_per_query
    # Partial match
    for cap in MODEL_CAPABILITIES.values():
        if cap.model in model:
            return cap.cost_per_query
    return 0.20


def get_model_capability(provider: str, model: str) -> Optional[ModelCapability]:
    """Get capability specification for a model.

    Args:
        provider: Provider name (openai, xai, gemini, anthropic)
        model: Model name

    Returns:
        ModelCapability or None if not found
    """
    key = f"{provider}/{model}"
    return MODEL_CAPABILITIES.get(key)


def get_models_by_specialization(specialization: str) -> List[ModelCapability]:
    """Get all models that specialize in a given area.

    Args:
        specialization: Specialization to filter by

    Returns:
        List of models with that specialization, sorted by cost
    """
    matching = [
        cap for cap in MODEL_CAPABILITIES.values()
        if specialization in cap.specializations
    ]
    return sorted(matching, key=lambda x: x.cost_per_query)


def get_cheapest_model() -> ModelCapability:
    """Get the cheapest available model.

    Returns:
        ModelCapability for cheapest model
    """
    return min(MODEL_CAPABILITIES.values(), key=lambda x: x.cost_per_query)


def get_fastest_model() -> ModelCapability:
    """Get the fastest available model.

    Returns:
        ModelCapability for fastest model
    """
    return min(MODEL_CAPABILITIES.values(), key=lambda x: x.latency_ms)


def get_largest_context_model() -> ModelCapability:
    """Get the model with largest context window.

    Returns:
        ModelCapability for model with largest context
    """
    return max(MODEL_CAPABILITIES.values(), key=lambda x: x.context_window)
