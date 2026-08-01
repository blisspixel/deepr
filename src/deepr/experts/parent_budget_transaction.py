"""Shared parent budget transaction for multi-call metered expert runs.

ROADMAP requires every gated metered lifecycle surface to share one durable
per-call and run-budget transaction. This module is the pure coordination
layer:

- One parent ceiling binds every nested child maximum.
- Child admissions cannot oversubscribe remaining parent headroom.
- Dispatch marks and settlements are one-use per child.
- The module never contacts a provider and never flips execution flags.

Adoption by individual surfaces remains fail-closed until each surface wires
this transaction through reserve / mark / settle with hermetic tests.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from deepr.experts.maximum_charge_contract import ABSOLUTE_DEEPR_CEILING_USD


class ParentBudgetError(ValueError):
    """Raised when a parent or child budget transition is invalid."""


class ParentBudgetState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    FROZEN = "frozen"


class ChildCallState(StrEnum):
    ADMITTED = "admitted"
    DISPATCH_MARKED = "dispatch_marked"
    SETTLED = "settled"
    CONSUMED = "consumed"
    CANCELLED = "cancelled"


@dataclass
class ChildCallSlot:
    """One nested call under a parent run ceiling."""

    child_id: str
    operation: str
    max_usd: float
    state: ChildCallState = ChildCallState.ADMITTED
    settled_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "operation": self.operation,
            "max_usd": self.max_usd,
            "state": self.state.value,
            "settled_usd": self.settled_usd,
            "metadata": dict(self.metadata),
        }


@dataclass
class ParentBudgetTransaction:
    """In-process parent budget authority for a multi-call metered run."""

    run_id: str
    parent_ceiling_usd: float
    surface: str
    state: ParentBudgetState = ParentBudgetState.OPEN
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    children: dict[str, ChildCallSlot] = field(default_factory=dict)
    freeze_reason: str = ""
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)

    def remaining_usd(self) -> float:
        """Return parent headroom not yet admitted or settled conservatively."""
        reserved = 0.0
        for child in self.children.values():
            if child.state in {ChildCallState.CANCELLED}:
                continue
            if child.state in {ChildCallState.SETTLED, ChildCallState.CONSUMED}:
                reserved += float(child.settled_usd)
            else:
                reserved += float(child.max_usd)
        return max(0.0, float(self.parent_ceiling_usd) - reserved)

    def admitted_max_usd(self) -> float:
        return sum(float(child.max_usd) for child in self.children.values() if child.state != ChildCallState.CANCELLED)

    def settled_usd(self) -> float:
        return sum(
            float(child.settled_usd)
            for child in self.children.values()
            if child.state in {ChildCallState.SETTLED, ChildCallState.CONSUMED}
        )

    def admit_child(
        self,
        *,
        operation: str,
        max_usd: float,
        child_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ChildCallSlot:
        """Admit one child under remaining parent headroom."""
        with self._lock:
            self._require_open()
            ceiling = _positive_money(max_usd, field_name="max_usd")
            if ceiling > self.remaining_usd() + 1e-12:
                raise ParentBudgetError(
                    f"child max_usd ${ceiling:.6f} exceeds remaining parent headroom ${self.remaining_usd():.6f}"
                )
            slot = ChildCallSlot(
                child_id=child_id or f"child-{uuid4().hex}",
                operation=str(operation or "").strip() or "unnamed",
                max_usd=ceiling,
                metadata=dict(metadata or {}),
            )
            if slot.child_id in self.children:
                raise ParentBudgetError(f"child_id {slot.child_id!r} already admitted")
            self.children[slot.child_id] = slot
            return slot

    def mark_dispatch(self, child_id: str) -> ChildCallSlot:
        """Mark durable dispatch intent for one admitted child (still local)."""
        with self._lock:
            self._require_open()
            child = self._child(child_id)
            if child.state != ChildCallState.ADMITTED:
                raise ParentBudgetError(f"child {child_id!r} cannot mark dispatch from state {child.state.value}")
            child.state = ChildCallState.DISPATCH_MARKED
            return child

    def settle_child(self, child_id: str, actual_usd: float) -> ChildCallSlot:
        """Settle exact usage that does not exceed the child maximum."""
        with self._lock:
            self._require_open()
            child = self._child(child_id)
            if child.state not in {ChildCallState.ADMITTED, ChildCallState.DISPATCH_MARKED}:
                raise ParentBudgetError(f"child {child_id!r} cannot settle from state {child.state.value}")
            actual = _non_negative_money(actual_usd, field_name="actual_usd")
            if actual > child.max_usd + 1e-12:
                self.state = ParentBudgetState.FROZEN
                self.freeze_reason = f"child {child_id!r} actual ${actual:.6f} exceeded max ${child.max_usd:.6f}"
                child.settled_usd = child.max_usd
                child.state = ChildCallState.CONSUMED
                raise ParentBudgetError(self.freeze_reason)
            child.settled_usd = actual
            child.state = ChildCallState.SETTLED
            return child

    def consume_child_ceiling(self, child_id: str, *, reason: str) -> ChildCallSlot:
        """Conservatively consume the full child maximum (ambiguous usage)."""
        with self._lock:
            self._require_open()
            child = self._child(child_id)
            if child.state in {ChildCallState.SETTLED, ChildCallState.CONSUMED, ChildCallState.CANCELLED}:
                raise ParentBudgetError(f"child {child_id!r} cannot consume from state {child.state.value}")
            child.settled_usd = child.max_usd
            child.state = ChildCallState.CONSUMED
            child.metadata["consume_reason"] = str(reason or "conservative_consume")
            return child

    def cancel_child(self, child_id: str) -> ChildCallSlot:
        """Cancel an admitted child that never dispatched."""
        with self._lock:
            self._require_open()
            child = self._child(child_id)
            if child.state != ChildCallState.ADMITTED:
                raise ParentBudgetError(f"child {child_id!r} cannot cancel from state {child.state.value}")
            child.state = ChildCallState.CANCELLED
            child.settled_usd = 0.0
            return child

    def close(self) -> None:
        """Close the parent after all children are terminal."""
        with self._lock:
            if self.state == ParentBudgetState.FROZEN:
                raise ParentBudgetError("frozen parent cannot close cleanly; reconcile first")
            open_children = [
                child.child_id
                for child in self.children.values()
                if child.state in {ChildCallState.ADMITTED, ChildCallState.DISPATCH_MARKED}
            ]
            if open_children:
                raise ParentBudgetError(f"cannot close parent while children remain open: {', '.join(open_children)}")
            self.state = ParentBudgetState.CLOSED

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "run_id": self.run_id,
                "surface": self.surface,
                "state": self.state.value,
                "parent_ceiling_usd": self.parent_ceiling_usd,
                "remaining_usd": self.remaining_usd(),
                "admitted_max_usd": self.admitted_max_usd(),
                "settled_usd": self.settled_usd(),
                "freeze_reason": self.freeze_reason,
                "created_at": self.created_at.isoformat(),
                "children": [child.to_dict() for child in self.children.values()],
            }

    def _child(self, child_id: str) -> ChildCallSlot:
        try:
            return self.children[child_id]
        except KeyError as exc:
            raise ParentBudgetError(f"unknown child_id {child_id!r}") from exc

    def _require_open(self) -> None:
        if self.state == ParentBudgetState.FROZEN:
            raise ParentBudgetError(f"parent budget is frozen: {self.freeze_reason or 'unknown'}")
        if self.state != ParentBudgetState.OPEN:
            raise ParentBudgetError(f"parent budget is {self.state.value}")


def open_parent_budget_transaction(
    *,
    surface: str,
    parent_ceiling_usd: float,
    run_id: str | None = None,
) -> ParentBudgetTransaction:
    """Open one parent transaction under the absolute Deepr ceiling."""
    ceiling = _positive_money(parent_ceiling_usd, field_name="parent_ceiling_usd")
    if ceiling > ABSOLUTE_DEEPR_CEILING_USD + 1e-12:
        raise ParentBudgetError(
            f"parent_ceiling_usd ${ceiling:.4f} exceeds absolute Deepr ceiling ${ABSOLUTE_DEEPR_CEILING_USD:.2f}"
        )
    name = str(surface or "").strip()
    if not name:
        raise ParentBudgetError("surface must be a non-empty string")
    return ParentBudgetTransaction(
        run_id=run_id or f"run-{uuid4().hex}",
        parent_ceiling_usd=ceiling,
        surface=name,
    )


def _positive_money(value: object, *, field_name: str) -> float:
    amount = _non_negative_money(value, field_name=field_name)
    if amount <= 0:
        raise ParentBudgetError(f"{field_name} must be positive")
    return amount


def _non_negative_money(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParentBudgetError(f"{field_name} must be a finite non-negative number")
    amount = float(value)
    if not math.isfinite(amount) or amount < 0:
        raise ParentBudgetError(f"{field_name} must be a finite non-negative number")
    return amount


# Lifecycle surfaces that must adopt this parent transaction before metered
# execution can be considered. Inventory only - not an enable list. Names match
# ``require_metered_expert_mutation`` operation strings used in production call
# sites so gate payloads and open_gated_lifecycle_budget share one vocabulary.
GATED_METERED_LIFECYCLE_SURFACES: tuple[str, ...] = (
    "api_curriculum_generation",
    "api_autonomous_learning",
    "api_expert_chat_council",
    "api_expert_chat_plan",
    "api_expert_portrait",
    "api_provider_benchmark",
    "api_consult_quality_judge",
    "api_expert_sync",
    "api_sync_compile_claims",
    "api_expert_sync_all",
    "api_eval_calibrate_corpus",
    "api_knowledge_synthesis",
    "api_knowledge_synthesis_extraction",
    "api_expert_task_planner",
    "composed_docs_analysis",
    "multi_agent_team_research",
    "hosted_expert_vector_upload",
    # Planned ROADMAP names retained for design docs until call sites rename.
    "expert_make_nonlocal",
    "expert_make_learn",
    "expert_refresh",
    "expert_refresh_synthesize",
    "expert_resume",
    "expert_reflect",
    "mcp_deepr_reflect",
    "fill_gaps",
    "fill_gaps_consensus",
    "fill_gaps_deep",
    "paid_portraits",
)


def surface_requires_parent_budget(surface: str) -> bool:
    return str(surface or "").strip() in GATED_METERED_LIFECYCLE_SURFACES


__all__ = [
    "GATED_METERED_LIFECYCLE_SURFACES",
    "ChildCallSlot",
    "ChildCallState",
    "ParentBudgetError",
    "ParentBudgetState",
    "ParentBudgetTransaction",
    "open_parent_budget_transaction",
    "surface_requires_parent_budget",
]
