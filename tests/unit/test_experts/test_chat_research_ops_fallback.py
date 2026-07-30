"""Regression tests for fail-closed paid expert research paths."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deepr.experts.chat_capacity import MeteredExpertChatDisabledError
from deepr.experts.chat_research_ops import run_deep_research, run_standard_research


@pytest.mark.asyncio
async def test_standard_research_does_not_fall_back_to_another_paid_provider():
    session = SimpleNamespace()

    with pytest.raises(MeteredExpertChatDisabledError) as blocked:
        await run_standard_research(session, "what is x?")

    assert blocked.value.operation == "expert_chat_standard_research"
    assert blocked.value.provider_work_dispatched is False


@pytest.mark.asyncio
async def test_deep_research_is_blocked_before_any_provider_work():
    session = SimpleNamespace()

    with pytest.raises(MeteredExpertChatDisabledError) as blocked:
        await run_deep_research(session, "expensive query")

    assert blocked.value.operation == "expert_chat_deep_research"
    assert blocked.value.provider_work_dispatched is False
