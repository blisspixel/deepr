"""Shared consult core tests."""

from __future__ import annotations

import pytest

from deepr.experts.consult import run_consult
from deepr.experts.profile import ExpertProfile, ExpertStore


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
