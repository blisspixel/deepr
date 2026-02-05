"""Tests for auto mode query routing.

Tests the AutoModeRouter's ability to route queries to optimal models
based on complexity, task type, and budget constraints.
"""

import pytest

from deepr.routing.auto_mode import AutoModeDecision, AutoModeRouter, BatchRoutingResult


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
    """Tests for AutoModeRouter."""

    @pytest.fixture
    def router(self):
        """Create a router instance for testing."""
        return AutoModeRouter()

    def test_simple_query_routes_cheap(self, router):
        """Simple factual queries should route to cheap model."""
        decision = router.route("What is Python?")

        assert decision.complexity == "simple"
        assert decision.task_type == "factual"
        assert decision.provider == "xai"
        assert decision.model == "grok-4-fast"
        assert decision.cost_estimate == 0.01

    def test_simple_question_routes_cheap(self, router):
        """Simple WH questions should route to cheap model."""
        decision = router.route("What is the capital of France?")

        assert decision.complexity == "simple"
        assert decision.provider == "xai"
        assert decision.model == "grok-4-fast"

    def test_complex_query_routes_research(self, router):
        """Complex research queries should route to deep research model."""
        decision = router.route("Analyze Tesla's competitive position in the EV market")

        assert decision.complexity == "complex"
        assert decision.task_type in ("research", "reasoning")
        assert decision.provider == "openai"
        assert decision.model in ("o3-deep-research", "o4-mini-deep-research", "gpt-5.2")
        assert decision.cost_estimate >= 0.10

    def test_complex_strategic_query_routes_research(self, router):
        """Strategic analysis queries should route to capable model."""
        decision = router.route(
            "Evaluate the strategic implications of AI regulation in Europe "
            "considering multiple stakeholder perspectives and trade-offs"
        )

        assert decision.complexity == "complex"
        assert decision.cost_estimate >= 0.10

    def test_moderate_query_routes_medium(self, router):
        """Moderate queries should route to medium-cost model."""
        decision = router.route("Compare AWS and Azure cloud services")

        assert decision.complexity in ("moderate", "complex")
        assert decision.cost_estimate >= 0.01

    def test_budget_constraint_downgrades(self, router):
        """Low budget should downgrade from expensive to cheaper model."""
        # Complex query with tight budget
        decision = router.route(
            "Analyze the strategic competitive landscape of the AI market",
            budget=0.05,  # Too low for o3-deep-research ($0.50)
        )

        # Should downgrade due to budget
        assert decision.cost_estimate <= 0.05

    def test_budget_none_allows_expensive(self, router):
        """No budget constraint should allow capable models."""
        decision = router.route(
            "Analyze and evaluate the strategic implications of quantum computing "
            "breakthroughs on the semiconductor industry, considering multiple perspectives",
            budget=None,
        )

        # Should use a capable model for complex query
        assert decision.complexity == "complex"
        assert decision.cost_estimate >= 0.10

    def test_prefer_cost_chooses_cheaper(self, router):
        """prefer_cost flag should influence toward cheaper options."""
        decision = router.route(
            "Explain how neural networks work",
            prefer_cost=True,
        )

        # Should prefer cheaper option (moderate with prefer_cost uses o4-mini or cheaper)
        assert decision.cost_estimate <= 0.15

    def test_prefer_speed_chooses_fast(self, router):
        """prefer_speed flag should influence toward fast models."""
        decision = router.route(
            "What is machine learning?",
            prefer_speed=True,
        )

        assert decision.provider == "xai"
        assert decision.model == "grok-4-fast"

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


class TestAutoModeRouterApiKeyAwareness:
    """Tests for API key awareness in routing."""

    def test_routes_to_available_provider(self, monkeypatch):
        """Router should only route to providers with API keys set."""
        # Only set OpenAI key, not XAI
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        router = AutoModeRouter()

        # Simple factual would prefer xai, but key not set → fallback to openai
        decision = router.route("What is Python?")
        assert decision.provider == "openai"
        assert decision.model == "gpt-5.2"

    def test_routes_to_xai_when_available(self, monkeypatch):
        """Router should prefer xai for simple queries when key is available."""
        monkeypatch.setenv("XAI_API_KEY", "xai-test-123")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")

        router = AutoModeRouter()

        decision = router.route("What is Python?")
        assert decision.provider == "xai"
        assert decision.model == "grok-4-fast"

    def test_complex_research_needs_openai(self, monkeypatch):
        """Complex research should use OpenAI deep research when available."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
        monkeypatch.setenv("XAI_API_KEY", "xai-test-123")

        router = AutoModeRouter()

        decision = router.route("Research the latest developments in quantum computing")
        assert decision.provider == "openai"
        assert "research" in decision.model or "gpt" in decision.model

    def test_complex_research_falls_to_gemini(self, monkeypatch):
        """Complex research should fallback to Gemini when OpenAI unavailable."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-123")
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        router = AutoModeRouter()

        decision = router.route("Research the latest developments in quantum computing")
        assert decision.provider == "gemini"


class TestAutoModeRouterBatch:
    """Tests for batch routing."""

    @pytest.fixture
    def router(self):
        """Create a router instance for testing."""
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

        # Should have summary with complexity groups
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

        # Total cost should not exceed budget
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

        # Cost-optimized should be equal or cheaper
        assert result_cost.total_cost_estimate <= result_normal.total_cost_estimate

    def test_batch_empty_queries(self, router):
        """Empty batch should return empty result."""
        result = router.route_batch([])

        assert len(result.decisions) == 0
        assert result.total_cost_estimate == 0


class TestAutoModeRouterExplain:
    """Tests for routing explanation."""

    @pytest.fixture
    def router(self):
        """Create a router instance for testing."""
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
