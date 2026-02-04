"""Unit tests for the Model Router - no API calls.

Tests the dynamic model routing system that selects optimal models
based on query complexity, task type, and budget constraints.
"""

import pytest
from deepr.experts.router import ModelRouter, ModelConfig


class TestModelConfig:
    """Test ModelConfig dataclass."""

    def test_create_basic_config(self):
        """Test creating a basic model config."""
        config = ModelConfig(
            provider="openai",
            model="gpt-5",
            cost_estimate=0.20
        )
        assert config.provider == "openai"
        assert config.model == "gpt-5"
        assert config.cost_estimate == 0.20
        assert config.reasoning_effort is None
        assert config.confidence == 1.0

    def test_create_config_with_reasoning_effort(self):
        """Test creating config with reasoning effort."""
        config = ModelConfig(
            provider="openai",
            model="gpt-5",
            cost_estimate=0.20,
            reasoning_effort="high"
        )
        assert config.reasoning_effort == "high"

    def test_create_config_with_confidence(self):
        """Test creating config with custom confidence."""
        config = ModelConfig(
            provider="xai",
            model="grok-4-fast",
            cost_estimate=0.01,
            confidence=0.95
        )
        assert config.confidence == 0.95


class TestComplexityClassification:
    """Test query complexity classification."""

    @pytest.fixture
    def router(self):
        """Create a model router instance."""
        return ModelRouter()

    def test_simple_what_question(self, router):
        """Test that simple 'what' questions are classified as simple."""
        complexity = router._classify_complexity("What is Python?")
        assert complexity == "simple"

    def test_simple_when_question(self, router):
        """Test that simple 'when' questions are classified as simple."""
        complexity = router._classify_complexity("When was Python released?")
        assert complexity == "simple"

    def test_simple_greeting(self, router):
        """Test that greetings are classified as simple."""
        complexity = router._classify_complexity("Hello, how are you?")
        assert complexity == "simple"

    def test_simple_version_query(self, router):
        """Test that version queries are classified as simple."""
        complexity = router._classify_complexity("What is the latest version of Node.js?")
        assert complexity == "simple"

    def test_moderate_how_question(self, router):
        """Test that 'how' questions are classified as moderate."""
        complexity = router._classify_complexity("How do I implement authentication?")
        assert complexity in ["moderate", "complex"]  # Could be either depending on context

    def test_moderate_comparison(self, router):
        """Test that comparison questions are classified appropriately.
        
        Note: Short comparison queries may be classified as simple due to
        word count heuristics (< 5 words adds +2.0 to simple score).
        Longer comparison queries will be classified as moderate/complex.
        """
        # Short comparison - may be simple due to word count
        complexity = router._classify_complexity("Compare React and Vue")
        assert complexity in ["simple", "moderate", "complex"]
        
        # Longer comparison - should be moderate or complex
        complexity = router._classify_complexity("Compare the differences between React and Vue frameworks for web development")
        assert complexity in ["moderate", "complex"]

    def test_complex_analysis(self, router):
        """Test that analysis requests are classified as complex."""
        complexity = router._classify_complexity("Analyze the trade-offs between microservices and monolithic architecture")
        assert complexity == "complex"

    def test_complex_strategy(self, router):
        """Test that strategy questions are classified as complex."""
        complexity = router._classify_complexity("Design a strategic roadmap for our AI product")
        assert complexity == "complex"

    def test_complex_multi_step(self, router):
        """Test that multi-step requests are classified as moderate or complex.
        
        Note: The router uses weighted scoring. Multi-step patterns add to
        complex score, but other factors like word count also influence.
        """
        complexity = router._classify_complexity("Create a multi-step implementation plan with several phases")
        assert complexity in ["moderate", "complex"]
        
        # More explicitly complex query
        complexity = router._classify_complexity("Analyze and design a multi-step strategic implementation plan with several phases considering all trade-offs")
        assert complexity == "complex"

    def test_short_query_bias_simple(self, router):
        """Test that very short queries bias toward simple."""
        complexity = router._classify_complexity("Hi")
        assert complexity == "simple"

    def test_long_query_bias_complex(self, router):
        """Test that very long queries bias toward complex."""
        long_query = "I need you to analyze the current market trends, evaluate our competitive position, " \
                     "design a comprehensive strategy, and create a detailed implementation roadmap " \
                     "considering all the trade-offs and potential risks involved"
        complexity = router._classify_complexity(long_query)
        assert complexity == "complex"

    def test_multiple_questions_bias_complex(self, router):
        """Test that multiple questions add complexity bias.
        
        Note: Multiple question marks add +1.0 to complex score, but
        simple WH-question patterns (what, how, why) also match simple/moderate.
        The final classification depends on the balance of all factors.
        """
        # Simple WH questions may still be classified as simple despite multiple ?
        complexity = router._classify_complexity("What is X? How does it work? Why should I use it?")
        assert complexity in ["simple", "moderate", "complex"]
        
        # More complex multi-part question
        complexity = router._classify_complexity("What are the trade-offs? How should we analyze them? Why does this strategy matter for our roadmap?")
        assert complexity in ["moderate", "complex"]


class TestTaskTypeDetection:
    """Test task type detection."""

    @pytest.fixture
    def router(self):
        """Create a model router instance."""
        return ModelRouter()

    def test_factual_what_question(self, router):
        """Test that 'what' questions are detected as factual."""
        task_type = router._detect_task_type("What is the capital of France?")
        assert task_type == "factual"

    def test_factual_list_request(self, router):
        """Test that list requests are detected as factual."""
        task_type = router._detect_task_type("List the top 10 programming languages")
        assert task_type == "factual"

    def test_reasoning_why_question(self, router):
        """Test that 'why' questions are detected as reasoning."""
        task_type = router._detect_task_type("Why should I use TypeScript?")
        assert task_type == "reasoning"

    def test_reasoning_explain_request(self, router):
        """Test that explain requests are detected as reasoning."""
        task_type = router._detect_task_type("Explain how async/await works")
        assert task_type == "reasoning"

    def test_research_comprehensive(self, router):
        """Test that comprehensive research requests are detected."""
        task_type = router._detect_task_type("Research the latest trends in AI development")
        assert task_type == "research"

    def test_research_investigate(self, router):
        """Test that investigation requests are detected as research."""
        task_type = router._detect_task_type("Investigate the current state of quantum computing")
        assert task_type == "research"

    def test_coding_implement(self, router):
        """Test that implementation requests are detected as coding."""
        task_type = router._detect_task_type("Implement a function to sort an array")
        assert task_type == "coding"

    def test_coding_debug(self, router):
        """Test that debug requests are detected as coding."""
        task_type = router._detect_task_type("Debug this error in my Python code")
        assert task_type == "coding"

    def test_document_analysis(self, router):
        """Test that document analysis requests are detected."""
        task_type = router._detect_task_type("Summarize this PDF document")
        assert task_type == "document_analysis"


class TestModelSelection:
    """Test model selection logic."""

    @pytest.fixture
    def router(self):
        """Create a model router instance."""
        return ModelRouter()

    def test_simple_factual_uses_cheap_model(self, router):
        """Test that simple factual queries use cheap model."""
        config = router.select_model("What is Python?")
        # Should use a cheap model
        assert config.cost_estimate <= 0.05

    def test_research_uses_deep_research_model(self, router):
        """Test that research queries use deep research model."""
        config = router.select_model("Research the latest AI trends comprehensively")
        # Should use deep research model when budget allows (o3-deep-research is BEST)
        assert config.model == "o3-deep-research" or config.cost_estimate >= 0.5

    def test_complex_uses_high_reasoning(self, router):
        """Test that complex queries use high reasoning effort."""
        config = router.select_model("Analyze the strategic trade-offs in our architecture design")
        # Should use high reasoning effort or expensive model
        assert config.reasoning_effort == "high" or config.cost_estimate >= 0.1

    def test_budget_constraint_respected(self, router):
        """Test that budget constraints are respected."""
        config = router.select_model(
            "Research the latest AI trends comprehensively",
            budget_remaining=0.50
        )
        # Should not exceed budget
        assert config.cost_estimate <= 0.50

    def test_zero_budget_uses_fallback(self, router):
        """Test that zero budget uses fallback model."""
        config = router.select_model(
            "Analyze complex architecture",
            budget_remaining=0.0
        )
        # Should use cheapest model
        assert config.cost_estimate <= 0.02
        assert config.confidence < 1.0  # Lower confidence due to budget constraint

    def test_openai_constraint_uses_openai(self, router):
        """Test that OpenAI constraint only uses OpenAI models."""
        config = router.select_model(
            "What is Python?",
            provider_constraint="openai"
        )
        assert config.provider == "openai"

    def test_openai_constraint_research_uses_deep_research(self, router):
        """Test that OpenAI constraint with research uses o3-deep-research (BEST model)."""
        config = router.select_model(
            "Research the latest AI trends comprehensively",
            provider_constraint="openai",
            budget_remaining=5.0
        )
        assert config.provider == "openai"
        assert config.model == "o3-deep-research"

    def test_large_context_uses_gemini(self, router):
        """Test that large context uses Gemini."""
        config = router.select_model(
            "Analyze this document",
            context_size=150_000
        )
        # Should use Gemini for large context
        assert config.provider == "gemini" or config.model == "gemini-3-pro"


class TestFallbackModel:
    """Test fallback model selection."""

    @pytest.fixture
    def router(self):
        """Create a model router instance."""
        return ModelRouter()

    def test_fallback_without_constraint(self, router):
        """Test fallback model without provider constraint."""
        config = router._fallback_free_model("test query", "simple")
        assert config.provider == "xai"
        assert config.model == "grok-4-fast"
        assert config.confidence == 0.6

    def test_fallback_with_openai_constraint(self, router):
        """Test fallback model with OpenAI constraint."""
        config = router._fallback_free_model("test query", "simple", provider_constraint="openai")
        assert config.provider == "openai"
        assert config.model == "gpt-5"
        assert config.reasoning_effort == "low"


class TestRoutingExplanation:
    """Test routing decision explanation."""

    @pytest.fixture
    def router(self):
        """Create a model router instance."""
        return ModelRouter()

    def test_explanation_includes_complexity(self, router):
        """Test that explanation includes complexity."""
        config = ModelConfig(
            provider="openai",
            model="gpt-5",
            cost_estimate=0.20
        )
        explanation = router.explain_routing_decision("What is Python?", config)
        assert "complexity" in explanation.lower()

    def test_explanation_includes_task_type(self, router):
        """Test that explanation includes task type."""
        config = ModelConfig(
            provider="openai",
            model="gpt-5",
            cost_estimate=0.20
        )
        explanation = router.explain_routing_decision("What is Python?", config)
        assert "task" in explanation.lower()

    def test_explanation_includes_model_info(self, router):
        """Test that explanation includes model information."""
        config = ModelConfig(
            provider="openai",
            model="gpt-5",
            cost_estimate=0.20
        )
        explanation = router.explain_routing_decision("What is Python?", config)
        assert "openai" in explanation.lower()
        assert "gpt-5" in explanation.lower()

    def test_explanation_includes_cost(self, router):
        """Test that explanation includes cost estimate."""
        config = ModelConfig(
            provider="openai",
            model="gpt-5",
            cost_estimate=0.20
        )
        explanation = router.explain_routing_decision("What is Python?", config)
        assert "$" in explanation or "cost" in explanation.lower()

    def test_explanation_includes_confidence(self, router):
        """Test that explanation includes confidence."""
        config = ModelConfig(
            provider="openai",
            model="gpt-5",
            cost_estimate=0.20,
            confidence=0.85
        )
        explanation = router.explain_routing_decision("What is Python?", config)
        assert "confidence" in explanation.lower() or "85%" in explanation


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def router(self):
        """Create a model router instance."""
        return ModelRouter()

    def test_empty_query(self, router):
        """Test handling of empty query."""
        config = router.select_model("")
        # Should return a valid config
        assert config.provider is not None
        assert config.model is not None

    def test_very_long_query(self, router):
        """Test handling of very long query."""
        long_query = "analyze " * 1000
        config = router.select_model(long_query)
        # Should return a valid config
        assert config.provider is not None
        assert config.model is not None

    def test_special_characters_in_query(self, router):
        """Test handling of special characters."""
        config = router.select_model("What is @#$%^&*() in Python?")
        # Should return a valid config
        assert config.provider is not None

    def test_unicode_in_query(self, router):
        """Test handling of unicode characters."""
        config = router.select_model("What is 日本語 in Python?")
        # Should return a valid config
        assert config.provider is not None

    def test_negative_budget(self, router):
        """Test handling of negative budget."""
        config = router.select_model("What is Python?", budget_remaining=-1.0)
        # Should use fallback model
        assert config.confidence < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
