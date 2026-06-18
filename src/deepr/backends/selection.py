"""Pure capacity-waterfall selection for normalized research backends.

This module orders already-discovered backends by marginal cost, checks the
eligibility gate, and applies optional measured quality floors. It does not run
adapters, read provider state, or make network calls.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from deepr.backends.capacity import BackendKind, CostModel
from deepr.backends.eligibility import BackendEligibility, evaluate_backend_eligibility
from deepr.backends.quota_ledger import QuotaState
from deepr.backends.research_backend import ResearchBackend


class BackendQualityStatus(str, Enum):
    """Whether a backend clears the measured quality gate for a task."""

    NOT_REQUIRED = "not_required"
    PASSED = "passed"
    UNKNOWN = "unknown"
    BELOW_FLOOR = "below_floor"


class BackendSelectionStatus(str, Enum):
    """Overall backend-selection result."""

    SELECTED = "selected"
    NO_ELIGIBLE_BACKEND = "no_eligible_backend"


@dataclass(frozen=True)
class BackendQualityGate:
    """Quality-floor decision for one backend."""

    backend_id: str
    task_class: str
    score: float | None
    floor: float | None
    status: BackendQualityStatus
    reason: str

    @property
    def passed(self) -> bool:
        return self.status in {BackendQualityStatus.NOT_REQUIRED, BackendQualityStatus.PASSED}

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "task_class": self.task_class,
            "score": self.score,
            "floor": self.floor,
            "passed": self.passed,
            "status": self.status.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BackendCandidate:
    """One backend plus every gate result used to route it."""

    backend: ResearchBackend
    eligibility: BackendEligibility
    quality_gate: BackendQualityGate

    @property
    def eligible(self) -> bool:
        return self.eligibility.eligible

    @property
    def routable(self) -> bool:
        return self.eligibility.eligible and self.quality_gate.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend.to_dict(),
            "eligibility": self.eligibility.to_dict(),
            "quality_gate": self.quality_gate.to_dict(),
            "routable": self.routable,
        }


@dataclass(frozen=True)
class BackendSelection:
    """A deterministic capacity-waterfall selection result."""

    status: BackendSelectionStatus
    selected: BackendCandidate | None
    candidates: tuple[BackendCandidate, ...]
    reason: str

    @property
    def backend_id(self) -> str:
        return self.selected.backend.backend_id if self.selected else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "backend_id": self.backend_id,
            "reason": self.reason,
            "selected": self.selected.to_dict() if self.selected else None,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


_KIND_RANK = {
    BackendKind.LOCAL: 0,
    BackendKind.PLAN_QUOTA: 1,
    BackendKind.API_METERED: 2,
}

_COST_RANK = {
    CostModel.OWNED_HARDWARE: 0,
    CostModel.CREDIT_POOL: 1,
    CostModel.ROLLING_WINDOW: 2,
    CostModel.CALENDAR_WINDOW: 3,
    CostModel.METERED: 4,
}


def select_capacity_backend(
    backends: Iterable[ResearchBackend],
    *,
    quota_states: Iterable[QuotaState] = (),
    task_class: str = "",
    allow_metered: bool = False,
    require_observed_quota: bool = True,
    quality_floor: float | None = None,
    quality_scores: Mapping[str, float] | None = None,
) -> BackendSelection:
    """Select the first backend that clears waterfall, eligibility, and quality gates.

    ``quality_scores`` are measured evidence indexed by backend id. The selector
    only enforces numeric floors; it does not decide semantic quality.
    """
    _validate_optional_score("quality_floor", quality_floor)
    quality_scores = quality_scores or {}
    for backend_id, score in quality_scores.items():
        _validate_optional_score(f"quality_scores[{backend_id!r}]", score)

    ordered = sorted(backends, key=_backend_rank)
    quota_state_tuple = tuple(quota_states)
    candidates = tuple(
        BackendCandidate(
            backend=backend,
            eligibility=evaluate_backend_eligibility(
                backend,
                quota_states=quota_state_tuple,
                task_class=task_class,
                allow_metered=allow_metered,
                require_observed_quota=require_observed_quota,
            ),
            quality_gate=_evaluate_quality_gate(
                backend,
                task_class=task_class,
                floor=quality_floor,
                quality_scores=quality_scores,
            ),
        )
        for backend in ordered
    )

    selected = next((candidate for candidate in candidates if candidate.routable), None)
    if selected:
        return BackendSelection(
            status=BackendSelectionStatus.SELECTED,
            selected=selected,
            candidates=candidates,
            reason=(
                f"selected {selected.backend.backend_id}: {selected.eligibility.reason}; {selected.quality_gate.reason}"
            ),
        )

    return BackendSelection(
        status=BackendSelectionStatus.NO_ELIGIBLE_BACKEND,
        selected=None,
        candidates=candidates,
        reason=_blocked_reason(candidates),
    )


def _backend_rank(backend: ResearchBackend) -> tuple[int, int, str]:
    return (
        _KIND_RANK.get(backend.kind, 99),
        _COST_RANK.get(backend.cost_model, 99),
        backend.backend_id,
    )


def _evaluate_quality_gate(
    backend: ResearchBackend,
    *,
    task_class: str,
    floor: float | None,
    quality_scores: Mapping[str, float],
) -> BackendQualityGate:
    score = quality_scores.get(backend.backend_id)
    task_label = task_class or "unspecified"

    if floor is None:
        return BackendQualityGate(
            backend_id=backend.backend_id,
            task_class=task_class,
            score=score,
            floor=None,
            status=BackendQualityStatus.NOT_REQUIRED,
            reason=f"no measured quality floor required for {task_label}",
        )

    if score is None:
        return BackendQualityGate(
            backend_id=backend.backend_id,
            task_class=task_class,
            score=None,
            floor=floor,
            status=BackendQualityStatus.UNKNOWN,
            reason=f"{backend.backend_id} has no measured quality score for {task_label}",
        )

    if score < floor:
        return BackendQualityGate(
            backend_id=backend.backend_id,
            task_class=task_class,
            score=score,
            floor=floor,
            status=BackendQualityStatus.BELOW_FLOOR,
            reason=f"{backend.backend_id} quality {score:.3f} is below floor {floor:.3f} for {task_label}",
        )

    return BackendQualityGate(
        backend_id=backend.backend_id,
        task_class=task_class,
        score=score,
        floor=floor,
        status=BackendQualityStatus.PASSED,
        reason=f"{backend.backend_id} quality {score:.3f} clears floor {floor:.3f} for {task_label}",
    )


def _blocked_reason(candidates: tuple[BackendCandidate, ...]) -> str:
    if not candidates:
        return "no backends were provided"

    blocked = [
        (f"{candidate.backend.backend_id}: {candidate.eligibility.status.value}, {candidate.quality_gate.status.value}")
        for candidate in candidates
    ]
    return "no backend cleared eligibility and quality gates (" + "; ".join(blocked) + ")"


def _validate_optional_score(label: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or value < 0.0 or value > 1.0:
        raise ValueError(f"{label} must be between 0 and 1")
