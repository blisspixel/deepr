"""Tests for the DeeprMCPServer tool method implementations.

These methods (``deepr_research``, ``deepr_check_status``, ``deepr_get_result``,
``deepr_agentic_research``, ``deepr_cancel_job``, plus the expert tools) are the
hottest part of the MCP surface. Coverage for them was ~37% before this file.

Each test mocks the external collaborators (cost-safety, provider, orchestrator,
storage, document manager, report generator) so we exercise the dispatcher /
guard logic without touching any network or filesystem.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.mcp.server import DeeprMCPServer
from deepr.mcp.state.job_manager import JobPhase
from deepr.providers.base import ResearchResponse, UsageStats


def _provider_response(status: str = "completed", cost: float = 0.0, metadata: dict | None = None):
    """Build a ResearchResponse like a provider's get_status() returns.

    Providers return a ResearchResponse object (not a dict); the cost lives on
    .usage.cost and the report text is extracted from .output by ReportGenerator.
    """
    return ResearchResponse(
        id="job",
        status=status,  # type: ignore[arg-type]
        usage=UsageStats(cost=cost),
        metadata=metadata or {},
    )


@pytest.fixture
def mock_server():
    """Build a DeeprMCPServer with mocked external collaborators."""
    with (
        patch("deepr.mcp.server.ExpertStore"),
        patch("deepr.mcp.server.load_config", return_value={}),
        patch("deepr.mcp.server.get_resource_handler") as mock_rh,
    ):
        rh = MagicMock()
        rh.jobs = MagicMock()
        rh.jobs.list_jobs.return_value = []
        rh.jobs.get_state.return_value = None
        rh.jobs.create_job = AsyncMock()
        rh.jobs.update_phase = AsyncMock()
        rh.persist_job = MagicMock()
        rh.get_resource_uri_for_job.return_value = {
            "status": "deepr://campaigns/x/status",
            "plan": "deepr://campaigns/x/plan",
            "beliefs": "deepr://campaigns/x/beliefs",
        }
        mock_rh.return_value = rh
        server = DeeprMCPServer()
        yield server


def _state(phase=JobPhase.EXECUTING, cost=0.5, progress=0.3, metadata=None):
    s = MagicMock()
    s.phase = phase
    s.cost_so_far = cost
    s.progress = progress
    s.started_at = datetime(2026, 5, 17, 12, 0, 0)
    s.metadata = metadata or {}
    return s


# ---------------------------------------------------------------------- #
# deepr_research
# ---------------------------------------------------------------------- #


class TestDeeprResearch:
    @pytest.mark.asyncio
    async def test_budget_blocked_by_cost_safety(self, mock_server):
        cost_safety = MagicMock()
        cost_safety.check_operation.return_value = (False, "daily limit reached", None)
        cost_safety.daily_cost = 12.34
        with patch("deepr.experts.cost_safety.get_cost_safety_manager", return_value=cost_safety):
            out = await mock_server.deepr_research(prompt="p", model="o4-mini-deep-research")
        assert out["error_code"] == "BUDGET_EXCEEDED"
        assert "daily limit reached" in out["message"]

    @pytest.mark.asyncio
    async def test_caller_budget_below_estimate(self, mock_server):
        cost_safety = MagicMock()
        cost_safety.check_operation.return_value = (True, "", None)
        with patch("deepr.experts.cost_safety.get_cost_safety_manager", return_value=cost_safety):
            out = await mock_server.deepr_research(
                prompt="p",
                model="o4-mini-deep-research",
                budget=0.01,  # estimate floor is 0.15 for o4-mini
            )
        assert out["error_code"] == "BUDGET_INSUFFICIENT"

    @pytest.mark.asyncio
    async def test_ssrf_blocks_http_file_url(self, mock_server):
        cost_safety = MagicMock()
        cost_safety.check_operation.return_value = (True, "", None)
        # Make SSRF protector reject every URL.
        mock_server.ssrf_protector = MagicMock()
        mock_server.ssrf_protector.validate_url.side_effect = ValueError("Internal address blocked")
        with patch("deepr.experts.cost_safety.get_cost_safety_manager", return_value=cost_safety):
            out = await mock_server.deepr_research(
                prompt="p",
                model="o4-mini",
                files=["http://169.254.169.254/latest/meta-data"],
            )
        assert out["error_code"] == "SSRF_BLOCKED"
        assert "Internal address blocked" in out["message"]

    @pytest.mark.asyncio
    async def test_missing_provider_api_key(self, mock_server):
        cost_safety = MagicMock()
        cost_safety.check_operation.return_value = (True, "", None)
        with (
            patch("deepr.experts.cost_safety.get_cost_safety_manager", return_value=cost_safety),
            patch.object(mock_server, "_get_api_key", return_value=None),
        ):
            out = await mock_server.deepr_research(prompt="p", model="o4-mini", provider="openai")
        assert out["error_code"] == "PROVIDER_NOT_CONFIGURED"

    @pytest.mark.asyncio
    async def test_happy_path_returns_job(self, mock_server):
        cost_safety = MagicMock()
        cost_safety.check_operation.return_value = (True, "", None)
        cost_safety.get_spending_summary.return_value = {
            "daily": {"spent": 1.0, "remaining": 99.0},
            "monthly": {"spent": 1.0},
        }
        orchestrator = MagicMock()
        orchestrator.submit_research = AsyncMock(return_value="job_abc")
        mock_server.resource_handler.jobs.get_state.return_value = _state(metadata={})
        with (
            patch("deepr.experts.cost_safety.get_cost_safety_manager", return_value=cost_safety),
            patch.object(mock_server, "_get_api_key", return_value="k"),
            patch("deepr.mcp.server.create_provider"),
            patch("deepr.mcp.server.create_storage"),
            patch("deepr.mcp.server.DocumentManager"),
            patch("deepr.mcp.server.ReportGenerator"),
            patch("deepr.mcp.server.ResearchOrchestrator", return_value=orchestrator),
        ):
            out = await mock_server.deepr_research(prompt="p", model="o4-mini")
        assert out["job_id"] == "job_abc"
        assert out["status"] == "submitted"
        assert "trace_id" in out
        assert out["daily_remaining"] == 99.0

    @pytest.mark.asyncio
    async def test_unexpected_exception_mapped_to_internal_error(self, mock_server):
        cost_safety = MagicMock()
        cost_safety.check_operation.return_value = (True, "", None)
        with (
            patch("deepr.experts.cost_safety.get_cost_safety_manager", return_value=cost_safety),
            patch.object(mock_server, "_get_api_key", return_value="k"),
            patch("deepr.mcp.server.create_provider", side_effect=RuntimeError("boom")),
        ):
            out = await mock_server.deepr_research(prompt="p", model="o4-mini")
        assert out["error_code"] == "INTERNAL_ERROR"


# ---------------------------------------------------------------------- #
# deepr_check_status
# ---------------------------------------------------------------------- #


class TestCheckStatus:
    @pytest.mark.asyncio
    async def test_job_not_found(self, mock_server):
        mock_server.resource_handler.jobs.get_state.return_value = None
        out = await mock_server.deepr_check_status(job_id="missing")
        assert out["error_code"] == "JOB_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_returns_provider_status_when_active(self, mock_server):
        mock_server.resource_handler.jobs.get_state.return_value = _state()
        prov = MagicMock()
        prov.get_status = AsyncMock(return_value=_provider_response(status="in_progress", cost=0.25))
        mock_server.active_jobs["j1"] = {
            "provider_instance": prov,
            "submitted_at": "2026-05-17T12:00:00",
        }
        out = await mock_server.deepr_check_status("j1")
        assert out["status"] == "in_progress"
        assert out["cost_so_far"] == 0.25

    @pytest.mark.asyncio
    async def test_provider_exception_falls_back_to_state(self, mock_server):
        st = _state(phase=JobPhase.EXECUTING)
        mock_server.resource_handler.jobs.get_state.return_value = st
        prov = MagicMock()
        prov.get_status = AsyncMock(side_effect=RuntimeError("provider down"))
        mock_server.active_jobs["j1"] = {"provider_instance": prov}
        out = await mock_server.deepr_check_status("j1")
        assert out["status"] == JobPhase.EXECUTING.value

    @pytest.mark.asyncio
    async def test_state_only_returns_submitted_when_no_state(self, mock_server):
        # Edge case: in active_jobs cache but no state. Hits final return.
        mock_server.resource_handler.jobs.get_state.return_value = None
        mock_server.active_jobs["j_orphan"] = {"provider_instance": None}
        out = await mock_server.deepr_check_status("j_orphan")
        assert out["status"] == "submitted"


# ---------------------------------------------------------------------- #
# deepr_get_result
# ---------------------------------------------------------------------- #


class TestGetResult:
    @pytest.mark.asyncio
    async def test_unknown_job(self, mock_server):
        out = await mock_server.deepr_get_result(job_id="missing")
        assert out["error_code"] == "JOB_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_provider_lost(self, mock_server):
        mock_server.active_jobs["j1"] = {"provider_instance": None}
        out = await mock_server.deepr_get_result("j1")
        assert out["error_code"] == "PROVIDER_LOST"

    @pytest.mark.asyncio
    async def test_in_progress(self, mock_server):
        prov = MagicMock()
        prov.get_status = AsyncMock(return_value=_provider_response(status="in_progress"))
        mock_server.active_jobs["j1"] = {"provider_instance": prov}
        out = await mock_server.deepr_get_result("j1")
        assert out["status"] == "in_progress"
        assert "Job not yet complete" in out["message"]

    @pytest.mark.asyncio
    async def test_completed_full_report(self, mock_server):
        prov = MagicMock()
        prov.get_status = AsyncMock(
            return_value=_provider_response(status="completed", cost=0.42, metadata={"x": 1, "sources": ["a", "b"]})
        )
        mock_server.active_jobs["j1"] = {"provider_instance": prov}
        # Report text comes from ReportGenerator.extract_text_from_response(response).
        with patch("deepr.mcp.server.ReportGenerator") as rg:
            rg.return_value.extract_text_from_response.return_value = "short report"
            out = await mock_server.deepr_get_result("j1")
        assert out["status"] == "completed"
        assert out["markdown_report"] == "short report"
        assert out["cost_final"] == 0.42
        assert out["sources"] == ["a", "b"]
        assert "j1" not in mock_server.active_jobs  # cleaned up

    @pytest.mark.asyncio
    async def test_completed_truncates_large_report(self, mock_server):
        prov = MagicMock()
        prov.get_status = AsyncMock(return_value=_provider_response(status="completed", cost=1.5))
        big_report = "A" * 200 + "\n## Section\n" + "B" * 200_000
        mock_server.active_jobs["j2"] = {"provider_instance": prov}
        with (
            patch.dict(os.environ, {"DEEPR_MAX_INLINE_CHARS": "1000"}),
            patch("deepr.mcp.server.ReportGenerator") as rg,
        ):
            rg.return_value.extract_text_from_response.return_value = big_report
            out = await mock_server.deepr_get_result("j2")
        assert out["status"] == "completed"
        assert "summary" in out
        assert out["full_report_uri"] == "deepr://reports/j2/final.md"
        assert out["report_length"] == len(big_report)

    @pytest.mark.asyncio
    async def test_exception_wrapped(self, mock_server):
        prov = MagicMock()
        prov.get_status = AsyncMock(side_effect=RuntimeError("boom"))
        mock_server.active_jobs["j1"] = {"provider_instance": prov}
        out = await mock_server.deepr_get_result("j1")
        assert out["error_code"] == "RESULT_FETCH_FAILED"


# ---------------------------------------------------------------------- #
# deepr_agentic_research
# ---------------------------------------------------------------------- #


class TestAgenticResearch:
    @pytest.mark.asyncio
    async def test_no_expert_returns_expert_required(self, mock_server):
        cost_safety = MagicMock()
        cost_safety.check_operation.return_value = (True, "", None)
        with patch("deepr.experts.cost_safety.get_cost_safety_manager", return_value=cost_safety):
            out = await mock_server.deepr_agentic_research(goal="research", budget=2.0)
        assert out["error_code"] == "EXPERT_REQUIRED"

    @pytest.mark.asyncio
    async def test_unknown_expert(self, mock_server):
        cost_safety = MagicMock()
        cost_safety.check_operation.return_value = (True, "", None)
        mock_server.store.load.return_value = None
        with patch("deepr.experts.cost_safety.get_cost_safety_manager", return_value=cost_safety):
            out = await mock_server.deepr_agentic_research(goal="g", expert_name="ghost", budget=2.0)
        assert out["error_code"] == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_blocked_by_cost_safety(self, mock_server):
        cost_safety = MagicMock()
        cost_safety.check_operation.return_value = (False, "blown", None)
        cost_safety.get_spending_summary.return_value = {
            "daily": {"spent": 50, "remaining": 0},
        }
        with patch("deepr.experts.cost_safety.get_cost_safety_manager", return_value=cost_safety):
            out = await mock_server.deepr_agentic_research(goal="g", expert_name="e", budget=1.0)
        assert out["error_code"] == "BUDGET_EXCEEDED"

    @pytest.mark.asyncio
    async def test_agentic_research_is_gated_before_job_or_chat_session(self, mock_server):
        cost_safety = MagicMock()
        cost_safety.check_operation.return_value = (True, "", None)
        cost_safety.get_spending_summary.return_value = {
            "daily": {"spent": 1, "remaining": 49},
        }
        expert = SimpleNamespace(name="myexpert")
        mock_server.store.load.return_value = expert
        mock_server.resource_handler.jobs.get_state.return_value = _state(metadata={})

        with (
            patch("deepr.experts.cost_safety.get_cost_safety_manager", return_value=cost_safety),
            patch(
                "deepr.mcp.server.ExpertChatSession",
                side_effect=AssertionError("metered chat session must not be constructed"),
            ) as session_cls,
        ):
            out = await mock_server.deepr_agentic_research(goal="goal", expert_name="myexpert", budget=2.0)
        assert out["error_code"] == "metered_expert_chat_accounting_unavailable"
        session_cls.assert_not_called()
        mock_server.resource_handler.jobs.create_job.assert_not_awaited()


# ---------------------------------------------------------------------- #
# deepr_cancel_job
# ---------------------------------------------------------------------- #


class TestCancelJob:
    @pytest.mark.asyncio
    async def test_missing(self, mock_server):
        mock_server.resource_handler.jobs.get_state.return_value = None
        out = await mock_server.deepr_cancel_job("none")
        assert out["error_code"] == "JOB_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_already_terminal(self, mock_server):
        mock_server.resource_handler.jobs.get_state.return_value = _state(phase=JobPhase.COMPLETED)
        out = await mock_server.deepr_cancel_job("done")
        assert out["error_code"] == "JOB_ALREADY_TERMINAL"
        assert "completed" in out["message"]

    @pytest.mark.asyncio
    async def test_cancel_running(self, mock_server):
        mock_server.resource_handler.jobs.get_state.return_value = _state(phase=JobPhase.EXECUTING)
        mock_server.active_jobs["job"] = {"provider_instance": MagicMock()}
        out = await mock_server.deepr_cancel_job("job")
        assert out["status"] == "cancelled"
        assert "job" not in mock_server.active_jobs


# ---------------------------------------------------------------------- #
# Expert tools (list / info / query / manifest / rank_gaps)
# ---------------------------------------------------------------------- #


class TestExpertTools:
    @pytest.mark.asyncio
    async def test_list_experts(self, mock_server):
        # list_all() returns ExpertProfile objects (not dicts) - mock the real
        # attribute interface the tool reads.
        mock_server.store.list_all.return_value = [
            SimpleNamespace(
                name="e1",
                domain="d",
                description="desc",
                total_documents=3,
                activity_tracker=SimpleNamespace(conversations=1),
            )
        ]
        out = await mock_server.list_experts()
        assert out[0]["name"] == "e1"
        assert out[0]["documents"] == 3
        assert out[0]["conversations"] == 1

    @pytest.mark.asyncio
    async def test_list_experts_error(self, mock_server):
        mock_server.store.list_all.side_effect = OSError("disk gone")
        out = await mock_server.list_experts()
        assert isinstance(out, list)
        assert out[0]["error_code"] == "EXPERT_LIST_FAILED"

    @pytest.mark.asyncio
    async def test_get_expert_info_not_found(self, mock_server):
        mock_server.store.load.return_value = None
        out = await mock_server.get_expert_info("ghost")
        assert out["error_code"] == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_expert_info_found(self, mock_server):
        expert = MagicMock()
        expert.name = "e1"
        expert.domain = "d"
        expert.description = "desc"
        expert.vector_store_id = "vs"
        expert.total_documents = 5
        # get_expert_info reads conversations/total_cost off the real
        # activity_tracker/budget_manager attributes (ExpertProfile), not a
        # legacy .stats dict - pin those mappings explicitly.
        expert.activity_tracker = SimpleNamespace(conversations=2)
        expert.budget_manager = SimpleNamespace(total_spending=1.23)
        expert.research_jobs = ["j1", "j2"]
        expert.created_at = datetime(2026, 1, 1)
        expert.last_knowledge_refresh = None
        manifest = MagicMock(claim_count=10, open_gap_count=2, avg_confidence=0.8)
        expert.get_manifest.return_value = manifest
        mock_server.store.load.return_value = expert
        out = await mock_server.get_expert_info("e1")
        assert out["name"] == "e1"
        assert out["stats"]["documents"] == 5
        assert out["stats"]["conversations"] == 2
        assert out["stats"]["research_jobs"] == 2
        assert out["stats"]["total_cost"] == 1.23
        assert out["claim_count"] == 10

    @pytest.mark.asyncio
    async def test_get_expert_info_manifest_swallowed(self, mock_server):
        expert = MagicMock()
        expert.name = "e1"
        expert.domain = "d"
        expert.description = "desc"
        expert.vector_store_id = "vs"
        expert.total_documents = 0
        expert.activity_tracker = SimpleNamespace(conversations=0)
        expert.budget_manager = SimpleNamespace(total_spending=0.0)
        expert.research_jobs = []
        expert.created_at = None
        expert.last_knowledge_refresh = None
        expert.get_manifest.side_effect = RuntimeError("manifest unavailable")
        mock_server.store.load.return_value = expert
        out = await mock_server.get_expert_info("e1")
        # Manifest fields absent but core info present (exception swallowed)
        assert out["name"] == "e1"
        assert "claim_count" not in out

    @pytest.mark.asyncio
    async def test_query_expert_not_found(self, mock_server):
        mock_server.store.load.return_value = None
        out = await mock_server.query_expert(expert_name="ghost", question="?")
        assert out["error_code"] == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_query_expert_api_is_gated_before_session_construction(self, mock_server):
        expert = MagicMock()
        mock_server.store.load.return_value = expert
        with patch(
            "deepr.mcp.server.ExpertChatSession",
            side_effect=AssertionError("metered chat session must not be constructed"),
        ) as session_cls:
            out = await mock_server.query_expert("e1", "what?", budget=0.25)
        assert out["error_code"] == "metered_expert_chat_accounting_unavailable"
        assert out["status"] == "blocked"
        assert out["provider_work_dispatched"] is False
        session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_expert_api_provider_model_still_fails_at_capacity_gate(self, mock_server):
        expert = MagicMock()
        mock_server.store.load.return_value = expert
        with patch(
            "deepr.mcp.server.ExpertChatSession",
            side_effect=AssertionError("metered chat session must not be constructed"),
        ) as session_cls:
            out = await mock_server.query_expert(
                "e1",
                "what?",
                backend="api",
                provider="anthropic",
                model="claude-sonnet-4-6",
                budget=1.0,
            )

        assert out["error_code"] == "metered_expert_chat_accounting_unavailable"
        session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_expert_anthropic_api_rejects_agentic_mode(self, mock_server):
        mock_server.store.load.return_value = MagicMock()

        out = await mock_server.query_expert("e1", "what?", backend="api", provider="anthropic", agentic=True)

        assert out["error_code"] == "UNSUPPORTED_AGENTIC_BACKEND"
        assert out["category"] == "validation"

    @pytest.mark.asyncio
    async def test_query_expert_local_backend_uses_readonly_chat_backend(self, mock_server):
        expert = MagicMock()
        mock_server.store.load.return_value = expert
        captured: dict[str, object] = {}

        class FakeBackend:
            provider = "local"
            model = "mistral"
            metered = False
            supports_tools = False
            supports_streaming = False
            supports_prompt_cache = False

            async def complete(self, request):
                captured["request"] = request
                return SimpleNamespace(text="local answer")

        context = {
            "schema_version": "deepr-expert-handoff-v1",
            "kind": "deepr.expert.handoff",
            "summary": {"claim_count": 2, "open_gap_count": 1, "original_idea_count": 0},
        }
        with (
            patch("deepr.mcp.server.ExpertChatSession") as session_cls,
            patch("deepr.mcp.query_expert_tool._build_readonly_query_backend", return_value=FakeBackend()) as builder,
            patch("deepr.mcp.query_expert_tool._compiled_context_for", return_value=context) as compiler,
        ):
            out = await mock_server.query_expert("e1", "what?", backend="local", local_model="mistral")

        assert out["answer"] == "local answer"
        assert out["expert"] == "e1"
        assert out["cost"] == 0.0
        assert out["research_triggered"] == 0
        assert out["backend"] == "local"
        assert out["capacity"]["live_metered_fallback"] is False
        assert out["capacity"]["execution_mode"] == "read_only_chat"
        assert out["capacity"]["provider"] == "local"
        assert out["readonly_chat_artifact"]["schema_version"] == "deepr-query-expert-readonly-v1"
        assert out["readonly_chat_artifact"]["context"]["claim_count"] == 2
        session_cls.assert_not_called()
        builder.assert_called_once_with("local", local_model="mistral", plan=None, plan_model=None)
        compiler.assert_called_once_with(expert)
        request = captured["request"]
        assert request.model == "mistral"
        assert request.tools is None
        assert request.tool_choice is None
        assert "Compiled expert context JSON" in request.messages[1]["content"]

    @pytest.mark.asyncio
    async def test_query_expert_plan_backend_uses_readonly_chat_backend(self, mock_server):
        expert = MagicMock()
        mock_server.store.load.return_value = expert
        captured: dict[str, object] = {}

        class FakeBackend:
            provider = "plan_quota:claude"
            model = "sonnet"
            metered = False
            supports_tools = False
            supports_streaming = False
            supports_prompt_cache = False

            async def complete(self, request):
                captured["request"] = request
                return SimpleNamespace(text="plan answer")

        context = {
            "schema_version": "deepr-expert-handoff-v1",
            "kind": "deepr.expert.handoff",
            "summary": {"claim_count": 0, "open_gap_count": 3, "original_idea_count": 1},
        }
        with (
            patch("deepr.mcp.query_expert_tool._build_readonly_query_backend", return_value=FakeBackend()) as builder,
            patch("deepr.mcp.query_expert_tool._compiled_context_for", return_value=context),
        ):
            out = await mock_server.query_expert(
                "e1",
                "what?",
                backend="plan",
                plan="claude",
                plan_model="sonnet",
            )

        assert out["answer"] == "plan answer"
        assert out["backend"] == "plan"
        assert out["capacity"]["live_metered_fallback"] is False
        assert out["capacity"]["provider"] == "plan_quota:claude"
        assert out["readonly_chat_artifact"]["schema_version"] == "deepr-query-expert-readonly-v1"
        assert out["readonly_chat_artifact"]["context"]["open_gap_count"] == 3
        builder.assert_called_once_with("plan", local_model=None, plan="claude", plan_model="sonnet")
        request = captured["request"]
        assert request.model == "sonnet"
        assert "what?" in request.messages[1]["content"]

    @pytest.mark.asyncio
    async def test_query_expert_plan_backend_rejects_agentic_mode(self, mock_server):
        mock_server.store.load.return_value = MagicMock()

        out = await mock_server.query_expert("e1", "what?", backend="plan", plan="claude", agentic=True)

        assert out["error_code"] == "UNSUPPORTED_AGENTIC_BACKEND"
        assert out["category"] == "validation"

    @pytest.mark.asyncio
    async def test_query_expert_owned_backend_reports_unavailable(self, mock_server):
        mock_server.store.load.return_value = MagicMock()

        with patch(
            "deepr.mcp.query_expert_tool._build_readonly_query_backend",
            side_effect=ValueError("No local model available"),
        ):
            out = await mock_server.query_expert("e1", "what?", backend="local")

        assert out["error_code"] == "QUERY_BACKEND_UNAVAILABLE"
        assert out["category"] == "validation"
        assert out["message"] == "No local model available"

    @pytest.mark.asyncio
    async def test_query_expert_owned_backend_rejects_api_provider_fields(self, mock_server):
        mock_server.store.load.return_value = MagicMock()

        out = await mock_server.query_expert("e1", "what?", backend="local", provider="anthropic")

        assert out["error_code"] == "INVALID_BACKEND"
        assert out["category"] == "validation"
        assert out["message"] == "provider and model are only valid when backend='api'"

    @pytest.mark.asyncio
    async def test_query_expert_api_gate_precedes_legacy_session_errors(self, mock_server):
        expert = MagicMock()
        mock_server.store.load.return_value = expert
        with patch(
            "deepr.mcp.server.ExpertChatSession",
            side_effect=AssertionError("legacy session must not be constructed"),
        ) as session_cls:
            out = await mock_server.query_expert("e1", "q")
        assert out["error_code"] == "metered_expert_chat_accounting_unavailable"
        session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_expert_manifest_not_found(self, mock_server):
        mock_server.store.load.return_value = None
        out = await mock_server.expert_manifest("ghost")
        assert out["error_code"] == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_expert_manifest_returns_dict(self, mock_server):
        expert = MagicMock()
        manifest = MagicMock()
        manifest.to_dict.return_value = {"claims": [], "gaps": []}
        expert.get_manifest.return_value = manifest
        mock_server.store.load.return_value = expert
        out = await mock_server.expert_manifest("e1")
        assert out == {"claims": [], "gaps": []}

    @pytest.mark.asyncio
    async def test_expert_manifest_error_wrapped(self, mock_server):
        expert = MagicMock()
        expert.get_manifest.side_effect = OSError("io")
        mock_server.store.load.return_value = expert
        out = await mock_server.expert_manifest("e1")
        assert out["error_code"] == "MANIFEST_FAILED"

    @pytest.mark.asyncio
    async def test_rank_gaps_not_found(self, mock_server):
        mock_server.store.load.return_value = None
        out = await mock_server.rank_gaps("ghost")
        assert out["error_code"] == "EXPERT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_rank_gaps_returns_top_n(self, mock_server):
        expert = MagicMock()
        gap = MagicMock()
        gap.to_dict.return_value = {"topic": "x", "priority": 5}
        manifest = MagicMock()
        manifest.top_gaps.return_value = [gap]
        manifest.open_gap_count = 3
        expert.get_manifest.return_value = manifest
        mock_server.store.load.return_value = expert
        out = await mock_server.rank_gaps("e1", top_n=1)
        assert out["expert_name"] == "e1"
        assert out["gaps"][0]["topic"] == "x"
        assert out["total_open_gaps"] == 3
