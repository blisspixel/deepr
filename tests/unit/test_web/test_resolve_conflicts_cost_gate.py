"""Regression for the legacy conflict-resolution silent-money path."""

from __future__ import annotations

from flask import Flask

from deepr.web import app as web_app


def test_resolve_conflicts_fails_before_store_or_provider(monkeypatch):
    import deepr.experts.profile_store as profile_store
    import deepr.providers as providers

    assert isinstance(web_app.app, Flask)
    web_app.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if web_app.limiter is not None:
        monkeypatch.setattr(web_app.limiter, "enabled", False)

    class ExplodingStore:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("blocked resolution must not open the expert store")

    def fail_create_provider(*_args, **_kwargs):
        raise AssertionError("blocked resolution must not construct a provider")

    monkeypatch.setattr(profile_store, "ExpertStore", ExplodingStore)
    monkeypatch.setattr(providers, "create_provider", fail_create_provider)

    response = web_app.app.test_client().post(
        "/api/experts/Safety%20Expert/resolve-conflicts",
        json={"budget": 5.0},
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["error_code"] == "METERED_ACCOUNTING_UNAVAILABLE"
    assert payload["read_only_alternative"] == "deepr expert contested"
