"""Unreviewed drafts and operator-attested purpose contracts for experts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

from filelock import FileLock
from filelock import Timeout as FileLockTimeout
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from deepr.experts.paths import canonical_expert_dir
from deepr.utils.atomic_io import append_jsonl_durable
from deepr.utils.security import SecurityError

EXPERT_BLUEPRINT_SCHEMA_VERSION = "deepr-expert-blueprint-v1"
EXPERT_BLUEPRINT_KIND = "deepr.expert.blueprint"
EXPERT_BLUEPRINT_DRAFT_SCHEMA_VERSION = "deepr-expert-blueprint-draft-v1"
EXPERT_BLUEPRINT_DRAFT_KIND = "deepr.expert.blueprint_draft"
EXPERT_BLUEPRINT_PREFLIGHT_SCHEMA_VERSION = "deepr-expert-blueprint-preflight-v1"
EXPERT_BLUEPRINT_PREFLIGHT_KIND = "deepr.expert.blueprint_preflight"
BLUEPRINT_RELATIVE_PATH = Path("blueprints") / "blueprints.jsonl"

_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_CONTENT_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_LOCK_TIMEOUT_SECONDS = 10.0


class BlueprintStorageError(RuntimeError):
    """Raised when canonical blueprint history cannot be trusted or written."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _clean_text(value: str, *, field_name: str, max_length: int) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    if len(cleaned) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return cleaned


def _clean_text_list(values: list[str], *, field_name: str, max_items: int = 50) -> list[str]:
    if len(values) > max_items:
        raise ValueError(f"{field_name} must contain at most {max_items} items")
    cleaned = [_clean_text(value, field_name=field_name, max_length=2000) for value in values]
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"{field_name} must not contain duplicates")
    return cleaned


def _clean_identifier(value: str, *, field_name: str) -> str:
    cleaned = value.strip().lower()
    if not _IDENTIFIER_PATTERN.fullmatch(cleaned):
        raise ValueError(f"{field_name} must use lowercase letters, numbers, dots, underscores, or hyphens")
    return cleaned


def _validation_field_name(info: ValidationInfo) -> str:
    if info.field_name is None:
        raise ValueError("validator field name is unavailable")
    return info.field_name.replace("_", " ")


def _validate_timestamp(value: str, *, field_name: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.isoformat()


class BlueprintDecisionUseCase(_StrictModel):
    """A real decision the expert is expected to support."""

    id: str
    question: str
    success_criteria: list[str] = Field(min_length=1, max_length=20)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _clean_identifier(value, field_name="decision use-case id")

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        return _clean_text(value, field_name="decision use-case question", max_length=4000)

    @field_validator("success_criteria")
    @classmethod
    def validate_success_criteria(cls, values: list[str]) -> list[str]:
        return _clean_text_list(values, field_name="decision use-case success criteria", max_items=20)


class BlueprintAcceptanceCase(_StrictModel):
    """A held-out question and proposed traits of an acceptable result."""

    id: str
    question: str
    success_criteria: list[str] = Field(min_length=1, max_length=20)
    failure_conditions: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _clean_identifier(value, field_name="acceptance-case id")

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        return _clean_text(value, field_name="acceptance-case question", max_length=4000)

    @field_validator("success_criteria", "failure_conditions")
    @classmethod
    def validate_criteria(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _clean_text_list(values, field_name=_validation_field_name(info), max_items=20)


class BlueprintSourcePolicy(_StrictModel):
    """Proposed source constraints without a semantic trust verdict."""

    primary_sources_required: bool
    preferred_source_types: list[str] = Field(default_factory=list, max_length=30)
    excluded_sources: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("preferred_source_types", "excluded_sources")
    @classmethod
    def validate_source_lists(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _clean_text_list(values, field_name=_validation_field_name(info), max_items=50)


class _ExpertBlueprintContent(_StrictModel):
    """Shared semantic content without an artifact-state claim."""

    expert_name: str
    mission: str
    non_goals: list[str] = Field(default_factory=list, max_length=50)
    decision_use_cases: list[BlueprintDecisionUseCase] = Field(min_length=1, max_length=50)
    source_policy: BlueprintSourcePolicy
    volatility: Literal["slow", "medium", "fast"]
    update_cadence_days: int = Field(ge=1, le=3650)
    initial_questions: list[str] = Field(min_length=1, max_length=50)
    acceptance_cases: list[BlueprintAcceptanceCase] = Field(min_length=1, max_length=100)

    @field_validator("expert_name")
    @classmethod
    def validate_expert_name(cls, value: str) -> str:
        return _clean_text(value, field_name="expert name", max_length=120)

    @field_validator("mission")
    @classmethod
    def validate_mission(cls, value: str) -> str:
        return _clean_text(value, field_name="mission", max_length=4000)

    @field_validator("non_goals", "initial_questions")
    @classmethod
    def validate_text_lists(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _clean_text_list(values, field_name=_validation_field_name(info), max_items=50)

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> Self:
        decision_ids = [item.id for item in self.decision_use_cases]
        if len(set(decision_ids)) != len(decision_ids):
            raise ValueError("decision use-case ids must be unique")
        acceptance_ids = [item.id for item in self.acceptance_cases]
        if len(set(acceptance_ids)) != len(acceptance_ids):
            raise ValueError("acceptance-case ids must be unique")
        return self


class ExpertBlueprintDraft(_ExpertBlueprintContent):
    """Strict, explicitly unreviewed external blueprint input."""

    schema_version: Literal["deepr-expert-blueprint-draft-v1"]
    kind: Literal["deepr.expert.blueprint_draft"]


class BlueprintAttestation(_StrictModel):
    status: Literal["operator_attested"]
    attested_by: str
    attested_at: str
    claim: Literal["scope_and_acceptance_review_completed"]
    identity_verified: Literal[False]

    @field_validator("attested_by")
    @classmethod
    def validate_attester(cls, value: str) -> str:
        return _clean_text(value, field_name="attested by", max_length=200)

    @field_validator("attested_at")
    @classmethod
    def validate_attested_at(cls, value: str) -> str:
        return _validate_timestamp(value, field_name="attested at")


class BlueprintAuthorityContract(_StrictModel):
    operator_attested_for_scope: Literal[True]
    human_authorship_claimed: Literal[False]
    reviewer_identity_verified: Literal[False]
    authoritative_for_scope: Literal[True]
    may_authorize_spend: Literal[False]
    may_authorize_knowledge_writes: Literal[False]
    may_authorize_external_actions: Literal[False]
    semantic_maturity_verdict: Literal[False]


class ExpertBlueprint(_ExpertBlueprintContent):
    """One immutable blueprint revision accepted through operator attestation."""

    schema_version: Literal["deepr-expert-blueprint-v1"]
    kind: Literal["deepr.expert.blueprint"]
    revision: int = Field(ge=1)
    content_hash: str
    created_at: str
    updated_at: str
    attestation: BlueprintAttestation
    contract: BlueprintAuthorityContract

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        if not _CONTENT_HASH_PATTERN.fullmatch(value):
            raise ValueError("content hash must be a lowercase SHA-256 digest")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_record_timestamp(cls, value: str, info: ValidationInfo) -> str:
        return _validate_timestamp(value, field_name=_validation_field_name(info))


@dataclass(frozen=True)
class BlueprintApplyResult:
    blueprint: ExpertBlueprint
    appended: bool


def blueprint_template(expert_name: str) -> dict[str, object]:
    """Return an intentionally incomplete, explicitly unreviewed draft."""
    return {
        "schema_version": EXPERT_BLUEPRINT_DRAFT_SCHEMA_VERSION,
        "kind": EXPERT_BLUEPRINT_DRAFT_KIND,
        "expert_name": " ".join(expert_name.split()),
        "mission": "",
        "non_goals": [],
        "decision_use_cases": [
            {
                "id": "decision-1",
                "question": "",
                "success_criteria": [""],
            }
        ],
        "source_policy": {
            "primary_sources_required": True,
            "preferred_source_types": [],
            "excluded_sources": [],
        },
        "volatility": "medium",
        "update_cadence_days": 30,
        "initial_questions": [""],
        "acceptance_cases": [
            {
                "id": "acceptance-1",
                "question": "",
                "success_criteria": [""],
                "failure_conditions": [],
            }
        ],
    }


def load_blueprint_draft(path: Path) -> ExpertBlueprintDraft:
    """Parse a strict external blueprint draft from JSON."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return ExpertBlueprintDraft.model_validate(raw)


def _draft_from_record(record: ExpertBlueprint) -> ExpertBlueprintDraft:
    fields = ExpertBlueprintDraft.model_fields
    payload = {name: getattr(record, name) for name in fields}
    payload["schema_version"] = EXPERT_BLUEPRINT_DRAFT_SCHEMA_VERSION
    payload["kind"] = EXPERT_BLUEPRINT_DRAFT_KIND
    return ExpertBlueprintDraft.model_validate(payload)


def blueprint_content_hash(draft: ExpertBlueprintDraft) -> str:
    """Hash the normalized unreviewed draft, excluding later attestation metadata."""
    canonical = json.dumps(
        draft.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_blueprint_preflight(draft: ExpertBlueprintDraft) -> dict[str, Any]:
    """Build a zero-call, non-authoritative preparation artifact for review."""
    acceptance_with_failures = sum(bool(case.failure_conditions) for case in draft.acceptance_cases)
    return {
        "schema_version": EXPERT_BLUEPRINT_PREFLIGHT_SCHEMA_VERSION,
        "kind": EXPERT_BLUEPRINT_PREFLIGHT_KIND,
        "status": "structurally_valid_unreviewed",
        "contract": {
            "structurally_valid": True,
            "semantic_quality_assessed": False,
            "human_review_claimed": False,
            "operator_attestation_present": False,
            "authoritative_for_scope": False,
            "writes_canonical_state": False,
            "model_calls": 0,
            "provider_calls": 0,
            "network_access": False,
            "cost_usd": 0.0,
        },
        "draft_content_hash": blueprint_content_hash(draft),
        "draft": draft.model_dump(mode="json"),
        "structural_summary": {
            "non_goal_count": len(draft.non_goals),
            "decision_use_case_count": len(draft.decision_use_cases),
            "acceptance_case_count": len(draft.acceptance_cases),
            "acceptance_cases_with_failure_conditions": acceptance_with_failures,
            "initial_question_count": len(draft.initial_questions),
            "preferred_source_type_count": len(draft.source_policy.preferred_source_types),
            "excluded_source_count": len(draft.source_policy.excluded_sources),
            "primary_sources_required": draft.source_policy.primary_sources_required,
            "volatility": draft.volatility,
            "update_cadence_days": draft.update_cadence_days,
        },
        "review_questions": [
            "Does the mission match the decisions this expert should improve?",
            "Are the non-goals and authority limits appropriate?",
            "Can each success criterion be judged on a real decision?",
            "Do the acceptance cases cover likely failure and abstention behavior?",
            "Does the source policy fit the domain's evidence and volatility?",
            "Which claims or assumptions in this draft need correction before attestation?",
        ],
        "next_step": {
            "review_required": True,
            "attestation_flag": "--attested-by",
            "claim_recorded_on_apply": "scope_and_acceptance_review_completed",
            "reviewer_identity_will_be_verified": False,
        },
    }


class ExpertBlueprintStore:
    """Append-only storage for operator-attested expert blueprint revisions."""

    def __init__(self, base_path: Path | str | None = None) -> None:
        self.base_path = Path(base_path) if base_path is not None else None

    def path_for(self, expert_name: str) -> Path:
        try:
            return canonical_expert_dir(expert_name, self.base_path) / BLUEPRINT_RELATIVE_PATH
        except SecurityError as exc:
            raise BlueprintStorageError("Expert blueprint path failed safety validation") from exc

    def _load_unlocked(self, expert_name: str) -> list[ExpertBlueprint]:
        normalized_name = _clean_text(expert_name, field_name="expert name", max_length=120)
        path = self.path_for(normalized_name)
        if not path.exists():
            return []
        records: list[ExpertBlueprint] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise BlueprintStorageError("Could not read expert blueprint history") from exc
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                record = ExpertBlueprint.model_validate(json.loads(line))
            except (json.JSONDecodeError, ValueError) as exc:
                raise BlueprintStorageError(f"Invalid blueprint history record at line {line_number}") from exc
            expected_revision = len(records) + 1
            if record.revision != expected_revision:
                raise BlueprintStorageError(
                    f"Blueprint revision sequence is invalid at line {line_number}: expected {expected_revision}"
                )
            if record.expert_name != normalized_name:
                raise BlueprintStorageError(f"Blueprint expert name mismatch at line {line_number}")
            if blueprint_content_hash(_draft_from_record(record)) != record.content_hash:
                raise BlueprintStorageError(f"Blueprint content hash mismatch at line {line_number}")
            records.append(record)
        return records

    def load_all(self, expert_name: str) -> list[ExpertBlueprint]:
        """Load and verify all revisions without creating filesystem state."""
        return self._load_unlocked(expert_name)

    def load_latest(self, expert_name: str) -> ExpertBlueprint | None:
        records = self.load_all(expert_name)
        return records[-1] if records else None

    def apply(
        self,
        draft: ExpertBlueprintDraft,
        *,
        attested_by: str,
        now: datetime | None = None,
    ) -> BlueprintApplyResult:
        """Append an operator-attested revision, or return an idempotent match."""
        attester = _clean_text(attested_by, field_name="attested by", max_length=200)
        timestamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
        content_hash = blueprint_content_hash(draft)
        path = self.path_for(draft.expert_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(path.with_suffix(path.suffix + ".lock")))
        try:
            with lock.acquire(timeout=_LOCK_TIMEOUT_SECONDS):
                records = self._load_unlocked(draft.expert_name)
                latest = records[-1] if records else None
                if latest is not None and latest.content_hash == content_hash:
                    return BlueprintApplyResult(blueprint=latest, appended=False)
                payload = {
                    **draft.model_dump(mode="json"),
                    "schema_version": EXPERT_BLUEPRINT_SCHEMA_VERSION,
                    "kind": EXPERT_BLUEPRINT_KIND,
                    "revision": len(records) + 1,
                    "content_hash": content_hash,
                    "created_at": latest.created_at if latest is not None else timestamp,
                    "updated_at": timestamp,
                    "attestation": {
                        "status": "operator_attested",
                        "attested_by": attester,
                        "attested_at": timestamp,
                        "claim": "scope_and_acceptance_review_completed",
                        "identity_verified": False,
                    },
                    "contract": {
                        "operator_attested_for_scope": True,
                        "human_authorship_claimed": False,
                        "reviewer_identity_verified": False,
                        "authoritative_for_scope": True,
                        "may_authorize_spend": False,
                        "may_authorize_knowledge_writes": False,
                        "may_authorize_external_actions": False,
                        "semantic_maturity_verdict": False,
                    },
                }
                record = ExpertBlueprint.model_validate(payload)
                append_jsonl_durable(path, record.model_dump(mode="json"), fsync=True)
                return BlueprintApplyResult(blueprint=record, appended=True)
        except FileLockTimeout as exc:
            raise BlueprintStorageError("Timed out acquiring the expert blueprint write lock") from exc
        except OSError as exc:
            raise BlueprintStorageError("Could not append the expert blueprint revision") from exc


__all__ = [
    "BLUEPRINT_RELATIVE_PATH",
    "EXPERT_BLUEPRINT_DRAFT_KIND",
    "EXPERT_BLUEPRINT_DRAFT_SCHEMA_VERSION",
    "EXPERT_BLUEPRINT_KIND",
    "EXPERT_BLUEPRINT_PREFLIGHT_KIND",
    "EXPERT_BLUEPRINT_PREFLIGHT_SCHEMA_VERSION",
    "EXPERT_BLUEPRINT_SCHEMA_VERSION",
    "BlueprintAcceptanceCase",
    "BlueprintApplyResult",
    "BlueprintAttestation",
    "BlueprintDecisionUseCase",
    "BlueprintSourcePolicy",
    "BlueprintStorageError",
    "ExpertBlueprint",
    "ExpertBlueprintDraft",
    "ExpertBlueprintStore",
    "blueprint_content_hash",
    "blueprint_template",
    "build_blueprint_preflight",
    "load_blueprint_draft",
]
