"""Durability, isolation, idempotency, and projection tests."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from deepr.experts.conversation.models import (
    ConversationBounds,
    ConversationBusy,
    ConversationContinueRequest,
    ConversationError,
    ConversationNotFound,
    ConversationResumeRequest,
    ErrorCode,
    IdempotencyConflict,
    TurnExecutionResult,
    TurnState,
    TurnUsage,
    VersionConflict,
)
from deepr.experts.conversation.store import ExpertConversationStore
from tests.unit.conversation_fixtures import (
    MutableClock,
    answer_artifact,
    completed_result,
    expert_snapshot,
    start_request,
)

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "schemas"


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _complete_start(store: ExpertConversationStore, *, owner: str = "owner-a", key: str = "start-001"):
    lease = store.reserve_start(start_request(owner_id=owner, idempotency_key=key))
    return lease, store.finalize_turn(lease, completed_result())


def test_store_uses_runtime_path_pragmas_and_releases_windows_handles(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "conversations.db"
    store = ExpertConversationStore(path)
    assert store.path == path
    assert store.quick_check() == "ok"

    connection = store._connect()
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA secure_delete").fetchone()[0] == 1
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        connection.close()

    moved = tmp_path / "moved.db"
    path.rename(moved)
    assert moved.exists()


def test_store_rejects_unknown_future_database_version(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA user_version=999")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ConversationError) as raised:
        ExpertConversationStore(path)
    assert raised.value.code is ErrorCode.STORAGE_FAILED


def test_start_survives_restart_before_executor_result(tmp_path: Path) -> None:
    path = tmp_path / "conversation.db"
    first_store = ExpertConversationStore(path)
    lease = first_store.reserve_start(start_request())

    restarted = ExpertConversationStore(path)
    state = restarted.get(owner_id="owner-a", conversation_id=lease.conversation_id)

    assert state.conversation["state"] == "open"
    assert state.conversation["version"] == 1
    assert state.conversation["current_turn_id"] == lease.turn_id
    assert state.turn is not None
    assert state.turn["state"] == "running"
    assert state.turn["artifact_available"] is False


def test_completed_start_and_public_contracts_validate(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    _, result = _complete_start(store)
    snapshot = store.get_snapshot(owner_id="owner-a", conversation_id=result.conversation["conversation_id"])
    events = store.list_events(owner_id="owner-a", conversation_id=result.conversation["conversation_id"])

    _validator("expert-conversation-v1.json").validate(result.conversation)
    assert result.turn is not None
    _validator("expert-conversation-turn-v1.json").validate(result.turn)
    _validator("expert-context-snapshot-v1.json").validate(snapshot)
    for event in events:
        _validator("expert-conversation-event-v1.json").validate(event)

    assert result.conversation["state"] == "open"
    assert result.conversation["version"] == 2
    assert result.conversation["usage"]["turns_started"] == 1
    assert result.conversation["usage"]["turns_completed"] == 1
    assert result.turn["trace"]["consult_lifecycle_trace_id"] == "trace_fixture_0001"


def test_start_idempotency_replays_without_another_dispatch(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    request = start_request()
    first = store.reserve_start(request)
    replay = store.reserve_start(request)

    assert first.dispatch_required is True
    assert replay.dispatch_required is False
    assert replay.replayed is True
    assert replay.conversation_id == first.conversation_id
    assert replay.turn_id == first.turn_id

    with pytest.raises(IdempotencyConflict):
        store.reserve_start(start_request(message="materially different"))


def test_concurrent_duplicate_start_has_exactly_one_dispatch(tmp_path: Path) -> None:
    path = tmp_path / "conversation.db"
    first_store = ExpertConversationStore(path)
    second_store = ExpertConversationStore(path)
    request = start_request()

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(lambda store: store.reserve_start(request), (first_store, second_store)))

    assert sum(lease.dispatch_required for lease in leases) == 1
    assert {lease.conversation_id for lease in leases} == {leases[0].conversation_id}


def test_owner_mismatch_is_indistinguishable_from_missing(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    _, result = _complete_start(store)
    conversation_id = result.conversation["conversation_id"]

    with pytest.raises(ConversationNotFound) as wrong_owner:
        store.get(owner_id="owner-b", conversation_id=conversation_id)
    with pytest.raises(ConversationNotFound) as missing:
        store.get(owner_id="owner-b", conversation_id="conv_" + "f" * 32)

    assert wrong_owner.value.to_envelope() == missing.value.to_envelope()
    assert conversation_id not in str(wrong_owner.value.to_envelope())


def test_continue_requires_current_version_and_one_active_turn(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    _, result = _complete_start(store)
    conversation_id = result.conversation["conversation_id"]

    with pytest.raises(VersionConflict) as stale:
        store.reserve_continue(
            ConversationContinueRequest(
                owner_id="owner-a",
                conversation_id=conversation_id,
                expected_version=1,
                idempotency_key="turn-stale",
                message="stale",
            )
        )
    assert stale.value.current_version == 2

    request = ConversationContinueRequest(
        owner_id="owner-a",
        conversation_id=conversation_id,
        expected_version=2,
        idempotency_key="turn-2",
        message="follow up",
    )
    active = store.reserve_continue(request)
    with pytest.raises(ConversationBusy):
        store.reserve_continue(
            ConversationContinueRequest(
                owner_id="owner-a",
                conversation_id=conversation_id,
                expected_version=active.projection_version,
                idempotency_key="turn-3",
                message="overlap",
            )
        )

    replay = store.reserve_continue(request)
    assert replay.dispatch_required is False
    assert replay.turn_id == active.turn_id


def test_concurrent_distinct_continuations_admit_only_one(tmp_path: Path) -> None:
    path = tmp_path / "conversation.db"
    primary = ExpertConversationStore(path)
    _, result = _complete_start(primary)
    conversation_id = result.conversation["conversation_id"]
    stores = (ExpertConversationStore(path), ExpertConversationStore(path))
    requests = (
        ConversationContinueRequest("owner-a", conversation_id, 2, "turn-a", "first contender"),
        ConversationContinueRequest("owner-a", conversation_id, 2, "turn-b", "second contender"),
    )

    def reserve(pair: tuple[ExpertConversationStore, ConversationContinueRequest]):
        try:
            return pair[0].reserve_continue(pair[1])
        except ConversationError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, zip(stores, requests, strict=True)))

    leases = [outcome for outcome in outcomes if not isinstance(outcome, ConversationError)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, ConversationError)]
    assert len(leases) == len(failures) == 1
    assert failures[0].code in {ErrorCode.VERSION_CONFLICT, ErrorCode.CONVERSATION_BUSY}


def test_input_required_continuation_must_match_pending_request(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    lease = store.reserve_start(start_request())
    input_result = TurnExecutionResult(
        state=TurnState.INPUT_REQUIRED,
        stop_reason="input_required",
        retryable=True,
        artifact=answer_artifact(semantic_status="input_required"),
        usage=TurnUsage(model_calls=1, input_tokens=80, output_tokens=40, elapsed_ms=500),
    )
    state = store.finalize_turn(lease, input_result)
    pending = state.conversation["pending_input_request_id"]
    assert state.conversation["state"] == "input_required"
    assert pending.startswith("input_")

    with pytest.raises(ConversationError) as wrong:
        store.reserve_continue(
            ConversationContinueRequest(
                "owner-a",
                lease.conversation_id,
                state.conversation["version"],
                "wrong-input",
                "clarification",
                "input_" + "f" * 32,
            )
        )
    assert wrong.value.code is ErrorCode.INVALID_STATE

    continued = store.reserve_continue(
        ConversationContinueRequest(
            "owner-a",
            lease.conversation_id,
            state.conversation["version"],
            "right-input",
            "clarification",
            pending,
        )
    )
    assert continued.dispatch_required is True


def test_close_is_versioned_and_idempotent(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    _, result = _complete_start(store)
    conversation_id = result.conversation["conversation_id"]

    closed = store.close_conversation(owner_id="owner-a", conversation_id=conversation_id, expected_version=2)
    replay = store.close_conversation(owner_id="owner-a", conversation_id=conversation_id, expected_version=2)

    assert closed.conversation["state"] == "closed"
    assert closed.conversation["version"] == 3
    assert replay.replayed is True
    assert replay.conversation["version"] == 3


def test_content_deletion_removes_raw_data_but_preserves_hashes(tmp_path: Path) -> None:
    path = tmp_path / "conversation.db"
    store = ExpertConversationStore(path)
    _, result = _complete_start(store)
    conversation_id = result.conversation["conversation_id"]
    deleted = store.delete_content(owner_id="owner-a", conversation_id=conversation_id, expected_version=2)
    snapshot = store.get_snapshot(owner_id="owner-a", conversation_id=conversation_id)
    events = store.list_events(owner_id="owner-a", conversation_id=conversation_id)

    assert deleted.conversation["state"] == "closed"
    assert deleted.conversation["retention"]["content_deleted"] is True
    assert deleted.turn is not None
    assert deleted.turn["request"]["content_available"] is False
    assert deleted.turn["request"]["content"] is None
    assert deleted.turn["artifact_available"] is False
    assert deleted.turn["artifact"] is None
    assert len(deleted.turn["request"]["content_sha256"]) == 64
    assert len(deleted.turn["artifact_sha256"]) == 64
    assert snapshot["content_available"] is False
    assert snapshot["expert_snapshots"] is None
    _validator("expert-conversation-turn-v1.json").validate(deleted.turn)
    _validator("expert-context-snapshot-v1.json").validate(snapshot)
    assert events[-1]["event_type"] == "content_deleted"
    assert events[-1]["content_retained"] is False
    assert all("question" not in json.dumps(event).lower() for event in events)

    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT content_json, content_sha256, deleted_at FROM conversation_contents"
        ).fetchall()
    finally:
        connection.close()
    assert rows
    assert all(content is None and len(digest) == 64 and deleted_at for content, digest, deleted_at in rows)


def test_events_and_snapshots_are_database_enforced_immutable(tmp_path: Path) -> None:
    path = tmp_path / "conversation.db"
    store = ExpertConversationStore(path)
    _, result = _complete_start(store)
    conversation_id = result.conversation["conversation_id"]
    connection = sqlite3.connect(path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE conversation_events SET reason_code = 'tampered' WHERE conversation_id = ?",
                (conversation_id,),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE conversation_snapshots SET roster_hash = ? WHERE conversation_id = ?",
                ("f" * 64, conversation_id),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="only be purged"):
            connection.execute(
                "UPDATE conversation_contents SET content_json = 'null' WHERE conversation_id = ?",
                (conversation_id,),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM conversation_contents WHERE conversation_id = ?", (conversation_id,))
    finally:
        connection.close()


def test_projection_verification_and_rebuild_repair_mutable_drift(tmp_path: Path) -> None:
    path = tmp_path / "conversation.db"
    store = ExpertConversationStore(path)
    _, result = _complete_start(store)
    conversation_id = result.conversation["conversation_id"]
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE conversations SET state = 'failed', version = 99, model_calls = 88 WHERE conversation_id = ?",
            (conversation_id,),
        )
        connection.commit()
    finally:
        connection.close()

    before = store.verify_projection(conversation_id)
    after = store.rebuild_projection(conversation_id)
    restored = store.get(owner_id="owner-a", conversation_id=conversation_id)

    assert before["matches"] is False
    assert after["matches"] is True
    assert restored.conversation["state"] == "open"
    assert restored.conversation["version"] == 2
    assert restored.conversation["usage"]["model_calls"] == 1


def test_result_overrun_fails_verifier_without_persisting_artifact(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    lease = store.reserve_start(start_request())
    overrun = completed_result(usage=TurnUsage(model_calls=41, input_tokens=1, output_tokens=1, elapsed_ms=1))

    result = store.finalize_turn(lease, overrun)

    assert result.conversation["state"] == "failed"
    assert result.conversation["usage"]["model_calls"] == 41
    assert result.turn["capacity"]["remaining"]["model_calls"] == 0
    assert result.turn is not None
    assert result.turn["state"] == "verifier_failed"
    assert result.turn["artifact_available"] is False
    assert result.turn["artifact_sha256"] is None


@pytest.mark.parametrize(
    ("bounds", "usage"),
    [
        (ConversationBounds(max_turns=1), TurnUsage(model_calls=1, input_tokens=1, output_tokens=1)),
        (ConversationBounds(max_model_calls=1), TurnUsage(model_calls=1, input_tokens=1, output_tokens=1)),
        (ConversationBounds(max_input_tokens=1), TurnUsage(model_calls=1, input_tokens=1, output_tokens=1)),
        (ConversationBounds(max_output_tokens=1), TurnUsage(model_calls=1, input_tokens=1, output_tokens=1)),
        (
            ConversationBounds(max_elapsed_seconds=1),
            TurnUsage(model_calls=1, input_tokens=1, output_tokens=1, elapsed_ms=1000),
        ),
    ],
)
def test_continuation_admission_checks_every_remaining_capacity(
    tmp_path: Path,
    bounds: ConversationBounds,
    usage: TurnUsage,
) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    lease = store.reserve_start(start_request(bounds=bounds))
    completed = store.finalize_turn(lease, completed_result(usage=usage))

    with pytest.raises(ConversationError) as raised:
        store.reserve_continue(
            ConversationContinueRequest(
                "owner-a",
                lease.conversation_id,
                completed.conversation["version"],
                "capacity-next",
                "continue",
            )
        )
    assert raised.value.code is ErrorCode.CAPACITY_EXHAUSTED


def test_expired_attempt_result_is_rejected_without_separate_recovery_call(tmp_path: Path) -> None:
    clock = MutableClock()
    store = ExpertConversationStore(tmp_path / "conversation.db", clock=clock)
    lease = store.reserve_start(start_request(bounds=ConversationBounds(max_elapsed_seconds=1)))
    clock.advance(seconds=32)

    late = store.finalize_turn(lease, completed_result())

    assert late.dispatch_status == "lease_expired_result_ignored"
    assert late.conversation["state"] == "waiting_capacity"
    assert late.conversation["usage"]["model_calls"] == 1
    assert late.turn["state"] == "interrupted"


def test_ambiguous_recovered_call_consumes_resume_capacity(tmp_path: Path) -> None:
    clock = MutableClock()
    store = ExpertConversationStore(tmp_path / "conversation.db", clock=clock)
    lease = store.reserve_start(start_request(bounds=ConversationBounds(max_model_calls=1, max_elapsed_seconds=1)))
    clock.advance(seconds=32)
    assert store.recover_expired_leases() == 1

    with pytest.raises(ConversationError) as raised:
        store.reserve_resume(ConversationResumeRequest("owner-a", lease.conversation_id, 2, "resume-exhausted"))
    assert raised.value.code is ErrorCode.CAPACITY_EXHAUSTED


def test_closed_conversation_content_expires_on_schedule(tmp_path: Path) -> None:
    clock = MutableClock()
    store = ExpertConversationStore(tmp_path / "conversation.db", clock=clock)
    lease = store.reserve_start(start_request(retention_days=1))
    completed = store.finalize_turn(lease, completed_result())
    closed = store.close_conversation(
        owner_id="owner-a",
        conversation_id=lease.conversation_id,
        expected_version=completed.conversation["version"],
    )
    clock.advance(days=2)

    expired = store.get(owner_id="owner-a", conversation_id=lease.conversation_id)

    assert closed.conversation["state"] == "closed"
    assert expired.conversation["state"] == "expired"
    assert expired.conversation["retention"]["content_deleted"] is True
    assert expired.turn["request"]["content"] is None
    assert expired.turn["artifact"] is None


def test_oversized_initial_context_rolls_back_all_records(tmp_path: Path) -> None:
    path = tmp_path / "conversation.db"
    store = ExpertConversationStore(path)
    request = start_request(
        snapshots=(expert_snapshot(packet={"large": "x" * 2_000}),),
        bounds=ConversationBounds(max_context_bytes=1_024),
    )

    with pytest.raises(ConversationError) as raised:
        store.reserve_start(request)
    assert raised.value.code is ErrorCode.CAPACITY_EXHAUSTED
    with store._reader() as connection:
        assert connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM conversation_contents").fetchone()[0] == 0


def test_content_integrity_mismatch_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "conversation.db"
    store = ExpertConversationStore(path)
    _, result = _complete_start(store)
    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TRIGGER conversation_contents_purge_only")
        connection.execute(
            "UPDATE conversation_contents SET content_json = ? WHERE content_kind = 'turn_artifact'",
            ('{"tampered":true}',),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ConversationError) as raised:
        store.get(owner_id="owner-a", conversation_id=result.conversation["conversation_id"])
    assert raised.value.code is ErrorCode.STORAGE_FAILED


def test_explicit_missing_turn_returns_not_found(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    _, result = _complete_start(store)

    with pytest.raises(ConversationError) as raised:
        store.get(
            owner_id="owner-a",
            conversation_id=result.conversation["conversation_id"],
            turn_id="turn_" + "f" * 32,
        )
    assert raised.value.code is ErrorCode.NOT_FOUND
