"""Attended settlement regression using real holds and an offline dispatch."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import click
import pytest

from deepr.core.cost_caps import read_operator_budget
from deepr.core.costs import CostEstimate
from deepr.experts.cost_safety import CostSafetyManager
from deepr.experts.research_cost_gate import ResearchCostBlocked, reserve_research_cost
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.observability.cost_ledger import CostLedger
from deepr.services import openrouter_attended_research as attended


@pytest.mark.parametrize("charge", [0.008, 0.02])
def test_attended_preserves_actual_charge_and_freezes_overrun(monkeypatch, charge):
    manager = CostSafetyManager()
    estimate = CostEstimate(
        min_cost=0.005,
        max_cost=0.01,
        expected_cost=0.008,
        model="test-model",
        reasoning="synthetic reservation",
    )

    # The existing fixture supplies synthetic OpenAI authority. Use that real
    # durable hold while replacing only OpenRouter admission and dispatch.
    def reserve(job_id, **kwargs):
        return reserve_research_cost(
            job_id=job_id,
            provider="openai",
            model="test-model",
            estimate=estimate,
            max_cost_per_job=0.01,
            max_daily_cost=1.0,
            max_monthly_cost=5.0,
            manager=manager,
        )

    parent = SimpleNamespace(close=Mock())
    publish = Mock()
    monkeypatch.setattr(attended, "paid_api_provider_scope", lambda _: nullcontext())
    monkeypatch.setattr(attended, "bounded_research_cost_estimate", lambda **_: estimate)
    monkeypatch.setattr(attended, "_confirm_openrouter_spend", lambda **_: None)
    monkeypatch.setattr(attended, "open_parent_budget_transaction", lambda **_: parent)
    monkeypatch.setattr(attended, "resolve_spend_caps", lambda **_: {"daily": 1, "weekly": 5, "monthly": 5})
    monkeypatch.setattr(attended, "reserve_research_cost", reserve)
    monkeypatch.setattr(attended, "require_unproxied_paid_transport", lambda: None)
    monkeypatch.setattr(attended, "load_openrouter_api_key", lambda: "offline-fixture")
    monkeypatch.setattr(
        attended,
        "_dispatch_openrouter_completion",
        lambda **_: SimpleNamespace(
            cost_usd=charge,
            completion_tokens=4,
            generation_id="offline-generation",
        ),
    )
    monkeypatch.setattr(attended, "_print_and_store", publish)
    arguments = dict(
        query="bounded question",
        model="qwen/qwen3.8-flash",
        limit=0.01,
        yes=False,
        no_web=True,
        no_code=True,
        upload=(),
        scrape=None,
    )
    if charge > 0.01:
        with pytest.raises(click.ClickException, match="Paid API frozen"):
            attended.run_attended_openrouter_research(**arguments)
        assert read_operator_budget().freeze_kind == "cost_ceiling_divergence"
        publish.assert_not_called()
        parent.close.assert_not_called()
        with pytest.raises(ResearchCostBlocked):
            reserve("after-overrun")
    else:
        attended.run_attended_openrouter_research(**arguments)
        assert read_operator_budget().frozen is False
        publish.assert_called_once()
        parent.close.assert_called_once()

    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(charge)
    assert events[0].request_id == "offline-generation"
    assert events[0].metadata["actual_cost_reported"] is True
    assert events[0].metadata.get("cost_ceiling_diverged", False) is (charge > 0.01)
    assert ResearchReservationStore().state(events[0].metadata["cost_reservation_id"]) == "settled"
