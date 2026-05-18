"""Coverage tests for ``deepr/worker/poller.py``.

Covers the previously-uncovered cycle paths: start/stop, poll_cycle dispatch,
_check_job_status for completed/failed/in_progress/queued (stuck) jobs,
_handle_completion success + queue-update-failure, _handle_failure persistence.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.worker.poller import JobPoller


@pytest.fixture
def poller():
    with (
        patch("deepr.worker.poller.load_config", return_value={}),
        patch("deepr.worker.poller.create_queue"),
        patch("deepr.worker.poller.create_storage"),
        patch("deepr.worker.poller.create_provider"),
        patch("deepr.worker.poller.CostController"),
    ):
        p = JobPoller(poll_interval=0)
        p.queue = MagicMock()
        p.storage = MagicMock()
        p.provider = MagicMock()
        p.cost_controller = MagicMock()
        return p


def _job(
    *,
    id="j1",
    provider_job_id="prov_1",
    submitted_at=None,
):
    j = MagicMock()
    j.id = id
    j.provider_job_id = provider_job_id
    j.submitted_at = submitted_at
    j.prompt = "p"
    j.model = "m"
    j.provider = "openai"
    return j


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_runs_until_stopped(self, poller):
        # Poll cycle is a no-op; one tick then stop.
        poller._poll_cycle = AsyncMock()

        async def _stop_after_tick(*_a, **_k):
            poller.running = False

        with patch("asyncio.sleep", new=_stop_after_tick):
            await poller.start()
        assert poller._poll_cycle.await_count >= 1

    @pytest.mark.asyncio
    async def test_start_swallows_cycle_errors(self, poller):
        poller._poll_cycle = AsyncMock(side_effect=RuntimeError("transient"))

        async def _stop_after_tick(*_a, **_k):
            poller.running = False

        with patch("asyncio.sleep", new=_stop_after_tick):
            await poller.start()  # must not raise

    @pytest.mark.asyncio
    async def test_stop_sets_flag(self, poller):
        poller.running = True
        await poller.stop()
        assert poller.running is False


class TestPollCycle:
    @pytest.mark.asyncio
    async def test_empty_cycle_returns(self, poller):
        poller.queue.list_jobs = AsyncMock(return_value=[])
        await poller._poll_cycle()
        poller.queue.list_jobs.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatches_each_job(self, poller):
        poller.queue.list_jobs = AsyncMock(return_value=[_job(id="a"), _job(id="b")])
        poller._check_job_status = AsyncMock()
        await poller._poll_cycle()
        assert poller._check_job_status.await_count == 2

    @pytest.mark.asyncio
    async def test_per_job_exception_continues(self, poller):
        poller.queue.list_jobs = AsyncMock(return_value=[_job(id="a"), _job(id="b")])
        # First job raises, second still gets called.
        calls = []

        async def fake(j):
            calls.append(j.id)
            if j.id == "a":
                raise RuntimeError("boom")

        poller._check_job_status = fake
        await poller._poll_cycle()
        assert calls == ["a", "b"]


class TestCheckJobStatus:
    @pytest.mark.asyncio
    async def test_no_provider_id_skipped(self, poller):
        poller.provider.get_status = AsyncMock()
        await poller._check_job_status(_job(provider_job_id=None))
        poller.provider.get_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_completed_routes_to_completion_handler(self, poller):
        resp = MagicMock(status="completed")
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller._handle_completion = AsyncMock()
        await poller._check_job_status(_job())
        poller._handle_completion.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_routes_to_failure_handler(self, poller):
        resp = MagicMock(status="failed", error="oops")
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller._handle_failure = AsyncMock()
        await poller._check_job_status(_job())
        poller._handle_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_in_progress_is_no_op(self, poller):
        resp = MagicMock(status="in_progress")
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller._handle_completion = AsyncMock()
        poller._handle_failure = AsyncMock()
        await poller._check_job_status(_job())
        poller._handle_completion.assert_not_called()
        poller._handle_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_queued_short_time_logs_only(self, poller):
        recent = datetime.now(timezone.utc) - timedelta(minutes=2)
        resp = MagicMock(status="queued")
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller._handle_failure = AsyncMock()
        await poller._check_job_status(_job(submitted_at=recent))
        poller._handle_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_queued_stuck_triggers_cancel_and_fail(self, poller):
        old = datetime.now(timezone.utc) - timedelta(minutes=15)
        resp = MagicMock(status="queued")
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller.provider.cancel_job = AsyncMock()
        poller._handle_failure = AsyncMock()
        await poller._check_job_status(_job(submitted_at=old))
        poller.provider.cancel_job.assert_awaited_once_with("prov_1")
        poller._handle_failure.assert_awaited_once()
        # Failure reason mentions auto-cancellation
        msg = poller._handle_failure.await_args.args[1]
        assert "auto-cancelled" in msg

    @pytest.mark.asyncio
    async def test_queued_stuck_cancel_failure_still_marks_failed(self, poller):
        old = datetime.now(timezone.utc) - timedelta(minutes=20)
        resp = MagicMock(status="queued")
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller.provider.cancel_job = AsyncMock(side_effect=RuntimeError("no can do"))
        poller._handle_failure = AsyncMock()
        await poller._check_job_status(_job(submitted_at=old))
        # Failure still recorded even though cancel raised.
        poller._handle_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_naive_submitted_at_gets_utc(self, poller):
        # Naive datetime — code must add timezone before subtracting.
        naive_old = datetime.now() - timedelta(minutes=20)
        resp = MagicMock(status="queued")
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller.provider.cancel_job = AsyncMock()
        poller._handle_failure = AsyncMock()
        await poller._check_job_status(_job(submitted_at=naive_old))
        poller._handle_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provider_status_exception_swallowed(self, poller):
        poller.provider.get_status = AsyncMock(side_effect=RuntimeError("net"))
        # Should not raise; logs and exits.
        await poller._check_job_status(_job())


class TestHandleCompletion:
    @pytest.mark.asyncio
    async def test_writes_report_and_marks_completed(self, poller):
        resp = MagicMock()
        block = {"type": "message", "content": [{"text": "answer body"}]}
        resp.output = [block]
        resp.usage = MagicMock(cost=0.42, total_tokens=1000)
        poller.storage.save_report = AsyncMock()
        poller.queue.update_results = AsyncMock(return_value=True)
        poller.queue.update_status = AsyncMock(return_value=True)
        with patch("deepr.experts.cost_safety.get_cost_safety_manager") as cs:
            cs.return_value.record_cost = MagicMock()
            await poller._handle_completion(_job(), resp)
        poller.storage.save_report.assert_awaited_once()
        poller.queue.update_status.assert_awaited()

    @pytest.mark.asyncio
    async def test_queue_update_failure_promotes_to_failure(self, poller):
        resp = MagicMock()
        resp.output = []
        resp.usage = None
        poller.storage.save_report = AsyncMock()
        poller.queue.update_results = AsyncMock(return_value=False)
        poller._handle_failure = AsyncMock()
        with patch("deepr.experts.cost_safety.get_cost_safety_manager"):
            await poller._handle_completion(_job(), resp)
        poller._handle_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_status_update_failure_promotes_to_failure(self, poller):
        resp = MagicMock()
        resp.output = []
        resp.usage = None
        poller.storage.save_report = AsyncMock()
        poller.queue.update_results = AsyncMock(return_value=True)
        poller.queue.update_status = AsyncMock(return_value=False)
        poller._handle_failure = AsyncMock()
        with patch("deepr.experts.cost_safety.get_cost_safety_manager"):
            await poller._handle_completion(_job(), resp)
        poller._handle_failure.assert_awaited_once()


class TestHandleFailure:
    @pytest.mark.asyncio
    async def test_persists_failed_status(self, poller):
        poller.queue.update_status = AsyncMock(return_value=True)
        await poller._handle_failure(_job(), "broke")
        poller.queue.update_status.assert_awaited_once()
        kwargs = poller.queue.update_status.await_args.kwargs
        assert kwargs["error"] == "broke"

    @pytest.mark.asyncio
    async def test_persistence_failure_swallowed(self, poller):
        poller.queue.update_status = AsyncMock(return_value=False)
        # Must not raise even if queue persist fails.
        await poller._handle_failure(_job(), "broke")

    @pytest.mark.asyncio
    async def test_internal_exception_swallowed(self, poller):
        poller.queue.update_status = AsyncMock(side_effect=RuntimeError("db gone"))
        await poller._handle_failure(_job(), "broke")
