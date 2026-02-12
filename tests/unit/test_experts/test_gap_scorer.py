"""Unit tests for experts.gap_scorer scoring functions."""

import pytest

from deepr.core.contracts import Gap
from deepr.experts.gap_scorer import rank_gaps, score_gap


class TestScoreGap:
    """Test score_gap function."""

    def test_medium_velocity_cost(self):
        gap = Gap.create(topic="test", priority=3, times_asked=0)
        scored = score_gap(gap, domain_velocity="medium")
        assert scored.estimated_cost == 1.00

    def test_fast_velocity_cost(self):
        gap = Gap.create(topic="test", priority=3)
        scored = score_gap(gap, domain_velocity="fast")
        assert scored.estimated_cost == 0.25

    def test_slow_velocity_cost(self):
        gap = Gap.create(topic="test", priority=3)
        scored = score_gap(gap, domain_velocity="slow")
        assert scored.estimated_cost == 2.00

    def test_unknown_velocity_defaults_to_medium(self):
        gap = Gap.create(topic="test", priority=3)
        scored = score_gap(gap, domain_velocity="unknown")
        assert scored.estimated_cost == 1.00

    def test_expected_value_base(self):
        gap = Gap.create(topic="test", priority=5, times_asked=0)
        scored = score_gap(gap)
        assert scored.expected_value == 1.0  # 5/5 = 1.0

    def test_expected_value_with_frequency_boost(self):
        gap = Gap.create(topic="test", priority=3, times_asked=5)
        scored = score_gap(gap)
        # base = 3/5 = 0.6, boost = min(5/10, 0.3) = 0.3, total = 0.9
        assert abs(scored.expected_value - 0.9) < 0.001

    def test_expected_value_capped_at_one(self):
        gap = Gap.create(topic="test", priority=5, times_asked=100)
        scored = score_gap(gap)
        assert scored.expected_value == 1.0

    def test_ev_cost_ratio_calculation(self):
        gap = Gap.create(topic="test", priority=5, times_asked=0)
        scored = score_gap(gap, domain_velocity="medium")
        # EV = 1.0, cost = 1.0, ratio = 1.0
        assert abs(scored.ev_cost_ratio - 1.0) < 0.001

    def test_zero_cost_floor(self):
        """Ensure no division by zero even with zero estimated cost."""
        gap = Gap.create(topic="test", priority=3)
        gap.estimated_cost = 0.0
        scored = score_gap(gap)
        # Cost floor is 0.001, not zero
        assert scored.ev_cost_ratio > 0

    def test_mutates_gap_in_place(self):
        gap = Gap.create(topic="test", priority=3)
        result = score_gap(gap)
        assert result is gap
        assert gap.expected_value > 0


class TestRankGaps:
    """Test rank_gaps function."""

    def test_sorts_by_ev_cost_ratio_desc(self):
        gaps = [
            Gap.create("low", ev_cost_ratio=0.5),
            Gap.create("high", ev_cost_ratio=2.0),
            Gap.create("mid", ev_cost_ratio=1.0),
        ]
        ranked = rank_gaps(gaps)
        assert ranked[0].topic == "high"
        assert ranked[1].topic == "mid"
        assert ranked[2].topic == "low"

    def test_top_n_truncation(self):
        gaps = [Gap.create(f"g{i}", ev_cost_ratio=float(i)) for i in range(10)]
        ranked = rank_gaps(gaps, top_n=3)
        assert len(ranked) == 3

    def test_top_n_greater_than_list(self):
        gaps = [Gap.create("only", ev_cost_ratio=1.0)]
        ranked = rank_gaps(gaps, top_n=5)
        assert len(ranked) == 1

    def test_empty_list(self):
        ranked = rank_gaps([], top_n=5)
        assert ranked == []
