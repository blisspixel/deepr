"""Legacy research-agent poller terminal lifecycle regressions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deepr.queue.base import JobStatus
from deepr.research_agent.poller import JobPoller


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
