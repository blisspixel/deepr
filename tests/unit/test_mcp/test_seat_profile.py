"""Fleet-seat profile: local consult for external hosts, with no claimed support."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.handoff import absent_context_section, build_expert_handoff, context_section_from_blueprint
from deepr.mcp.host_profile import read_only_tool_names
from deepr.mcp.seat_consumer import (
    build_seat_profile,
    explain_route_tool,
    serialize_seat_profile,
    validate_seat_profile,
)
from deepr.mcp.security.tool_allowlist import ResearchMode, ToolAllowlist


def test_read_only_profile_does_not_gain_seat_tools() -> None:
    names = read_only_tool_names()
    assert "deepr_consult_experts" not in names
    assert "deepr_route_explain" not in names
    assert len(names) == 10


def test_seat_mode_allows_consult_and_refuses_spend_tools() -> None:
    allow = ToolAllowlist(mode=ResearchMode.SEAT)
    assert allow.is_allowed("deepr_consult_experts") is True
    assert allow.is_allowed("deepr_route_explain") is True
    assert allow.is_allowed("deepr_expert_handoff") is True
    assert allow.require_confirmation("deepr_consult_experts") is False
    for denied in ("deepr_research", "deepr_expert_absorb", "deepr_install_skill", "deepr_reflect"):
        assert allow.is_allowed(denied) is False


@pytest.mark.asyncio
async def test_route_card_is_zero_cost_and_not_a_verdict(monkeypatch, tmp_path) -> None:
    class _FakeStore:
        def list_all(self):
            return [
                SimpleNamespace(name="Cloud Security Expert", domain="cloud security", description=""),
                SimpleNamespace(name="Baking Expert", domain="sourdough", description=""),
            ]

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", _FakeStore)
    payload = await explain_route_tool(
        query="cloud security",
        max_experts=1,
        top_n=2,
        admissions_path=tmp_path / "none.jsonl",
    )
    assert payload["contract"]["cost_usd"] == 0.0
    assert payload["contract"]["no_model_call"] is True
    assert payload["contract"]["routing_only"] is True
    assert payload["expert_routing"]["candidates"][0]["would_consult"] is True


@pytest.mark.asyncio
async def test_seat_consult_refuses_plan_before_provider_work(monkeypatch) -> None:
    monkeypatch.setenv("DEEPR_RESEARCH_MODE", "seat")
    from deepr.mcp.consult_tool import consult_experts_tool

    out = await consult_experts_tool(question="What changed?", synthesis_backend="plan", plan="claude")
    assert out["error_code"] == "SEAT_LOCAL_ONLY"
    assert out["retryable"] is False


def test_seat_profile_names_open_source_hosts_without_claiming_support() -> None:
    profile = build_seat_profile()
    assert validate_seat_profile(profile) == []
    assert serialize_seat_profile(profile).endswith("\n")
    assert profile["env"]["DEEPR_RESEARCH_MODE"] == "seat"
    assert profile["env"]["DEEPR_MAX_COST_PER_MONTH"] == "0"
    assert profile["authority"]["host_support_claimed"] is False
    assert profile["config_fragment"]["mcpServers"]["deepr"]["args"] == ["mcp", "serve"]


def test_handoff_context_section_copies_purpose_without_authority() -> None:
    blueprint = SimpleNamespace(
        revision=2,
        content_hash="abc",
        mission="Choose the next mesh test",
        non_goals=["Do not buy spectrum"],
        decision_use_cases=[SimpleNamespace(id="next-test", question="Which band do we measure?")],
    )
    section = context_section_from_blueprint(blueprint)
    assert section["purpose_status"] == "operator_attested"
    assert section["mission"] == "Choose the next mesh test"
    assert section["may_authorize_spend"] is False
    assert section["may_authorize_external_actions"] is False
    payload = build_expert_handoff(
        SimpleNamespace(
            name="Reach Expert",
            domain="interop",
            description=None,
            created_at=None,
            updated_at=None,
            knowledge_cutoff_date=None,
            last_knowledge_refresh=None,
            refresh_frequency_days=0,
            domain_velocity="",
            source_files=[],
            research_jobs=[],
            total_documents=0,
            get_manifest=lambda: SimpleNamespace(
                expert_name="Reach Expert",
                claims=[],
                decisions=[],
                top_gaps=lambda _limit: [],
                claim_count=0,
                open_gap_count=0,
                avg_confidence=0.0,
                generated_at=None,
                policies={},
            ),
        ),
        context_section=section,
        telemetry={"contested_claims": {"open_count": 0}},
        loop_status={"count": 0},
    )
    assert payload["context_section"]["authority"] == "context_only"
    assert absent_context_section()["purpose_status"] == "absent"
