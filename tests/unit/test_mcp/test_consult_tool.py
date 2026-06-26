"""Tests for the deepr_consult_experts MCP tool - the harness-native consult path.

The council + consult core are tested elsewhere; here we exercise the MCP handler
(artifact shape, budget guard, error mapping) and registration, with the shared
``run_consult`` core monkeypatched so tests stay pure and $0.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deepr.mcp.server import DeeprMCPServer

_RESULT = {
    "perspectives": [
        {
            "expert_name": "A",
            "domain": "alpha",
            "response": "answer A",
            "confidence": 0.9,
            "cost": 0.01,
            "context": {"source": "belief_store", "selection": "query_overlap", "beliefs_included": 1},
        },
    ],
    "synthesis": "the synthesized answer",
    "agreements": ["both agree"],
    "disagreements": [],
    "total_cost": 0.0212,
}


@pytest.fixture
def server():
    with (
        patch("deepr.mcp.server.ExpertStore"),
        patch("deepr.mcp.server.load_config", return_value={}),
        patch("deepr.mcp.server.get_resource_handler", return_value=MagicMock()),
    ):
        yield DeeprMCPServer()


def test_consult_tool_registered(server):
    names = [t.name for t in server.registry.all_tools()]
    assert "deepr_consult_experts" in names


@pytest.mark.asyncio
async def test_consult_returns_versioned_artifact(server, monkeypatch):
    async def fake(question, experts, max_experts, budget, **_kwargs):
        return _RESULT

    monkeypatch.setattr("deepr.experts.consult.run_consult", fake)
    out = await server.consult_experts(question="how do we harden absorb?", max_experts=2, budget=1.0)
    assert out["schema_version"] == "deepr-consult-v1"
    assert out["answer"] == "the synthesized answer"
    assert out["experts_consulted"] == ["A"]
    assert out["perspectives"][0]["context"]["selection"] == "query_overlap"
    assert out["cost_usd"] == 0.0212


@pytest.mark.asyncio
async def test_consult_local_backend_disables_metered_fallback(server, monkeypatch):
    sentinel_client = object()
    captured: dict[str, object] = {}

    monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: "qwen-local")
    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: sentinel_client)

    async def fake(question, experts, max_experts, budget, **kwargs):
        captured.update(kwargs)
        return {**_RESULT, "total_cost": 0.0}

    monkeypatch.setattr("deepr.experts.consult.run_consult", fake)

    out = await server.consult_experts(question="q", synthesis_backend="local", budget=0.0)

    assert captured["synthesis_client"] is sentinel_client
    assert captured["synthesis_model"] == "qwen-local"
    assert captured["synthesis_provider"] == "local"
    assert captured["allow_live_fallback"] is False
    assert out["capacity"]["live_metered_fallback"] is False
    assert out["capacity"]["synthesis_backend"] == "local"


@pytest.mark.asyncio
async def test_consult_plan_backend_vets_capacity_and_disables_metered_fallback(server, monkeypatch):
    from deepr.backends.waterfall import BACKEND_PLAN_QUOTA, BackendChoice

    captured: dict[str, object] = {}

    class FakeAdapter:
        backend_id = "codex"
        tos_note = ""
        exe = "codex"
        needs_pty = False
        cost_model = type("CostModel", (), {"value": "prepaid"})()
        window_kind = "daily"
        unit_name = "request"

    class FakePlanClient:
        def __init__(self, adapter, *, model=None, operation=""):
            captured["adapter"] = adapter
            captured["plan_model"] = model
            captured["operation"] = operation

    monkeypatch.setattr(
        "deepr.backends.waterfall.choose_plan_quota_backend",
        lambda backend: BackendChoice(BACKEND_PLAN_QUOTA, None, "plan ok", plan_backend_id=backend),
    )
    monkeypatch.setattr("deepr.backends.plan_quota.get_adapter", lambda backend: FakeAdapter())
    monkeypatch.setattr("deepr.backends.plan_quota.PlanQuotaChatClient", FakePlanClient)

    async def fake(question, experts, max_experts, budget, **kwargs):
        captured.update(kwargs)
        return {**_RESULT, "total_cost": 0.0}

    monkeypatch.setattr("deepr.experts.consult.run_consult", fake)

    out = await server.consult_experts(question="q", synthesis_backend="plan", plan="codex", plan_model="fast")

    assert isinstance(captured["synthesis_client"], FakePlanClient)
    assert captured["synthesis_model"] == "fast"
    assert captured["synthesis_provider"] == "plan_quota:codex"
    assert captured["allow_live_fallback"] is False
    assert captured["plan_model"] == "fast"
    assert captured["operation"] == "plan_quota_consult_synthesis"
    assert out["capacity"]["synthesis_backend"] == "plan"
    assert out["capacity"]["provider"] == "plan_quota:codex"


@pytest.mark.asyncio
async def test_consult_rejects_nonpositive_budget(server):
    out = await server.consult_experts(question="q", budget=0)
    assert "INVALID_BUDGET" in str(out)


@pytest.mark.asyncio
async def test_consult_failure_mapped_to_error(server, monkeypatch):
    async def boom(*args, **kwargs):
        raise ValueError("council down")

    monkeypatch.setattr("deepr.experts.consult.run_consult", boom)
    out = await server.consult_experts(question="q", budget=1.0)
    assert "CONSULT_FAILED" in str(out)
