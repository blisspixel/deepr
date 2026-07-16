"""Validated contracts for protocol-neutral expert conversations."""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

CONVERSATION_SCHEMA_VERSION = "deepr-expert-conversation-v1"
CONVERSATION_KIND = "deepr.expert.conversation"
TURN_SCHEMA_VERSION = "deepr-expert-conversation-turn-v1"
TURN_KIND = "deepr.expert.conversation_turn"
EVENT_SCHEMA_VERSION = "deepr-expert-conversation-event-v1"
EVENT_KIND = "deepr.expert.conversation_event"
SNAPSHOT_SCHEMA_VERSION = "deepr-expert-context-snapshot-v1"
SNAPSHOT_KIND = "deepr.expert.context_snapshot"
ERROR_SCHEMA_VERSION = "deepr-expert-conversation-error-v1"
ERROR_KIND = "deepr.expert.conversation_error"

DEFAULT_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 365
MAX_RECENT_TURNS = 6
MAX_ATTEMPTS_PER_TURN = 100
DEFAULT_MAX_CONTEXT_BYTES = 65_536
MAX_MESSAGE_BYTES = 131_072
MAX_DECISION_BRIEF_BYTES = 65_536
MAX_SNAPSHOT_BYTES = 524_288
LEASE_GRACE_SECONDS = 30
HOST_ACTION_BOUNDARY = "Deepr provides advice only; the host decides and enacts downstream work."
CONTEXT_BUILDER_VERSION = "conversation-context-v1"

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TRACE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9:_-]{7,127}$")


class ConversationState(StrEnum):
    OPEN = "open"
    INPUT_REQUIRED = "input_required"
    WAITING_CAPACITY = "waiting_capacity"
    CLOSED = "closed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TurnState(StrEnum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    INPUT_REQUIRED = "input_required"
    WAITING_CAPACITY = "waiting_capacity"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BUDGET_EXHAUSTED = "budget_exhausted"
    VERIFIER_FAILED = "verifier_failed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class ConsultationMode(StrEnum):
    FOCUSED = "focused"
    COUNCIL = "council"
    STRUCTURED_PANEL = "structured_panel"
    DEEP = "deep"


class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    NOT_FOUND = "not_found"
    VERSION_CONFLICT = "version_conflict"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    CONVERSATION_BUSY = "conversation_busy"
    INVALID_STATE = "invalid_state"
    OWNERSHIP_DENIED = "ownership_denied"
    RETENTION_EXPIRED = "retention_expired"
    CONTENT_DELETED = "content_deleted"
    CAPACITY_EXHAUSTED = "capacity_exhausted"
    WAITING_CAPACITY = "waiting_capacity"
    EXECUTOR_FAILED = "executor_failed"
    STORAGE_FAILED = "storage_failed"


class ConversationError(Exception):
    """Typed adapter-safe conversation failure."""

    def __init__(
        self,
        code: ErrorCode,
        safe_message: str,
        *,
        retryable: bool = False,
        conversation_id: str | None = None,
        current_version: int | None = None,
        state: ConversationState | None = None,
        expected_version: int | None = None,
        field_name: str | None = None,
        retry_after_ms: int | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable
        self.conversation_id = conversation_id
        self.current_version = current_version
        self.state = state
        self.expected_version = expected_version
        self.field_name = field_name
        self.retry_after_ms = retry_after_ms

    def to_envelope(self) -> dict[str, Any]:
        return {
            "schema_version": ERROR_SCHEMA_VERSION,
            "kind": ERROR_KIND,
            "error": {
                "code": self.code.value,
                "safe_message": self.safe_message,
                "retryable": self.retryable,
                "conversation_id": self.conversation_id,
                "current_version": self.current_version,
                "state": self.state.value if self.state is not None else None,
                "details": {
                    "expected_version": self.expected_version,
                    "current_version": self.current_version,
                    "field": self.field_name,
                    "retry_after_ms": self.retry_after_ms,
                },
            },
        }


class ConversationNotFound(ConversationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.NOT_FOUND, "Conversation not found.")


class VersionConflict(ConversationError):
    def __init__(
        self,
        conversation_id: str,
        *,
        expected_version: int,
        current_version: int,
        state: ConversationState,
    ) -> None:
        super().__init__(
            ErrorCode.VERSION_CONFLICT,
            "The conversation changed; fetch current state before retrying.",
            retryable=True,
            conversation_id=conversation_id,
            expected_version=expected_version,
            current_version=current_version,
            state=state,
        )


class IdempotencyConflict(ConversationError):
    def __init__(self, conversation_id: str | None = None) -> None:
        super().__init__(
            ErrorCode.IDEMPOTENCY_CONFLICT,
            "The idempotency key was already used for a different request.",
            conversation_id=conversation_id,
        )


class ConversationBusy(ConversationError):
    def __init__(self, conversation_id: str, version: int, state: ConversationState) -> None:
        super().__init__(
            ErrorCode.CONVERSATION_BUSY,
            "The conversation already has an active turn.",
            retryable=True,
            conversation_id=conversation_id,
            current_version=version,
            state=state,
            retry_after_ms=250,
        )


def invalid_request(message: str, *, field_name: str | None = None) -> ConversationError:
    return ConversationError(ErrorCode.INVALID_REQUEST, message, field_name=field_name)


def canonical_json(value: Any) -> str:
    """Serialize JSON deterministically and reject non-finite numbers."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise invalid_request("Value must be finite JSON data.") from exc


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def owner_binding_sha256(owner_id: str) -> str:
    if not isinstance(owner_id, str):
        raise invalid_request("Owner identity must contain 1 to 256 characters.", field_name="owner_id")
    normalized = owner_id.strip()
    if not normalized or len(normalized) > 256:
        raise invalid_request("Owner identity must contain 1 to 256 characters.", field_name="owner_id")
    return sha256_text(f"deepr-owner-v1\0{normalized}")


def idempotency_key_sha256(key: str) -> str:
    if not isinstance(key, str) or not _IDEMPOTENCY_RE.fullmatch(key):
        raise invalid_request(
            "Idempotency key must contain 1 to 128 safe identifier characters.",
            field_name="idempotency_key",
        )
    return sha256_text(f"deepr-idempotency-v1\0{key}")


def new_opaque_id(prefix: str) -> str:
    """Generate an opaque id with exactly 128 bits of random entropy."""
    return f"{prefix}_{secrets.token_hex(16)}"


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise invalid_request("Timestamp must include a timezone.")
    return value.astimezone(UTC)


def parse_datetime(value: str) -> datetime:
    try:
        return require_utc(datetime.fromisoformat(value))
    except (TypeError, ValueError) as exc:
        raise invalid_request("Stored timestamp is invalid.") from exc


def validate_sha256(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise invalid_request(f"{field_name} must be a lowercase SHA-256 hex digest.", field_name=field_name)


def validate_message(value: str, *, field_name: str = "message", maximum_bytes: int = MAX_MESSAGE_BYTES) -> None:
    if not isinstance(value, str) or not value.strip():
        raise invalid_request(f"{field_name} must be non-empty text.", field_name=field_name)
    if utf8_size(value) > maximum_bytes:
        raise invalid_request(f"{field_name} exceeds its byte ceiling.", field_name=field_name)


@dataclass(frozen=True)
class ConversationBounds:
    max_turns: int = 20
    max_model_calls: int = 40
    max_input_tokens: int = 100_000
    max_output_tokens: int = 50_000
    max_context_bytes: int = DEFAULT_MAX_CONTEXT_BYTES
    max_elapsed_seconds: int = 300
    max_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        integer_bounds = {
            "max_turns": (self.max_turns, 1, 100),
            "max_model_calls": (self.max_model_calls, 1, 1000),
            "max_input_tokens": (self.max_input_tokens, 1, 1_000_000_000),
            "max_output_tokens": (self.max_output_tokens, 1, 1_000_000_000),
            "max_context_bytes": (self.max_context_bytes, 1024, 1_048_576),
            "max_elapsed_seconds": (self.max_elapsed_seconds, 1, 86_400),
        }
        for name, (value, minimum, maximum) in integer_bounds.items():
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise invalid_request(f"{name} is outside its supported range.", field_name=name)
        if (
            isinstance(self.max_cost_usd, bool)
            or not isinstance(self.max_cost_usd, (int, float))
            or not math.isfinite(float(self.max_cost_usd))
            or not 0 <= float(self.max_cost_usd) <= 1_000_000
        ):
            raise invalid_request("max_cost_usd is outside its supported range.", field_name="max_cost_usd")

    def to_dict(self) -> dict[str, int | float]:
        return {
            "max_turns": self.max_turns,
            "max_model_calls": self.max_model_calls,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_context_bytes": self.max_context_bytes,
            "max_elapsed_seconds": self.max_elapsed_seconds,
            "max_cost_usd": float(self.max_cost_usd),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ConversationBounds:
        if not isinstance(value, dict):
            raise invalid_request("Conversation bounds must be an object.", field_name="bounds")
        try:
            return cls(**value)
        except TypeError as exc:
            raise invalid_request("Conversation bounds do not match the v1 contract.", field_name="bounds") from exc


@dataclass(frozen=True)
class BackendSelection:
    capacity_source: str
    backend_class: str
    model: str
    fallback_policy: str = "none"
    live_metered_fallback: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.capacity_source, str) or self.capacity_source not in {
            "local_owned",
            "plan_quota",
            "metered_api",
        }:
            raise invalid_request("Unsupported capacity source.", field_name="capacity_source")
        if not isinstance(self.backend_class, str) or self.backend_class not in {"local", "plan", "api"}:
            raise invalid_request("Unsupported backend class.", field_name="backend_class")
        if not isinstance(self.model, str) or not self.model.strip() or len(self.model) > 256:
            raise invalid_request("Model must contain 1 to 256 characters.", field_name="model")
        if not isinstance(self.fallback_policy, str) or self.fallback_policy not in {"none", "explicit_only"}:
            raise invalid_request("Unsupported fallback policy.", field_name="fallback_policy")
        if not isinstance(self.live_metered_fallback, bool):
            raise invalid_request("live_metered_fallback must be boolean.", field_name="live_metered_fallback")

    @classmethod
    def local(cls, model: str) -> BackendSelection:
        return cls(capacity_source="local_owned", backend_class="local", model=model)

    def require_stage_one_local(self, bounds: ConversationBounds) -> None:
        if (
            self.capacity_source != "local_owned"
            or self.backend_class != "local"
            or self.fallback_policy != "none"
            or self.live_metered_fallback
            or bounds.max_cost_usd != 0.0
        ):
            raise invalid_request(
                "The protocol-neutral local core accepts local owned capacity with no fallback and a $0 ceiling only.",
                field_name="backend",
            )

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "capacity_source": self.capacity_source,
            "backend_class": self.backend_class,
            "model": self.model,
            "fallback_policy": self.fallback_policy,
            "live_metered_fallback": self.live_metered_fallback,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BackendSelection:
        if not isinstance(value, dict):
            raise invalid_request("Backend selection must be an object.", field_name="backend")
        try:
            return cls(**value)
        except TypeError as exc:
            raise invalid_request("Backend selection does not match the v1 contract.", field_name="backend") from exc


@dataclass(frozen=True)
class ExpertSnapshotInput:
    expert_name: str
    state_sha256: str
    source_position: str
    packet: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.expert_name, str) or not self.expert_name.strip() or len(self.expert_name) > 128:
            raise invalid_request("Expert name must contain 1 to 128 characters.", field_name="expert_name")
        validate_sha256(self.state_sha256, field_name="state_sha256")
        if (
            not isinstance(self.source_position, str)
            or not self.source_position.strip()
            or len(self.source_position) > 256
        ):
            raise invalid_request("Source position must contain 1 to 256 characters.", field_name="source_position")
        if not isinstance(self.packet, dict):
            raise invalid_request("Expert snapshot packet must be an object.", field_name="packet")
        encoded = canonical_json(self.packet)
        if utf8_size(encoded) > MAX_SNAPSHOT_BYTES:
            raise invalid_request("Expert snapshot packet exceeds its byte ceiling.", field_name="packet")
        object.__setattr__(self, "packet", json.loads(encoded))

    @property
    def packet_sha256(self) -> str:
        return sha256_json(self.packet)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "state_sha256": self.state_sha256,
            "source_position": self.source_position,
            "packet_sha256": self.packet_sha256,
            "packet": self.packet,
        }


def _normalize_start_snapshots(values: Any, mode: Any) -> tuple[ExpertSnapshotInput, ...]:
    if not isinstance(values, (list, tuple)) or any(not isinstance(item, ExpertSnapshotInput) for item in values):
        raise invalid_request("Expert snapshots must match the v1 contract.", field_name="expert_snapshots")
    snapshots = tuple(values)
    if not 1 <= len(snapshots) <= 10:
        raise invalid_request("One to ten expert snapshots are required.", field_name="expert_snapshots")
    names = [snapshot.expert_name for snapshot in snapshots]
    if len(names) != len(set(names)):
        raise invalid_request("Expert names must be unique and canonical.", field_name="expert_snapshots")
    if not isinstance(mode, ConsultationMode):
        raise invalid_request("Conversation mode is invalid.", field_name="mode")
    if mode not in {ConsultationMode.FOCUSED, ConsultationMode.COUNCIL}:
        raise invalid_request("Stage 1 supports focused and council conversation modes only.", field_name="mode")
    if mode is ConsultationMode.FOCUSED and len(names) != 1:
        raise invalid_request("Focused mode requires exactly one expert.", field_name="expert_snapshots")
    return snapshots


@dataclass(frozen=True)
class ConversationStartRequest:
    owner_id: str
    idempotency_key: str
    message: str
    expert_snapshots: tuple[ExpertSnapshotInput, ...]
    backend: BackendSelection
    bounds: ConversationBounds = field(default_factory=ConversationBounds)
    mode: ConsultationMode = ConsultationMode.FOCUSED
    decision_brief: str | None = None
    retention_days: int = DEFAULT_RETENTION_DAYS

    def __post_init__(self) -> None:
        owner_binding_sha256(self.owner_id)
        idempotency_key_sha256(self.idempotency_key)
        validate_message(self.message)
        if not isinstance(self.backend, BackendSelection):
            raise invalid_request("Backend selection is invalid.", field_name="backend")
        if not isinstance(self.bounds, ConversationBounds):
            raise invalid_request("Conversation bounds are invalid.", field_name="bounds")
        if self.decision_brief is not None:
            validate_message(
                self.decision_brief,
                field_name="decision_brief",
                maximum_bytes=MAX_DECISION_BRIEF_BYTES,
            )
        snapshots = _normalize_start_snapshots(self.expert_snapshots, self.mode)
        object.__setattr__(self, "expert_snapshots", snapshots)
        if (
            isinstance(self.retention_days, bool)
            or not isinstance(self.retention_days, int)
            or not 1 <= self.retention_days <= MAX_RETENTION_DAYS
        ):
            raise invalid_request("Retention must be between 1 and 365 days.", field_name="retention_days")
        self.backend.require_stage_one_local(self.bounds)

    @property
    def owner_hash(self) -> str:
        return owner_binding_sha256(self.owner_id)

    @property
    def idempotency_hash(self) -> str:
        return idempotency_key_sha256(self.idempotency_key)

    def request_material(self) -> dict[str, Any]:
        return {
            "operation": "start",
            "message": self.message,
            "decision_brief": self.decision_brief,
            # Snapshot packets are server-compiled state, not caller input. A
            # duplicate delivery must replay the first recorded conversation
            # even if an expert changed between attempts. The canonical roster
            # remains part of the request identity so a reused key cannot
            # silently target different experts.
            "expert_names": [snapshot.expert_name for snapshot in self.expert_snapshots],
            "backend": self.backend.to_dict(),
            "bounds": self.bounds.to_dict(),
            "mode": self.mode.value,
            "retention_days": self.retention_days,
        }


@dataclass(frozen=True)
class ConversationContinueRequest:
    owner_id: str
    conversation_id: str
    expected_version: int
    idempotency_key: str
    message: str
    input_request_id: str | None = None

    def __post_init__(self) -> None:
        owner_binding_sha256(self.owner_id)
        idempotency_key_sha256(self.idempotency_key)
        validate_message(self.message)
        if (
            isinstance(self.expected_version, bool)
            or not isinstance(self.expected_version, int)
            or self.expected_version < 1
        ):
            raise invalid_request("Expected version must be a positive integer.", field_name="expected_version")
        if not isinstance(self.conversation_id, str) or not re.fullmatch(
            r"conv_[A-Za-z0-9_-]{22,64}", self.conversation_id
        ):
            raise invalid_request("Conversation id has an invalid shape.", field_name="conversation_id")
        if self.input_request_id is not None and (
            not isinstance(self.input_request_id, str)
            or not re.fullmatch(r"input_[A-Za-z0-9_-]{16,64}", self.input_request_id)
        ):
            raise invalid_request("Input request id has an invalid shape.", field_name="input_request_id")

    @property
    def owner_hash(self) -> str:
        return owner_binding_sha256(self.owner_id)

    @property
    def idempotency_hash(self) -> str:
        return idempotency_key_sha256(self.idempotency_key)

    def request_material(self) -> dict[str, Any]:
        return {
            "operation": "continue",
            "conversation_id": self.conversation_id,
            "message": self.message,
            "input_request_id": self.input_request_id,
        }


@dataclass(frozen=True)
class ConversationResumeRequest:
    owner_id: str
    conversation_id: str
    expected_version: int
    idempotency_key: str

    def __post_init__(self) -> None:
        owner_binding_sha256(self.owner_id)
        idempotency_key_sha256(self.idempotency_key)
        if (
            isinstance(self.expected_version, bool)
            or not isinstance(self.expected_version, int)
            or self.expected_version < 1
        ):
            raise invalid_request("Expected version must be a positive integer.", field_name="expected_version")
        if not isinstance(self.conversation_id, str) or not re.fullmatch(
            r"conv_[A-Za-z0-9_-]{22,64}", self.conversation_id
        ):
            raise invalid_request("Conversation id has an invalid shape.", field_name="conversation_id")

    @property
    def owner_hash(self) -> str:
        return owner_binding_sha256(self.owner_id)

    @property
    def idempotency_hash(self) -> str:
        return idempotency_key_sha256(self.idempotency_key)

    def request_material(self, turn_id: str) -> dict[str, Any]:
        return {"operation": "resume", "conversation_id": self.conversation_id, "turn_id": turn_id}


@dataclass(frozen=True)
class TurnUsage:
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: int = 0
    cost_usd: float = 0.0

    def __post_init__(self) -> None:
        for name in ("model_calls", "input_tokens", "output_tokens", "elapsed_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise invalid_request(f"{name} must be a non-negative integer.", field_name=name)
        if (
            isinstance(self.cost_usd, bool)
            or not isinstance(self.cost_usd, (int, float))
            or not math.isfinite(float(self.cost_usd))
            or self.cost_usd < 0
        ):
            raise invalid_request("cost_usd must be finite and non-negative.", field_name="cost_usd")

    def to_dict(self) -> dict[str, int | float]:
        return {
            "model_calls": self.model_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "elapsed_ms": self.elapsed_ms,
            "cost_usd": float(self.cost_usd),
        }


def _validate_execution_result_header(
    state: Any,
    stop_reason: Any,
    retryable: Any,
    usage: Any,
) -> None:
    allowed = {
        TurnState.COMPLETED,
        TurnState.INPUT_REQUIRED,
        TurnState.WAITING_CAPACITY,
        TurnState.CANCELLED,
        TurnState.BUDGET_EXHAUSTED,
        TurnState.VERIFIER_FAILED,
        TurnState.FAILED,
    }
    if not isinstance(state, TurnState) or state not in allowed:
        raise invalid_request("Executor returned an unsupported terminal state.", field_name="state")
    if not isinstance(stop_reason, str):
        raise invalid_request("Executor stop reason must be text.", field_name="stop_reason")
    if not isinstance(retryable, bool):
        raise invalid_request("Executor retryable flag must be boolean.", field_name="retryable")
    if not isinstance(usage, TurnUsage):
        raise invalid_request("Executor usage must match the v1 contract.", field_name="usage")
    if stop_reason != state.value:
        raise invalid_request("Executor stop reason must match its typed state.", field_name="stop_reason")


def _validate_execution_result_artifact(state: TurnState, artifact: Any) -> None:
    if state in {TurnState.COMPLETED, TurnState.INPUT_REQUIRED}:
        if not isinstance(artifact, dict):
            raise invalid_request("Completed or input-required turns need an answer artifact.", field_name="artifact")
        validate_answer_artifact(artifact, expected_state=state)
    elif artifact is not None:
        raise invalid_request("This turn state cannot carry an answer artifact.", field_name="artifact")


@dataclass(frozen=True)
class TurnExecutionResult:
    state: TurnState
    stop_reason: str
    retryable: bool
    usage: TurnUsage = field(default_factory=TurnUsage)
    artifact: dict[str, Any] | None = None
    consult_trace_id: str | None = None
    consult_lifecycle_trace_id: str | None = None

    def __post_init__(self) -> None:
        _validate_execution_result_header(self.state, self.stop_reason, self.retryable, self.usage)
        _validate_execution_result_artifact(self.state, self.artifact)
        for field_name, value in (
            ("consult_trace_id", self.consult_trace_id),
            ("consult_lifecycle_trace_id", self.consult_lifecycle_trace_id),
        ):
            if value is not None and (not isinstance(value, str) or not _TRACE_ID_RE.fullmatch(value)):
                raise invalid_request(f"{field_name} has an invalid shape.", field_name=field_name)
        if self.artifact is not None:
            object.__setattr__(self, "artifact", json.loads(canonical_json(self.artifact)))

    @classmethod
    def completed(
        cls,
        artifact: dict[str, Any],
        *,
        usage: TurnUsage | None = None,
        consult_trace_id: str | None = None,
        consult_lifecycle_trace_id: str | None = None,
    ) -> TurnExecutionResult:
        return cls(
            state=TurnState.COMPLETED,
            stop_reason="completed",
            retryable=False,
            artifact=artifact,
            usage=usage or TurnUsage(),
            consult_trace_id=consult_trace_id,
            consult_lifecycle_trace_id=consult_lifecycle_trace_id,
        )

    @classmethod
    def waiting_capacity(cls) -> TurnExecutionResult:
        return cls(state=TurnState.WAITING_CAPACITY, stop_reason="waiting_capacity", retryable=True)


@dataclass(frozen=True)
class ConversationExecutionContext:
    conversation_id: str
    turn_id: str
    attempt_id: str
    mode: ConsultationMode
    expert_names: tuple[str, ...]
    backend: BackendSelection
    message: str
    decision_brief: str | None
    context_snapshot: dict[str, Any]
    recent_turns: tuple[dict[str, Any], ...]
    decision_ledger: dict[str, Any]
    context_bytes: int
    context_sha256: str
    bounds: ConversationBounds
    remaining: dict[str, int | float]


@dataclass(frozen=True)
class TurnLease:
    conversation_id: str
    turn_id: str
    attempt_id: str
    projection_version: int
    dispatch_required: bool
    replayed: bool
    execution_context: ConversationExecutionContext | None


@dataclass(frozen=True)
class ConversationOperationResult:
    conversation: dict[str, Any]
    turn: dict[str, Any] | None
    replayed: bool = False
    dispatch_status: str = "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation": self.conversation,
            "turn": self.turn,
            "replayed": self.replayed,
            "dispatch_status": self.dispatch_status,
        }


def validate_answer_artifact(artifact: dict[str, Any], *, expected_state: TurnState) -> None:
    required = {
        "direct_answer",
        "experts_consulted",
        "assumptions",
        "evidence",
        "uncertainty",
        "agreements",
        "dissent",
        "decision_implications",
        "change_conditions",
        "unresolved_gaps",
        "recommended_next_question",
        "semantic_status",
        "host_action_boundary",
    }
    if not isinstance(artifact, dict) or set(artifact) != required:
        raise invalid_request("Answer artifact fields do not match the v1 contract.", field_name="artifact")
    if not isinstance(artifact["direct_answer"], str):
        raise invalid_request("Direct answer must be text.", field_name="artifact.direct_answer")
    validate_message(artifact["direct_answer"], field_name="artifact.direct_answer", maximum_bytes=262_144)
    experts = artifact["experts_consulted"]
    if (
        not isinstance(experts, list)
        or not 1 <= len(experts) <= 10
        or any(
            not isinstance(expert, str) or not expert.strip() or expert != expert.strip() or len(expert) > 128
            for expert in experts
        )
        or len(experts) != len(set(experts))
    ):
        raise invalid_request("Answer artifact expert roster is invalid.", field_name="artifact.experts_consulted")
    list_fields = (
        "assumptions",
        "evidence",
        "agreements",
        "dissent",
        "decision_implications",
        "change_conditions",
        "unresolved_gaps",
    )
    if any(not isinstance(artifact[field_name], list) for field_name in list_fields):
        raise invalid_request("Answer artifact collection fields must be arrays.", field_name="artifact")
    _validate_assumptions(artifact["assumptions"])
    _validate_evidence(artifact["evidence"])
    _validate_uncertainty(artifact["uncertainty"])
    _validate_text_list(artifact["agreements"], "artifact.agreements")
    _validate_dissent(artifact["dissent"])
    _validate_decision_implications(artifact["decision_implications"])
    _validate_artifact_references(artifact)
    _validate_text_list(artifact["change_conditions"], "artifact.change_conditions")
    _validate_text_list(artifact["unresolved_gaps"], "artifact.unresolved_gaps")
    _validate_artifact_status(artifact, expected_state=expected_state)
    encoded = canonical_json(artifact)
    if utf8_size(encoded) > 524_288:
        raise invalid_request("Answer artifact exceeds its byte ceiling.", field_name="artifact")


def _validate_artifact_status(artifact: dict[str, Any], *, expected_state: TurnState) -> None:
    next_question = artifact["recommended_next_question"]
    if next_question is not None and (
        not isinstance(next_question, str) or not next_question.strip() or len(next_question) > 8192
    ):
        raise invalid_request(
            "Recommended next question must be null or bounded text.",
            field_name="artifact.recommended_next_question",
        )
    semantic_status = artifact["semantic_status"]
    if not isinstance(semantic_status, str) or semantic_status not in {
        "answered",
        "input_required",
        "evidence_required",
    }:
        raise invalid_request("Answer semantic status is invalid.", field_name="artifact.semantic_status")
    if expected_state is TurnState.INPUT_REQUIRED and semantic_status != "input_required":
        raise invalid_request(
            "Input-required turn must request input semantically.", field_name="artifact.semantic_status"
        )
    if expected_state is TurnState.COMPLETED and semantic_status == "input_required":
        raise invalid_request(
            "Completed turn cannot carry input-required semantic status.", field_name="artifact.semantic_status"
        )
    if artifact["host_action_boundary"] != HOST_ACTION_BOUNDARY:
        raise invalid_request(
            "Answer artifact cannot widen host authority.", field_name="artifact.host_action_boundary"
        )


def _validate_assumptions(values: Any) -> None:
    if len(values) > 100 or any(
        not isinstance(item, dict)
        or set(item) != {"text", "source"}
        or not isinstance(item["text"], str)
        or not item["text"].strip()
        or len(item["text"]) > 4096
        or not isinstance(item["source"], str)
        or item["source"] not in {"host_supplied", "model_proposed"}
        for item in values
    ):
        raise invalid_request("Answer assumptions are invalid.", field_name="artifact.assumptions")


def _validate_evidence(values: Any) -> None:
    if len(values) > 200 or any(
        not isinstance(item, dict)
        or set(item) != {"evidence_ref", "source_type", "expert_name", "citation"}
        or not isinstance(item["evidence_ref"], str)
        or not item["evidence_ref"].strip()
        or len(item["evidence_ref"]) > 256
        or not isinstance(item["source_type"], str)
        or item["source_type"] not in {"expert_state", "prior_turn", "caller_supplied", "external_source"}
        or (
            item["expert_name"] is not None
            and (
                not isinstance(item["expert_name"], str)
                or not item["expert_name"].strip()
                or len(item["expert_name"]) > 128
            )
        )
        or (
            item["citation"] is not None
            and (not isinstance(item["citation"], str) or not item["citation"].strip() or len(item["citation"]) > 2048)
        )
        for item in values
    ):
        raise invalid_request("Answer evidence entries are invalid.", field_name="artifact.evidence")
    references = [item["evidence_ref"] for item in values]
    if len(references) != len(set(references)):
        raise invalid_request("Answer evidence references must be unique.", field_name="artifact.evidence")


def _validate_uncertainty(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"kind", "value", "rationale"}:
        raise invalid_request("Answer uncertainty must match its v1 shape.", field_name="artifact.uncertainty")
    if not isinstance(value["kind"], str) or value["kind"] not in {
        "qualitative",
        "probability",
        "interval",
        "not_applicable",
    }:
        raise invalid_request("Answer uncertainty kind is invalid.", field_name="artifact.uncertainty.kind")
    uncertainty_value = value["value"]
    valid_value = uncertainty_value is None or (isinstance(uncertainty_value, str) and len(uncertainty_value) <= 256)
    valid_value = valid_value or (
        isinstance(uncertainty_value, (int, float))
        and not isinstance(uncertainty_value, bool)
        and math.isfinite(float(uncertainty_value))
        and 0 <= float(uncertainty_value) <= 1
    )
    valid_value = valid_value or (
        isinstance(uncertainty_value, list)
        and len(uncertainty_value) == 2
        and all(
            isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(float(item))
            for item in uncertainty_value
        )
    )
    if (
        not valid_value
        or not isinstance(value["rationale"], str)
        or not value["rationale"].strip()
        or len(value["rationale"]) > 4096
    ):
        raise invalid_request("Answer uncertainty value is invalid.", field_name="artifact.uncertainty")


def _validate_text_list(values: Any, field_name: str) -> None:
    if len(values) > 100 or any(not isinstance(item, str) or not item.strip() or len(item) > 4096 for item in values):
        raise invalid_request("Answer text collection is invalid.", field_name=field_name)


def _validate_dissent(values: Any) -> None:
    if len(values) > 100 or any(
        not isinstance(item, dict)
        or set(item) != {"position", "expert_names", "evidence_refs"}
        or not isinstance(item["position"], str)
        or not item["position"].strip()
        or len(item["position"]) > 8192
        or not isinstance(item["expert_names"], list)
        or not item["expert_names"]
        or len(item["expert_names"]) > 10
        or any(not isinstance(name, str) or not name.strip() or len(name) > 128 for name in item["expert_names"])
        or len(item["expert_names"]) != len(set(item["expert_names"]))
        or not isinstance(item["evidence_refs"], list)
        or len(item["evidence_refs"]) > 100
        or any(not isinstance(ref, str) or not ref.strip() or len(ref) > 256 for ref in item["evidence_refs"])
        or len(item["evidence_refs"]) != len(set(item["evidence_refs"]))
        for item in values
    ):
        raise invalid_request("Answer dissent entries are invalid.", field_name="artifact.dissent")


def _validate_decision_implications(values: Any) -> None:
    if len(values) > 100 or any(
        not isinstance(item, dict)
        or set(item) != {"proposal", "authority"}
        or not isinstance(item["proposal"], str)
        or not item["proposal"].strip()
        or len(item["proposal"]) > 8192
        or item["authority"] != "proposal_only"
        for item in values
    ):
        raise invalid_request(
            "Every decision implication must remain proposal-only.",
            field_name="artifact.decision_implications",
        )


def _validate_artifact_references(artifact: dict[str, Any]) -> None:
    experts = set(artifact["experts_consulted"])
    evidence_refs = {item["evidence_ref"] for item in artifact["evidence"]}
    if any(item["expert_name"] is not None and item["expert_name"] not in experts for item in artifact["evidence"]):
        raise invalid_request(
            "Answer evidence names an expert outside the consulted roster.", field_name="artifact.evidence"
        )
    if any(
        not set(item["expert_names"]).issubset(experts) or not set(item["evidence_refs"]).issubset(evidence_refs)
        for item in artifact["dissent"]
    ):
        raise invalid_request(
            "Answer dissent contains an unresolved expert or evidence reference.", field_name="artifact.dissent"
        )


def remaining_capacity(bounds: ConversationBounds, usage: dict[str, Any]) -> dict[str, int | float]:
    return {
        "turns": max(0, bounds.max_turns - int(usage["turns_started"])),
        "model_calls": max(0, bounds.max_model_calls - int(usage["model_calls"])),
        "input_tokens": max(0, bounds.max_input_tokens - int(usage["input_tokens"])),
        "output_tokens": max(0, bounds.max_output_tokens - int(usage["output_tokens"])),
        "elapsed_ms": max(0, bounds.max_elapsed_seconds * 1000 - int(usage["elapsed_ms"])),
        "cost_usd": max(0.0, float(bounds.max_cost_usd) - float(usage["cost_usd"])),
    }


def lease_expiry(now: datetime, bounds: ConversationBounds, *, elapsed_ms: int = 0) -> datetime:
    """Bound recovery lease time by the conversation's remaining elapsed budget."""
    remaining_ms = max(1, bounds.max_elapsed_seconds * 1000 - elapsed_ms)
    return require_utc(now) + timedelta(milliseconds=remaining_ms + LEASE_GRACE_SECONDS * 1000)
