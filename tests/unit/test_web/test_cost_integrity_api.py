"""Dashboard spend-truth regressions: /api/cost/integrity and summary budget fields.

The dashboard once showed nothing while a 30-job campaign billed $37.79 with
zero surviving artifacts. Orphaned spend and over-budget state must be
first-class API facts the UI can render loudly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deepr.core.cost_caps import budget_file_path
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.observability.cost_ledger import CostLedger
from deepr.web import app as web_app


def test_cost_integrity_flags_orphaned_spend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reports = tmp_path / "reports"
    (reports / "2026-07-25_0900_kept-topic_a7ae5c65").mkdir(parents=True)
    monkeypatch.setattr(web_app, "load_config", lambda: {"results_dir": str(reports)})

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


def test_cost_integrity_fails_closed_on_malformed_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(web_app, "load_config", lambda: {"results_dir": str(reports)})
    ledger = CostLedger()
    ledger.ledger_path.write_text('{"operation":', encoding="utf-8")

    response = web_app.app.test_client().get("/api/cost/integrity")

    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error"}


def test_cost_summary_reports_settled_holds_exposure_and_effective_caps() -> None:
    ledger = CostLedger()
    ledger.record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=1.25,
        model="o4-mini-deep-research",
        idempotency_key="web-exposure-settled",
    )
    ResearchReservationStore().reserve(
        reservation_id="web-exposure-hold",
        job_id="web-exposure-job",
        reserved_cost=0.75,
        max_daily_cost=10.0,
        max_weekly_cost=200.0,
        max_monthly_cost=200.0,
    )

    response = web_app.app.test_client().get("/api/cost/summary")

    assert response.status_code == 200
    summary = response.get_json()["summary"]
    assert summary["settled"]["monthly"] == pytest.approx(1.25)
    assert summary["active_holds"] == pytest.approx(0.75)
    assert summary["exposure"]["monthly"] == pytest.approx(2.0)
    assert summary["monthly_exposure"] == pytest.approx(2.0)
    assert summary["effective_caps"] == {
        "per_job": 1.0,
        "daily": 2.0,
        "weekly": 5.0,
        "monthly": 5.0,
    }
    assert summary["remaining"]["monthly"] == pytest.approx(3.0)
    assert summary["paid_api_frozen"] is False
    assert summary["over_budget"] is False


def test_cost_summary_reads_freeze_and_zero_caps_without_restart() -> None:
    budget_path = budget_file_path()
    document = json.loads(budget_path.read_text(encoding="utf-8"))
    document.update({"paid_api_frozen": True, "freeze_reason": "operator stop"})
    budget_path.write_text(json.dumps(document), encoding="utf-8")

    response = web_app.app.test_client().get("/api/cost/summary")

    assert response.status_code == 200
    summary = response.get_json()["summary"]
    assert summary["paid_api_frozen"] is True
    assert summary["freeze_reason"] == "operator stop"
    assert summary["effective_caps"] == {"per_job": 0.0, "daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    assert summary["daily_limit"] == 0.0
    assert summary["monthly_limit"] == 0.0
    assert summary["effective_monthly_limit"] == 0.0
    assert summary["over_budget"] is False


def test_cost_summary_reports_wallet_drawdown_from_creation_time() -> None:
    from deepr.core.spend_wallet import create_wallet, save_wallet
    from deepr.observability.cost_ledger import current_cost_state_id

    ledger = CostLedger()
    ledger.record_event(
        operation="prior_paid_work",
        provider="openai",
        cost_usd=4.50,
        idempotency_key="web-wallet-prior",
    )
    budget_path = budget_file_path()
    budget_path.write_text(
        json.dumps({"monthly_limit": 50.0, "paid_api_frozen": True, "freeze_reason": "default freeze"}),
        encoding="utf-8",
    )
    save_wallet(
        create_wallet(
            amount_usd=50.0,
            cost_state_id=current_cost_state_id(),
            settled_cost_baseline_usd=4.50,
        )
    )
    ledger.record_event(
        operation="wallet_paid_work",
        provider="openai",
        cost_usd=0.25,
        idempotency_key="web-wallet-spend",
    )

    response = web_app.app.test_client().get("/api/cost/summary")

    assert response.status_code == 200
    summary = response.get_json()["summary"]
    assert summary["paid_api_frozen"] is True
    assert summary["authority_mode"] == "spend_wallet"
    assert summary["effective_caps"] == {"per_job": 0.0, "daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    assert summary["exposure"]["monthly"] == pytest.approx(0.25)
    assert summary["spend_wallet_spent"] == pytest.approx(0.25)
    assert summary["spend_wallet_available"] == pytest.approx(49.75)
    assert summary["spend_wallet_protection"] == "local_only"
    assert summary["provider_hard_boundary_verified"] is False
    assert summary["provider_prepaid_verified"] is False
