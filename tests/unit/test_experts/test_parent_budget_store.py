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


def _complete_envelope(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "parent_ceiling_usd": 1.0,
        "provider": "openai",
        "model": "gpt-5-mini",
        "endpoint": "https://api.openai.com/v1",
        "account_scope": "org_test",
        "credential_fingerprint": "cred-fingerprint-test",
        "request_digest": "sha256:deadbeef",
        "input_tokens": 100,
        "output_tokens": 50,
        "reasoning_tokens": 0,
        "cache_write_tokens": 0,
        "cache_read_tokens": 0,
        "tool_usd": 0.0,
        "hosted_storage_usd": 0.0,
        "background_jobs_usd": 0.0,
        "transport_surcharge_usd": 0.0,
        "fallback_usd": 0.0,
        "retries_disabled": True,
        "redirects_disabled": True,
        "deepr_owned_client": True,
        "official_endpoint_pinned": True,
        "injected_client_rejected": True,
        "overage_disabled": True,
    }
    base.update(overrides)
    return base


def test_open_requires_complete_contract_when_requested(tmp_path: Path) -> None:
    path = tmp_path / "parent_budget_transactions.jsonl"
    with pytest.raises(ParentBudgetError):
        DurableParentBudget.open(
            surface="expert_refresh",
            parent_ceiling_usd=1.0,
            path=path,
            require_complete_contract=True,
            maximum_charge_envelope=_complete_envelope(retries_disabled=False),
        )
    with pytest.raises(ParentBudgetError, match="must match parent_ceiling_usd"):
        DurableParentBudget.open(
            surface="expert_refresh",
            parent_ceiling_usd=1.0,
            path=path,
            require_complete_contract=True,
            maximum_charge_envelope=_complete_envelope(parent_ceiling_usd=0.5),
        )
    durable = DurableParentBudget.open(
        surface="expert_refresh",
        parent_ceiling_usd=1.0,
        run_id="run-contract",
        path=path,
        require_complete_contract=True,
        maximum_charge_envelope=_complete_envelope(parent_ceiling_usd=1.0),
    )
    assert durable.parent.run_id == "run-contract"
    events = load_parent_budget_events(path)
    assert events[-1]["maximum_charge_contract"]["complete"] is True


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
