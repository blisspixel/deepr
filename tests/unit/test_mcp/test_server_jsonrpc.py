"""
Tests for MCP Server JSON-RPC protocol handlers.

Validates the full JSON-RPC method dispatch including:
- initialize handshake
- tools/list and tools/call
- resources/list, resources/read, resources/subscribe, resources/unsubscribe
- prompts/list and prompts/get
- Structured error responses
- Legacy method name compatibility
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.server import (
    _LEGACY_METHOD_MAP,
    DeeprMCPServer,
    ToolError,
    _build_tools_list,
    _handle_initialize,
    _handle_prompts_get,
    _handle_prompts_list,
    _handle_resources_list,
    _handle_resources_read,
    _handle_resources_subscribe,
    _handle_resources_unsubscribe,
    _handle_tools_call,
    _handle_tools_list,
    _make_error,
)

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def mock_server():
    """Create a DeeprMCPServer with mocked external dependencies."""
    with (
        patch("deepr.mcp.server.ExpertStore"),
        patch("deepr.mcp.server.load_config", return_value={}),
        patch("deepr.mcp.server.get_resource_handler") as mock_rh,
    ):
        # Set up a real-ish resource handler mock
        handler = MagicMock()
        handler.jobs = MagicMock()
        handler.jobs.list_jobs.return_value = []
        handler.jobs.get_state.return_value = None
        handler.list_resources.return_value = []
        handler.read_resource.return_value = MagicMock(
            success=True,
            data={"test": "data"},
            error=None,
        )
        handler.get_resource_uri_for_job.return_value = {
            "status": "deepr://campaigns/test/status",
            "plan": "deepr://campaigns/test/plan",
            "beliefs": "deepr://campaigns/test/beliefs",
        }
        mock_rh.return_value = handler

        server = DeeprMCPServer()
        yield server


# ------------------------------------------------------------------ #
# ToolError and _make_error
# ------------------------------------------------------------------ #


class TestToolError:
    """Test structured error dataclass."""

    def test_to_dict_minimal(self):
        err = ToolError(error_code="TEST", message="fail")
        d = err.to_dict()
        assert d == {"error_code": "TEST", "message": "fail"}

    def test_to_dict_full(self):
        err = ToolError(
            error_code="BUDGET_EXCEEDED",
            message="Over limit",
            retry_hint="Wait 1h",
            fallback_suggestion="Use cheaper model",
        )
        d = err.to_dict()
        assert d["error_code"] == "BUDGET_EXCEEDED"
        assert d["retry_hint"] == "Wait 1h"
        assert d["fallback_suggestion"] == "Use cheaper model"

    def test_make_error_convenience(self):
        d = _make_error("CODE", "msg", retry_hint="try again")
        assert d["error_code"] == "CODE"
        assert d["message"] == "msg"
        assert d["retry_hint"] == "try again"
        assert "fallback_suggestion" not in d


# ------------------------------------------------------------------ #
# initialize
# ------------------------------------------------------------------ #


class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_returns_capabilities(self, mock_server):
        result = await _handle_initialize(mock_server, {})

        assert result["protocolVersion"] == "2024-11-05"
        assert "tools" in result["capabilities"]
        assert "resources" in result["capabilities"]
        assert "prompts" in result["capabilities"]
        assert result["serverInfo"]["name"] == "deepr-research"

    @pytest.mark.asyncio
    async def test_initialize_resources_support_subscribe(self, mock_server):
        result = await _handle_initialize(mock_server, {})
        assert result["capabilities"]["resources"]["subscribe"] is True


# ------------------------------------------------------------------ #
# tools/list
# ------------------------------------------------------------------ #


class TestToolsList:
    @pytest.mark.asyncio
    async def test_tools_list_gateway_mode(self, mock_server):
        """Default: only return gateway tool for context efficiency."""
        result = await _handle_tools_list(mock_server, {})
        assert "tools" in result
        # Gateway mode returns a small set
        assert len(result["tools"]) >= 1

    @pytest.mark.asyncio
    async def test_tools_list_full_mode(self, mock_server):
        """When _fullList is set, return all tools."""
        result = await _handle_tools_list(mock_server, {"_fullList": True})
        assert "tools" in result
        # Full mode should return more tools than gateway mode
        gateway_result = await _handle_tools_list(mock_server, {})
        assert len(result["tools"]) >= len(gateway_result["tools"])


# ------------------------------------------------------------------ #
# tools/call
# ------------------------------------------------------------------ #


class TestToolsCall:
    @pytest.mark.asyncio
    async def test_call_unknown_tool(self, mock_server):
        result = await _handle_tools_call(mock_server, {"name": "nonexistent_tool", "arguments": {}})
        assert result["isError"] is True
        data = json.loads(result["content"][0]["text"])
        assert data["error_code"] == "TOOL_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_call_deepr_status(self, mock_server):
        result = await _handle_tools_call(mock_server, {"name": "deepr_status", "arguments": {}})
        assert result["isError"] is False
        data = json.loads(result["content"][0]["text"])
        assert data["status"] == "healthy"
        assert "version" in data

    @pytest.mark.asyncio
    async def test_call_deepr_tool_search(self, mock_server):
        result = await _handle_tools_call(
            mock_server,
            {"name": "deepr_tool_search", "arguments": {"query": "research"}},
        )
        assert result["isError"] is False

    @pytest.mark.asyncio
    async def test_call_deepr_cancel_nonexistent(self, mock_server):
        result = await _handle_tools_call(
            mock_server,
            {"name": "deepr_cancel_job", "arguments": {"job_id": "fake"}},
        )
        data = json.loads(result["content"][0]["text"])
        assert data["error_code"] == "JOB_NOT_FOUND"
        assert result["isError"] is True

    @pytest.mark.asyncio
    async def test_call_deepr_check_status_not_found(self, mock_server):
        result = await _handle_tools_call(
            mock_server,
            {"name": "deepr_check_status", "arguments": {"job_id": "missing"}},
        )
        data = json.loads(result["content"][0]["text"])
        assert data["error_code"] == "JOB_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_call_deepr_list_experts(self, mock_server):
        mock_server.store.list_all.return_value = [
            {
                "name": "test",
                "domain": "test",
                "description": "test",
                "stats": {"documents": 0, "conversations": 0},
            }
        ]
        result = await _handle_tools_call(mock_server, {"name": "deepr_list_experts", "arguments": {}})
        assert result["isError"] is False
        data = json.loads(result["content"][0]["text"])
        assert isinstance(data, list)
        assert data[0]["name"] == "test"

    @pytest.mark.asyncio
    async def test_call_tool_result_format(self, mock_server):
        """All tool results should follow the MCP content format."""
        result = await _handle_tools_call(mock_server, {"name": "deepr_status", "arguments": {}})
        assert "content" in result
        assert isinstance(result["content"], list)
        assert result["content"][0]["type"] == "text"
        # Text should be valid JSON
        json.loads(result["content"][0]["text"])


# ------------------------------------------------------------------ #
# resources/list and resources/read
# ------------------------------------------------------------------ #


class TestResources:
    @pytest.mark.asyncio
    async def test_resources_list(self, mock_server):
        mock_server.resource_handler.list_resources.return_value = [
            "deepr://campaigns/j1/status",
            "deepr://experts/e1/profile",
        ]
        result = await _handle_resources_list(mock_server, {})
        assert "resources" in result
        assert len(result["resources"]) == 2
        assert result["resources"][0]["uri"] == "deepr://campaigns/j1/status"

    @pytest.mark.asyncio
    async def test_resources_read_success(self, mock_server):
        result = await _handle_resources_read(mock_server, {"uri": "deepr://campaigns/test/status"})
        assert "contents" in result
        assert result["contents"][0]["uri"] == "deepr://campaigns/test/status"
        # Data should be JSON string
        json.loads(result["contents"][0]["text"])

    @pytest.mark.asyncio
    async def test_resources_read_failure(self, mock_server):
        mock_server.resource_handler.read_resource.return_value = MagicMock(success=False, data=None, error="Not found")
        result = await _handle_resources_read(mock_server, {"uri": "deepr://campaigns/fake/status"})
        text = json.loads(result["contents"][0]["text"])
        assert "error" in text


# ------------------------------------------------------------------ #
# resources/subscribe and resources/unsubscribe
# ------------------------------------------------------------------ #


class TestSubscriptions:
    @pytest.mark.asyncio
    async def test_resources_subscribe(self, mock_server):
        mock_server.resource_handler.handle_subscribe = AsyncMock(
            return_value={"subscription_id": "sub_1", "uri": "deepr://campaigns/t/status"}
        )
        result = await _handle_resources_subscribe(mock_server, {"uri": "deepr://campaigns/t/status"})
        assert result["subscription_id"] == "sub_1"

    @pytest.mark.asyncio
    async def test_resources_unsubscribe(self, mock_server):
        mock_server.resource_handler.handle_unsubscribe = AsyncMock(
            return_value={"success": True, "subscription_id": "sub_1"}
        )
        result = await _handle_resources_unsubscribe(mock_server, {"subscription_id": "sub_1"})
        assert result["success"] is True


# ------------------------------------------------------------------ #
# prompts/list and prompts/get
# ------------------------------------------------------------------ #


class TestPrompts:
    @pytest.mark.asyncio
    async def test_prompts_list(self, mock_server):
        result = await _handle_prompts_list(mock_server, {})
        assert "prompts" in result
        assert isinstance(result["prompts"], list)

    @pytest.mark.asyncio
    async def test_prompts_get_valid(self, mock_server):
        # Get available prompts first
        list_result = await _handle_prompts_list(mock_server, {})
        if list_result["prompts"]:
            name = list_result["prompts"][0]["name"]
            # Build args from required arguments
            args = {}
            for arg in list_result["prompts"][0].get("arguments", []):
                if arg.get("required"):
                    args[arg["name"]] = "test_value"

            result = await _handle_prompts_get(mock_server, {"name": name, "arguments": args})
            assert "description" in result or "error" in result

    @pytest.mark.asyncio
    async def test_prompts_get_nonexistent(self, mock_server):
        result = await _handle_prompts_get(mock_server, {"name": "nonexistent_prompt", "arguments": {}})
        assert "error" in result


# ------------------------------------------------------------------ #
# Legacy method mapping
# ------------------------------------------------------------------ #


class TestLegacyMethods:
    def test_legacy_map_exists(self):
        assert "list_experts" in _LEGACY_METHOD_MAP
        assert "get_expert_info" in _LEGACY_METHOD_MAP
        assert "query_expert" in _LEGACY_METHOD_MAP

    def test_legacy_map_targets_valid_tools(self):
        valid_tools = {
            "deepr_list_experts",
            "deepr_get_expert_info",
            "deepr_query_expert",
            "deepr_expert_manifest",
            "deepr_rank_gaps",
        }
        for legacy, new in _LEGACY_METHOD_MAP.items():
            assert new in valid_tools, f"Legacy '{legacy}' maps to unknown tool '{new}'"


# ------------------------------------------------------------------ #
# _build_tools_list
# ------------------------------------------------------------------ #


class TestBuildToolsList:
    def test_gateway_mode_returns_gateway(self, mock_server):
        tools = _build_tools_list(mock_server, use_gateway=True)
        assert len(tools) >= 1

    def test_full_mode_returns_all(self, mock_server):
        tools = _build_tools_list(mock_server, use_gateway=False)
        names = [t.get("name", "") for t in tools]
        assert "deepr_status" in names or len(tools) >= 3
