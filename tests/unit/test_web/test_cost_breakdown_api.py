"""Canonical-ledger regressions for the web cost breakdown."""

from __future__ import annotations

import pytest

from deepr.observability.cost_ledger import CostLedger
from deepr.web import app as web_app


def test_cost_breakdown_reads_model_events_from_canonical_ledger() -> None:
    ledger = CostLedger()
    ledger.record_event(
        operation="expert_chat",
        provider="openai",
        cost_usd=0.25,
        model="gpt-5.2",
        idempotency_key="cost-breakdown-model",
    )
    ledger.record_event(
        operation="legacy_operation",
        provider="openai",
        cost_usd=0.10,
        model="",
        idempotency_key="cost-breakdown-unknown",
    )

    response = web_app.app.test_client().get("/api/cost/breakdown?time_range=30d")

    assert response.status_code == 200
    breakdown = {item["model"]: item for item in response.get_json()["breakdown"]}
    assert breakdown["gpt-5.2"]["cost"] == 0.25
    assert breakdown["gpt-5.2"]["count"] == 1
    assert breakdown["unknown"]["cost"] == 0.10
    assert sum(item["cost"] for item in breakdown.values()) == pytest.approx(0.35)


def test_cost_breakdown_uses_reconciled_attribution_without_double_counting() -> None:
    task_id = "research_browser-chat-turn-55b09a61d7a54739837586f76d888e3d"
    target_key = "job:browser-chat-turn-55b09a61d7a54739837586f76d888e3d:completion"
    ledger = CostLedger()
    ledger.record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=0.20,
        model="qwen2.5-coder:32b",
        tokens_input=17,
        task_id=task_id,
        session_id=task_id,
        idempotency_key=target_key,
    )
    ledger.record_event(
        operation="cost_accounting_reconciliation",
        provider="openai",
        cost_usd=0.0,
        model="gpt-5.2",
        task_id=task_id,
        session_id=task_id,
        idempotency_key="reconcile:browser-chat-turn-55b09a61d7a54739837586f76d888e3d:attribution-v1",
        metadata={
            "supersedes_idempotency_key": target_key,
            "correction_type": "attribution_metadata",
            "observed_outcome": "http_429_no_usage_response",
            "conservative_ceiling_charge_usd": 0.20,
            "actual_cost_reported": False,
            "settlement_basis": "conservative_unaccounted_ceiling",
            "original_model_attribution": "qwen2.5-coder:32b",
            "routed_model_attribution": "gpt-5.2",
            "total_adjustment_usd": 0.0,
        },
    )

    response = web_app.app.test_client().get("/api/cost/breakdown?time_range=30d")

    assert response.status_code == 200
    breakdown = {item["model"]: item for item in response.get_json()["breakdown"]}
    assert "qwen2.5-coder:32b" not in breakdown
    assert breakdown["gpt-5.2"] == {
        "model": "gpt-5.2",
        "cost": 0.2,
        "count": 1,
        "tokens": 17,
        "avg_cost": 0.2,
    }
    assert sum(item["cost"] for item in breakdown.values()) == pytest.approx(0.2)
