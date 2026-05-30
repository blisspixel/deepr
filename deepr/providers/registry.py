"""Model capabilities registry for dynamic routing.

Defines capabilities, costs, and specializations for all supported models across providers.
Used by ModelRouter to make intelligent routing decisions.
"""

from dataclasses import dataclass


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
    deprecated: bool = False  # Whether this model is deprecated
    successor: str | None = None  # Model key to migrate to (e.g. "openai/gpt-4.1")


# Model capabilities registry
MODEL_CAPABILITIES: dict[str, ModelCapability] = {
    # OpenAI Models
    "openai/gpt-5.4": ModelCapability(
        provider="openai",
        model="gpt-5.4",
        cost_per_query=0.30,
        latency_ms=2300,
        context_window=1_050_000,
        specializations=["reasoning", "planning", "agentic", "synthesis", "large_context"],
        strengths=[
            "Newest OpenAI frontier model",
            "Strong long-horizon task execution",
            "1M+ token context window",
            "Improved tool-use reliability",
            "Supports none/low/medium/high/xhigh reasoning effort",
        ],
        weaknesses=["Higher cost than gpt-5.2", "May require prompt/effort tuning for best cost-quality tradeoff"],
        input_cost_per_1m=2.50,
        output_cost_per_1m=15.00,
    ),
    "openai/gpt-5.4-pro": ModelCapability(
        provider="openai",
        model="gpt-5.4-pro",
        cost_per_query=0.90,
        latency_ms=8000,
        context_window=1_050_000,
        specializations=["reasoning", "planning", "agentic", "synthesis", "hard_problems"],
        strengths=[
            "Highest-precision GPT-5.4 variant",
            "Stronger long-horizon reasoning for complex tasks",
            "1M+ token context window",
            "Responses API support with advanced tools",
        ],
        weaknesses=[
            "Expensive compared with non-pro variants",
            "Higher latency and may take minutes on hard tasks",
        ],
        input_cost_per_1m=30.00,
        output_cost_per_1m=180.00,
    ),
    "openai/gpt-5.4-mini": ModelCapability(
        provider="openai",
        model="gpt-5.4-mini",
        cost_per_query=0.05,
        latency_ms=1500,
        context_window=400_000,
        specializations=["reasoning", "speed", "balanced", "agentic"],
        strengths=[
            "Newer-generation budget reasoning (GPT-5.4 family)",
            "Good reasoning at low cost",
            "Fast responses",
            "400K context window",
            "Configurable reasoning effort",
        ],
        weaknesses=[
            "Pricier than gpt-5-mini ($0.75/$4.50 vs $0.25/$2.00 per MTok)",
            "Less capable than full gpt-5.4",
        ],
        input_cost_per_1m=0.75,
        output_cost_per_1m=4.50,
    ),
    "openai/gpt-5.4-nano": ModelCapability(
        provider="openai",
        model="gpt-5.4-nano",
        cost_per_query=0.01,
        latency_ms=800,
        context_window=400_000,
        specializations=["speed", "cost", "general", "summarization"],
        strengths=[
            "Cheapest GPT-5.4 variant ($0.20/$1.25 per MTok)",
            "Very fast responses",
            "400K context window",
            "Good for summarization and classification",
        ],
        weaknesses=[
            "Lowest reasoning capability in GPT-5.4 family",
            "Pricier than gpt-5-nano ($0.20/$1.25 vs $0.05/$0.40 per MTok)",
        ],
        input_cost_per_1m=0.20,
        output_cost_per_1m=1.25,
    ),
    "openai/gpt-5.5": ModelCapability(
        provider="openai",
        model="gpt-5.5",
        cost_per_query=0.50,
        latency_ms=2500,
        context_window=1_050_000,
        specializations=["reasoning", "coding", "agentic", "tool_calling", "synthesis", "instruction_following"],
        strengths=[
            "OpenAI's most capable model (April 2026)",
            "Strongest for coding, tool-heavy agents, and complex workflows",
            "More efficient reasoning — fewer tokens for same quality",
            "1M+ token context window (922K input, 128K output)",
            "Configurable reasoning effort (none/low/medium/high/xhigh)",
            "Improved instruction following and task execution",
        ],
        weaknesses=[
            "2x more expensive than GPT-5.4 ($5/$30 vs $2.50/$15)",
            "May require prompt re-tuning from GPT-5.4 (not a drop-in replacement)",
        ],
        input_cost_per_1m=5.00,
        output_cost_per_1m=30.00,
    ),
    "openai/gpt-5.5-pro": ModelCapability(
        provider="openai",
        model="gpt-5.5-pro",
        cost_per_query=1.50,
        latency_ms=10000,
        context_window=1_050_000,
        specializations=["reasoning", "planning", "agentic", "synthesis", "hard_problems"],
        strengths=[
            "Highest-precision GPT-5.5 variant for hardest tasks",
            "Maximum reasoning depth for complex multi-step problems",
            "1M+ token context window",
            "Best for highest-stakes reasoning where cost is secondary",
        ],
        weaknesses=[
            "Very expensive ($30/$180 per MTok)",
            "High latency — may take minutes on hard tasks",
            "Overkill for most workloads",
        ],
        input_cost_per_1m=30.00,
        output_cost_per_1m=180.00,
    ),
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
    # Grok 4.20 — Flagship (March 2026)
    "xai/grok-4-20-reasoning": ModelCapability(
        provider="xai",
        model="grok-4-20-reasoning",
        cost_per_query=0.10,
        latency_ms=3000,
        context_window=2_000_000,
        specializations=["reasoning", "analysis", "synthesis", "coding", "factual"],
        strengths=[
            "xAI flagship model (March 2026)",
            "Lowest hallucination rate across benchmarks",
            "Strict prompt adherence",
            "Full agentic tool calling (web, X, code interpreter)",
            "Native vision support",
            "2M token context window",
        ],
        weaknesses=[
            "10x more expensive than Grok 4.1 Fast ($2/$6 vs $0.20/$0.50)",
            "Slower than non-reasoning variant",
        ],
        input_cost_per_1m=2.00,
        output_cost_per_1m=6.00,
    ),
    "xai/grok-4-20-non-reasoning": ModelCapability(
        provider="xai",
        model="grok-4-20-non-reasoning",
        cost_per_query=0.08,
        latency_ms=2000,
        context_window=2_000_000,
        specializations=["speed", "factual", "news", "general", "high_throughput"],
        strengths=[
            "Flagship Grok without reasoning overhead",
            "Low-latency for high-volume tasks",
            "Strict prompt adherence",
            "Native vision support",
            "2M token context window",
        ],
        weaknesses=[
            "More expensive than 4.1 Fast tier ($2/$6 vs $0.20/$0.50)",
            "Weaker than reasoning variant on complex analysis",
        ],
        input_cost_per_1m=2.00,
        output_cost_per_1m=6.00,
    ),
    "xai/grok-4-20-multi-agent": ModelCapability(
        provider="xai",
        model="grok-4-20-multi-agent",
        cost_per_query=0.50,
        latency_ms=60_000,
        context_window=2_000_000,
        specializations=["research", "analysis", "synthesis", "agentic"],
        strengths=[
            "4 or 16 parallel agents for deep research",
            "Autonomous web + X + code search",
            "Comprehensive multi-step analysis and synthesis",
            "2M token context window",
        ],
        weaknesses=[
            "Expensive ($2/$6 per MTok, multiplied by agent count)",
            "Slow (30-120 seconds depending on agent count)",
            "Requires Responses API for full multi-agent mode",
        ],
        input_cost_per_1m=2.00,
        output_cost_per_1m=6.00,
    ),
    # Grok 4.3 — Newest generation (May 2026)
    "xai/grok-4-3": ModelCapability(
        provider="xai",
        model="grok-4-3",
        cost_per_query=0.05,
        latency_ms=2500,
        context_window=1_000_000,
        specializations=["reasoning", "agentic", "tool_calling", "instruction_following"],
        strengths=[
            "Fastest, most intelligent Grok model (May 2026)",
            "Tops leaderboards in agentic tool calling and instruction following",
            "Configurable reasoning effort (low/medium/high)",
            "1M token context window",
            "Competitive pricing ($1.25/$2.50 per MTok)",
        ],
        weaknesses=[
            "Smaller context than Grok 4.20 (1M vs 2M)",
            "Newer model, less battle-tested in production",
        ],
        input_cost_per_1m=1.25,
        output_cost_per_1m=2.50,
    ),
    # Grok 4.1 Fast — Budget tier (DEPRECATED: retires May 15, 2026)
    "xai/grok-4-1-fast-reasoning": ModelCapability(
        provider="xai",
        model="grok-4-1-fast-reasoning",
        cost_per_query=0.01,
        latency_ms=2000,
        context_window=2_000_000,
        specializations=["reasoning", "speed", "news", "factual"],
        strengths=[
            "Grok 4.1 generation with reasoning",
            "2M token context window",
            "Web search via Responses API",
            "Very cheap ($0.20/$0.50 per M tokens)",
        ],
        weaknesses=[
            "Slightly slower than non-reasoning variant",
            "Superseded by Grok 4.20 for quality",
            "DEPRECATED: Retires May 15, 2026. Successor: Grok 4.3",
        ],
        input_cost_per_1m=0.20,
        output_cost_per_1m=0.50,
        deprecated=True,
        successor="xai/grok-4-3",
    ),
    "xai/grok-4-1-fast-non-reasoning": ModelCapability(
        provider="xai",
        model="grok-4-1-fast-non-reasoning",
        cost_per_query=0.008,
        latency_ms=1200,
        context_window=2_000_000,
        specializations=["speed", "news", "factual", "high_throughput"],
        strengths=[
            "Low-latency Grok 4.1 variant",
            "2M token context window",
            "Great for high-volume factual and retrieval tasks",
        ],
        weaknesses=[
            "Weaker than reasoning variant on complex analysis",
            "DEPRECATED: Retires May 15, 2026. Successor: Grok 4.20 Non-Reasoning",
        ],
        input_cost_per_1m=0.20,
        output_cost_per_1m=0.50,
        deprecated=True,
        successor="xai/grok-4-20-non-reasoning",
    ),
    "xai/grok-code-fast-1": ModelCapability(
        provider="xai",
        model="grok-code-fast-1",
        cost_per_query=0.012,
        latency_ms=1300,
        context_window=256_000,
        specializations=["coding", "speed", "cost", "developer_workflows"],
        strengths=[
            "xAI coding-optimized fast model",
            "Low-cost coding and transformation tasks",
            "Good fit for agent loops with short responses",
        ],
        weaknesses=[
            "Narrower specialization than general-purpose Grok reasoning models",
            "DEPRECATED: Retires May 15, 2026. Successor: Grok 4.3",
        ],
        input_cost_per_1m=0.20,
        output_cost_per_1m=1.50,
        deprecated=True,
        successor="xai/grok-4-3",
    ),
    # Grok legacy models (DEPRECATED: retire May 15, 2026)
    "xai/grok-4-fast-reasoning": ModelCapability(
        provider="xai",
        model="grok-4-fast-reasoning",
        cost_per_query=0.02,
        latency_ms=2500,
        context_window=1_000_000,
        specializations=["reasoning", "speed"],
        strengths=["Grok 4 Fast with reasoning"],
        weaknesses=["DEPRECATED: Retires May 15, 2026. Successor: Grok 4.3"],
        input_cost_per_1m=0.50,
        output_cost_per_1m=1.50,
        deprecated=True,
        successor="xai/grok-4-3",
    ),
    "xai/grok-4-fast-non-reasoning": ModelCapability(
        provider="xai",
        model="grok-4-fast-non-reasoning",
        cost_per_query=0.015,
        latency_ms=1500,
        context_window=1_000_000,
        specializations=["speed", "factual"],
        strengths=["Grok 4 Fast without reasoning overhead"],
        weaknesses=["DEPRECATED: Retires May 15, 2026. Successor: Grok 4.20 Non-Reasoning"],
        input_cost_per_1m=0.50,
        output_cost_per_1m=1.50,
        deprecated=True,
        successor="xai/grok-4-20-non-reasoning",
    ),
    "xai/grok-4-0709": ModelCapability(
        provider="xai",
        model="grok-4-0709",
        cost_per_query=0.05,
        latency_ms=3000,
        context_window=1_000_000,
        specializations=["reasoning", "analysis"],
        strengths=["Grok 4 July 2025 snapshot"],
        weaknesses=["DEPRECATED: Retires May 15, 2026. Successor: Grok 4.3"],
        input_cost_per_1m=2.00,
        output_cost_per_1m=6.00,
        deprecated=True,
        successor="xai/grok-4-3",
    ),
    "xai/grok-3": ModelCapability(
        provider="xai",
        model="grok-3",
        cost_per_query=0.10,
        latency_ms=4000,
        context_window=131_072,
        specializations=["reasoning", "general"],
        strengths=["Original Grok 3 model"],
        weaknesses=["DEPRECATED: Retires May 15, 2026. Successor: Grok 4.3"],
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
        deprecated=True,
        successor="xai/grok-4-3",
    ),
    "xai/grok-imagine-image-pro": ModelCapability(
        provider="xai",
        model="grok-imagine-image-pro",
        cost_per_query=0.04,
        latency_ms=5000,
        context_window=8_000,
        specializations=["image_generation"],
        strengths=["Professional image generation"],
        weaknesses=["DEPRECATED: Retires May 15, 2026. Successor: grok-imagine-image"],
        input_cost_per_1m=0.0,
        output_cost_per_1m=0.0,
        deprecated=True,
        successor="xai/grok-imagine-image",
    ),
    # Google Models (Gemini)
    # Gemini 3.5 Flash — newest Flash generation (GA May 19, 2026, Google I/O 2026)
    "gemini/gemini-3.5-flash": ModelCapability(
        provider="gemini",
        model="gemini-3.5-flash",
        cost_per_query=0.03,
        latency_ms=1500,
        context_window=1_000_000,
        specializations=["reasoning", "coding", "agentic", "multimodal", "speed", "thinking"],
        strengths=[
            "First model in the Gemini 3.5 family (GA May 19, 2026)",
            "Surpasses Gemini 3.1 Pro on coding, agentic, and multimodal benchmarks",
            "Frontier intelligence at Flash speed (~4x faster output than frontier peers)",
            "1M token context window, 65K output",
            "Multimodal input (text, image, audio, video, PDF)",
            "Dynamic thinking",
        ],
        weaknesses=[
            "3x pricier than Gemini 3 Flash preview ($1.50/$9.00 vs $0.50/$3.00 per MTok)",
            "Thinking tokens add to output cost",
        ],
        input_cost_per_1m=1.50,
        output_cost_per_1m=9.00,  # Includes thinking tokens; non-global regions $1.65/$9.90
    ),
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
        weaknesses=[
            "Preview model (may change)",
            "Thinking tokens add to output cost",
            "Superseded for quality by gemini-3.5-flash (which costs ~3x more)",
        ],
        input_cost_per_1m=0.50,
        output_cost_per_1m=3.00,  # Includes thinking tokens
    ),
    # Gemini 3.1 Flash-Lite — GA (May 7, 2026); most cost-effective Gemini
    "gemini/gemini-3.1-flash-lite": ModelCapability(
        provider="gemini",
        model="gemini-3.1-flash-lite",
        cost_per_query=0.007,
        latency_ms=1300,
        context_window=1_000_000,
        specializations=["speed", "cost", "general", "high_throughput", "thinking"],
        strengths=[
            "Most cost-effective Gemini model (GA May 7, 2026)",
            "1M token context window",
            "Low-cost high-throughput inference",
            "Dynamic thinking",
        ],
        weaknesses=[
            "Less capable than Pro/Flash models on deep reasoning",
        ],
        input_cost_per_1m=0.25,
        output_cost_per_1m=1.50,
    ),
    "gemini/gemini-3.1-flash-lite-preview": ModelCapability(
        provider="gemini",
        model="gemini-3.1-flash-lite-preview",
        cost_per_query=0.006,
        latency_ms=1300,
        context_window=1_000_000,
        specializations=["speed", "cost", "general", "high_throughput", "thinking"],
        strengths=[
            "Newest Flash-Lite in Gemini 3.1 series",
            "1M token context window",
            "Low-cost high-throughput inference",
        ],
        weaknesses=[
            "Preview model (lifecycle may change)",
            "Less capable than Pro models on deep reasoning",
            "Superseded by GA gemini-3.1-flash-lite ($0.25/$1.50 per MTok)",
        ],
        input_cost_per_1m=0.20,
        output_cost_per_1m=1.20,
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
        cost_per_query=2.50,
        latency_ms=600_000,  # 5-20 minutes
        context_window=1_000_000,
        specializations=["research", "analysis", "synthesis"],
        strengths=[
            "Autonomous multi-step research with Google Search",
            "Structured reports with citations",
            "File grounding via File Search Stores",
            "Background async execution",
            "Powered by Gemini 3.1 Pro",
        ],
        weaknesses=["Slow (5-20 minutes per job)", "~$2.50 per job", "Experimental API (may change)"],
        input_cost_per_1m=2.00,
        output_cost_per_1m=12.00,
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
    "gemini/gemini-2.5-flash-lite": ModelCapability(
        provider="gemini",
        model="gemini-2.5-flash-lite",
        cost_per_query=0.003,
        latency_ms=1100,
        context_window=1_000_000,
        specializations=["speed", "cost", "general", "high_throughput"],
        strengths=[
            "Stable low-cost Flash-Lite model",
            "1M token context window",
            "Strong throughput for lightweight tasks",
        ],
        weaknesses=["Less capable on deep reasoning and synthesis"],
        input_cost_per_1m=0.10,
        output_cost_per_1m=0.40,
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
    # Claude Opus 4.7 — most capable Claude (GA Apr 16, 2026); leads SWE-bench Pro
    "anthropic/claude-opus-4-7": ModelCapability(
        provider="anthropic",
        model="claude-opus-4-7",
        cost_per_query=0.85,  # Same per-token rate as 4.6, but new tokenizer (~35% more tokens)
        latency_ms=12000,
        context_window=1_000_000,  # Full 1M at standard pricing
        specializations=["research", "reasoning", "coding", "analysis", "complex_tasks", "agents"],
        strengths=[
            "Most capable Claude model (GA Apr 16, 2026)",
            "Leads SWE-bench Pro (64.3%)",
            "Adaptive Thinking (auto-adjusts reasoning effort)",
            "Full 1M token context window at standard pricing",
            "128K max output tokens",
            "Fast mode available (6x price for faster output)",
        ],
        weaknesses=[
            "No native deep research API (requires orchestration)",
            "New tokenizer uses up to 35% more tokens for the same text (higher effective cost)",
            "Slower than Sonnet (~12s vs ~3s)",
        ],
        input_cost_per_1m=5.00,
        output_cost_per_1m=25.00,
    ),
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
            "Superseded by claude-opus-4-7 (same price)",
        ],
        input_cost_per_1m=5.00,
        output_cost_per_1m=25.00,
    ),
    # Claude Sonnet 4.6 — best value for everyday coding (GA Apr 2026)
    "anthropic/claude-sonnet-4-6": ModelCapability(
        provider="anthropic",
        model="claude-sonnet-4-6",
        cost_per_query=0.48,  # Estimated with 16K thinking budget
        latency_ms=3000,
        context_window=1_000_000,  # Full 1M at standard pricing
        specializations=["reasoning", "coding", "analysis", "balanced", "agents"],
        strengths=[
            "Best speed/intelligence balance; best value for everyday coding",
            "Fast responses (~3s)",
            "Extended Thinking support",
            "Full 1M token context window at standard pricing",
            "64K max output tokens",
        ],
        weaknesses=[
            "Less capable than Opus 4.7 for complex research",
            "No native deep research API",
        ],
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
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
            "Superseded by claude-sonnet-4-6 (same price)",
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


def _normalize_model_name(name: str) -> str:
    """Normalize a model name so dot/hyphen variants compare equal.

    The Grok provider reports model IDs with dots (``grok-4.20-...``) but
    the registry keys them with hyphens (``grok-4-20-...``). Without this
    normalization, a substring match on the dotted form falls through to
    the o4-mini default — a ~80% under-charge on every Grok 4.20 call.
    """
    if not name:
        return name
    return name.replace(".", "-").lower()


def get_token_pricing(model: str) -> dict[str, float]:
    """Get per-token pricing for a model.

    Searches registry by model name across all providers.

    Args:
        model: Model name (e.g., "o3-deep-research", "grok-4-1-fast-non-reasoning")

    Returns:
        Dict with "input" and "output" costs per 1M tokens.
        Returns default pricing if model not found.
    """
    # Resolve alias first so callers using ``gemini-deep-research`` or
    # ``deep-research`` see the real provider model's per-token pricing
    # instead of the o4-mini default.
    resolved = _MODEL_ALIASES.get(model, model)
    needle = _normalize_model_name(resolved)

    # Exact match (normalized)
    for cap in MODEL_CAPABILITIES.values():
        if cap.input_cost_per_1m > 0 and _normalize_model_name(cap.model) == needle:
            return {"input": cap.input_cost_per_1m, "output": cap.output_cost_per_1m}

    # Partial match — longest cap.model first so e.g. ``gemini-2.5-flash-lite``
    # matches its own entry before the shorter ``gemini-2.5-flash`` prefix
    # (which would have charged Flash-Lite at Flash rates, ~3x overcharge).
    candidates = sorted(
        (cap for cap in MODEL_CAPABILITIES.values() if cap.input_cost_per_1m > 0),
        key=lambda c: len(c.model or ""),
        reverse=True,
    )
    for cap in candidates:
        if _normalize_model_name(cap.model) in needle:
            return {"input": cap.input_cost_per_1m, "output": cap.output_cost_per_1m}

    # Default to o4-mini pricing
    default = MODEL_CAPABILITIES.get("openai/o4-mini-deep-research")
    if default:
        return {"input": default.input_cost_per_1m, "output": default.output_cost_per_1m}
    return {"input": 1.10, "output": 4.40}


# Models whose published pricing doubles for prompts exceeding a per-model
# input-token threshold. Used by get_cost_estimate() so pre-flight budget
# checks reflect tiered pricing rather than the base cost_per_query rate.
_TIERED_PRICING: dict[str, tuple[int, float]] = {
    "gemini-3.1-pro-preview": (200_000, 2.0),
    "gemini-3-pro-preview": (200_000, 2.0),
}

# Caller-facing aliases that resolve to expensive deep-research provider
# paths. Without these, both the orchestrator and MCP fall back to the
# generic $0.20 default and approve jobs that cost ~$2.50 to run.
_MODEL_ALIASES: dict[str, str] = {
    "gemini-deep-research": "deep-research-pro-preview-12-2025",
    "deep-research": "deep-research-pro-preview-12-2025",
}


def get_cost_estimate(model: str, input_tokens: int | None = None) -> float:
    """Get per-query cost estimate for a model.

    Args:
        model: Model name
        input_tokens: Optional prompt size in tokens. When provided and the
            model has tiered pricing (e.g. Gemini 3.x Pro 2x above 200K
            input tokens), the returned estimate reflects the tier so that
            budget checks do not approve large-context jobs against an
            underestimated cost.

    Returns:
        Estimated cost per query in USD. Returns 0.20 if model not found.
    """
    resolved = _MODEL_ALIASES.get(model, model)
    needle = _normalize_model_name(resolved)
    base = 0.20

    # Exact match (normalized) first.
    for cap in MODEL_CAPABILITIES.values():
        if _normalize_model_name(cap.model) == needle:
            base = cap.cost_per_query
            break
    else:
        # Partial match — longest cap.model first so e.g. a "gpt-5.4-mini"
        # snapshot matches its own entry before the shorter "gpt-5.4" prefix.
        # Without longest-first this both over-charges (mini -> full price) and,
        # worse, under-charges ("gpt-5.4-pro-<date>" -> cheaper "gpt-5.4"),
        # letting budget pre-flight approve an expensive job. Mirrors
        # get_token_pricing().
        for cap in sorted(MODEL_CAPABILITIES.values(), key=lambda c: len(c.model or ""), reverse=True):
            if _normalize_model_name(cap.model) in needle:
                base = cap.cost_per_query
                break

    if input_tokens is not None:
        for tiered_model, (threshold, multiplier) in _TIERED_PRICING.items():
            if _normalize_model_name(tiered_model) in needle and input_tokens > threshold:
                return round(base * multiplier, 4)

    return base


def get_model_capability(provider: str, model: str) -> ModelCapability | None:
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
