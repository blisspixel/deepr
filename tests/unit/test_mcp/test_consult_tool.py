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
        {"expert_name": "A", "domain": "alpha", "response": "answer A", "confidence": 0.9, "cost": 0.01},
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
    async def fake(question, experts, max_experts, budget):
        return _RESULT

    monkeypatch.setattr("deepr.experts.consult.run_consult", fake)
    out = await server.consult_experts(question="how do we harden absorb?", max_experts=2, budget=1.0)
    assert out["schema_version"] == "deepr-consult-v1"
    assert out["answer"] == "the synthesized answer"
    assert out["experts_consulted"] == ["A"]
    assert out["cost_usd"] == 0.0212


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
