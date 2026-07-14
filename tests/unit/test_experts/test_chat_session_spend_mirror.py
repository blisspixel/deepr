from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
async def test_deep_research_final_usage_is_idempotent_and_charges_delta_only(monkeypatch):
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

    first = await reconcile_deep_research_job(session, "resp_1")
    second = await reconcile_deep_research_job(session, "resp_1")

    assert first["status"] == "reconciled"
    assert first["ledger_written"] is True
    assert second["status"] == "not_pending"
    events = [e for e in CostLedger().get_events() if e.operation == "deep_research_final_usage"]
    assert len(events) == 1
    assert events[0].idempotency_key == "job:resp_1:final_usage"
    # Ledger dollar total must be overrun-only (submission already settled the estimate).
    assert events[0].cost_usd == pytest.approx(first["delta_cost"])
    assert events[0].cost_usd == pytest.approx(max(0.0, first["actual_cost"] - first["estimated_cost"]))
    assert session.cost_session.total_cost == pytest.approx(first["delta_cost"])
