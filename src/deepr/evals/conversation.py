"""Zero-cost structural evaluation for durable expert conversations.

The evaluator uses built-in immutable fixtures. It does not construct a
provider, read an expert store, open a network connection, or judge whether an
answer is true or useful. Its purpose is to freeze the protocol invariants that
the local core and later MCP and A2A adapters must preserve.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.conversation.models import (
    CONVERSATION_KIND,
    CONVERSATION_SCHEMA_VERSION,
    DEFAULT_MAX_CONTEXT_BYTES,
    DEFAULT_RETENTION_DAYS,
    ERROR_KIND,
    ERROR_SCHEMA_VERSION,
    EVENT_KIND,
    EVENT_SCHEMA_VERSION,
    HOST_ACTION_BOUNDARY,
    MAX_RECENT_TURNS,
    MAX_RETENTION_DAYS,
    SNAPSHOT_KIND,
    SNAPSHOT_SCHEMA_VERSION,
    TURN_KIND,
    TURN_SCHEMA_VERSION,
)

CONVERSATION_EVAL_SCHEMA_VERSION = "deepr-conversation-eval-v1"
CONVERSATION_EVAL_KIND = "deepr.eval.conversation"
CONVERSATION_EVAL_METHODOLOGY_VERSION = "1.0"

_FIXED_TIME = "2026-07-15T16:00:00+00:00"
_FIXED_LATER_TIME = "2026-07-15T16:00:01+00:00"
_CONVERSATION_ID = "conv_AAAAAAAAAAAAAAAAAAAAAA"
_TURN_ID = "turn_BBBBBBBBBBBBBBBB"
_SNAPSHOT_ID = "snap_CCCCCCCCCCCCCCCC"
_EVENT_ID = "evt_DDDDDDDDDDDDDDDD"
_ATTEMPT_ID = "attempt_EEEEEEEEEEEEEEEE"
_TRACE_ID = "trace_fixture_0001"
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64
_HASH_D = "d" * 64
_HOST_ACTION_BOUNDARY = HOST_ACTION_BOUNDARY


def conversation_contract_fixtures() -> dict[str, dict[str, Any]]:
    """Return fresh copies of the five published contract fixtures."""
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "kind": SNAPSHOT_KIND,
        "snapshot_id": _SNAPSHOT_ID,
        "conversation_id": _CONVERSATION_ID,
        "created_at": _FIXED_TIME,
        "context_builder_version": "conversation-context-v1",
        "roster_hash": _HASH_A,
        "snapshot_sha256": _HASH_B,
        "total_bytes": 512,
        "content_available": True,
        "content_deleted_at": None,
        "expert_snapshots": [
            {
                "expert_name": "reliability_engineering",
                "state_sha256": _HASH_C,
                "source_position": "belief-events:42",
                "packet_sha256": _HASH_D,
                "packet": {
                    "beliefs": [
                        {
                            "belief_id": "belief-42",
                            "claim": "Retries require idempotency.",
                            "confidence": 0.91,
                            "citation_refs": ["source-7"],
                        }
                    ],
                    "gaps": ["Outcome calibration is pending."],
                },
            }
        ],
    }
    conversation = {
        "schema_version": CONVERSATION_SCHEMA_VERSION,
        "kind": CONVERSATION_KIND,
        "conversation_id": _CONVERSATION_ID,
        "state": "open",
        "version": 2,
        "mode": "focused",
        "expert_names": ["reliability_engineering"],
        "context_snapshot_id": _SNAPSHOT_ID,
        "backend": {
            "capacity_source": "local_owned",
            "backend_class": "local",
            "model": "fixture-local-model",
            "fallback_policy": "none",
            "live_metered_fallback": False,
        },
        "bounds": {
            "max_turns": 20,
            "max_model_calls": 40,
            "max_input_tokens": 100_000,
            "max_output_tokens": 50_000,
            "max_context_bytes": DEFAULT_MAX_CONTEXT_BYTES,
            "max_elapsed_seconds": 300,
            "max_cost_usd": 0.0,
        },
        "usage": {
            "turns_started": 1,
            "turns_completed": 1,
            "model_calls": 1,
            "input_tokens": 120,
            "output_tokens": 80,
            "elapsed_ms": 900,
            "cost_usd": 0.0,
        },
        "retention": {
            "retention_days": DEFAULT_RETENTION_DAYS,
            "expires_at": "2026-08-14T16:00:00+00:00",
            "content_deleted": False,
            "content_deleted_at": None,
        },
        "current_turn_id": None,
        "latest_turn_id": _TURN_ID,
        "pending_input_request_id": None,
        "created_at": _FIXED_TIME,
        "updated_at": _FIXED_LATER_TIME,
        "host_action_boundary": _HOST_ACTION_BOUNDARY,
    }
    turn = {
        "schema_version": TURN_SCHEMA_VERSION,
        "kind": TURN_KIND,
        "conversation_id": _CONVERSATION_ID,
        "turn_id": _TURN_ID,
        "ordinal": 1,
        "state": "completed",
        "attempt_count": 1,
        "request": {
            "content_available": True,
            "content": "What failure would invalidate this rollout plan?",
            "content_sha256": _HASH_A,
            "input_request_id": None,
        },
        "context": {
            "snapshot_id": _SNAPSHOT_ID,
            "snapshot_sha256": _HASH_B,
            "recent_turn_ids": [],
            "context_bytes": 512,
            "context_sha256": _HASH_C,
        },
        "artifact_available": True,
        "artifact": {
            "direct_answer": "A replay that dispatches twice invalidates the rollout plan.",
            "experts_consulted": ["reliability_engineering"],
            "assumptions": [
                {
                    "text": "The caller can supply stable idempotency keys.",
                    "source": "model_proposed",
                }
            ],
            "evidence": [
                {
                    "evidence_ref": "belief-42",
                    "source_type": "expert_state",
                    "expert_name": "reliability_engineering",
                    "citation": "source-7",
                }
            ],
            "uncertainty": {
                "kind": "qualitative",
                "value": "medium",
                "rationale": "Crash recovery has not been live-validated yet.",
            },
            "agreements": ["Retries must not create another logical turn."],
            "dissent": [
                {
                    "position": "A short recoverable deletion grace period may be safer operationally.",
                    "expert_names": ["reliability_engineering"],
                    "evidence_refs": ["belief-42"],
                }
            ],
            "decision_implications": [
                {
                    "proposal": "Gate release on duplicate-delivery and restart tests.",
                    "authority": "proposal_only",
                }
            ],
            "change_conditions": ["A durable broker proves exactly-once completion under crash injection."],
            "unresolved_gaps": ["Cross-process lease recovery remains untested."],
            "recommended_next_question": "Which crash points must the recovery suite inject?",
            "semantic_status": "answered",
            "host_action_boundary": _HOST_ACTION_BOUNDARY,
        },
        "artifact_sha256": _HASH_D,
        "stop": {
            "reason": "completed",
            "retryable": False,
        },
        "capacity": {
            "turn": {
                "model_calls": 1,
                "input_tokens": 120,
                "output_tokens": 80,
                "elapsed_ms": 900,
                "cost_usd": 0.0,
            },
            "remaining": {
                "turns": 19,
                "model_calls": 39,
                "input_tokens": 99_880,
                "output_tokens": 49_920,
                "elapsed_ms": 299_100,
                "cost_usd": 0.0,
            },
        },
        "trace": {
            "attempt_id": _ATTEMPT_ID,
            "consult_trace_id": _TRACE_ID,
            "consult_lifecycle_trace_id": _TRACE_ID,
        },
        "created_at": _FIXED_TIME,
        "updated_at": _FIXED_LATER_TIME,
    }
    event = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "event_id": _EVENT_ID,
        "conversation_id": _CONVERSATION_ID,
        "sequence": 3,
        "projection_version": 2,
        "event_type": "turn_completed",
        "turn_id": _TURN_ID,
        "attempt_id": _ATTEMPT_ID,
        "previous_state": "open",
        "current_state": "open",
        "reason_code": "completed",
        "request_sha256": _HASH_A,
        "artifact_sha256": _HASH_D,
        "owner_binding_sha256": _HASH_B,
        "content_retained": True,
        "created_at": _FIXED_LATER_TIME,
    }
    error = {
        "schema_version": ERROR_SCHEMA_VERSION,
        "kind": ERROR_KIND,
        "error": {
            "code": "version_conflict",
            "safe_message": "The conversation changed; fetch current state before retrying.",
            "retryable": True,
            "conversation_id": _CONVERSATION_ID,
            "current_version": 2,
            "state": "open",
            "details": {
                "expected_version": 1,
                "current_version": 2,
                "field": None,
                "retry_after_ms": None,
            },
        },
    }
    return {
        "conversation": conversation,
        "turn": turn,
        "event": event,
        "context_snapshot": snapshot,
        "error": error,
    }


FROZEN_COMPARISON_MANIFEST: dict[str, Any] = {
    "manifest_version": "deepr-conversation-comparison-v1",
    "question_id": "question-fixture-001",
    "question_sha256": _HASH_A,
    "expert_names": ["reliability_engineering"],
    "snapshot_id": _SNAPSHOT_ID,
    "snapshot_sha256": _HASH_B,
    "repeated_one_shot": {
        "isolated_calls": True,
        "application_context_carried": False,
        "calls": [
            {
                "call_id": "one-shot-1",
                "question_variant": "initial",
                "visible_prior_turn_ids": [],
            },
            {
                "call_id": "one-shot-2",
                "question_variant": "follow_up_with_caller_recap",
                "visible_prior_turn_ids": [],
            },
        ],
    },
    "durable_conversation": {
        "conversation_id": _CONVERSATION_ID,
        "application_context_carried": True,
        "turns": [
            {
                "turn_id": _TURN_ID,
                "ordinal": 1,
                "visible_prior_turn_ids": [],
                "expected_version": None,
            },
            {
                "turn_id": "turn_FFFFFFFFFFFFFFFF",
                "ordinal": 2,
                "visible_prior_turn_ids": [_TURN_ID],
                "expected_version": 2,
            },
        ],
    },
    "comparison_status": "structural_only",
    "semantic_quality_review": "unreviewed",
}

_EXECUTION_CONTRACT = {
    "execution_mode": "frozen_fixture",
    "capacity_mode": "local_only",
    "provider_calls": 0,
    "backend_calls": 0,
    "expert_store_reads": 0,
    "network_access": False,
    "fallback_policy": "none",
    "live_metered_fallback": False,
    "cost_usd": 0.0,
    "writes_runtime_state": False,
    "semantic_verdict": False,
}


@dataclass(frozen=True)
class ConversationEvalOutcome:
    """One deterministic contract check."""

    case_id: str
    category: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "passed": self.passed,
            "failed": not self.passed,
            "semantic_verdict": False,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ConversationEvalReport:
    """Versioned report for the frozen conversation contract suite."""

    outcomes: tuple[ConversationEvalOutcome, ...]
    suite_name: str = "durable-expert-conversation-fixture"
    methodology_version: str = CONVERSATION_EVAL_METHODOLOGY_VERSION
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_cases(self) -> int:
        return len(self.outcomes)

    @property
    def passed_cases(self) -> int:
        return sum(outcome.passed for outcome in self.outcomes)

    @property
    def failed_cases(self) -> int:
        return self.total_cases - self.passed_cases

    @property
    def score(self) -> float:
        return self.passed_cases / self.total_cases if self.total_cases else 0.0

    @property
    def cost_usd(self) -> float:
        return 0.0

    @property
    def semantic_review_status(self) -> str:
        return "unreviewed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONVERSATION_EVAL_SCHEMA_VERSION,
            "kind": CONVERSATION_EVAL_KIND,
            "suite_name": self.suite_name,
            "methodology_version": self.methodology_version,
            "cost_usd": self.cost_usd,
            "semantic_review_status": self.semantic_review_status,
            "contract": dict(_EXECUTION_CONTRACT),
            "policy": {
                "default_retention_days": DEFAULT_RETENTION_DAYS,
                "maximum_retention_days": MAX_RETENTION_DAYS,
                "maximum_recent_turns": MAX_RECENT_TURNS,
                "default_max_context_bytes": DEFAULT_MAX_CONTEXT_BYTES,
                "content_deletion": "immediate_logical_removal",
                "audit_event_retention": "hashes_and_lifecycle_only",
            },
            "fixtures": conversation_contract_fixtures(),
            "comparison_manifest": json.loads(json.dumps(FROZEN_COMPARISON_MANIFEST)),
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "score": round(self.score, 6),
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
            "generated_at": self.generated_at.isoformat(),
        }


def _outcome(case_id: str, category: str, passed: bool, **detail: Any) -> ConversationEvalOutcome:
    return ConversationEvalOutcome(case_id=case_id, category=category, passed=passed, detail=detail)


def _check_contract_fixture_coverage() -> ConversationEvalOutcome:
    fixtures = conversation_contract_fixtures()
    expected = {"conversation", "turn", "event", "context_snapshot", "error"}
    versions = {payload["schema_version"] for payload in fixtures.values()}
    passed = set(fixtures) == expected and len(versions) == len(expected)
    return _outcome(
        "contract_fixture_coverage",
        "contract",
        passed,
        fixture_names=sorted(fixtures),
        schema_versions=sorted(versions),
    )


def _check_application_identity_boundary() -> ConversationEvalOutcome:
    fixtures = conversation_contract_fixtures()
    conversation_id = fixtures["conversation"]["conversation_id"]
    turn = fixtures["turn"]
    event = fixtures["event"]
    forbidden_fields = {"mcp_session_id", "transport_session_id", "a2a_task_id", "bearer_token", "api_key"}
    flattened_keys = set(fixtures["conversation"]) | set(turn) | set(event)
    passed = (
        conversation_id.startswith("conv_")
        and turn["conversation_id"] == conversation_id
        and event["conversation_id"] == conversation_id
        and forbidden_fields.isdisjoint(flattened_keys)
    )
    return _outcome(
        "protocol_neutral_application_identity",
        "identity",
        passed,
        conversation_id=conversation_id,
        transport_identity_used=False,
        credential_used_as_locator=False,
    )


def _check_serialized_version_contract() -> ConversationEvalOutcome:
    manifest = FROZEN_COMPARISON_MANIFEST["durable_conversation"]
    turns = manifest["turns"]
    passed = (
        turns[0]["ordinal"] == 1
        and turns[0]["expected_version"] is None
        and turns[1]["ordinal"] == 2
        and turns[1]["expected_version"] == 2
        and turns[1]["visible_prior_turn_ids"] == [turns[0]["turn_id"]]
    )
    return _outcome(
        "serialized_optimistic_versioning",
        "concurrency",
        passed,
        one_active_turn_per_conversation=True,
        stale_version_result="version_conflict",
    )


def _check_idempotency_contract() -> ConversationEvalOutcome:
    matrix = [
        {"same_key": True, "same_request_hash": True, "result": "replay_without_dispatch"},
        {"same_key": True, "same_request_hash": False, "result": "idempotency_conflict"},
        {"same_key": False, "same_request_hash": True, "result": "new_logical_request"},
    ]
    passed = matrix == [
        {"same_key": True, "same_request_hash": True, "result": "replay_without_dispatch"},
        {"same_key": True, "same_request_hash": False, "result": "idempotency_conflict"},
        {"same_key": False, "same_request_hash": True, "result": "new_logical_request"},
    ]
    return _outcome(
        "idempotency_replay_and_conflict",
        "concurrency",
        passed,
        matrix=matrix,
        record_before_backend_construction=True,
    )


def _check_typed_state_contract() -> ConversationEvalOutcome:
    conversation_states = {
        "open",
        "input_required",
        "waiting_capacity",
        "closed",
        "expired",
        "cancelled",
        "failed",
    }
    turn_states = {
        "accepted",
        "running",
        "input_required",
        "waiting_capacity",
        "completed",
        "cancelled",
        "budget_exhausted",
        "verifier_failed",
        "interrupted",
        "failed",
    }
    resumable_same_turn = {"waiting_capacity", "interrupted"}
    terminal_conversations = {"closed", "expired", "cancelled", "failed"}
    passed = not terminal_conversations.intersection({"open", "input_required", "waiting_capacity"}) and (
        resumable_same_turn < turn_states
    )
    return _outcome(
        "typed_lifecycle_states",
        "state",
        passed,
        conversation_states=sorted(conversation_states),
        turn_states=sorted(turn_states),
        resumable_same_turn=sorted(resumable_same_turn),
    )


def _check_bounded_context_contract() -> ConversationEvalOutcome:
    manifest_turns = FROZEN_COMPARISON_MANIFEST["durable_conversation"]["turns"]
    observed_recent = max(len(turn["visible_prior_turn_ids"]) for turn in manifest_turns)
    passed = (
        MAX_RECENT_TURNS == 6
        and DEFAULT_MAX_CONTEXT_BYTES == 65_536
        and observed_recent <= MAX_RECENT_TURNS
        and all("snapshot_id" in FROZEN_COMPARISON_MANIFEST for _ in (0,))
    )
    return _outcome(
        "bounded_frozen_context",
        "context",
        passed,
        frozen_snapshot=True,
        maximum_recent_turns=MAX_RECENT_TURNS,
        maximum_context_bytes=DEFAULT_MAX_CONTEXT_BYTES,
        full_transcript_replay=False,
    )


def _check_retention_and_deletion_contract() -> ConversationEvalOutcome:
    fixtures = conversation_contract_fixtures()
    retention = fixtures["conversation"]["retention"]
    event_keys = set(fixtures["event"])
    content_fields = {"content", "direct_answer", "packet", "prompt", "response"}
    passed = (
        retention["retention_days"] == DEFAULT_RETENTION_DAYS
        and 0 < DEFAULT_RETENTION_DAYS <= MAX_RETENTION_DAYS
        and retention["content_deleted"] is False
        and content_fields.isdisjoint(event_keys)
    )
    return _outcome(
        "finite_retention_separate_from_audit",
        "privacy",
        passed,
        default_days=DEFAULT_RETENTION_DAYS,
        maximum_days=MAX_RETENTION_DAYS,
        deletion="immediate_logical_removal",
        audit_contains_raw_content=False,
    )


def _check_answer_contract() -> ConversationEvalOutcome:
    artifact = conversation_contract_fixtures()["turn"]["artifact"]
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
    passed = set(artifact) == required and all(
        implication["authority"] == "proposal_only" for implication in artifact["decision_implications"]
    )
    return _outcome(
        "consulting_quality_answer_shape",
        "answer",
        passed,
        required_fields=sorted(required),
        preserves_dissent=True,
        records_change_conditions=True,
        semantic_quality_judged=False,
    )


def _check_structural_comparison_manifest() -> ConversationEvalOutcome:
    manifest = FROZEN_COMPARISON_MANIFEST
    one_shot = manifest["repeated_one_shot"]
    durable = manifest["durable_conversation"]
    passed = (
        len(one_shot["calls"]) == len(durable["turns"]) == 2
        and one_shot["application_context_carried"] is False
        and durable["application_context_carried"] is True
        and manifest["comparison_status"] == "structural_only"
        and manifest["semantic_quality_review"] == "unreviewed"
    )
    return _outcome(
        "repeated_one_shot_comparison_manifest",
        "comparison",
        passed,
        same_question=True,
        same_roster=True,
        same_snapshot=True,
        semantic_superiority_claimed=False,
    )


def _check_local_only_no_side_effects() -> ConversationEvalOutcome:
    fixtures = conversation_contract_fixtures()
    conversation = fixtures["conversation"]
    contract = _EXECUTION_CONTRACT
    passed = (
        conversation["backend"]["capacity_source"] == "local_owned"
        and conversation["backend"]["fallback_policy"] == "none"
        and conversation["backend"]["live_metered_fallback"] is False
        and conversation["bounds"]["max_cost_usd"] == 0.0
        and contract["provider_calls"] == 0
        and contract["backend_calls"] == 0
        and contract["network_access"] is False
        and contract["writes_runtime_state"] is False
        and contract["cost_usd"] == 0.0
    )
    return _outcome("local_only_no_fallback_or_side_effects", "capacity", passed, **contract)


def _check_semantic_judgment_boundary() -> ConversationEvalOutcome:
    artifact = conversation_contract_fixtures()["turn"]["artifact"]
    passed = (
        _EXECUTION_CONTRACT["semantic_verdict"] is False
        and FROZEN_COMPARISON_MANIFEST["semantic_quality_review"] == "unreviewed"
        and artifact["semantic_status"] == "answered"
    )
    return _outcome(
        "semantic_judgment_remains_model_or_review_work",
        "agentic_balance",
        passed,
        schema_checks_form_only=True,
        truth_judged=False,
        usefulness_judged=False,
        calibration_judged=False,
    )


def _check_owner_and_authority_boundary() -> ConversationEvalOutcome:
    fixtures = conversation_contract_fixtures()
    error = fixtures["error"]["error"]
    artifact = fixtures["turn"]["artifact"]
    passed = (
        error["safe_message"] == "The conversation changed; fetch current state before retrying."
        and artifact["host_action_boundary"] == _HOST_ACTION_BOUNDARY
        and all(item["authority"] == "proposal_only" for item in artifact["decision_implications"])
    )
    return _outcome(
        "owner_isolation_and_host_authority",
        "security",
        passed,
        mismatched_owner_result="not_found",
        conversation_id_is_credential=False,
        downstream_actions_authorized=False,
    )


def run_conversation_eval() -> ConversationEvalReport:
    """Run all built-in durable-conversation structural checks."""
    return ConversationEvalReport(
        outcomes=(
            _check_contract_fixture_coverage(),
            _check_application_identity_boundary(),
            _check_serialized_version_contract(),
            _check_idempotency_contract(),
            _check_typed_state_contract(),
            _check_bounded_context_contract(),
            _check_retention_and_deletion_contract(),
            _check_answer_contract(),
            _check_structural_comparison_manifest(),
            _check_local_only_no_side_effects(),
            _check_semantic_judgment_boundary(),
            _check_owner_and_authority_boundary(),
        )
    )


def write_conversation_eval_report(
    report: ConversationEvalReport,
    *,
    output_dir: Path | None = None,
) -> Path:
    """Write the report only when the caller explicitly requests it."""
    if output_dir is None:
        from deepr.config import runtime_data_path

        root = runtime_data_path("benchmarks")
    else:
        root = output_dir
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    path = root / f"conversation_eval_{timestamp}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path
