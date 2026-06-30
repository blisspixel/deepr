"""Capacity-waterfall backend selection (v2.16).

Chooses which backend runs a piece of work so owned capacity is drained before
a metered API is ever touched (docs/design/capacity-waterfall.md). Three rungs,
cheapest first: an eval-admitted local Ollama model, then a prepaid plan-quota
CLI (codex/claude/opencode), then the metered API. The choice is a pure decision
plus a human-readable reason, so "why did this run on X" is always answerable (a
no-surprise-bills invariant).

The metered API is the explicit last resort. Local is chosen when a live
admission exists for the task class and the model is loaded. The plan-quota rung
is *auto-routed only* when an installed, ToS-clean CLI is in subscription auth
mode and has an observed, non-exhausted quota window; since vendor CLIs do not
expose trustworthy remaining quota, that gate stays closed by default and the
explicit ``--plan`` path (``choose_plan_quota_backend``) is how operators opt in.
``--local`` / ``--api`` overrides are handled by the caller.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from deepr.backends import admission
from deepr.backends.capacity import BackendKind, CostModel, available_local_models
from deepr.backends.quota_ledger import QuotaState, summarize_quota_state

# Plan-quota admissions share the local admission store, namespaced so the local
# rung never mistakes one for an Ollama model. Admission is necessary operator
# intent, but never sufficient for auto-routing: the plan rung also needs a
# trusted remaining-quota observation.
PLAN_ADMISSION_PREFIX = "plan:"
from deepr.backends.research_backend import ResearchBackend
from deepr.backends.selection import BackendSelection, BackendSelectionStatus, select_capacity_backend

BACKEND_LOCAL = "local"
BACKEND_PLAN_QUOTA = "plan_quota"
BACKEND_API_METERED = "api_metered"


@dataclass
class BackendChoice:
    """The selected backend, the local model (if any), and why."""

    backend: str
    model: str | None
    reason: str
    plan_backend_id: str | None = None

    @property
    def is_local(self) -> bool:
        return self.backend == BACKEND_LOCAL

    @property
    def is_plan_quota(self) -> bool:
        return self.backend == BACKEND_PLAN_QUOTA


def _metered(reason: str) -> BackendChoice:
    return BackendChoice(BACKEND_API_METERED, None, reason)


def choose_maintenance_backend(
    task_class: str,
    *,
    now: datetime | None = None,
    available_models_fn: Callable[[], list[str]] = available_local_models,
    admissions_path=None,
    quality_floor: float = admission.DEFAULT_LOCAL_EVAL_MIN_SCORE,
    which: Callable[[str], str | None] = shutil.which,
    plan_env: dict[str, str] | None = None,
    quota_ledger_path: Path | None = None,
) -> BackendChoice:
    """Pick the cheapest eligible backend: local, then plan-quota, then metered.

    Admission drives the local rung (not list order or an env var): of the local
    models admitted for ``task_class``, use one that Ollama currently has. When
    several qualify, ``DEEPR_LOCAL_MODEL`` breaks the tie if it is itself
    admitted, available, and clears the measured quality floor.

    When local is not selected, the plan-quota rung is considered: an installed,
    auto-routable (free-at-margin, ToS-clean) CLI in subscription auth mode with
    an observed, non-exhausted quota window. Because vendor CLIs do not expose
    trustworthy *remaining* quota, this stays gated off by default (no observed
    remaining -> not auto-routed); the explicit ``--plan`` path is how operators
    opt in today. Metered API is the explicit last resort.
    """

    def _fallback(reason: str) -> BackendChoice:
        plan = _choose_plan_quota(
            task_class,
            now=now,
            which=which,
            plan_env=plan_env,
            quota_ledger_path=quota_ledger_path,
            admissions_path=admissions_path,
        )
        return plan or _metered(reason)

    admitted = {
        a.model: a
        for a in admission.list_active(now=now, path=admissions_path)
        if a.task_class == task_class and not a.model.startswith(PLAN_ADMISSION_PREFIX)
    }
    if not admitted:
        return _fallback(
            f"no local model admitted for {task_class!r} "
            f"(admit one: deepr capacity admit <model> --task-class {task_class})"
        )

    available = set(available_models_fn())
    if not available:
        return _fallback(f"local Ollama not reachable; admitted model(s) {sorted(admitted)} unavailable")

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
        return _fallback(selection.reason)

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


def _plan_quota_backend(adapter) -> ResearchBackend:  # adapter: PlanQuotaAdapter
    return ResearchBackend(
        backend_id=adapter.backend_id,
        name=adapter.display_name,
        kind=BackendKind.PLAN_QUOTA,
        cost_model=adapter.cost_model,
        available=True,
        detail=adapter.value_note,
        task_classes=(),
        requires_quota_ledger=True,
        metadata={"plan_backend_id": adapter.backend_id},
    )


def _choose_plan_quota(
    task_class: str,
    *,
    now: datetime | None,
    which: Callable[[str], str | None],
    plan_env: dict[str, str] | None,
    quota_ledger_path: Path | None,
    admissions_path: Path | None,
) -> BackendChoice | None:
    """The plan-quota rung: installed, safe, admitted, and quota-observed.

    Admission records operator intent, but it does not replace a quota signal.
    Auto-routing to a plan CLI is allowed only when a trusted local ledger
    observation says usable quota remains. Without that, the explicit
    ``--plan`` path is the works-now route.
    """
    from deepr.backends.plan_quota.adapters import auto_routable_adapters

    env = plan_env if plan_env is not None else dict(os.environ)
    stamp = now or datetime.now(UTC)
    admitted = {
        a.model
        for a in admission.list_active(now=now, path=admissions_path)
        if a.task_class == task_class and a.model.startswith(PLAN_ADMISSION_PREFIX)
    }
    eligible_adapters = [
        adapter
        for adapter in auto_routable_adapters()
        if which(adapter.exe) is not None
        and f"{PLAN_ADMISSION_PREFIX}{adapter.backend_id}" in admitted
        and _auto_routable(adapter, env)
    ]
    if not eligible_adapters:
        return None

    backends = [_plan_quota_backend(adapter) for adapter in eligible_adapters]
    # Reset-expired exhaustion events are ignored, but an active trusted
    # remaining-quota observation is still required before auto-routing.
    states = [s for s in summarize_quota_state(quota_ledger_path) if not _exhaustion_cleared(s, stamp)]
    selection = select_capacity_backend(
        backends,
        quota_states=states,
        task_class=task_class,
        require_observed_quota=True,
    )
    if selection.status != BackendSelectionStatus.SELECTED or selection.selected is None:
        return None

    picked = selection.selected.backend.backend_id
    return BackendChoice(
        BACKEND_PLAN_QUOTA,
        None,
        f"plan-quota backend {picked!r} (operator-admitted, quota-observed): "
        f"{selection.selected.eligibility.reason}; prepaid capacity before metered API",
        plan_backend_id=picked,
    )


def _exhaustion_cleared(state: QuotaState, now: datetime) -> bool:
    """True when an exhaustion observation's reset time has passed (no longer blocks)."""
    event = state.latest_event
    return state.exhausted and event.reset_at is not None and event.reset_at <= now


def _auto_routable(adapter, env: dict[str, str]) -> bool:  # adapter: PlanQuotaAdapter
    from deepr.backends.plan_quota.safety import evaluate_plan_quota_safety

    decision = evaluate_plan_quota_safety(adapter, env=env)
    return decision.safe and not decision.requires_ack


def choose_plan_quota_backend(
    backend_id: str,
    *,
    env: dict[str, str] | None = None,
    allow_metered_at_margin: bool = False,
) -> BackendChoice:
    """Resolve an explicit ``--plan <id>`` request into a vetted BackendChoice.

    Unlike the auto rung, an explicit operator request does not require an
    observed quota window (the operator chose it), but it still passes the
    deterministic safety gate (auth mode is plan, billing acknowledged).
    """
    from deepr.backends.plan_quota.adapters import get_adapter
    from deepr.backends.plan_quota.safety import evaluate_plan_quota_safety

    adapter = get_adapter(backend_id)
    if adapter is None:
        return _metered(f"unknown plan-quota backend {backend_id!r}")

    decision = evaluate_plan_quota_safety(adapter, env=env if env is not None else dict(os.environ))
    if not decision.safe:
        return _metered(decision.reason)
    if decision.requires_ack and not allow_metered_at_margin:
        return _metered(
            f"{adapter.display_name} is metered at the margin and requires explicit paid-capacity acknowledgement"
        )
    return BackendChoice(BACKEND_PLAN_QUOTA, None, decision.reason, plan_backend_id=backend_id)
