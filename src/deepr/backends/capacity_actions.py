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


def build_capacity_next_actions(
    *,
    task_class: str = admission.TASK_CLASS_SYNC,
    now: datetime | None = None,
    capacity_sources: list[CapacitySource] | None = None,
    local_models: list[str] | None = None,
    admissions_path: Path | None = None,
    benchmarks_dir: Path = admission.DEFAULT_BENCHMARKS_DIR,
    quality_floor: float = admission.DEFAULT_LOCAL_EVAL_MIN_SCORE,
) -> list[CapacityNextAction]:
    """Return ranked next actions for the given capacity task class."""
    sources = capacity_sources if capacity_sources is not None else detect_capacity()
    models = local_models if local_models is not None else available_local_models()
    choice = choose_maintenance_backend(
        task_class,
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
                choice.reason,
                _expert_command(task_class, local=True),
            )
        )
        return actions

    actions.append(CapacityNextAction(1, "blocked", "Automatic local routing is blocked", choice.reason))
    actions.extend(_local_setup_actions(sources, models))
    actions.extend(_latest_eval_actions(task_class, benchmarks_dir, quality_floor, models))
    actions.extend(_fallback_actions(task_class, sources))
    return sorted(actions, key=lambda action: action.rank)


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


def _fallback_actions(task_class: str, sources: list[CapacitySource]) -> list[CapacityNextAction]:
    if not any(source.kind == BackendKind.API_METERED and source.available for source in sources):
        return []
    return [
        CapacityNextAction(
            9,
            "fallback",
            "Metered API is available as last resort",
            "Use it only behind the explicit budget gate when local capacity is blocked.",
            _expert_command(task_class, local=False),
        )
    ]


def _expert_command(task_class: str, *, local: bool) -> str:
    if task_class == admission.TASK_CLASS_ABSORB:
        flag = "--local" if local else "--api"
        return f'deepr expert absorb "<expert>" <report_id> {flag} -y'
    if local:
        return 'deepr expert sync "<expert>" --fresh-context -y'
    return 'deepr expert sync "<expert>" --api --budget 2.00 -y'
