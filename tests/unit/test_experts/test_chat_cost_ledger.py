"""Release-safe live expert-chat accounting gate regressions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from deepr.experts.chat import ExpertChatSession
from deepr.experts.chat_capacity import MeteredExpertChatDisabledError


def _session() -> ExpertChatSession:
    sess = ExpertChatSession.__new__(ExpertChatSession)
    sess.cost_accumulated = 0.0
    sess.session_id = "chat_test_session"
    sess.cost_safety = MagicMock()
    sess.chat_backend = SimpleNamespace(metered=False)
    return sess


def test_owned_chat_accounting_stays_zero_dollars():
    sess = _session()
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=500)
    model = SimpleNamespace(model="gpt-5.2", provider="openai")

    sess._account_chat_cost(usage, model)

    assert sess.cost_accumulated == 0.0
    sess.cost_safety.record_cost.assert_not_called()


def test_account_chat_cost_zero_cost_writes_nothing():
    sess = _session()
    usage = SimpleNamespace(prompt_tokens=0, completion_tokens=0)
    model = SimpleNamespace(model="gpt-5.2", provider="openai")

    sess._account_chat_cost(usage, model)

    assert sess.cost_accumulated == 0.0
    sess.cost_safety.record_cost.assert_not_called()


def test_metered_chat_accounting_cannot_be_reached_post_dispatch():
    sess = _session()
    sess.chat_backend = SimpleNamespace(metered=True)
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=500)
    model = SimpleNamespace(model="gpt-5.2", provider="openai")

    with pytest.raises(MeteredExpertChatDisabledError) as exc_info:
        sess._account_chat_cost(usage, model)

    assert exc_info.value.operation == "expert_chat_accounting"
    assert exc_info.value.provider_work_dispatched is False
    assert sess.cost_accumulated == 0.0
    sess.cost_safety.record_cost.assert_not_called()


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
