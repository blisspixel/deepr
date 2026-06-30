"""Regression tests for expert portrait web API cost safety."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytest.importorskip("flask")

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key")

from deepr.web import app as web_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    web_app.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    web_app._PORTRAIT_LAST_GENERATED.clear()
    monkeypatch.setattr(web_app, "_experts_dir", tmp_path / "experts")
    return web_app.app.test_client()


def _install_fake_store(monkeypatch, profile, saved):
    import deepr.experts.profile_store as profile_store

    class FakeStore:
        def __init__(self, *_args, **_kwargs):
            pass

        def exists(self, name):
            return name == profile.name

        def load(self, name):
            return profile if name == profile.name else None

        def save(self, saved_profile):
            saved.append(saved_profile)

    monkeypatch.setattr(profile_store, "ExpertStore", FakeStore)


def test_portrait_generation_blocks_before_provider_spend(client, monkeypatch):
    import deepr.experts.cost_safety as cost_safety
    import deepr.experts.portraits as portraits

    profile = SimpleNamespace(name="Budget Expert", domain="cost control", description="testing")
    saved = []
    _install_fake_store(monkeypatch, profile, saved)

    class FakeCostSafety:
        def check_and_reserve(self, **kwargs):
            assert kwargs["estimated_cost"] == 0.04
            return False, "daily limit reached", False, ""

        def refund_reservation(self, _reservation_id):
            raise AssertionError("blocked calls must not reserve")

        def record_cost(self, **_kwargs):
            raise AssertionError("blocked calls must not record cost")

    async def fail_generate_portrait(**_kwargs):
        raise AssertionError("provider call should be blocked before spend")

    monkeypatch.setattr(cost_safety, "get_cost_safety_manager", lambda: FakeCostSafety())
    monkeypatch.setattr(portraits, "portrait_cost", lambda provider: 0.04 if provider != "local" else 0.0)
    monkeypatch.setattr(portraits, "generate_portrait", fail_generate_portrait)

    resp = client.post("/api/experts/Budget%20Expert/generate-portrait", json={"provider": "openai"})

    assert resp.status_code == 402
    assert resp.get_json() == {"error": "Portrait generation blocked by cost safety: daily limit reached"}
    assert saved == []


def test_portrait_generation_settles_reserved_cost(client, monkeypatch):
    import deepr.experts.cost_safety as cost_safety
    import deepr.experts.portraits as portraits

    profile = SimpleNamespace(name="Budget Expert", domain="cost control", description="testing")
    saved = []
    checks = []
    records = []
    _install_fake_store(monkeypatch, profile, saved)

    class FakeCostSafety:
        def check_and_reserve(self, **kwargs):
            checks.append(kwargs)
            return True, "OK", False, "reservation-1"

        def refund_reservation(self, _reservation_id):
            raise AssertionError("successful generation must not refund")

        def record_cost(self, **kwargs):
            records.append(kwargs)
            return True

    async def fake_generate_portrait(**kwargs):
        assert kwargs["provider"] == "openai"
        return "/portraits/budget-expert.png"

    monkeypatch.setattr(cost_safety, "get_cost_safety_manager", lambda: FakeCostSafety())
    monkeypatch.setattr(portraits, "portrait_cost", lambda provider: 0.04 if provider != "local" else 0.0)
    monkeypatch.setattr(portraits, "generate_portrait", fake_generate_portrait)

    resp = client.post("/api/experts/Budget%20Expert/generate-portrait", json={"provider": "openai"})

    assert resp.status_code == 200
    assert resp.get_json() == {"portrait_url": "/portraits/budget-expert.png"}
    assert profile.portrait_url == "/portraits/budget-expert.png"
    assert saved == [profile]
    assert checks[0]["session_id"] == "portrait_Budget Expert"
    assert records[0]["reservation_id"] == "reservation-1"
    assert records[0]["actual_cost"] == 0.04
    assert records[0]["provider"] == "openai"


def test_portrait_generation_allows_explicit_local_without_cost_reservation(client, monkeypatch):
    import deepr.experts.cost_safety as cost_safety
    import deepr.experts.portraits as portraits

    profile = SimpleNamespace(name="Local Expert", domain="local image", description="testing")
    saved = []
    _install_fake_store(monkeypatch, profile, saved)

    async def fake_generate_portrait(**kwargs):
        assert kwargs["provider"] == "local"
        return "/portraits/local-expert.png"

    monkeypatch.setattr(cost_safety, "get_cost_safety_manager", lambda: pytest.fail("local portraits are free"))
    monkeypatch.setattr(portraits, "portrait_cost", lambda provider: 0.0 if provider == "local" else 0.04)
    monkeypatch.setattr(portraits, "generate_portrait", fake_generate_portrait)

    resp = client.post("/api/experts/Local%20Expert/generate-portrait", json={"provider": "local"})

    assert resp.status_code == 200
    assert resp.get_json() == {"portrait_url": "/portraits/local-expert.png"}
    assert saved == [profile]
