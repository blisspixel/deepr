"""Tests for deepr.backends.plan_quota.client - the CLI-as-chat-backend shim.

A fake runner stands in for the vendor subprocess, so these run with no CLI
installed and no network. Quota and cost ledgers are written to explicit tmp
paths and asserted.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest

from deepr.backends.fresh_context import FreshContext, FreshContextConfig, FreshSource
from deepr.backends.plan_quota.adapters import get_adapter
from deepr.backends.plan_quota.attempt_accounting import AttemptAccountingStatus
from deepr.backends.plan_quota.cli_runner import CliResult
from deepr.backends.plan_quota.client import (
    PlanQuotaChatClient,
    PlanQuotaError,
    PlanQuotaExhausted,
    _safe_cli_error_summary,
    make_plan_quota_research_fn,
    probe_plan_quota,
)
from deepr.backends.quota_ledger import QuotaEventType, QuotaLedger
from deepr.observability.cost_ledger import CostLedger


def _runner(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int | None = 0,
    timed_out: bool = False,
    launch_error: str = "",
    runtime_error: str = "",
):
    calls: list[list[str]] = []
    envs: list[dict[str, str] | None] = []
    stdins: list[str | None] = []

    async def fake(argv, **kwargs):
        calls.append(argv)
        envs.append(kwargs.get("env"))
        stdins.append(kwargs.get("stdin"))
        return CliResult(
            returncode,
            stdout,
            stderr,
            timed_out,
            launch_error,
            5,
            runtime_error=runtime_error,
        )

    fake.calls = calls  # type: ignore[attr-defined]
    fake.envs = envs  # type: ignore[attr-defined]
    fake.stdins = stdins  # type: ignore[attr-defined]
    return fake


def test_safe_error_summary_redacts_short_prompt_echo_and_bearer_secret():
    summary = _safe_cli_error_summary(
        "Prompt: xy7\nAuthorization: Bearer private-token-value\nfatal: login required",
        prompt="xy7",
    )

    assert "xy7" not in summary
    assert "private-token-value" not in summary
    assert "[REDACTED]" in summary
    assert "fatal: login required" in summary


def test_safe_error_summary_keeps_terminal_cause_before_footer_lines():
    summary = _safe_cli_error_summary(
        "\n".join(
            [
                "banner",
                "ERROR: selected model is unavailable",
                "request id: 123",
                "elapsed: 4s",
                "tokens: 0",
                "session closed",
            ]
        )
    )

    assert "selected model is unavailable" in summary
    assert "session closed" in summary
    assert "banner" not in summary


class TestResearchFn:
    async def test_returns_answer_and_zero_cost(self, tmp_path):
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(stdout="the answer"),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        result = await fn("what changed?", 5.0)
        assert result["answer"] == "the answer"
        assert result["cost"] == 0.0
        assert result["backend"] == "plan_quota:codex"

    async def test_records_quota_and_cost_event(self, tmp_path):
        qpath, cpath = tmp_path / "q.jsonl", tmp_path / "c.jsonl"
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(stdout="ok"),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )
        await fn("q", 1.0)
        quota = QuotaLedger(qpath).get_events()
        assert len(quota) == 1
        assert quota[0].event_type == QuotaEventType.USAGE_OBSERVED
        assert quota[0].backend_id == "codex"
        assert quota[0].units_used == 1.0
        cost = CostLedger(cpath).get_events()
        assert len(cost) == 1
        assert cost[0].cost_usd == 0.0
        assert cost[0].provider == "plan_quota:codex"
        assert cost[0].metadata["backend_id"] == "codex"

    async def test_exhaustion_is_reported_and_recorded(self, tmp_path):
        qpath = tmp_path / "q.jsonl"
        cpath = tmp_path / "c.jsonl"
        # Codex streams status/errors to stderr; a real limit notice lands there,
        # not in the stdout answer body.
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(stderr="Error: usage_limit_reached"),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )
        result = await fn("q", 1.0)
        assert result["answer"] == ""
        assert result.get("quota_exhausted") is True
        events = QuotaLedger(qpath).get_events()
        assert events[0].event_type == QuotaEventType.EXHAUSTED
        costs = CostLedger(cpath).get_events()
        assert len(costs) == 1
        assert costs[0].metadata["outcome"] == "exhausted"
        assert costs[0].metadata["quota_units"] is None

    async def test_exhaustion_records_reset_time_when_stated(self, tmp_path):
        qpath = tmp_path / "q.jsonl"
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(stderr="usage_limit_reached. Try again in 1h 30m."),
            quota_ledger_path=qpath,
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        result = await fn("q", 1.0)
        assert result.get("quota_exhausted") is True
        event = QuotaLedger(qpath).get_events()[0]
        assert event.event_type == QuotaEventType.EXHAUSTED
        assert event.reset_at is not None

    async def test_launch_error_is_reported_not_raised(self, tmp_path):
        qpath, cpath = tmp_path / "q.jsonl", tmp_path / "c.jsonl"
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(
                stderr="usage_limit_reached",
                launch_error="not found",
                returncode=None,
            ),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )
        result = await fn("q", 1.0)
        assert result["answer"] == ""
        assert "error" in result
        assert QuotaLedger(qpath).get_events() == []
        event = CostLedger(cpath).get_events()[0]
        assert event.metadata["outcome"] == "launch_error"
        assert event.metadata["vendor_dispatched"] is False

    async def test_scratch_failure_is_not_classified_as_vendor_dispatch(self, monkeypatch, tmp_path):
        def fail_scratch():
            raise PermissionError(tmp_path / "private-scratch")

        monkeypatch.setattr(
            "deepr.backends.plan_quota.cli_runner._scratch_dir",
            fail_scratch,
        )
        qpath, cpath = tmp_path / "q.jsonl", tmp_path / "c.jsonl"
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )

        with pytest.raises(PlanQuotaError) as exc_info:
            await client.chat.completions.create(
                model="x",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert str(tmp_path) not in str(exc_info.value)
        assert QuotaLedger(qpath).get_events() == []
        cost = CostLedger(cpath).get_events()[0]
        assert cost.metadata["outcome"] == "launch_error"
        assert cost.metadata["vendor_dispatched"] is False

    async def test_timeout_is_reported(self, tmp_path):
        qpath, cpath = tmp_path / "q.jsonl", tmp_path / "c.jsonl"
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(returncode=None, timed_out=True),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )
        result = await fn("q", 1.0)
        assert result["answer"] == ""
        assert "timed out" in result["error"]
        quota = QuotaLedger(qpath).get_events()[0]
        assert quota.event_type == QuotaEventType.ATTEMPT_OBSERVED
        assert quota.units_used is None
        assert quota.metadata["outcome"] == "timeout"
        costs = CostLedger(cpath).get_events()
        assert len(costs) == 1
        assert costs[0].metadata["outcome"] == "timeout"
        assert costs[0].cost_usd == 0.0

    async def test_runtime_error_is_path_safe_and_accounted_as_dispatched(self, tmp_path):
        qpath, cpath = tmp_path / "q.jsonl", tmp_path / "c.jsonl"
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(
                stderr="usage_limit_reached",
                returncode=None,
                runtime_error="runner failed (PermissionError)",
            ),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )

        result = await fn("q", 1.0)

        assert result["answer"] == ""
        assert result["error"].endswith("runner failed (PermissionError)")
        quota = QuotaLedger(qpath).get_events()
        costs = CostLedger(cpath).get_events()
        assert quota[0].event_type == QuotaEventType.ATTEMPT_OBSERVED
        assert quota[0].metadata["outcome"] == "runner_error"
        assert costs[0].metadata["outcome"] == "runner_error"
        assert costs[0].idempotency_key == quota[0].idempotency_key

    async def test_nonzero_exit_is_reported(self, tmp_path):
        qpath, cpath = tmp_path / "q.jsonl", tmp_path / "c.jsonl"
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(stderr="boom", returncode=2),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )
        result = await fn("q", 1.0)
        assert "error" in result and result["answer"] == ""
        assert QuotaLedger(qpath).get_events()[0].event_type == QuotaEventType.ATTEMPT_OBSERVED
        assert CostLedger(cpath).get_events()[0].metadata["outcome"] == "nonzero_exit"

    async def test_nonzero_exit_surfaces_redacted_terminal_cause(self, tmp_path):
        private_prompt = "private customer request alpha beta gamma 123456789"
        stderr = "\n".join(
            [
                *(f"Codex banner and progress line {i}" for i in range(20)),
                f"Prompt: {private_prompt}",
                "fatal: requested model is unavailable; api_key=sk-proj-supersecret123456",
            ]
        )
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(stderr=stderr, returncode=1),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )

        result = await fn(private_prompt, 1.0)

        assert "requested model is unavailable" in result["error"]
        assert "[REDACTED]" in result["error"]
        assert "Codex banner and progress line 0" not in result["error"]
        assert private_prompt not in result["error"]
        assert "supersecret" not in result["error"]

    async def test_empty_output_is_error(self, tmp_path, monkeypatch):
        from deepr.backends.plan_quota import antigravity_transcript

        monkeypatch.setattr(antigravity_transcript, "recover_answer", lambda brain, since: None)
        qpath, cpath = tmp_path / "q.jsonl", tmp_path / "c.jsonl"
        fn = make_plan_quota_research_fn(
            get_adapter("antigravity"),
            runner=_runner(stdout="   "),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )
        result = await fn("q", 1.0)
        assert "error" in result
        assert "no output" in result["error"]
        assert QuotaLedger(qpath).get_events()[0].event_type == QuotaEventType.ATTEMPT_OBSERVED
        assert CostLedger(cpath).get_events()[0].metadata["outcome"] == "empty_output"

    async def test_context_builder_injected(self, tmp_path):
        runner = _runner(stdout="ans")

        async def context_builder(query):
            assert query == "q"
            return "## Fresh retrieval context\n[S1] x"

        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=runner,
            context_builder=context_builder,
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        result = await fn("q", 1.0)
        assert result["answer"] == "ans"
        prompt = runner.calls[0][-1]
        assert prompt == "-"
        assert "Fresh retrieval context" in runner.stdins[0]

    async def test_passes_prior_source_pack_to_context_builder_when_supported(self, tmp_path):
        runner = _runner(stdout="ans")
        prior_pack = {"sources": [{"url": "https://example.com", "etag": '"abc"'}]}
        seen = {}

        async def context_builder(query, *, prior_source_pack=None):
            seen["query"] = query
            seen["prior_source_pack"] = prior_source_pack
            return "ctx"

        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=runner,
            context_builder=context_builder,
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        result = await fn("q", 1.0, prior_source_pack=prior_pack)

        assert result["answer"] == "ans"
        assert seen == {"query": "q", "prior_source_pack": prior_pack}

    async def test_under_ready_context_skips_plan_cli_and_preserves_evidence(self, tmp_path):
        runner = _runner(stdout="must not be used")
        context = FreshContext(
            query="search-discovered topic",
            generated_at="2026-07-11T00:00:00Z",
            prompt_config=FreshContextConfig(),
            sources=(
                FreshSource(
                    title="Only fetched source",
                    url="https://example.com/only",
                    content="One fetched page.",
                ),
            ),
        )

        async def context_builder(query):
            assert query == "concise topic"
            return context

        quota_path = tmp_path / "q.jsonl"
        cost_path = tmp_path / "c.jsonl"
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=runner,
            context_builder=context_builder,
            quota_ledger_path=quota_path,
            cost_ledger_path=cost_path,
        )
        result = await fn("full answer prompt", 1.0, retrieval_query="concise topic")

        assert runner.calls == []
        assert not quota_path.exists()
        assert not cost_path.exists()
        assert result["backend"] == "plan_quota:codex"
        assert result["error_code"] == "fresh_context_not_ready"
        assert result["retryable"] is True
        assert result["no_metered_fallback"] is True
        assert result["context_preflight"]["ready_source_count"] == 1
        assert result["source_pack"]["source_count"] == 1
        assert "No generation backend was called" in result["error"]

    async def test_plan_child_env_drops_metered_api_keys(self, tmp_path):
        runner = _runner(stdout="ans")
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=runner,
            env={"OPENAI_API_KEY": "sk-xxx", "PATH": "x"},
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )

        await fn("q", 1.0)

        assert runner.envs[0] == {"PATH": "x"}

    async def test_codex_prompt_is_sent_over_stdin(self, tmp_path):
        runner = _runner(stdout="ans")
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=runner,
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )

        await fn("q", 1.0)

        assert runner.calls[0][-1] == "-"
        assert "q" in (runner.stdins[0] or "")


class TestChatShim:
    @pytest.mark.parametrize("timeout", [True, 0, -1, float("nan"), float("inf")])
    def test_invalid_timeout_fails_before_runner_or_ledger_setup(self, tmp_path, timeout):
        runner = _runner(stdout="must not run")

        with pytest.raises(PlanQuotaError, match="finite positive"):
            PlanQuotaChatClient(
                get_adapter("codex"),
                runner=runner,
                timeout=timeout,
                quota_ledger_path=tmp_path / "q.jsonl",
                cost_ledger_path=tmp_path / "c.jsonl",
            )

        assert runner.calls == []
        assert not (tmp_path / "q.jsonl").exists()
        assert not (tmp_path / "c.jsonl").exists()

    def test_metered_at_margin_client_is_rejected_before_setup(self):
        runner = _runner(stdout="must not run")

        with pytest.raises(PlanQuotaError, match="durable reservation"):
            PlanQuotaChatClient(get_adapter("copilot"), runner=runner)

        assert runner.calls == []

    async def test_create_returns_openai_shape(self, tmp_path):
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=_runner(stdout="hello"),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        resp = await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])
        assert resp.choices[0].message.content == "hello"

    async def test_cancellation_before_runner_dispatch_records_no_attempt(self, tmp_path):
        runner = _runner(stdout="must not run")
        qpath, cpath = tmp_path / "q.jsonl", tmp_path / "c.jsonl"
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=runner,
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )

        task = asyncio.create_task(
            client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])
        )
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert runner.calls == []
        assert not qpath.exists()
        assert not cpath.exists()

    async def test_cancellation_after_runner_dispatch_is_accounted_once_and_propagates(self, tmp_path):
        runner_started = asyncio.Event()
        runner_cancelled = asyncio.Event()

        async def blocking_runner(argv, **kwargs):
            runner_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                runner_cancelled.set()
                raise

        qpath, cpath = tmp_path / "q.jsonl", tmp_path / "c.jsonl"
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=blocking_runner,
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )
        task = asyncio.create_task(
            client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])
        )
        await runner_started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert runner_cancelled.is_set()
        quota_events = QuotaLedger(qpath).get_events()
        cost_events = CostLedger(cpath).get_events()
        assert len(quota_events) == 1
        assert len(cost_events) == 1
        quota = quota_events[0]
        cost = cost_events[0]
        assert quota.event_type == QuotaEventType.ATTEMPT_OBSERVED
        assert quota.units_used is None
        assert quota.metadata["outcome"] == "cancelled"
        assert quota.metadata["vendor_dispatched"] is True
        assert quota.metadata["quota_usage_observed"] is False
        assert cost.cost_usd == 0.0
        assert cost.metadata["outcome"] == "cancelled"
        assert cost.metadata["quota_units"] is None
        assert cost.metadata["quota_usage_observed"] is False
        assert cost.idempotency_key == quota.idempotency_key
        assert cost.metadata["attempt_id"] == cost.idempotency_key

        client._record_attempt(
            attempt_id=cost.idempotency_key,
            outcome="cancelled",
            quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
            quota_units=None,
            vendor_dispatched=True,
            detail="duplicate cancellation cleanup",
        )

        assert len(QuotaLedger(qpath).get_events()) == 1
        assert len(CostLedger(cpath).get_events()) == 1

    async def test_cancellation_during_offloop_accounting_waits_and_exposes_status(
        self,
        monkeypatch,
        tmp_path,
    ):
        accounting_started = threading.Event()
        release_accounting = threading.Event()
        accounting_finished = threading.Event()

        def blocking_accounting(*args, **kwargs):
            accounting_started.set()
            assert release_accounting.wait(timeout=2)
            accounting_finished.set()
            return AttemptAccountingStatus(quota_recorded=True, cost_recorded=True)

        monkeypatch.setattr(
            "deepr.backends.plan_quota.client.record_plan_quota_attempt",
            blocking_accounting,
        )
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=_runner(stdout="hello"),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        task = asyncio.create_task(
            client.chat.completions.create(
                model="x",
                messages=[{"role": "user", "content": "hi"}],
            )
        )
        deadline = asyncio.get_running_loop().time() + 1
        while not accounting_started.is_set() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.005)
        assert accounting_started.is_set()

        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        release_accounting.set()
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await task

        assert accounting_finished.is_set()
        assert exc_info.value.__dict__["plan_quota_attempt_id"].startswith("plan-quota:codex:")
        assert exc_info.value.__dict__["quota_recorded"] is True
        assert exc_info.value.__dict__["cost_recorded"] is True

    async def test_unexpected_runner_error_is_accounted_and_propagated_unchanged(self, tmp_path):
        runner_error = RuntimeError("fixture runner failure")

        async def broken_runner(argv, **kwargs):
            raise runner_error

        qpath = tmp_path / "q.jsonl"
        cpath = tmp_path / "c.jsonl"
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=broken_runner,
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )

        with pytest.raises(PlanQuotaError) as exc_info:
            await client.chat.completions.create(
                model="x",
                messages=[{"role": "user", "content": "hi"}],
            )

        error = exc_info.value
        assert str(error) == "codex runner failed (RuntimeError)"
        assert error.__dict__["plan_quota_runner_exception"] is runner_error
        attempt_id = error.__dict__["plan_quota_attempt_id"]
        assert error.__dict__["quota_recorded"] is True
        assert error.__dict__["cost_recorded"] is True
        quota = QuotaLedger(qpath).get_events()
        costs = CostLedger(cpath).get_events()
        assert len(quota) == 1
        assert len(costs) == 1
        assert quota[0].event_type == QuotaEventType.ATTEMPT_OBSERVED
        assert quota[0].metadata["outcome"] == "runner_error"
        assert quota[0].metadata["quota_usage_observed"] is False
        assert costs[0].metadata["outcome"] == "runner_error"
        assert quota[0].idempotency_key == attempt_id
        assert costs[0].idempotency_key == attempt_id

    async def test_runner_error_keeps_partial_accounting_failure_attached(self, tmp_path):
        runner_error = RuntimeError("fixture runner failure")

        async def broken_runner(argv, **kwargs):
            raise runner_error

        qpath = tmp_path / "q.jsonl"
        blocked_cost_path = tmp_path / "cost-ledger-dir"
        blocked_cost_path.mkdir()
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=broken_runner,
            quota_ledger_path=qpath,
            cost_ledger_path=blocked_cost_path,
        )

        with pytest.raises(PlanQuotaError) as exc_info:
            await client.chat.completions.create(
                model="x",
                messages=[{"role": "user", "content": "hi"}],
            )

        error = exc_info.value
        accounting_error = error.__dict__["plan_quota_accounting_error"]
        assert isinstance(accounting_error, PlanQuotaError)
        assert error.__dict__["quota_recorded"] is True
        assert error.__dict__["cost_recorded"] is False
        assert accounting_error.__dict__["quota_recorded"] is True
        assert accounting_error.__dict__["cost_recorded"] is False
        assert str(tmp_path) not in str(accounting_error)
        assert len(QuotaLedger(qpath).get_events()) == 1

    async def test_runner_os_error_is_path_safe_with_raw_error_non_rendered(self, tmp_path):
        runner_error = PermissionError(tmp_path / "private-runner-state")

        async def broken_runner(argv, **kwargs):
            raise runner_error

        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=broken_runner,
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )

        with pytest.raises(PlanQuotaError) as exc_info:
            await client.chat.completions.create(
                model="x",
                messages=[{"role": "user", "content": "hi"}],
            )

        assert str(exc_info.value) == "codex runner failed (PermissionError)"
        assert str(tmp_path) not in str(exc_info.value)
        assert str(tmp_path) not in repr(exc_info.value)
        assert exc_info.value.__dict__["plan_quota_runner_exception"] is runner_error

    async def test_cancellation_attaches_cost_ledger_failure_and_keeps_quota_observation(self, tmp_path):
        runner_started = asyncio.Event()

        async def blocking_runner(argv, **kwargs):
            runner_started.set()
            await asyncio.Future()

        qpath = tmp_path / "q.jsonl"
        blocked_cost_path = tmp_path / "cost-ledger-dir"
        blocked_cost_path.mkdir()
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=blocking_runner,
            quota_ledger_path=qpath,
            cost_ledger_path=blocked_cost_path,
        )
        task = asyncio.create_task(
            client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])
        )
        await runner_started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await task

        attempt_id = exc_info.value.__dict__["plan_quota_attempt_id"]
        accounting_error = exc_info.value.__dict__["plan_quota_accounting_error"]
        assert attempt_id.startswith("plan-quota:codex:")
        assert isinstance(accounting_error, PlanQuotaError)
        assert "cost ledger write failed" in str(accounting_error)
        assert str(tmp_path) not in str(accounting_error)
        assert isinstance(accounting_error.__cause__, OSError)
        assert any(attempt_id in note for note in exc_info.value.__notes__)
        assert all(str(tmp_path) not in note for note in exc_info.value.__notes__)

        quota_events = QuotaLedger(qpath).get_events()
        assert len(quota_events) == 1
        assert quota_events[0].idempotency_key == attempt_id
        assert quota_events[0].metadata["outcome"] == "cancelled"
        assert quota_events[0].metadata["quota_usage_observed"] is False

        with pytest.raises(PlanQuotaError, match="cost ledger write failed"):
            client._record_attempt(
                attempt_id=attempt_id,
                outcome="cancelled",
                quota_event_type=QuotaEventType.ATTEMPT_OBSERVED,
                quota_units=None,
                vendor_dispatched=True,
                detail="retry cancellation accounting",
            )

        assert len(QuotaLedger(qpath).get_events()) == 1
        assert blocked_cost_path.is_dir()

    async def test_cancellation_attaches_quota_ledger_failure_and_keeps_cost_observation(self, tmp_path):
        runner_started = asyncio.Event()

        async def blocking_runner(argv, **kwargs):
            runner_started.set()
            await asyncio.Future()

        blocked_quota_path = tmp_path / "quota-ledger-dir"
        blocked_quota_path.mkdir()
        cpath = tmp_path / "c.jsonl"
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=blocking_runner,
            quota_ledger_path=blocked_quota_path,
            cost_ledger_path=cpath,
        )
        task = asyncio.create_task(
            client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])
        )
        await runner_started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await task

        accounting_error = exc_info.value.__dict__["plan_quota_accounting_error"]
        assert "quota ledger write failed" in str(accounting_error)
        assert str(tmp_path) not in str(accounting_error)
        assert accounting_error.__dict__["quota_recorded"] is False
        assert accounting_error.__dict__["cost_recorded"] is True
        cost_events = CostLedger(cpath).get_events()
        assert len(cost_events) == 1
        assert cost_events[0].metadata["outcome"] == "cancelled"
        assert blocked_quota_path.is_dir()

    async def test_create_fails_closed_when_cost_ledger_cannot_be_written(self, tmp_path):
        blocked_path = tmp_path / "ledger-dir"
        blocked_path.mkdir()
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=_runner(stdout="hello"),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=blocked_path,
        )

        with pytest.raises(PlanQuotaError, match="cost ledger write failed") as exc_info:
            await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])

        error = exc_info.value
        attempt_id = error.__dict__["plan_quota_attempt_id"]
        assert attempt_id.startswith("plan-quota:codex:")
        assert error.__dict__["quota_recorded"] is True
        assert error.__dict__["cost_recorded"] is False
        assert QuotaLedger(tmp_path / "q.jsonl").get_events()[0].idempotency_key == attempt_id

    async def test_create_fails_closed_when_quota_ledger_cannot_be_written(self, tmp_path):
        blocked_path = tmp_path / "quota-ledger-dir"
        blocked_path.mkdir()
        cpath = tmp_path / "c.jsonl"
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=_runner(stdout="hello"),
            quota_ledger_path=blocked_path,
            cost_ledger_path=cpath,
        )

        with pytest.raises(PlanQuotaError, match="quota ledger write failed") as exc_info:
            await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])

        assert str(tmp_path) not in str(exc_info.value)
        attempt_id = exc_info.value.__dict__["plan_quota_attempt_id"]
        assert exc_info.value.__dict__["quota_recorded"] is False
        assert exc_info.value.__dict__["cost_recorded"] is True
        costs = CostLedger(cpath).get_events()
        assert len(costs) == 1
        assert costs[0].metadata["outcome"] == "success"
        assert costs[0].idempotency_key == attempt_id

    async def test_failed_call_preserves_cause_when_attempt_ledger_write_fails(self, tmp_path):
        blocked_path = tmp_path / "ledger-dir"
        blocked_path.mkdir()
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=_runner(stderr="banner\nterminal: invalid login", returncode=1),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=blocked_path,
        )

        with pytest.raises(PlanQuotaError) as exc_info:
            await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])

        message = str(exc_info.value)
        assert "terminal: invalid login" in message
        assert "cost ledger write failed" in message
        attempt_id = exc_info.value.__dict__["plan_quota_attempt_id"]
        assert exc_info.value.__dict__["quota_recorded"] is True
        assert exc_info.value.__dict__["cost_recorded"] is False
        accounting_error = exc_info.value.__dict__["plan_quota_accounting_error"]
        assert accounting_error.__dict__["plan_quota_attempt_id"] == attempt_id
        quota = QuotaLedger(tmp_path / "q.jsonl").get_events()
        assert quota[0].idempotency_key == attempt_id

    async def test_json_response_format_appends_instruction(self, tmp_path):
        runner = _runner(stdout='{"k": 1}')
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=runner,
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        await client.chat.completions.create(
            model="x",
            messages=[{"role": "system", "content": "extract"}, {"role": "user", "content": "text"}],
            response_format={"type": "json_object"},
        )
        prompt = runner.stdins[0] or ""
        assert "valid JSON object" in prompt
        assert "[System instructions]" in prompt

    async def test_antigravity_answer_recovered_from_transcript(self, tmp_path, monkeypatch):
        # agy drops stdout under a pipe; the answer comes from its transcript.
        from deepr.backends.plan_quota import antigravity_transcript

        monkeypatch.setattr(antigravity_transcript, "recover_answer", lambda brain, since: "recovered reply")
        client = PlanQuotaChatClient(
            get_adapter("antigravity"),
            runner=_runner(stdout=""),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        resp = await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])
        assert resp.choices[0].message.content == "recovered reply"

    async def test_antigravity_empty_transcript_is_no_output_error(self, tmp_path, monkeypatch):
        from deepr.backends.plan_quota import antigravity_transcript
        from deepr.backends.plan_quota.client import PlanQuotaError

        monkeypatch.setattr(antigravity_transcript, "recover_answer", lambda brain, since: None)
        client = PlanQuotaChatClient(
            get_adapter("antigravity"),
            runner=_runner(stdout=""),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        with pytest.raises(PlanQuotaError, match="no output"):
            await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])

    async def test_antigravity_transcript_failure_is_accounted_without_path_leak(self, tmp_path, monkeypatch):
        from deepr.backends.plan_quota import antigravity_transcript

        def fail_recovery(_brain, *, since):
            raise PermissionError(tmp_path / "private-transcript.jsonl")

        monkeypatch.setattr(antigravity_transcript, "recover_answer", fail_recovery)
        qpath = tmp_path / "q.jsonl"
        cpath = tmp_path / "c.jsonl"
        client = PlanQuotaChatClient(
            get_adapter("antigravity"),
            runner=_runner(stdout=""),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )

        with pytest.raises(PlanQuotaError, match="transcript recovery failed") as exc_info:
            await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])

        assert str(tmp_path) not in str(exc_info.value)
        assert QuotaLedger(qpath).get_events()[0].metadata["outcome"] == "post_dispatch_error"
        assert CostLedger(cpath).get_events()[0].metadata["outcome"] == "post_dispatch_error"


class TestProbe:
    @pytest.mark.parametrize("timeout", [True, 0, -1, float("nan"), float("inf")])
    async def test_invalid_timeout_returns_before_runner_or_accounting(self, tmp_path, timeout):
        runner = _runner(stdout="must not run")
        qpath = tmp_path / "q.jsonl"
        cpath = tmp_path / "c.jsonl"

        result = await probe_plan_quota(
            get_adapter("codex"),
            runner=runner,
            timeout=timeout,
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )

        assert result["ok"] is False
        assert "finite positive" in result["error"]
        assert runner.calls == []
        assert not qpath.exists()
        assert not cpath.exists()

    async def test_metered_at_margin_probe_is_rejected_before_runner_dispatch(self, tmp_path):
        runner = _runner(stdout="must not run")
        cost_path = tmp_path / "costs.jsonl"

        result = await probe_plan_quota(get_adapter("copilot"), runner=runner, cost_ledger_path=cost_path)

        assert result["ok"] is False
        assert result["latency_ms"] == 0
        assert "durable reservation" in result["error"]
        assert runner.calls == []
        assert not cost_path.exists()

    async def test_ok(self, tmp_path):
        qpath = tmp_path / "quota.jsonl"
        result = await probe_plan_quota(
            get_adapter("codex"),
            runner=_runner(stdout="OK"),
            quota_ledger_path=qpath,
            cost_ledger_path=tmp_path / "costs.jsonl",
        )
        assert result["ok"] is True
        assert result["reply"] == "OK"
        assert result["backend"] == "codex"
        event = json.loads((tmp_path / "costs.jsonl").read_text(encoding="utf-8").strip())
        assert event["operation"] == "plan_quota_probe"
        assert event["provider"] == "plan_quota:codex"
        assert event["cost_usd"] == 0.0
        assert event["metadata"]["quota_units"] == 1
        assert event["metadata"]["outcome"] == "success"
        quota = QuotaLedger(qpath).get_events()
        assert len(quota) == 1
        assert quota[0].event_type == QuotaEventType.USAGE_OBSERVED
        assert result["quota_observation_recorded"] is True
        assert event["idempotency_key"] == result["attempt_id"]
        assert quota[0].idempotency_key == result["attempt_id"]

    async def test_cancellation_after_probe_dispatch_is_accounted_and_propagates(self, tmp_path):
        runner_started = asyncio.Event()
        runner_cancelled = asyncio.Event()

        async def blocking_runner(argv, **kwargs):
            runner_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                runner_cancelled.set()
                raise

        qpath = tmp_path / "quota.jsonl"
        cpath = tmp_path / "costs.jsonl"
        task = asyncio.create_task(
            probe_plan_quota(
                get_adapter("codex"),
                runner=blocking_runner,
                quota_ledger_path=qpath,
                cost_ledger_path=cpath,
            )
        )
        await runner_started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await task

        assert runner_cancelled.is_set()
        attempt_id = exc_info.value.__dict__["plan_quota_attempt_id"]
        quota = QuotaLedger(qpath).get_events()
        costs = CostLedger(cpath).get_events()
        assert len(quota) == 1
        assert len(costs) == 1
        assert quota[0].event_type == QuotaEventType.ATTEMPT_OBSERVED
        assert quota[0].metadata["outcome"] == "cancelled"
        assert costs[0].metadata["outcome"] == "cancelled"
        assert quota[0].idempotency_key == attempt_id
        assert costs[0].idempotency_key == attempt_id

    async def test_unexpected_probe_runner_error_is_accounted_and_propagated(self, tmp_path):
        runner_error = RuntimeError("fixture probe runner failure")

        async def broken_runner(argv, **kwargs):
            raise runner_error

        qpath = tmp_path / "quota.jsonl"
        cpath = tmp_path / "costs.jsonl"

        result = await probe_plan_quota(
            get_adapter("codex"),
            runner=broken_runner,
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )

        assert result["ok"] is False
        assert result["error"] == "codex runner failed (RuntimeError)"
        assert result["quota_observation_recorded"] is True
        assert result["cost_event_recorded"] is True
        attempt_id = result["attempt_id"]
        quota = QuotaLedger(qpath).get_events()
        costs = CostLedger(cpath).get_events()
        assert len(quota) == 1
        assert len(costs) == 1
        assert quota[0].event_type == QuotaEventType.ATTEMPT_OBSERVED
        assert quota[0].metadata["outcome"] == "runner_error"
        assert costs[0].metadata["outcome"] == "runner_error"
        assert quota[0].idempotency_key == attempt_id
        assert costs[0].idempotency_key == attempt_id

    async def test_probe_cancellation_during_offloop_finish_exposes_status(
        self,
        monkeypatch,
        tmp_path,
    ):
        accounting_started = threading.Event()
        release_accounting = threading.Event()

        def blocking_accounting(*args, **kwargs):
            accounting_started.set()
            assert release_accounting.wait(timeout=2)
            return AttemptAccountingStatus(quota_recorded=True, cost_recorded=True)

        monkeypatch.setattr(
            "deepr.backends.plan_quota.client.record_plan_quota_attempt",
            blocking_accounting,
        )
        task = asyncio.create_task(
            probe_plan_quota(
                get_adapter("codex"),
                runner=_runner(stdout="OK"),
                quota_ledger_path=tmp_path / "q.jsonl",
                cost_ledger_path=tmp_path / "c.jsonl",
            )
        )
        deadline = asyncio.get_running_loop().time() + 1
        while not accounting_started.is_set() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.005)
        assert accounting_started.is_set()

        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        release_accounting.set()
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await task

        assert exc_info.value.__dict__["plan_quota_attempt_id"].startswith("plan-quota:codex:")
        assert exc_info.value.__dict__["quota_recorded"] is True
        assert exc_info.value.__dict__["cost_recorded"] is True

    async def test_probe_drops_metered_api_keys(self, tmp_path):
        runner = _runner(stdout="OK")
        result = await probe_plan_quota(
            get_adapter("codex"),
            runner=runner,
            env={"OPENAI_API_KEY": "sk-xxx", "PATH": "x"},
        )
        assert result["ok"] is True
        assert runner.envs[0] == {"PATH": "x"}

    async def test_probe_uses_stdin_when_adapter_requires_it(self, tmp_path):
        runner = _runner(stdout="OK")
        result = await probe_plan_quota(get_adapter("codex"), runner=runner)
        assert result["ok"] is True
        assert runner.calls[0][-1] == "-"
        assert runner.stdins[0] == "Reply with exactly: OK"

    async def test_exhausted(self, tmp_path):
        qpath = tmp_path / "quota.jsonl"
        result = await probe_plan_quota(
            get_adapter("codex"),
            runner=_runner(stdout="usage_limit_reached"),
            quota_ledger_path=qpath,
            cost_ledger_path=tmp_path / "costs.jsonl",
        )
        assert result["ok"] is False
        assert "exhaust" in result["error"]
        event = json.loads((tmp_path / "costs.jsonl").read_text(encoding="utf-8").strip())
        assert event["operation"] == "plan_quota_probe"
        assert event["metadata"]["outcome"] == "exhausted"
        quota = QuotaLedger(qpath).get_events()
        assert len(quota) == 1
        assert quota[0].event_type == QuotaEventType.EXHAUSTED

    async def test_probe_fails_closed_when_cost_ledger_cannot_be_written(self, tmp_path):
        blocked_path = tmp_path / "ledger-dir"
        blocked_path.mkdir()

        result = await probe_plan_quota(
            get_adapter("codex"),
            runner=_runner(stdout="OK"),
            cost_ledger_path=blocked_path,
        )

        assert result["ok"] is False
        assert result["reply"] == "OK"
        assert "cost ledger write failed" in result["error"]

    async def test_probe_fails_closed_when_quota_ledger_cannot_be_written(self, tmp_path):
        blocked_path = tmp_path / "quota-ledger-dir"
        blocked_path.mkdir()
        cpath = tmp_path / "costs.jsonl"

        result = await probe_plan_quota(
            get_adapter("codex"),
            runner=_runner(stdout="OK"),
            quota_ledger_path=blocked_path,
            cost_ledger_path=cpath,
        )

        assert result["ok"] is False
        assert result["reply"] == "OK"
        assert "quota ledger write failed" in result["error"]
        assert str(tmp_path) not in result["error"]
        assert result["quota_observation_recorded"] is False
        assert result["cost_event_recorded"] is True
        assert len(CostLedger(cpath).get_events()) == 1

    async def test_probe_accounting_uses_bounded_lock_wait(self, tmp_path):
        qpath = tmp_path / "quota.jsonl"
        cpath = tmp_path / "costs.jsonl"
        holder = QuotaLedger(qpath)
        entered = threading.Event()
        release = threading.Event()

        def hold_lock() -> None:
            with holder._locked():
                entered.set()
                assert release.wait(timeout=5)

        thread = threading.Thread(target=hold_lock)
        thread.start()
        assert entered.wait(timeout=5)
        started = time.monotonic()
        try:
            result = await probe_plan_quota(
                get_adapter("codex"),
                runner=_runner(stdout="OK"),
                quota_ledger_path=qpath,
                cost_ledger_path=cpath,
            )
        finally:
            release.set()
            thread.join(timeout=5)

        assert time.monotonic() - started < 2.0
        assert result["ok"] is False
        assert "QuotaLedgerLockTimeout" in result["error"]
        assert result["quota_observation_recorded"] is False
        assert result["cost_event_recorded"] is True
        assert not thread.is_alive()

    async def test_probe_transcript_failure_is_accounted_without_path_leak(self, tmp_path, monkeypatch):
        from deepr.backends.plan_quota import antigravity_transcript

        def fail_recovery(_brain, *, since):
            raise PermissionError(tmp_path / "private-transcript.jsonl")

        monkeypatch.setattr(antigravity_transcript, "recover_answer", fail_recovery)
        qpath = tmp_path / "quota.jsonl"
        cpath = tmp_path / "costs.jsonl"

        result = await probe_plan_quota(
            get_adapter("antigravity"),
            runner=_runner(stdout=""),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )

        assert result["ok"] is False
        assert result["outcome"] == "post_dispatch_error"
        assert "PermissionError" in result["error"]
        assert str(tmp_path) not in result["error"]
        assert QuotaLedger(qpath).get_events()[0].metadata["outcome"] == "post_dispatch_error"
        assert CostLedger(cpath).get_events()[0].metadata["outcome"] == "post_dispatch_error"

    async def test_launch_failure(self, tmp_path):
        qpath, cpath = tmp_path / "quota.jsonl", tmp_path / "costs.jsonl"
        result = await probe_plan_quota(
            get_adapter("codex"),
            runner=_runner(
                stderr="usage_limit_reached",
                launch_error="nope",
                returncode=None,
            ),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )
        assert result["ok"] is False
        assert result["error"]
        assert QuotaLedger(qpath).get_events() == []
        assert CostLedger(cpath).get_events()[0].metadata["outcome"] == "launch_error"

    async def test_timeout(self, tmp_path):
        qpath, cpath = tmp_path / "quota.jsonl", tmp_path / "costs.jsonl"
        result = await probe_plan_quota(
            get_adapter("codex"),
            runner=_runner(returncode=None, timed_out=True),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )
        assert result["ok"] is False
        assert "timed out" in result["error"]
        assert QuotaLedger(qpath).get_events()[0].event_type == QuotaEventType.ATTEMPT_OBSERVED
        assert CostLedger(cpath).get_events()[0].metadata["outcome"] == "timeout"

    async def test_nonzero_records_attempt_and_terminal_cause(self, tmp_path):
        qpath, cpath = tmp_path / "quota.jsonl", tmp_path / "costs.jsonl"
        result = await probe_plan_quota(
            get_adapter("codex"),
            runner=_runner(stderr="banner\nterminal: login required", returncode=1),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )

        assert result["ok"] is False
        assert "terminal: login required" in result["error"]
        assert result["outcome"] == "nonzero_exit"
        assert QuotaLedger(qpath).get_events()[0].event_type == QuotaEventType.ATTEMPT_OBSERVED
        assert CostLedger(cpath).get_events()[0].metadata["outcome"] == "nonzero_exit"

    async def test_empty_output_records_attempt(self, tmp_path):
        qpath, cpath = tmp_path / "quota.jsonl", tmp_path / "costs.jsonl"
        result = await probe_plan_quota(
            get_adapter("codex"),
            runner=_runner(stdout=""),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )

        assert result["ok"] is False
        assert result["outcome"] == "empty_output"
        assert QuotaLedger(qpath).get_events()[0].event_type == QuotaEventType.ATTEMPT_OBSERVED
        assert CostLedger(cpath).get_events()[0].metadata["outcome"] == "empty_output"


class TestPromptDelivery:
    """Each CLI receives the prompt by file, stdin, or argv per its adapter."""

    def test_file_mode_writes_prompt_and_cleans_up(self):
        import os

        from deepr.backends.plan_quota.client import _build_invocation, _cleanup_prompt_file

        argv, stdin, path = _build_invocation(get_adapter("grok"), "long\nresearch prompt", None)
        assert stdin is None
        assert path is not None and os.path.exists(path)
        with open(path, encoding="utf-8") as handle:
            assert handle.read() == "long\nresearch prompt"
        assert "--prompt-file" in argv and path in argv
        _cleanup_prompt_file(path)
        assert not os.path.exists(path)

    def test_stdin_mode_pipes_prompt(self):
        from deepr.backends.plan_quota.client import _build_invocation

        argv, stdin, path = _build_invocation(get_adapter("claude"), "p", None)
        assert stdin == "p"
        assert path is None
        assert argv == ["claude", "-p", "-"]

    def test_arg_mode_passes_prompt_as_argument(self):
        from deepr.backends.plan_quota.client import _build_invocation

        argv, stdin, path = _build_invocation(get_adapter("opencode"), "p", None)
        assert stdin is None
        assert path is None
        assert argv[-1] == "p"


class TestExhaustionScoping:
    """Exhaustion is an error condition, not a word that appears in the answer."""

    async def test_answer_about_rate_limits_is_not_exhaustion(self, tmp_path):
        # A successful answer that discusses rate limits/quotas/credits (a
        # provider-API research topic) must not be misread as a depleted plan.
        answer = "Provider APIs enforce a rate limit; quota windows and credits vary across vendors."
        client = PlanQuotaChatClient(
            get_adapter("grok"),
            runner=_runner(stdout=answer, returncode=0),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        resp = await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "q"}])
        assert "rate limit" in resp.choices[0].message.content

    async def test_failed_run_with_quota_signal_is_exhaustion(self, tmp_path):
        client = PlanQuotaChatClient(
            get_adapter("grok"),
            runner=_runner(stdout="rate limit exceeded; quota gone", returncode=1),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        with pytest.raises(PlanQuotaExhausted):
            await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "q"}])

    async def test_codex_current_limit_on_stderr_records_exhaustion_and_absolute_reset(self, tmp_path, monkeypatch):
        from datetime import UTC, datetime

        reset_at = datetime(2026, 7, 11, 16, 20, tzinfo=UTC)
        seen: list[str] = []

        def parse_reset(text: str):
            seen.append(text)
            return reset_at

        monkeypatch.setattr("deepr.backends.plan_quota.client.parse_reset_at_utc", parse_reset)
        qpath, cpath = tmp_path / "q.jsonl", tmp_path / "c.jsonl"
        message = "You've hit your usage limit. Try again at 9:20 AM."
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=_runner(stderr=message, returncode=1),
            quota_ledger_path=qpath,
            cost_ledger_path=cpath,
        )

        with pytest.raises(PlanQuotaExhausted, match="reschedule after reset"):
            await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "q"}])

        assert seen == [message]
        quota = QuotaLedger(qpath).get_events()
        assert len(quota) == 1
        assert quota[0].event_type == QuotaEventType.EXHAUSTED
        assert quota[0].reset_at == reset_at
        costs = CostLedger(cpath).get_events()
        assert len(costs) == 1
        assert costs[0].metadata["outcome"] == "exhausted"

    async def test_codex_current_limit_phrase_on_failed_stdout_is_not_exhaustion(self, tmp_path):
        qpath = tmp_path / "q.jsonl"
        message = "You've hit your usage limit. Try again at 9:20 AM."
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=_runner(stdout=message, stderr="command failed", returncode=1),
            quota_ledger_path=qpath,
            cost_ledger_path=tmp_path / "c.jsonl",
        )

        with pytest.raises(PlanQuotaError) as exc_info:
            await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "q"}])

        assert not isinstance(exc_info.value, PlanQuotaExhausted)
        event = QuotaLedger(qpath).get_events()[0]
        assert event.event_type == QuotaEventType.ATTEMPT_OBSERVED

    async def test_stderr_limit_on_successful_run_is_still_exhaustion(self, tmp_path):
        # Codex prints its answer to stdout and a limit notice to stderr; a real
        # limit on stderr is still caught even when the process exited 0.
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=_runner(stdout="here is the answer", stderr="usage_limit_reached", returncode=0),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        with pytest.raises(PlanQuotaExhausted):
            await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "q"}])
