"""Dynamic model routing for optimal model selection based on query complexity, task type, and budget.

Implements Phase 3a of the Expert System roadmap: Model Router Architecture.

This router analyzes queries and automatically selects the most cost-effective model
while maintaining quality. Routes simple queries to fast/cheap models and complex
reasoning to deep research models.
"""

import os
import re
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class ModelConfig:
    """Configuration for a selected model."""

    provider: str
    model: str
    cost_estimate: float
    reasoning_effort: Optional[str] = None  # For GPT-5 adaptive reasoning
    confidence: float = 1.0  # Confidence in this routing decision


class ModelRouter:
    """Routes queries to optimal models based on complexity, task type, and budget."""

    # Complexity indicators (weighted scoring)
    COMPLEXITY_INDICATORS = {
        "simple": {
            "patterns": [
                r"\b(what|when|where|who)\b.*\?$",  # Simple WH questions ending with ?
                r"\b(is|are|was|were)\b\s+\w+",  # Simple is/are questions
                r"\b(yes|no|true|false)\b",  # Binary questions
                r"\b(hello|hi|hey|thanks|thank you)\b",  # Greetings
                r"\b(latest version|current version|version)\b",  # Version queries
                r"\b(define|definition|meaning)\b",  # Simple definitions
                r"\b(when did|when was|what is|what are)\b",  # Simple factual questions
            ],
            "weight": 2.0,  # Increased weight to prioritize simple classification
        },
        "moderate": {
            "patterns": [
                r"\b(how)\b",  # How questions (not when/what/where)
                r"\b(compare|difference|versus|vs)\b",  # Comparisons
                r"\b(explain|describe)\b",  # Explanations
                r"\b(best practice|recommendation)\b",  # Best practices
                r"\b(should|would|could)\b",  # Advisory questions
            ],
            "weight": 1.5,  # Reduced weight
        },
        "complex": {
            "patterns": [
                r"\b(analyze|evaluate|assess)\b",  # Analysis
                r"\b(design|architect|implement)\b",  # Design work
                r"\b(strategy|strategic|roadmap)\b",  # Strategic planning
                r"\b(optimize|improve|enhance)\b",  # Optimization
                r"\b(trade-off|tradeoff|pros and cons)\b",  # Trade-off analysis
                r"\b(multi-step|multiple|several)\b.*\b(step|phase|stage)\b",  # Multi-step
                r"\b(considering|given|taking into account)\b",  # Contextual reasoning
                r"\b(comprehensive|in-depth|thorough|extensive)\b",  # Depth indicators
            ],
            "weight": 3.0,
        },
    }

    # Task type detection
    TASK_TYPES = {
        "factual": [
            r"\b(what|when|where|who)\b",
            r"\b(list|enumerate|tell me about)\b",
            r"\b(version|date|time|name)\b",
        ],
        "reasoning": [
            r"\b(why|how)\b",
            r"\b(explain|understand|reasoning)\b",
            r"\b(analyze|evaluate|assess)\b",
            r"\b(should|would|could|recommend)\b",
        ],
        "research": [
            r"\b(research|investigate|find out)\b",
            r"\b(comprehensive|detailed|in-depth)\b",
            r"\b(latest|current|recent|new)\b.*\b(trend|development|news)\b",
            r"\b(compare.*and.*and)\b",  # Multiple comparisons
        ],
        "coding": [
            r"\b(code|implement|function|class|api)\b",
            r"\b(debug|error|bug|fix)\b",
            r"\b(python|javascript|typescript|java|go|rust)\b",
        ],
        "document_analysis": [
            r"\b(document|pdf|file|attachment)\b",
            r"\b(summarize|extract|parse)\b",
            r"\b(read|review|analyze).*\b(document|file|pdf)\b",
        ],
    }

    def __init__(self):
        """Initialize the model router with capability registry and benchmark data."""
        # Import registry lazily to avoid circular imports
        from deepr.providers.registry import MODEL_CAPABILITIES

        self.capabilities = MODEL_CAPABILITIES

        # Load benchmark rankings for OpenAI model selection
        use_benchmark_routing = os.getenv("DEEPR_USE_BENCHMARK_ROUTING", "").lower() in {"1", "true", "yes"}
        self._openai_bench = self._load_openai_benchmarks() if use_benchmark_routing else None

    def _load_openai_benchmarks(self) -> dict[str, list[tuple[str, float, float]]] | None:
        """Load benchmark rankings filtered to OpenAI models only.

        Returns:
            dict: task_type -> [(model, quality, cost), ...] sorted by quality desc,
            or None if no benchmark data.
        """
        import json
        from collections import defaultdict
        from pathlib import Path

        bench_dir = Path("data/benchmarks")
        if not bench_dir.exists():
            return None

        files = sorted(bench_dir.glob("benchmark_*.json"))
        if not files:
            return None

        try:
            data = json.loads(files[-1].read_text(encoding="utf-8"))
        except Exception:
            return None

        rankings_data = data.get("rankings", [])
        if not rankings_data:
            return None

        # Merge scores across tiers, OpenAI models only
        model_scores: dict[str, dict[str, float]] = defaultdict(dict)
        for r in rankings_data:
            model_key = r.get("model_key", "")
            if not model_key.startswith("openai/"):
                continue
            for task_type, score in r.get("scores_by_type", {}).items():
                prev = model_scores[model_key].get(task_type, 0)
                if score > prev:
                    model_scores[model_key][task_type] = score

        if not model_scores:
            return None

        # Build per-task-type rankings
        all_task_types: set[str] = set()
        for scores in model_scores.values():
            all_task_types.update(scores.keys())

        rankings: dict[str, list[tuple[str, float, float]]] = {}
        for task_type in all_task_types:
            ranked: list[tuple[str, float, float]] = []
            for model_key, scores in model_scores.items():
                if task_type not in scores:
                    continue
                quality = scores[task_type]
                model = model_key.split("/", 1)[1]
                cap = self.capabilities.get(model_key)
                cost = cap.cost_per_query if cap else 0.10
                ranked.append((model, quality, cost))
            ranked.sort(key=lambda r: (-r[1], r[2]))
            rankings[task_type] = ranked

        return rankings

    def _select_openai_from_benchmarks(
        self,
        complexity: str,
        task_type: str,
        budget_remaining: Optional[float],
    ) -> ModelConfig | None:
        """Select best OpenAI model using benchmark data.

        Returns ModelConfig or None if no benchmark data / no suitable model.
        """
        if not self._openai_bench:
            return None

        # Map to benchmark task types
        task_map = {
            ("simple", "factual"): "quick_lookup",
            ("simple", "reasoning"): "knowledge_base",
            ("moderate", "reasoning"): "reasoning",
            ("moderate", "research"): "synthesis",
            ("complex", "research"): "comprehensive_research",
            ("complex", "reasoning"): "reasoning",
            ("complex", "coding"): "technical_docs",
        }

        bench_task = task_map.get((complexity, task_type), task_type)
        ranked = self._openai_bench.get(bench_task)
        if not ranked:
            return None

        for model, quality, cost in ranked:
            if budget_remaining is not None and cost > budget_remaining:
                continue
            # Determine reasoning effort based on complexity
            effort = None
            if model.startswith("gpt-5"):
                effort = {"simple": "low", "moderate": "medium", "complex": "high"}.get(complexity, "medium")
            return ModelConfig(
                provider="openai",
                model=model,
                cost_estimate=cost,
                reasoning_effort=effort,
                confidence=min(quality, 0.95),
            )

        return None

    def select_model(
        self,
        query: str,
        context_size: int = 0,
        budget_remaining: Optional[float] = None,
        current_model: str = "gpt-5.2",
        provider_constraint: Optional[str] = None,
    ) -> ModelConfig:
        """Select the optimal model for a query.

        Args:
            query: The user's query
            context_size: Approximate size of context in tokens
            budget_remaining: Remaining budget in dollars (None = unlimited)
            current_model: The default/current model being used
            provider_constraint: Optional provider constraint (e.g., "openai" for vector store compatibility)

        Returns:
            ModelConfig with provider, model, and cost estimate
        """
        # Analyze query
        complexity = self._classify_complexity(query)
        task_type = self._detect_task_type(query)

        # Budget constraints
        if budget_remaining is not None and budget_remaining <= 0:
            return self._fallback_free_model(query, complexity, provider_constraint)

        # Route based on complexity and task type
        # If provider is constrained (e.g., for vector store compatibility), only use that provider
        if provider_constraint == "openai":
            # Try benchmark-driven selection first
            bench_result = self._select_openai_from_benchmarks(complexity, task_type, budget_remaining)
            if bench_result:
                return bench_result

            # Fallback: hardcoded OpenAI routing
            if task_type == "research" and (budget_remaining is None or budget_remaining >= 2.0):
                return ModelConfig(provider="openai", model="o3-deep-research", cost_estimate=2.0, confidence=0.9)

            if complexity == "complex" and (budget_remaining is None or budget_remaining >= 0.01):
                return ModelConfig(
                    provider="openai",
                    model="gpt-5.2",
                    cost_estimate=0.01,  # ~5K tokens @ $1.75/$14 per 1M
                    reasoning_effort="high",
                    confidence=0.9,
                )

            if complexity == "moderate" or task_type == "reasoning":
                return ModelConfig(
                    provider="openai",
                    model="gpt-5.2",
                    cost_estimate=0.005,  # ~2K tokens @ $1.75/$14 per 1M
                    reasoning_effort="medium",
                    confidence=0.85,
                )

            # Simple queries - use GPT-5.2 with low reasoning effort for speed (1-3 seconds)
            return ModelConfig(
                provider="openai",
                model="gpt-5.2",
                cost_estimate=0.001,  # ~500 tokens @ $1.75/$14 per 1M
                reasoning_effort="low",
                confidence=0.9,  # High confidence for simple queries
            )

        # No provider constraint - use best model across all providers
        if complexity == "simple" and task_type == "factual":
            # Simple factual queries → fast cheap model
            return ModelConfig(provider="xai", model="grok-4-fast", cost_estimate=0.01, confidence=0.95)

        if task_type == "research" and (budget_remaining is None or budget_remaining >= 2.0):
            # Deep research → o3-deep-research (best quality for deep research)
            return ModelConfig(provider="openai", model="o3-deep-research", cost_estimate=2.0, confidence=0.9)

        if context_size > 100_000 and (budget_remaining is None or budget_remaining >= 0.15):
            # Large context → Gemini
            return ModelConfig(provider="gemini", model="gemini-3-pro", cost_estimate=0.15, confidence=0.85)

        if complexity == "complex" and (budget_remaining is None or budget_remaining >= 0.25):
            # Complex reasoning → GPT-5 with high reasoning effort
            return ModelConfig(
                provider="openai", model="gpt-5.2", cost_estimate=0.30, reasoning_effort="high", confidence=0.9
            )

        if complexity == "moderate":
            # Moderate complexity → GPT-5.2 with medium reasoning or Grok if budget tight
            if budget_remaining is not None and budget_remaining < 0.20:
                return ModelConfig(provider="xai", model="grok-4-fast", cost_estimate=0.01, confidence=0.75)
            return ModelConfig(
                provider="openai", model="gpt-5.2", cost_estimate=0.20, reasoning_effort="medium", confidence=0.85
            )

        # Default: Keep current model with adaptive reasoning
        return ModelConfig(
            provider="openai", model=current_model, cost_estimate=0.20, reasoning_effort="medium", confidence=0.8
        )

    def _classify_complexity(self, query: str) -> Literal["simple", "moderate", "complex"]:
        """Classify query complexity using pattern matching.

        Args:
            query: The user's query

        Returns:
            Complexity level: simple, moderate, or complex
        """
        query_lower = query.lower()
        scores = {"simple": 0.0, "moderate": 0.0, "complex": 0.0}

        for level, config in self.COMPLEXITY_INDICATORS.items():
            for pattern in config["patterns"]:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    scores[level] += config["weight"]

        # Additional heuristics
        word_count = len(query.split())
        if word_count < 5:
            scores["simple"] += 2.0
        elif word_count > 20:
            scores["complex"] += 1.5

        # Count question marks (multiple questions = more complex)
        question_marks = query.count("?")
        if question_marks > 1:
            scores["complex"] += 1.0

        # Return highest scoring complexity level
        max_level = max(scores, key=scores.get)

        # If no clear signal, default to moderate
        if scores[max_level] == 0:
            return "moderate"

        return max_level

    def _detect_task_type(self, query: str) -> str:
        """Detect the primary task type of a query.

        Args:
            query: The user's query

        Returns:
            Task type: factual, reasoning, research, coding, or document_analysis
        """
        query_lower = query.lower()
        scores = {task: 0 for task in self.TASK_TYPES.keys()}

        for task_type, patterns in self.TASK_TYPES.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    scores[task_type] += 1

        # Return highest scoring task type, default to reasoning
        max_task = max(scores, key=scores.get)
        if scores[max_task] == 0:
            return "reasoning"

        return max_task

    def _fallback_free_model(
        self, query: str, complexity: str, provider_constraint: Optional[str] = None
    ) -> ModelConfig:
        """Fallback to free/cheap model when budget exhausted.

        Args:
            query: The user's query
            complexity: Query complexity level
            provider_constraint: Optional provider constraint

        Returns:
            ModelConfig for cheapest available model
        """
        # If constrained to OpenAI, use GPT-5.2 with low reasoning effort
        if provider_constraint == "openai":
            return ModelConfig(
                provider="openai",
                model="gpt-5.2",
                cost_estimate=0.001,  # Minimal cost for simple query
                reasoning_effort="low",
                confidence=0.6,
            )

        # Otherwise use grok-4-fast as cheapest option
        return ModelConfig(
            provider="xai",
            model="grok-4-fast",
            cost_estimate=0.01,
            confidence=0.6,  # Lower confidence due to budget constraint
        )

    def explain_routing_decision(self, query: str, selected_model: ModelConfig) -> str:
        """Generate human-readable explanation of routing decision.

        Useful for debugging and transparency (Phase 3b: Visible Thinking).

        Args:
            query: The user's query
            selected_model: The selected model configuration

        Returns:
            Human-readable explanation string
        """
        complexity = self._classify_complexity(query)
        task_type = self._detect_task_type(query)

        explanation = f"Routing decision for query (complexity: {complexity}, task: {task_type}):\n"
        explanation += f"Selected: {selected_model.provider}/{selected_model.model}\n"
        explanation += f"Cost estimate: ${selected_model.cost_estimate:.2f}\n"
        explanation += f"Confidence: {selected_model.confidence:.0%}\n"

        # Add reasoning
        if complexity == "simple" and selected_model.model == "grok-4-fast":
            explanation += "Reason: Simple query routed to fast, cheap model for cost efficiency\n"
        elif task_type == "research" and selected_model.model == "o3-deep-research":
            explanation += "Reason: Research task routed to deep reasoning model for quality\n"
        elif selected_model.reasoning_effort:
            explanation += f"Reason: {complexity.capitalize()} query using adaptive reasoning (effort: {selected_model.reasoning_effort})\n"

        return explanation
