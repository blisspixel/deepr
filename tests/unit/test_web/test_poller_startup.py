"""Regression tests for the web background poller startup hook."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("flask")

import deepr.web.app as web_app
from deepr.web.research_cost_api import WebResearchCostCoordinator


@pytest.fixture
def client(monkeypatch):
    web_app.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if web_app.limiter is not None:
        monkeypatch.setattr(web_app.limiter, "enabled", False)
    return web_app.app.test_client()


def test_web_import_does_not_construct_metered_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(web_app, "provider", None)

    with pytest.raises(RuntimeError, match="OpenAI is not configured"):
        web_app._default_openai_provider()


def test_testing_mode_does_not_start_background_poller(monkeypatch):
    monkeypatch.setitem(web_app.app.config, "TESTING", True)
    monkeypatch.setattr(web_app, "_poller_started", False)

    started = []

    class DummyThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            started.append(self.kwargs)

    monkeypatch.setattr(web_app.threading, "Thread", DummyThread)

    web_app._start_poller()

    assert web_app._poller_started is False
    assert started == []


def test_paid_submit_fails_closed_when_cost_controls_are_unavailable(client, monkeypatch):
    provider_factory = MagicMock()
    monkeypatch.setattr(web_app, "research_costs", WebResearchCostCoordinator(None, None))
    monkeypatch.setattr(web_app, "_default_openai_provider", provider_factory)

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 503
    assert response.get_json()["error"] == "Cost controls unavailable; submission denied"
    provider_factory.assert_not_called()


def test_paid_submit_fails_closed_when_cost_estimation_raises(client, monkeypatch):
    provider_factory = MagicMock()
    estimator = MagicMock()
    estimator.estimate_cost.side_effect = RuntimeError("estimator unavailable")
    monkeypatch.setattr(web_app, "research_costs", WebResearchCostCoordinator(MagicMock(), estimator))
    monkeypatch.setattr(web_app, "_default_openai_provider", provider_factory)

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 503
    assert response.get_json()["error"] == "Cost estimation unavailable; submission denied"
    provider_factory.assert_not_called()


def test_paid_submit_fails_closed_when_cost_limit_check_raises(client, monkeypatch):
    provider_factory = MagicMock()
    estimate = MagicMock(min_cost=0.1, max_cost=0.3, expected_cost=0.2)
    estimator = MagicMock()
    estimator.estimate_cost.return_value = estimate
    controller = MagicMock()
    controller.check_cost_limit.side_effect = RuntimeError("ledger unavailable")
    monkeypatch.setattr(web_app, "research_costs", WebResearchCostCoordinator(controller, estimator))
    monkeypatch.setattr(web_app, "_default_openai_provider", provider_factory)

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 503
    assert response.get_json()["error"] == "Cost limit check unavailable; submission denied"
    provider_factory.assert_not_called()


def test_paid_submit_does_not_expose_cost_reservation_exception(client, monkeypatch):
    from deepr.experts.research_cost_gate import ResearchCostBlocked

    provider_factory = MagicMock()
    estimate = MagicMock(min_cost=0.1, max_cost=0.3, expected_cost=0.2)
    estimator = MagicMock()
    estimator.estimate_cost.return_value = estimate
    controller = MagicMock(max_cost_per_job=1.0, max_daily_cost=5.0, max_monthly_cost=20.0)
    controller.check_cost_limit.return_value = (True, None)
    coordinator = WebResearchCostCoordinator(controller, estimator)
    monkeypatch.setattr(web_app, "research_costs", coordinator)
    monkeypatch.setattr(web_app, "_default_openai_provider", provider_factory)
    monkeypatch.setattr(
        "deepr.web.research_cost_api.reserve_research_cost",
        MagicMock(side_effect=ResearchCostBlocked("secret ledger traceback")),
    )

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 429
    assert response.get_json()["error"] == "Research cost limit exceeded"
    assert b"secret ledger traceback" not in response.data
    provider_factory.assert_not_called()


def test_paid_submit_does_not_expose_provider_configuration_exception(client, monkeypatch):
    reservation = MagicMock()
    coordinator = MagicMock()
    coordinator.reserve.return_value = (
        {"min_cost": 0.1, "max_cost": 0.3, "expected_cost": 0.2},
        reservation,
        None,
    )
    provider_factory = MagicMock(side_effect=RuntimeError("secret provider traceback"))
    monkeypatch.setattr(web_app, "research_costs", coordinator)
    monkeypatch.setattr(web_app, "_default_openai_provider", provider_factory)

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 503
    assert response.get_json() == {"error": "Research provider is unavailable"}
    assert b"secret provider traceback" not in response.data
    coordinator.refund.assert_called_once_with(reservation)


def test_paid_submit_preserves_explicit_no_key_error(client, monkeypatch):
    reservation = MagicMock()
    coordinator = MagicMock()
    coordinator.reserve.return_value = (
        {"min_cost": 0.1, "max_cost": 0.3, "expected_cost": 0.2},
        reservation,
        None,
    )
    monkeypatch.setattr(web_app, "research_costs", coordinator)
    monkeypatch.setattr(web_app, "provider", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.post("/api/jobs", json={"prompt": "Research power-grid constraints."})

    assert response.status_code == 503
    assert response.get_json() == {"error": web_app.research_cost_api.OPENAI_NOT_CONFIGURED}
    coordinator.refund.assert_called_once_with(reservation)
