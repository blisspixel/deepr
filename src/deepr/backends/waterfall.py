"""Capacity-waterfall backend selection (v2.16).

Chooses which backend runs a piece of work so owned capacity is drained before
a metered API is ever touched (docs/design/capacity-waterfall.md). Today the
waterfall has two rungs that are actually wired - an eval-admitted local model
and the metered API; plan-quota CLI adapters slot in between later. The choice
is a pure decision plus a human-readable reason, so "why did this run on X" is
always answerable (a no-surprise-bills invariant).

The metered API is the explicit last resort: local is chosen only when a live
admission exists for the task class (see ``admission``) and a local model is
actually available. No admission, or no local model, falls through to metered.
``--local`` / ``--api`` overrides are handled by the caller; this is the
automatic path.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from deepr.backends import admission
from deepr.backends.capacity import BackendKind, CostModel, available_local_models
from deepr.backends.research_backend import ResearchBackend
from deepr.backends.selection import BackendSelection, BackendSelectionStatus, select_capacity_backend

BACKEND_LOCAL = "local"
BACKEND_API_METERED = "api_metered"


@dataclass
class BackendChoice:
    """The selected backend, the local model (if any), and why."""

    backend: str
    model: str | None
    reason: str

    @property
    def is_local(self) -> bool:
        return self.backend == BACKEND_LOCAL


def _metered(reason: str) -> BackendChoice:
    return BackendChoice(BACKEND_API_METERED, None, reason)


def choose_maintenance_backend(
    task_class: str,
    *,
    now: datetime | None = None,
    available_models_fn: Callable[[], list[str]] = available_local_models,
    admissions_path=None,
    quality_floor: float = admission.DEFAULT_LOCAL_EVAL_MIN_SCORE,
) -> BackendChoice:
    """Pick an admitted, currently-available local model else metered API.

    Admission drives selection (not list order or an env var): of the local
    models admitted for ``task_class``, use one that Ollama currently has. When
    several qualify, ``DEEPR_LOCAL_MODEL`` breaks the tie if it is itself
    admitted, available, and clears the measured quality floor. No admission,
    no measured score, or the admitted model not loaded falls through to the
    metered API - the explicit last resort.
    """
    admitted = {a.model: a for a in admission.list_active(now=now, path=admissions_path) if a.task_class == task_class}
    if not admitted:
        return _metered(
            f"no local model admitted for {task_class!r} "
            f"(admit one: deepr capacity admit <model> --task-class {task_class})"
        )

    available = set(available_models_fn())
    if not available:
        return _metered(f"local Ollama not reachable; admitted model(s) {sorted(admitted)} unavailable")

    local_backends = [_admission_backend(adm, available=adm.model in available) for adm in admitted.values()]
    quality_scores = _quality_scores(local_backends, admitted)

    pref = os.getenv("DEEPR_LOCAL_MODEL")
    preferred_selection = _preferred_selection(
        pref,
        local_backends=local_backends,
        quality_scores=quality_scores,
        task_class=task_class,
        quality_floor=quality_floor,
    )
    selection = preferred_selection or select_capacity_backend(
        local_backends,
        task_class=task_class,
        quality_floor=quality_floor,
        quality_scores=quality_scores,
    )
    if selection.status != BackendSelectionStatus.SELECTED or selection.selected is None:
        return _metered(selection.reason)

    pick = str(selection.selected.backend.metadata["model"])
    adm = admitted[pick]
    expiry = adm.expires_at.strftime("%Y-%m-%d") if adm.expires_at else "never"
    return BackendChoice(
        BACKEND_LOCAL,
        pick,
        f"local model {pick!r} admitted for {task_class!r} (expires {expiry}); "
        f"{selection.selected.quality_gate.reason}; owned capacity before metered API",
    )


def _preferred_selection(
    preferred_model: str | None,
    *,
    local_backends: list[ResearchBackend],
    quality_scores: dict[str, float],
    task_class: str,
    quality_floor: float,
) -> BackendSelection | None:
    """Select the env-preferred model only when it clears every gate."""
    if not preferred_model:
        return None
    preferred = [backend for backend in local_backends if backend.metadata.get("model") == preferred_model]
    if not preferred:
        return None
    selection = select_capacity_backend(
        preferred,
        task_class=task_class,
        quality_floor=quality_floor,
        quality_scores=quality_scores,
    )
    return selection if selection.status == BackendSelectionStatus.SELECTED else None


def _admission_backend(adm: admission.Admission, *, available: bool) -> ResearchBackend:
    detail = "loaded in local Ollama" if available else "admitted model is not loaded in local Ollama"
    return ResearchBackend(
        backend_id=_local_backend_id(adm.model),
        name=f"Ollama local model {adm.model}",
        kind=BackendKind.LOCAL,
        cost_model=CostModel.OWNED_HARDWARE,
        available=available,
        detail=detail,
        task_classes=(adm.task_class,),
        requires_quota_ledger=False,
        metadata={
            "model": adm.model,
            "admission_score": adm.score,
            "admission_expires_at": adm.expires_at.isoformat() if adm.expires_at else None,
        },
    )


def _local_backend_id(model: str) -> str:
    return f"local-ollama:{model}"


def _quality_scores(backends: list[ResearchBackend], admissions: dict[str, admission.Admission]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for backend in backends:
        model = str(backend.metadata["model"])
        score = admissions[model].score
        if isinstance(score, bool) or score is None or score < 0.0 or score > 1.0:
            continue
        scores[backend.backend_id] = score
    return scores
