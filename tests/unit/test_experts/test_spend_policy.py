"""Tests for budget degradation tiers and the value-of-spend gate."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.spend_policy import (
    METERED_OFF_TIERS,
    BudgetTier,
    SpendPolicyConfig,
    budget_tier,
    describe_tier,
    evaluate_spend,
    tier_from_manager,
)


class TestBudgetTier:
    @pytest.mark.parametrize(
        ("spent", "expected"),
        [
            (0.0, BudgetTier.NORMAL),
            (6.9, BudgetTier.NORMAL),  # 69%
            (7.0, BudgetTier.CONSERVE),  # 70% boundary
            (8.9, BudgetTier.CONSERVE),
            (9.0, BudgetTier.LOCAL_ONLY),  # 90% boundary
            (9.9, BudgetTier.LOCAL_ONLY),
            (10.0, BudgetTier.PAUSE_METERED),  # 100% boundary
            (12.0, BudgetTier.PAUSE_METERED),  # over cap
        ],
    )
    def test_boundaries_on_a_ten_dollar_cap(self, spent, expected):
        assert budget_tier(spent, 10.0) == expected

    def test_no_cap_is_normal(self):
        assert budget_tier(100.0, 0.0) == BudgetTier.NORMAL
        assert budget_tier(100.0, -1.0) == BudgetTier.NORMAL

    def test_negative_spend_is_normal(self):
        assert budget_tier(-5.0, 10.0) == BudgetTier.NORMAL


class TestHardOffTiers:
    def test_local_only_denies_metered(self):
        d = evaluate_spend(spent=9.5, cap=10.0, est_cost=0.01, gap_closure=1, value=1, urgency=1, volatility=1)
        assert d.allowed is False
        assert d.tier == BudgetTier.LOCAL_ONLY
        assert d.pausable is True  # resumable, never a hard failure

    def test_pause_metered_denies_even_zero_cost_high_value(self):
        d = evaluate_spend(spent=10.0, cap=10.0, est_cost=0.0, gap_closure=1, value=1, urgency=1, volatility=1)
        assert d.allowed is False
        assert d.tier == BudgetTier.PAUSE_METERED
        assert d.pausable is True

    def test_off_tiers_set_is_consistent(self):
        assert BudgetTier.LOCAL_ONLY in METERED_OFF_TIERS
        assert BudgetTier.PAUSE_METERED in METERED_OFF_TIERS
        assert BudgetTier.NORMAL not in METERED_OFF_TIERS


class TestValueGate:
    def test_default_value_op_clears_normal_but_defers_in_conserve(self):
        normal = evaluate_spend(spent=0.0, cap=10.0, est_cost=0.50)  # NORMAL, default 0.5 factors
        conserve = evaluate_spend(spent=8.0, cap=10.0, est_cost=0.50)  # CONSERVE
        assert normal.allowed is True
        assert conserve.allowed is False
        assert conserve.pausable is True

    def test_high_value_clears_conserve(self):
        d = evaluate_spend(spent=8.0, cap=10.0, est_cost=0.50, gap_closure=0.9, value=0.9, urgency=0.9, volatility=0.9)
        assert d.tier == BudgetTier.CONSERVE
        assert d.allowed is True

    def test_higher_cost_is_harder_to_clear(self):
        cheap = evaluate_spend(spent=0.0, cap=10.0, est_cost=0.10)
        dear = evaluate_spend(spent=0.0, cap=10.0, est_cost=5.0)
        assert cheap.hurdle < dear.hurdle
        assert cheap.allowed and not dear.allowed

    def test_conserve_hurdle_exceeds_normal_hurdle(self):
        normal = evaluate_spend(spent=0.0, cap=10.0, est_cost=0.50)
        conserve = evaluate_spend(spent=8.0, cap=10.0, est_cost=0.50)
        assert conserve.hurdle > normal.hurdle  # rises as the pool drains

    def test_free_op_always_clears(self):
        d = evaluate_spend(spent=0.0, cap=10.0, est_cost=0.0, gap_closure=0.1, value=0.1, urgency=0.1, volatility=0.1)
        assert d.allowed is True  # no money at risk

    def test_factors_are_clamped(self):
        # Out-of-range factors must not blow up the product or exceed [0,1].
        over = evaluate_spend(spent=0.0, cap=10.0, est_cost=0.50, gap_closure=5, value=5, urgency=5, volatility=5)
        under = evaluate_spend(spent=0.0, cap=10.0, est_cost=0.50, gap_closure=-1, value=1, urgency=1, volatility=1)
        assert over.benefit == 1.0  # all clamped to 1 -> product 1
        assert under.benefit == 0.0  # one clamped to 0 -> product 0

    def test_benefit_is_monotonic_in_factors(self):
        low = evaluate_spend(
            spent=8.0, cap=10.0, est_cost=0.50, gap_closure=0.5, value=0.5, urgency=0.5, volatility=0.5
        )
        high = evaluate_spend(
            spent=8.0, cap=10.0, est_cost=0.50, gap_closure=0.9, value=0.9, urgency=0.9, volatility=0.9
        )
        assert high.benefit > low.benefit


class TestDecisionShapeAndSafety:
    def test_to_dict_is_complete(self):
        d = evaluate_spend(spent=0.0, cap=10.0, est_cost=0.50)
        payload = d.to_dict()
        assert set(payload) == {"allowed", "tier", "reason", "benefit", "hurdle", "pausable"}
        assert payload["tier"] == "normal"

    def test_never_raises_on_garbage(self):
        # NaN-free garbage: zero cap, huge spend, weird costs - must not raise.
        for spent, cap, cost in [(0, 0, 0), (1e9, 1.0, 1e9), (-1, -1, -1)]:
            d = evaluate_spend(spent=spent, cap=cap, est_cost=cost)
            assert isinstance(d.allowed, bool)

    def test_config_is_tunable(self):
        # A stricter normal hurdle defers what the default would allow.
        strict = SpendPolicyConfig(normal_multiple=1.0)
        d = evaluate_spend(spent=0.0, cap=10.0, est_cost=0.50, config=strict)
        assert d.allowed is False


class TestManagerAdapters:
    def _manager(self, spent, cap):
        return SimpleNamespace(monthly_cost=spent, max_monthly=cap)

    def test_tier_from_manager_reads_monthly_state(self):
        assert tier_from_manager(self._manager(8.0, 10.0)) == BudgetTier.CONSERVE

    def test_describe_tier_snapshot(self):
        snap = describe_tier(self._manager(9.5, 10.0))
        assert snap["tier"] == "local_only"
        assert snap["drain_percent"] == 95.0
        assert snap["metered_off"] is True
