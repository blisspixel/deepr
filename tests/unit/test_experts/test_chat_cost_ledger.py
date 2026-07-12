"""Regression: expert chat answer-generation cost must reach the ledger + caps.

Conversational answer generation used to update only the in-session
``cost_accumulated`` counter, so chat/council consultation spend escaped both the
canonical cost ledger ("every spend source writes it") and the daily/monthly
caps. ``_account_chat_cost`` now routes it through ``cost_safety.record_cost``.

The method is unit-tested in isolation (via ``__new__`` to skip the heavy session
constructor) - we assert the contract: accumulate AND record.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from deepr.experts.chat import ExpertChatSession


def _session() -> ExpertChatSession:
    sess = ExpertChatSession.__new__(ExpertChatSession)
    sess.cost_accumulated = 0.0
    sess.session_id = "chat_test_session"
    sess.cost_safety = MagicMock()
    return sess


def test_account_chat_cost_records_to_ledger_and_accumulates():
    sess = _session()
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=500)
    model = SimpleNamespace(model="gpt-5.2", provider="openai")

    sess._account_chat_cost(usage, model)

    assert sess.cost_accumulated > 0  # in-session counter updated
    sess.cost_safety.record_cost.assert_called_once()
    kwargs = sess.cost_safety.record_cost.call_args.kwargs
    assert kwargs["operation_type"] == "expert_chat"
    assert kwargs["actual_cost"] == sess.cost_accumulated
    assert kwargs["source"] == "experts.chat"
    assert kwargs["session_id"] == "chat_test_session"


def test_account_chat_cost_zero_cost_writes_nothing():
    sess = _session()
    usage = SimpleNamespace(prompt_tokens=0, completion_tokens=0)
    model = SimpleNamespace(model="gpt-5.2", provider="openai")

    sess._account_chat_cost(usage, model)

    assert sess.cost_accumulated == 0.0
    sess.cost_safety.record_cost.assert_not_called()


def test_account_chat_cost_ledger_failure_is_swallowed():
    # The ledger write is best-effort; a failure must not break the chat turn,
    # but the in-session counter still moves.
    sess = _session()
    sess.cost_safety.record_cost.side_effect = RuntimeError("disk full")
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=500)
    model = SimpleNamespace(model="gpt-5.2", provider="openai")

    sess._account_chat_cost(usage, model)  # must not raise

    assert sess.cost_accumulated > 0


async def test_cancel_inflight_provider_work_requests_each_accepted_job() -> None:
    sess = ExpertChatSession.__new__(ExpertChatSession)
    cancel = AsyncMock()
    sess.client = SimpleNamespace(responses=SimpleNamespace(cancel=cancel))
    sess.pending_research = {"response-1": {}, "response-2": {}}

    result = await sess.cancel_inflight_provider_work()

    assert result == {"status": "provider_cancel_requested", "requested": 2, "failed": 0}
    assert [call.args for call in cancel.await_args_list] == [("response-1",), ("response-2",)]
    assert sess.pending_research == {}


async def test_cancel_inflight_provider_work_reports_missing_provider_cancel() -> None:
    sess = ExpertChatSession.__new__(ExpertChatSession)
    sess.client = SimpleNamespace()
    sess.pending_research = {"response-1": {}}

    result = await sess.cancel_inflight_provider_work()

    assert result == {"status": "provider_cancel_unavailable", "requested": 0, "failed": 1}
    assert list(sess.pending_research) == ["response-1"]
