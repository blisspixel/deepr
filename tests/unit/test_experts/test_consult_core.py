"""Shared consult core tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from deepr.experts.consult import (
    MAX_CONSULT_EXPERTS,
    AnthropicConsultSynthesisClient,
    ConsultBackendError,
    build_collaboration_contract,
    build_consult_payload,
    build_synthesis_backend,
    resolve_explicit_expert_choices,
    run_consult,
)
from deepr.experts.profile import ExpertProfile, ExpertStore


def test_consult_machine_contracts_preserve_sub_tenth_cent_costs_exactly():
    result = {
        "perspectives": [
            {
                "expert_name": "Tiny Cost Expert",
                "domain": "accounting",
                "response": "Keep exact costs.",
                "confidence": 0.8,
                "cost": 0.000045,
                "context": {"source": "belief_store"},
            }
        ],
        "synthesis": "Exact.",
        "agreements": [],
        "disagreements": [],
        "requested_budget_usd": 1.0,
        "total_cost": 0.000045,
    }

    payload = build_consult_payload("q", result)
    collaboration = build_collaboration_contract("q", result)

    assert payload["cost_usd"] == 0.000045
    assert payload["contract"]["cost_usd"] == 0.000045
    assert payload["collaboration"]["budget_capacity_contract"]["actual_cost_usd"] == 0.000045
    assert payload["collaboration"]["roster"][0]["cost_usd"] == 0.000045
    assert collaboration["contract"]["cost_usd"] == 0.000045


@pytest.mark.asyncio
async def test_run_consult_resolves_explicit_expert_slug_to_profile(monkeypatch):
    store = ExpertStore()
    store.save(
        ExpertProfile(
            name="AI Agent Harnesses",
            vector_store_id="vs-test",
            domain="agent harnesses",
            description="agent loop and long-running harness design",
        )
    )
    captured: dict[str, object] = {}

    async def fake_consult(self, question, experts, budget):
        captured["question"] = question
        captured["experts"] = experts
        captured["budget"] = budget
        return {"query": question, "perspectives": [], "synthesis": "", "total_cost": 0.0}

    monkeypatch.setattr("deepr.experts.council.ExpertCouncil.consult", fake_consult)

    await run_consult("What should the loop improve next?", ["ai_agent_harnesses"], max_experts=3, budget=1.25)

    assert captured["question"] == "What should the loop improve next?"
    assert captured["experts"] == [{"name": "AI Agent Harnesses", "domain": "agent harnesses"}]
    assert captured["budget"] == 1.25


def test_resolve_explicit_expert_choices_preserves_roster_order():
    profiles = [
        ExpertProfile(name="Alpha Expert", vector_store_id="vs-alpha", domain="alpha"),
        ExpertProfile(name="Beta Expert", vector_store_id="vs-beta", domain="beta"),
    ]

    choices = resolve_explicit_expert_choices(["beta_expert", "ALPHA EXPERT"], profiles=profiles)

    assert choices == [
        {"name": "Beta Expert", "domain": "beta"},
        {"name": "Alpha Expert", "domain": "alpha"},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "roster",
    [
        ["AI Agent Harnesses", "AI Agent Harnesses"],
        ["AI Agent Harnesses", "ai agent harnesses"],
        ["AI Agent Harnesses", "ai_agent_harnesses"],
    ],
    ids=["exact", "case", "slug"],
)
async def test_run_consult_rejects_duplicate_explicit_expert_aliases_before_dispatch(monkeypatch, roster):
    ExpertStore().save(
        ExpertProfile(
            name="AI Agent Harnesses",
            vector_store_id="vs-test",
            domain="agent harnesses",
        )
    )
    consult = AsyncMock()
    monkeypatch.setattr("deepr.experts.council.ExpertCouncil.consult", consult)

    with pytest.raises(ValueError, match="Duplicate expert roster entry"):
        await run_consult("q", roster, max_experts=3, budget=0.0)

    consult.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_consult_rejects_oversized_explicit_roster_before_resolution(monkeypatch):
    def fail_resolution(_experts):
        raise AssertionError("explicit roster should be bounded before resolution")

    monkeypatch.setattr("deepr.experts.consult.resolve_explicit_expert_choices", fail_resolution)

    with pytest.raises(ValueError, match=f"cannot exceed {MAX_CONSULT_EXPERTS}"):
        await run_consult(
            "q",
            [f"Expert {index}" for index in range(MAX_CONSULT_EXPERTS + 1)],
            max_experts=3,
            budget=0.0,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("max_experts", [0, MAX_CONSULT_EXPERTS + 1, True, 1.5])
async def test_run_consult_rejects_invalid_automatic_fanout_before_council_construction(monkeypatch, max_experts):
    def fail_council(**_kwargs):
        raise AssertionError("invalid automatic fanout should fail before council construction")

    monkeypatch.setattr("deepr.experts.council.ExpertCouncil", fail_council)

    with pytest.raises(ValueError, match=f"between 1 and {MAX_CONSULT_EXPERTS}"):
        await run_consult("q", [], max_experts=max_experts, budget=0.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [float("nan"), float("inf"), float("-inf"), -0.1, True])
async def test_run_consult_rejects_invalid_budget_before_council_construction(monkeypatch, budget):
    def fail_council(**_kwargs):
        raise AssertionError("invalid budget should fail before council construction")

    monkeypatch.setattr("deepr.experts.council.ExpertCouncil", fail_council)

    with pytest.raises(ValueError, match="finite and non-negative"):
        await run_consult("q", ["A"], max_experts=3, budget=budget)


@pytest.mark.asyncio
async def test_run_consult_passes_synthesis_backend_options(monkeypatch):
    sentinel_client = object()
    captured: dict[str, object] = {}

    class FakeCouncil:
        def __init__(
            self,
            *,
            synthesis_client,
            synthesis_model,
            synthesis_provider,
            allow_live_fallback,
        ):
            captured["synthesis_client"] = synthesis_client
            captured["synthesis_model"] = synthesis_model
            captured["synthesis_provider"] = synthesis_provider
            captured["allow_live_fallback"] = allow_live_fallback

        async def select_experts(self, query, max_experts):
            captured["select"] = (query, max_experts)
            return [{"name": "A", "domain": "alpha"}]

        async def consult(self, question, experts, budget):
            captured["consult"] = (question, experts, budget)
            return {"query": question, "perspectives": [], "synthesis": "", "total_cost": 0.0}

    monkeypatch.setattr("deepr.experts.council.ExpertCouncil", FakeCouncil)

    await run_consult(
        "q",
        [],
        max_experts=2,
        budget=0.5,
        synthesis_client=sentinel_client,
        synthesis_model="local-model",
        synthesis_provider="local",
        allow_live_fallback=False,
    )

    assert captured["synthesis_client"] is sentinel_client
    assert captured["synthesis_model"] == "local-model"
    assert captured["synthesis_provider"] == "local"
    assert captured["allow_live_fallback"] is False
    assert captured["select"] == ("q", 2)
    assert captured["consult"] == ("q", [{"name": "A", "domain": "alpha"}], 0.5)


def test_build_synthesis_backend_supports_anthropic_api_provider():
    backend = build_synthesis_backend(api_provider="anthropic", api_model="claude-sonnet-4-6")

    assert isinstance(backend.client, AnthropicConsultSynthesisClient)
    assert backend.provider == "anthropic"
    assert backend.model == "claude-sonnet-4-6"
    assert backend.allow_live_fallback is False


def test_build_synthesis_backend_defaults_openai_compatibly():
    backend = build_synthesis_backend()

    assert backend.client is None
    assert backend.provider == "openai"
    assert backend.model is None
    assert backend.allow_live_fallback is False


def test_build_synthesis_backend_rejects_api_overrides_for_owned_capacity():
    with pytest.raises(ConsultBackendError, match="API provider/model overrides"):
        build_synthesis_backend(use_local=True, api_provider="anthropic")
