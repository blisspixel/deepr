"""Regression: standard-research fallback must not double-write the ledger."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deepr.experts.chat_backends import ExpertChatResult
from deepr.experts.chat_research_ops import run_deep_research, run_standard_research
from deepr.experts.cost_safety import get_cost_safety_manager, reset_cost_safety_manager
from deepr.observability.cost_ledger import CostLedger


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "costs"))
    reset_cost_safety_manager()
    yield
    reset_cost_safety_manager()


@pytest.mark.asyncio
async def test_standard_research_fallback_mirrors_session_without_second_ledger(monkeypatch):
    from deepr.experts import chat_capacity

    monkeypatch.setattr(chat_capacity, "METERED_EXPERT_CHAT_EXECUTION_ENABLED", True)
    monkeypatch.setenv("DEEPR_ALLOW_METERED_EXPERT_CHAT", "1")

    manager = get_cost_safety_manager()
    cost_session = manager.create_session("fallback", "chat", budget_limit=10.0)

    async def _complete(request):
        # Simulate durable backend settle writing the sole canonical ledger event.
        CostLedger().record_event(
            operation="research_completion",
            provider="openai",
            cost_usd=0.01,
            model="gpt-5.5",
            source="test.simulated_durable_settle",
            idempotency_key="job:fallback-test:completion",
        )
        return ExpertChatResult(
            message=SimpleNamespace(content="fallback answer", tool_calls=[]),
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )

    backend = SimpleNamespace(
        metered=True,
        provider="openai",
        complete=AsyncMock(side_effect=_complete),
    )

    session = SimpleNamespace(
        session_id="fallback",
        chat_backend=backend,
        chat_provider="openai",
        cost_safety=manager,
        cost_session=cost_session,
        cost_accumulated=0.0,
        _provider_model_or=lambda model: model,
        _provider_reasoning_effort_or_none=lambda _effort: None,
        _add_research_to_knowledge_base=AsyncMock(),
    )

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("grok unavailable")

    monkeypatch.setattr(
        "deepr.experts.chat_research_ops.execute_metered_chat_provider_call",
        _boom,
    )

    result = await run_standard_research(session, "what is x?")

    assert "answer" in result
    assert result["mode"] == "standard_research_fallback"
    events = CostLedger().get_events()
    assert len(events) == 1
    assert events[0].operation == "research_completion"
    assert session.cost_session.total_cost > 0
    assert session.cost_accumulated == pytest.approx(session.cost_session.total_cost)


@pytest.mark.asyncio
async def test_deep_research_blocks_when_needs_confirmation(monkeypatch):
    """needs_confirmation must not be discarded as a soft allow."""
    from deepr.experts import chat_capacity

    monkeypatch.setattr(chat_capacity, "METERED_EXPERT_CHAT_EXECUTION_ENABLED", True)
    monkeypatch.setenv("DEEPR_ALLOW_METERED_EXPERT_CHAT", "1")

    manager = get_cost_safety_manager()
    cost_session = manager.create_session("deep", "chat", budget_limit=50.0)

    def _needs_confirm(**_kwargs):
        return True, "High cost operation: $2.00", True

    monkeypatch.setattr(manager, "check_operation", _needs_confirm)

    provider_called = False

    async def _provider_call(**_kwargs):
        nonlocal provider_called
        provider_called = True
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(
        "deepr.experts.chat_research_ops.execute_metered_chat_provider_call",
        _provider_call,
    )

    session = SimpleNamespace(
        session_id="deep",
        chat_backend=SimpleNamespace(metered=True, provider="openai"),
        cost_safety=manager,
        cost_session=cost_session,
        budget=50.0,
    )

    result = await run_deep_research(session, "expensive query")

    assert result["status"] == "blocked"
    assert "blocked" in result["error"].lower() or "confirm" in result["error"].lower()
    assert provider_called is False
