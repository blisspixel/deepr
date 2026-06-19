"""Tests for versioned expert handoff payloads."""

from __future__ import annotations

from deepr.core.contracts import Claim, DecisionRecord, DecisionType, ExpertManifest, Gap
from deepr.experts.handoff import HANDOFF_SCHEMA_VERSION, build_expert_handoff
from deepr.experts.profile import ExpertProfile


def _profile() -> ExpertProfile:
    return ExpertProfile(
        name="Reach Expert",
        vector_store_id="vs-reach",
        description="Remote handoff expert",
        domain="interop",
    )


def _manifest() -> ExpertManifest:
    return ExpertManifest(
        expert_name="Reach Expert",
        domain="interop",
        claims=[
            Claim.create("Low confidence claim", "interop", 0.4),
            Claim.create("High confidence claim", "interop", 0.9),
        ],
        gaps=[
            Gap.create("Low value gap", ev_cost_ratio=0.5, priority=2),
            Gap.create("High value gap", ev_cost_ratio=3.0, priority=5),
        ],
        decisions=[
            DecisionRecord.create(
                DecisionType.ROUTING,
                "Use handoff payload",
                "Downstream agents need a stable read contract",
                confidence=0.8,
            )
        ],
        policies={"refresh_days": 30, "budget_cap": 5.0, "velocity": "medium"},
    )


def test_build_expert_handoff_is_versioned_and_bounded():
    payload = build_expert_handoff(
        _profile(),
        manifest=_manifest(),
        telemetry={"contested_claims": {"open_count": 2}},
        loop_status={"count": 1, "runs": []},
        max_claims=1,
        max_gaps=1,
        include_decisions=True,
    )

    assert payload["schema_version"] == HANDOFF_SCHEMA_VERSION
    assert payload["kind"] == "deepr.expert.handoff"
    assert payload["contract"]["read_only"] is True
    assert payload["contract"]["cost_usd"] == 0.0
    assert payload["summary"]["claim_count"] == 2
    assert payload["summary"]["open_gap_count"] == 2
    assert payload["summary"]["contested_open_count"] == 2
    assert payload["claims"][0]["statement"] == "High confidence claim"
    assert len(payload["claims"]) == 1
    assert payload["gaps"][0]["topic"] == "High value gap"
    assert len(payload["gaps"]) == 1
    assert payload["decisions"][0]["title"] == "Use handoff payload"
    assert payload["okf"]["canonical"] is False
    assert payload["okf"]["profile_schema_version"] == "deepr-okf-profile-v1"
    assert payload["okf"]["profile_schema_url"] == "docs/schemas/okf-profile-v1.json"
    assert "deepr_expert_handoff" in payload["recommended_mcp_tools"]


def test_build_expert_handoff_can_omit_heavy_sections():
    payload = build_expert_handoff(
        _profile(),
        manifest=_manifest(),
        telemetry={"contested_claims": {"open_count": 0}},
        loop_status={"count": 0, "runs": []},
        include_claims=False,
        include_gaps=False,
    )

    assert "claims" not in payload
    assert "gaps" not in payload
    assert "decisions" not in payload
    assert payload["limits"]["max_claims"] == 0
    assert payload["limits"]["max_gaps"] == 0
