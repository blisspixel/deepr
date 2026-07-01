"""Tests for expert-sync value-of-spend gating."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from deepr.experts.spend_decisions import load_spend_decisions, record_spend_decision
from deepr.experts.sync import Subscription
from deepr.experts.sync_spend_gate import build_sync_spend_decider, sync_subscription_benefit_factors


def test_sync_benefit_factors_use_schedule_metadata_not_topic_meaning():
    now = datetime(2026, 6, 30, tzinfo=UTC)
    first = Subscription(topic="Any topic", cadence_days=7)
    overdue = Subscription(topic="Different words", cadence_days=7, last_synced=now - timedelta(days=14))

    first_factors = sync_subscription_benefit_factors(first, now=now)
    overdue_factors = sync_subscription_benefit_factors(overdue, now=now)

    assert first_factors["gap_closure"] == 1.0
    assert overdue_factors["gap_closure"] == 0.6
    assert overdue_factors["urgency"] == 1.0
    assert first_factors["value"] == overdue_factors["value"] == 0.5


def test_spend_decision_log_appends_jsonl(tmp_path):
    path = tmp_path / "spend_decisions.jsonl"
    record = record_spend_decision(
        expert_name="Budget Expert",
        operation="expert_sync",
        topic="Topic X",
        capacity_source="api_metered",
        estimated_cost=0.5,
        factors={"gap_closure": 0.6, "value": 0.5, "urgency": 0.5, "volatility": 0.7},
        decision={"allowed": False, "tier": "conserve", "reason": "defer", "benefit": 0.105, "hurdle": 0.2},
        path=path,
        now=datetime(2026, 6, 30, tzinfo=UTC),
    )

    loaded = load_spend_decisions(path)
    assert loaded == [record]
    assert loaded[0]["schema_version"] == "deepr-spend-decision-v1"
    assert loaded[0]["kind"] == "deepr.expert.spend_decision"
    assert loaded[0]["decision"]["allowed"] is False


def test_sync_spend_decider_records_and_denies_low_value_conserve(tmp_path):
    now = datetime(2026, 6, 30, tzinfo=UTC)
    path = tmp_path / "decisions.jsonl"
    manager = SimpleNamespace(monthly_cost=8.0, max_monthly=10.0)
    sub = Subscription(topic="Routine weekly delta", cadence_days=7, budget=0.5, last_synced=now - timedelta(days=7))
    decider = build_sync_spend_decider(
        expert_name="Budget Expert",
        capacity_source="api_metered",
        manager=manager,
        decision_log_path=path,
        now=now,
    )

    decision = decider(sub, 0.5)
    loaded = load_spend_decisions(path)

    assert decision.allowed is False
    assert decision.tier.value == "conserve"
    assert loaded[0]["expert_name"] == "Budget Expert"
    assert loaded[0]["topic"] == "Routine weekly delta"
    assert loaded[0]["decision"]["allowed"] is False
