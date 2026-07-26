"""Tests for the `deepr_expert_validate` MCP tool.

Exercises:
- Schema registration in the gateway / tool registry.
- Dispatch from `deepr_expert_validate` -> server.expert_validate.
- Error shape when the expert does not exist.
- Error shape when the validator service raises ExpertValidatorError.
- Successful return shape (matches ValidationResult.to_dict()).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.search.registry import create_default_registry
from deepr.mcp.server import DeeprMCPServer
from deepr.services.expert_validator import ExpertValidatorError, ValidationResult


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


def _stub_result(verdict: str = "pass") -> ValidationResult:
    return ValidationResult(
        expert_name="Test Expert",
        claim="some claim",
        verdict=verdict,  # type: ignore[arg-type]
        confidence=0.8,
        reasoning="ok",
        supporting=[],
        contradicting=[],
        caveats=[],
        model="gpt-5-mini",
    )


class TestExpertValidateTool:
    @pytest.mark.asyncio
    async def test_success_returns_to_dict_payload(self, mock_server) -> None:
        mock_server.store.load = MagicMock(return_value=MagicMock(name="Test Expert"))

        with patch("deepr.services.expert_validator.ExpertValidator") as mock_cls:
            inst = MagicMock()
            inst.validate = AsyncMock(return_value=_stub_result("pass"))
            mock_cls.return_value = inst

            result = await mock_server.expert_validate(
                expert_name="Test Expert",
                claim="some claim",
                budget=0.05,
                allow_metered_api=True,
                confirm_metered_cost=True,
            )

        assert "error_code" not in result
        assert result["verdict"] == "pass"
        assert result["expert_name"] == "Test Expert"
        assert result["model"] == "gpt-5-mini"
        assert "caveats" in result
        assert "supporting" in result
        assert "contradicting" in result

    @pytest.mark.asyncio
    async def test_missing_expert_returns_clean_error(self, mock_server) -> None:
        mock_server.store.load = MagicMock(return_value=None)

        result = await mock_server.expert_validate(
            expert_name="Ghost",
            claim="anything",
            budget=0.05,
            allow_metered_api=True,
            confirm_metered_cost=True,
        )

        assert result.get("error_code") == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_validator_error_becomes_invalid_input(self, mock_server) -> None:
        mock_server.store.load = MagicMock(return_value=MagicMock(name="Test Expert"))

        with patch("deepr.services.expert_validator.ExpertValidator") as mock_cls:
            inst = MagicMock()
            inst.validate = AsyncMock(side_effect=ExpertValidatorError("claim must be non-empty"))
            mock_cls.return_value = inst

            result = await mock_server.expert_validate(
                expert_name="Test Expert",
                claim="",
                budget=0.05,
                allow_metered_api=True,
                confirm_metered_cost=True,
            )

        assert result.get("error_code") == "EXPERT_VALIDATE_INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_passes_model_override(self, mock_server) -> None:
        mock_server.store.load = MagicMock(return_value=MagicMock(name="Test Expert"))

        with patch("deepr.services.expert_validator.ExpertValidator") as mock_cls:
            inst = MagicMock()
            inst.validate = AsyncMock(return_value=_stub_result("pass"))
            mock_cls.return_value = inst

            await mock_server.expert_validate(
                expert_name="Test Expert",
                claim="ok",
                model="gpt-5",
                max_evidence=3,
                budget=0.03,
                allow_metered_api=True,
                confirm_metered_cost=True,
            )

            # The validator should have been constructed with the overrides.
            ctor_kwargs = mock_cls.call_args.kwargs
            assert ctor_kwargs["model"] == "gpt-5"
            assert ctor_kwargs["max_evidence"] == 3
            assert inst.validate.await_args.kwargs["max_cost_per_job"] == 0.03

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
