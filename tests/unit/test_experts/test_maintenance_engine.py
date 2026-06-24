"""Tests for build_sync_engine - the shared sync-backend wiring."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.maintenance_engine import build_sync_engine


class _FakeEngine:
    def __init__(self, profile, *, research_fn=None, absorber=None):
        self.profile = profile
        self.research_fn = research_fn
        self.absorber = absorber


@pytest.fixture
def patch_engine(monkeypatch):
    monkeypatch.setattr("deepr.experts.sync.ExpertSyncEngine", _FakeEngine)
    return _FakeEngine


def test_metered_default_uses_plain_engine(patch_engine):
    profile = SimpleNamespace(name="X")
    engine, source = build_sync_engine(profile)
    assert isinstance(engine, _FakeEngine)
    assert engine.research_fn is None and engine.absorber is None  # injection-free metered path
    assert source == "api_metered"


def test_local_builds_local_research_and_absorber(patch_engine, monkeypatch):
    profile = SimpleNamespace(name="X")
    client, research_fn = object(), object()
    captured = {}

    class _FakeAbsorber:
        def __init__(self, prof, *, model, client):
            captured.update(model=model, client=client)

    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: client)
    monkeypatch.setattr(
        "deepr.backends.local.make_local_research_fn",
        lambda model, *, context_builder=None: research_fn,
    )
    monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", _FakeAbsorber)

    engine, source = build_sync_engine(profile, use_local=True, local_model="qwen-local")

    assert source == "local"
    assert engine.research_fn is research_fn
    assert captured == {"model": "qwen-local", "client": client}


def test_local_without_model_is_a_programming_error(patch_engine):
    # The caller must resolve the model before choosing the local rung.
    with pytest.raises(ValueError, match="resolved local_model"):
        build_sync_engine(SimpleNamespace(name="X"), use_local=True, local_model=None)


def test_plan_reports_backend_id_source(patch_engine, monkeypatch):
    profile = SimpleNamespace(name="X")
    adapter = SimpleNamespace(backend_id="codex", tos_note="")
    monkeypatch.setattr("deepr.backends.plan_quota.PlanQuotaChatClient", lambda a, *, model=None: object())
    monkeypatch.setattr(
        "deepr.backends.plan_quota.make_plan_quota_research_fn",
        lambda a, *, model=None, context_builder=None, client=None: object(),
    )
    monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", lambda *a, **k: object())

    _engine, source = build_sync_engine(profile, use_plan=True, plan_adapter=adapter, plan_model="gpt")

    assert source == "plan_quota:codex"
