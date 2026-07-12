"""Regression tests for expert gap-fill web API cost safety."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("flask")

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key")

from deepr.web import app as web_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    web_app.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if web_app.limiter is not None:
        web_app.limiter.enabled = False
    monkeypatch.setattr(web_app, "_experts_dir", tmp_path / "experts")
    return web_app.app.test_client()


def test_fill_gaps_requires_metered_confirmation_before_store_or_provider(client, monkeypatch):
    import deepr.experts.profile_store as profile_store
    import deepr.providers as providers

    class ExplodingStore:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("unconfirmed metered gap fill must not open the expert store")

    def fail_create_provider(*_args, **_kwargs):
        raise AssertionError("unconfirmed metered gap fill must not construct a provider")

    monkeypatch.setattr(profile_store, "ExpertStore", ExplodingStore)
    monkeypatch.setattr(providers, "create_provider", fail_create_provider)

    resp = client.post(
        "/api/experts/Budget%20Expert/fill-gaps",
        json={"deep": True, "budget": 5.0, "top": 3},
    )

    assert resp.status_code == 402
    assert resp.get_json() == {
        "error": "Metered gap filling requires explicit API and cost confirmation.",
        "status": "blocked",
        "estimated_cost_usd": 5.0,
        "required": {
            "allow_metered_api": True,
            "confirm_metered_cost": True,
        },
        "safe_alternative": 'deepr expert route-gaps "Budget Expert" --execute --scheduled',
    }


def test_confirmed_fill_gaps_still_fails_before_provider_work(client, monkeypatch):
    import deepr.experts.profile_store as profile_store

    class ExplodingStore:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("disabled metered gap fill must not open the expert store")

    monkeypatch.setattr(profile_store, "ExpertStore", ExplodingStore)
    resp = client.post(
        "/api/experts/Budget%20Expert/fill-gaps",
        json={
            "allow_metered_api": True,
            "confirm_metered_cost": True,
            "deep": True,
            "budget": 5.0,
        },
    )

    assert resp.status_code == 503
    payload = resp.get_json()
    assert payload["error_code"] == "metered_expert_mutation_accounting_unavailable"
    assert payload["provider_work_started"] is False
    assert payload["retryable"] is False


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/experts/Budget%20Expert/citation-validations", "get"),
        ("/api/experts/Budget%20Expert/discover-gaps", "post"),
    ],
)
def test_other_metered_expert_web_mutations_fail_closed(client, path, method):
    response = getattr(client, method)(path)

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["error_code"] == "metered_expert_mutation_accounting_unavailable"
    assert payload["provider_work_started"] is False
