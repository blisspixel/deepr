"""Tests for build_sync_engine - the shared sync-backend wiring."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.maintenance_engine import build_sync_engine


class _FakeEngine:
    def __init__(self, profile, *, research_fn=None, absorber=None, claim_extractor=None, claim_verifier=None):
        self.profile = profile
        self.research_fn = research_fn
        self.absorber = absorber
        self.claim_extractor = claim_extractor
        self.claim_verifier = claim_verifier


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
        def __init__(self, prof, *, model, client, estimated_cost=0.0):
            captured.update(model=model, client=client, estimated_cost=estimated_cost)

    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: client)
    monkeypatch.setattr(
        "deepr.backends.local.make_local_research_fn",
        lambda model, *, context_builder=None, client=None: research_fn,
    )
    monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", _FakeAbsorber)

    engine, source = build_sync_engine(profile, use_local=True, local_model="qwen-local")

    assert source == "local"
    assert engine.research_fn is research_fn
    assert captured == {"model": "qwen-local", "client": client, "estimated_cost": 0.0}
    assert engine.claim_extractor is None


def test_local_passes_grounding_checker_when_supplied(patch_engine, monkeypatch):
    profile = SimpleNamespace(name="X")
    checker = object()
    captured = {}

    class _FakeAbsorber:
        def __init__(self, prof, *, model, client, grounding_checker=None, estimated_cost=0.0):
            captured.update(model=model, grounding_checker=grounding_checker, estimated_cost=estimated_cost)

    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: object())
    monkeypatch.setattr(
        "deepr.backends.local.make_local_research_fn",
        lambda model, *, context_builder=None, client=None: object(),
    )
    monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", _FakeAbsorber)

    _engine, source = build_sync_engine(profile, use_local=True, local_model="qwen-local", grounding_checker=checker)

    assert source == "local"
    assert captured == {"model": "qwen-local", "grounding_checker": checker, "estimated_cost": 0.0}


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


def test_local_compile_claims_reuses_local_client(patch_engine, monkeypatch):
    profile = SimpleNamespace(name="X")
    client, research_fn = object(), object()

    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: client)
    monkeypatch.setattr(
        "deepr.backends.local.make_local_research_fn",
        lambda model, *, context_builder=None, client=None: research_fn,
    )
    monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", lambda *a, **k: object())

    engine, source = build_sync_engine(
        profile,
        use_local=True,
        local_model="qwen-local",
        compile_claims=True,
    )

    assert source == "local"
    assert engine.claim_extractor is not None
    assert engine.claim_extractor.client is client
    assert engine.claim_extractor.estimated_cost_usd == 0.0
    assert engine.claim_verifier is not None
    assert engine.claim_verifier.client is client
    assert engine.claim_verifier.estimated_cost_usd == 0.0


def test_metered_compile_claims_is_explicit_opt_in(patch_engine):
    profile = SimpleNamespace(name="X")

    engine, source = build_sync_engine(profile, compile_claims=True)

    assert source == "api_metered"
    assert engine.claim_extractor is not None
    assert engine.claim_extractor.allow_metered is True
    assert engine.claim_extractor.estimated_cost_usd > 0
    assert engine.claim_verifier is not None
    assert engine.claim_verifier.allow_metered is True
    assert engine.claim_verifier.estimated_cost_usd > 0


def test_metered_plan_compile_claims_uses_budgeted_estimate(patch_engine, monkeypatch):
    profile = SimpleNamespace(name="X")
    adapter = SimpleNamespace(backend_id="copilot", tos_note="", metered_at_margin=True)
    monkeypatch.setattr("deepr.backends.plan_quota.PlanQuotaChatClient", lambda a, *, model=None: object())
    monkeypatch.setattr(
        "deepr.backends.plan_quota.make_plan_quota_research_fn",
        lambda a, *, model=None, context_builder=None, client=None: object(),
    )
    monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", lambda *a, **k: object())

    engine, source = build_sync_engine(profile, use_plan=True, plan_adapter=adapter, compile_claims=True)

    assert source == "plan_quota:copilot"
    assert engine.claim_extractor is not None
    assert engine.claim_extractor.allow_metered is True
    assert engine.claim_extractor.estimated_cost_usd > 0
    assert engine.claim_verifier is not None
    assert engine.claim_verifier.allow_metered is True
    assert engine.claim_verifier.estimated_cost_usd > 0


def test_metered_path_injects_absorber_when_grounding_checker_supplied(patch_engine, monkeypatch):
    profile = SimpleNamespace(name="X")
    checker = object()
    captured = {}

    class _FakeAbsorber:
        def __init__(self, prof, *, grounding_checker=None):
            captured["grounding_checker"] = grounding_checker

    monkeypatch.setattr("deepr.experts.report_absorber.ReportAbsorber", _FakeAbsorber)

    engine, source = build_sync_engine(profile, grounding_checker=checker)

    assert source == "api_metered"
    assert engine.research_fn is None
    assert engine.absorber is not None
    assert captured["grounding_checker"] is checker
