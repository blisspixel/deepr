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

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from deepr.backends import admission
from deepr.backends.local import default_local_model

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


def choose_maintenance_backend(
    task_class: str,
    *,
    now: datetime | None = None,
    local_model_fn: Callable[[], str | None] = default_local_model,
    admissions_path=None,
) -> BackendChoice:
    """Pick local (if admitted and available) else metered API, for maintenance.

    ``local_model_fn`` resolves the available local model (probes Ollama by
    default; injectable for tests). A local model is used only when it has a
    live admission for ``task_class`` - the eval-gated rung of the waterfall.
    """
    model = local_model_fn()
    if not model:
        return BackendChoice(BACKEND_API_METERED, None, "no local model available")
    adm = admission.active_admission(model, task_class, now=now, path=admissions_path)
    if adm is None:
        return BackendChoice(
            BACKEND_API_METERED,
            None,
            f"local model {model!r} not admitted for {task_class!r} "
            f"(admit it: deepr capacity admit {model} --task-class {task_class})",
        )
    expiry = adm.expires_at.strftime("%Y-%m-%d") if adm.expires_at else "never"
    return BackendChoice(
        BACKEND_LOCAL,
        model,
        f"local model {model!r} admitted for {task_class!r} (expires {expiry}); owned capacity before metered API",
    )
