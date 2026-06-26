"""Tests for deepr.backends.plan_quota.client - the CLI-as-chat-backend shim.

A fake runner stands in for the vendor subprocess, so these run with no CLI
installed and no network. Quota and cost ledgers are written to explicit tmp
paths and asserted.
"""

from __future__ import annotations

import pytest

from deepr.backends.plan_quota.adapters import get_adapter
from deepr.backends.plan_quota.cli_runner import CliResult
from deepr.backends.plan_quota.client import (
    PlanQuotaChatClient,
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
):
    calls: list[list[str]] = []
    envs: list[dict[str, str] | None] = []
    stdins: list[str | None] = []

    async def fake(argv, **kwargs):
        calls.append(argv)
        envs.append(kwargs.get("env"))
        stdins.append(kwargs.get("stdin"))
        return CliResult(returncode, stdout, stderr, timed_out, launch_error, 5)

    fake.calls = calls  # type: ignore[attr-defined]
    fake.envs = envs  # type: ignore[attr-defined]
    fake.stdins = stdins  # type: ignore[attr-defined]
    return fake


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
        # Codex streams status/errors to stderr; a real limit notice lands there,
        # not in the stdout answer body.
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(stderr="Error: usage_limit_reached"),
            quota_ledger_path=qpath,
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        result = await fn("q", 1.0)
        assert result["answer"] == ""
        assert result.get("quota_exhausted") is True
        events = QuotaLedger(qpath).get_events()
        assert events[0].event_type == QuotaEventType.EXHAUSTED

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
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(launch_error="not found", returncode=None),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        result = await fn("q", 1.0)
        assert result["answer"] == ""
        assert "error" in result

    async def test_timeout_is_reported(self, tmp_path):
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(returncode=None, timed_out=True),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        result = await fn("q", 1.0)
        assert result["answer"] == ""
        assert "timed out" in result["error"]

    async def test_nonzero_exit_is_reported(self, tmp_path):
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(stderr="boom", returncode=2),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        result = await fn("q", 1.0)
        assert "error" in result and result["answer"] == ""

    async def test_empty_output_is_error(self, tmp_path):
        fn = make_plan_quota_research_fn(
            get_adapter("antigravity"),
            runner=_runner(stdout="   "),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        result = await fn("q", 1.0)
        assert "error" in result
        assert "no output" in result["error"]

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
    async def test_create_returns_openai_shape(self, tmp_path):
        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=_runner(stdout="hello"),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        resp = await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "hi"}])
        assert resp.choices[0].message.content == "hello"

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


class TestProbe:
    async def test_ok(self, tmp_path):
        result = await probe_plan_quota(get_adapter("codex"), runner=_runner(stdout="OK"))
        assert result["ok"] is True
        assert result["reply"] == "OK"
        assert result["backend"] == "codex"

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
        result = await probe_plan_quota(get_adapter("codex"), runner=_runner(stdout="usage_limit_reached"))
        assert result["ok"] is False
        assert "exhaust" in result["error"]

    async def test_launch_failure(self, tmp_path):
        result = await probe_plan_quota(get_adapter("codex"), runner=_runner(launch_error="nope", returncode=None))
        assert result["ok"] is False
        assert result["error"]

    async def test_timeout(self, tmp_path):
        result = await probe_plan_quota(get_adapter("codex"), runner=_runner(returncode=None, timed_out=True))
        assert result["ok"] is False
        assert "timed out" in result["error"]


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
        from deepr.backends.plan_quota.client import PlanQuotaExhausted

        client = PlanQuotaChatClient(
            get_adapter("grok"),
            runner=_runner(stdout="rate limit exceeded; quota gone", returncode=1),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        with pytest.raises(PlanQuotaExhausted):
            await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "q"}])

    async def test_stderr_limit_on_successful_run_is_still_exhaustion(self, tmp_path):
        # Codex prints its answer to stdout and a limit notice to stderr; a real
        # limit on stderr is still caught even when the process exited 0.
        from deepr.backends.plan_quota.client import PlanQuotaExhausted

        client = PlanQuotaChatClient(
            get_adapter("codex"),
            runner=_runner(stdout="here is the answer", stderr="usage_limit_reached", returncode=0),
            quota_ledger_path=tmp_path / "q.jsonl",
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        with pytest.raises(PlanQuotaExhausted):
            await client.chat.completions.create(model="x", messages=[{"role": "user", "content": "q"}])
