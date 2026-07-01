"""Tests for route-gaps value-of-spend gating."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from deepr.experts.gap_router import GapRoute
from deepr.experts.gap_spend_gate import build_gap_fill_spend_decider, gap_route_benefit_factors
from deepr.experts.spend_decisions import load_spend_decisions


def _route(topic: str, *, priority: int = 3, cost: float = 0.5, ev_cost_ratio: float = 0.0) -> GapRoute:
    return GapRoute(
        topic=topic,
        instrument="research",
        available=True,
        estimated_cost=cost,
        rationale="test",
        suggestion="",
        priority=priority,
        ev_cost_ratio=ev_cost_ratio,
    )


def test_gap_route_benefit_factors_use_numeric_route_metadata_not_topic_meaning():
    left = _route("API pricing changed yesterday", priority=4, cost=0.25, ev_cost_ratio=2.0)
    right = _route("Completely different words", priority=4, cost=0.25, ev_cost_ratio=2.0)

    assert gap_route_benefit_factors(left) == gap_route_benefit_factors(right)
    assert gap_route_benefit_factors(left) == {
        "gap_closure": 1.0,
        "value": 0.5,
        "urgency": 0.8,
        "volatility": 0.5,
    }


def test_gap_fill_spend_decider_records_and_denies_low_value_conserve(tmp_path):
    now = datetime(2026, 7, 1, tzinfo=UTC)
    path = tmp_path / "spend_decisions.jsonl"
    manager = SimpleNamespace(monthly_cost=8.0, max_monthly=10.0)
    route = _route("Low priority follow-up", priority=1, cost=1.0, ev_cost_ratio=0.05)
    decider = build_gap_fill_spend_decider(
        expert_name="Budget Expert",
        capacity_source="api_metered",
        manager=manager,
        decision_log_path=path,
        now=now,
    )

    decision = decider(route, 1.0)
    loaded = load_spend_decisions(path)

    assert decision.allowed is False
    assert decision.tier.value == "conserve"
    assert loaded[0]["expert_name"] == "Budget Expert"
    assert loaded[0]["operation"] == "expert_gap_fill"
    assert loaded[0]["topic"] == "Low priority follow-up"
    assert loaded[0]["decision"]["allowed"] is False
