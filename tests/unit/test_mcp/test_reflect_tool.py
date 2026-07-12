"""Tests for the `deepr_reflect` MCP tool."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.experts.reflection import ReflectionReport
from deepr.mcp.search.registry import create_default_registry
from deepr.mcp.security.tool_allowlist import ResearchMode, ToolAllowlist
from deepr.mcp.server import DeeprMCPServer, _handle_tools_call


@pytest.fixture
def mock_server():
    with (
        patch("deepr.mcp.server.ExpertStore"),
        patch("deepr.mcp.server.load_config", return_value={}),
        patch("deepr.mcp.server.get_resource_handler") as mock_rh,
    ):
        mock_rh.return_value = MagicMock()
        yield DeeprMCPServer()


class TestSchemaAndAllowlist:
    def test_registered(self):
        assert "deepr_reflect" in {t.name for t in create_default_registry().all_tools()}

    def test_blocked_in_read_only(self):
        assert ToolAllowlist(mode=ResearchMode.READ_ONLY).is_allowed("deepr_reflect") is False


class TestReflectTool:
    @pytest.mark.asyncio
    async def test_missing_report(self, mock_server):
        with patch("deepr.services.context_index.ContextIndex") as mock_idx:
            mock_idx.return_value.get_report_by_job_id.return_value = None
            mock_idx.return_value.get_report_content.return_value = None
            out = await mock_server.reflect(report_id="missing")
        assert out.get("error_code") == "REPORT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_returns_report(self, mock_server, monkeypatch):
        from deepr.experts import metered_mutation_gate

        monkeypatch.setattr(metered_mutation_gate, "METERED_EXPERT_MUTATIONS_ENABLED", True)
        stub = ReflectionReport(question="q", verdict="accept", overall_score=0.84, dimensions=[], followups=[])
        with (
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.reflection.ReflectionEngine") as mock_engine,
        ):
            mock_idx.return_value.get_report_by_job_id.return_value = MagicMock(prompt="Will X happen?")
            mock_idx.return_value.get_report_content.return_value = "report body"
            inst = MagicMock()
            inst.reflect = AsyncMock(return_value=stub)
            mock_engine.return_value = inst

            out = await mock_server.reflect(report_id="job1", depth=1)

        assert out["verdict"] == "accept"
        assert out["overall_score"] == 0.84

    @pytest.mark.asyncio
    async def test_metered_reflection_fails_closed_before_engine(self, mock_server):
        with (
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.reflection.ReflectionEngine") as mock_engine,
        ):
            mock_idx.return_value.get_report_by_job_id.return_value = MagicMock(prompt="Will X happen?")
            mock_idx.return_value.get_report_content.return_value = "report body"
            out = await mock_server.reflect(report_id="job1", depth=1)

        assert out["error_code"] == "metered_expert_mutation_accounting_unavailable"
        assert out["category"] == "budget"
        assert out["retryable"] is False
        mock_engine.assert_not_called()


class TestReportIdDispatchValidation:
    """Regression: an empty/whitespace report_id must be rejected at the
    dispatch boundary before it can reach ContextIndex's prefix lookup (which
    historically matched an arbitrary report for an empty/wildcard prefix)."""

    @staticmethod
    def _error_code(out: dict) -> str | None:
        assert out.get("isError") is True
        return json.loads(out["content"][0]["text"]).get("error_code")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", ["", "   ", "\t"])
    async def test_reflect_empty_report_id_rejected(self, mock_server, bad):
        out = await _handle_tools_call(
            mock_server,
            {"name": "deepr_reflect", "arguments": {"report_id": bad, "_approved": True}},
        )
        assert self._error_code(out) == "INVALID_PARAMS"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", ["", "   "])
    async def test_absorb_empty_report_id_rejected(self, mock_server, bad):
        out = await _handle_tools_call(
            mock_server,
            {
                "name": "deepr_expert_absorb",
                "arguments": {"expert_name": "X", "report_id": bad, "_approved": True},
            },
        )
        assert self._error_code(out) == "INVALID_PARAMS"
