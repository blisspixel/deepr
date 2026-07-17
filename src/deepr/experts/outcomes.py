"""Append-only operator-attested outcomes for expert-supported decisions."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self, TypedDict

from filelock import FileLock
from filelock import Timeout as FileLockTimeout
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from deepr.experts.paths import canonical_expert_dir
from deepr.utils.atomic_io import append_jsonl_durable
from deepr.utils.security import SecurityError

EXPERT_OUTCOME_SCHEMA_VERSION = "deepr-expert-outcome-v1"
EXPERT_OUTCOME_KIND = "deepr.expert.outcome"
EXPERT_OUTCOME_SUMMARY_SCHEMA_VERSION = "deepr-expert-outcome-summary-v1"
EXPERT_OUTCOME_SUMMARY_KIND = "deepr.expert.outcome_summary"
OUTCOME_RELATIVE_PATH = Path("outcomes") / "outcomes.jsonl"

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
type OutcomeResult = Literal["succeeded", "mixed", "failed", "unresolved"]

_RESULTS: tuple[OutcomeResult, ...] = ("succeeded", "mixed", "failed", "unresolved")
_LOCK_TIMEOUT_SECONDS = 10.0


class OutcomeStorageError(RuntimeError):
    """Raised when outcome history cannot be trusted or appended."""


class OutcomeConflictError(OutcomeStorageError):
    """Raised when an existing outcome id is reused for different content."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _clean_text(value: str, *, field_name: str, max_length: int) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    if len(cleaned) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return cleaned


def _clean_id(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not _ID_PATTERN.fullmatch(cleaned):
        raise ValueError(f"{field_name} contains unsupported characters")
    return cleaned


def _clean_refs(values: list[str], *, field_name: str) -> list[str]:
    cleaned = [_clean_text(value, field_name=field_name, max_length=2000) for value in values]
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"{field_name} must not contain duplicates")
    return cleaned


def _validation_field_name(info: ValidationInfo) -> str:
    if info.field_name is None:
        raise ValueError("validator field name is unavailable")
    return info.field_name.replace("_", " ")


def normalize_timestamp(value: str, *, field_name: str = "timestamp") -> str:
    """Require an ISO 8601 timestamp with an explicit timezone."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.isoformat()


class ExpertOutcomeDraft(_StrictModel):
    """Operator-supplied outcome content before canonical metadata is attached."""

    expert_name: str
    decision_id: str
    decision_summary: str
    result: OutcomeResult
    observation: str
    observed_at: str
    attested_by: str
    consult_trace_id: str | None = None
    belief_ids: list[str] = Field(default_factory=list, max_length=100)
    source_refs: list[str] = Field(default_factory=list, max_length=100)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    supersedes_outcome_id: str | None = None

    @field_validator("expert_name")
    @classmethod
    def validate_expert_name(cls, value: str) -> str:
        return _clean_text(value, field_name="expert name", max_length=120)

    @field_validator("decision_id")
    @classmethod
    def validate_decision_id(cls, value: str) -> str:
        return _clean_id(value, field_name="decision id")

    @field_validator("consult_trace_id", "supersedes_outcome_id")
    @classmethod
    def validate_optional_id(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _clean_id(value, field_name=_validation_field_name(info))

    @field_validator("decision_summary")
    @classmethod
    def validate_decision_summary(cls, value: str) -> str:
        return _clean_text(value, field_name="decision summary", max_length=4000)

    @field_validator("observation")
    @classmethod
    def validate_observation(cls, value: str) -> str:
        return _clean_text(value, field_name="observation", max_length=8000)

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: str) -> str:
        return normalize_timestamp(value, field_name="observed at")

    @field_validator("attested_by")
    @classmethod
    def validate_attester(cls, value: str) -> str:
        return _clean_text(value, field_name="attested by", max_length=200)

    @field_validator("belief_ids")
    @classmethod
    def validate_belief_ids(cls, values: list[str]) -> list[str]:
        return [_clean_id(value, field_name="belief id") for value in values]

    @field_validator("source_refs", "evidence_refs")
    @classmethod
    def validate_reference_lists(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _clean_refs(values, field_name=_validation_field_name(info))

    @model_validator(mode="after")
    def validate_unique_belief_ids(self) -> Self:
        if len(set(self.belief_ids)) != len(self.belief_ids):
            raise ValueError("belief ids must not contain duplicates")
        return self


class OutcomeAuthorityContract(_StrictModel):
    operator_attested: Literal[True]
    human_authorship_claimed: Literal[False]
    reviewer_identity_verified: Literal[False]
    append_only: Literal[True]
    cost_usd: float = Field(ge=0.0, le=0.0)
    model_calls: Literal[0]
    automatic_learning: Literal[False]
    may_change_beliefs: Literal[False]
    may_change_routing: Literal[False]
    semantic_success_inferred: Literal[False]


class ExpertOutcome(_StrictModel):
    """One immutable observation of an expert-supported decision outcome."""

    schema_version: Literal["deepr-expert-outcome-v1"]
    kind: Literal["deepr.expert.outcome"]
    outcome_id: str
    content_hash: str
    recorded_at: str
    attested_at: str
    expert_name: str
    decision_id: str
    decision_summary: str
    result: OutcomeResult
    observation: str
    observed_at: str
    attested_by: str
    consult_trace_id: str | None
    belief_ids: list[str]
    source_refs: list[str]
    evidence_refs: list[str]
    supersedes_outcome_id: str | None
    contract: OutcomeAuthorityContract

    @field_validator("outcome_id", "decision_id")
    @classmethod
    def validate_required_id(cls, value: str, info: ValidationInfo) -> str:
        return _clean_id(value, field_name=_validation_field_name(info))

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        if not _HASH_PATTERN.fullmatch(value):
            raise ValueError("content hash must be a lowercase SHA-256 digest")
        return value

    @field_validator("recorded_at", "attested_at", "observed_at")
    @classmethod
    def validate_timestamps(cls, value: str, info: ValidationInfo) -> str:
        return normalize_timestamp(value, field_name=_validation_field_name(info))


@dataclass(frozen=True)
class OutcomeApplyResult:
    outcome: ExpertOutcome
    appended: bool


def outcome_content_hash(draft: ExpertOutcomeDraft) -> str:
    canonical = json.dumps(
        draft.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _draft_from_outcome(outcome: ExpertOutcome) -> ExpertOutcomeDraft:
    fields = ExpertOutcomeDraft.model_fields
    return ExpertOutcomeDraft.model_validate({name: getattr(outcome, name) for name in fields})


def _parse_history_record(line: str, *, line_number: int) -> ExpertOutcome:
    try:
        return ExpertOutcome.model_validate(json.loads(line))
    except (json.JSONDecodeError, ValueError) as exc:
        raise OutcomeStorageError(f"Invalid outcome history record at line {line_number}") from exc


def _validate_history_record(
    outcome: ExpertOutcome,
    *,
    expert_name: str,
    line_number: int,
    by_id: dict[str, ExpertOutcome],
    superseded_ids: set[str],
) -> None:
    if outcome.expert_name != expert_name:
        raise OutcomeStorageError(f"Outcome expert name mismatch at line {line_number}")
    if outcome.outcome_id in by_id:
        raise OutcomeStorageError(f"Duplicate outcome id at line {line_number}")
    if outcome_content_hash(_draft_from_outcome(outcome)) != outcome.content_hash:
        raise OutcomeStorageError(f"Outcome content hash mismatch at line {line_number}")
    supersedes = outcome.supersedes_outcome_id
    if supersedes is None:
        return
    earlier = by_id.get(supersedes)
    if earlier is None:
        raise OutcomeStorageError(f"Outcome supersedes an unknown earlier record at line {line_number}")
    if supersedes in superseded_ids:
        raise OutcomeStorageError(f"Outcome creates a branched correction at line {line_number}")
    if earlier.decision_id != outcome.decision_id:
        raise OutcomeStorageError(f"Outcome correction changes decision id at line {line_number}")


class ExpertOutcomeStore:
    """Append-only storage for operator-attested outcome observations."""

    def __init__(self, base_path: Path | str | None = None) -> None:
        self.base_path = Path(base_path) if base_path is not None else None

    def path_for(self, expert_name: str) -> Path:
        try:
            return canonical_expert_dir(expert_name, self.base_path) / OUTCOME_RELATIVE_PATH
        except SecurityError as exc:
            raise OutcomeStorageError("Expert outcome path failed safety validation") from exc

    def _load_unlocked(self, expert_name: str) -> list[ExpertOutcome]:
        normalized_name = _clean_text(expert_name, field_name="expert name", max_length=120)
        path = self.path_for(normalized_name)
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise OutcomeStorageError("Could not read expert outcome history") from exc
        outcomes: list[ExpertOutcome] = []
        by_id: dict[str, ExpertOutcome] = {}
        superseded_ids: set[str] = set()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            outcome = _parse_history_record(line, line_number=line_number)
            _validate_history_record(
                outcome,
                expert_name=normalized_name,
                line_number=line_number,
                by_id=by_id,
                superseded_ids=superseded_ids,
            )
            supersedes = outcome.supersedes_outcome_id
            if supersedes is not None:
                superseded_ids.add(supersedes)
            outcomes.append(outcome)
            by_id[outcome.outcome_id] = outcome
        return outcomes

    def load_all(self, expert_name: str) -> list[ExpertOutcome]:
        """Load all observations without creating filesystem state."""
        return self._load_unlocked(expert_name)

    def record(
        self,
        draft: ExpertOutcomeDraft,
        *,
        outcome_id: str | None = None,
        now: datetime | None = None,
    ) -> OutcomeApplyResult:
        """Append one outcome or return an exact idempotent match."""
        normalized_id = (
            _clean_id(outcome_id, field_name="outcome id") if outcome_id else f"outcome_{uuid.uuid4().hex[:16]}"
        )
        timestamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
        content_hash = outcome_content_hash(draft)
        path = self.path_for(draft.expert_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(path.with_suffix(path.suffix + ".lock")))
        try:
            with lock.acquire(timeout=_LOCK_TIMEOUT_SECONDS):
                outcomes = self._load_unlocked(draft.expert_name)
                by_id = {item.outcome_id: item for item in outcomes}
                existing = by_id.get(normalized_id)
                if existing is not None:
                    if existing.content_hash == content_hash:
                        return OutcomeApplyResult(outcome=existing, appended=False)
                    raise OutcomeConflictError(f"Outcome id '{normalized_id}' already exists with different content")
                if draft.supersedes_outcome_id is not None and draft.supersedes_outcome_id not in by_id:
                    raise OutcomeConflictError(
                        f"Superseded outcome '{draft.supersedes_outcome_id}' does not exist for this expert"
                    )
                superseded = draft.supersedes_outcome_id
                if superseded is not None:
                    if any(item.supersedes_outcome_id == superseded for item in outcomes):
                        raise OutcomeConflictError(f"Outcome '{superseded}' already has a correction")
                    if by_id[superseded].decision_id != draft.decision_id:
                        raise OutcomeConflictError("A correction must retain the earlier outcome's decision id")
                payload = {
                    "schema_version": EXPERT_OUTCOME_SCHEMA_VERSION,
                    "kind": EXPERT_OUTCOME_KIND,
                    "outcome_id": normalized_id,
                    "content_hash": content_hash,
                    "recorded_at": timestamp,
                    "attested_at": timestamp,
                    **draft.model_dump(mode="json"),
                    "contract": {
                        "operator_attested": True,
                        "human_authorship_claimed": False,
                        "reviewer_identity_verified": False,
                        "append_only": True,
                        "cost_usd": 0.0,
                        "model_calls": 0,
                        "automatic_learning": False,
                        "may_change_beliefs": False,
                        "may_change_routing": False,
                        "semantic_success_inferred": False,
                    },
                }
                outcome = ExpertOutcome.model_validate(payload)
                append_jsonl_durable(path, outcome.model_dump(mode="json"), fsync=True)
                return OutcomeApplyResult(outcome=outcome, appended=True)
        except FileLockTimeout as exc:
            raise OutcomeStorageError("Timed out acquiring the expert outcome write lock") from exc
        except OSError as exc:
            raise OutcomeStorageError("Could not append the expert outcome") from exc


class OutcomeSummaryContract(TypedDict):
    read_only: bool
    cost_usd: float
    model_calls: int
    semantic_quality_verdict: bool
    routing_change_allowed: bool


class OutcomeLinkage(TypedDict):
    consult_trace_linked: int
    belief_linked: int
    source_linked: int
    evidence_linked: int


class OutcomeSummary(TypedDict):
    schema_version: str
    kind: str
    contract: OutcomeSummaryContract
    expert_name: str
    total_outcomes: int
    active_outcomes: int
    superseded_outcomes: int
    result_counts: dict[OutcomeResult, int]
    observation_result_counts: dict[OutcomeResult, int]
    linkage: OutcomeLinkage
    recent_outcomes: list[dict[str, Any]]


def build_outcome_summary(
    expert_name: str,
    outcomes: list[ExpertOutcome],
    *,
    limit: int = 20,
) -> OutcomeSummary:
    """Build a structural read-only summary without a quality verdict."""
    bounded_limit = max(1, min(int(limit), 100))
    normalized_name = _clean_text(expert_name, field_name="expert name", max_length=120)
    superseded_ids = {item.supersedes_outcome_id for item in outcomes if item.supersedes_outcome_id is not None}
    active = [item for item in outcomes if item.outcome_id not in superseded_ids]
    counts: dict[OutcomeResult, int] = {result: sum(item.result == result for item in active) for result in _RESULTS}
    observation_counts: dict[OutcomeResult, int] = {
        result: sum(item.result == result for item in outcomes) for result in _RESULTS
    }
    contract: OutcomeSummaryContract = {
        "read_only": True,
        "cost_usd": 0.0,
        "model_calls": 0,
        "semantic_quality_verdict": False,
        "routing_change_allowed": False,
    }
    linkage: OutcomeLinkage = {
        "consult_trace_linked": sum(item.consult_trace_id is not None for item in outcomes),
        "belief_linked": sum(bool(item.belief_ids) for item in outcomes),
        "source_linked": sum(bool(item.source_refs) for item in outcomes),
        "evidence_linked": sum(bool(item.evidence_refs) for item in outcomes),
    }
    return {
        "schema_version": EXPERT_OUTCOME_SUMMARY_SCHEMA_VERSION,
        "kind": EXPERT_OUTCOME_SUMMARY_KIND,
        "contract": contract,
        "expert_name": normalized_name,
        "total_outcomes": len(outcomes),
        "active_outcomes": len(active),
        "superseded_outcomes": len(superseded_ids),
        "result_counts": counts,
        "observation_result_counts": observation_counts,
        "linkage": linkage,
        "recent_outcomes": [item.model_dump(mode="json") for item in outcomes[-bounded_limit:]],
    }


__all__ = [
    "EXPERT_OUTCOME_KIND",
    "EXPERT_OUTCOME_SCHEMA_VERSION",
    "EXPERT_OUTCOME_SUMMARY_KIND",
    "EXPERT_OUTCOME_SUMMARY_SCHEMA_VERSION",
    "OUTCOME_RELATIVE_PATH",
    "ExpertOutcome",
    "ExpertOutcomeDraft",
    "ExpertOutcomeStore",
    "OutcomeApplyResult",
    "OutcomeConflictError",
    "OutcomeLinkage",
    "OutcomeResult",
    "OutcomeStorageError",
    "OutcomeSummary",
    "OutcomeSummaryContract",
    "build_outcome_summary",
    "normalize_timestamp",
    "outcome_content_hash",
]
