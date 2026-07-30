"""Fail-closed regressions for web cost history and estimate decisions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.observability.cost_ledger import CostLedger
from deepr.web import app as web_app


def _estimator(*, minimum: float = 0.1, maximum: float = 0.2, expected: float = 0.15):
    return SimpleNamespace(
        estimate_cost=lambda _prompt, _model: SimpleNamespace(
            min_cost=minimum,
            max_cost=maximum,
            expected_cost=expected,
        )
    )


def test_cost_history_reads_non_queue_spend_from_strict_canonical_ledger() -> None:
    CostLedger().record_event(
        operation="expert_chat",
        provider="openai",
        cost_usd=0.125,
        model="gpt-5.2",
        tokens_input=11,
        tokens_output=7,
        source="experts.chat",
        idempotency_key="web-history-expert-chat",
    )

    response = web_app.app.test_client().get("/api/cost/history?time_range=30d")

    assert response.status_code == 200
    history = response.get_json()["history"]
    assert history == [
        {
            "id": "web-history-expert-chat",
            "prompt": "expert_chat",
            "operation": "expert_chat",
            "provider": "openai",
            "source": "experts.chat",
            "model": "gpt-5.2",
            "cost": 0.125,
            "tokens": 18,
            "completed_at": history[0]["completed_at"],
        }
    ]


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/cost/trends?days=30",
        "/api/cost/breakdown?time_range=30d",
        "/api/cost/history?time_range=30d",
    ],
)
def test_secondary_cost_views_fail_closed_on_malformed_ledger(endpoint: str) -> None:
    ledger = CostLedger()
    ledger.ledger_path.write_text('{"operation":', encoding="utf-8")

    response = web_app.app.test_client().get(endpoint)

    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error"}


def test_cost_estimate_counts_atomic_active_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "cost_estimator", _estimator())
    CostLedger().record_event(
        operation="research_completion",
        provider="openai",
        cost_usd=1.5,
        idempotency_key="web-estimate-daily-settled",
    )
    ResearchReservationStore().reserve(
        reservation_id="web-estimate-hold",
        job_id="web-estimate-job",
        reserved_cost=0.4,
        max_daily_cost=2.0,
        max_weekly_cost=5.0,
        max_monthly_cost=5.0,
    )

    response = web_app.app.test_client().post(
        "/api/cost/estimate",
        json={"prompt": "Bound this research before dispatch", "model": "o4-mini-deep-research"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["money_state"] == "known"
    assert payload["allowed"] is False
    assert "daily limit" in payload["reason"]
    assert payload["active_holds"] == pytest.approx(0.4)
    assert payload["exposure"]["daily"] == pytest.approx(1.9)


def test_cost_estimate_fails_closed_when_atomic_exposure_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web_app, "cost_estimator", _estimator())

    def fail_snapshot(self):
        raise RuntimeError("broken canonical state")

    monkeypatch.setattr(ResearchReservationStore, "exposure_snapshot", fail_snapshot)

    response = web_app.app.test_client().post(
        "/api/cost/estimate",
        json={"prompt": "Do not guess about money", "model": "o4-mini-deep-research"},
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["allowed"] is False
    assert payload["money_state"] == "unknown"
    assert "paid API dispatch is blocked" in payload["reason"]


def test_cost_estimate_fails_closed_when_estimation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_estimate(_prompt, _model):
        raise RuntimeError("estimator unavailable")

    monkeypatch.setattr(web_app, "cost_estimator", SimpleNamespace(estimate_cost=fail_estimate))

    response = web_app.app.test_client().post(
        "/api/cost/estimate",
        json={"prompt": "Do not use a fallback guess", "model": "o4-mini-deep-research"},
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["allowed"] is False
    assert payload["money_state"] == "unknown"
    assert "estimate is unavailable" in payload["reason"]


@pytest.mark.parametrize(
    ("minimum", "maximum", "expected"),
    [
        (float("nan"), 0.2, 0.15),
        (0.2, 0.1, 0.15),
        (0.1, 0.2, 0.3),
    ],
)
def test_cost_estimate_fails_closed_on_invalid_estimate_bounds(
    monkeypatch: pytest.MonkeyPatch,
    minimum: float,
    maximum: float,
    expected: float,
) -> None:
    monkeypatch.setattr(
        web_app,
        "cost_estimator",
        _estimator(minimum=minimum, maximum=maximum, expected=expected),
    )

    response = web_app.app.test_client().post(
        "/api/cost/estimate",
        json={"prompt": "Reject untrustworthy estimate bounds", "model": "o4-mini-deep-research"},
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["allowed"] is False
    assert payload["money_state"] == "unknown"
