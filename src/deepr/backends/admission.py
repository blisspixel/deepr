"""Eval-gated admission for local backends (capacity waterfall, v2.16).

The waterfall router prefers owned capacity (a local Ollama model at $0) over a
metered API - but only when that local model has been shown good enough for the
task. "It's free" must never override "it's good enough" (docs/design/
capacity-waterfall.md). An admission is the operator's explicit, dated record
that a given local model is acceptable for a given task class; the automatic
path uses local only while a live admission exists. ``--local`` stays a manual
override that needs no admission (the operator asked for it directly).

Admissions are machine-local, like the cost ledger: which local models exist
and how good they are depends on the hardware, so this never lives in the
portable experts dir (ADR 0004). Append-only JSONL, env-overridable via
``DEEPR_CAPACITY_DATA_DIR`` so tests isolate themselves from the real ledger.

Admissions expire (default 90 days): models and their quantizations change, so
an old admission must lapse and be re-earned rather than silently persist.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from deepr.config import runtime_data_path

# Task classes the maintenance commands admit against. Free-form strings are
# allowed, but these are the canonical ones so admit/check sites agree.
TASK_CLASS_SYNC = "sync"
TASK_CLASS_ABSORB = "absorb"
TASK_CLASS_GAP_FILL = "gap_fill"

DEFAULT_ADMISSION_DAYS = 90
DEFAULT_LOCAL_EVAL_MIN_SCORE = 0.70


def _default_benchmarks_dir() -> Path:
    return runtime_data_path("benchmarks")


DEFAULT_BENCHMARKS_DIR = _default_benchmarks_dir()


class AdmissionEvidenceError(ValueError):
    """Raised when an eval artifact cannot support local admission."""


@dataclass(frozen=True)
class LocalEvalAdmissionEvidence:
    """Validated evidence loaded from a saved local comparison artifact."""

    model: str
    score: float
    prompt_set: str
    judge_model: str
    methodology_version: str
    generated_at: str
    prompt_count: int
    task_classes: tuple[str, ...]
    artifact_path: Path
    winner: str

    def note(self) -> str:
        classes = ",".join(self.task_classes) if self.task_classes else "unknown"
        return (
            f"local eval {self.prompt_set} v{self.methodology_version}; "
            f"judge={self.judge_model}; score={self.score:.3f}; "
            f"prompts={self.prompt_count}; eval_task_classes={classes}; "
            f"artifact={self.artifact_path.name}"
        )


def default_capacity_data_dir() -> Path:
    """Resolve the machine-local capacity-data directory.

    Honors ``DEEPR_CAPACITY_DATA_DIR`` so deployments can relocate it and - as
    with the cost ledger - so the test suite isolates itself instead of writing
    admissions into the user's real ledger. Default is CWD-relative.
    """
    base = os.environ.get("DEEPR_CAPACITY_DATA_DIR", "").strip()
    return Path(base) if base else Path("data/capacity")


def admissions_path(path: Path | None = None) -> Path:
    return path or default_capacity_data_dir() / "admissions.jsonl"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def resolve_local_eval_artifact(value: str, *, benchmarks_dir: Path = DEFAULT_BENCHMARKS_DIR) -> Path:
    """Resolve an eval artifact path or the newest local comparison artifact."""
    if value.strip().lower() == "latest":
        return latest_local_eval_artifact(benchmarks_dir)
    path = Path(value)
    if not path.is_file():
        raise AdmissionEvidenceError(f"eval artifact not found: {value}")
    return path


def latest_local_eval_artifact(benchmarks_dir: Path = DEFAULT_BENCHMARKS_DIR) -> Path:
    """Return the newest ``deepr eval local --save`` artifact."""
    candidates = sorted(
        benchmarks_dir.glob("local_compare_*.json"),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    if not candidates:
        raise AdmissionEvidenceError(f"no local eval artifacts found under {benchmarks_dir}")
    return candidates[0]


def load_local_eval_evidence(
    artifact_path: Path,
    *,
    model: str | None = None,
    min_score: float = DEFAULT_LOCAL_EVAL_MIN_SCORE,
) -> LocalEvalAdmissionEvidence:
    """Load admission evidence from ``deepr eval local --save`` output.

    The model judge supplies semantic scoring. This loader only enforces the
    deterministic envelope: artifact shape, zero Deepr metered cost, score
    range, requested model match, minimum score, and no failed prompt attempts.
    """
    _validate_probability("min_score", min_score)
    payload = _load_eval_payload(artifact_path)
    _validate_zero_cost(
        payload.get("cost"),
        "artifact cost",
        "only zero-cost local eval artifacts can be used for local admission",
    )

    comparisons = payload.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        raise AdmissionEvidenceError("eval artifact has no model comparisons")

    selected = _select_eval_comparison(comparisons, model=model, winner=str(payload.get("winner") or ""))
    selected_model, score, prompt_results = _extract_selected_eval_result(selected, min_score=min_score)
    task_classes = _validate_prompt_results(selected_model, prompt_results)

    return LocalEvalAdmissionEvidence(
        model=selected_model,
        score=score,
        prompt_set=str(payload.get("prompt_set") or "unknown"),
        judge_model=str(payload.get("judge_model") or "unknown"),
        methodology_version=str(payload.get("methodology_version") or "unknown"),
        generated_at=str(payload.get("generated_at") or ""),
        prompt_count=len(prompt_results),
        task_classes=task_classes,
        artifact_path=artifact_path,
        winner=str(payload.get("winner") or ""),
    )


def _load_eval_payload(artifact_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AdmissionEvidenceError(f"could not read eval artifact: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AdmissionEvidenceError(f"eval artifact is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AdmissionEvidenceError("eval artifact must be a JSON object")
    return payload


def _validate_zero_cost(value: Any, label: str, message: str) -> None:
    cost = _as_float(value, label)
    if cost != 0.0:
        raise AdmissionEvidenceError(message)


def _extract_selected_eval_result(
    selected: dict[str, Any],
    *,
    min_score: float,
) -> tuple[str, float, list[Any]]:
    selected_model = _required_str(selected.get("model"), "comparison model")
    _validate_zero_cost(
        selected.get("cost"),
        f"{selected_model} comparison cost",
        "only zero-cost local model comparisons can be used for local admission",
    )
    score = _as_float(selected.get("average_score"), f"{selected_model} average_score")
    _validate_probability(f"{selected_model} average_score", score)
    if score < min_score:
        raise AdmissionEvidenceError(f"{selected_model} score {score:.3f} is below required minimum {min_score:.3f}")

    prompt_results = selected.get("prompt_results")
    if not isinstance(prompt_results, list) or not prompt_results:
        raise AdmissionEvidenceError(f"{selected_model} has no prompt results")
    return selected_model, score, prompt_results


def _validate_prompt_results(selected_model: str, prompt_results: list[Any]) -> tuple[str, ...]:
    errors = _failed_prompt_ids(prompt_results)
    if errors:
        raise AdmissionEvidenceError(f"{selected_model} has failed prompt results: {', '.join(errors)}")

    task_classes: set[str] = set()
    for index, result in enumerate(prompt_results, start=1):
        task_class = _validate_prompt_result(selected_model, index, result)
        if task_class:
            task_classes.add(task_class)
    return tuple(sorted(task_classes))


def _failed_prompt_ids(prompt_results: list[Any]) -> list[str]:
    return [
        str(result.get("prompt_id") or "?")
        for result in prompt_results
        if isinstance(result, dict) and result.get("error")
    ]


def _validate_prompt_result(selected_model: str, index: int, result: Any) -> str | None:
    if not isinstance(result, dict):
        raise AdmissionEvidenceError(f"{selected_model} prompt result {index} is not an object")
    verdict = result.get("verdict")
    if not isinstance(verdict, dict):
        raise AdmissionEvidenceError(f"{selected_model} prompt result {index} has no verdict")
    verdict_score = _as_float(verdict.get("score"), f"{selected_model} prompt result {index} score")
    _validate_probability(f"{selected_model} prompt result {index} score", verdict_score)
    task_class = result.get("task_class")
    return task_class if isinstance(task_class, str) and task_class else None


def _select_eval_comparison(comparisons: list[Any], *, model: str | None, winner: str) -> dict[str, Any]:
    objects = [comparison for comparison in comparisons if isinstance(comparison, dict)]
    if not objects:
        raise AdmissionEvidenceError("eval artifact comparisons are not objects")

    if model:
        selected = next((comparison for comparison in objects if comparison.get("model") == model), None)
        if selected is None:
            raise AdmissionEvidenceError(f"model {model!r} was not found in eval artifact")
        return selected

    if winner:
        selected = next((comparison for comparison in objects if comparison.get("model") == winner), None)
        if selected is not None:
            return selected

    return max(
        objects,
        key=lambda comparison: (
            _safe_score(comparison.get("average_score")),
            -int(comparison.get("average_latency_ms") or 0),
            str(comparison.get("model") or ""),
        ),
    )


def _required_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdmissionEvidenceError(f"{label} is required")
    return value


def _as_float(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise AdmissionEvidenceError(f"{label} must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AdmissionEvidenceError(f"{label} must be numeric") from exc


def _safe_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return -1.0
    return score if 0.0 <= score <= 1.0 else -1.0


def _validate_probability(label: str, value: float) -> None:
    if isinstance(value, bool) or value < 0.0 or value > 1.0:
        raise AdmissionEvidenceError(f"{label} must be between 0 and 1")


@dataclass
class Admission:
    """One admission-ledger event for a (model, task_class) pair.

    ``event`` is ``"admit"`` or ``"revoke"``; the most recent event for a pair
    decides whether it is currently admitted. ``expires_at`` is None for revoke.
    """

    model: str
    task_class: str
    recorded_at: datetime
    expires_at: datetime | None
    event: str = "admit"
    score: float | None = None
    note: str = ""

    def is_active(self, *, now: datetime) -> bool:
        """True if this event grants a live admission as of ``now``."""
        if self.event != "admit":
            return False
        return self.expires_at is None or now < self.expires_at

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "task_class": self.task_class,
            "recorded_at": self.recorded_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "event": self.event,
            "score": self.score,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Admission:
        exp = d.get("expires_at")
        return cls(
            model=str(d["model"]),
            task_class=str(d["task_class"]),
            recorded_at=datetime.fromisoformat(d["recorded_at"]),
            expires_at=datetime.fromisoformat(exp) if exp else None,
            event=str(d.get("event", "admit")),
            score=d.get("score"),
            note=str(d.get("note", "")),
        )


def load_events(path: Path | None = None) -> list[Admission]:
    """Read all admission events in recorded order. Missing file -> empty."""
    p = admissions_path(path)
    if not p.exists():
        return []
    events: list[Admission] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(Admission.from_dict(json.loads(line)))
        except (json.JSONDecodeError, KeyError, ValueError):
            # A corrupt line must not break routing; skip it.
            continue
    return events


def _append(event: Admission, path: Path | None = None) -> None:
    p = admissions_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    from deepr.utils.atomic_io import append_jsonl_durable

    append_jsonl_durable(p, event.to_dict(), fsync=True)


def record_admission(
    model: str,
    task_class: str,
    *,
    days: int = DEFAULT_ADMISSION_DAYS,
    score: float | None = None,
    note: str = "",
    now: datetime | None = None,
    path: Path | None = None,
) -> Admission:
    """Admit ``model`` for ``task_class`` for ``days`` (operator acceptance)."""
    stamp = now or _utc_now()
    event = Admission(
        model=model,
        task_class=task_class,
        recorded_at=stamp,
        expires_at=stamp + timedelta(days=days),
        event="admit",
        score=score,
        note=note,
    )
    _append(event, path)
    return event


def revoke_admission(
    model: str, task_class: str, *, now: datetime | None = None, path: Path | None = None
) -> Admission:
    """Revoke any admission for ``model`` on ``task_class`` (takes effect now)."""
    event = Admission(
        model=model,
        task_class=task_class,
        recorded_at=now or _utc_now(),
        expires_at=None,
        event="revoke",
    )
    _append(event, path)
    return event


def _latest_per_pair(events: Iterable[Admission]) -> dict[tuple[str, str], Admission]:
    """The most recent event for each (model, task_class), by recorded_at."""
    latest: dict[tuple[str, str], Admission] = {}
    for e in events:
        key = (e.model, e.task_class)
        prev = latest.get(key)
        if prev is None or e.recorded_at >= prev.recorded_at:
            latest[key] = e
    return latest


def active_admission(
    model: str, task_class: str, *, now: datetime | None = None, path: Path | None = None
) -> Admission | None:
    """The live admission for (model, task_class), or None if none/expired/revoked."""
    stamp = now or _utc_now()
    latest = _latest_per_pair(load_events(path))
    event = latest.get((model, task_class))
    if event is None or not event.is_active(now=stamp):
        return None
    return event


def is_admitted(model: str, task_class: str, *, now: datetime | None = None, path: Path | None = None) -> bool:
    return active_admission(model, task_class, now=now, path=path) is not None


def list_active(*, now: datetime | None = None, path: Path | None = None) -> list[Admission]:
    """All currently-live admissions, sorted by model then task class."""
    stamp = now or _utc_now()
    live = [e for e in _latest_per_pair(load_events(path)).values() if e.is_active(now=stamp)]
    return sorted(live, key=lambda a: (a.model, a.task_class))
