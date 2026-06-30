"""Tests for the deepr_consult_experts MCP tool - the harness-native consult path.

The council + consult core are tested elsewhere; here we exercise the MCP handler
(artifact shape, budget guard, error mapping) and registration, with the shared
``run_consult`` core monkeypatched so tests stay pure and $0.
"""

from __future__ import annotations

import json
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
    "requested_budget_usd": 1.0,
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


@pytest.fixture(autouse=True)
def consult_trace_path(monkeypatch, tmp_path):
    path = tmp_path / "consult_traces.jsonl"
    monkeypatch.setenv("DEEPR_CONSULT_TRACE_PATH", str(path))
    return path


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
    assert out["synthesis_status"] == "completed"
    assert out["synthesis_error_type"] == ""
    assert out["experts_consulted"] == ["A"]
    assert out["perspectives"][0]["context"]["selection"] == "query_overlap"
    assert out["cost_usd"] == 0.0212
    assert out["trace"]["schema_version"] == "deepr-consult-trace-v1"
    assert out["collaboration"]["schema_version"] == "deepr-expert-collaboration-v1"
    assert out["collaboration"]["task"]["consult_trace_id"] == out["trace"]["trace_id"]
    assert out["collaboration"]["evidence_packet"]["belief_store_perspective_count"] == 1


@pytest.mark.asyncio
async def test_consult_mcp_writes_trace(server, monkeypatch, consult_trace_path):
    monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: "qwen-local")
    monkeypatch.setattr("deepr.backends.local.ollama_chat_client", lambda: object())

    async def fake(question, experts, max_experts, budget, **_kwargs):
        return {**_RESULT, "synthesis_status": "completed"}

    monkeypatch.setattr("deepr.experts.consult.run_consult", fake)

    out = await server.consult_experts(
        question="q",
        experts=["A"],
        synthesis_backend="local",
        budget=0.0,
    )

    trace = json.loads(consult_trace_path.read_text(encoding="utf-8").strip())
    assert out["trace"]["trace_id"] == trace["trace_id"]
    assert trace["input"]["requested_experts"] == ["A"]
    assert trace["capacity"]["synthesis_backend"] == "local"


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
async def test_consult_api_provider_and_model_pass_to_shared_core(server, monkeypatch):
    captured: dict[str, object] = {}

    async def fake(question, experts, max_experts, budget, **kwargs):
        captured["budget"] = budget
        captured.update(kwargs)
        return {**_RESULT, "total_cost": 0.0}

    monkeypatch.setattr("deepr.experts.consult.run_consult", fake)

    out = await server.consult_experts(
        question="q",
        synthesis_backend="api",
        provider="anthropic",
        model="claude-sonnet-4-6",
        budget=1.0,
    )

    assert captured["budget"] == 1.0
    assert captured["synthesis_provider"] == "anthropic"
    assert captured["synthesis_model"] == "claude-sonnet-4-6"
    assert captured["allow_live_fallback"] is True
    assert out["capacity"]["synthesis_backend"] == "api"
    assert out["capacity"]["provider"] == "anthropic"
    assert out["capacity"]["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_consult_rejects_api_provider_for_owned_capacity(server):
    out = await server.consult_experts(
        question="q",
        synthesis_backend="local",
        provider="anthropic",
        budget=0.0,
    )
    assert out["error_code"] == "INVALID_BACKEND"
    assert "provider and model are only valid" in out["message"]


@pytest.mark.asyncio
async def test_consult_rejects_nonpositive_budget(server):
    out = await server.consult_experts(question="q", budget=0)
    assert "INVALID_BUDGET" in str(out)


@pytest.mark.asyncio
async def test_consult_failure_mapped_to_error(server, monkeypatch, consult_trace_path):
    async def boom(*args, **kwargs):
        raise ValueError("council down")

    monkeypatch.setattr("deepr.experts.consult.run_consult", boom)
    out = await server.consult_experts(question="q", budget=1.0)
    assert "CONSULT_FAILED" in str(out)
    trace = json.loads(consult_trace_path.read_text(encoding="utf-8").strip())
    assert trace["status"] == "failed"
    assert trace["failure"]["error_type"] == "ValueError"
