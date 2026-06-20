"""Tests for the `deepr_expert_handoff` MCP tool."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.expert_handoff import get_expert_handoff
from deepr.mcp.search.registry import create_default_registry
from deepr.mcp.security.tool_allowlist import ResearchMode, ToolAllowlist
from deepr.mcp.server import DeeprMCPServer, _handle_tools_call


def _handoff_payload() -> dict:
    return {
        "schema_version": "deepr-expert-handoff-v1",
        "kind": "deepr.expert.handoff",
        "generated_at": "2026-06-20T00:00:00+00:00",
        "contract": {"read_only": True, "cost_usd": 0.0},
        "expert": {"name": "Test Expert", "domain": "testing"},
        "summary": {},
        "manifest": {},
        "expert_state": {},
        "loop_status": {},
        "okf": {},
        "recommended_mcp_tools": [],
    }


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
        schema = create_default_registry().get("deepr_expert_handoff")
        assert schema is not None
        assert set(schema.input_schema.get("required", [])) == {"expert_name"}
        assert schema.cost_tier == "free"

    def test_blocked_in_read_only(self):
        assert ToolAllowlist(mode=ResearchMode.READ_ONLY).is_allowed("deepr_expert_handoff") is False

    def test_confirm_required_in_standard(self):
        allow = ToolAllowlist(mode=ResearchMode.STANDARD)
        assert allow.is_allowed("deepr_expert_handoff") is True
        assert allow.require_confirmation("deepr_expert_handoff") is True


class TestExpertHandoffTool:
    @pytest.mark.asyncio
    async def test_missing_expert(self, mock_server):
        mock_server.store.load = MagicMock(return_value=None)
        out = await get_expert_handoff(mock_server.store, expert_name="Ghost")
        assert out.get("error_code") == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_invalid_limit(self, mock_server):
        out = await get_expert_handoff(mock_server.store, expert_name="Test Expert", max_claims=101)
        assert out.get("error_code") == "INVALID_PARAMS"

    @pytest.mark.asyncio
    async def test_returns_handoff_payload(self, mock_server):
        profile = MagicMock()
        profile.name = "Test Expert"
        mock_server.store.load = MagicMock(return_value=profile)

        with patch("deepr.mcp.expert_handoff.build_expert_handoff") as build_handoff:
            build_handoff.return_value = _handoff_payload()
            out = await get_expert_handoff(
                mock_server.store,
                expert_name="Test Expert",
                max_claims=3,
                max_gaps=2,
                loop_limit=4,
                include_claims=False,
            )

        assert out["schema_version"] == "deepr-expert-handoff-v1"
        assert out["kind"] == "deepr.expert.handoff"
        build_handoff.assert_called_once_with(
            profile,
            max_claims=3,
            max_gaps=2,
            loop_limit=4,
            include_claims=False,
            include_gaps=True,
            include_decisions=False,
        )

    @pytest.mark.asyncio
    async def test_malformed_handoff_payload_fails_closed(self, mock_server):
        profile = MagicMock()
        profile.name = "Test Expert"
        mock_server.store.load = MagicMock(return_value=profile)

        with patch("deepr.mcp.expert_handoff.build_expert_handoff") as build_handoff:
            build_handoff.return_value = {"schema_version": "deepr-expert-handoff-v1"}
            out = await get_expert_handoff(mock_server.store, expert_name="Test Expert")

        assert out["error_code"] == "SCHEMA_VALIDATION_FAILED"
        assert out["schema_version"] == "deepr-expert-handoff-v1"
        assert any("kind" in error for error in out["schema_errors"])

    @pytest.mark.asyncio
    async def test_dispatch_requires_confirmation(self, mock_server):
        result = await _handle_tools_call(
            mock_server,
            {"name": "deepr_expert_handoff", "arguments": {"expert_name": "Test Expert"}},
        )
        assert result["isError"] is True
        assert "CONFIRMATION_REQUIRED" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_method_when_approved(self, mock_server):
        profile = MagicMock()
        profile.name = "Test Expert"
        mock_server.store.load = MagicMock(return_value=profile)

        with patch("deepr.mcp.expert_handoff.build_expert_handoff") as build_handoff:
            build_handoff.return_value = _handoff_payload()
            result = await _handle_tools_call(
                mock_server,
                {
                    "name": "deepr_expert_handoff",
                    "arguments": {"expert_name": "Test Expert", "_approved": True},
                },
            )

        assert result["isError"] is False
        payload = json.loads(result["content"][0]["text"])
        assert payload["schema_version"] == "deepr-expert-handoff-v1"
