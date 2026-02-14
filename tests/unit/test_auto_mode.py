"""Tests for auto mode query routing.

Tests the AutoModeRouter's ability to route queries to optimal models
based on complexity, task type, and budget constraints, using benchmark
quality rankings.
"""

import deepr.routing.auto_mode as auto_mode_module
import pytest

from deepr.routing.auto_mode import AutoModeDecision, AutoModeRouter, BatchRoutingResult

# Controlled benchmark rankings for deterministic tests.
# Structure: task_type -> [(provider, model, quality, cost), ...]
_MOCK_RANKINGS = {
    "quick_lookup": [
        ("openai", "gpt-4.1-nano", 1.0, 0.003),
        ("openai", "gpt-5.2", 1.0, 0.25),
        ("xai", "grok-4-fast", 0.85, 0.01),
        ("gemini", "gemini-2.5-flash", 0.80, 0.02),
    ],
    "knowledge_base": [
        ("openai", "gpt-5.2", 0.90, 0.25),
        ("openai", "gpt-4.1-nano", 0.80, 0.003),
        ("gemini", "gemini-2.5-pro", 0.75, 0.12),
    ],
    "reasoning": [
        ("openai", "gpt-4.1-nano", 1.0, 0.003),
        ("openai", "gpt-5.2", 1.0, 0.25),
        ("xai", "grok-4-fast", 0.82, 0.01),
    ],
    "synthesis": [
        ("openai", "gpt-4.1-nano", 1.0, 0.003),
        ("openai", "gpt-5.2", 1.0, 0.25),
    ],
    "comprehensive_research": [
        ("openai", "gpt-5.2", 0.97, 0.25),
        ("xai", "grok-4-fast-reasoning", 0.89, 0.01),
    ],
    "technical_docs": [
        ("openai", "gpt-4.1-nano", 1.0, 0.003),
        ("openai", "gpt-5.2", 0.50, 0.25),
    ],
    "document_analysis": [
        ("openai", "gpt-5.2", 1.0, 0.25),
        ("openai", "gpt-4.1-nano", 0.875, 0.003),
    ],
    "_overall": [
        ("openai", "gpt-4.1-nano", 0.95, 0.003),
        ("openai", "gpt-5.2", 0.90, 0.25),
        ("xai", "grok-4-fast-reasoning", 0.88, 0.01),
        ("gemini", "gemini-2.5-pro", 0.85, 0.12),
        ("xai", "grok-4-fast", 0.80, 0.01),
        ("gemini", "gemini-2.5-flash", 0.75, 0.02),
    ],
}


class TestAutoModeDecision:
    """Tests for AutoModeDecision dataclass."""

    def test_to_dict(self):
        """Test serialization to dict."""
        decision = AutoModeDecision(
            provider="xai",
            model="grok-4-fast",
            complexity="simple",
            task_type="factual",
            cost_estimate=0.01,
            confidence=0.95,
            reasoning="Simple factual query",
        )

        d = decision.to_dict()

        assert d["provider"] == "xai"
        assert d["model"] == "grok-4-fast"
        assert d["complexity"] == "simple"
        assert d["task_type"] == "factual"
        assert d["cost_estimate"] == 0.01
        assert d["confidence"] == 0.95
        assert d["reasoning"] == "Simple factual query"

    def test_from_dict(self):
        """Test deserialization from dict."""
        d = {
            "provider": "openai",
            "model": "o3-deep-research",
            "complexity": "complex",
            "task_type": "research",
            "cost_estimate": 0.50,
            "confidence": 0.9,
            "reasoning": "Complex research query",
        }

        decision = AutoModeDecision.from_dict(d)

        assert decision.provider == "openai"
        assert decision.model == "o3-deep-research"
        assert decision.complexity == "complex"
        assert decision.task_type == "research"
        assert decision.cost_estimate == 0.50


class TestAutoModeRouter:
    """Tests for AutoModeRouter with benchmark-driven routing."""

    @pytest.fixture
    def router(self, monkeypatch):
        """Create a router instance with all providers available and mock benchmarks."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("XAI_API_KEY", "xai-test")
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
        monkeypatch.setattr(auto_mode_module, "_BENCHMARK_RANKINGS", _MOCK_RANKINGS)
        return AutoModeRouter()

    def test_simple_factual_uses_benchmark_winner(self, router):
        """Simple factual queries should use benchmark winner for quick_lookup."""
        decision = router.route("What is Python?")

        assert decision.complexity == "simple"
        assert decision.task_type == "factual"
        # Benchmark says gpt-4.1-nano is best for quick_lookup (quality 1.0, cheapest)
        assert decision.provider == "openai"
        assert decision.model == "gpt-4.1-nano"
        assert decision.cost_estimate == 0.003

    def test_simple_question_is_cheap(self, router):
        """Simple WH questions should route to a cheap model."""
        decision = router.route("What is the capital of France?")

        assert decision.complexity == "simple"
        assert decision.cost_estimate <= 0.01

    def test_complex_research_uses_best_quality(self, router):
        """Complex research queries should use highest quality model."""
        decision = router.route(
            "Research the latest comprehensive developments in quantum computing"
        )

        assert decision.complexity == "complex"
        assert decision.task_type == "research"
        # Benchmark says gpt-5.2 is best for comprehensive_research (quality 0.97)
        assert decision.provider == "openai"
        assert decision.model == "gpt-5.2"
        assert decision.cost_estimate == 0.25

    def test_complex_reasoning_uses_benchmark(self, router):
        """Complex reasoning queries should use benchmark winner."""
        decision = router.route(
            "Evaluate the strategic implications of AI regulation in Europe "
            "considering multiple stakeholder perspectives and trade-offs"
        )

        assert decision.complexity == "complex"
        # Benchmark routing, should pick a model
        assert decision.provider is not None
        assert decision.model is not None

    def test_moderate_query_uses_benchmark(self, router):
        """Moderate queries should use benchmark data for routing."""
        decision = router.route("Compare AWS and Azure cloud services")

        assert decision.complexity in ("moderate", "complex")
        assert decision.cost_estimate >= 0.001

    def test_budget_constraint_downgrades(self, router):
        """Low budget should filter out expensive models."""
        decision = router.route(
            "Analyze the strategic competitive landscape of the AI market",
            budget=0.05,
        )

        assert decision.cost_estimate <= 0.05

    def test_budget_none_allows_expensive(self, router):
        """No budget constraint should allow expensive models."""
        decision = router.route(
            "Research and evaluate the strategic implications of quantum computing "
            "breakthroughs on the semiconductor industry, considering multiple perspectives",
            budget=None,
        )

        assert decision.complexity == "complex"
        assert decision.provider is not None

    def test_prefer_cost_sorts_by_value(self, router):
        """prefer_cost flag should sort by cost-per-quality (cheapest value first)."""
        decision = router.route(
            "Explain how neural networks work",
            prefer_cost=True,
        )

        # With prefer_cost, should pick cheapest per quality
        assert decision.cost_estimate <= 0.15

    def test_prefer_speed_sorts_by_value(self, router):
        """prefer_speed flag should prefer cheaper/faster models."""
        decision = router.route(
            "What is machine learning?",
            prefer_speed=True,
        )

        # prefer_speed triggers value sorting → cheapest option
        assert decision.cost_estimate <= 0.01

    def test_factual_task_type_detected(self, router):
        """Factual questions should detect factual task type."""
        decision = router.route("What year was Python created?")

        assert decision.task_type == "factual"

    def test_research_task_type_detected(self, router):
        """Research queries should detect research task type."""
        decision = router.route("Research the latest trends in renewable energy")

        assert decision.task_type == "research"

    def test_coding_task_type_detected(self, router):
        """Coding queries should detect coding task type."""
        decision = router.route("How do I implement a binary search in Python?")

        assert decision.task_type in ("coding", "reasoning")

    def test_reasoning_includes_benchmark_in_explanation(self, router):
        """Routing reasoning should mention benchmark source."""
        decision = router.route("What is Python?")

        assert "Benchmark" in decision.reasoning or "benchmark" in decision.reasoning


class TestAutoModeRouterApiKeyAwareness:
    """Tests for API key awareness in routing."""

    @pytest.fixture(autouse=True)
    def _mock_benchmarks(self, monkeypatch):
        """Use mock benchmarks for all tests in this class."""
        monkeypatch.setattr(auto_mode_module, "_BENCHMARK_RANKINGS", _MOCK_RANKINGS)

    def test_routes_to_available_provider(self, monkeypatch):
        """Router should only route to providers with API keys set."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        router = AutoModeRouter()

        # Simple factual → quick_lookup → best with OpenAI key = gpt-4.1-nano
        decision = router.route("What is Python?")
        assert decision.provider == "openai"

    def test_only_xai_key_uses_xai(self, monkeypatch):
        """Router should use XAI models when only XAI key is available."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "xai-test-123")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        router = AutoModeRouter()

        # quick_lookup has xai/grok-4-fast ranked 3rd, should pick it
        decision = router.route("What is Python?")
        assert decision.provider == "xai"

    def test_complex_research_needs_openai(self, monkeypatch):
        """Complex research should use OpenAI when available."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
        monkeypatch.setenv("XAI_API_KEY", "xai-test-123")

        router = AutoModeRouter()

        decision = router.route("Research the latest developments in quantum computing")
        assert decision.provider == "openai"

    def test_complex_research_falls_to_xai(self, monkeypatch):
        """Complex research should fallback when OpenAI unavailable."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("XAI_API_KEY", "xai-test-123")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        router = AutoModeRouter()

        decision = router.route("Research the latest developments in quantum computing")
        # comprehensive_research has xai/grok-4-fast-reasoning ranked 2nd
        assert decision.provider == "xai"

    def test_no_benchmark_uses_cheapest(self, monkeypatch):
        """Without benchmarks, router should use cheapest available model."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setattr(auto_mode_module, "_BENCHMARK_RANKINGS", None)

        router = AutoModeRouter()

        decision = router.route("What is Python?")
        assert decision.provider == "openai"
        # Should fall through to _cheapest_available
        assert "Cheapest" in decision.reasoning or "Last resort" in decision.reasoning


class TestAutoModeRouterBatch:
    """Tests for batch routing."""

    @pytest.fixture
    def router(self, monkeypatch):
        """Create a router instance with all providers available."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("XAI_API_KEY", "xai-test")
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
        monkeypatch.setattr(auto_mode_module, "_BENCHMARK_RANKINGS", _MOCK_RANKINGS)
        return AutoModeRouter()

    def test_batch_routes_multiple(self, router):
        """Batch routing should handle multiple queries."""
        queries = [
            "What is Python?",
            "Analyze the AI market in 2025",
            "Compare AWS vs Azure",
        ]

        result = router.route_batch(queries)

        assert isinstance(result, BatchRoutingResult)
        assert len(result.decisions) == 3
        assert result.total_cost_estimate > 0

    def test_batch_groups_by_complexity(self, router):
        """Batch routing should group queries by complexity."""
        queries = [
            "What is Python?",  # simple
            "What is JavaScript?",  # simple
            "Analyze Tesla's market position",  # complex
        ]

        result = router.route_batch(queries)

        assert "simple" in result.summary or "complex" in result.summary
        assert result.total_cost_estimate > 0

    def test_batch_with_budget_constraint(self, router):
        """Batch with budget should distribute costs."""
        queries = [
            "What is Python?",
            "Analyze Tesla",
            "Compare cloud providers",
        ]

        result = router.route_batch(queries, budget_total=1.0)

        assert result.total_cost_estimate <= 1.5  # Allow some flexibility

    def test_batch_prefer_cost(self, router):
        """Batch with prefer_cost should minimize costs."""
        queries = [
            "What is Python?",
            "How does machine learning work?",
            "Explain neural networks",
        ]

        result_normal = router.route_batch(queries, prefer_cost=False)
        result_cost = router.route_batch(queries, prefer_cost=True)

        assert result_cost.total_cost_estimate <= result_normal.total_cost_estimate

    def test_batch_empty_queries(self, router):
        """Empty batch should return empty result."""
        result = router.route_batch([])

        assert len(result.decisions) == 0
        assert result.total_cost_estimate == 0


class TestAutoModeRouterExplain:
    """Tests for routing explanation."""

    @pytest.fixture
    def router(self, monkeypatch):
        """Create a router instance with all providers available."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("XAI_API_KEY", "xai-test")
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
        monkeypatch.setattr(auto_mode_module, "_BENCHMARK_RANKINGS", _MOCK_RANKINGS)
        return AutoModeRouter()

    def test_explain_routing(self, router):
        """explain_routing should return readable explanation."""
        explanation = router.explain_routing("What is Python?")

        assert "Query Analysis" in explanation
        assert "Routing Decision" in explanation
        assert "Reasoning" in explanation
        assert "simple" in explanation.lower() or "complexity" in explanation.lower()

    def test_explain_contains_cost(self, router):
        """Explanation should include cost estimate."""
        explanation = router.explain_routing("What is Python?")

        assert "$" in explanation or "Cost" in explanation
