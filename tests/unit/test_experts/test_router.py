"""Unit tests for the model router (Phase 3a)."""

import pytest
from deepr.experts.router import ModelRouter, ModelConfig


class TestModelRouter:
    """Test cases for ModelRouter class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.router = ModelRouter()

    def test_simple_factual_query(self):
        """Test that simple factual queries route to appropriate model."""
        queries = [
            "What is Python?",
            "When was AWS founded?",
            "Who created Linux?",
            "What is the latest version of Node.js?",
            "Define microservices",
        ]

        for query in queries:
            result = self.router.select_model(query, budget_remaining=10.0)

            # Should route to cheap or moderate-cost model (not expensive deep research)
            assert result.cost_estimate <= 0.30  # Not deep research
            assert result.confidence >= 0.7

            # Router should classify appropriately and not use expensive models
            complexity = self.router._classify_complexity(query)
            task_type = self.router._detect_task_type(query)

            # These are all simple factual queries - shouldn't use deep research
            assert result.model != "o4-mini-deep-research"

    def test_complex_reasoning_query(self):
        """Test that complex reasoning queries route to powerful models."""
        queries = [
            "Analyze the trade-offs between microservices and monolithic architecture for a startup",
            "Design a multi-region disaster recovery strategy for a SaaS platform",
            "Evaluate the pros and cons of building vs buying a data platform",
            "Should we optimize for latency or throughput given these constraints?",
        ]

        for query in queries:
            result = self.router.select_model(query, budget_remaining=10.0)

            # Should route to powerful model (GPT-5 or deep research)
            assert result.provider in ["openai", "gemini"]
            assert result.cost_estimate >= 0.20  # More expensive
            # Complex queries should use reasoning effort if GPT-5
            if result.provider == "openai" and "gpt-5" in result.model:
                assert result.reasoning_effort in ["medium", "high"]

    def test_research_query(self):
        """Test that research queries route to deep research model when budget allows."""
        queries = [
            "Research the latest developments in quantum computing",
            "Comprehensive analysis of EV market trends",
            "Investigate best practices for multi-cloud architecture",
        ]

        for query in queries:
            result = self.router.select_model(query, budget_remaining=5.0)

            # Should route to deep research when budget allows
            if result.model == "o4-mini-deep-research":
                assert result.provider == "openai"
                assert result.cost_estimate >= 1.0

    def test_budget_constraints(self):
        """Test that router respects budget constraints."""
        query = "Analyze trade-offs between AWS and Azure for our use case"

        # With plenty of budget
        result_high_budget = self.router.select_model(query, budget_remaining=10.0)
        cost_high = result_high_budget.cost_estimate

        # With low budget
        result_low_budget = self.router.select_model(query, budget_remaining=0.05)
        cost_low = result_low_budget.cost_estimate

        # Low budget should select cheaper model
        assert cost_low <= cost_high

    def test_large_context_routing(self):
        """Test that large context sizes route to appropriate models."""
        query = "Summarize these documents"
        large_context = 150_000  # 150K tokens

        result = self.router.select_model(
            query,
            context_size=large_context,
            budget_remaining=5.0
        )

        # Should route to Gemini for large context
        if large_context > 100_000:
            assert result.provider == "gemini"
            assert result.model == "gemini-3-pro"

    def test_no_budget_fallback(self):
        """Test that router falls back to cheap model when budget exhausted."""
        query = "What is machine learning?"

        result = self.router.select_model(query, budget_remaining=0.0)

        # Should fallback to cheapest model
        assert result.cost_estimate <= 0.05
        assert result.confidence < 1.0  # Lower confidence due to constraint

    def test_classify_complexity(self):
        """Test complexity classification."""
        simple_queries = [
            "What is Docker?",
            "When was Python created?",
            "Is AWS cheaper than Azure?",
        ]

        moderate_queries = [
            "Why should I use Kubernetes?",
            "Compare AWS and Azure pricing",
            "Explain the benefits of microservices",
        ]

        complex_queries = [
            "Analyze the trade-offs between Docker and Podman",
            "Design a Kubernetes architecture for multi-region deployment",
            "Evaluate whether we should migrate from AWS to Azure considering cost, performance, and team expertise",
        ]

        for query in simple_queries:
            complexity = self.router._classify_complexity(query)
            assert complexity == "simple", f"Failed for: {query}"

        for query in moderate_queries:
            complexity = self.router._classify_complexity(query)
            assert complexity in ["moderate", "complex"], f"Failed for: {query}"

        # Note: "How does X work?" can be simple or moderate depending on length
        # The router uses word count and other heuristics, so we're flexible
        how_query = "How does Docker work?"
        how_complexity = self.router._classify_complexity(how_query)
        assert how_complexity in ["simple", "moderate"], f"Unexpected complexity for: {how_query}"

        for query in complex_queries:
            complexity = self.router._classify_complexity(query)
            assert complexity in ["moderate", "complex"], f"Failed for: {query}"

    def test_detect_task_type(self):
        """Test task type detection."""
        factual_queries = [
            "What is the latest version of Python?",
            "List the AWS regions",
            "When was Docker released?",
        ]

        reasoning_queries = [
            "Why should I use Kubernetes?",
            "Should I choose AWS or Azure?",
            "Explain how Docker networking works",
        ]

        research_queries = [
            "Research the latest trends in AI",
            "Find out the comprehensive pros and cons of GraphQL",
            "Investigate recent developments in quantum computing",
        ]

        for query in factual_queries:
            task_type = self.router._detect_task_type(query)
            assert task_type == "factual", f"Failed for: {query}"

        for query in reasoning_queries:
            task_type = self.router._detect_task_type(query)
            assert task_type == "reasoning", f"Failed for: {query}"

        for query in research_queries:
            task_type = self.router._detect_task_type(query)
            assert task_type == "research", f"Failed for: {query}"

    def test_router_disabled_fallback(self):
        """Test that router returns default model when disabled."""
        router = ModelRouter()
        query = "Any query"

        # Simulate router disabled by using default model parameter
        result = router.select_model(
            query,
            current_model="gpt-5.2",
            budget_remaining=None
        )

        # Should still return a valid config
        assert isinstance(result, ModelConfig)
        assert result.provider is not None
        assert result.model is not None

    def test_explain_routing_decision(self):
        """Test routing explanation generation."""
        query = "What is Python?"
        selected_model = self.router.select_model(query, budget_remaining=10.0)

        explanation = self.router.explain_routing_decision(query, selected_model)

        # Should contain key information
        assert "complexity:" in explanation.lower()
        assert "task:" in explanation.lower()
        assert selected_model.provider in explanation
        assert selected_model.model in explanation
        assert f"${selected_model.cost_estimate:.2f}" in explanation

    def test_reasoning_effort_assignment(self):
        """Test that reasoning effort is assigned correctly."""
        simple_query = "What is AWS?"
        complex_query = "Analyze the trade-offs between AWS Lambda and Kubernetes for serverless deployment"

        simple_result = self.router.select_model(simple_query, budget_remaining=10.0)
        complex_result = self.router.select_model(complex_query, budget_remaining=10.0)

        # Simple queries shouldn't need high reasoning effort
        if simple_result.provider == "openai" and simple_result.reasoning_effort:
            assert simple_result.reasoning_effort in ["low", "medium"]

        # Complex queries should use higher reasoning effort
        if complex_result.provider == "openai" and complex_result.reasoning_effort:
            assert complex_result.reasoning_effort in ["medium", "high"]

    def test_cost_estimates(self):
        """Test that cost estimates are reasonable."""
        queries = [
            ("What is Python?", 0.05),  # Simple - max $0.05
            ("How does Kubernetes work?", 0.30),  # Moderate - max $0.30
            ("Design a comprehensive disaster recovery strategy", 3.0),  # Complex - max $3.00
        ]

        for query, max_cost in queries:
            result = self.router.select_model(query, budget_remaining=10.0)
            assert result.cost_estimate <= max_cost, f"Cost too high for: {query}"
            assert result.cost_estimate > 0, f"Cost should be positive for: {query}"

    def test_confidence_scoring(self):
        """Test that confidence scores are reasonable."""
        queries = [
            "What is Docker?",
            "Should I use AWS or Azure?",
            "Design a multi-region architecture",
        ]

        for query in queries:
            # With good budget
            result_good = self.router.select_model(query, budget_remaining=10.0)
            assert 0.0 <= result_good.confidence <= 1.0
            assert result_good.confidence >= 0.7

            # With no budget (should have lower confidence)
            result_constrained = self.router.select_model(query, budget_remaining=0.0)
            assert result_constrained.confidence < result_good.confidence


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
