"""Tests for deepr.backends.plan_quota.client - the CLI-as-chat-backend shim.

A fake runner stands in for the vendor subprocess, so these run with no CLI
installed and no network. Quota and cost ledgers are written to explicit tmp
paths and asserted.
"""

from __future__ import annotations

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

    async def fake(argv, **kwargs):
        calls.append(argv)
        return CliResult(returncode, stdout, stderr, timed_out, launch_error, 5)

    fake.calls = calls  # type: ignore[attr-defined]
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
        fn = make_plan_quota_research_fn(
            get_adapter("codex"),
            runner=_runner(stdout="Error: usage_limit_reached"),
            quota_ledger_path=qpath,
            cost_ledger_path=tmp_path / "c.jsonl",
        )
        result = await fn("q", 1.0)
        assert result["answer"] == ""
        assert result.get("quota_exhausted") is True
        events = QuotaLedger(qpath).get_events()
        assert events[0].event_type == QuotaEventType.EXHAUSTED

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
        assert "PTY" in result["error"]

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
        assert "Fresh retrieval context" in prompt


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
        prompt = runner.calls[0][-1]
        assert "valid JSON object" in prompt
        assert "[System instructions]" in prompt


class TestProbe:
    async def test_ok(self, tmp_path):
        result = await probe_plan_quota(get_adapter("codex"), runner=_runner(stdout="OK"))
        assert result["ok"] is True
        assert result["reply"] == "OK"
        assert result["backend"] == "codex"

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
