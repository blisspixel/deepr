"""Coverage tests for ``deepr/worker/poller.py``.

Covers the previously-uncovered cycle paths: start/stop, poll_cycle dispatch,
_check_job_status for completed/failed/in_progress/queued (stuck) jobs,
_handle_completion success + queue-update-failure, _handle_failure persistence.
"""

import asyncio
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from deepr.queue.base import JobStatus
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
    j.metadata = {}
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

    @pytest.mark.asyncio
    async def test_fanout_is_bounded_and_duplicate_job_settles_once(self, poller):
        jobs = [_job(id=f"j{index}", provider_job_id=f"p{index}") for index in range(10)]
        jobs.append(_job(id="j0", provider_job_id="duplicate-provider-id"))
        poller.queue.list_jobs = AsyncMock(return_value=jobs)
        poller._handle_completion = AsyncMock()
        active = 0
        max_active = 0
        first_batch_ready = asyncio.Event()
        release = asyncio.Event()

        async def get_status(_provider_job_id):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            if active == 8:
                first_batch_ready.set()
            try:
                await release.wait()
                return MagicMock(status="completed")
            finally:
                active -= 1

        poller.provider.get_status = get_status
        cycle = asyncio.create_task(poller._poll_cycle())
        await asyncio.wait_for(first_batch_ready.wait(), timeout=1.0)

        assert max_active == 8
        release.set()
        await cycle

        settled_ids = Counter(call.args[0].id for call in poller._handle_completion.await_args_list)
        assert settled_ids == Counter({f"j{index}": 1 for index in range(10)})

    @pytest.mark.asyncio
    async def test_cancellation_clears_in_flight_job_guard(self, poller):
        started = asyncio.Event()

        async def wait_forever(_job):
            started.set()
            await asyncio.Event().wait()

        poller._check_job_status = wait_forever
        task = asyncio.create_task(poller.check_job_status(_job(id="cancelled")))
        await asyncio.wait_for(started.wait(), timeout=1.0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert poller._in_flight_job_ids == set()


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
        resp = MagicMock(status="failed", error="secret\nforged")
        job = _job()
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller._handle_failure = AsyncMock()
        await poller._check_job_status(job)
        poller._handle_failure.assert_awaited_once_with(job, "Provider reported research failure")

    @pytest.mark.asyncio
    async def test_incomplete_routes_to_content_free_terminal_failure(self, poller):
        resp = MagicMock(status="incomplete", error="secret\nforged")
        job = _job()
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller._handle_failure = AsyncMock()

        await poller._check_job_status(job)

        poller._handle_failure.assert_awaited_once_with(job, "Provider returned an incomplete research result")

    @pytest.mark.asyncio
    async def test_cancelled_persists_cancelled_terminal_state(self, poller):
        job = _job()
        poller.provider.get_status = AsyncMock(return_value=MagicMock(status="cancelled"))
        poller._handle_failure = AsyncMock()

        await poller._check_job_status(job)

        poller._handle_failure.assert_awaited_once_with(
            job,
            "Provider reported research cancellation",
            status=JobStatus.CANCELLED,
        )

    @pytest.mark.asyncio
    async def test_unknown_status_remains_active_and_is_logged_without_content(self, poller, caplog):
        poller.provider.get_status = AsyncMock(return_value=MagicMock(status="new\nforged"))
        poller._handle_failure = AsyncMock()

        await poller._check_job_status(_job())

        poller._handle_failure.assert_not_awaited()
        assert "unsupported provider status" in caplog.text
        assert "forged" not in caplog.text

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
        recent = datetime.now(UTC) - timedelta(minutes=2)
        resp = MagicMock(status="queued")
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller._handle_failure = AsyncMock()
        await poller._check_job_status(_job(submitted_at=recent))
        poller._handle_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_queued_stuck_triggers_cancel_and_fail(self, poller):
        old = datetime.now(UTC) - timedelta(minutes=15)
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
    async def test_queued_stuck_cancel_failure_retains_tracking(self, poller):
        old = datetime.now(UTC) - timedelta(minutes=20)
        resp = MagicMock(status="queued")
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller.provider.cancel_job = AsyncMock(side_effect=RuntimeError("no can do"))
        poller._handle_failure = AsyncMock()
        await poller._check_job_status(_job(submitted_at=old))
        poller._handle_failure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_naive_submitted_at_gets_utc(self, poller):
        # Naive datetime - code must add timezone before subtracting.
        naive_old = datetime.now() - timedelta(minutes=20)
        resp = MagicMock(status="queued")
        poller.provider.get_status = AsyncMock(return_value=resp)
        poller.provider.cancel_job = AsyncMock()
        poller._handle_failure = AsyncMock()
        await poller._check_job_status(_job(submitted_at=naive_old))
        poller._handle_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provider_status_exception_swallowed_without_content(self, poller, caplog):
        poller.provider.get_status = AsyncMock(side_effect=RuntimeError("secret\nforged"))
        # Should not raise; logs and exits.
        await poller._check_job_status(_job())

        assert "RuntimeError" in caplog.text
        assert "secret" not in caplog.text


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
    async def test_queue_update_failure_retains_processing_for_retry(self, poller):
        resp = MagicMock()
        resp.output = []
        resp.usage = None
        poller.storage.save_report = AsyncMock()
        poller.queue.update_results = AsyncMock(return_value=False)
        poller._handle_failure = AsyncMock()
        with patch("deepr.experts.cost_safety.get_cost_safety_manager"):
            await poller._handle_completion(_job(), resp)
        poller._handle_failure.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_status_update_failure_retains_processing_for_retry(self, poller):
        resp = MagicMock()
        resp.output = []
        resp.usage = None
        poller.storage.save_report = AsyncMock()
        poller.queue.update_results = AsyncMock(return_value=True)
        poller.queue.update_status = AsyncMock(return_value=False)
        poller._handle_failure = AsyncMock()
        with patch("deepr.experts.cost_safety.get_cost_safety_manager"):
            await poller._handle_completion(_job(), resp)
        poller._handle_failure.assert_not_awaited()


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
