"""Web budget controls may narrow, but never raise, operator authority."""

import json

import pytest

from deepr.core.cost_caps import budget_file_path, read_operator_budget, resolve_spend_caps
from deepr.web import app as web_app


@pytest.fixture
def client(monkeypatch):
    web_app.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if web_app.limiter is not None:
        monkeypatch.setattr(web_app.limiter, "enabled", False)
    monkeypatch.setattr(web_app, "_API_KEY", "budget-test-secret")
    monkeypatch.setattr(web_app, "_ALLOW_UNAUTHENTICATED_LOOPBACK", False)
    return web_app.app.test_client()


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer budget-test-secret"}


def test_connection_probe_is_blocked_before_provider_construction(client, monkeypatch) -> None:
    constructed = False

    class ForbiddenClient:
        def __init__(self, *_args, **_kwargs):
            nonlocal constructed
            constructed = True

    monkeypatch.setenv("OPENAI_API_KEY", "configured-test-key")
    monkeypatch.setattr("openai.OpenAI", ForbiddenClient)

    response = client.post(
        "/api/config/test-connection",
        json={"provider": "openai"},
        headers=_headers(),
    )

    assert response.status_code == 503
    assert response.get_json()["error_code"] == "external_metadata_cost_unverified"
    assert constructed is False


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
        json={"monthly": 4.01},
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
    original_web_search = web_app._config["enable_web_search"]

    response = client.patch(
        "/api/config",
        json={"enable_web_search": False, "monthly_limit": 4.01},
        headers=_headers(),
    )

    assert response.status_code == 400
    assert web_app._config["enable_web_search"] is original_web_search
    assert controller.max_daily_cost == 2.0
    assert controller.max_monthly_cost == 3.0


def test_web_monthly_limit_below_provider_hard_limit_freezes_paid_authority(client, monkeypatch) -> None:
    controller = web_app.cost_controller
    assert controller is not None
    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "2")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "3")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "4")

    response = client.patch(
        "/api/cost/limits",
        json={"monthly": 3.0},
        headers=_headers(),
    )

    assert response.status_code == 200
    assert read_operator_budget().monthly_limit == 3.0
    assert resolve_spend_caps() == {"per_job": 0.0, "daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    assert controller.max_cost_per_job == 0.0
    assert controller.max_daily_cost == 0.0
    assert controller.max_monthly_cost == 0.0


def test_dashboard_rejects_interface_local_per_job_or_daily_limits(client, monkeypatch) -> None:
    monkeypatch.setenv("DEEPR_MAX_COST_PER_JOB", "2")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_DAY", "3")
    monkeypatch.setenv("DEEPR_MAX_COST_PER_MONTH", "4")

    response = client.patch(
        "/api/cost/limits",
        json={"per_job": 1.0, "daily": 2.0},
        headers=_headers(),
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Cost limit update rejected by canonical budget policy",
        "error_code": "cost_limit_update_rejected",
    }
    assert read_operator_budget().monthly_limit == 5.0


def test_cost_limit_write_preserves_operator_freeze_metadata(client) -> None:
    budget_path = budget_file_path()
    document = json.loads(budget_path.read_text(encoding="utf-8"))
    document.update(
        {
            "paid_api_frozen": True,
            "freeze_reason": "operator stop",
            "review_ticket": "cost-17",
        }
    )
    budget_path.write_text(json.dumps(document), encoding="utf-8")

    response = client.patch("/api/cost/limits", json={"monthly": 0.0}, headers=_headers())

    assert response.status_code == 200
    updated = json.loads(budget_path.read_text(encoding="utf-8"))
    assert updated["monthly_limit"] == 0.0
    assert updated["paid_api_frozen"] is True
    assert updated["freeze_reason"] == "operator stop"
    assert updated["review_ticket"] == "cost-17"


def test_dashboard_zero_then_cli_positive_remains_frozen(client) -> None:
    response = client.patch("/api/cost/limits", json={"monthly": 0.0}, headers=_headers())
    assert response.status_code == 200

    budget_path = budget_file_path()
    zeroed = json.loads(budget_path.read_text(encoding="utf-8"))
    assert zeroed["paid_api_frozen"] is True
    assert zeroed["freeze_kind"] == "zero_ceiling"
    assert "paid_api_authorization" not in zeroed

    zeroed["monthly_limit"] = 10.0
    budget_path.write_text(json.dumps(zeroed), encoding="utf-8")

    assert read_operator_budget().frozen is True
    assert resolve_spend_caps()["monthly"] == 0.0
