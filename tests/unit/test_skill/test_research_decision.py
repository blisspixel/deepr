"""
Property-based tests for research mode classification.

Validates: Requirements 2.1, 2.2, 2.3, 10.2
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, strategies as st, assume, settings

# Add skills directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "skills" / "deepr-research" / "scripts"))

from research_decision import (
    ResearchMode,
    ResearchDecision,
    CostEstimate,
    classify_query,
    estimate_cost,
    requires_confirmation,
    MODE_COSTS,
)


class TestResearchModeClassification:
    """Property 2: Research Mode Classification Consistency"""
    
    @given(st.text(min_size=1, max_size=500).filter(lambda x: x.strip()))
    @settings(max_examples=100)
    def test_classification_always_returns_valid_mode(self, query: str):
        """
        Property: Any non-empty query produces a valid ResearchMode.
        Validates: Requirements 2.1, 2.2, 2.3
        """
        decision = classify_query(query)
        assert isinstance(decision.mode, ResearchMode)
        assert decision.mode in ResearchMode
    
    @given(st.text(min_size=1, max_size=500).filter(lambda x: x.strip()))
    @settings(max_examples=100)
    def test_classification_always_returns_cost_estimate(self, query: str):
        """
        Property: Every classification includes a cost estimate.
        Validates: Requirements 2.5, 5.1
        """
        decision = classify_query(query)
        assert isinstance(decision.cost, CostEstimate)
        assert decision.cost.min_cost >= 0
        assert decision.cost.max_cost >= decision.cost.min_cost
    
    @given(st.text(min_size=1, max_size=500).filter(lambda x: x.strip()))
    @settings(max_examples=100)
    def test_classification_always_returns_model(self, query: str):
        """
        Property: Every classification specifies a model.
        Validates: Requirements 10.2
        """
        decision = classify_query(query)
        assert isinstance(decision.model, str)
        assert len(decision.model) > 0
    
    @given(st.text(min_size=1, max_size=500).filter(lambda x: x.strip()))
    @settings(max_examples=100)
    def test_classification_confidence_in_valid_range(self, query: str):
        """
        Property: Confidence is always between 0 and 1.
        """
        decision = classify_query(query)
        assert 0.0 <= decision.confidence <= 1.0
    
    @given(st.text(min_size=1, max_size=500).filter(lambda x: x.strip()))
    @settings(max_examples=100)
    def test_classification_has_rationale(self, query: str):
        """
        Property: Every classification includes a rationale.
        """
        decision = classify_query(query)
        assert isinstance(decision.rationale, str)
        assert len(decision.rationale) > 0


class TestForcedModeOverride:
    """Test forced mode parameter."""
    
    @given(
        st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
        st.sampled_from(list(ResearchMode)),
    )
    @settings(max_examples=50)
    def test_forced_mode_is_respected(self, query: str, forced_mode: ResearchMode):
        """
        Property: When force_mode is specified, that mode is always returned.
        """
        decision = classify_query(query, force_mode=forced_mode)
        assert decision.mode == forced_mode
        assert decision.confidence == 1.0


class TestBudgetConstraint:
    """Test budget constraint application."""
    
    @given(
        st.text(min_size=1, max_size=200).filter(lambda x: x.strip()),
        st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_budget_constraint_respected(self, query: str, max_budget: float):
        """
        Property: Result cost never exceeds specified budget.
        """
        decision = classify_query(query, max_budget=max_budget)
        assert decision.cost.max_cost <= max_budget or decision.mode == ResearchMode.QUICK


class TestCostEstimateProperties:
    """Test CostEstimate dataclass properties."""
    
    @given(
        st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        st.integers(min_value=1, max_value=3600),
        st.integers(min_value=1, max_value=3600),
    )
    @settings(max_examples=100)
    def test_cost_range_format(
        self, min_cost: float, max_cost: float, min_time: int, max_time: int
    ):
        """
        Property: cost_range always produces valid string format.
        """
        # Ensure min <= max
        if min_cost > max_cost:
            min_cost, max_cost = max_cost, min_cost
        if min_time > max_time:
            min_time, max_time = max_time, min_time
        
        estimate = CostEstimate(min_cost, max_cost, min_time, max_time)
        cost_str = estimate.cost_range
        
        assert isinstance(cost_str, str)
        assert cost_str == "FREE" or cost_str.startswith("$")
    
    @given(
        st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        st.integers(min_value=1, max_value=3600),
        st.integers(min_value=1, max_value=3600),
    )
    @settings(max_examples=100)
    def test_time_range_format(
        self, min_cost: float, max_cost: float, min_time: int, max_time: int
    ):
        """
        Property: time_range always produces valid string format.
        """
        if min_cost > max_cost:
            min_cost, max_cost = max_cost, min_cost
        if min_time > max_time:
            min_time, max_time = max_time, min_time
        
        estimate = CostEstimate(min_cost, max_cost, min_time, max_time)
        time_str = estimate.time_range
        
        assert isinstance(time_str, str)
        assert "sec" in time_str or "min" in time_str


class TestConfirmationThreshold:
    """Test confirmation threshold logic."""
    
    @given(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=50)
    def test_confirmation_threshold_consistency(self, threshold: float):
        """
        Property: Confirmation requirement is consistent with threshold.
        """
        for mode in ResearchMode:
            cost = MODE_COSTS[mode]
            decision = ResearchDecision(
                mode=mode,
                model="test",
                cost=cost,
                rationale="test",
                confidence=1.0,
            )
            
            needs_confirm = requires_confirmation(decision, threshold)
            
            if cost.max_cost >= threshold:
                assert needs_confirm
            else:
                assert not needs_confirm


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_query_raises_error(self):
        """Empty query should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            classify_query("")
    
    def test_whitespace_only_raises_error(self):
        """Whitespace-only query should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            classify_query("   \t\n  ")
    
    def test_negative_budget_raises_error(self):
        """Negative max_budget should raise ValueError."""
        with pytest.raises(ValueError, match="max_budget cannot be negative"):
            classify_query("test query", max_budget=-1.0)
    
    @given(st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False))
    @settings(max_examples=20)
    def test_any_negative_budget_raises_error(self, negative_budget: float):
        """
        Property: Any negative budget should raise ValueError.
        """
        with pytest.raises(ValueError, match="max_budget cannot be negative"):
            classify_query("test query", max_budget=negative_budget)
    
    @given(st.text(min_size=1000, max_size=2000).filter(lambda x: x.strip()))
    @settings(max_examples=10)
    def test_very_long_query_handled(self, query: str):
        """
        Property: Very long queries are handled without error.
        """
        decision = classify_query(query)
        assert isinstance(decision.mode, ResearchMode)


class TestModeSpecificBehavior:
    """Test mode-specific classification behavior."""
    
    def test_quick_indicators_favor_quick_mode(self):
        """Queries with quick indicators should favor QUICK mode."""
        quick_queries = [
            "what is Python",
            "define machine learning",
            "quick lookup of API rate limits",
        ]
        for query in quick_queries:
            decision = classify_query(query)
            # Should be QUICK or STANDARD, not deep
            assert decision.mode in (ResearchMode.QUICK, ResearchMode.STANDARD)
    
    def test_deep_indicators_favor_deep_mode(self):
        """Queries with deep indicators should favor deeper modes."""
        deep_queries = [
            "comprehensive analysis of market trends and competitive landscape",
            "thorough investigation of security implications",
            "detailed strategic assessment of long-term implications",
        ]
        for query in deep_queries:
            decision = classify_query(query)
            # Should favor deeper modes
            assert decision.mode in (
                ResearchMode.STANDARD,
                ResearchMode.DEEP_FAST,
                ResearchMode.DEEP_PREMIUM,
            )
