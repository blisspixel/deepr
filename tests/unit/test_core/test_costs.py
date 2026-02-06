"""Tests for cost estimation, tracking, and control."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from deepr.core.costs import (
    CHEAP_TEST_PROMPTS,
    CostController,
    CostEstimate,
    CostEstimator,
    CostRecord,
    get_safe_test_prompt,
)


class TestCostEstimate:
    """Tests for CostEstimate dataclass."""

    def test_construction(self):
        est = CostEstimate(
            min_cost=0.01,
            max_cost=0.10,
            expected_cost=0.05,
            model="o3-deep-research",
            reasoning="test reasoning",
        )
        assert est.min_cost == 0.01
        assert est.max_cost == 0.10
        assert est.expected_cost == 0.05
        assert est.model == "o3-deep-research"
        assert est.reasoning == "test reasoning"


class TestCostRecord:
    """Tests for CostRecord dataclass."""

    def test_construction(self):
        now = datetime.now(timezone.utc)
        rec = CostRecord(
            job_id="j1",
            provider="openai",
            model="o3-deep-research",
            input_tokens=1000,
            output_tokens=2000,
            reasoning_tokens=500,
            total_tokens=3500,
            cost=0.05,
            timestamp=now,
        )
        assert rec.job_id == "j1"
        assert rec.provider == "openai"
        assert rec.total_tokens == 3500
        assert rec.cost == 0.05
        assert rec.timestamp == now


class TestCostEstimator:
    """Tests for CostEstimator."""

    def test_estimate_prompt_tokens_simple(self):
        tokens = CostEstimator.estimate_prompt_tokens("Hello world")
        # 11 chars / 4 = 2 (int)
        assert tokens == 2

    def test_estimate_prompt_tokens_with_documents(self):
        tokens = CostEstimator.estimate_prompt_tokens("query", documents=["doc1", "doc2"])
        # 5 chars + 2 * 20000 = 40005 / 4 = 10001
        assert tokens == 10001

    def test_estimate_prompt_tokens_no_documents(self):
        tokens = CostEstimator.estimate_prompt_tokens("query", documents=None)
        assert tokens == 1  # 5 / 4 = 1

    def test_estimate_prompt_tokens_empty_documents(self):
        tokens = CostEstimator.estimate_prompt_tokens("query", documents=[])
        assert tokens == 1  # empty list treated as falsy

    def test_estimate_cost_deep_research_short_prompt(self):
        est = CostEstimator.estimate_cost("Hi", model="o3-deep-research")
        assert est.model == "o3-deep-research"
        assert est.min_cost <= est.expected_cost <= est.max_cost
        assert "Web search enabled" in est.reasoning

    def test_estimate_cost_deep_research_medium_prompt(self):
        prompt = "x" * 100  # 100 chars, between 50 and 200
        est = CostEstimator.estimate_cost(prompt, model="o3-deep-research")
        assert est.min_cost <= est.expected_cost <= est.max_cost

    def test_estimate_cost_deep_research_long_prompt(self):
        prompt = "x" * 300  # > 200 chars
        est = CostEstimator.estimate_cost(prompt, model="o3-deep-research")
        assert est.min_cost <= est.expected_cost <= est.max_cost

    def test_estimate_cost_no_web_search(self):
        est = CostEstimator.estimate_cost("Hi", enable_web_search=False)
        assert "Web search enabled" not in est.reasoning

    def test_estimate_cost_with_documents(self):
        est = CostEstimator.estimate_cost("query", documents=["doc1"])
        assert "1 documents attached" in est.reasoning

    def test_estimate_cost_regular_model(self):
        est = CostEstimator.estimate_cost("query", model="gpt-5")
        assert est.model == "gpt-5"
        assert est.min_cost <= est.expected_cost <= est.max_cost

    def test_estimate_cost_unknown_model_uses_default_pricing(self):
        est = CostEstimator.estimate_cost("query", model="unknown-model")
        assert est.model == "unknown-model"
        # Should use o3-deep-research pricing as fallback
        assert est.min_cost >= 0

    def test_calculate_actual_cost_known_model(self):
        cost = CostEstimator.calculate_actual_cost(
            model="o3-deep-research",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # input: 2.00, output: 8.00 => 10.00
        assert cost == 10.0

    def test_calculate_actual_cost_with_reasoning_tokens(self):
        cost = CostEstimator.calculate_actual_cost(
            model="o3-deep-research",
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=1_000_000,
        )
        # reasoning at output rate: 8.00
        assert cost == 8.0

    def test_calculate_actual_cost_unknown_model(self):
        cost = CostEstimator.calculate_actual_cost(
            model="unknown-model",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        # Falls back to o3-deep-research pricing
        assert cost == 10.0

    def test_calculate_actual_cost_zero_tokens(self):
        cost = CostEstimator.calculate_actual_cost(
            model="gpt-5",
            input_tokens=0,
            output_tokens=0,
        )
        assert cost == 0.0

    def test_web_search_multiplier_increases_output(self):
        no_search = CostEstimator.estimate_cost("Hi", enable_web_search=False)
        with_search = CostEstimator.estimate_cost("Hi", enable_web_search=True)
        assert with_search.max_cost > no_search.max_cost


class TestCostController:
    """Tests for CostController."""

    def test_init_defaults(self):
        ctrl = CostController()
        assert ctrl.max_cost_per_job == 5.0
        assert ctrl.max_daily_cost == 25.0
        assert ctrl.max_monthly_cost == 200.0
        assert ctrl.daily_spending == 0.0
        assert ctrl.monthly_spending == 0.0

    def test_init_custom_limits(self):
        ctrl = CostController(max_cost_per_job=10.0, max_daily_cost=50.0, max_monthly_cost=500.0)
        assert ctrl.max_cost_per_job == 10.0
        assert ctrl.max_daily_cost == 50.0
        assert ctrl.max_monthly_cost == 500.0

    def test_check_cost_limit_allowed(self):
        ctrl = CostController()
        est = CostEstimate(min_cost=0.01, max_cost=1.0, expected_cost=0.5, model="m", reasoning="r")
        allowed, reason = ctrl.check_cost_limit(est)
        assert allowed is True
        assert reason is None

    def test_check_cost_limit_per_job_exceeded(self):
        ctrl = CostController(max_cost_per_job=1.0)
        est = CostEstimate(min_cost=0.5, max_cost=2.0, expected_cost=1.0, model="m", reasoning="r")
        allowed, reason = ctrl.check_cost_limit(est)
        assert allowed is False
        assert "exceeds limit" in reason

    def test_check_cost_limit_daily_exceeded(self):
        ctrl = CostController(max_daily_cost=10.0)
        ctrl.daily_spending = 9.5
        est = CostEstimate(min_cost=0.5, max_cost=1.0, expected_cost=1.0, model="m", reasoning="r")
        allowed, reason = ctrl.check_cost_limit(est)
        assert allowed is False
        assert "daily limit" in reason.lower()

    def test_check_cost_limit_monthly_exceeded(self):
        ctrl = CostController(max_monthly_cost=10.0)
        ctrl.monthly_spending = 9.5
        est = CostEstimate(min_cost=0.5, max_cost=1.0, expected_cost=1.0, model="m", reasoning="r")
        allowed, reason = ctrl.check_cost_limit(est)
        assert allowed is False
        assert "monthly limit" in reason.lower()

    def test_record_cost(self):
        ctrl = CostController()
        ctrl.record_cost(5.0)
        assert ctrl.daily_spending == 5.0
        assert ctrl.monthly_spending == 5.0
        ctrl.record_cost(3.0)
        assert ctrl.daily_spending == 8.0
        assert ctrl.monthly_spending == 8.0

    def test_reset_if_needed_daily(self):
        ctrl = CostController()
        ctrl.daily_spending = 10.0
        ctrl.monthly_spending = 50.0
        ctrl.last_reset = datetime.now(timezone.utc) - timedelta(days=1, seconds=1)
        ctrl.reset_if_needed()
        assert ctrl.daily_spending == 0.0
        # Monthly should NOT be reset (same month possibly)
        assert ctrl.monthly_spending == 50.0

    def test_reset_if_needed_monthly(self):
        ctrl = CostController()
        ctrl.daily_spending = 10.0
        ctrl.monthly_spending = 50.0
        # Set last_reset to a different month
        ctrl.last_reset = datetime(2024, 1, 15, tzinfo=timezone.utc)
        with patch("deepr.core.costs.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 2, 1, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            ctrl.reset_if_needed()
        assert ctrl.monthly_spending == 0.0

    def test_get_spending_summary_structure(self):
        ctrl = CostController()
        ctrl.record_cost(5.0)
        summary = ctrl.get_spending_summary()
        assert "daily" in summary
        assert "daily_limit" in summary
        assert "daily_remaining" in summary
        assert "monthly" in summary
        assert "monthly_limit" in summary
        assert "monthly_remaining" in summary

    def test_get_spending_summary_values(self):
        ctrl = CostController(max_daily_cost=25.0, max_monthly_cost=200.0)
        ctrl.record_cost(10.0)
        summary = ctrl.get_spending_summary()
        assert summary["daily"] == 10.0
        assert summary["daily_limit"] == 25.0
        assert summary["daily_remaining"] == 15.0
        assert summary["monthly"] == 10.0
        assert summary["monthly_remaining"] == 190.0


class TestGetSafeTestPrompt:
    """Tests for get_safe_test_prompt."""

    def test_valid_index(self):
        prompt = get_safe_test_prompt(0)
        assert "prompt" in prompt
        assert "expected_cost" in prompt
        assert "description" in prompt

    def test_all_valid_indices(self):
        for i in range(len(CHEAP_TEST_PROMPTS)):
            prompt = get_safe_test_prompt(i)
            assert prompt == CHEAP_TEST_PROMPTS[i]

    def test_out_of_range_index(self):
        prompt = get_safe_test_prompt(999)
        assert prompt == CHEAP_TEST_PROMPTS[0]

    def test_negative_index(self):
        prompt = get_safe_test_prompt(-1)
        assert prompt == CHEAP_TEST_PROMPTS[0]
