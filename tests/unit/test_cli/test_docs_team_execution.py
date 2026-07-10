"""Regression coverage for user-facing docs and team execution wiring."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from deepr.cli.commands.docs import _analyze_and_queue
from deepr.cli.commands.team import run_dream_team, team
from deepr.experts.research_reservation_store import ResearchReservationStore
from deepr.observability.cost_ledger import CostLedger
from deepr.providers.base import ResearchResponse, UsageStats
from deepr.queue.base import JobStatus
from deepr.queue.local_queue import SQLiteQueue


@pytest.mark.asyncio
async def test_docs_analysis_uses_real_service_methods_and_configured_queue(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    docs_path = tmp_path / "docs"
    docs_path.mkdir()
    queue_path = tmp_path / "runtime" / "research.db"
    reservation = MagicMock()
    reservation.metadata.return_value = {"cost_reservation_id": "reservation-1"}
    dispatch = AsyncMock(return_value="provider-job")

    with (
        patch(
            "deepr.config.load_config",
            return_value={"queue_db_path": str(queue_path)},
        ),
        patch(
            "deepr.services.doc_reviewer.DocReviewer.review_docs",
            return_value={"sufficient": [], "needs_update": [], "gaps": ["gap"]},
        ) as review,
        patch(
            "deepr.services.research_planner.ResearchPlanner.plan_research",
            return_value=[{"title": "Gap", "prompt": "Research the gap", "type": "analysis"}],
        ) as plan,
        patch("deepr.providers.openai_provider.OpenAIProvider", return_value=MagicMock()),
        patch(
            "deepr.experts.research_cost_gate.reserve_configured_research_cost",
            return_value=(MagicMock(), reservation),
        ),
        patch("deepr.services.research_submission.dispatch_reserved_research", dispatch),
    ):
        await _analyze_and_queue(
            docs_path=str(docs_path),
            scenario="Close documentation gaps",
            max_topics=1,
            planner_model="gpt-5-mini",
            research_model="o4-mini-deep-research",
            auto_execute=True,
        )

    review.assert_called_once_with(scenario="Close documentation gaps")
    plan.assert_called_once()
    assert dispatch.await_count == 1
    assert Path(dispatch.await_args.kwargs["queue"].db_path) == queue_path


def test_team_analyze_constructs_batch_executor_and_executes_campaign(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    queue_path = tmp_path / "queue.db"
    results_path = tmp_path / "reports"
    team_members = [
        {
            "role": "Market Analyst",
            "focus": "Market structure",
            "perspective": "quantitative",
            "rationale": "Ground the decision",
        }
    ]
    campaign = {
        "tasks": {
            1: {
                "title": "Market Analyst",
                "phase": 1,
                "job_id": "job-1",
                "status": "completed",
                "result": "Findings",
                "cost": 0.1,
            }
        }
    }

    with CliRunner().isolated_filesystem():
        with (
            patch(
                "deepr.config.load_config",
                return_value={
                    "queue_db_path": str(queue_path),
                    "results_dir": str(results_path),
                    "api_key": "test-key",
                },
            ),
            patch("deepr.providers.create_provider", return_value=MagicMock()),
            patch("deepr.services.context_builder.OpenAI", return_value=MagicMock()),
            patch("deepr.services.team_architect.TeamArchitect.design_team", return_value=team_members),
            patch(
                "deepr.services.batch_executor.BatchExecutor.execute_campaign",
                new_callable=AsyncMock,
                return_value=campaign,
            ) as execute,
            patch(
                "deepr.services.team_architect.TeamSynthesizer.synthesize_with_conflict_analysis",
                return_value="# Synthesis",
            ) as synthesize,
        ):
            result = CliRunner().invoke(
                team,
                ["analyze", "Should we enter?", "--team-size", "3", "--yes"],
            )

    assert result.exit_code == 0, result.output
    execute.assert_awaited_once()
    synthesize.assert_called_once()


@pytest.mark.asyncio
async def test_dream_team_final_immediate_task_settles_durable_hold(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    queue = SQLiteQueue(str(tmp_path / "team.db"))
    provider = MagicMock(
        submit_research=AsyncMock(return_value="provider-job"),
        get_status=AsyncMock(
            return_value=ResearchResponse(
                id="provider-job",
                status="completed",
                model="o4-mini-deep-research",
                output=[{"type": "message", "content": [{"type": "text", "text": "Findings"}]}],
                usage=UsageStats(input_tokens=100, output_tokens=50, total_tokens=150, cost=0.12),
            )
        ),
    )
    storage = MagicMock(save_report=AsyncMock(return_value=SimpleNamespace(url="report.md")))
    architect = MagicMock()
    architect.design_team.return_value = [
        {
            "role": "Analyst",
            "focus": "Evidence",
            "perspective": "quantitative",
            "rationale": "Ground the answer",
        }
    ]

    with (
        patch(
            "deepr.config.load_config",
            return_value={
                "queue_db_path": str(tmp_path / "team.db"),
                "results_dir": str(tmp_path / "reports"),
                "api_key": "test-key",
                "max_cost_per_job": 5.0,
                "max_daily_cost": 25.0,
                "max_monthly_cost": 200.0,
            },
        ),
        patch("deepr.services.team_architect.TeamArchitect", return_value=architect),
        patch("deepr.providers.create_provider", return_value=provider),
        patch("deepr.storage.create_storage", return_value=storage),
    ):
        results = await run_dream_team("Question", perspectives=1, provider="openai")

    assert len(results) == 1
    persisted = await queue.get_job(results[0]["job_id"])
    assert persisted is not None
    assert Path(queue.db_path) == tmp_path / "team.db"
    assert ResearchReservationStore().active_cost() == 0
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].cost_usd == pytest.approx(0.12)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_cancels", [False, True])
async def test_dream_team_timeout_preserves_cost_and_tracking_contract(
    tmp_path, monkeypatch, provider_cancels: bool
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    queue_path = tmp_path / f"timeout-team-{provider_cancels}.db"
    queue = SQLiteQueue(str(queue_path))
    provider = MagicMock(
        submit_research=AsyncMock(return_value="provider-pending"),
        get_status=AsyncMock(
            return_value=ResearchResponse(
                id="provider-pending",
                status="in_progress",
                model="o4-mini-deep-research",
            )
        ),
        cancel_job=AsyncMock(return_value=provider_cancels),
    )
    architect = MagicMock()
    architect.design_team.return_value = [
        {
            "role": "Analyst",
            "focus": "Evidence",
            "perspective": "quantitative",
            "rationale": "Ground the answer",
        }
    ]

    with (
        patch(
            "deepr.config.load_config",
            return_value={
                "queue_db_path": str(queue_path),
                "results_dir": str(tmp_path / "reports"),
                "api_key": "test-key",
                "max_cost_per_job": 5.0,
                "max_daily_cost": 25.0,
                "max_monthly_cost": 200.0,
            },
        ),
        patch("deepr.services.team_architect.TeamArchitect", return_value=architect),
        patch("deepr.providers.create_provider", return_value=provider),
        patch("deepr.storage.create_storage", return_value=MagicMock()),
        patch("deepr.cli.commands.team.TEAM_POLL_TIMEOUT_SECONDS", 0),
    ):
        results = await run_dream_team("Question", perspectives=1, provider="openai")

    jobs = await queue.list_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.provider_job_id == "provider-pending"
    reservation_id = str(job.metadata["cost_reservation_id"])
    store = ResearchReservationStore()
    events = CostLedger().get_events()
    if provider_cancels:
        assert results == []
        assert job.status == JobStatus.CANCELLED
        assert not store.is_active(reservation_id)
        assert len(events) == 1
        assert events[0].cost_usd > 0
    else:
        assert results[0]["status"] == "pending"
        assert job.status == JobStatus.PROCESSING
        assert store.is_active(reservation_id)
        assert events == []
        store.refund(reservation_id)
