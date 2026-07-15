"""Durable expert loop-run records.

The loop runner is still being built, but scheduled expert surfaces already need
one shared status contract. This module defines the versioned record and an
append-only JSONL store that can be consumed by CLI, MCP, and future dashboards.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import Any

from deepr.utils.atomic_io import append_jsonl_durable

LOOP_RUN_SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now(UTC)


class LoopRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_LOOP_STATUSES = frozenset(
    {
        LoopRunStatus.COMPLETED,
        LoopRunStatus.FAILED,
        LoopRunStatus.CANCELLED,
    }
)


class LoopStopReason(str, Enum):
    VERIFIER_PASSED = "verifier_passed"
    NO_DUE_WORK = "no_due_work"
    OVERLAP_LOCKED = "overlap_locked"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CAPACITY_UNAVAILABLE = "capacity_unavailable"
    HUMAN_GATE_REQUIRED = "human_gate_required"
    MAX_ITERATIONS = "max_iterations"
    TOOL_FAILURE = "tool_failure"
    VERIFIER_FAILED = "verifier_failed"
    SCHEMA_ERROR = "schema_error"
    CANCELLED = "cancelled"


LOOP_STATUS_STOP_REASONS = {
    LoopRunStatus.WAITING: frozenset(
        {
            LoopStopReason.BUDGET_EXHAUSTED,
            LoopStopReason.CAPACITY_UNAVAILABLE,
            LoopStopReason.HUMAN_GATE_REQUIRED,
            LoopStopReason.OVERLAP_LOCKED,
        }
    ),
    LoopRunStatus.COMPLETED: frozenset(
        {
            LoopStopReason.VERIFIER_PASSED,
            LoopStopReason.NO_DUE_WORK,
        }
    ),
    LoopRunStatus.FAILED: frozenset(
        {
            LoopStopReason.MAX_ITERATIONS,
            LoopStopReason.SCHEMA_ERROR,
            LoopStopReason.TOOL_FAILURE,
            LoopStopReason.VERIFIER_FAILED,
        }
    ),
    LoopRunStatus.CANCELLED: frozenset({LoopStopReason.CANCELLED}),
}


def loop_runs_path(expert_name: str, path: Path | None = None) -> Path:
    if path is not None:
        return path
    from deepr.experts.paths import canonical_expert_dir

    # Same canonical (slug) directory as profile + beliefs, so loop runs are not
    # orphaned in a separate display-named dir.
    return canonical_expert_dir(expert_name) / "loop_runs.jsonl"


def new_loop_run_id() -> str:
    return f"loop_{uuid.uuid4().hex[:12]}"


def known_exception_cost(exception: BaseException) -> float:
    """Return the greatest finite non-negative spend carried by an error chain."""
    known = 0.0
    current: BaseException | None = exception
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for attribute in ("actual_cost", "total_cost", "budget_spent"):
            value = getattr(current, attribute, None)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            numeric = float(value)
            if isfinite(numeric) and numeric >= 0.0:
                known = max(known, numeric)
        current = current.__cause__ or current.__context__
    return known


def _parse_dt(value: Any, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 datetime string")
    parsed = datetime.fromisoformat(value)
    _validate_aware_datetime(parsed, field_name=field_name)
    return parsed


def _dt_to_str(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _validate_nonnegative_int(value: object, *, field_name: str, positive: bool = False) -> None:
    minimum = 1 if positive else 0
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        requirement = "positive" if positive else "non-negative"
        raise ValueError(f"{field_name} must be a {requirement} integer")


def _validate_finite_number(
    value: object,
    *,
    field_name: str,
    nonnegative: bool,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        requirement = "finite non-negative number" if nonnegative else "finite number"
        raise ValueError(f"{field_name} must be a {requirement}")
    numeric = float(value)
    if not isfinite(numeric) or (nonnegative and numeric < 0):
        requirement = "finite non-negative number" if nonnegative else "finite number"
        raise ValueError(f"{field_name} must be a {requirement}")


def _validate_aware_datetime(value: object, *, field_name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a UTC offset")


@dataclass(frozen=True)
class ExpertLoopRun:
    run_id: str
    expert_name: str
    loop_type: str
    goal: str
    trigger: str
    status: LoopRunStatus = LoopRunStatus.PENDING
    schema_version: int = LOOP_RUN_SCHEMA_VERSION
    started_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    finished_at: datetime | None = None
    iteration_count: int = 0
    max_iterations: int | None = None
    state_artifact_path: str = ""
    budget_limit: float | None = None
    budget_spent: float = 0.0
    capacity_source: str = ""
    backend_profile_id: str = ""
    trace_id: str = ""
    queue_id: str = ""
    job_id: str = ""
    approval_id: str = ""
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    knowledge_change_refs: list[str] = field(default_factory=list)
    verifier_id: str = ""
    verifier_version: str = ""
    verifier_outcome: str = ""
    verifier_score: float | None = None
    verifier_threshold: float | None = None
    verifier_evidence_refs: list[str] = field(default_factory=list)
    accepted_changes: int = 0
    rejected_changes: int = 0
    stop_reason: LoopStopReason | None = None
    failure_reason: str = ""
    next_action: dict[str, Any] = field(default_factory=dict)
    run_context: dict[str, Any] = field(default_factory=dict)

    @property
    def acceptance_rate(self) -> float:
        attempted = self.accepted_changes + self.rejected_changes
        return self.accepted_changes / attempted if attempted else 0.0

    @property
    def cost_per_accepted_change(self) -> float:
        return self.budget_spent / self.accepted_changes if self.accepted_changes else 0.0

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_LOOP_STATUSES

    def __post_init__(self) -> None:
        self._validate_identity_fields()
        self._validate_numeric_fields()
        self._validate_timestamps()
        self._validate_stop_reason()

    def _validate_identity_fields(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise ValueError("schema_version must be an integer")
        if self.schema_version != LOOP_RUN_SCHEMA_VERSION:
            raise ValueError(f"unsupported loop-run schema version: {self.schema_version}")
        for field_name in ("run_id", "expert_name", "loop_type", "goal", "trigger"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")

    def _validate_numeric_fields(self) -> None:
        _validate_nonnegative_int(self.iteration_count, field_name="iteration_count")
        if self.max_iterations is not None:
            _validate_nonnegative_int(self.max_iterations, field_name="max_iterations", positive=True)
        if self.budget_limit is not None:
            _validate_finite_number(self.budget_limit, field_name="budget_limit", nonnegative=True)
        _validate_finite_number(self.budget_spent, field_name="budget_spent", nonnegative=True)
        _validate_nonnegative_int(self.accepted_changes, field_name="accepted_changes")
        _validate_nonnegative_int(self.rejected_changes, field_name="rejected_changes")
        if self.verifier_score is not None:
            _validate_finite_number(self.verifier_score, field_name="verifier_score", nonnegative=False)
        if self.verifier_threshold is not None:
            _validate_finite_number(self.verifier_threshold, field_name="verifier_threshold", nonnegative=False)

    def _validate_timestamps(self) -> None:
        _validate_aware_datetime(self.started_at, field_name="started_at")
        _validate_aware_datetime(self.updated_at, field_name="updated_at")
        if self.finished_at is not None:
            _validate_aware_datetime(self.finished_at, field_name="finished_at")

    def _validate_stop_reason(self) -> None:
        if self.is_terminal and self.stop_reason is None:
            raise ValueError("terminal loop runs require a typed stop_reason")
        allowed_stop_reasons = LOOP_STATUS_STOP_REASONS.get(self.status)
        if (
            allowed_stop_reasons is not None
            and self.stop_reason is not None
            and self.stop_reason not in allowed_stop_reasons
        ):
            raise ValueError(f"{self.status.value} loop runs cannot use stop_reason {self.stop_reason.value}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "expert_name": self.expert_name,
            "loop_type": self.loop_type,
            "goal": self.goal,
            "trigger": self.trigger,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "finished_at": _dt_to_str(self.finished_at),
            "iteration_count": self.iteration_count,
            "max_iterations": self.max_iterations,
            "state_artifact_path": self.state_artifact_path,
            "budget_limit": self.budget_limit,
            "budget_spent": self.budget_spent,
            "capacity_source": self.capacity_source,
            "backend_profile_id": self.backend_profile_id,
            "trace_id": self.trace_id,
            "queue_id": self.queue_id,
            "job_id": self.job_id,
            "approval_id": self.approval_id,
            "input_refs": self.input_refs,
            "output_refs": self.output_refs,
            "knowledge_change_refs": self.knowledge_change_refs,
            "verifier_id": self.verifier_id,
            "verifier_version": self.verifier_version,
            "verifier_outcome": self.verifier_outcome,
            "verifier_score": self.verifier_score,
            "verifier_threshold": self.verifier_threshold,
            "verifier_evidence_refs": self.verifier_evidence_refs,
            "accepted_changes": self.accepted_changes,
            "rejected_changes": self.rejected_changes,
            "acceptance_rate": round(self.acceptance_rate, 4),
            "cost_per_accepted_change": round(self.cost_per_accepted_change, 4),
            "stop_reason": self.stop_reason.value if self.stop_reason else None,
            "failure_reason": self.failure_reason,
            "next_action": self.next_action,
            "run_context": self.run_context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpertLoopRun:
        return cls(
            schema_version=data.get("schema_version", LOOP_RUN_SCHEMA_VERSION),
            run_id=str(data["run_id"]),
            expert_name=str(data["expert_name"]),
            loop_type=str(data["loop_type"]),
            goal=str(data["goal"]),
            trigger=str(data["trigger"]),
            status=LoopRunStatus(str(data.get("status", LoopRunStatus.PENDING.value))),
            started_at=_parse_dt(data.get("started_at"), field_name="started_at") or _utc_now(),
            updated_at=_parse_dt(data.get("updated_at"), field_name="updated_at") or _utc_now(),
            finished_at=_parse_dt(data.get("finished_at"), field_name="finished_at"),
            iteration_count=data.get("iteration_count", 0),
            max_iterations=data.get("max_iterations"),
            state_artifact_path=str(data.get("state_artifact_path", "")),
            budget_limit=data.get("budget_limit"),
            budget_spent=data.get("budget_spent", 0.0),
            capacity_source=str(data.get("capacity_source", "")),
            backend_profile_id=str(data.get("backend_profile_id", "")),
            trace_id=str(data.get("trace_id", "")),
            queue_id=str(data.get("queue_id", "")),
            job_id=str(data.get("job_id", "")),
            approval_id=str(data.get("approval_id", "")),
            input_refs=_string_list(data.get("input_refs")),
            output_refs=_string_list(data.get("output_refs")),
            knowledge_change_refs=_string_list(data.get("knowledge_change_refs")),
            verifier_id=str(data.get("verifier_id", "")),
            verifier_version=str(data.get("verifier_version", "")),
            verifier_outcome=str(data.get("verifier_outcome", "")),
            verifier_score=data.get("verifier_score"),
            verifier_threshold=data.get("verifier_threshold"),
            verifier_evidence_refs=_string_list(data.get("verifier_evidence_refs")),
            accepted_changes=data.get("accepted_changes", 0),
            rejected_changes=data.get("rejected_changes", 0),
            stop_reason=LoopStopReason(str(data["stop_reason"])) if data.get("stop_reason") else None,
            failure_reason=str(data.get("failure_reason", "")),
            next_action=_dict_or_empty(data.get("next_action")),
            run_context=_dict_or_empty(data.get("run_context")),
        )


class ExpertLoopRunStore:
    """Append-only loop-run snapshots for one expert."""

    def __init__(self, expert_name: str, *, path: Path | None = None):
        self.expert_name = expert_name
        self.path = loop_runs_path(expert_name, path)

    def append(self, run: ExpertLoopRun) -> ExpertLoopRun:
        if run.expert_name != self.expert_name:
            raise ValueError("run expert_name does not match store")
        append_jsonl_durable(self.path, run.to_dict(), fsync=True)
        return run

    def list_runs(
        self,
        *,
        status: LoopRunStatus | None = None,
        loop_type: str | None = None,
        limit: int = 20,
    ) -> list[ExpertLoopRun]:
        _validate_nonnegative_int(limit, field_name="limit", positive=True)
        latest: dict[str, ExpertLoopRun] = {}
        for run in self._iter_snapshots():
            latest[run.run_id] = run
        runs: Iterable[ExpertLoopRun] = latest.values()
        if status is not None:
            runs = [run for run in runs if run.status == status]
        if loop_type is not None:
            runs = [run for run in runs if run.loop_type == loop_type]
        return sorted(runs, key=lambda run: run.updated_at, reverse=True)[:limit]

    def latest(self) -> ExpertLoopRun | None:
        runs = self.list_runs(limit=1)
        return runs[0] if runs else None

    def _iter_snapshots(self) -> list[ExpertLoopRun]:
        if not self.path.exists():
            return []
        snapshots: list[ExpertLoopRun] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    snapshots.append(ExpertLoopRun.from_dict(payload))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return snapshots


def record_loop_run(
    *,
    run_id: str | None = None,
    expert_name: str,
    loop_type: str,
    goal: str,
    trigger: str,
    status: LoopRunStatus,
    stop_reason: LoopStopReason | None,
    next_action: dict[str, Any] | None = None,
    budget_limit: float | None = None,
    budget_spent: float = 0.0,
    capacity_source: str = "",
    backend_profile_id: str = "",
    accepted_changes: int = 0,
    rejected_changes: int = 0,
    verifier_id: str = "",
    verifier_version: str = "",
    verifier_outcome: str = "",
    verifier_score: float | None = None,
    verifier_threshold: float | None = None,
    run_context: dict[str, Any] | None = None,
    failure_reason: str = "",
    started_at: datetime | None = None,
    updated_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> ExpertLoopRun:
    timestamp = _utc_now()
    run = ExpertLoopRun(
        run_id=run_id or new_loop_run_id(),
        expert_name=expert_name,
        loop_type=loop_type,
        goal=goal,
        trigger=trigger,
        status=status,
        stop_reason=stop_reason,
        next_action=next_action or {},
        budget_limit=budget_limit,
        budget_spent=budget_spent,
        capacity_source=capacity_source,
        backend_profile_id=backend_profile_id,
        accepted_changes=accepted_changes,
        rejected_changes=rejected_changes,
        verifier_id=verifier_id,
        verifier_version=verifier_version,
        verifier_outcome=verifier_outcome,
        verifier_score=verifier_score,
        verifier_threshold=verifier_threshold,
        run_context=run_context or {},
        failure_reason=failure_reason,
        started_at=started_at or timestamp,
        updated_at=updated_at or timestamp,
        finished_at=finished_at,
    )
    return ExpertLoopRunStore(expert_name).append(run)
