"""Tests for the `deepr_expert_validate` MCP tool.

Exercises:
- Schema registration in the gateway / tool registry.
- Dispatch from `deepr_expert_validate` -> server.expert_validate.
- Production metered dispatch remains frozen after a valid contract.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.search.registry import create_default_registry
from deepr.mcp.server import DeeprMCPServer


@pytest.fixture
def mock_server():
    with (
        patch("deepr.mcp.server.ExpertStore"),
        patch("deepr.mcp.server.load_config", return_value={}),
        patch("deepr.mcp.server.get_resource_handler") as mock_rh,
    ):
        rh = MagicMock()
        mock_rh.return_value = rh
        server = DeeprMCPServer()
        yield server


class TestSchemaRegistration:
    def test_tool_appears_in_default_registry(self) -> None:
        reg = create_default_registry()
        names = {t.name for t in reg.all_tools()}
        assert "deepr_expert_validate" in names

    def test_schema_requires_expert_and_claim(self) -> None:
        reg = create_default_registry()
        schema = next(t for t in reg.all_tools() if t.name == "deepr_expert_validate")
        required = set(schema.input_schema.get("required", []))
        props = schema.input_schema.get("properties", {})
        assert {
            "expert_name",
            "claim",
            "budget",
            "allow_metered_api",
            "confirm_metered_cost",
        } <= required
        assert "model" in props
        assert "max_evidence" in props


class TestExpertValidateTool:
    @pytest.mark.asyncio
    async def test_consented_request_still_freezes_production_dispatch(self, mock_server) -> None:
        with patch("deepr.services.expert_validator.ExpertValidator") as mock_cls:
            result = await mock_server.expert_validate(
                expert_name="Test Expert",
                claim="some claim",
                budget=0.05,
                allow_metered_api=True,
                confirm_metered_cost=True,
            )

        assert result.get("error_code") == "METERED_DISPATCH_FROZEN"
        mock_cls.assert_not_called()
        mock_server.store.load.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("allow_metered_api", "confirm_metered_cost"),
        [(False, False), (True, False), (False, True)],
    )
    async def test_explicit_dual_consent_is_required_before_expert_lookup(
        self,
        mock_server,
        allow_metered_api,
        confirm_metered_cost,
    ) -> None:
        result = await mock_server.expert_validate(
            expert_name="Test Expert",
            claim="claim",
            budget=0.05,
            allow_metered_api=allow_metered_api,
            confirm_metered_cost=confirm_metered_cost,
        )

        assert result["error_code"] == "METERED_API_NOT_APPROVED"
        mock_server.store.load.assert_not_called()

    @pytest.mark.asyncio
    async def test_finite_positive_ceiling_is_required_before_expert_lookup(self, mock_server) -> None:
        result = await mock_server.expert_validate(
            expert_name="Test Expert",
            claim="claim",
            allow_metered_api=True,
            confirm_metered_cost=True,
        )

        assert result["error_code"] == "INVALID_BUDGET"
        mock_server.store.load.assert_not_called()
