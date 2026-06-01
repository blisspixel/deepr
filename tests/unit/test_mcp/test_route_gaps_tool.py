"""Tests for the `deepr_route_gaps` MCP tool."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.core.contracts import ExpertManifest, Gap
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
        names = {t.name for t in create_default_registry().all_tools()}
        assert "deepr_route_gaps" in names

    def test_blocked_in_read_only(self):
        assert ToolAllowlist(mode=ResearchMode.READ_ONLY).is_allowed("deepr_route_gaps") is False


class TestRouteGapsTool:
    @pytest.mark.asyncio
    async def test_missing_expert(self, mock_server):
        mock_server.store.load = MagicMock(return_value=None)
        out = await mock_server.route_gaps(expert_name="Ghost")
        assert out.get("error_code") == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_returns_routes(self, mock_server):
        expert = MagicMock(name="E")
        manifest = ExpertManifest(
            expert_name="E",
            domain="ai",
            gaps=[
                Gap.create(topic="hiring signals and competitive strategy", ev_cost_ratio=2.0),
                Gap.create(topic="academic papers on llms", ev_cost_ratio=1.0),
            ],
        )
        expert.get_manifest.return_value = manifest
        mock_server.store.load = MagicMock(return_value=expert)

        # Pin instrument availability so the result is deterministic.
        with patch("deepr.experts.gap_router.shutil.which", return_value="/usr/bin/x"):
            out = await mock_server.route_gaps(expert_name="E", top_n=5)

        assert out["expert_name"] == "E"
        assert len(out["routes"]) == 2
        assert {r["instrument"] for r in out["routes"]} == {"primr", "distillr"}
