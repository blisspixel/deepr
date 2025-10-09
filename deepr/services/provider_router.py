"""
Provider Router Service

Intelligently routes research tasks to the best available provider based on:
- Task type (documentation vs analysis)
- Task complexity
- Cost preferences
- Provider availability
- Provider capabilities

This enables multi-provider support where users can configure multiple API keys
and Deepr automatically uses the best provider for each task.
"""

from typing import List, Dict, Optional, Literal
from dataclasses import dataclass


@dataclass
class ProviderCapability:
    """Describes a provider's capabilities and characteristics."""

    name: str  # "openai", "anthropic", "azure"
    supports_deep_research: bool  # Turnkey deep research API
    supports_extended_thinking: bool  # Reasoning traces
    supports_web_search: bool  # Built-in web search
    supports_tool_use: bool  # Custom tool orchestration
    avg_speed: str  # "fast", "medium", "slow"
    cost_tier: str  # "cheap", "moderate", "expensive"
    reliability: float  # 0.0-1.0
    max_context: int  # Maximum context window


# Provider catalog (will be populated based on research)
PROVIDER_CAPABILITIES = {
    "openai": ProviderCapability(
        name="openai",
        supports_deep_research=True,  # o3/o4-mini-deep-research
        supports_extended_thinking=True,  # o1/o3 reasoning
        supports_web_search=True,  # Built into deep research
        supports_tool_use=True,
        avg_speed="medium",
        cost_tier="moderate",
        reliability=0.95,
        max_context=128_000,
    ),
    "anthropic": ProviderCapability(
        name="anthropic",
        supports_deep_research=False,  # No turnkey API (we orchestrate)
        supports_extended_thinking=True,  # Extended Thinking
        supports_web_search=False,  # We provide via tools
        supports_tool_use=True,  # Excellent tool use
        avg_speed="fast",
        cost_tier="moderate",
        reliability=0.93,
        max_context=200_000,
    ),
    "azure": ProviderCapability(
        name="azure",
        supports_deep_research=True,  # Same as OpenAI
        supports_extended_thinking=True,
        supports_web_search=True,  # Bing Search integration
        supports_tool_use=True,
        avg_speed="medium",
        cost_tier="moderate",
        reliability=0.97,  # Enterprise SLA
        max_context=128_000,
    ),
}


class ProviderRouter:
    """
    Routes research tasks to optimal providers.

    Strategy:
    1. Check which providers are available (have API keys)
    2. Evaluate task requirements
    3. Score each provider for the task
    4. Select highest-scoring available provider
    """

    def __init__(self, available_providers: List[str]):
        """
        Initialize router with available providers.

        Args:
            available_providers: List of provider names with configured API keys
                                 e.g., ["openai", "anthropic"]
        """
        self.available_providers = available_providers
        self.capabilities = {
            name: PROVIDER_CAPABILITIES[name]
            for name in available_providers
            if name in PROVIDER_CAPABILITIES
        }

    def route_task(
        self,
        task_type: Literal["documentation", "analysis", "synthesis"],
        complexity: Literal["simple", "medium", "complex"] = "medium",
        prefer_cost: bool = False,
        prefer_speed: bool = False,
    ) -> str:
        """
        Select the best provider for a research task.

        Args:
            task_type: Type of research task
            complexity: Complexity level
            prefer_cost: Prioritize cheapest option
            prefer_speed: Prioritize fastest option

        Returns:
            Provider name to use

        Examples:
            # Documentation gathering (cheap, fast)
            router.route_task("documentation", "simple", prefer_cost=True)
            # -> "openai" (o4-mini-deep-research)

            # Deep analysis (thorough)
            router.route_task("analysis", "complex")
            # -> "anthropic" (Extended Thinking) or "openai" (o3)

            # Final synthesis
            router.route_task("synthesis", "complex")
            # -> Best available reasoning model
        """
        if not self.available_providers:
            raise ValueError("No providers available")

        # Default to first available provider
        if len(self.available_providers) == 1:
            return self.available_providers[0]

        # Score each provider
        scores = {}
        for provider_name, caps in self.capabilities.items():
            score = 0

            # Documentation tasks prefer turnkey deep research
            if task_type == "documentation":
                if caps.supports_deep_research:
                    score += 10
                if caps.avg_speed == "fast":
                    score += 5
                if caps.cost_tier == "cheap":
                    score += 5

            # Analysis tasks prefer extended thinking
            elif task_type == "analysis":
                if caps.supports_extended_thinking:
                    score += 10
                if complexity == "complex":
                    if caps.max_context > 150_000:
                        score += 5
                if caps.supports_tool_use:
                    score += 3

            # Synthesis tasks prefer best reasoning
            elif task_type == "synthesis":
                if caps.supports_extended_thinking:
                    score += 10
                if caps.reliability > 0.9:
                    score += 5

            # Apply preferences
            if prefer_cost:
                if caps.cost_tier == "cheap":
                    score += 10
                elif caps.cost_tier == "moderate":
                    score += 5

            if prefer_speed:
                if caps.avg_speed == "fast":
                    score += 10
                elif caps.avg_speed == "medium":
                    score += 5

            # Reliability always matters
            score += caps.reliability * 10

            scores[provider_name] = score

        # Return highest-scoring provider
        return max(scores.items(), key=lambda x: x[1])[0]

    def get_model_for_task(
        self,
        provider: str,
        task_type: Literal["documentation", "analysis", "synthesis"],
    ) -> str:
        """
        Get the optimal model from a provider for a task type.

        Args:
            provider: Provider name
            task_type: Type of research task

        Returns:
            Model name to use

        Examples:
            get_model_for_task("openai", "documentation")
            # -> "o4-mini-deep-research" (fast, cheap)

            get_model_for_task("openai", "analysis")
            # -> "o3-deep-research" (thorough)

            get_model_for_task("anthropic", "analysis")
            # -> "claude-3-5-sonnet-20250131" (Extended Thinking)
        """
        if provider == "openai" or provider == "azure":
            if task_type == "documentation":
                return "o4-mini-deep-research"  # Fast, cheap
            else:
                return "o3-deep-research"  # Thorough

        elif provider == "anthropic":
            # TODO: Update after research completes with current model names
            return "claude-3-5-sonnet-20250131"

        else:
            raise ValueError(f"Unknown provider: {provider}")


def create_router_from_env() -> ProviderRouter:
    """
    Create a provider router based on available API keys in environment.

    Checks for:
    - OPENAI_API_KEY
    - ANTHROPIC_API_KEY
    - AZURE_OPENAI_API_KEY

    Returns:
        ProviderRouter configured with available providers
    """
    import os

    available = []

    if os.getenv("OPENAI_API_KEY"):
        available.append("openai")

    if os.getenv("ANTHROPIC_API_KEY"):
        available.append("anthropic")

    if os.getenv("AZURE_OPENAI_API_KEY"):
        available.append("azure")

    if not available:
        raise ValueError(
            "No provider API keys found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or AZURE_OPENAI_API_KEY"
        )

    return ProviderRouter(available)
