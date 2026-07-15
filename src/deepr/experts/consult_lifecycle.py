"""Durable lifecycle journal for expert consult runs.

The journal is opened before backend construction or provider dispatch. It is
separate from the final consult trace because a host interruption can prevent
that transaction artifact from being finalized. Lifecycle events contain only
lineage hashes, bounded counters, capacity posture, and process ownership. They
never contain answers or private reasoning.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, TypedDict, cast

from deepr.config import default_data_dir, runtime_data_path
from deepr.experts.consult_lifecycle_contract import (
    _Bounds,
    _mapping_with_optional,
    _nonnegative_int,
    _normalize_bounds,
    _normalize_cost,
    _normalize_progress,
    _Progress,
)
from deepr.experts.consult_lifecycle_errors import (
    ConsultLifecycleElapsedLimitError,
    ConsultLifecycleError,
    ConsultLifecycleJournalError,
    ConsultLifecycleLockTimeoutError,
    ConsultLifecycleStorageError,
    ConsultLifecycleTransitionError,
)
from deepr.experts.consult_lifecycle_storage import (
    _lock_path as _storage_lock_path,
)
from deepr.experts.consult_lifecycle_storage import (
    _shared_path_lock as _storage_shared_path_lock,
)
from deepr.experts.consult_lifecycle_storage import (
    append_journal_event,
    bounded_journal_lock,
    ensure_journal_parent,
    read_journal_lines,
)

_lock_path = _storage_lock_path
_shared_path_lock = _storage_shared_path_lock

CONSULT_LIFECYCLE_SCHEMA_VERSION = "deepr-consult-lifecycle-event-v1"
CONSULT_LIFECYCLE_KIND = "deepr.expert.consult_lifecycle_event"
_DEFAULT_LOCK_TIMEOUT_SECONDS = 5.0


class LifecycleState(StrEnum):
    """Persisted consult run states."""

    RUNNING = "running"
    WAITING_CAPACITY = "waiting_capacity"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    VERIFIER_FAILED = "verifier_failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    FAILED = "failed"


class LifecyclePhase(StrEnum):
    """Bounded phases that can own a consult attempt."""

    PREFLIGHT = "preflight"
    PERSPECTIVES = "perspectives"
    SYNTHESIS = "synthesis"
    TRACE_FINALIZE = "trace_finalize"
    DELIBERATION = "deliberation"


class LifecycleEventType(StrEnum):
    """Append-only lifecycle event types."""

    STARTED = "started"
    HEARTBEAT = "heartbeat"
    STATE_TRANSITION = "state_transition"


RESUMABLE_STATES = frozenset({LifecycleState.WAITING_CAPACITY, LifecycleState.INTERRUPTED})
TERMINAL_STATES = frozenset(
    {
        LifecycleState.COMPLETED,
        LifecycleState.CANCELLED,
        LifecycleState.VERIFIER_FAILED,
        LifecycleState.BUDGET_EXHAUSTED,
        LifecycleState.FAILED,
    }
)

_TRACE_ID_PATTERN = re.compile(r"^consult_[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ATTEMPT_ID_PATTERN = re.compile(r"^attempt_[a-f0-9]{12}$")
_REASON_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_CAPACITY_KEYS = frozenset({"source", "backend", "provider", "model", "admission", "live_metered_fallback"})
_CAPACITY_ADMISSIONS = frozenset({"admitted", "waiting", "unavailable", "unknown"})
_LINEAGE_KEYS = frozenset({"operation", "question_hash", "roster_hash", "snapshot_set_hash"})
_REMAINING_REQUIRED_KEYS = frozenset({"cost_usd", "dispatches", "elapsed_ms"})
_REMAINING_OPTIONAL_KEYS = frozenset({"context_bytes", "output_tokens"})
_OWNERSHIP_KEYS = frozenset({"process_id", "thread_id"})
_EVENT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "contract",
        "trace_id",
        "attempt_id",
        "sequence",
        "recorded_at",
        "event_type",
        "state",
        "previous_state",
        "phase",
        "reason_code",
        "elapsed_ms",
        "max_elapsed_seconds",
        "lineage",
        "capacity",
        "bounds",
        "progress",
        "remaining",
        "ownership",
    }
)


class _PersistedEventFields(TypedDict):
    attempt_id: str
    event_type: LifecycleEventType
    state: LifecycleState
    previous_state: LifecycleState | None
    reason_code: str | None
    elapsed_ms: int
    max_elapsed_seconds: float
    lineage: dict[str, object]
    capacity: dict[str, object]
    bounds: _Bounds
    progress: _Progress


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _new_trace_id() -> str:
    return f"consult_{uuid.uuid4().hex[:12]}"


def _new_attempt_id() -> str:
    return f"attempt_{uuid.uuid4().hex[:12]}"


def _journal_path(path: Path | None) -> Path:
    if path is not None:
        return path
    explicit = os.getenv("DEEPR_CONSULT_LIFECYCLE_PATH")
    if explicit:
        return Path(explicit)
    consult_trace_path = os.getenv("DEEPR_CONSULT_TRACE_PATH")
    if consult_trace_path:
        return Path(consult_trace_path).parent / "consult_lifecycle_events.jsonl"
    if os.getenv("DEEPR_DATA_DIR"):
        return runtime_data_path("consult_traces", "consult_lifecycle_events.jsonl")
    return default_data_dir() / "consult_traces" / "consult_lifecycle_events.jsonl"


@contextmanager
def _bounded_journal_lock(path: Path, timeout_seconds: float) -> Iterator[None]:
    with bounded_journal_lock(path, timeout_seconds, maximum_seconds=_DEFAULT_LOCK_TIMEOUT_SECONDS):
        yield


def _read_journal_lines(path: Path) -> list[str]:
    return read_journal_lines(path)


def _parse_journal_event(line: str, line_number: int) -> tuple[dict[str, Any], str, int]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ConsultLifecycleJournalError(f"Lifecycle journal line {line_number} is not valid JSON") from exc
    if not isinstance(event, dict):
        raise ConsultLifecycleJournalError(f"Lifecycle journal line {line_number} is not an object")
    trace_id = event.get("trace_id")
    sequence = event.get("sequence")
    if not isinstance(trace_id, str) or not _TRACE_ID_PATTERN.fullmatch(trace_id):
        raise ConsultLifecycleJournalError(f"Lifecycle journal line {line_number} has an invalid trace_id")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ConsultLifecycleJournalError(f"Lifecycle journal line {line_number} has an invalid sequence")
    return event, trace_id, sequence


def _validate_journal_sequence(
    *, trace_id: str, sequence: int, line_number: int, last_sequences: Mapping[str, int]
) -> None:
    expected = last_sequences.get(trace_id, 0) + 1
    if sequence != expected:
        raise ConsultLifecycleJournalError(
            f"Lifecycle journal line {line_number} has sequence {sequence}; expected {expected}"
        )


def _validate_journal_contract(
    event: Mapping[str, object], *, previous: Mapping[str, object] | None, line_number: int
) -> None:
    try:
        _validate_persisted_event(event, previous=previous)
    except (KeyError, TypeError, ValueError) as exc:
        raise ConsultLifecycleJournalError(
            f"Lifecycle journal line {line_number} violates the lifecycle contract: {exc}"
        ) from exc


def _read_events_unlocked(path: Path) -> list[dict[str, Any]]:
    try:
        exists = path.exists()
    except (OSError, RuntimeError) as exc:
        raise ConsultLifecycleStorageError("journal lookup", partial_write_possible=False) from exc
    if not exists:
        return []
    events: list[dict[str, Any]] = []
    last_sequences: dict[str, int] = {}
    last_events: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(_read_journal_lines(path), start=1):
        if not line.strip():
            continue
        event, trace_id, sequence = _parse_journal_event(line, line_number)
        _validate_journal_sequence(
            trace_id=trace_id,
            sequence=sequence,
            line_number=line_number,
            last_sequences=last_sequences,
        )
        _validate_journal_contract(event, previous=last_events.get(trace_id), line_number=line_number)
        last_sequences[trace_id] = sequence
        last_events[trace_id] = event
        events.append(event)
    return events


def load_consult_lifecycle_events(*, trace_id: str | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    """Load lifecycle events, failing closed on corruption or sequence gaps."""
    if trace_id is not None:
        _validate_trace_id(trace_id)
    target = _journal_path(path)
    try:
        exists = target.exists()
    except (OSError, RuntimeError) as exc:
        raise ConsultLifecycleStorageError("journal lookup", partial_write_possible=False) from exc
    if not exists:
        return []
    ensure_journal_parent(target)
    with _bounded_journal_lock(target, _DEFAULT_LOCK_TIMEOUT_SECONDS):
        events = _read_events_unlocked(target)
    if trace_id is None:
        return events
    return [event for event in events if event["trace_id"] == trace_id]


def _validate_trace_id(trace_id: str) -> None:
    if not _TRACE_ID_PATTERN.fullmatch(trace_id):
        raise ValueError("trace_id must start with consult_ and contain only safe identifier characters")


def _exact_mapping(value: Mapping[str, object], keys: frozenset[str], name: str) -> dict[str, object]:
    result = dict(value)
    extras = set(result) - keys
    missing = keys - set(result)
    if extras or missing:
        raise ValueError(f"{name} must contain exactly {sorted(keys)}")
    return result


def _as_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return cast(Mapping[str, object], value)


def _normalize_capacity(value: Mapping[str, object]) -> dict[str, object]:
    raw = _exact_mapping(value, _CAPACITY_KEYS, "capacity")
    result: dict[str, object] = {}
    for key in ("source", "backend"):
        item = raw[key]
        if not isinstance(item, str) or not item.strip() or len(item) > 128:
            raise ValueError(f"capacity.{key} must be a non-empty string of at most 128 characters")
        result[key] = item.strip()
    for key in ("provider", "model"):
        item = raw[key]
        if not isinstance(item, str) or len(item) > 256:
            raise ValueError(f"capacity.{key} must be a string of at most 256 characters")
        result[key] = item
    admission = raw["admission"]
    if not isinstance(admission, str) or admission not in _CAPACITY_ADMISSIONS:
        raise ValueError(f"capacity.admission must be one of {sorted(_CAPACITY_ADMISSIONS)}")
    result["admission"] = admission
    fallback = raw["live_metered_fallback"]
    if not isinstance(fallback, bool):
        raise ValueError("capacity.live_metered_fallback must be a boolean")
    result["live_metered_fallback"] = fallback
    return result


def _validate_capacity_transition(previous: Mapping[str, object], current: Mapping[str, object]) -> None:
    """Allow admission changes and one-way blank provider/model enrichment."""
    for key in ("source", "backend", "live_metered_fallback"):
        if current[key] != previous[key]:
            raise ValueError(f"capacity.{key} cannot change")
    for key in ("provider", "model"):
        previous_value = str(previous[key])
        current_value = str(current[key])
        if previous_value and current_value != previous_value:
            raise ValueError(f"capacity.{key} cannot change after resolution")


def _normalize_lineage(value: Mapping[str, object]) -> dict[str, object]:
    raw = dict(value)
    extras = set(raw) - _LINEAGE_KEYS
    required = {"operation", "question_hash", "roster_hash"}
    if extras or not required.issubset(raw):
        raise ValueError("lineage requires operation, question_hash, and roster_hash; snapshot_set_hash is optional")
    operation = raw["operation"]
    if operation not in {"one_shot", "deliberation"}:
        raise ValueError("lineage.operation must be one_shot or deliberation")
    result: dict[str, object] = {"operation": operation}
    for key in ("question_hash", "roster_hash", "snapshot_set_hash"):
        if key not in raw:
            continue
        item = raw[key]
        if not isinstance(item, str) or not _HASH_PATTERN.fullmatch(item):
            raise ValueError(f"lineage.{key} must be a lowercase SHA-256 hex digest")
        result[key] = item
    return result


def _normalize_max_elapsed(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("max_elapsed_seconds must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0 or normalized > 31_536_000:
        raise ValueError("max_elapsed_seconds must be finite, positive, and no greater than one year")
    return normalized


def _elapsed_limit_ms(max_elapsed_seconds: float) -> int:
    return max(1, math.ceil(max_elapsed_seconds * 1000))


def _normalize_reason_code(value: str) -> str:
    if not _REASON_CODE_PATTERN.fullmatch(value):
        raise ValueError("reason_code must be a lowercase typed identifier")
    return value


def _remaining(
    *, max_elapsed_seconds: float, elapsed_ms: int, bounds: _Bounds, progress: _Progress
) -> dict[str, int | float]:
    cost_remaining = Decimal(str(bounds["max_cost_usd"])) - Decimal(str(progress["cost_usd_observed"]))
    remaining: dict[str, int | float] = {
        "cost_usd": float(max(Decimal(0), cost_remaining)),
        "dispatches": max(0, bounds["max_dispatches"] - progress["dispatches_completed"]),
        "elapsed_ms": max(0, _elapsed_limit_ms(max_elapsed_seconds) - elapsed_ms),
    }
    if "max_context_bytes" in bounds:
        remaining["context_bytes"] = max(
            0,
            bounds["max_context_bytes"] - progress.get("context_bytes_observed", 0),
        )
    if "max_output_tokens" in bounds:
        remaining["output_tokens"] = max(
            0,
            bounds["max_output_tokens"] - progress.get("output_tokens_observed", 0),
        )
    return remaining


def _apply_observed_stops(
    *,
    event_type: LifecycleEventType,
    state: LifecycleState,
    reason_code: str | None,
    elapsed_ms: int,
    elapsed_limit_ms: int,
    cost_stopped: bool,
    elapsed_stopped: bool,
) -> tuple[LifecycleEventType, LifecycleState, str | None, int]:
    if cost_stopped:
        return LifecycleEventType.STATE_TRANSITION, LifecycleState.FAILED, "cost_bound_exceeded", elapsed_ms
    if elapsed_stopped:
        return (
            LifecycleEventType.STATE_TRANSITION,
            LifecycleState.FAILED,
            "elapsed_limit",
            max(elapsed_ms, elapsed_limit_ms),
        )
    return event_type, state, reason_code, elapsed_ms


def _contract() -> dict[str, object]:
    return {
        "append_only": True,
        "trace_writes_only": True,
        "writes_expert_state": False,
        "writes_graph": False,
        "writes_routing_state": False,
        "answer_text_allowed": False,
        "private_reasoning_allowed": False,
    }


def _validate_event_identity(raw: Mapping[str, object]) -> str:
    if raw["schema_version"] != CONSULT_LIFECYCLE_SCHEMA_VERSION or raw["kind"] != CONSULT_LIFECYCLE_KIND:
        raise ValueError("schema_version or kind is not supported")
    if raw["contract"] != _contract():
        raise ValueError("contract does not match the trace-only write boundary")
    attempt_id = raw["attempt_id"]
    if not isinstance(attempt_id, str) or not _ATTEMPT_ID_PATTERN.fullmatch(attempt_id):
        raise ValueError("attempt_id is invalid")
    recorded_at = raw["recorded_at"]
    if not isinstance(recorded_at, str):
        raise ValueError("recorded_at is invalid")
    parsed_time = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    if parsed_time.tzinfo is None:
        raise ValueError("recorded_at must include a timezone")
    return attempt_id


def _normalize_event_reason(raw: Mapping[str, object]) -> str | None:
    reason_code = raw["reason_code"]
    if reason_code is None:
        return None
    if not isinstance(reason_code, str):
        raise ValueError("reason_code is invalid")
    return _normalize_reason_code(reason_code)


def _validate_remaining_and_ownership(
    raw: Mapping[str, object],
    *,
    elapsed_ms: int,
    max_elapsed_seconds: float,
    bounds: _Bounds,
    progress: _Progress,
) -> None:
    remaining_raw = _mapping_with_optional(
        _as_mapping(raw["remaining"], "remaining"),
        required=_REMAINING_REQUIRED_KEYS,
        optional=_REMAINING_OPTIONAL_KEYS,
        name="remaining",
    )
    remaining: dict[str, int | float] = {
        "cost_usd": _normalize_cost(remaining_raw["cost_usd"], "remaining.cost_usd"),
        "dispatches": _nonnegative_int(remaining_raw["dispatches"], "remaining.dispatches"),
        "elapsed_ms": _nonnegative_int(remaining_raw["elapsed_ms"], "remaining.elapsed_ms"),
    }
    if "context_bytes" in remaining_raw:
        remaining["context_bytes"] = _nonnegative_int(remaining_raw["context_bytes"], "remaining.context_bytes")
    if "output_tokens" in remaining_raw:
        remaining["output_tokens"] = _nonnegative_int(remaining_raw["output_tokens"], "remaining.output_tokens")
    if remaining != _remaining(
        max_elapsed_seconds=max_elapsed_seconds,
        elapsed_ms=elapsed_ms,
        bounds=bounds,
        progress=progress,
    ):
        raise ValueError("remaining counters do not match bounds and progress")
    ownership = _exact_mapping(_as_mapping(raw["ownership"], "ownership"), _OWNERSHIP_KEYS, "ownership")
    for key in _OWNERSHIP_KEYS:
        _nonnegative_int(ownership[key], f"ownership.{key}")


def _normalize_persisted_event(event: Mapping[str, object]) -> _PersistedEventFields:
    raw = _exact_mapping(event, _EVENT_KEYS, "event")
    attempt_id = _validate_event_identity(raw)
    LifecyclePhase(str(raw["phase"]))
    previous_state_raw = raw["previous_state"]
    previous_state = None if previous_state_raw is None else LifecycleState(str(previous_state_raw))
    elapsed_ms = _nonnegative_int(raw["elapsed_ms"], "elapsed_ms")
    max_elapsed_seconds = _normalize_max_elapsed(raw["max_elapsed_seconds"])
    state = LifecycleState(str(raw["state"]))
    reason_code = _normalize_event_reason(raw)
    if elapsed_ms >= _elapsed_limit_ms(max_elapsed_seconds):
        if state not in TERMINAL_STATES:
            raise ValueError("a nonterminal event cannot reach or exceed max_elapsed_seconds")
        if state is not LifecycleState.FAILED or reason_code != "elapsed_limit":
            raise ValueError("an event at the elapsed ceiling must use the failed elapsed_limit stop")
    bounds = _normalize_bounds(_as_mapping(raw["bounds"], "bounds"))
    progress = _normalize_progress(_as_mapping(raw["progress"], "progress"), bounds)
    _validate_remaining_and_ownership(
        raw,
        elapsed_ms=elapsed_ms,
        max_elapsed_seconds=max_elapsed_seconds,
        bounds=bounds,
        progress=progress,
    )
    return {
        "attempt_id": attempt_id,
        "event_type": LifecycleEventType(str(raw["event_type"])),
        "state": state,
        "previous_state": previous_state,
        "reason_code": reason_code,
        "elapsed_ms": elapsed_ms,
        "max_elapsed_seconds": max_elapsed_seconds,
        "lineage": _normalize_lineage(_as_mapping(raw["lineage"], "lineage")),
        "capacity": _normalize_capacity(_as_mapping(raw["capacity"], "capacity")),
        "bounds": bounds,
        "progress": progress,
    }


def _validate_first_persisted_event(current: _PersistedEventFields) -> None:
    if current["event_type"] is not LifecycleEventType.STARTED or current["state"] is not LifecycleState.RUNNING:
        raise ValueError("the first event must start in running")
    if current["previous_state"] is not None or current["reason_code"] is not None:
        raise ValueError("the first event cannot have a previous state or reason")


def _validate_immutable_history(current: _PersistedEventFields, previous: _PersistedEventFields) -> None:
    prior_state = previous["state"]
    if prior_state in TERMINAL_STATES:
        raise ValueError(f"no event may follow terminal state {prior_state.value}")
    if current["previous_state"] is not prior_state:
        raise ValueError("previous_state does not match the preceding event")
    if current["elapsed_ms"] < previous["elapsed_ms"]:
        raise ValueError("elapsed_ms cannot decrease")
    if current["max_elapsed_seconds"] != previous["max_elapsed_seconds"]:
        raise ValueError("max_elapsed_seconds cannot change")
    if current["lineage"] != previous["lineage"]:
        raise ValueError("lineage cannot change")
    if current["bounds"] != previous["bounds"]:
        raise ValueError("bounds cannot change")
    _validate_capacity_transition(previous["capacity"], current["capacity"])


def _validate_monotonic_progress(current: _Progress, previous: _Progress) -> None:
    if current["dispatches_completed"] < previous["dispatches_completed"]:
        raise ValueError("progress.dispatches_completed cannot decrease")
    for key in ("context_bytes_observed", "output_tokens_observed"):
        if key in previous and key not in current:
            raise ValueError(f"progress.{key} cannot be removed")
        current_value = _nonnegative_int(current.get(key, 0), f"progress.{key}")
        previous_value = _nonnegative_int(previous.get(key, 0), f"previous progress.{key}")
        if current_value < previous_value:
            raise ValueError(f"progress.{key} cannot decrease")
    if Decimal(str(current["cost_usd_observed"])) < Decimal(str(previous["cost_usd_observed"])):
        raise ValueError("progress.cost_usd_observed cannot decrease")


def _validate_persisted_transition(current: _PersistedEventFields, previous: _PersistedEventFields) -> None:
    event_type = current["event_type"]
    if event_type is LifecycleEventType.STARTED:
        if previous["state"] not in RESUMABLE_STATES or current["state"] is not LifecycleState.RUNNING:
            raise ValueError("only waiting or interrupted runs may start a resumed attempt")
        if current["attempt_id"] == previous["attempt_id"] or current["reason_code"] != "resumed":
            raise ValueError("a resumed attempt needs a new attempt_id and resumed reason")
    elif event_type is LifecycleEventType.HEARTBEAT:
        if previous["state"] is not LifecycleState.RUNNING or current["state"] is not LifecycleState.RUNNING:
            raise ValueError("a heartbeat must continue a running attempt")
        if current["attempt_id"] != previous["attempt_id"] or current["reason_code"] is not None:
            raise ValueError("a heartbeat must retain attempt ownership and have no reason")
    else:
        if previous["state"] is not LifecycleState.RUNNING or current["state"] is LifecycleState.RUNNING:
            raise ValueError("a state transition must close a running attempt")
        if current["attempt_id"] != previous["attempt_id"] or current["reason_code"] is None:
            raise ValueError("a state transition must retain attempt ownership and name a reason")


def _validate_persisted_event(event: Mapping[str, object], *, previous: Mapping[str, object] | None) -> None:
    """Validate stored shape, immutable metadata, and state-machine history."""
    current = _normalize_persisted_event(event)
    if previous is None:
        _validate_first_persisted_event(current)
        return
    prior = _normalize_persisted_event(previous)
    _validate_immutable_history(current, prior)
    _validate_monotonic_progress(current["progress"], prior["progress"])
    _validate_persisted_transition(current, prior)


def _event(
    *,
    trace_id: str,
    attempt_id: str,
    sequence: int,
    event_type: LifecycleEventType,
    state: LifecycleState,
    previous_state: LifecycleState | None,
    phase: LifecyclePhase,
    reason_code: str | None,
    elapsed_ms: int,
    max_elapsed_seconds: float,
    lineage: Mapping[str, object],
    capacity: Mapping[str, object],
    bounds: _Bounds,
    progress: _Progress,
) -> dict[str, Any]:
    return {
        "schema_version": CONSULT_LIFECYCLE_SCHEMA_VERSION,
        "kind": CONSULT_LIFECYCLE_KIND,
        "contract": _contract(),
        "trace_id": trace_id,
        "attempt_id": attempt_id,
        "sequence": sequence,
        "recorded_at": _utc_now(),
        "event_type": event_type.value,
        "state": state.value,
        "previous_state": previous_state.value if previous_state is not None else None,
        "phase": phase.value,
        "reason_code": reason_code,
        "elapsed_ms": elapsed_ms,
        "max_elapsed_seconds": max_elapsed_seconds,
        "lineage": dict(lineage),
        "capacity": dict(capacity),
        "bounds": dict(bounds),
        "progress": dict(progress),
        "remaining": _remaining(
            max_elapsed_seconds=max_elapsed_seconds,
            elapsed_ms=elapsed_ms,
            bounds=bounds,
            progress=progress,
        ),
        "ownership": {
            "process_id": os.getpid(),
            "thread_id": threading.get_native_id(),
        },
    }


def _terminal_replay_or_raise(latest: dict[str, Any], *, force_elapsed: bool, trace_id: str) -> dict[str, Any]:
    if force_elapsed and latest["state"] == "failed" and latest["reason_code"] == "elapsed_limit":
        return latest
    raise ConsultLifecycleTransitionError(f"Lifecycle {trace_id} is terminal in {latest['state']}")


class ConsultLifecycle:
    """One active attempt in an append-only consult lifecycle."""

    def __init__(self, *, path: Path, start_event: Mapping[str, Any]) -> None:
        self.path = path
        self.trace_id = str(start_event["trace_id"])
        self.attempt_id = str(start_event["attempt_id"])
        self.max_elapsed_seconds = float(start_event["max_elapsed_seconds"])
        self.bounds = _normalize_bounds(_as_mapping(start_event["bounds"], "bounds"))
        self.lineage = dict(start_event["lineage"])
        self._elapsed_base_ms = int(start_event["elapsed_ms"])
        self._attempt_started_monotonic = time.monotonic()

    @classmethod
    def start(
        cls,
        *,
        max_elapsed_seconds: float,
        capacity: Mapping[str, object],
        bounds: Mapping[str, object],
        lineage: Mapping[str, object],
        trace_id: str | None = None,
        path: Path | None = None,
        phase: LifecyclePhase | str = LifecyclePhase.PREFLIGHT,
        progress: Mapping[str, object] | None = None,
    ) -> ConsultLifecycle:
        """Open a new running attempt before backend construction."""
        normalized_trace_id = trace_id or _new_trace_id()
        _validate_trace_id(normalized_trace_id)
        normalized_elapsed = _normalize_max_elapsed(max_elapsed_seconds)
        normalized_bounds = _normalize_bounds(bounds)
        normalized_progress = _normalize_progress(progress, normalized_bounds)
        normalized_capacity = _normalize_capacity(capacity)
        normalized_lineage = _normalize_lineage(lineage)
        normalized_phase = LifecyclePhase(phase)
        attempt_started_monotonic = time.monotonic()
        target = _journal_path(path)
        ensure_journal_parent(target)
        with _bounded_journal_lock(target, normalized_elapsed):
            events = _read_events_unlocked(target)
            if any(event["trace_id"] == normalized_trace_id for event in events):
                raise ConsultLifecycleTransitionError(f"Lifecycle {normalized_trace_id} already exists")
            event = _event(
                trace_id=normalized_trace_id,
                attempt_id=_new_attempt_id(),
                sequence=1,
                event_type=LifecycleEventType.STARTED,
                state=LifecycleState.RUNNING,
                previous_state=None,
                phase=normalized_phase,
                reason_code=None,
                elapsed_ms=0,
                max_elapsed_seconds=normalized_elapsed,
                lineage=normalized_lineage,
                capacity=normalized_capacity,
                bounds=normalized_bounds,
                progress=normalized_progress,
            )
            append_journal_event(target, event)
        lifecycle = cls(path=target, start_event=event)
        lifecycle._attempt_started_monotonic = attempt_started_monotonic
        return lifecycle

    @classmethod
    def resume(
        cls,
        *,
        trace_id: str,
        path: Path | None = None,
        phase: LifecyclePhase | str = LifecyclePhase.PREFLIGHT,
        capacity: Mapping[str, object] | None = None,
        progress: Mapping[str, object] | None = None,
    ) -> ConsultLifecycle:
        """Resume a waiting or interrupted run with a new attempt id."""
        _validate_trace_id(trace_id)
        normalized_phase = LifecyclePhase(phase)
        target = _journal_path(path)
        ensure_journal_parent(target)
        with _bounded_journal_lock(target, _DEFAULT_LOCK_TIMEOUT_SECONDS):
            events = _read_events_unlocked(target)
            trace_events = [event for event in events if event["trace_id"] == trace_id]
            if not trace_events:
                raise ConsultLifecycleTransitionError(f"Lifecycle {trace_id} does not exist")
            first = trace_events[0]
            latest = trace_events[-1]
            latest_state = LifecycleState(str(latest["state"]))
            if latest_state not in RESUMABLE_STATES:
                raise ConsultLifecycleTransitionError(f"Lifecycle {trace_id} cannot resume from {latest_state.value}")
            normalized_bounds = _normalize_bounds(first["bounds"])
            progress_value = latest["progress"] if progress is None else progress
            normalized_progress = _normalize_progress(progress_value, normalized_bounds)
            cls._require_monotonic_progress(latest["progress"], normalized_progress)
            capacity_value = latest["capacity"] if capacity is None else capacity
            normalized_capacity = _normalize_capacity(capacity_value)
            latest_capacity = _normalize_capacity(_as_mapping(latest["capacity"], "latest capacity"))
            try:
                _validate_capacity_transition(latest_capacity, normalized_capacity)
            except ValueError as exc:
                raise ConsultLifecycleTransitionError(str(exc)) from exc
            event = _event(
                trace_id=trace_id,
                attempt_id=_new_attempt_id(),
                sequence=int(latest["sequence"]) + 1,
                event_type=LifecycleEventType.STARTED,
                state=LifecycleState.RUNNING,
                previous_state=latest_state,
                phase=normalized_phase,
                reason_code="resumed",
                elapsed_ms=int(latest["elapsed_ms"]),
                max_elapsed_seconds=_normalize_max_elapsed(first["max_elapsed_seconds"]),
                lineage=_normalize_lineage(first["lineage"]),
                capacity=normalized_capacity,
                bounds=normalized_bounds,
                progress=normalized_progress,
            )
            append_journal_event(target, event)
        return cls(path=target, start_event=event)

    @staticmethod
    def _require_monotonic_progress(previous: Mapping[str, object], current: _Progress) -> None:
        previous_dispatches = _nonnegative_int(
            previous["dispatches_completed"], "previous progress.dispatches_completed"
        )
        if current["dispatches_completed"] < previous_dispatches:
            raise ConsultLifecycleTransitionError("progress.dispatches_completed cannot decrease")
        for key in ("context_bytes_observed", "output_tokens_observed"):
            if key in previous and key not in current:
                raise ConsultLifecycleTransitionError(f"progress.{key} cannot be removed")
            previous_value = _nonnegative_int(previous.get(key, 0), f"previous progress.{key}")
            current_value = _nonnegative_int(current.get(key, 0), f"progress.{key}")
            if current_value < previous_value:
                raise ConsultLifecycleTransitionError(f"progress.{key} cannot decrease")
        previous_cost = _normalize_cost(previous["cost_usd_observed"], "previous progress.cost_usd_observed")
        if Decimal(str(current["cost_usd_observed"])) < Decimal(str(previous_cost)):
            raise ConsultLifecycleTransitionError("progress.cost_usd_observed cannot decrease")

    def remaining_elapsed_seconds(self) -> float:
        """Return the cumulative active-time ceiling remaining for this attempt."""
        active_seconds = max(0.0, time.monotonic() - self._attempt_started_monotonic)
        return max(0.0, self.max_elapsed_seconds - self._elapsed_base_ms / 1000 - active_seconds)

    def _append(
        self,
        *,
        event_type: LifecycleEventType,
        state: LifecycleState,
        phase: LifecyclePhase,
        reason_code: str | None,
        progress: Mapping[str, object] | None,
        capacity: Mapping[str, object] | None,
        force_elapsed_limit: bool = False,
        raise_elapsed_limit: bool = True,
    ) -> dict[str, Any]:
        with _bounded_journal_lock(self.path, self.remaining_elapsed_seconds()):
            events = _read_events_unlocked(self.path)
            trace_events = [event for event in events if event["trace_id"] == self.trace_id]
            if not trace_events:
                raise ConsultLifecycleJournalError(f"Lifecycle {self.trace_id} disappeared")
            latest = trace_events[-1]
            latest_state = LifecycleState(str(latest["state"]))
            if latest_state in TERMINAL_STATES:
                return _terminal_replay_or_raise(
                    latest,
                    force_elapsed=force_elapsed_limit,
                    trace_id=self.trace_id,
                )
            if latest_state is not LifecycleState.RUNNING:
                raise ConsultLifecycleTransitionError(f"Lifecycle {self.trace_id} must resume before another event")
            if latest["attempt_id"] != self.attempt_id:
                raise ConsultLifecycleTransitionError("This lifecycle attempt no longer owns the run")
            if event_type is LifecycleEventType.HEARTBEAT and state is not LifecycleState.RUNNING:
                raise ConsultLifecycleTransitionError("Heartbeat events must remain running")
            if event_type is LifecycleEventType.STATE_TRANSITION and state is LifecycleState.RUNNING:
                raise ConsultLifecycleTransitionError("Use heartbeat for a running event")
            progress_value = latest["progress"] if progress is None else progress
            normalized_progress = _normalize_progress(progress_value, self.bounds)
            self._require_monotonic_progress(latest["progress"], normalized_progress)
            cost_stopped = Decimal(str(normalized_progress["cost_usd_observed"])) > Decimal(
                str(self.bounds["max_cost_usd"])
            )
            capacity_value = latest["capacity"] if capacity is None else capacity
            normalized_capacity = _normalize_capacity(capacity_value)
            latest_capacity = _normalize_capacity(_as_mapping(latest["capacity"], "latest capacity"))
            try:
                _validate_capacity_transition(latest_capacity, normalized_capacity)
            except ValueError as exc:
                raise ConsultLifecycleTransitionError(str(exc)) from exc
            active_seconds = max(0.0, time.monotonic() - self._attempt_started_monotonic)
            cumulative_seconds = self._elapsed_base_ms / 1000 + active_seconds
            elapsed_ms = max(int(latest["elapsed_ms"]), math.floor(cumulative_seconds * 1000))
            elapsed_stopped = force_elapsed_limit or cumulative_seconds >= self.max_elapsed_seconds
            event_type, state, reason_code, elapsed_ms = _apply_observed_stops(
                event_type=event_type,
                state=state,
                reason_code=reason_code,
                elapsed_ms=elapsed_ms,
                elapsed_limit_ms=_elapsed_limit_ms(self.max_elapsed_seconds),
                cost_stopped=cost_stopped,
                elapsed_stopped=elapsed_stopped,
            )
            event = _event(
                trace_id=self.trace_id,
                attempt_id=self.attempt_id,
                sequence=int(latest["sequence"]) + 1,
                event_type=event_type,
                state=state,
                previous_state=latest_state,
                phase=phase,
                reason_code=reason_code,
                elapsed_ms=elapsed_ms,
                max_elapsed_seconds=self.max_elapsed_seconds,
                lineage=self.lineage,
                capacity=normalized_capacity,
                bounds=self.bounds,
                progress=normalized_progress,
            )
            append_journal_event(self.path, event)
            if elapsed_stopped and raise_elapsed_limit:
                raise ConsultLifecycleElapsedLimitError(self.trace_id, event)
            return event

    def stop_elapsed_limit(
        self,
        *,
        phase: LifecyclePhase | str,
        progress: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        """Durably record the idempotent typed elapsed-limit terminal stop."""
        return self._append(
            event_type=LifecycleEventType.STATE_TRANSITION,
            state=LifecycleState.FAILED,
            phase=LifecyclePhase(phase),
            reason_code="elapsed_limit",
            progress=progress,
            capacity=None,
            force_elapsed_limit=True,
            raise_elapsed_limit=False,
        )

    def heartbeat(
        self,
        *,
        phase: LifecyclePhase | str,
        progress: Mapping[str, object] | None = None,
        capacity: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        """Append a running heartbeat owned by this attempt."""
        return self._append(
            event_type=LifecycleEventType.HEARTBEAT,
            state=LifecycleState.RUNNING,
            phase=LifecyclePhase(phase),
            reason_code=None,
            progress=progress,
            capacity=capacity,
        )

    def transition(
        self,
        state: LifecycleState | str,
        *,
        phase: LifecyclePhase | str,
        reason_code: str,
        progress: Mapping[str, object] | None = None,
        capacity: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        """Close this attempt in a resumable or terminal state."""
        normalized_state = LifecycleState(state)
        if normalized_state is LifecycleState.RUNNING:
            raise ConsultLifecycleTransitionError("Use heartbeat for a running event")
        return self._append(
            event_type=LifecycleEventType.STATE_TRANSITION,
            state=normalized_state,
            phase=LifecyclePhase(phase),
            reason_code=_normalize_reason_code(reason_code),
            progress=progress,
            capacity=capacity,
        )

    def finish(
        self,
        state: LifecycleState | str,
        *,
        phase: LifecyclePhase | str = LifecyclePhase.TRACE_FINALIZE,
        reason_code: str,
        progress: Mapping[str, object] | None = None,
        capacity: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        """Append exactly one immutable terminal event for this attempt."""
        normalized_state = LifecycleState(state)
        if normalized_state not in TERMINAL_STATES:
            raise ConsultLifecycleTransitionError("finish requires a terminal state")
        return self.transition(
            normalized_state,
            phase=phase,
            reason_code=reason_code,
            progress=progress,
            capacity=capacity,
        )


__all__ = [
    "CONSULT_LIFECYCLE_KIND",
    "CONSULT_LIFECYCLE_SCHEMA_VERSION",
    "RESUMABLE_STATES",
    "TERMINAL_STATES",
    "ConsultLifecycle",
    "ConsultLifecycleElapsedLimitError",
    "ConsultLifecycleError",
    "ConsultLifecycleJournalError",
    "ConsultLifecycleLockTimeoutError",
    "ConsultLifecycleStorageError",
    "ConsultLifecycleTransitionError",
    "LifecycleEventType",
    "LifecyclePhase",
    "LifecycleState",
    "load_consult_lifecycle_events",
]
