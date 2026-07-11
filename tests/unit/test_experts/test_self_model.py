"""Tests for derived expert self-model records."""

from __future__ import annotations

from datetime import UTC, datetime

from deepr.core.contracts import Claim, ExpertManifest, Gap, Source
from deepr.experts.profile import ExpertProfile
from deepr.experts.self_model import (
    EXPERT_SELF_MODEL_KIND,
    EXPERT_SELF_MODEL_SCHEMA_VERSION,
    build_expert_self_model,
    build_expert_self_model_context,
    build_expert_self_model_context_from_profile,
)


def _profile(**overrides):
    defaults = {
        "name": "Agent Harness Expert",
        "vector_store_id": "vs-agent-harness",
        "domain": "agent harnesses",
        "knowledge_cutoff_date": datetime(2026, 6, 26, tzinfo=UTC),
        "last_knowledge_refresh": datetime(2026, 6, 26, tzinfo=UTC),
        "total_documents": 3,
        "installed_skills": ["consult-review"],
    }
    defaults.update(overrides)
    return ExpertProfile(**defaults)


def _manifest() -> ExpertManifest:
    source = Source.create("Trace design note", extraction_method="manual")
    return ExpertManifest(
        expert_name="Agent Harness Expert",
        domain="agent harnesses",
        claims=[
            Claim.create(
                "Trace failed consults before changing prompts.",
                "agent harnesses",
                0.91,
                sources=[source],
            ),
            Claim.create(
                "Unchecked context can be promoted automatically.",
                "agent harnesses",
                0.31,
                contradicts=["claim_safe_review"],
            ),
        ],
        gaps=[
            Gap.create(
                "semantic answer quality evals",
                questions=["Which answers were generic despite stored beliefs?"],
                priority=5,
                ev_cost_ratio=12.0,
            ),
            Gap.create(
                "closed packaging gap",
                questions=["resolved"],
                filled=True,
                ev_cost_ratio=50.0,
            ),
        ],
    )


def test_build_expert_self_model_bounds_current_focus_packet():
    payload = build_expert_self_model(_profile(), _manifest(), focus_limit=1)

    assert payload["schema_version"] == EXPERT_SELF_MODEL_SCHEMA_VERSION
    assert payload["kind"] == EXPERT_SELF_MODEL_KIND
    assert payload["contract"]["read_only"] is True
    assert payload["contract"]["cost_usd"] == 0.0
    assert payload["contract"]["derived_view"] is True
    assert payload["expert"]["name"] == "Agent Harness Expert"
    assert payload["capabilities"]["claim_count"] == 2
    assert payload["capabilities"]["open_gap_count"] == 1
    assert len(payload["current_focus_packet"]["selected_beliefs"]) == 1
    assert len(payload["current_focus_packet"]["selected_gaps"]) == 1
    assert payload["current_focus_packet"]["selected_gaps"][0]["topic"] == "semantic answer quality evals"
    assert payload["current_focus_packet"]["active_contradictions"][0]["claim_id"]
    assert "deepr expert why" in payload["current_focus_packet"]["allowed_tools"]
    assert "deepr expert explain-belief" not in payload["current_focus_packet"]["allowed_tools"]


def test_build_expert_self_model_surfaces_blockers_and_risks():
    profile = _profile(vector_store_id="", knowledge_cutoff_date=None, installed_skills=[], total_documents=0)
    manifest = ExpertManifest(
        expert_name="Empty Expert",
        domain="empty",
        gaps=[Gap.create("missing baseline", questions=["What is known?"], ev_cost_ratio=2.0)],
    )

    payload = build_expert_self_model(profile, manifest)
    codes = {item["code"] for item in payload["blocked_capabilities"]}

    assert {"no_manifest_claims", "no_vector_store", "open_gaps"} <= codes
    assert any("Freshness status is incomplete" in risk for risk in payload["unresolved_risks"])
    assert payload["current_goals"][0] == "refresh stale or incomplete knowledge"
    assert payload["current_goals"][1] == "close highest-value gap: missing baseline"
    assert "No current claims in manifest." in payload["limitations"]


def test_build_expert_self_model_does_not_require_vector_store_for_local_expert():
    profile = _profile(provider="local", vector_store_id="")

    payload = build_expert_self_model(profile, _manifest())

    assert "no_vector_store" not in {item["code"] for item in payload["blocked_capabilities"]}


def test_build_expert_self_model_does_not_mutate_inputs():
    profile = _profile()
    manifest = _manifest()
    profile_before = profile.to_dict()
    manifest_before = manifest.to_dict()

    payload = build_expert_self_model(profile, manifest)
    payload["current_focus_packet"]["selected_beliefs"][0]["contradicts"].append("mutated")

    assert profile.to_dict() == profile_before
    assert manifest.to_dict() == manifest_before


def test_build_expert_self_model_context_from_profile_is_bounded():
    payload = build_expert_self_model_context_from_profile(_profile(), focus_limit=1)

    assert payload["schema_version"] == EXPERT_SELF_MODEL_SCHEMA_VERSION
    assert payload["kind"] == EXPERT_SELF_MODEL_KIND
    assert payload["status"] == "available"
    assert payload["contract"] == {
        "read_only": True,
        "cost_usd": 0.0,
        "derived_view": True,
        "goal_changes_require_review": True,
    }
    assert set(payload) == {
        "schema_version",
        "kind",
        "status",
        "contract",
        "current_goals",
        "calibration",
        "blocked_capability_count",
        "unresolved_risk_count",
        "current_focus_packet",
    }
    assert payload["current_focus_packet"]["allowed_tools"]


def test_build_expert_self_model_context_handles_missing_profile(monkeypatch):
    class EmptyExpertStore:
        def load(self, name):
            assert name == "Ghost Expert"
            return None

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", EmptyExpertStore)

    assert build_expert_self_model_context("Ghost Expert") == {}


def test_build_expert_self_model_context_reports_unavailable_without_paths(monkeypatch):
    class ExplodingExpertStore:
        def load(self, name):
            raise RuntimeError(f"cannot read local path for {name}")

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", ExplodingExpertStore)

    payload = build_expert_self_model_context("Broken Expert")

    assert payload == {
        "schema_version": EXPERT_SELF_MODEL_SCHEMA_VERSION,
        "kind": EXPERT_SELF_MODEL_KIND,
        "status": "unavailable",
        "error_type": "RuntimeError",
    }
