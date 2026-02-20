"""Model capabilities registry for dynamic routing.

Defines capabilities, costs, and specializations for all supported models across providers.
Used by ModelRouter to make intelligent routing decisions.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelCapability:
    """Capability specification for a model."""

    provider: str
    model: str
    cost_per_query: float  # Average cost in USD
    latency_ms: int  # Average latency in milliseconds
    context_window: int  # Max context window in tokens
    specializations: list[str]  # Areas where this model excels
    strengths: list[str]  # Key strengths
    weaknesses: list[str]  # Known limitations
    input_cost_per_1m: float = 0.0  # Cost per 1M input tokens (USD)
    output_cost_per_1m: float = 0.0  # Cost per 1M output tokens (USD)


# Model capabilities registry
MODEL_CAPABILITIES: dict[str, ModelCapability] = {
    # OpenAI Models
    "openai/gpt-5.2": ModelCapability(
        provider="openai",
        model="gpt-5.2",
        cost_per_query=0.25,
        latency_ms=2000,
        context_window=400_000,
        specializations=["reasoning", "planning", "curriculum", "synthesis"],
        strengths=[
            "Frontier enterprise reasoning",
            "Excellent at structured output (JSON)",
            "400K context window",
            "Better at complex multi-step problems",
            "Adaptive reasoning effort",
        ],
        weaknesses=["Registration required", "Higher cost than gpt-5"],
        input_cost_per_1m=1.75,
        output_cost_per_1m=14.00,
    ),
    "openai/gpt-5": ModelCapability(
        provider="openai",
        model="gpt-5",
        cost_per_query=0.15,
        latency_ms=2500,
        context_window=400_000,
        specializations=["reasoning", "planning", "analysis", "synthesis"],
        strengths=[
            "Frontier-scale reasoning",
            "400K context window",
            "Deep multi-step analysis",
            "Code generation",
        ],
        weaknesses=["Registration required", "Higher cost than gpt-5-mini"],
        input_cost_per_1m=1.25,
        output_cost_per_1m=10.00,
    ),
    "openai/gpt-5-mini": ModelCapability(
        provider="openai",
        model="gpt-5-mini",
        cost_per_query=0.03,
        latency_ms=1500,
        context_window=400_000,
        specializations=["reasoning", "speed", "balanced"],
        strengths=[
            "Good reasoning at low cost",
            "Fast responses",
            "400K context window",
            "No registration required",
        ],
        weaknesses=["Less capable than gpt-5 for complex tasks"],
        input_cost_per_1m=0.25,
        output_cost_per_1m=2.00,
    ),
    "openai/gpt-4.1": ModelCapability(
        provider="openai",
        model="gpt-4.1",
        cost_per_query=0.04,
        latency_ms=2000,
        context_window=1_047_576,
        specializations=["reasoning", "planning", "synthesis", "large_context"],
        strengths=[
            "1M+ token context window",
            "Strong general-purpose reasoning",
            "No registration required",
            "Cost-effective for large documents",
        ],
        weaknesses=["Slower than mini/nano variants", "Not frontier-scale reasoning"],
        input_cost_per_1m=2.00,
        output_cost_per_1m=8.00,
    ),
    "openai/gpt-4.1-mini": ModelCapability(
        provider="openai",
        model="gpt-4.1-mini",
        cost_per_query=0.01,
        latency_ms=1200,
        context_window=1_047_576,
        specializations=["speed", "cost", "general", "large_context"],
        strengths=[
            "1M+ token context window",
            "Very affordable ($0.40/$1.60 per MTok)",
            "Fast responses",
            "No registration required",
        ],
        weaknesses=["Less capable reasoning than gpt-4.1"],
        input_cost_per_1m=0.40,
        output_cost_per_1m=1.60,
    ),
    "openai/gpt-4.1-nano": ModelCapability(
        provider="openai",
        model="gpt-4.1-nano",
        cost_per_query=0.003,
        latency_ms=800,
        context_window=1_047_576,
        specializations=["speed", "cost", "general", "large_context"],
        strengths=[
            "1M+ token context window",
            "Cheapest GPT-4.1 variant ($0.10/$0.40 per MTok)",
            "Very fast responses",
        ],
        weaknesses=["Least capable 4.1 variant", "Not ideal for complex reasoning"],
        input_cost_per_1m=0.10,
        output_cost_per_1m=0.40,
    ),
    "openai/gpt-5-nano": ModelCapability(
        provider="openai",
        model="gpt-5-nano",
        cost_per_query=0.005,
        latency_ms=800,
        context_window=400_000,
        specializations=["speed", "cost", "general", "summarization"],
        strengths=[
            "Cheapest GPT-5 variant ($0.05/$0.40 per MTok)",
            "Very fast responses",
            "400K context window",
            "Good for summarization and classification",
        ],
        weaknesses=["Lowest reasoning capability in GPT-5 family"],
        input_cost_per_1m=0.05,
        output_cost_per_1m=0.40,
    ),
    # OpenAI Reasoning Models (o-series, non-deep-research)
    "openai/o3": ModelCapability(
        provider="openai",
        model="o3",
        cost_per_query=0.10,
        latency_ms=5000,
        context_window=200_000,
        specializations=["reasoning", "math", "science", "coding"],
        strengths=[
            "Strong reasoning chains",
            "Excellent at math, science, and coding",
            "200K context window",
        ],
        weaknesses=["Succeeded by GPT-5 for most tasks", "Slower than GPT models"],
        input_cost_per_1m=2.00,
        output_cost_per_1m=8.00,
    ),
    "openai/o4-mini": ModelCapability(
        provider="openai",
        model="o4-mini",
        cost_per_query=0.04,
        latency_ms=3000,
        context_window=200_000,
        specializations=["reasoning", "speed", "cost", "math", "science"],
        strengths=[
            "Fast, cost-efficient reasoning",
            "Good at math and science",
            "200K context window",
        ],
        weaknesses=["Succeeded by GPT-5 mini for most tasks", "Smaller context than GPT models"],
        input_cost_per_1m=1.10,
        output_cost_per_1m=4.40,
    ),
    # OpenAI Deep Research Models
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
            "Excellent for strategic decisions",
        ],
        weaknesses=["Expensive ($2 per query)", "Slow (30-60 seconds minimum)", "Overkill for simple queries"],
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
            "Real-time information access",
        ],
        weaknesses=[
            "Less capable at complex reasoning",
            "Not ideal for multi-step analysis",
            "Lower quality for strategic work",
        ],
        input_cost_per_1m=0.20,
        output_cost_per_1m=0.50,
    ),
    "xai/grok-4-1-fast-reasoning": ModelCapability(
        provider="xai",
        model="grok-4-1-fast-reasoning",
        cost_per_query=0.01,
        latency_ms=2000,
        context_window=2_000_000,
        specializations=["reasoning", "speed", "news", "factual"],
        strengths=[
            "Latest Grok generation with reasoning",
            "2M token context window",
            "Web search via Responses API",
            "Same low pricing as Grok 4 Fast",
        ],
        weaknesses=[
            "Slightly slower than non-reasoning variant",
            "Preview model",
        ],
        input_cost_per_1m=0.20,
        output_cost_per_1m=0.50,
    ),
    "xai/grok-4-fast-reasoning": ModelCapability(
        provider="xai",
        model="grok-4-fast-reasoning",
        cost_per_query=0.01,
        latency_ms=2000,
        context_window=2_000_000,
        specializations=["reasoning", "speed", "news", "factual"],
        strengths=[
            "Reasoning-capable Grok 4",
            "2M token context window",
            "Web search via Responses API",
            "Very cheap ($0.20/$0.50 per M tokens)",
        ],
        weaknesses=[
            "Superseded by Grok 4.1",
        ],
        input_cost_per_1m=0.20,
        output_cost_per_1m=0.50,
    ),
    # Google Models (Gemini)
    "gemini/gemini-3-flash-preview": ModelCapability(
        provider="gemini",
        model="gemini-3-flash-preview",
        cost_per_query=0.01,
        latency_ms=1500,
        context_window=1_000_000,
        specializations=["speed", "thinking", "general"],
        strengths=[
            "Newest generation, fast",
            "Pro-level intelligence at Flash pricing",
            "1M token context window",
            "Dynamic thinking",
        ],
        weaknesses=["Preview model (may change)", "Thinking tokens add to output cost"],
        input_cost_per_1m=0.50,
        output_cost_per_1m=3.00,  # Includes thinking tokens
    ),
    "gemini/gemini-3.1-pro-preview": ModelCapability(
        provider="gemini",
        model="gemini-3.1-pro-preview",
        cost_per_query=0.20,
        latency_ms=40000,
        context_window=1_000_000,
        specializations=["reasoning", "large_context", "document_analysis", "synthesis", "thinking", "agentic"],
        strengths=[
            "Latest Gemini generation, best multimodal understanding",
            "1M token context window, 65K output",
            "Configurable thinking levels (minimal/low/medium/high)",
            "Excellent for document analysis, synthesis, and agentic tasks",
            "URL context and custom tools support",
        ],
        weaknesses=[
            "Preview model (may change)",
            "2x pricing for prompts >200K tokens",
            "No free tier",
        ],
        input_cost_per_1m=2.00,
        output_cost_per_1m=12.00,  # Includes thinking tokens; 2x for >200K prompts
    ),
    "gemini/gemini-3-pro-preview": ModelCapability(
        provider="gemini",
        model="gemini-3-pro-preview",
        cost_per_query=0.20,
        latency_ms=4000,
        context_window=1_000_000,
        specializations=["reasoning", "large_context", "document_analysis", "synthesis", "thinking"],
        strengths=[
            "1M token context window",
            "Mandatory thinking (always reasons deeply)",
            "Excellent for document analysis and synthesis",
        ],
        weaknesses=[
            "Superseded by Gemini 3.1 Pro Preview",
            "Preview model (may change)",
            "Can't disable thinking",
            "2x pricing for prompts >200K tokens",
        ],
        input_cost_per_1m=2.00,
        output_cost_per_1m=12.00,  # Includes thinking tokens
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
            "Background async execution",
        ],
        weaknesses=["Slow (5-20 minutes per job)", "~$1 per job", "Experimental API (may change)"],
        input_cost_per_1m=1.25,
        output_cost_per_1m=5.00,
    ),
    "gemini/gemini-2.5-flash": ModelCapability(
        provider="gemini",
        model="gemini-2.5-flash",
        cost_per_query=0.005,
        latency_ms=1500,
        context_window=1_000_000,
        specializations=["speed", "cost", "general", "thinking"],
        strengths=[
            "Thinking model with optional reasoning",
            "1M token context window",
            "Fast responses",
            "Thinking can be disabled for speed",
        ],
        weaknesses=["Less capable than pro models", "Thinking tokens add to output cost"],
        input_cost_per_1m=0.30,
        output_cost_per_1m=2.50,  # Includes thinking tokens
    ),
    "gemini/gemini-2.5-pro": ModelCapability(
        provider="gemini",
        model="gemini-2.5-pro",
        cost_per_query=0.15,
        latency_ms=4000,
        context_window=1_000_000,
        specializations=["reasoning", "large_context", "synthesis", "thinking"],
        strengths=[
            "Strong thinking/reasoning model",
            "1M token context window",
            "Can't disable thinking (always reasons)",
            "Good for complex analysis",
        ],
        weaknesses=["Slower due to mandatory thinking", "Higher cost from thinking tokens"],
        input_cost_per_1m=1.25,
        output_cost_per_1m=10.00,  # Includes thinking tokens
    ),
    # Anthropic Models
    # Note: Anthropic does NOT have a turnkey deep research API like OpenAI/Gemini.
    # Research capability is achieved via Extended Thinking + tool use + our orchestration.
    # For research, we recommend Opus 4.6 - best reasoning with Adaptive Thinking.
    "anthropic/claude-opus-4-6": ModelCapability(
        provider="anthropic",
        model="claude-opus-4-6",
        cost_per_query=0.80,  # Estimated with Extended Thinking budget
        latency_ms=12000,
        context_window=200_000,  # 1M beta available
        specializations=["research", "reasoning", "coding", "analysis", "complex_tasks", "agents"],
        strengths=[
            "Most intelligent Claude model (Feb 2026)",
            "Adaptive Thinking (auto-adjusts reasoning effort)",
            "Extended Thinking with high token budget",
            "128K max output tokens",
            "1M context window (beta)",
            "Exceptional at coding and agentic workflows",
        ],
        weaknesses=[
            "No native deep research API (requires orchestration)",
            "Slower than Sonnet (~12s vs ~3s)",
            "Higher cost than Sonnet (~$0.80 vs ~$0.48/query)",
        ],
        input_cost_per_1m=5.00,
        output_cost_per_1m=25.00,
    ),
    "anthropic/claude-sonnet-4-5": ModelCapability(
        provider="anthropic",
        model="claude-sonnet-4-5",
        cost_per_query=0.48,  # Estimated with 16K thinking budget
        latency_ms=3000,
        context_window=200_000,  # 1M beta available
        specializations=["reasoning", "coding", "analysis", "balanced", "agents"],
        strengths=[
            "Best speed/intelligence balance",
            "Fast responses (~3s)",
            "Extended Thinking support",
            "1M context window (beta)",
            "64K max output tokens",
        ],
        weaknesses=[
            "Less capable than Opus 4.6 for complex research",
            "No Adaptive Thinking",
            "No native deep research API",
        ],
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
    ),
    # Azure AI Foundry
    # Deep research (o3) available in: West US, Norway East, South Central US
    # GPT-4.1/5 available globally (20+ regions via Global Standard deployment)
    "azure-foundry/o3-deep-research": ModelCapability(
        provider="azure-foundry",
        model="o3-deep-research",
        cost_per_query=0.50,
        latency_ms=120_000,
        context_window=200_000,
        specializations=["research", "analysis", "strategic_planning"],
        strengths=[
            "Enterprise deep research with Bing grounding",
            "Azure AD / Managed Identity authentication",
            "Built-in web search via Bing",
            "Agent/Thread/Run pattern for async jobs",
        ],
        weaknesses=[
            "Deep research limited to West US, Norway East, South Central US",
            "Requires Azure AI Foundry project setup",
            "No standalone file upload (thread attachments only)",
        ],
        input_cost_per_1m=11.0,
        output_cost_per_1m=44.0,
    ),
    "azure-foundry/gpt-5": ModelCapability(
        provider="azure-foundry",
        model="gpt-5",
        cost_per_query=0.15,
        latency_ms=2500,
        context_window=400_000,
        specializations=["reasoning", "planning", "analysis", "synthesis"],
        strengths=[
            "Frontier-scale reasoning via Azure",
            "Azure AD / Managed Identity authentication",
            "400K context window",
            "Available in 10+ regions (Global Standard)",
        ],
        weaknesses=[
            "Registration required",
            "Only code interpreter + file search tools (no deep research tool)",
            "Requires Azure AI Foundry project setup",
        ],
        input_cost_per_1m=1.25,
        output_cost_per_1m=10.00,
    ),
    "azure-foundry/gpt-5-mini": ModelCapability(
        provider="azure-foundry",
        model="gpt-5-mini",
        cost_per_query=0.03,
        latency_ms=1500,
        context_window=400_000,
        specializations=["reasoning", "speed", "balanced"],
        strengths=[
            "Good reasoning at low cost via Azure",
            "Azure AD / Managed Identity authentication",
            "400K context window",
            "No registration required",
        ],
        weaknesses=[
            "Less capable than gpt-5 for complex tasks",
            "Requires Azure AI Foundry project setup",
        ],
        input_cost_per_1m=0.25,
        output_cost_per_1m=2.00,
    ),
    "azure-foundry/gpt-4.1": ModelCapability(
        provider="azure-foundry",
        model="gpt-4.1",
        cost_per_query=0.04,
        latency_ms=2000,
        context_window=1_047_576,
        specializations=["reasoning", "planning", "synthesis", "large_context"],
        strengths=[
            "1M+ token context window",
            "Available in 19 regions (widest Azure availability)",
            "Azure AD / Managed Identity authentication",
            "No registration required",
        ],
        weaknesses=[
            "Not frontier-scale reasoning (use gpt-5 for that)",
            "Requires Azure AI Foundry project setup",
        ],
        input_cost_per_1m=2.00,
        output_cost_per_1m=8.00,
    ),
    "azure-foundry/gpt-4.1-mini": ModelCapability(
        provider="azure-foundry",
        model="gpt-4.1-mini",
        cost_per_query=0.01,
        latency_ms=1200,
        context_window=1_047_576,
        specializations=["speed", "cost", "general", "large_context"],
        strengths=[
            "1M+ token context window at low cost",
            "Available in 19 regions",
            "Azure AD / Managed Identity authentication",
            "No registration required",
        ],
        weaknesses=[
            "Less capable reasoning than gpt-4.1",
            "Requires Azure AI Foundry project setup",
        ],
        input_cost_per_1m=0.40,
        output_cost_per_1m=1.60,
    ),
    "azure-foundry/gpt-4o": ModelCapability(
        provider="azure-foundry",
        model="gpt-4o",
        cost_per_query=0.03,
        latency_ms=3000,
        context_window=128_000,
        specializations=["reasoning", "planning", "synthesis", "chat"],
        strengths=[
            "Strong general-purpose reasoning",
            "Azure AD / Managed Identity authentication",
            "Good for expert chat, synthesis, planning",
            "128K context window",
        ],
        weaknesses=[
            "Superseded by gpt-4.1 (1M context, same price)",
            "Requires Azure AI Foundry project setup",
        ],
        input_cost_per_1m=2.50,
        output_cost_per_1m=10.00,
    ),
    "azure-foundry/gpt-4o-mini": ModelCapability(
        provider="azure-foundry",
        model="gpt-4o-mini",
        cost_per_query=0.005,
        latency_ms=1500,
        context_window=128_000,
        specializations=["speed", "cost", "general", "chat"],
        strengths=[
            "Very fast and cheap",
            "Azure AD / Managed Identity authentication",
            "Good for quick lookups and simple tasks",
        ],
        weaknesses=[
            "Superseded by gpt-4.1-mini (1M context, similar price)",
            "Less capable at complex reasoning",
            "Requires Azure AI Foundry project setup",
        ],
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.60,
    ),
    "anthropic/claude-haiku-4-5": ModelCapability(
        provider="anthropic",
        model="claude-haiku-4-5",
        cost_per_query=0.05,
        latency_ms=1000,
        context_window=200_000,
        specializations=["speed", "cost", "general"],
        strengths=[
            "Fastest Claude model",
            "Lowest cost ($1/$5 per MTok)",
            "Extended Thinking support",
            "64K max output tokens",
            "Near-frontier intelligence at budget price",
        ],
        weaknesses=["Not suitable for deep research", "Less capable than Sonnet/Opus for complex reasoning"],
        input_cost_per_1m=1.00,
        output_cost_per_1m=5.00,
    ),
}


def get_token_pricing(model: str) -> dict[str, float]:
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


def get_models_by_specialization(specialization: str) -> list[ModelCapability]:
    """Get all models that specialize in a given area.

    Args:
        specialization: Specialization to filter by

    Returns:
        List of models with that specialization, sorted by cost
    """
    matching = [cap for cap in MODEL_CAPABILITIES.values() if specialization in cap.specializations]
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
