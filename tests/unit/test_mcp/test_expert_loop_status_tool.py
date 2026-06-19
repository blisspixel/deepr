"""Tests for the `deepr_expert_loop_status` MCP tool."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.experts.loop_runs import LoopRunStatus
from deepr.mcp.expert_loop_status import get_expert_loop_status
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
        schema = create_default_registry().get("deepr_expert_loop_status")
        assert schema is not None
        assert set(schema.input_schema.get("required", [])) == {"expert_name"}
        assert schema.cost_tier == "free"

    def test_blocked_in_read_only(self):
        assert ToolAllowlist(mode=ResearchMode.READ_ONLY).is_allowed("deepr_expert_loop_status") is False

    def test_confirm_required_in_standard(self):
        allow = ToolAllowlist(mode=ResearchMode.STANDARD)
        assert allow.is_allowed("deepr_expert_loop_status") is True
        assert allow.require_confirmation("deepr_expert_loop_status") is True


class TestExpertLoopStatusTool:
    @pytest.mark.asyncio
    async def test_missing_expert(self, mock_server):
        mock_server.store.load = MagicMock(return_value=None)
        out = await get_expert_loop_status(mock_server.store, expert_name="Ghost")
        assert out.get("error_code") == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_invalid_status(self, mock_server):
        mock_server.store.load = MagicMock(return_value=MagicMock(name="Test Expert"))
        out = await get_expert_loop_status(mock_server.store, expert_name="Test Expert", status="bogus")
        assert out.get("error_code") == "INVALID_LOOP_STATUS"

    @pytest.mark.asyncio
    async def test_invalid_limit(self, mock_server):
        out = await get_expert_loop_status(mock_server.store, expert_name="Test Expert", limit=0)
        assert out.get("error_code") == "INVALID_PARAMS"

    @pytest.mark.asyncio
    async def test_returns_loop_runs_with_filters(self, mock_server):
        profile = MagicMock()
        profile.name = "Test Expert"
        mock_server.store.load = MagicMock(return_value=profile)
        run = MagicMock()
        run.to_dict.return_value = {"run_id": "loop_1", "status": "waiting"}

        with patch("deepr.mcp.expert_loop_status.ExpertLoopRunStore") as store_class:
            store = MagicMock()
            store.list_runs.return_value = [run]
            store_class.return_value = store

            out = await get_expert_loop_status(
                mock_server.store,
                expert_name="Test Expert",
                limit=3,
                status="waiting",
                loop_type="sync",
            )

        assert out == {
            "expert_name": "Test Expert",
            "count": 1,
            "runs": [{"run_id": "loop_1", "status": "waiting"}],
        }
        store_class.assert_called_once_with("Test Expert")
        store.list_runs.assert_called_once_with(status=LoopRunStatus.WAITING, loop_type="sync", limit=3)

    @pytest.mark.asyncio
    async def test_dispatch_requires_confirmation(self, mock_server):
        result = await _handle_tools_call(
            mock_server,
            {"name": "deepr_expert_loop_status", "arguments": {"expert_name": "Test Expert"}},
        )
        assert result["isError"] is True
        assert "CONFIRMATION_REQUIRED" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_method_when_approved(self, mock_server):
        profile = MagicMock()
        profile.name = "Test Expert"
        mock_server.store.load = MagicMock(return_value=profile)

        with patch("deepr.mcp.expert_loop_status.ExpertLoopRunStore") as store_class:
            store_class.return_value.list_runs.return_value = []
            result = await _handle_tools_call(
                mock_server,
                {
                    "name": "deepr_expert_loop_status",
                    "arguments": {"expert_name": "Test Expert", "_approved": True},
                },
            )

        assert result["isError"] is False
        payload = json.loads(result["content"][0]["text"])
        assert payload["expert_name"] == "Test Expert"
        assert payload["count"] == 0
