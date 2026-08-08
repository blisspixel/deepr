"""Tests for shared parent budget transaction substrate."""

from __future__ import annotations

import pytest

from deepr.experts.maximum_charge_contract import ABSOLUTE_DEEPR_CEILING_USD
from deepr.experts.metered_mutation_gate import (
    METERED_EXPERT_MUTATIONS_ENABLED,
    MeteredExpertMutationDisabledError,
    require_metered_expert_mutation,
)
from deepr.experts.parent_budget_transaction import (
    GATED_METERED_LIFECYCLE_SURFACES,
    ChildCallState,
    ParentBudgetError,
    ParentBudgetState,
    open_parent_budget_transaction,
    surface_requires_parent_budget,
)


def test_mutations_remain_fail_closed() -> None:
    assert METERED_EXPERT_MUTATIONS_ENABLED is False
    with pytest.raises(MeteredExpertMutationDisabledError) as caught:
        require_metered_expert_mutation("api_expert_sync", safe_alternative="use --local")
    payload = caught.value.to_dict()
    assert payload["provider_work_started"] is False
    assert payload["parent_budget_transaction_required"] is True
    assert payload["parent_budget_surface_known"] is True
    assert "api_expert_sync" in payload["gated_lifecycle_surfaces"]


def test_gated_surface_inventory_is_non_empty() -> None:
    assert "fill_gaps" in GATED_METERED_LIFECYCLE_SURFACES
    assert "api_expert_portrait" in GATED_METERED_LIFECYCLE_SURFACES
    assert "api_expert_sync" in GATED_METERED_LIFECYCLE_SURFACES
    assert surface_requires_parent_budget("fill_gaps") is True
    assert surface_requires_parent_budget("api_expert_portrait") is True
    assert surface_requires_parent_budget("unknown") is False


def test_parent_admits_children_within_ceiling() -> None:
    parent = open_parent_budget_transaction(surface="expert_refresh", parent_ceiling_usd=1.0)
    first = parent.admit_child(operation="call_a", max_usd=0.4)
    second = parent.admit_child(operation="call_b", max_usd=0.5)
    assert first.state is ChildCallState.ADMITTED
    assert second.state is ChildCallState.ADMITTED
    assert parent.remaining_usd() == pytest.approx(0.1)
    with pytest.raises(ParentBudgetError):
        parent.admit_child(operation="call_c", max_usd=0.2)


def test_dispatch_settle_and_close() -> None:
    parent = open_parent_budget_transaction(surface="fill_gaps", parent_ceiling_usd=0.5)
    child = parent.admit_child(operation="gap_fill", max_usd=0.4)
    parent.mark_dispatch(child.child_id)
    parent.settle_child(child.child_id, 0.25)
    assert parent.children[child.child_id].state is ChildCallState.SETTLED
    assert parent.settled_usd() == pytest.approx(0.25)
    assert parent.remaining_usd() == pytest.approx(0.25)
    parent.close()
    assert parent.state is ParentBudgetState.CLOSED


def test_over_actual_freezes_and_consumes_ceiling() -> None:
    parent = open_parent_budget_transaction(surface="expert_reflect", parent_ceiling_usd=0.3)
    child = parent.admit_child(operation="reflect", max_usd=0.2)
    with pytest.raises(ParentBudgetError):
        parent.settle_child(child.child_id, 0.25)
    assert parent.state is ParentBudgetState.FROZEN
    assert parent.children[child.child_id].state is ChildCallState.CONSUMED
    assert parent.children[child.child_id].settled_usd == pytest.approx(0.2)


def test_cancel_releases_headroom() -> None:
    parent = open_parent_budget_transaction(surface="paid_portraits", parent_ceiling_usd=1.0)
    child = parent.admit_child(operation="portrait", max_usd=0.7)
    parent.cancel_child(child.child_id)
    assert parent.remaining_usd() == pytest.approx(1.0)
    parent.close()


def test_consume_child_ceiling_is_conservative() -> None:
    parent = open_parent_budget_transaction(surface="eval_calibrate_corpus", parent_ceiling_usd=1.0)
    child = parent.admit_child(operation="judge", max_usd=0.5)
    parent.mark_dispatch(child.child_id)
    parent.consume_child_ceiling(child.child_id, reason="ambiguous_usage")
    assert parent.children[child.child_id].settled_usd == pytest.approx(0.5)
    assert parent.remaining_usd() == pytest.approx(0.5)


def test_rejects_parent_above_absolute_ceiling() -> None:
    with pytest.raises(ParentBudgetError):
        open_parent_budget_transaction(
            surface="expert_sync_api",
            parent_ceiling_usd=ABSOLUTE_DEEPR_CEILING_USD + 0.01,
        )


def test_cannot_close_with_open_children() -> None:
    parent = open_parent_budget_transaction(surface="expert_resume", parent_ceiling_usd=1.0)
    parent.admit_child(operation="resume_step", max_usd=0.2)
    with pytest.raises(ParentBudgetError):
        parent.close()


def test_cannot_double_close() -> None:
    parent = open_parent_budget_transaction(surface="expert_resume", parent_ceiling_usd=1.0)
    parent.close()
    with pytest.raises(ParentBudgetError, match="already closed"):
        parent.close()


def test_concurrent_admits_never_oversubscribe() -> None:
    import threading

    parent = open_parent_budget_transaction(surface="fill_gaps_deep", parent_ceiling_usd=1.0)
    errors: list[BaseException] = []
    admitted = 0
    admitted_lock = threading.Lock()

    def worker(index: int) -> None:
        nonlocal admitted
        try:
            parent.admit_child(operation=f"c{index}", max_usd=0.3, child_id=f"c{index}")
            with admitted_lock:
                admitted += 1
        except ParentBudgetError as exc:
            errors.append(exc)
        except Exception as exc:  # pragma: no cover - unexpected
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert admitted <= 3
    assert parent.admitted_max_usd() <= 1.0 + 1e-9
    assert all(isinstance(err, ParentBudgetError) for err in errors)
    assert admitted + len(errors) == 10
