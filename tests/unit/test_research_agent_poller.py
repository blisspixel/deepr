"""Legacy research-agent poller terminal lifecycle regressions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.queue.base import JobStatus
from deepr.research_agent.poller import JobPoller


def _completion_poller() -> JobPoller:
    poller = JobPoller.__new__(JobPoller)
    poller.storage = MagicMock(save_report=AsyncMock(return_value=True))
    poller.queue = MagicMock(
        update_results=AsyncMock(return_value=True),
        update_status=AsyncMock(return_value=True),
    )
    return poller


def _completed_job() -> SimpleNamespace:
    return SimpleNamespace(
        id="legacy-complete",
        prompt="careful research",
        provider_job_id="provider-job",
        provider="openai",
        model="o3-deep-research",
        metadata={"cost_reservation_id": "reservation"},
    )


def _completed_response(*, cost: float | None = 0.42, tokens: int = 1000) -> SimpleNamespace:
    usage = None if cost is None and tokens == 0 else SimpleNamespace(cost=cost, total_tokens=tokens)
    return SimpleNamespace(
        status="completed",
        output=[{"type": "message", "content": [{"type": "output_text", "text": "answer"}]}],
        usage=usage,
    )


@pytest.mark.asyncio
async def test_completion_settles_canonical_cost_before_terminal_success() -> None:
    poller = _completion_poller()
    job = _completed_job()
    response = _completed_response()
    reservation = MagicMock(estimated_cost=0.50)
    order: list[str] = []

    async def update_results(**_kwargs):
        order.append("results")
        return True

    async def update_status(*_args):
        order.append("status")
        return True

    poller.queue.update_results.side_effect = update_results
    poller.queue.update_status.side_effect = update_status
    with (
        patch("deepr.research_agent.poller.restore_research_cost_reservation", return_value=reservation),
        patch(
            "deepr.research_agent.poller.settle_research_cost", side_effect=lambda *_a, **_k: order.append("settle")
        ) as settle,
        patch(
            "deepr.research_agent.poller.reconcile_research_cost_from_ledger",
            side_effect=lambda *_a, **_k: order.append("reconcile") or True,
        ) as reconcile,
    ):
        await poller._handle_completion(job, response)

    settle.assert_called_once_with(
        reservation,
        actual_cost=0.42,
        tokens=1000,
        request_id="provider-job",
        source="research_agent.poller._handle_completion",
    )
    reconcile.assert_called_once_with(reservation, job_id="legacy-complete")
    assert order == ["settle", "results", "reconcile", "status"]
    assert poller.queue.update_results.await_args.kwargs["cost"] == 0.42
    poller.queue.update_status.assert_awaited_once_with("legacy-complete", JobStatus.COMPLETED)


@pytest.mark.asyncio
async def test_completion_without_reservation_records_canonical_legacy_cost() -> None:
    poller = _completion_poller()
    job = _completed_job()
    response = _completed_response(cost=0.25, tokens=600)

    with (
        patch("deepr.research_agent.poller.restore_research_cost_reservation", return_value=None),
        patch("deepr.research_agent.poller.record_unreserved_research_cost", return_value=0.25) as record,
        patch("deepr.research_agent.poller.reconcile_research_cost_from_ledger", return_value=True) as reconcile,
    ):
        await poller._handle_completion(job, response)

    record.assert_called_once_with(
        job_id="legacy-complete",
        provider="openai",
        model="o3-deep-research",
        actual_cost=0.25,
        tokens=600,
        request_id="provider-job",
        source="research_agent.poller._handle_completion",
    )
    reconcile.assert_called_once_with(None, job_id="legacy-complete")
    poller.queue.update_status.assert_awaited_once_with("legacy-complete", JobStatus.COMPLETED)


@pytest.mark.asyncio
async def test_completion_settlement_failure_never_publishes_results_or_terminal_status() -> None:
    poller = _completion_poller()
    reservation = MagicMock(estimated_cost=0.50)

    with (
        patch("deepr.research_agent.poller.restore_research_cost_reservation", return_value=reservation),
        patch("deepr.research_agent.poller.settle_research_cost", side_effect=RuntimeError("ledger unavailable")),
        patch("deepr.research_agent.poller.reconcile_research_cost_from_ledger") as reconcile,
    ):
        await poller._handle_completion(_completed_job(), _completed_response())

    reconcile.assert_not_called()
    poller.queue.update_results.assert_not_awaited()
    poller.queue.update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_missing_ledger_evidence_never_marks_success() -> None:
    poller = _completion_poller()
    reservation = MagicMock(estimated_cost=0.50)

    with (
        patch("deepr.research_agent.poller.restore_research_cost_reservation", return_value=reservation),
        patch("deepr.research_agent.poller.settle_research_cost"),
        patch("deepr.research_agent.poller.reconcile_research_cost_from_ledger", return_value=False),
    ):
        await poller._handle_completion(_completed_job(), _completed_response())

    poller.queue.update_results.assert_awaited_once()
    poller.queue.update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_missing_usage_settles_reserved_ceiling() -> None:
    poller = _completion_poller()
    reservation = MagicMock(estimated_cost=0.50)

    with (
        patch("deepr.research_agent.poller.restore_research_cost_reservation", return_value=reservation),
        patch("deepr.research_agent.poller.settle_research_cost") as settle,
        patch("deepr.research_agent.poller.reconcile_research_cost_from_ledger", return_value=True),
    ):
        await poller._handle_completion(_completed_job(), _completed_response(cost=None, tokens=0))

    settle.assert_called_once_with(
        reservation,
        actual_cost=None,
        tokens=0,
        request_id="provider-job",
        source="research_agent.poller._handle_completion",
    )
    assert poller.queue.update_results.await_args.kwargs["cost"] == 0.50


@pytest.mark.asyncio
async def test_incomplete_provider_result_closes_cost_before_terminal_status() -> None:
    poller = JobPoller.__new__(JobPoller)
    poller.provider = MagicMock(
        get_status=AsyncMock(
            return_value=SimpleNamespace(
                status="incomplete",
                error=None,
            )
        )
    )
    poller.queue = MagicMock(update_status=AsyncMock(return_value=True))
    reservation = MagicMock()
    job = SimpleNamespace(
        id="legacy-incomplete",
        provider_job_id="provider-job",
        provider="openai",
        model="o3-deep-research",
        metadata={"cost_reservation_id": "reservation"},
    )

    with (
        patch("deepr.research_agent.poller.restore_research_cost_reservation", return_value=reservation),
        patch("deepr.research_agent.poller.settle_research_cost") as settle,
        patch("deepr.research_agent.poller.reconcile_research_cost_from_ledger", return_value=True),
    ):
        await poller._check_job_status(job)

    settle.assert_called_once_with(
        reservation,
        actual_cost=None,
        request_id="provider-job",
        source="research_agent.poller._handle_failure",
    )
    poller.queue.update_status.assert_awaited_once_with(
        job_id="legacy-incomplete",
        status=JobStatus.FAILED,
        error="Provider returned an incomplete research result",
    )
