"""Tests for the `deepr_reflect` MCP tool."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.experts.reflection import ReflectionReport
from deepr.mcp.search.registry import create_default_registry
from deepr.mcp.security.tool_allowlist import ResearchMode, ToolAllowlist
from deepr.mcp.server import DeeprMCPServer


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
    async def test_returns_report(self, mock_server):
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
