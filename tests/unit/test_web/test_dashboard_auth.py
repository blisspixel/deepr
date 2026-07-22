"""Dashboard HTTP authentication states used by the browser access gate."""

import pytest

from deepr.web import app as web_app


@pytest.fixture
def client(monkeypatch):
    web_app.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if web_app.limiter is not None:
        monkeypatch.setattr(web_app.limiter, "enabled", False)
    return web_app.app.test_client()


def test_health_remains_public_when_dashboard_auth_is_not_configured(client, monkeypatch) -> None:
    monkeypatch.setattr(web_app, "_API_KEY", "")
    monkeypatch.setattr(web_app, "_ALLOW_UNAUTHENTICATED_LOOPBACK", False)

    response = client.get("/api/health")

    assert response.status_code == 200


def test_protected_read_reports_missing_server_auth_configuration(client, monkeypatch) -> None:
    monkeypatch.setattr(web_app, "_API_KEY", "")
    monkeypatch.setattr(web_app, "_ALLOW_UNAUTHENTICATED_LOOPBACK", False)

    response = client.get("/api/cost/limits")

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "Dashboard authentication is not configured",
        "error_code": "AUTH_NOT_CONFIGURED",
    }


def test_protected_read_rejects_wrong_token_and_accepts_shared_secret(client, monkeypatch) -> None:
    monkeypatch.setattr(web_app, "_API_KEY", "dashboard-test-secret")
    monkeypatch.setattr(web_app, "_ALLOW_UNAUTHENTICATED_LOOPBACK", False)

    rejected = client.get("/api/cost/limits", headers={"Authorization": "Bearer wrong-secret"})
    accepted = client.get(
        "/api/cost/limits",
        headers={"Authorization": "Bearer dashboard-test-secret"},
    )

    assert rejected.status_code == 401
    assert rejected.get_json() == {"error": "Unauthorized"}
    assert accepted.status_code == 200


def test_explicit_tokenless_loopback_mode_preserves_local_dashboard_access(client, monkeypatch) -> None:
    monkeypatch.setattr(web_app, "_API_KEY", "")
    monkeypatch.setattr(web_app, "_ALLOW_UNAUTHENTICATED_LOOPBACK", True)

    response = client.get("/api/cost/limits", environ_base={"REMOTE_ADDR": "127.0.0.1"})

    assert response.status_code == 200
