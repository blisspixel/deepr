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


def test_conversation_routes_reject_windows_device_session_ids(client, monkeypatch) -> None:
    monkeypatch.setattr(web_app, "_check_auth", lambda: None)
    monkeypatch.setattr(web_app, "_decode_expert_name", lambda name: ("fixture", None))

    loaded = client.get("/api/experts/fixture/conversations/CON")
    deleted = client.delete("/api/experts/fixture/conversations/NUL")

    assert loaded.status_code == 400
    assert deleted.status_code == 400


def test_portraits_stay_public_when_dashboard_auth_is_not_configured(client, monkeypatch, tmp_path) -> None:
    portraits = tmp_path / "portraits"
    portraits.mkdir()
    (portraits / "fixture-expert.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(web_app, "_API_KEY", "")
    monkeypatch.setattr(web_app, "_ALLOW_UNAUTHENTICATED_LOOPBACK", False)
    monkeypatch.setattr(
        web_app, "runtime_data_path", lambda name: portraits if name == "portraits" else tmp_path / name
    )

    response = client.get("/portraits/fixture-expert.png")

    assert response.status_code == 200


def test_portraits_require_dashboard_secret_when_configured(client, monkeypatch, tmp_path) -> None:
    portraits = tmp_path / "portraits"
    portraits.mkdir()
    (portraits / "fixture-expert.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(web_app, "_API_KEY", "dashboard-test-secret")
    monkeypatch.setattr(web_app, "_ALLOW_UNAUTHENTICATED_LOOPBACK", False)
    monkeypatch.setattr(
        web_app, "runtime_data_path", lambda name: portraits if name == "portraits" else tmp_path / name
    )

    rejected = client.get("/portraits/fixture-expert.png")
    accepted = client.get(
        "/portraits/fixture-expert.png",
        headers={"Authorization": "Bearer dashboard-test-secret"},
    )
    cookied = client.get("/portraits/fixture-expert.png")

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert cookied.status_code == 200
    cookie = accepted.headers.get("Set-Cookie", "")
    assert "deepr_dashboard=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" not in cookie


def test_dashboard_cookie_is_secure_on_https(client, monkeypatch, tmp_path) -> None:
    portraits = tmp_path / "portraits"
    portraits.mkdir()
    (portraits / "fixture-expert.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(web_app, "_API_KEY", "dashboard-test-secret")
    monkeypatch.setattr(web_app, "_ALLOW_UNAUTHENTICATED_LOOPBACK", False)
    monkeypatch.setattr(
        web_app, "runtime_data_path", lambda name: portraits if name == "portraits" else tmp_path / name
    )

    accepted = client.get(
        "/portraits/fixture-expert.png",
        headers={"Authorization": "Bearer dashboard-test-secret"},
        base_url="https://localhost",
    )

    assert accepted.status_code == 200
    cookie = accepted.headers.get("Set-Cookie", "")
    assert "deepr_dashboard=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
