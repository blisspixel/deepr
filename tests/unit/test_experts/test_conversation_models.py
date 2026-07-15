"""Validation tests for durable expert-conversation models."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Callable

import pytest

from deepr.experts.conversation.models import (
    ERROR_KIND,
    ERROR_SCHEMA_VERSION,
    BackendSelection,
    ConsultationMode,
    ConversationBounds,
    ConversationContinueRequest,
    ConversationError,
    ConversationResumeRequest,
    ConversationStartRequest,
    ErrorCode,
    ExpertSnapshotInput,
    TurnExecutionResult,
    TurnState,
    TurnUsage,
    canonical_json,
    idempotency_key_sha256,
    new_opaque_id,
    owner_binding_sha256,
    parse_datetime,
    require_utc,
)
from tests.unit.conversation_fixtures import answer_artifact, expert_snapshot, start_request


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_turns", 0),
        ("max_turns", True),
        ("max_model_calls", 1001),
        ("max_context_bytes", 100),
        ("max_elapsed_seconds", 0),
        ("max_cost_usd", -0.01),
        ("max_cost_usd", math.inf),
    ],
)
def test_bounds_reject_invalid_values(field: str, value: object) -> None:
    values: dict[str, object] = {field: value}
    with pytest.raises(ConversationError) as raised:
        ConversationBounds(**values)  # type: ignore[arg-type]
    assert raised.value.code is ErrorCode.INVALID_REQUEST


def test_stage_one_rejects_plan_api_and_fallback_capacity() -> None:
    snapshots = (expert_snapshot(),)
    invalid_backends = [
        BackendSelection("plan_quota", "plan", "codex"),
        BackendSelection("metered_api", "api", "gpt", "explicit_only", False),
        BackendSelection("local_owned", "local", "local", "explicit_only", False),
        BackendSelection("local_owned", "local", "local", "none", True),
    ]

    for backend in invalid_backends:
        with pytest.raises(ConversationError) as raised:
            ConversationStartRequest(
                owner_id="owner",
                idempotency_key="key",
                message="question",
                expert_snapshots=snapshots,
                backend=backend,
            )
        assert raised.value.code is ErrorCode.INVALID_REQUEST


def test_snapshot_and_result_defensively_copy_untrusted_json() -> None:
    packet = {"beliefs": [{"claim": "original"}]}
    snapshot = expert_snapshot(packet=packet)
    artifact = answer_artifact()
    result = TurnExecutionResult.completed(artifact)

    packet["beliefs"][0]["claim"] = "mutated"
    artifact["direct_answer"] = "mutated"

    assert snapshot.packet["beliefs"][0]["claim"] == "original"
    assert result.artifact is not None
    assert result.artifact["direct_answer"] == "Use an idempotent durable transition."


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("direct_answer",), None),
        (("experts_consulted",), []),
        (("assumptions", 0, "source"), "invented"),
        (("assumptions", 0, "source"), []),
        (("evidence", 0, "source_type"), "memory"),
        (("evidence", 0, "source_type"), []),
        (("uncertainty", "kind"), "certain"),
        (("uncertainty", "kind"), []),
        (("dissent", 0, "expert_names"), []),
        (("decision_implications", 0, "authority"), "enacted"),
        (("semantic_status",), "done"),
        (("semantic_status",), []),
        (("host_action_boundary",), "The model may deploy."),
    ],
)
def test_answer_contract_rejects_malformed_or_authoritative_content(path: tuple[object, ...], value: object) -> None:
    artifact = answer_artifact()
    target: object = artifact
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]

    with pytest.raises(ConversationError):
        TurnExecutionResult.completed(artifact)


def test_input_required_turn_requires_matching_semantic_status() -> None:
    with pytest.raises(ConversationError):
        TurnExecutionResult(
            state=TurnState.INPUT_REQUIRED,
            stop_reason="input_required",
            retryable=True,
            artifact=answer_artifact(semantic_status="answered"),
        )

    result = TurnExecutionResult(
        state=TurnState.INPUT_REQUIRED,
        stop_reason="input_required",
        retryable=True,
        artifact=answer_artifact(semantic_status="input_required"),
    )
    assert result.state is TurnState.INPUT_REQUIRED

    with pytest.raises(ConversationError):
        TurnExecutionResult.completed(answer_artifact(semantic_status="input_required"))


def test_answer_contract_rejects_unresolved_and_duplicate_references() -> None:
    outside_roster = answer_artifact()
    outside_roster["evidence"][0]["expert_name"] = "not_consulted"
    with pytest.raises(ConversationError):
        TurnExecutionResult.completed(outside_roster)

    missing_evidence = answer_artifact()
    missing_evidence["dissent"][0]["evidence_refs"] = ["missing"]
    with pytest.raises(ConversationError):
        TurnExecutionResult.completed(missing_evidence)

    duplicate = answer_artifact()
    duplicate["evidence"].append({**duplicate["evidence"][0], "citation": "another-source"})
    with pytest.raises(ConversationError):
        TurnExecutionResult.completed(duplicate)


def test_waiting_turn_cannot_carry_artifact() -> None:
    with pytest.raises(ConversationError):
        TurnExecutionResult(
            state=TurnState.WAITING_CAPACITY,
            stop_reason="waiting_capacity",
            retryable=True,
            artifact=answer_artifact(),
        )


def test_start_request_rejects_duplicate_experts_wrong_mode_and_retention() -> None:
    snapshots = (expert_snapshot(), expert_snapshot())
    with pytest.raises(ConversationError):
        start_request(snapshots=snapshots, mode=ConsultationMode.COUNCIL)
    with pytest.raises(ConversationError):
        start_request(
            snapshots=(expert_snapshot(), expert_snapshot("security", marker="55")),
            mode=ConsultationMode.FOCUSED,
        )
    with pytest.raises(ConversationError):
        start_request(retention_days=366)


@pytest.mark.parametrize("key", ["", " has-space", "x" * 129, "slash/not-allowed"])
def test_idempotency_key_rejects_unsafe_shapes(key: str) -> None:
    with pytest.raises(ConversationError):
        idempotency_key_sha256(key)


def test_owner_and_idempotency_hashes_do_not_reveal_input() -> None:
    owner_hash = owner_binding_sha256("scoped-key-123")
    idem_hash = idempotency_key_sha256("request-123")
    assert len(owner_hash) == len(idem_hash) == 64
    assert "scoped-key" not in owner_hash
    assert "request" not in idem_hash
    assert owner_hash == owner_binding_sha256("scoped-key-123")


def test_opaque_conversation_ids_have_128_bits_and_are_unique() -> None:
    values = {new_opaque_id("conv") for _ in range(100)}
    assert len(values) == 100
    assert all(value.startswith("conv_") and len(value.removeprefix("conv_")) == 32 for value in values)


def test_typed_error_envelope_is_redacted_and_versioned() -> None:
    error = ConversationError(
        ErrorCode.VERSION_CONFLICT,
        "Fetch current state.",
        retryable=True,
        conversation_id="conv_" + "a" * 32,
        current_version=4,
        expected_version=3,
    )
    payload = error.to_envelope()

    assert payload["schema_version"] == ERROR_SCHEMA_VERSION
    assert payload["kind"] == ERROR_KIND
    assert payload["error"]["details"] == {
        "expected_version": 3,
        "current_version": 4,
        "field": None,
        "retry_after_ms": None,
    }
    assert "traceback" not in str(payload).lower()


def test_continue_request_rejects_non_integer_version() -> None:
    with pytest.raises(ConversationError):
        ConversationContinueRequest(
            owner_id="owner",
            conversation_id="conv_" + "a" * 32,
            expected_version="2",  # type: ignore[arg-type]
            idempotency_key="turn-2",
            message="continue",
        )


def test_public_models_reject_wrong_runtime_types_with_typed_errors() -> None:
    with pytest.raises(ConversationError):
        owner_binding_sha256(123)  # type: ignore[arg-type]
    with pytest.raises(ConversationError):
        idempotency_key_sha256(None)  # type: ignore[arg-type]
    with pytest.raises(ConversationError):
        BackendSelection("local_owned", "local", 7)  # type: ignore[arg-type]
    with pytest.raises(ConversationError):
        start_request(retention_days="30")  # type: ignore[arg-type]


def test_turn_usage_rejects_nonfinite_and_negative_values() -> None:
    with pytest.raises(ConversationError):
        TurnUsage(cost_usd=math.nan)
    with pytest.raises(ConversationError):
        TurnUsage(output_tokens=-1)


def test_low_level_contract_helpers_fail_with_typed_errors() -> None:
    invalid_calls: list[Callable[[], Any]] = [
        lambda: canonical_json({"not_json": {1, 2}}),
        lambda: owner_binding_sha256(" "),
        lambda: require_utc(datetime(2026, 7, 15)),
        lambda: parse_datetime("not-a-time"),
        lambda: ConversationBounds.from_dict([]),  # type: ignore[arg-type]
        lambda: ConversationBounds.from_dict({"unexpected": 1}),
        lambda: BackendSelection.from_dict([]),  # type: ignore[arg-type]
        lambda: BackendSelection.from_dict({"unexpected": 1}),
    ]

    for call in invalid_calls:
        with pytest.raises(ConversationError):
            call()


@pytest.mark.parametrize(
    "backend",
    [
        ("unknown", "local", "model", "none", False),
        ("local_owned", "unknown", "model", "none", False),
        ("local_owned", "local", "model", "unknown", False),
        ("local_owned", "local", "model", "none", "false"),
    ],
)
def test_backend_selection_rejects_invalid_primitive_contracts(backend: tuple[object, ...]) -> None:
    with pytest.raises(ConversationError):
        BackendSelection(*backend)  # type: ignore[arg-type]


def test_snapshot_input_rejects_invalid_fields_and_size() -> None:
    invalid_snapshots: list[Callable[[], ExpertSnapshotInput]] = [
        lambda: ExpertSnapshotInput("", "a" * 64, "position", {}),
        lambda: ExpertSnapshotInput("expert", "invalid", "position", {}),
        lambda: ExpertSnapshotInput("expert", "a" * 64, "", {}),
        lambda: ExpertSnapshotInput("expert", "a" * 64, "position", []),  # type: ignore[arg-type]
        lambda: ExpertSnapshotInput("expert", "a" * 64, "position", {"large": "x" * 524_289}),
    ]

    for build in invalid_snapshots:
        with pytest.raises(ConversationError):
            build()


def test_start_and_continuation_models_reject_invalid_nested_contracts() -> None:
    base = start_request()
    invalid_starts: list[Callable[[], ConversationStartRequest]] = [
        lambda: ConversationStartRequest(
            base.owner_id,
            base.idempotency_key,
            base.message,
            base.expert_snapshots,
            "local",  # type: ignore[arg-type]
        ),
        lambda: ConversationStartRequest(
            base.owner_id,
            base.idempotency_key,
            base.message,
            base.expert_snapshots,
            base.backend,
            "bounds",  # type: ignore[arg-type]
        ),
        lambda: ConversationStartRequest(
            base.owner_id,
            base.idempotency_key,
            base.message,
            base.expert_snapshots,
            base.backend,
            mode="focused",  # type: ignore[arg-type]
        ),
        lambda: ConversationStartRequest(
            base.owner_id,
            base.idempotency_key,
            base.message,
            (),
            base.backend,
        ),
    ]
    for build in invalid_starts:
        with pytest.raises(ConversationError):
            build()

    with pytest.raises(ConversationError):
        ConversationContinueRequest("owner", "bad-id", 1, "key", "message")
    with pytest.raises(ConversationError):
        ConversationContinueRequest("owner", "conv_" + "a" * 32, 1, "key", "message", "bad-input")
    with pytest.raises(ConversationError):
        ConversationResumeRequest("owner", "conv_" + "a" * 32, 0, "key")
    with pytest.raises(ConversationError):
        ConversationResumeRequest("owner", "bad-id", 1, "key")


def test_executor_result_rejects_invalid_runtime_contracts() -> None:
    invalid_results: list[Callable[[], TurnExecutionResult]] = [
        lambda: TurnExecutionResult("completed", "completed", False),  # type: ignore[arg-type]
        lambda: TurnExecutionResult(TurnState.FAILED, 7, False),  # type: ignore[arg-type]
        lambda: TurnExecutionResult(TurnState.FAILED, "failed", 0),  # type: ignore[arg-type]
        lambda: TurnExecutionResult(TurnState.FAILED, "failed", False, usage={}),  # type: ignore[arg-type]
        lambda: TurnExecutionResult(TurnState.FAILED, "completed", False),
        lambda: TurnExecutionResult(TurnState.COMPLETED, "completed", False),
        lambda: TurnExecutionResult(
            TurnState.FAILED,
            "failed",
            False,
            consult_trace_id="bad",
        ),
    ]

    for build in invalid_results:
        with pytest.raises(ConversationError):
            build()


def test_answer_contract_enforces_nested_size_and_shape_bounds() -> None:
    malformed = answer_artifact()
    malformed["uncertainty"] = []
    with pytest.raises(ConversationError):
        TurnExecutionResult.completed(malformed)

    bad_value = answer_artifact()
    bad_value["uncertainty"]["value"] = "x" * 257
    with pytest.raises(ConversationError):
        TurnExecutionResult.completed(bad_value)

    bad_collection = answer_artifact()
    bad_collection["agreements"] = [""]
    with pytest.raises(ConversationError):
        TurnExecutionResult.completed(bad_collection)

    oversized = answer_artifact()
    large_item = "x" * 4096
    oversized["agreements"] = [large_item] * 100
    oversized["change_conditions"] = [large_item] * 100
    with pytest.raises(ConversationError):
        TurnExecutionResult.completed(oversized)
