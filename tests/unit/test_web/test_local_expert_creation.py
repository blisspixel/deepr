"""Web profile creation must preserve the local-only capacity contract."""

from __future__ import annotations

import json
from types import SimpleNamespace

import deepr.web.app as web_app
from deepr.experts.profile import ExpertProfile
from deepr.experts.profile_store import ExpertStore


def test_web_creation_persists_an_untrained_local_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "_experts_dir", tmp_path)
    monkeypatch.setattr(web_app, "_check_auth", lambda: None)
    monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: "fixture-local:2b")
    client = web_app.app.test_client()

    response = client.post("/api/experts", json={"name": "Web Local Expert", "description": "Local evidence review"})

    assert response.status_code == 201
    profile = ExpertStore(str(tmp_path)).load("Web Local Expert")
    assert profile is not None
    assert profile.provider == "local"
    assert profile.model == "fixture-local:2b"
    assert profile.vector_store_id.startswith("local-only:")
    assert profile.monthly_learning_budget == 0.0
    assert profile.knowledge_cutoff_date is None
    assert profile.last_knowledge_refresh is None
    assert profile.total_documents == 0


def test_web_creation_without_a_runtime_cannot_inherit_paid_capacity(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "_experts_dir", tmp_path)
    monkeypatch.setattr(web_app, "_check_auth", lambda: None)
    monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: None)
    client = web_app.app.test_client()

    response = client.post(
        "/api/experts", json={"name": "Offline Expert", "provider": "openai", "monthly_learning_budget": 5.0}
    )

    assert response.status_code == 201
    profile = ExpertStore(str(tmp_path)).load("Offline Expert")
    assert profile is not None
    assert profile.provider == "local"
    assert profile.model == "ollama"
    assert profile.monthly_learning_budget == 0.0
    assert client.post("/api/experts", json={"name": "Offline Expert"}).status_code == 409


def test_profile_details_preserve_the_rosters_study_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "_experts_dir", tmp_path)
    monkeypatch.setattr(web_app, "_check_auth", lambda: None)
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(tmp_path))
    profile = ExpertProfile(name="Studied Expert", vector_store_id="local-only:studied_expert", provider="local")
    ExpertStore(str(tmp_path)).save(profile)
    noticed = tmp_path / "studied_expert" / "noticed" / "current.json"
    noticed.parent.mkdir(parents=True)
    noticed.write_text(
        json.dumps({"totals": {"findings": 14, "grounded_findings": 13}, "independence": {"source_count": 1}}),
        encoding="utf-8",
    )
    client = web_app.app.test_client()

    detail = client.get("/api/experts/Studied%20Expert").get_json()["expert"]
    roster = client.get("/api/experts").get_json()["experts"][0]

    assert detail["studied_findings"] == roster["studied_findings"] == 14
    assert detail["grounded_findings"] == roster["grounded_findings"] == 13
    assert detail["source_count"] == roster["source_count"] == 1


def test_counting_an_untrained_expert_does_not_create_a_belief_store(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(tmp_path))
    profile = SimpleNamespace(
        name="Untrained", source_files=[], research_jobs=[], get_manifest=lambda: SimpleNamespace(gaps=[])
    )

    assert web_app._expert_counts(profile) == (0, 0, 0)
    assert not (tmp_path / "untrained" / "beliefs").exists()
