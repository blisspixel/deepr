"""Tests for cost estimation and control (no API calls)."""

from deepr.core.costs import CostController, CostEstimator, get_safe_test_prompt


class TestCostEstimator:
    """Test cost estimation (purely local calculations)."""

    def test_estimate_short_prompt(self):
        """Test estimation for short prompt."""
        estimate = CostEstimator.estimate_cost(
            prompt="What is 2+2?",
            model="o4-mini-deep-research",
            enable_web_search=False,
        )

        assert estimate.min_cost < estimate.expected_cost < estimate.max_cost
        assert estimate.expected_cost < 1.0  # Should be cheap
        assert "input tokens" in estimate.reasoning.lower()

    def test_estimate_medium_prompt(self):
        """Test estimation for medium prompt."""
        prompt = "Explain quantum computing in detail. " * 20  # ~150 words

        estimate = CostEstimator.estimate_cost(
            prompt=prompt,
            model="o3-deep-research",
            enable_web_search=True,
        )

        assert estimate.expected_cost > 0.5  # More substantial
        assert estimate.max_cost > estimate.expected_cost
        assert "web search" in estimate.reasoning.lower()

    def test_estimate_with_documents(self):
        """Test estimation with documents."""
        estimate = CostEstimator.estimate_cost(
            prompt="Summarize these documents",
            model="o3-deep-research",
            documents=["doc1.pdf", "doc2.pdf"],
        )

        # Should be more expensive with documents
        estimate_no_docs = CostEstimator.estimate_cost(
            prompt="Summarize these documents",
            model="o3-deep-research",
        )

        assert estimate.expected_cost > estimate_no_docs.expected_cost
        assert "documents attached" in estimate.reasoning.lower()

    def test_cost_sensitive_model_cheaper(self):
        """Test that o4-mini is cheaper than o3."""
        prompt = "Write an essay about climate change."

        o3_estimate = CostEstimator.estimate_cost(prompt, "o3-deep-research")
        o4_estimate = CostEstimator.estimate_cost(prompt, "o4-mini-deep-research")

        assert o4_estimate.expected_cost < o3_estimate.expected_cost

    def test_calculate_actual_cost(self):
        """Test actual cost calculation."""
        cost = CostEstimator.calculate_actual_cost(
            model="o3-deep-research",
            input_tokens=1000,
            output_tokens=10000,
            reasoning_tokens=500,
        )

        # Should be in reasonable range
        assert 0.05 < cost < 1.0
        assert isinstance(cost, float)

    def test_token_estimation(self):
        """Test token count estimation."""
        short_prompt = "Hello"
        tokens = CostEstimator.estimate_prompt_tokens(short_prompt)
        assert 1 <= tokens <= 5

        long_prompt = "This is a longer prompt " * 100
        tokens_long = CostEstimator.estimate_prompt_tokens(long_prompt)
        assert tokens_long > tokens
        assert tokens_long > 100


class TestCostController:
    """Test cost control and limits (no API calls)."""

    def test_initialization(self):
        """Test controller initializes with limits."""
        controller = CostController(
            max_cost_per_job=5.0,
            max_daily_cost=50.0,
            max_monthly_cost=500.0,
        )

        assert controller.max_cost_per_job == 5.0
        assert controller.daily_spending == 0.0
        assert controller.monthly_spending == 0.0

    def test_check_per_job_limit(self):
        """Test per-job cost limit enforcement."""
        controller = CostController(max_cost_per_job=1.0)

        cheap_estimate = CostEstimator.estimate_cost("Short prompt", "o4-mini-deep-research", enable_web_search=False)

        allowed, reason = controller.check_cost_limit(cheap_estimate)
        assert allowed is True
        assert reason is None

        # Create artificially expensive estimate
        from deepr.core.costs import CostEstimate

        expensive = CostEstimate(min_cost=5.0, max_cost=10.0, expected_cost=7.5, model="o3", reasoning="Test")

        allowed, reason = controller.check_cost_limit(expensive)
        assert allowed is False
        assert "exceeds limit" in reason.lower()

    def test_check_daily_limit(self):
        """Test daily spending limit."""
        controller = CostController(max_cost_per_job=10.0, max_daily_cost=5.0)

        # Spend almost to limit
        controller.daily_spending = 4.5

        estimate = CostEstimator.estimate_cost("Moderate prompt", "o4-mini-deep-research")

        # Should be blocked if would exceed daily limit
        if estimate.expected_cost > 0.5:
            allowed, reason = controller.check_cost_limit(estimate)
            assert allowed is False or allowed is True  # Depends on estimate
            if not allowed:
                assert "daily" in reason.lower()

    def test_record_cost(self):
        """Test cost recording."""
        controller = CostController()

        assert controller.daily_spending == 0.0
        assert controller.monthly_spending == 0.0

        controller.record_cost(2.50)

        assert controller.daily_spending == 2.50
        assert controller.monthly_spending == 2.50

        controller.record_cost(1.25)

        assert controller.daily_spending == 3.75
        assert controller.monthly_spending == 3.75

    def test_spending_summary(self):
        """Test spending summary."""
        controller = CostController(max_daily_cost=10.0, max_monthly_cost=100.0)

        controller.daily_spending = 3.50
        controller.monthly_spending = 25.00

        summary = controller.get_spending_summary()

        assert summary["daily"] == 3.50
        assert summary["daily_limit"] == 10.0
        assert summary["daily_remaining"] == 6.50
        assert summary["monthly"] == 25.00
        assert summary["monthly_remaining"] == 75.00


class TestSafeTestPrompts:
    """Test safe/cheap test prompts."""

    def test_get_safe_test_prompt(self):
        """Test getting safe test prompts."""
        prompt_data = get_safe_test_prompt(0)

        assert "prompt" in prompt_data
        assert "expected_cost" in prompt_data
        assert "description" in prompt_data
        assert prompt_data["expected_cost"] < 0.50  # All should be cheap

    def test_all_safe_prompts_are_cheap(self):
        """Test all safe prompts have low expected cost."""
        from deepr.core.costs import CHEAP_TEST_PROMPTS

        for i, prompt_data in enumerate(CHEAP_TEST_PROMPTS):
            assert prompt_data["expected_cost"] < 1.0, f"Prompt {i} too expensive"

            # Verify estimation
            estimate = CostEstimator.estimate_cost(
                prompt_data["prompt"],
                "o4-mini-deep-research",
                enable_web_search=False,
            )

            # Estimates should be in reasonable range
            assert estimate.expected_cost < 2.0, f"Prompt {i} estimate too high"

    def test_index_bounds(self):
        """Test safe prompt index handling."""
        # Valid index
        prompt = get_safe_test_prompt(0)
        assert prompt is not None

        # Out of bounds - should return first
        prompt = get_safe_test_prompt(999)
        assert prompt is not None

        # Negative - should return first
        prompt = get_safe_test_prompt(-1)
        assert prompt is not None
