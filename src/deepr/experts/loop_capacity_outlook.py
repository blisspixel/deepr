"""Non-probing capacity outlook for an expert's next maintenance loop run.

Reads the durable admission ledger only - no live Ollama or plan-quota probe -
so a read-only loop-status view can tell an operator whether cheap ($0 local or
prepaid plan) capacity is *admitted* for each maintenance task class, or whether
the next run would fall to metered API budget.

"Admitted" is a durable eligibility fact, not a liveness guarantee: a local
model must still be loaded (confirm with ``deepr capacity --probe``) and plan
auto-routing also needs an observed quota window. An explicit ``--local``/
``--plan`` selects that rung directly, though a ``--plan`` request still clears
the no-surprise-bills safety gate, which can itself fall back to metered. The
split follows AGENTIC_BALANCE: this is deterministic form (reading recorded
admission state), never a judgment.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from deepr.backends import admission
from deepr.backends.waterfall import PLAN_ADMISSION_PREFIX

# The maintenance task classes an expert's loops run under (recurring sync,
# one-shot absorb, gap-fill, and reflection). Kept explicit so the outlook always
# reports the same class set even when the ledger has no admission for one.
LOOP_TASK_CLASSES = (
    admission.TASK_CLASS_SYNC,
    admission.TASK_CLASS_ABSORB,
    admission.TASK_CLASS_GAP_FILL,
    admission.TASK_CLASS_REFLECT,
)


def build_capacity_outlook(*, now: datetime | None = None, admissions_path: Path | None = None) -> dict[str, Any]:
    """Summarize admitted $0/prepaid capacity per maintenance task class.

    Pure read of the admission ledger (no provider probe, no model call). For
    each task class it reports whether a local model and/or a plan-quota backend
    is currently admitted, plus their identifiers, and a top-level flag for
    whether any cheap capacity is admitted at all. Plan admissions are stored in
    the same ledger with a ``plan:`` model prefix; the prefix is what separates a
    prepaid-plan rung from a local Ollama rung within one task class.
    """
    active = admission.list_active(now=now, path=admissions_path)

    local_by_class: dict[str, set[str]] = {}
    plan_by_class: dict[str, set[str]] = {}
    for adm in active:
        if adm.model.startswith(PLAN_ADMISSION_PREFIX):
            plan_by_class.setdefault(adm.task_class, set()).add(adm.model.removeprefix(PLAN_ADMISSION_PREFIX))
        else:
            local_by_class.setdefault(adm.task_class, set()).add(adm.model)

    task_classes: dict[str, Any] = {}
    for task_class in LOOP_TASK_CLASSES:
        local_models = sorted(local_by_class.get(task_class, set()))
        plan_backends = sorted(plan_by_class.get(task_class, set()))
        task_classes[task_class] = {
            "local_capacity_admitted": bool(local_models),
            "plan_capacity_admitted": bool(plan_backends),
            "admitted_local_models": local_models,
            "admitted_plan_backends": plan_backends,
        }

    any_admitted = any(
        entry["local_capacity_admitted"] or entry["plan_capacity_admitted"] for entry in task_classes.values()
    )
    return {
        "read_only": True,
        "probe_free": True,
        "any_cheap_capacity_admitted": any_admitted,
        "task_classes": task_classes,
        "note": (
            "Reflects admitted $0/prepaid capacity from the admission ledger only, with no "
            "live probe. 'Admitted' means a rung is eligible for that task class, not that it "
            "is reachable right now: a local model must be loaded (confirm with "
            "`deepr capacity --probe`) and plan auto-routing also needs an observed quota "
            "window. An explicit --local/--plan selects that rung (a --plan request still "
            "passes the no-surprise-bills safety gate, which can fall back to metered). No "
            "admission for a task class means a run of it falls to metered API budget."
        ),
    }


__all__ = ["LOOP_TASK_CLASSES", "build_capacity_outlook"]
