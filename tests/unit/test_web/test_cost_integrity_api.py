"""Dashboard spend-truth regressions: /api/cost/integrity and summary budget fields.

The dashboard once showed nothing while a 30-job campaign billed $37.79 with
zero surviving artifacts. Orphaned spend and over-budget state must be
first-class API facts the UI can render loudly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from deepr.observability.cost_ledger import CostLedger
from deepr.web import app as web_app


def test_cost_integrity_flags_orphaned_spend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reports = tmp_path / "reports"
    (reports / "2026-07-25_0900_kept-topic_a7ae5c65").mkdir(parents=True)
    monkeypatch.setattr(web_app, "_REPORTS_ROOT", reports)

    ledger = CostLedger()
    ledger.record_event(
        operation="research_completion",
        provider="xai",
        cost_usd=0.03,
        model="grok-4-5",
        task_id="research_research-a7ae5c653d8c",
        idempotency_key="integrity-matched",
    )
    ledger.record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=1.85,
        model="o4-mini-deep-research",
        task_id="research_research-deadbeef1234",
        idempotency_key="integrity-orphaned",
    )

    response = web_app.app.test_client().get("/api/cost/integrity")

    assert response.status_code == 200
    integrity = response.get_json()["integrity"]
    assert integrity["matched_spend"] == 0.03
    assert integrity["orphaned_spend"] == 1.85
    assert integrity["orphaned_events"] == 1


def test_cost_summary_reports_over_budget_against_gate_limit() -> None:
    # The approval gate's budget.json limit governs even when the env-cap
    # controller limit is higher; the summary must flag the breach.
    with patch(
        "deepr.cli.commands.budget.load_budget_config",
        return_value={"monthly_limit": 10.0, "monthly_spending": 0.0},
    ):
        response = web_app.app.test_client().get("/api/cost/summary")

    assert response.status_code == 200
    summary = response.get_json()["summary"]
    assert summary["budget_monthly_limit"] == 10.0
    assert summary["effective_monthly_limit"] <= 10.0
    assert summary["over_budget"] == (summary["monthly"] > summary["effective_monthly_limit"])
