"""Auto mode router for intelligent query routing based on complexity.

Routes queries to the most cost-effective model, checking API key
availability before selecting a provider:

- Simple factual queries → grok-4-fast ($0.01) or gpt-4.1-mini ($0.01)
- Simple other → gpt-4.1-mini ($0.01) or gemini-2.5-flash ($0.02)
- Moderate queries → o4-mini-deep-research ($0.10)
- Complex research → o3-deep-research ($0.50)
- Complex analysis → o4-mini-deep-research ($0.10) or gpt-4.1 ($0.04)

When benchmark results exist (data/benchmarks/routing_preferences.json),
the benchmark-recommended models override hardcoded defaults if their
provider has an API key configured.

This enables processing 20+ queries for $1-2 instead of $20-40.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from deepr.experts.router import ModelRouter
from deepr.observability.provider_router import AutonomousProviderRouter


@dataclass
class AutoModeDecision:
    """Routing decision for a query in auto mode.

    Attributes:
        provider: Selected provider (openai, xai, gemini)
        model: Selected model name
        complexity: Query complexity (simple, moderate, complex)
        task_type: Detected task type (factual, reasoning, research, coding, etc.)
        cost_estimate: Estimated cost in dollars
        confidence: Confidence in routing decision (0-1)
        reasoning: Human-readable explanation of routing choice
    """

    provider: str
    model: str
    complexity: Literal["simple", "moderate", "complex"]
    task_type: str
    cost_estimate: float
    confidence: float
    reasoning: str

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "provider": self.provider,
            "model": self.model,
            "complexity": self.complexity,
            "task_type": self.task_type,
            "cost_estimate": self.cost_estimate,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AutoModeDecision":
        """Create from dictionary."""
        return cls(
            provider=data["provider"],
            model=data["model"],
            complexity=data["complexity"],
            task_type=data["task_type"],
            cost_estimate=data["cost_estimate"],
            confidence=data["confidence"],
            reasoning=data["reasoning"],
        )


@dataclass
class BatchRoutingResult:
    """Result of routing a batch of queries.

    Attributes:
        decisions: List of routing decisions for each query
        summary: Summary statistics by complexity/model
        total_cost_estimate: Total estimated cost for all queries
    """

    decisions: list[AutoModeDecision]
    summary: dict[str, dict]
    total_cost_estimate: float


# Cost estimates per model (in dollars)
MODEL_COSTS = {
    ("xai", "grok-4-fast"): 0.01,
    ("openai", "gpt-5.2"): 0.25,
    ("openai", "gpt-5-mini"): 0.03,
    ("openai", "gpt-4.1"): 0.04,
    ("openai", "gpt-4.1-mini"): 0.01,
    ("openai", "o4-mini-deep-research"): 0.10,
    ("openai", "o3-deep-research"): 0.50,
    ("gemini", "gemini-3-pro"): 0.15,
    ("gemini", "gemini-2.5-flash"): 0.02,
    ("anthropic", "claude-opus-4-6"): 0.80,
    ("anthropic", "claude-opus-4-5"): 0.80,
    ("anthropic", "claude-sonnet-4-5"): 0.48,
    ("anthropic", "claude-haiku-4-5"): 0.05,
    ("azure-foundry", "o3-deep-research"): 0.50,
    ("azure-foundry", "gpt-5-mini"): 0.03,
    ("azure-foundry", "gpt-4.1"): 0.04,
    ("azure-foundry", "gpt-4.1-mini"): 0.01,
    ("azure-foundry", "gpt-4o"): 0.03,
    ("azure-foundry", "gpt-4o-mini"): 0.005,
}

# Provider → environment variable mapping for API key checks
_PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "xai": "XAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "azure": "AZURE_OPENAI_KEY",
    "azure-foundry": "AZURE_PROJECT_ENDPOINT",
}


def _has_api_key(provider: str) -> bool:
    """Check if an API key is configured for the given provider.

    Args:
        provider: Provider name (openai, xai, gemini, etc.)

    Returns:
        True if the provider has an API key set in the environment
    """
    env_var = _PROVIDER_KEY_ENV.get(provider)
    if not env_var:
        return False
    return bool(os.environ.get(env_var))


_logger = logging.getLogger(__name__)


def _load_benchmark_preferences() -> dict | None:
    """Load routing preferences from benchmark results if available.

    Returns:
        Parsed task_preferences dict, or None if file missing/invalid.
    """
    prefs_path = Path("data/benchmarks/routing_preferences.json")
    if not prefs_path.exists():
        return None
    try:
        data = json.loads(prefs_path.read_text(encoding="utf-8"))
        return data.get("task_preferences")
    except Exception:
        _logger.debug("Could not load benchmark routing preferences")
        return None


# Load once at module import
_BENCHMARK_PREFS = _load_benchmark_preferences()


def _benchmark_model_for(task_type: str, strategy: str = "best_value") -> tuple[str, str] | None:
    """Get the benchmark-recommended (provider, model) for a task type.

    Args:
        task_type: Task type key (e.g. 'quick_lookup', 'reasoning')
        strategy: 'best_quality' or 'best_value'

    Returns:
        (provider, model) tuple if recommendation exists and provider has an
        API key, otherwise None.
    """
    if not _BENCHMARK_PREFS or task_type not in _BENCHMARK_PREFS:
        return None
    model_key = _BENCHMARK_PREFS[task_type].get(strategy)
    if not model_key or "/" not in model_key:
        return None
    provider, model = model_key.split("/", 1)
    if _has_api_key(provider):
        return (provider, model)
    return None


class AutoModeRouter:
    """Routes queries to optimal models based on complexity and cost.

    Combines query analysis from ModelRouter with provider metrics from
    AutonomousProviderRouter to make intelligent routing decisions.

    Example:
        router = AutoModeRouter()

        # Route single query (adapts to available API keys)
        decision = router.route("What is Python?")
        # → grok-4-fast $0.01 (if XAI_API_KEY set)
        # → gpt-4.1-mini $0.01 (if only OPENAI_API_KEY set)

        # Route batch with budget
        results = router.route_batch(queries, budget_total=5.0)
    """

    def __init__(
        self,
        model_router: Optional[ModelRouter] = None,
        provider_router: Optional[AutonomousProviderRouter] = None,
    ):
        """Initialize auto mode router.

        Args:
            model_router: Optional ModelRouter instance (creates one if not provided)
            provider_router: Optional AutonomousProviderRouter (creates one if not provided)
        """
        self._model_router = model_router or ModelRouter()
        self._provider_router = provider_router or AutonomousProviderRouter()

        # Cache which providers have API keys configured
        self._available_providers = {p for p in _PROVIDER_KEY_ENV if _has_api_key(p)}

    def _is_provider_usable(self, provider: str) -> bool:
        """Check if a provider has an API key and a healthy circuit.

        Args:
            provider: Provider name

        Returns:
            True if provider has an API key configured
        """
        return provider in self._available_providers

    def route(
        self,
        query: str,
        budget: Optional[float] = None,
        prefer_cost: bool = False,
        prefer_speed: bool = False,
    ) -> AutoModeDecision:
        """Route a single query to the optimal model.

        Args:
            query: The research query
            budget: Maximum budget for this query (None = unlimited)
            prefer_cost: If True, prefer cheaper options when uncertain
            prefer_speed: If True, prefer faster options when uncertain

        Returns:
            AutoModeDecision with provider, model, and metadata
        """
        # Analyze query complexity and task type
        complexity = self._model_router._classify_complexity(query)
        task_type = self._model_router._detect_task_type(query)

        # Get model recommendation from ModelRouter
        model_config = self._model_router.select_model(
            query=query,
            budget_remaining=budget,
        )

        # Override with auto-mode specific routing rules
        provider, model, cost_estimate, reasoning = self._apply_auto_rules(
            complexity=complexity,
            task_type=task_type,
            budget=budget,
            prefer_cost=prefer_cost,
            prefer_speed=prefer_speed,
            base_provider=model_config.provider,
            base_model=model_config.model,
        )

        # Check provider health from autonomous router
        if not self._provider_router.is_circuit_available(provider, model):
            provider, model, cost_estimate, reasoning = self._get_fallback(complexity, task_type, budget)

        return AutoModeDecision(
            provider=provider,
            model=model,
            complexity=complexity,
            task_type=task_type,
            cost_estimate=cost_estimate,
            confidence=model_config.confidence,
            reasoning=reasoning,
        )

    def route_batch(
        self,
        queries: list[str],
        budget_total: Optional[float] = None,
        prefer_cost: bool = False,
    ) -> BatchRoutingResult:
        """Route a batch of queries with optional total budget constraint.

        Args:
            queries: List of research queries
            budget_total: Maximum total budget for all queries (None = unlimited)
            prefer_cost: If True, prefer cheaper options

        Returns:
            BatchRoutingResult with decisions and summary
        """
        decisions = []
        remaining_budget = budget_total

        # First pass: route all queries optimally
        for query in queries:
            per_query_budget = None
            if remaining_budget is not None:
                # Distribute remaining budget proportionally
                queries_left = len(queries) - len(decisions)
                per_query_budget = remaining_budget / queries_left if queries_left > 0 else 0

            decision = self.route(
                query=query,
                budget=per_query_budget,
                prefer_cost=prefer_cost or (budget_total is not None),
            )
            decisions.append(decision)

            if remaining_budget is not None:
                remaining_budget -= decision.cost_estimate
                # Ensure we don't go negative
                remaining_budget = max(0, remaining_budget)

        # Build summary
        summary = self._build_summary(decisions)
        total_cost = sum(d.cost_estimate for d in decisions)

        return BatchRoutingResult(
            decisions=decisions,
            summary=summary,
            total_cost_estimate=total_cost,
        )

    def _pick_provider(self, preferred: str, *fallbacks: str) -> str:
        """Pick the first usable provider from the given preference order.

        Checks API key availability. Returns the preferred provider if
        its key is configured, otherwise tries fallbacks in order.

        Args:
            preferred: First-choice provider
            *fallbacks: Backup providers in priority order

        Returns:
            The first provider with a configured API key,
            or the preferred provider as last resort
        """
        if self._is_provider_usable(preferred):
            return preferred
        for fb in fallbacks:
            if self._is_provider_usable(fb):
                return fb
        if not self._available_providers:
            raise ValueError(
                "No API keys configured. Set at least one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, XAI_API_KEY"
            )
        return preferred  # Has key but circuit may be open

    def _apply_auto_rules(
        self,
        complexity: str,
        task_type: str,
        budget: Optional[float],
        prefer_cost: bool,
        prefer_speed: bool,
        base_provider: str,
        base_model: str,
    ) -> tuple:
        """Apply auto-mode specific routing rules.

        Routing table (checked in order):
        - simple + factual → grok-4-fast ($0.01)
        - simple + other   → gpt-4.1-mini ($0.01)
        - moderate         → o4-mini-deep-research ($0.10) or grok-4-fast on tight budget
        - complex research → o3-deep-research ($0.50), degrades through o4-mini → gpt-4.1
        - complex analysis → o4-mini-deep-research ($0.10) or gpt-4.1 ($0.04)

        Each tier checks API key availability and falls back to the
        next usable provider.

        Returns:
            Tuple of (provider, model, cost_estimate, reasoning)
        """
        # --- Benchmark override: use measured best model if available ---
        if _BENCHMARK_PREFS and not prefer_cost:
            rec = _benchmark_model_for(task_type, "best_value")
            if rec:
                bm_provider, bm_model = rec
                cost = MODEL_COSTS.get((bm_provider, bm_model), 0.10)
                if budget is None or cost <= budget:
                    return (
                        bm_provider,
                        bm_model,
                        cost,
                        f"Benchmark-recommended for {task_type} → {bm_provider}/{bm_model} (${cost:.2f})",
                    )

        # --- Simple factual queries → grok-4-fast (cheapest, fastest) ---
        if complexity == "simple" and task_type == "factual":
            provider = self._pick_provider("xai", "openai", "gemini")
            if provider == "xai":
                return (
                    "xai",
                    "grok-4-fast",
                    0.01,
                    "Simple factual query → grok-4-fast ($0.01)",
                )
            # Fallback: openai gpt-4.1-mini is cheapest for simple queries
            if provider == "openai":
                return (
                    "openai",
                    "gpt-4.1-mini",
                    0.01,
                    "Simple factual query → gpt-4.1-mini ($0.01, XAI_API_KEY not set)",
                )
            return (
                "gemini",
                "gemini-2.5-flash",
                0.02,
                "Simple factual query → gemini-2.5-flash ($0.02, XAI/OpenAI keys not set)",
            )

        # --- Simple non-factual → gpt-4.1-mini (fast, cheapest) ---
        if complexity == "simple":
            provider = self._pick_provider("openai", "xai", "gemini")
            if provider == "openai":
                return (
                    "openai",
                    "gpt-4.1-mini",
                    0.01,
                    "Simple query → gpt-4.1-mini ($0.01)",
                )
            if provider == "xai":
                return (
                    "xai",
                    "grok-4-fast",
                    0.01,
                    "Simple query → grok-4-fast ($0.01, OPENAI_API_KEY not set)",
                )
            return (
                "gemini",
                "gemini-2.5-flash",
                0.02,
                "Simple query → gemini-2.5-flash ($0.02, OpenAI/XAI keys not set)",
            )

        # --- Moderate complexity → o4-mini-deep-research (good middle tier) ---
        if complexity == "moderate":
            if prefer_cost and budget is not None and budget < 0.05:
                provider = self._pick_provider("xai", "gemini", "openai")
                if provider == "xai":
                    return (
                        "xai",
                        "grok-4-fast",
                        0.01,
                        "Moderate query downgraded → grok-4-fast due to budget ($0.01)",
                    )
                return (
                    provider,
                    "gemini-2.5-flash" if provider == "gemini" else "gpt-4.1-mini",
                    0.02 if provider == "gemini" else 0.01,
                    f"Moderate query downgraded due to budget → {provider}",
                )

            provider = self._pick_provider("openai", "gemini", "xai")
            if provider == "openai":
                return (
                    "openai",
                    "o4-mini-deep-research",
                    0.10,
                    "Moderate query → o4-mini-deep-research ($0.10)",
                )
            if provider == "gemini":
                return (
                    "gemini",
                    "gemini-3-pro",
                    0.15,
                    "Moderate query → gemini-3-pro ($0.15, OPENAI_API_KEY not set)",
                )
            return (
                "xai",
                "grok-4-fast",
                0.01,
                "Moderate query → grok-4-fast ($0.01, OpenAI/Gemini keys not set)",
            )

        # --- Complex research → o3-deep-research (full power) ---
        if complexity == "complex" and task_type == "research":
            if budget is not None and budget < 0.50:
                # Budget too low for o3, try o4-mini-deep-research
                if budget >= 0.10 and self._is_provider_usable("openai"):
                    return (
                        "openai",
                        "o4-mini-deep-research",
                        0.10,
                        "Complex research budget-limited → o4-mini-deep-research ($0.10)",
                    )
                # Further downgrade
                provider = self._pick_provider("openai", "gemini", "xai")
                if provider == "openai":
                    return (
                        "openai",
                        "gpt-4.1",
                        0.04,
                        "Complex research budget-limited → gpt-4.1 ($0.04)",
                    )
                return (
                    provider,
                    "gemini-2.5-flash" if provider == "gemini" else "grok-4-fast",
                    0.02 if provider == "gemini" else 0.01,
                    f"Complex research budget-limited → {provider} fallback",
                )

            provider = self._pick_provider("openai", "azure-foundry", "gemini")
            if provider == "openai":
                return (
                    "openai",
                    "o3-deep-research",
                    0.50,
                    "Complex research → o3-deep-research ($0.50)",
                )
            if provider == "azure-foundry":
                return (
                    "azure-foundry",
                    "o3-deep-research",
                    0.50,
                    "Complex research → azure-foundry o3-deep-research ($0.50, OPENAI_API_KEY not set)",
                )
            return (
                "gemini",
                "gemini-3-pro",
                0.15,
                "Complex research → gemini-3-pro ($0.15, OPENAI_API_KEY not set)",
            )

        # --- Complex analysis (non-research) → o4-mini or gpt-4.1 ---
        if complexity == "complex":
            if budget is not None and budget < 0.10:
                provider = self._pick_provider("openai", "xai", "gemini")
                if provider == "openai":
                    return (
                        "openai",
                        "gpt-4.1",
                        0.04,
                        "Complex analysis budget-limited → gpt-4.1 ($0.04)",
                    )
                return (
                    provider,
                    "grok-4-fast" if provider == "xai" else "gemini-2.5-flash",
                    0.01 if provider == "xai" else 0.02,
                    f"Complex analysis budget-limited → {provider} fallback",
                )

            provider = self._pick_provider("openai", "gemini", "xai")
            if provider == "openai":
                return (
                    "openai",
                    "o4-mini-deep-research",
                    0.10,
                    "Complex analysis → o4-mini-deep-research ($0.10)",
                )
            if provider == "gemini":
                return (
                    "gemini",
                    "gemini-3-pro",
                    0.15,
                    "Complex analysis → gemini-3-pro ($0.15, OPENAI_API_KEY not set)",
                )
            return (
                "xai",
                "grok-4-fast",
                0.01,
                "Complex analysis → grok-4-fast ($0.01, only XAI_API_KEY available)",
            )

        # Default: use base model config
        cost = MODEL_COSTS.get((base_provider, base_model), 0.10)
        return (
            base_provider,
            base_model,
            cost,
            f"Default routing to {base_provider}/{base_model}",
        )

    def _get_fallback(
        self,
        complexity: str,
        task_type: str,
        budget: Optional[float],
    ) -> tuple:
        """Get fallback routing when primary provider circuit is open.

        Checks both API key availability and circuit breaker state.

        Returns:
            Tuple of (provider, model, cost_estimate, reasoning)
        """
        # Try gemini as fallback for complex queries
        if complexity == "complex" and self._is_provider_usable("gemini"):
            if self._provider_router.is_circuit_available("gemini", "gemini-3-pro"):
                return (
                    "gemini",
                    "gemini-3-pro",
                    0.15,
                    "Fallback to gemini-3-pro (primary provider unavailable)",
                )

        # Try o4-mini as lighter OpenAI fallback for complex queries
        if complexity in ("complex", "moderate") and self._is_provider_usable("openai"):
            if self._provider_router.is_circuit_available("openai", "o4-mini-deep-research"):
                return (
                    "openai",
                    "o4-mini-deep-research",
                    0.10,
                    "Fallback to o4-mini-deep-research (primary circuit open)",
                )

        # Try grok as universal fallback
        if self._is_provider_usable("xai"):
            if self._provider_router.is_circuit_available("xai", "grok-4-fast"):
                return (
                    "xai",
                    "grok-4-fast",
                    0.01,
                    "Fallback to grok-4-fast (primary provider unavailable)",
                )

        # Last resort: return openai gpt-4.1-mini even if circuit might be open
        return (
            "openai",
            "gpt-4.1-mini",
            0.01,
            "Last resort fallback to gpt-4.1-mini (all providers may be unhealthy)",
        )

    def _build_summary(self, decisions: list[AutoModeDecision]) -> dict[str, dict]:
        """Build summary statistics from routing decisions.

        Returns:
            Dictionary mapping complexity to stats
        """
        summary = {}

        for decision in decisions:
            key = f"{decision.complexity}"
            if key not in summary:
                summary[key] = {
                    "count": 0,
                    "cost_estimate": 0.0,
                    "models": {},
                }

            summary[key]["count"] += 1
            summary[key]["cost_estimate"] += decision.cost_estimate

            model_key = f"{decision.provider}/{decision.model}"
            if model_key not in summary[key]["models"]:
                summary[key]["models"][model_key] = 0
            summary[key]["models"][model_key] += 1

        return summary

    def explain_routing(self, query: str) -> str:
        """Generate detailed explanation of routing decision.

        Args:
            query: The query to explain routing for

        Returns:
            Human-readable explanation
        """
        decision = self.route(query)
        complexity = decision.complexity
        task_type = decision.task_type

        explanation = f"""
Query Analysis
──────────────
Query: {query[:80]}{"..." if len(query) > 80 else ""}
Complexity: {complexity}
Task Type: {task_type}

Routing Decision
────────────────
Provider: {decision.provider}
Model: {decision.model}
Cost Estimate: ${decision.cost_estimate:.2f}
Confidence: {decision.confidence:.0%}

Reasoning
─────────
{decision.reasoning}
"""
        return explanation.strip()
