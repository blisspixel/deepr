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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
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
        ]
    ),

    # Anthropic Models
    "anthropic/claude-sonnet-4-5": ModelCapability(
        provider="anthropic",
        model="claude-sonnet-4-5",
        cost_per_query=0.25,
        latency_ms=3000,
        context_window=200_000,
        specializations=["reasoning", "coding", "analysis"],
        strengths=[
            "Strong reasoning capabilities",
            "Excellent at following instructions",
            "Good coding abilities",
            "Large context window"
        ],
        weaknesses=[
            "Higher cost",
            "Not specialized for research"
        ]
    ),
}


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
