"""Tests for the `deepr_expert_health_check` MCP tool.

Exercises:
- Schema registration in the tool registry (read-side, cost-free).
- Allowlist classification (SENSITIVE: blocked in read-only, confirm otherwise).
- Dispatch from `deepr_expert_health_check` -> server.expert_health_check.
- Error shape when the expert does not exist.
- Successful return shape (matches HealthReport.to_dict()).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.experts.health_check import HealthFinding, HealthReport
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


class TestSchemaRegistration:
    def test_tool_appears_in_default_registry(self) -> None:
        reg = create_default_registry()
        names = {t.name for t in reg.all_tools()}
        assert "deepr_expert_health_check" in names

    def test_schema_requires_only_expert_name(self) -> None:
        reg = create_default_registry()
        schema = next(t for t in reg.all_tools() if t.name == "deepr_expert_health_check")
        assert set(schema.input_schema.get("required", [])) == {"expert_name"}
        assert schema.cost_tier == "free"


class TestAllowlist:
    def test_blocked_in_read_only(self) -> None:
        allow = ToolAllowlist(mode=ResearchMode.READ_ONLY)
        assert allow.is_allowed("deepr_expert_health_check") is False

    def test_confirm_required_in_standard(self) -> None:
        allow = ToolAllowlist(mode=ResearchMode.STANDARD)
        assert allow.is_allowed("deepr_expert_health_check") is True
        assert allow.require_confirmation("deepr_expert_health_check") is True


def _stub_report() -> HealthReport:
    return HealthReport(
        expert_name="Test Expert",
        domain="d",
        status="needs_attention",
        findings=[HealthFinding("freshness", "warning", "stale")],
        actions=[],
    )


class TestHealthCheckTool:
    @pytest.mark.asyncio
    async def test_success_returns_report_dict(self, mock_server) -> None:
        mock_server.store.load = MagicMock(return_value=MagicMock(name="Test Expert"))

        with patch("deepr.experts.health_check.ExpertHealthChecker") as mock_cls:
            inst = MagicMock()
            inst.run.return_value = _stub_report()
            mock_cls.return_value = inst

            result = await mock_server.expert_health_check(expert_name="Test Expert")

        assert "error_code" not in result
        assert result["expert_name"] == "Test Expert"
        assert result["status"] == "needs_attention"
        assert result["findings"][0]["category"] == "freshness"

    @pytest.mark.asyncio
    async def test_missing_expert_returns_clean_error(self, mock_server) -> None:
        mock_server.store.load = MagicMock(return_value=None)
        result = await mock_server.expert_health_check(expert_name="Ghost")
        assert result.get("error_code") == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_dispatch_gated_by_confirmation_in_standard(self, mock_server) -> None:
        # SENSITIVE tool: dispatch in the default STANDARD mode must be blocked
        # pending confirmation rather than silently executing.
        from deepr.mcp.server import _handle_tools_call

        mock_server.store.load = MagicMock(return_value=MagicMock(name="Test Expert"))
        result = await _handle_tools_call(
            mock_server,
            {"name": "deepr_expert_health_check", "arguments": {"expert_name": "Test Expert"}},
        )
        assert result["isError"] is True
        assert "CONFIRMATION_REQUIRED" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_method_when_approved(self, mock_server) -> None:
        # With an explicit approval token the dispatch table entry must reach
        # the server method with the expert_name argument.
        from deepr.mcp.server import _handle_tools_call

        mock_server.store.load = MagicMock(return_value=MagicMock(name="Test Expert"))
        with patch("deepr.experts.health_check.ExpertHealthChecker") as mock_cls:
            inst = MagicMock()
            inst.run.return_value = _stub_report()
            mock_cls.return_value = inst

            result = await _handle_tools_call(
                mock_server,
                {
                    "name": "deepr_expert_health_check",
                    "arguments": {"expert_name": "Test Expert", "_approved": True},
                },
            )

        assert result["isError"] is False
