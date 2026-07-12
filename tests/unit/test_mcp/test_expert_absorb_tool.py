"""Tests for the `deepr_expert_absorb` MCP tool.

Exercises:
- Schema registration (mutating, low cost tier).
- Allowlist classification (WRITE: blocked in read-only, confirm otherwise).
- Dispatch -> server.expert_absorb with report resolution.
- Error shapes: missing expert, missing report.
- Successful return shape (matches AbsorptionResult.to_dict()).
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.experts.report_absorber import AbsorbedClaim, AbsorptionResult, ReportAbsorberCostError
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
    def test_tool_registered(self):
        names = {t.name for t in create_default_registry().all_tools()}
        assert "deepr_expert_absorb" in names

    def test_schema_requires_expert_and_report(self):
        schema = next(t for t in create_default_registry().all_tools() if t.name == "deepr_expert_absorb")
        assert {"expert_name", "report_id"} <= set(schema.input_schema.get("required", []))
        assert "dry_run" in schema.input_schema["properties"]


class TestAllowlist:
    def test_blocked_in_read_only(self):
        assert ToolAllowlist(mode=ResearchMode.READ_ONLY).is_allowed("deepr_expert_absorb") is False

    def test_confirm_required_in_standard(self):
        allow = ToolAllowlist(mode=ResearchMode.STANDARD)
        assert allow.is_allowed("deepr_expert_absorb") is True
        assert allow.require_confirmation("deepr_expert_absorb") is True


def _stub_result(dry_run: bool = False, *, accepted: bool = False) -> AbsorptionResult:
    return AbsorptionResult(
        expert_name="Test Expert",
        report_id="rep1",
        dry_run=dry_run,
        total_candidates=1,
        absorbed=[AbsorbedClaim("Accepted claim", 0.8, "belief-1", "added")] if accepted else [],
        rejected=[],
        estimated_cost=0.03,
        actual_cost=0.0125,
        budget=0.10,
    )


class TestAbsorbTool:
    @pytest.mark.asyncio
    async def test_overlap_is_retryable_before_store_or_model_construction(self, mock_server):
        @contextmanager
        def held_lock(*_args, **_kwargs):
            yield False

        mock_server.store.load = MagicMock(side_effect=AssertionError("store must not be read"))
        with (
            patch("deepr.experts.loop_lock.expert_verb_lock", held_lock),
            patch("deepr.experts.report_absorber.ReportAbsorber") as mock_absorber,
        ):
            result = await mock_server.expert_absorb(expert_name="Busy Expert", report_id="rep1")

        assert result["error_code"] == "ABSORB_OVERLAP_LOCKED"
        assert result["category"] == "conflict"
        assert result["retryable"] is True
        mock_server.store.load.assert_not_called()
        mock_absorber.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_expert(self, mock_server):
        mock_server.store.load = MagicMock(return_value=None)
        result = await mock_server.expert_absorb(expert_name="Ghost", report_id="rep1")
        assert result.get("error_code") == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_missing_report(self, mock_server):
        mock_server.store.load = MagicMock(return_value=MagicMock(name="Test Expert"))
        with patch("deepr.services.context_index.ContextIndex") as mock_idx:
            mock_idx.return_value.get_report_content.return_value = None
            result = await mock_server.expert_absorb(expert_name="Test Expert", report_id="missing")
        assert result.get("error_code") == "REPORT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_paid_dry_run_saves_cost_but_not_refresh(self, mock_server):
        expert = MagicMock(name="Test Expert")
        expert.total_research_cost = 0.0
        expert.last_knowledge_refresh = None
        mock_server.store.load = MagicMock(return_value=expert)
        mock_server.store.save = MagicMock()
        with (
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.report_absorber.ReportAbsorber") as mock_absorber,
        ):
            mock_idx.return_value.get_report_content.return_value = "report body"
            inst = MagicMock()
            inst.absorb = AsyncMock(return_value=_stub_result(dry_run=True))
            mock_absorber.return_value = inst

            result = await mock_server.expert_absorb(expert_name="Test Expert", report_id="rep1", dry_run=True)

        assert result["dry_run"] is True
        assert expert.total_research_cost == 0.0125
        assert expert.last_knowledge_refresh is None
        mock_server.store.save.assert_called_once_with(expert)

    @pytest.mark.asyncio
    async def test_apply_saves_profile(self, mock_server):
        expert = MagicMock(name="Test Expert")
        expert.total_research_cost = 0.0
        mock_server.store.load = MagicMock(return_value=expert)
        mock_server.store.save = MagicMock()
        with (
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.report_absorber.ReportAbsorber") as mock_absorber,
        ):
            mock_idx.return_value.get_report_content.return_value = "report body"
            inst = MagicMock()
            inst.absorb = AsyncMock(return_value=_stub_result(dry_run=False))
            mock_absorber.return_value = inst

            result = await mock_server.expert_absorb(expert_name="Test Expert", report_id="rep1")

        assert result["report_id"] == "rep1"
        mock_server.store.save.assert_called_once()  # applied -> persisted
        assert expert.total_research_cost == 0.0125
        assert inst.absorb.await_args.kwargs["budget"] == 0.10

    @pytest.mark.asyncio
    async def test_accepted_write_advances_both_freshness_fields(self, mock_server):
        expert = MagicMock(name="Test Expert")
        expert.total_research_cost = 0.0
        expert.knowledge_cutoff_date = None
        expert.last_knowledge_refresh = None
        mock_server.store.load = MagicMock(return_value=expert)
        mock_server.store.save = MagicMock()
        accepted = _stub_result(accepted=True)
        with (
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.report_absorber.ReportAbsorber") as mock_absorber,
        ):
            mock_idx.return_value.get_report_content.return_value = "report body"
            mock_absorber.return_value.absorb = AsyncMock(return_value=accepted)

            result = await mock_server.expert_absorb(expert_name="Test Expert", report_id="rep1")

        assert result["absorbed_count"] == 1
        assert expert.knowledge_cutoff_date == accepted.generated_at
        assert expert.last_knowledge_refresh == accepted.generated_at
        mock_server.store.save.assert_called_once_with(expert)

    @pytest.mark.asyncio
    async def test_accounting_failure_is_reported_as_budget_exceeded(self, mock_server):
        expert = MagicMock(name="Test Expert")
        expert.total_research_cost = 0.0
        mock_server.store.load = MagicMock(return_value=expert)
        with (
            patch("deepr.services.context_index.ContextIndex") as mock_idx,
            patch("deepr.experts.report_absorber.ReportAbsorber") as mock_absorber,
        ):
            mock_idx.return_value.get_report_content.return_value = "report body"
            inst = MagicMock()
            inst.absorb = AsyncMock(
                side_effect=ReportAbsorberCostError("canonical settlement unavailable", actual_cost=0.004)
            )
            mock_absorber.return_value = inst

            result = await mock_server.expert_absorb(expert_name="Test Expert", report_id="rep1")

        assert result["error_code"] == "BUDGET_EXCEEDED"
        assert "settlement unavailable" in result["message"]
        assert expert.total_research_cost == 0.004
        mock_server.store.save.assert_called_once_with(expert)
