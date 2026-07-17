"""Versioned contracts and deterministic bounds for expert investigations."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

INPUT_BUNDLE_SCHEMA_VERSION = "deepr-investigation-input-bundle-v1"
INPUT_BUNDLE_KIND = "deepr.expert.investigation_input_bundle"
PLAN_SCHEMA_VERSION = "deepr-investigation-plan-v1"
PLAN_KIND = "deepr.expert.investigation_plan"
RUN_SCHEMA_VERSION = "deepr-investigation-run-v1"
RUN_KIND = "deepr.expert.investigation_run"
CHARTER_SCHEMA_VERSION = "deepr-investigation-charter-v1"
CHARTER_KIND = "deepr.expert.investigation_charter"
POSITION_SCHEMA_VERSION = "deepr-investigation-position-v1"
POSITION_KIND = "deepr.expert.investigation_position"
DISCUSSION_SCHEMA_VERSION = "deepr-investigation-discussion-v1"
DISCUSSION_KIND = "deepr.expert.investigation_discussion"
CHECK_SCHEMA_VERSION = "deepr-investigation-check-v1"
CHECK_KIND = "deepr.expert.investigation_check"
RESULT_SCHEMA_VERSION = "deepr-investigation-result-v1"
RESULT_KIND = "deepr.expert.investigation_result"
LEARNING_MANIFEST_SCHEMA_VERSION = "deepr-investigation-learning-manifest-v1"
LEARNING_MANIFEST_KIND = "deepr.expert.investigation_learning_manifest"
EVENT_SCHEMA_VERSION = "deepr-investigation-event-v1"
EVENT_KIND = "deepr.expert.investigation_event"

DEFAULT_MAX_ELAPSED_SECONDS = 3600.0
MAX_MAX_ELAPSED_SECONDS = 21_600.0
DEFAULT_MAX_OUTPUT_TOKENS_PER_CALL = 4096
DEFAULT_MAX_PROMPT_BYTES_PER_CALL = 262_144
DEFAULT_MAX_DISK_BYTES = 268_435_456
DEFAULT_SEARCH_QUERIES_PER_EXPERT = 4
DEFAULT_PAGE_FETCHES_PER_EXPERT = 8
DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS = 32_768
MIN_LOCAL_CONTEXT_WINDOW_TOKENS = 8_192
MAX_LOCAL_CONTEXT_WINDOW_TOKENS = 1_048_576
MAX_EXPERTS = 5
MIN_EXPERTS = 1

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_REF_RE = re.compile(r"[^a-z0-9._-]+")


class InvestigationContractError(ValueError):
    """Raised when an investigation artifact violates its deterministic contract."""


class ProtocolMode(StrEnum):
    """Bounded collaboration protocol selected by the caller."""

    INDEPENDENT = "independent"
    DISCUSS = "discuss"
    DEEP = "deep"


class LearningMode(StrEnum):
    """Post-answer learning policy."""

    OFF = "off"
    STAGE = "stage"


class RunState(StrEnum):
    """Durable investigation lifecycle state."""

    PLANNED = "planned"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    COMPLETED_PARTIAL = "completed_partial"
    CANCELLED = "cancelled"
    BUDGET_EXHAUSTED = "budget_exhausted"
    VERIFIER_FAILED = "verifier_failed"
    FAILED = "failed"


class Phase(StrEnum):
    """Ordered execution phases for resumable local runs."""

    PREFLIGHT = "preflight"
    CHARTERS = "charters"
    RESEARCH = "research"
    POSITIONS = "positions"
    DISCUSSION = "discussion"
    REVISIONS = "revisions"
    CHECK = "check"
    SYNTHESIS = "synthesis"
    LEARNING = "learning"
    COMPLETE = "complete"


TERMINAL_STATES = frozenset(
    {
        RunState.COMPLETED,
        RunState.COMPLETED_PARTIAL,
        RunState.CANCELLED,
        RunState.BUDGET_EXHAUSTED,
        RunState.VERIFIER_FAILED,
        RunState.FAILED,
    }
)


def utc_now() -> str:
    """Return one UTC timestamp in the repository's canonical text form."""
    return datetime.now(UTC).isoformat()


def canonical_json(value: Any) -> str:
    """Serialize stable JSON used for hashes and model packets."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def validate_sha256(value: Any, *, field_name: str) -> str:
    normalized = str(value or "")
    if not _SHA256_RE.fullmatch(normalized):
        raise InvestigationContractError(f"{field_name} must be lowercase sha256 hex")
    return normalized


def safe_ref(value: str, *, fallback: str = "item") -> str:
    """Return a bounded path-safe identifier without deciding semantic identity."""
    normalized = _SAFE_REF_RE.sub("-", value.lower()).strip("-._")
    return (normalized or fallback)[:80]


def new_run_id() -> str:
    return f"inv_{uuid.uuid4().hex}"


def _exact_int(value: Any, *, field_name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise InvestigationContractError(f"{field_name} must be an integer from {minimum} to {maximum}")
    return value


def _finite_float(value: Any, *, field_name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvestigationContractError(f"{field_name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or not minimum <= normalized <= maximum:
        raise InvestigationContractError(f"{field_name} must be finite from {minimum} to {maximum}")
    return normalized


def maximum_generation_calls(
    expert_count: int,
    protocol: ProtocolMode | str,
    learning: LearningMode | str,
) -> int:
    """Return the exact worst-case call formula from the accepted design."""
    count = _exact_int(expert_count, field_name="expert_count", minimum=MIN_EXPERTS, maximum=MAX_EXPERTS)
    protocol_mode = ProtocolMode(protocol)
    learning_mode = LearningMode(learning)
    research_calls = 2
    discussion_calls = 1 if protocol_mode in {ProtocolMode.DISCUSS, ProtocolMode.DEEP} else 0
    revision_calls = 1 if protocol_mode is ProtocolMode.DEEP else 0
    learning_calls = 2 if learning_mode is LearningMode.STAGE else 0
    return count * (research_calls + discussion_calls + revision_calls + learning_calls) + 2


@dataclass(frozen=True)
class InvestigationBounds:
    """One parent capacity envelope shared across every phase and expert."""

    max_generation_calls: int
    max_search_queries: int
    max_page_fetches: int
    max_input_tokens: int
    max_output_tokens: int
    max_prompt_bytes_per_call: int = DEFAULT_MAX_PROMPT_BYTES_PER_CALL
    max_output_tokens_per_call: int = DEFAULT_MAX_OUTPUT_TOKENS_PER_CALL
    max_elapsed_seconds: float = DEFAULT_MAX_ELAPSED_SECONDS
    max_disk_bytes: int = DEFAULT_MAX_DISK_BYTES
    max_concurrency: int = 1
    budget_usd: float = 0.0

    @classmethod
    def for_plan(
        cls,
        *,
        expert_count: int,
        protocol: ProtocolMode,
        learning: LearningMode,
        max_elapsed_seconds: float = DEFAULT_MAX_ELAPSED_SECONDS,
    ) -> InvestigationBounds:
        calls = maximum_generation_calls(expert_count, protocol, learning)
        return cls(
            max_generation_calls=calls,
            max_search_queries=expert_count * DEFAULT_SEARCH_QUERIES_PER_EXPERT,
            max_page_fetches=expert_count * DEFAULT_PAGE_FETCHES_PER_EXPERT,
            max_input_tokens=calls * math.ceil(DEFAULT_MAX_PROMPT_BYTES_PER_CALL / 4),
            max_output_tokens=calls * DEFAULT_MAX_OUTPUT_TOKENS_PER_CALL,
            max_elapsed_seconds=max_elapsed_seconds,
        ).validated()

    def validated(self) -> InvestigationBounds:
        _exact_int(self.max_generation_calls, field_name="max_generation_calls", minimum=1, maximum=256)
        _exact_int(self.max_search_queries, field_name="max_search_queries", minimum=0, maximum=256)
        _exact_int(self.max_page_fetches, field_name="max_page_fetches", minimum=0, maximum=256)
        _exact_int(self.max_input_tokens, field_name="max_input_tokens", minimum=1, maximum=1_000_000_000)
        _exact_int(self.max_output_tokens, field_name="max_output_tokens", minimum=1, maximum=10_000_000)
        _exact_int(
            self.max_prompt_bytes_per_call,
            field_name="max_prompt_bytes_per_call",
            minimum=1024,
            maximum=4_194_304,
        )
        _exact_int(
            self.max_output_tokens_per_call,
            field_name="max_output_tokens_per_call",
            minimum=128,
            maximum=65_536,
        )
        _finite_float(
            self.max_elapsed_seconds,
            field_name="max_elapsed_seconds",
            minimum=1.0,
            maximum=MAX_MAX_ELAPSED_SECONDS,
        )
        _exact_int(self.max_disk_bytes, field_name="max_disk_bytes", minimum=1024, maximum=4_294_967_296)
        _exact_int(self.max_concurrency, field_name="max_concurrency", minimum=1, maximum=MAX_EXPERTS)
        _finite_float(self.budget_usd, field_name="budget_usd", minimum=0.0, maximum=10_000.0)
        return self

    def to_dict(self) -> dict[str, int | float]:
        return {
            "max_generation_calls": self.max_generation_calls,
            "max_search_queries": self.max_search_queries,
            "max_page_fetches": self.max_page_fetches,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_prompt_bytes_per_call": self.max_prompt_bytes_per_call,
            "max_output_tokens_per_call": self.max_output_tokens_per_call,
            "max_elapsed_seconds": self.max_elapsed_seconds,
            "max_disk_bytes": self.max_disk_bytes,
            "max_concurrency": self.max_concurrency,
            "budget_usd": self.budget_usd,
        }

    @classmethod
    def from_dict(cls, value: Any) -> InvestigationBounds:
        if not isinstance(value, dict):
            raise InvestigationContractError("bounds must be an object")
        try:
            return cls(**value).validated()
        except TypeError as exc:
            raise InvestigationContractError(f"invalid bounds fields: {exc}") from exc


def validate_input_bundle(bundle: Any) -> dict[str, Any]:
    if not isinstance(bundle, dict):
        raise InvestigationContractError("input_bundle must be an object")
    if bundle.get("schema_version") != INPUT_BUNDLE_SCHEMA_VERSION or bundle.get("kind") != INPUT_BUNDLE_KIND:
        raise InvestigationContractError("unsupported investigation input bundle")
    root = bundle.get("root")
    if not isinstance(root, str) or not root:
        raise InvestigationContractError("input bundle root must be non-empty")
    items = bundle.get("items")
    if not isinstance(items, list):
        raise InvestigationContractError("input bundle items must be an array")
    for item in items:
        if not isinstance(item, dict):
            raise InvestigationContractError("every input item must be an object")
        if item.get("input_type") not in {"inline_text", "url", "file"}:
            raise InvestigationContractError("unsupported input item type")
        validate_sha256(item.get("content_sha256"), field_name="input item content_sha256")
    validate_sha256(bundle.get("bundle_sha256"), field_name="bundle_sha256")
    material = {key: value for key, value in bundle.items() if key != "bundle_sha256"}
    if sha256_json(material) != bundle["bundle_sha256"]:
        raise InvestigationContractError("input bundle hash does not match its content")
    return bundle


def _validate_plan_experts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not MIN_EXPERTS <= len(value) <= MAX_EXPERTS:
        raise InvestigationContractError(f"experts must contain {MIN_EXPERTS} to {MAX_EXPERTS} entries")
    names: set[str] = set()
    experts: list[dict[str, Any]] = []
    for raw_expert in value:
        if not isinstance(raw_expert, dict):
            raise InvestigationContractError("every expert entry requires a name")
        expert = raw_expert
        name = expert.get("name")
        if not isinstance(name, str) or not name.strip():
            raise InvestigationContractError("every expert entry requires a name")
        key = name.casefold()
        if key in names:
            raise InvestigationContractError("expert names must be unique")
        names.add(key)
        snapshot_sha256 = validate_sha256(expert.get("snapshot_sha256"), field_name="snapshot_sha256")
        snapshot = expert.get("snapshot")
        if not isinstance(snapshot, dict):
            raise InvestigationContractError("every expert entry requires a frozen snapshot")
        if sha256_json(snapshot) != snapshot_sha256:
            raise InvestigationContractError("expert snapshot hash does not match its content")
        experts.append(expert)
    return experts


def _validate_plan_modes(plan: dict[str, Any]) -> tuple[ProtocolMode, LearningMode]:
    protocol_value = plan.get("protocol")
    learning_value = plan.get("learning")
    if not isinstance(protocol_value, str):
        raise InvestigationContractError("protocol must be a string")
    if not isinstance(learning_value, str):
        raise InvestigationContractError("learning must be a string")
    try:
        return ProtocolMode(protocol_value), LearningMode(learning_value)
    except ValueError as exc:
        raise InvestigationContractError(str(exc)) from exc


def _validate_local_capacity(value: Any) -> None:
    if not isinstance(value, dict) or value.get("class") != "local" or value.get("fallback") != "none":
        raise InvestigationContractError("v1 investigation plans require pinned local capacity and no fallback")
    capacity = value
    model = capacity.get("model")
    if not isinstance(model, str) or not model.strip():
        raise InvestigationContractError("local capacity requires an exact model")
    review_model = capacity.get("review_model", model)
    if not isinstance(review_model, str) or not review_model.strip():
        raise InvestigationContractError("local capacity requires an exact review_model")
    _exact_int(
        capacity.get("context_window_tokens", DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS),
        field_name="context_window_tokens",
        minimum=MIN_LOCAL_CONTEXT_WINDOW_TOKENS,
        maximum=MAX_LOCAL_CONTEXT_WINDOW_TOKENS,
    )
    _exact_int(
        capacity.get(
            "review_context_window_tokens", capacity.get("context_window_tokens", DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS)
        ),
        field_name="review_context_window_tokens",
        minimum=MIN_LOCAL_CONTEXT_WINDOW_TOKENS,
        maximum=MAX_LOCAL_CONTEXT_WINDOW_TOKENS,
    )


def _validate_retrieval_bounds(value: Any, *, expert_count: int, bounds: InvestigationBounds) -> None:
    if not isinstance(value, dict):
        raise InvestigationContractError("retrieval must be an object")
    retrieval = value
    queries_per_expert = _exact_int(
        retrieval.get("max_queries_per_expert"),
        field_name="max_queries_per_expert",
        minimum=0,
        maximum=256,
    )
    pages_per_expert = _exact_int(
        retrieval.get("max_pages_per_expert"),
        field_name="max_pages_per_expert",
        minimum=0,
        maximum=256,
    )
    if queries_per_expert * expert_count != bounds.max_search_queries:
        raise InvestigationContractError("retrieval query bounds do not match the parent envelope")
    if pages_per_expert * expert_count != bounds.max_page_fetches:
        raise InvestigationContractError("retrieval page bounds do not match the parent envelope")


def _validate_learning_contract(value: Any, *, learning: LearningMode) -> None:
    if not isinstance(value, dict):
        raise InvestigationContractError("learning_contract must be an object")
    expected_relevance = learning is LearningMode.STAGE
    expected_judgment = "independent_verifier_model" if expected_relevance else "not_applicable"
    expected: dict[str, Any] = {
        "mode": learning.value,
        "source_pack_evidence_only": True,
        "dialogue_is_evidence": False,
        "domain_relevance_required": expected_relevance,
        "domain_relevance_judgment": expected_judgment,
        "writes_expert_state": False,
        "writes_beliefs": False,
        "writes_graph": False,
        "human_reviewed": False,
    }
    for field, required in expected.items():
        if value.get(field) != required:
            raise InvestigationContractError(f"learning_contract.{field} must be {required!r}")


def _validate_plan_hash(plan: dict[str, Any]) -> None:
    validate_sha256(plan.get("plan_sha256"), field_name="plan_sha256")
    material = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if sha256_json(material) != plan["plan_sha256"]:
        raise InvestigationContractError("plan hash does not match its content")


def validate_plan(plan: Any) -> dict[str, Any]:
    """Validate the public plan shape and its self-hash without doing I/O."""
    if not isinstance(plan, dict):
        raise InvestigationContractError("plan must be an object")
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION or plan.get("kind") != PLAN_KIND:
        raise InvestigationContractError("unsupported investigation plan")
    question = plan.get("question")
    if not isinstance(question, str) or not question.strip():
        raise InvestigationContractError("question must be non-empty")
    experts = _validate_plan_experts(plan.get("experts"))
    protocol, learning = _validate_plan_modes(plan)
    _validate_local_capacity(plan.get("capacity"))
    bounds = InvestigationBounds.from_dict(plan.get("bounds"))
    expected_calls = maximum_generation_calls(len(experts), protocol, learning)
    if bounds.max_generation_calls != expected_calls:
        raise InvestigationContractError("max_generation_calls does not match the protocol formula")
    if bounds.budget_usd != 0.0:
        raise InvestigationContractError("local v1 investigation budget_usd must be zero")
    _validate_retrieval_bounds(plan.get("retrieval"), expert_count=len(experts), bounds=bounds)
    _validate_learning_contract(plan.get("learning_contract"), learning=learning)
    validate_input_bundle(plan.get("input_bundle"))
    _validate_plan_hash(plan)
    return plan


def initial_usage() -> dict[str, int | float]:
    return {
        "generation_calls": 0,
        "search_queries": 0,
        "page_fetches": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "prompt_bytes": 0,
        "artifact_bytes": 0,
        "elapsed_seconds": 0.0,
        "cost_usd": 0.0,
    }


def remaining_capacity(bounds: InvestigationBounds, usage: dict[str, Any]) -> dict[str, int | float]:
    """Compute non-negative remaining counters from measured or conservative usage."""
    return {
        "generation_calls": max(0, bounds.max_generation_calls - int(usage.get("generation_calls", 0))),
        "search_queries": max(0, bounds.max_search_queries - int(usage.get("search_queries", 0))),
        "page_fetches": max(0, bounds.max_page_fetches - int(usage.get("page_fetches", 0))),
        "input_tokens": max(0, bounds.max_input_tokens - int(usage.get("input_tokens", 0))),
        "output_tokens": max(0, bounds.max_output_tokens - int(usage.get("output_tokens", 0))),
        "disk_bytes": max(0, bounds.max_disk_bytes - int(usage.get("artifact_bytes", 0))),
        "cost_usd": max(0.0, bounds.budget_usd - float(usage.get("cost_usd", 0.0))),
    }


def event_payload(
    *,
    run_id: str,
    sequence: int,
    event_type: str,
    phase: Phase | str,
    status: RunState | str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a content-free append-only lifecycle event."""
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "run_id": run_id,
        "sequence": sequence,
        "event_type": event_type,
        "phase": str(phase),
        "status": str(status),
        "detail": dict(detail or {}),
        "created_at": utc_now(),
    }


__all__ = [
    "CHARTER_KIND",
    "CHARTER_SCHEMA_VERSION",
    "CHECK_KIND",
    "CHECK_SCHEMA_VERSION",
    "DEFAULT_LOCAL_CONTEXT_WINDOW_TOKENS",
    "DEFAULT_MAX_ELAPSED_SECONDS",
    "DISCUSSION_KIND",
    "DISCUSSION_SCHEMA_VERSION",
    "EVENT_KIND",
    "EVENT_SCHEMA_VERSION",
    "INPUT_BUNDLE_KIND",
    "INPUT_BUNDLE_SCHEMA_VERSION",
    "LEARNING_MANIFEST_KIND",
    "LEARNING_MANIFEST_SCHEMA_VERSION",
    "MAX_EXPERTS",
    "MAX_LOCAL_CONTEXT_WINDOW_TOKENS",
    "MIN_EXPERTS",
    "MIN_LOCAL_CONTEXT_WINDOW_TOKENS",
    "PLAN_KIND",
    "PLAN_SCHEMA_VERSION",
    "POSITION_KIND",
    "POSITION_SCHEMA_VERSION",
    "RESULT_KIND",
    "RESULT_SCHEMA_VERSION",
    "RUN_KIND",
    "RUN_SCHEMA_VERSION",
    "TERMINAL_STATES",
    "InvestigationBounds",
    "InvestigationContractError",
    "LearningMode",
    "Phase",
    "ProtocolMode",
    "RunState",
    "canonical_json",
    "event_payload",
    "initial_usage",
    "maximum_generation_calls",
    "new_run_id",
    "remaining_capacity",
    "safe_ref",
    "sha256_bytes",
    "sha256_json",
    "utc_now",
    "validate_input_bundle",
    "validate_plan",
    "validate_sha256",
]
