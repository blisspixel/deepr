"""Append-only durable journal for parent budget transactions.

In-process ``ParentBudgetTransaction`` objects coordinate nested admissions.
This store records the same transitions as JSONL events under the cost data
directory so a crash mid-run leaves an auditable trail. Replay rebuilds the
latest per-run snapshot without rewriting history.

Never enables metered dispatch by itself.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.parent_budget_transaction import (
    ChildCallSlot,
    ChildCallState,
    ParentBudgetError,
    ParentBudgetState,
    ParentBudgetTransaction,
    open_parent_budget_transaction,
)
from deepr.utils.atomic_io import append_jsonl_durable

PARENT_BUDGET_SCHEMA_VERSION = "deepr-parent-budget-event-v1"
PARENT_BUDGET_KIND = "deepr.costs.parent_budget_event"

_EVENT_TYPES = frozenset(
    {
        "opened",
        "child_admitted",
        "dispatch_marked",
        "settled",
        "consumed",
        "cancelled",
        "closed",
        "frozen",
    }
)

_lock = threading.RLock()


def parent_budget_log_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    from deepr.observability.cost_authority import default_cost_data_dir

    return default_cost_data_dir() / "parent_budget_transactions.jsonl"


def _now() -> datetime:
    return datetime.now(UTC)


def _append_event(event: Mapping[str, Any], path: Path | None) -> dict[str, Any]:
    payload = dict(event)
    payload.setdefault("schema_version", PARENT_BUDGET_SCHEMA_VERSION)
    payload.setdefault("kind", PARENT_BUDGET_KIND)
    payload.setdefault("recorded_at", _now().isoformat())
    event_type = str(payload.get("event_type") or "")
    if event_type not in _EVENT_TYPES:
        raise ParentBudgetError(f"unknown parent budget event_type {event_type!r}")
    if not str(payload.get("run_id") or "").strip():
        raise ParentBudgetError("run_id is required")
    append_jsonl_durable(parent_budget_log_path(path), payload, fsync=True)
    return payload


def load_parent_budget_events(path: Path | None = None) -> list[dict[str, Any]]:
    resolved = parent_budget_log_path(path)
    if not resolved.exists():
        return []
    events: list[dict[str, Any]] = []
    with resolved.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ParentBudgetError("parent budget event must be a JSON object")
            events.append(payload)
    return events


def _apply_consumed_event(parent: ParentBudgetTransaction, event: Mapping[str, Any]) -> None:
    child_id = str(event.get("child_id") or "")
    child = parent.children.get(child_id)
    if child is None:
        raise ParentBudgetError(f"missing child {child_id!r} for consume replay")
    child.settled_usd = float(event.get("settled_usd") or child.max_usd)
    child.state = ChildCallState.CONSUMED
    if event.get("freeze"):
        parent.state = ParentBudgetState.FROZEN
        parent.freeze_reason = str(event.get("freeze_reason") or "")
        return
    child.metadata["consume_reason"] = str(event.get("reason") or "conservative_consume")


def _apply_replay_event(parent: ParentBudgetTransaction, event: Mapping[str, Any]) -> None:
    event_type = str(event.get("event_type") or "")
    child_id = str(event.get("child_id") or "")
    if event_type == "child_admitted":
        parent.admit_child(
            operation=str(event.get("operation") or ""),
            max_usd=float(event.get("max_usd") or 0),
            child_id=child_id,
            metadata=dict(event.get("metadata") or {}),
        )
        return
    if event_type == "dispatch_marked":
        parent.mark_dispatch(child_id)
        return
    if event_type == "settled":
        parent.settle_child(child_id, float(event.get("actual_usd") or 0))
        return
    if event_type == "consumed":
        _apply_consumed_event(parent, event)
        return
    if event_type == "cancelled":
        parent.cancel_child(child_id)
        return
    if event_type == "closed":
        parent.state = ParentBudgetState.CLOSED
        return
    if event_type == "frozen":
        parent.state = ParentBudgetState.FROZEN
        parent.freeze_reason = str(event.get("freeze_reason") or "")


def replay_parent_budget(run_id: str, path: Path | None = None) -> ParentBudgetTransaction | None:
    """Rebuild one parent transaction from the append-only journal."""
    target = str(run_id or "").strip()
    if not target:
        raise ParentBudgetError("run_id is required")
    parent: ParentBudgetTransaction | None = None
    for event in load_parent_budget_events(path):
        if str(event.get("run_id") or "") != target:
            continue
        if str(event.get("event_type") or "") == "opened":
            parent = open_parent_budget_transaction(
                surface=str(event.get("surface") or ""),
                parent_ceiling_usd=float(event.get("parent_ceiling_usd") or 0),
                run_id=target,
            )
            continue
        if parent is None:
            raise ParentBudgetError(f"run {target!r} has events before opened")
        _apply_replay_event(parent, event)
    return parent


def open_gated_lifecycle_budget(
    *,
    surface: str,
    parent_ceiling_usd: float,
    maximum_charge_envelope: Mapping[str, Any],
    run_id: str | None = None,
    path: Path | None = None,
) -> DurableParentBudget:
    """Open a durable parent budget for a gated metered lifecycle surface.

    Requires a complete offline maximum-charge envelope and a known gated
    surface name. Does not enable provider dispatch; callers must still pass
    ``require_metered_expert_mutation`` / execution flags.
    """
    from deepr.experts.parent_budget_transaction import surface_requires_parent_budget

    name = str(surface or "").strip()
    if not surface_requires_parent_budget(name):
        raise ParentBudgetError(
            f"surface {name!r} is not in the gated metered lifecycle inventory"
        )
    return DurableParentBudget.open(
        surface=name,
        parent_ceiling_usd=parent_ceiling_usd,
        run_id=run_id,
        path=path,
        maximum_charge_envelope=maximum_charge_envelope,
        require_complete_contract=True,
    )


class DurableParentBudget:
    """Parent budget that journals every transition."""

    def __init__(self, parent: ParentBudgetTransaction, *, path: Path | None = None) -> None:
        self.parent = parent
        self.path = path

    @classmethod
    def open(
        cls,
        *,
        surface: str,
        parent_ceiling_usd: float,
        run_id: str | None = None,
        path: Path | None = None,
        maximum_charge_envelope: Mapping[str, Any] | None = None,
        require_complete_contract: bool = False,
    ) -> DurableParentBudget:
        """Open and journal a parent budget.

        When ``require_complete_contract`` is true, a complete offline
        maximum-charge envelope is mandatory. Completeness still does not
        enable provider dispatch.
        """
        contract_summary: dict[str, Any] | None = None
        if require_complete_contract or maximum_charge_envelope is not None:
            from deepr.experts.maximum_charge_contract import evaluate_maximum_charge_contract

            if maximum_charge_envelope is None:
                raise ParentBudgetError(
                    "maximum_charge_envelope is required when require_complete_contract is set"
                )
            verdict = evaluate_maximum_charge_contract(maximum_charge_envelope)
            contract_summary = verdict.to_dict()
            if require_complete_contract and not verdict.complete:
                detail = "; ".join(verdict.failures) or "maximum-charge contract incomplete"
                raise ParentBudgetError(detail)
            envelope_ceiling = maximum_charge_envelope.get("parent_ceiling_usd")
            if envelope_ceiling is not None and abs(float(envelope_ceiling) - float(parent_ceiling_usd)) > 1e-9:
                raise ParentBudgetError(
                    "maximum_charge_envelope.parent_ceiling_usd must match parent_ceiling_usd"
                )
            if verdict.complete and verdict.computed_max_usd is not None:
                if float(verdict.computed_max_usd) > float(parent_ceiling_usd) + 1e-9:
                    raise ParentBudgetError(
                        "maximum-charge computed_max_usd exceeds parent_ceiling_usd"
                    )

        with _lock:
            parent = open_parent_budget_transaction(
                surface=surface,
                parent_ceiling_usd=parent_ceiling_usd,
                run_id=run_id,
            )
            durable = cls(parent, path=path)
            event: dict[str, Any] = {
                "event_type": "opened",
                "run_id": parent.run_id,
                "surface": parent.surface,
                "parent_ceiling_usd": parent.parent_ceiling_usd,
                "require_complete_contract": require_complete_contract,
            }
            if contract_summary is not None:
                event["maximum_charge_contract"] = contract_summary
            _append_event(event, path)
            return durable

    def admit_child(
        self,
        *,
        operation: str,
        max_usd: float,
        child_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ChildCallSlot:
        with _lock:
            child = self.parent.admit_child(
                operation=operation,
                max_usd=max_usd,
                child_id=child_id,
                metadata=metadata,
            )
            _append_event(
                {
                    "event_type": "child_admitted",
                    "run_id": self.parent.run_id,
                    "child_id": child.child_id,
                    "operation": child.operation,
                    "max_usd": child.max_usd,
                    "metadata": dict(child.metadata),
                },
                self.path,
            )
            return child

    def mark_dispatch(self, child_id: str) -> ChildCallSlot:
        with _lock:
            child = self.parent.mark_dispatch(child_id)
            _append_event(
                {
                    "event_type": "dispatch_marked",
                    "run_id": self.parent.run_id,
                    "child_id": child.child_id,
                },
                self.path,
            )
            return child

    def settle_child(self, child_id: str, actual_usd: float) -> ChildCallSlot:
        with _lock:
            try:
                child = self.parent.settle_child(child_id, actual_usd)
            except ParentBudgetError:
                # Freeze path already mutated child; journal consume + freeze.
                child = self.parent.children[child_id]
                _append_event(
                    {
                        "event_type": "consumed",
                        "run_id": self.parent.run_id,
                        "child_id": child_id,
                        "settled_usd": child.settled_usd,
                        "freeze": True,
                        "freeze_reason": self.parent.freeze_reason,
                    },
                    self.path,
                )
                _append_event(
                    {
                        "event_type": "frozen",
                        "run_id": self.parent.run_id,
                        "freeze_reason": self.parent.freeze_reason,
                    },
                    self.path,
                )
                raise
            _append_event(
                {
                    "event_type": "settled",
                    "run_id": self.parent.run_id,
                    "child_id": child.child_id,
                    "actual_usd": child.settled_usd,
                },
                self.path,
            )
            return child

    def consume_child_ceiling(self, child_id: str, *, reason: str) -> ChildCallSlot:
        with _lock:
            child = self.parent.consume_child_ceiling(child_id, reason=reason)
            _append_event(
                {
                    "event_type": "consumed",
                    "run_id": self.parent.run_id,
                    "child_id": child.child_id,
                    "settled_usd": child.settled_usd,
                    "reason": reason,
                    "freeze": False,
                },
                self.path,
            )
            return child

    def cancel_child(self, child_id: str) -> ChildCallSlot:
        with _lock:
            child = self.parent.cancel_child(child_id)
            _append_event(
                {
                    "event_type": "cancelled",
                    "run_id": self.parent.run_id,
                    "child_id": child.child_id,
                },
                self.path,
            )
            return child

    def close(self) -> None:
        with _lock:
            self.parent.close()
            _append_event(
                {
                    "event_type": "closed",
                    "run_id": self.parent.run_id,
                    "settled_usd": self.parent.settled_usd(),
                },
                self.path,
            )

    def to_dict(self) -> dict[str, Any]:
        return self.parent.to_dict()


__all__ = [
    "PARENT_BUDGET_KIND",
    "PARENT_BUDGET_SCHEMA_VERSION",
    "DurableParentBudget",
    "load_parent_budget_events",
    "open_gated_lifecycle_budget",
    "parent_budget_log_path",
    "replay_parent_budget",
]
