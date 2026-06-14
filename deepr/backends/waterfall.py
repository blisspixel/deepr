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
from deepr.backends.capacity import available_local_models

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
) -> BackendChoice:
    """Pick an admitted, currently-available local model else metered API.

    Admission drives selection (not list order or an env var): of the local
    models admitted for ``task_class``, use one that Ollama currently has. When
    several qualify, ``DEEPR_LOCAL_MODEL`` breaks the tie if it is itself
    admitted and available. No admission, or the admitted model not loaded,
    falls through to the metered API - the explicit last resort.
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

    pref = os.getenv("DEEPR_LOCAL_MODEL")
    if pref and pref in admitted and pref in available:
        pick = pref
    else:
        pick = next((m for m in admitted if m in available), None)
    if pick is None:
        return _metered(f"admitted local model(s) {sorted(admitted)} not currently loaded in Ollama")

    adm = admitted[pick]
    expiry = adm.expires_at.strftime("%Y-%m-%d") if adm.expires_at else "never"
    return BackendChoice(
        BACKEND_LOCAL,
        pick,
        f"local model {pick!r} admitted for {task_class!r} (expires {expiry}); owned capacity before metered API",
    )
