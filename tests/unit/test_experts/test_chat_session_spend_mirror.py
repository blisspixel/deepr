from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deepr.experts.chat_capacity import MeteredExpertChatDisabledError
from deepr.experts.chat_metered import mirror_chat_session_spend
from deepr.experts.chat_research_ops import reconcile_deep_research_job
from deepr.experts.cost_safety import CostSession, get_cost_safety_manager, reset_cost_safety_manager
from deepr.observability.cost_ledger import CostLedger


@pytest.fixture(autouse=True)
def _isolate_costs(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPR_COST_DATA_DIR", str(tmp_path / "costs"))
    reset_cost_safety_manager()
    yield
    reset_cost_safety_manager()


def test_mirror_chat_session_spend_does_not_append_ledger():
    session = SimpleNamespace(
        cost_session=CostSession("chat_test", "chat", budget_limit=5.0),
        cost_accumulated=0.0,
    )
    before = len(CostLedger().get_events())
    cost = mirror_chat_session_spend(
        session,
        operation_type="expert_chat",
        actual_cost=0.42,
        details="unit",
    )
    assert cost == pytest.approx(0.42)
    assert session.cost_session.total_cost == pytest.approx(0.42)
    assert session.cost_accumulated == pytest.approx(0.42)
    assert len(CostLedger().get_events()) == before


@pytest.mark.asyncio
async def test_deep_research_reconciliation_is_blocked_before_retrieval(monkeypatch):
    from deepr.experts import chat_capacity

    monkeypatch.setattr(chat_capacity, "METERED_EXPERT_CHAT_EXECUTION_ENABLED", True)
    manager = get_cost_safety_manager()
    cost_session = manager.create_session("chat_deep", "chat", budget_limit=20.0)
    session = SimpleNamespace(
        session_id="chat_deep",
        cost_session=cost_session,
        cost_accumulated=0.0,
        cost_safety=manager,
        pending_research={
            "resp_1": {"query": "q", "estimated_cost": 2.0},
        },
        client=SimpleNamespace(
            responses=SimpleNamespace(
                retrieve=AsyncMock(
                    return_value=SimpleNamespace(
                        status="completed",
                        usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000),
                    )
                )
            )
        ),
    )

    with pytest.raises(MeteredExpertChatDisabledError) as blocked:
        await reconcile_deep_research_job(session, "resp_1")

    assert blocked.value.operation == "expert_chat_deep_research_reconciliation"
    session.client.responses.retrieve.assert_not_awaited()
    events = [e for e in CostLedger().get_events() if e.operation == "deep_research_final_usage"]
    assert events == []
    assert session.cost_session.total_cost == 0
