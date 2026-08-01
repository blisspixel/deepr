"""Tests for durable parent budget journal and replay."""

from __future__ import annotations

from pathlib import Path

import pytest

from deepr.experts.parent_budget_store import (
    DurableParentBudget,
    load_parent_budget_events,
    replay_parent_budget,
)
from deepr.experts.parent_budget_transaction import ChildCallState, ParentBudgetError, ParentBudgetState


def test_durable_open_admit_settle_close_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "parent_budget_transactions.jsonl"
    durable = DurableParentBudget.open(
        surface="fill_gaps",
        parent_ceiling_usd=1.0,
        run_id="run-test-1",
        path=path,
    )
    child = durable.admit_child(operation="gap", max_usd=0.4, child_id="c1")
    durable.mark_dispatch(child.child_id)
    durable.settle_child(child.child_id, 0.2)
    durable.close()

    events = load_parent_budget_events(path)
    assert [event["event_type"] for event in events] == [
        "opened",
        "child_admitted",
        "dispatch_marked",
        "settled",
        "closed",
    ]
    rebuilt = replay_parent_budget("run-test-1", path)
    assert rebuilt is not None
    assert rebuilt.state is ParentBudgetState.CLOSED
    assert rebuilt.settled_usd() == pytest.approx(0.2)
    assert rebuilt.children["c1"].state is ChildCallState.SETTLED


def test_durable_freeze_on_overrun_is_replayable(tmp_path: Path) -> None:
    path = tmp_path / "parent_budget_transactions.jsonl"
    durable = DurableParentBudget.open(
        surface="expert_reflect",
        parent_ceiling_usd=0.5,
        run_id="run-freeze",
        path=path,
    )
    durable.admit_child(operation="reflect", max_usd=0.3, child_id="r1")
    with pytest.raises(ParentBudgetError):
        durable.settle_child("r1", 0.4)

    rebuilt = replay_parent_budget("run-freeze", path)
    assert rebuilt is not None
    assert rebuilt.state is ParentBudgetState.FROZEN
    assert rebuilt.children["r1"].state is ChildCallState.CONSUMED
    assert rebuilt.children["r1"].settled_usd == pytest.approx(0.3)


def test_durable_cancel_and_consume(tmp_path: Path) -> None:
    path = tmp_path / "parent_budget_transactions.jsonl"
    durable = DurableParentBudget.open(
        surface="paid_portraits",
        parent_ceiling_usd=1.0,
        run_id="run-cancel",
        path=path,
    )
    durable.admit_child(operation="a", max_usd=0.2, child_id="a1")
    durable.cancel_child("a1")
    durable.admit_child(operation="b", max_usd=0.5, child_id="b1")
    durable.mark_dispatch("b1")
    durable.consume_child_ceiling("b1", reason="lost_response")
    durable.close()

    rebuilt = replay_parent_budget("run-cancel", path)
    assert rebuilt is not None
    assert rebuilt.children["a1"].state is ChildCallState.CANCELLED
    assert rebuilt.children["b1"].state is ChildCallState.CONSUMED
    assert rebuilt.settled_usd() == pytest.approx(0.5)
