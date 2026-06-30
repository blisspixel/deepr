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
    if web_app.limiter is not None:
        web_app.limiter.enabled = False
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

    resp = client.post(
        "/api/experts/Budget%20Expert/generate-portrait",
        json={"provider": "openai", "confirm_metered_cost": True},
    )

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

    resp = client.post(
        "/api/experts/Budget%20Expert/generate-portrait",
        json={"provider": "openai", "confirm_metered_cost": True},
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"portrait_url": "/portraits/budget-expert.png"}
    assert profile.portrait_url == "/portraits/budget-expert.png"
    assert saved == [profile]
    assert checks[0]["session_id"] == "portrait_Budget Expert"
    assert records[0]["reservation_id"] == "reservation-1"
    assert records[0]["actual_cost"] == 0.04
    assert records[0]["provider"] == "openai"


def test_portrait_generation_refunds_and_returns_generic_error_on_provider_failure(client, monkeypatch):
    import deepr.experts.cost_safety as cost_safety
    import deepr.experts.portraits as portraits

    profile = SimpleNamespace(name="Budget Expert", domain="cost control", description="testing")
    saved = []
    refunds = []
    _install_fake_store(monkeypatch, profile, saved)

    class FakeCostSafety:
        def check_and_reserve(self, **_kwargs):
            return True, "OK", False, "reservation-1"

        def refund_reservation(self, reservation_id):
            refunds.append(reservation_id)
            return True

        def record_cost(self, **_kwargs):
            raise AssertionError("failed generation must not record cost")

    async def fail_generate_portrait(**_kwargs):
        raise RuntimeError("provider detail that must not reach the response")

    monkeypatch.setattr(cost_safety, "get_cost_safety_manager", lambda: FakeCostSafety())
    monkeypatch.setattr(portraits, "portrait_cost", lambda provider: 0.04 if provider != "local" else 0.0)
    monkeypatch.setattr(portraits, "generate_portrait", fail_generate_portrait)

    resp = client.post(
        "/api/experts/Budget%20Expert/generate-portrait",
        json={"provider": "openai", "confirm_metered_cost": True},
    )

    assert resp.status_code == 500
    assert resp.get_json() == {"error": "Portrait generation failed"}
    assert refunds == ["reservation-1"]
    assert saved == []


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


def test_portrait_generation_refuses_existing_without_force(client, monkeypatch):
    import deepr.experts.cost_safety as cost_safety
    import deepr.experts.portraits as portraits

    profile = SimpleNamespace(
        name="Existing Expert",
        domain="local image",
        description="testing",
        portrait_url="/portraits/existing-expert.png",
    )
    saved = []
    _install_fake_store(monkeypatch, profile, saved)

    monkeypatch.setattr(
        cost_safety, "get_cost_safety_manager", lambda: pytest.fail("existing portrait must not reserve")
    )
    monkeypatch.setattr(portraits, "generate_portrait", pytest.fail)

    resp = client.post("/api/experts/Existing%20Expert/generate-portrait", json={"provider": "local"})

    assert resp.status_code == 409
    assert resp.get_json() == {
        "error": "Portrait already exists. Pass force=true to regenerate.",
        "portrait_url": "/portraits/existing-expert.png",
    }
    assert saved == []


def test_portrait_generation_requires_metered_cost_confirmation(client, monkeypatch):
    import deepr.experts.cost_safety as cost_safety
    import deepr.experts.portraits as portraits

    profile = SimpleNamespace(name="Paid Expert", domain="paid image", description="testing")
    saved = []
    _install_fake_store(monkeypatch, profile, saved)

    monkeypatch.setattr(cost_safety, "get_cost_safety_manager", lambda: pytest.fail("unconfirmed metered spend"))
    monkeypatch.setattr(portraits, "portrait_cost", lambda provider: 0.04 if provider != "local" else 0.0)
    monkeypatch.setattr(portraits, "generate_portrait", pytest.fail)

    resp = client.post("/api/experts/Paid%20Expert/generate-portrait", json={"provider": "openai"})

    assert resp.status_code == 402
    assert resp.get_json() == {
        "error": "Metered portrait generation requires explicit cost confirmation.",
        "provider": "openai",
        "estimated_cost_usd": 0.04,
    }
    assert saved == []


def test_portrait_generation_without_local_or_explicit_paid_provider_fails_before_reservation(client, monkeypatch):
    import deepr.experts.cost_safety as cost_safety
    import deepr.experts.portraits as portraits

    profile = SimpleNamespace(name="No Generator Expert", domain="image", description="testing")
    saved = []
    _install_fake_store(monkeypatch, profile, saved)

    monkeypatch.setattr(cost_safety, "get_cost_safety_manager", lambda: pytest.fail("no provider must not reserve"))
    monkeypatch.setattr(portraits, "detect_provider", lambda: None)
    monkeypatch.setattr(portraits, "generate_portrait", pytest.fail)

    resp = client.post("/api/experts/No%20Generator%20Expert/generate-portrait", json={})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "No image generator available"}
    assert saved == []
