"""Web budget controls may narrow, but never raise, operator authority."""

import pytest

from deepr.web import app as web_app


@pytest.fixture
def client(monkeypatch):
    web_app.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if web_app.limiter is not None:
        monkeypatch.setattr(web_app.limiter, "enabled", False)
    monkeypatch.setattr(web_app, "_API_KEY", "budget-test-secret")
    monkeypatch.setattr(web_app, "_ALLOW_UNAUTHENTICATED_LOOPBACK", False)
    monkeypatch.setattr(web_app, "_save_limits", lambda *_args: None)
    return web_app.app.test_client()


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer budget-test-secret"}


def test_cost_endpoint_cannot_raise_any_authoritative_limit(client, monkeypatch) -> None:
    controller = web_app.cost_controller
    assert controller is not None
    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "2")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "3")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "4")
    original = (
        controller.max_cost_per_job,
        controller.max_daily_cost,
        controller.max_monthly_cost,
    )

    response = client.patch(
        "/api/cost/limits",
        json={"per_job": 2.01, "daily": 3.01, "monthly": 4.01},
        headers=_headers(),
    )

    assert response.status_code == 400
    assert (
        controller.max_cost_per_job,
        controller.max_daily_cost,
        controller.max_monthly_cost,
    ) == original


def test_config_endpoint_validates_atomically_before_mutation(client, monkeypatch) -> None:
    controller = web_app.cost_controller
    assert controller is not None
    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "3")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "4")
    monkeypatch.setattr(controller, "max_daily_cost", 2.0)
    monkeypatch.setattr(controller, "max_monthly_cost", 3.0)

    response = client.patch(
        "/api/config",
        json={"daily_limit": 1.0, "monthly_limit": 4.01},
        headers=_headers(),
    )

    assert response.status_code == 400
    assert controller.max_daily_cost == 2.0
    assert controller.max_monthly_cost == 3.0


def test_web_limits_may_narrow_authority(client, monkeypatch) -> None:
    controller = web_app.cost_controller
    assert controller is not None
    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "2")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "3")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "4")

    response = client.patch(
        "/api/cost/limits",
        json={"per_job": 1.0, "daily": 2.0, "monthly": 3.0},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert controller.max_cost_per_job == 1.0
    assert controller.max_daily_cost == 2.0
    assert controller.max_monthly_cost == 3.0
