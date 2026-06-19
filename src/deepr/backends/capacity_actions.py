"""Ranked next actions for making cheap capacity usable.

This is the quality-of-life layer over the capacity waterfall. It performs no
research and makes no paid calls. It explains what is currently blocking the
owned-capacity path and gives the next safe command to run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from deepr.backends import admission
from deepr.backends.capacity import BackendKind, CapacitySource, available_local_models, detect_capacity
from deepr.backends.waterfall import choose_maintenance_backend


@dataclass(frozen=True)
class CapacityNextAction:
    """One ranked operator action."""

    rank: int
    status: str
    title: str
    detail: str
    command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "status": self.status,
            "title": self.title,
            "detail": self.detail,
            "command": self.command,
        }


@dataclass(frozen=True)
class CapacityJobContext:
    """Concrete job shape for capacity guidance.

    This is deterministic command/planning context only. It never decides
    semantic quality and never runs the job.
    """

    task_class: str = admission.TASK_CLASS_SYNC
    expert_name: str = "<expert>"
    report_id: str = "<report_id>"
    context_mode: str = "none"
    scheduled: bool = False

    @property
    def requires_local(self) -> bool:
        return self.task_class == admission.TASK_CLASS_SYNC and self.context_mode in {"fresh", "deep"}

    @property
    def context_label(self) -> str:
        if self.context_mode == "none":
            return "no local context requested"
        return f"{self.context_mode} local context requested"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_class": self.task_class,
            "expert_name": self.expert_name,
            "report_id": self.report_id,
            "context_mode": self.context_mode,
            "scheduled": self.scheduled,
            "requires_local": self.requires_local,
        }


def build_capacity_next_actions(
    *,
    task_class: str = admission.TASK_CLASS_SYNC,
    job_context: CapacityJobContext | None = None,
    now: datetime | None = None,
    capacity_sources: list[CapacitySource] | None = None,
    local_models: list[str] | None = None,
    admissions_path: Path | None = None,
    benchmarks_dir: Path = admission.DEFAULT_BENCHMARKS_DIR,
    quality_floor: float = admission.DEFAULT_LOCAL_EVAL_MIN_SCORE,
) -> list[CapacityNextAction]:
    """Return ranked next actions for the given capacity task class."""
    if job_context is not None and job_context.task_class != task_class:
        raise ValueError("job_context.task_class must match task_class")
    context = job_context or CapacityJobContext(task_class=task_class)
    _validate_job_context(context)
    sources = capacity_sources if capacity_sources is not None else detect_capacity()
    models = local_models if local_models is not None else available_local_models()
    choice = choose_maintenance_backend(
        context.task_class,
        now=now,
        available_models_fn=lambda: models,
        admissions_path=admissions_path,
        quality_floor=quality_floor,
    )

    actions: list[CapacityNextAction] = []
    if choice.is_local:
        actions.append(
            CapacityNextAction(
                1,
                "ready",
                "Automatic local routing is ready",
                _ready_detail(choice.reason, context),
                _expert_command(context, local=True),
            )
        )
        return actions

    actions.append(CapacityNextAction(1, "blocked", "Automatic local routing is blocked", choice.reason))
    actions.extend(_local_setup_actions(sources, models))
    actions.extend(_latest_eval_actions(context.task_class, benchmarks_dir, quality_floor, models))
    actions.extend(_wait_actions(context))
    if not context.requires_local:
        actions.extend(_fallback_actions(context, sources))
    return sorted(actions, key=lambda action: action.rank)


def _validate_job_context(context: CapacityJobContext) -> None:
    if context.context_mode not in {"none", "fresh", "deep"}:
        raise ValueError("context_mode must be one of: none, fresh, deep")
    if context.task_class != admission.TASK_CLASS_SYNC and context.context_mode != "none":
        raise ValueError("context_mode is only supported for sync task-class previews")


def _ready_detail(reason: str, context: CapacityJobContext) -> str:
    if context.context_mode == "none":
        return reason
    return f"{reason}; {context.context_label}"


def _local_setup_actions(sources: list[CapacitySource], models: list[str]) -> list[CapacityNextAction]:
    local_running = any(source.kind == BackendKind.LOCAL and source.available for source in sources)
    if not local_running:
        return [
            CapacityNextAction(
                2,
                "setup",
                "Start local capacity",
                "Ollama is not reachable, so no owned-hardware model can be evaluated or admitted.",
                "ollama serve",
            ),
            CapacityNextAction(
                3,
                "verify",
                "Probe local capacity",
                "After starting Ollama, confirm Deepr can reach it without spending.",
                "deepr capacity --probe",
            ),
        ]

    if not models:
        return [
            CapacityNextAction(
                2,
                "setup",
                "Pull a local model",
                "Ollama is running, but no local models are available to evaluate.",
                "ollama pull llama3.1",
            )
        ]

    return [
        CapacityNextAction(
            4,
            "evaluate",
            "Run a saved local eval",
            "Local models are available, but automatic routing needs scored evidence before it will use them.",
            "deepr eval local --max-models 2 --max-prompts 2 --save",
        )
    ]


def _latest_eval_actions(
    task_class: str,
    benchmarks_dir: Path,
    quality_floor: float,
    models: list[str],
) -> list[CapacityNextAction]:
    try:
        artifact = admission.latest_local_eval_artifact(benchmarks_dir)
    except admission.AdmissionEvidenceError:
        return []

    try:
        evidence = admission.load_local_eval_evidence(artifact, min_score=quality_floor)
    except admission.AdmissionEvidenceError as exc:
        return [
            CapacityNextAction(
                5,
                "evaluate",
                "Refresh the local eval",
                f"Latest saved eval artifact cannot be admitted: {exc}",
                "deepr eval local --max-models 2 --max-prompts 2 --save",
            )
        ]

    actions: list[CapacityNextAction] = []
    if evidence.model not in models:
        actions.append(
            CapacityNextAction(
                5,
                "setup",
                "Pull the latest eval winner",
                f"Latest admissible artifact selected {evidence.model!r}, but it is not available in Ollama now.",
                f"ollama pull {evidence.model}",
            )
        )

    actions.append(
        CapacityNextAction(
            6,
            "admit",
            "Admit the latest local eval winner",
            f"{evidence.model!r} scored {evidence.score:.3f} in {artifact.name}.",
            f"deepr capacity admit --from-eval latest --task-class {task_class}",
        )
    )
    return actions


def _wait_actions(context: CapacityJobContext) -> list[CapacityNextAction]:
    if not context.scheduled and not context.requires_local:
        return []

    detail = (
        "This scheduled job should wait for owned/prepaid capacity instead of paying now."
        if context.scheduled
        else "Fresh/deep context sync requires a local backend; do not fall through to metered API for this job."
    )
    return [
        CapacityNextAction(
            8,
            "wait",
            "Wait for cheap capacity",
            detail,
        )
    ]


def _fallback_actions(context: CapacityJobContext, sources: list[CapacitySource]) -> list[CapacityNextAction]:
    if not any(source.kind == BackendKind.API_METERED and source.available for source in sources):
        return []
    return [
        CapacityNextAction(
            9,
            "fallback",
            "Metered API is available as last resort",
            "Use it only behind the explicit budget gate when local capacity is blocked.",
            _expert_command(context, local=False),
        )
    ]


def _expert_command(context: CapacityJobContext, *, local: bool) -> str:
    expert = _quote(context.expert_name)
    if context.task_class == admission.TASK_CLASS_ABSORB:
        flag = "--local" if local else "--api"
        return f"deepr expert absorb {expert} {context.report_id} {flag} -y"
    if local:
        context_flag = ""
        if context.context_mode == "fresh":
            context_flag = " --fresh-context"
        elif context.context_mode == "deep":
            context_flag = " --deep-context"
        return f"deepr expert sync {expert}{context_flag} -y"
    return f"deepr expert sync {expert} --api --budget 2.00 -y"


def _quote(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'
