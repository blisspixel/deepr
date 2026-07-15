"""Restart, lease, resume, and retention recovery tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from deepr.experts.conversation.models import (
    MAX_ATTEMPTS_PER_TURN,
    ConversationError,
    ConversationResumeRequest,
    ErrorCode,
    TurnExecutionResult,
)
from deepr.experts.conversation.store import ExpertConversationStore
from tests.unit.conversation_fixtures import MutableClock, completed_result, start_request


def test_running_attempt_is_recovered_only_after_durable_lease_expiry(tmp_path: Path) -> None:
    clock = MutableClock()
    path = tmp_path / "conversation.db"
    first = ExpertConversationStore(path, clock=clock)
    lease = first.reserve_start(start_request())

    restarted = ExpertConversationStore(path, clock=clock)
    assert restarted.recover_expired_leases() == 0
    assert restarted.get(owner_id="owner-a", conversation_id=lease.conversation_id).turn["state"] == "running"

    clock.advance(seconds=331)
    assert restarted.recover_expired_leases() == 1
    interrupted = restarted.get(owner_id="owner-a", conversation_id=lease.conversation_id)
    assert interrupted.conversation["state"] == "waiting_capacity"
    assert interrupted.conversation["version"] == 2
    assert interrupted.conversation["usage"]["model_calls"] == 1
    assert interrupted.turn is not None
    assert interrupted.turn["state"] == "interrupted"
    assert interrupted.turn["stop"]["retryable"] is True
    assert restarted.recover_expired_leases() == 0


def test_interrupted_turn_resumes_same_turn_with_exact_context(tmp_path: Path) -> None:
    clock = MutableClock()
    store = ExpertConversationStore(tmp_path / "conversation.db", clock=clock)
    first = store.reserve_start(start_request())
    original_context_hash = first.execution_context.context_sha256
    clock.advance(seconds=331)
    assert store.recover_expired_leases() == 1

    resumed = store.reserve_resume(
        ConversationResumeRequest(
            owner_id="owner-a",
            conversation_id=first.conversation_id,
            expected_version=2,
            idempotency_key="resume-1",
        )
    )

    assert resumed.turn_id == first.turn_id
    assert resumed.attempt_id != first.attempt_id
    assert resumed.projection_version == 3
    assert resumed.execution_context is not None
    assert resumed.execution_context.context_sha256 == original_context_hash
    completed = store.finalize_turn(resumed, completed_result())
    assert completed.conversation["version"] == 4
    assert completed.conversation["usage"]["model_calls"] == 2
    assert completed.turn["attempt_count"] == 2
    assert store.verify_projection(first.conversation_id)["matches"] is True

    replay = store.reserve_resume(
        ConversationResumeRequest(
            owner_id="owner-a",
            conversation_id=first.conversation_id,
            expected_version=3,
            idempotency_key="resume-1",
        )
    )
    assert replay.dispatch_required is False
    assert replay.turn_id == first.turn_id


def test_late_result_from_expired_attempt_cannot_overwrite_resumed_attempt(tmp_path: Path) -> None:
    clock = MutableClock()
    store = ExpertConversationStore(tmp_path / "conversation.db", clock=clock)
    first = store.reserve_start(start_request())
    clock.advance(seconds=331)
    store.recover_expired_leases()
    resumed = store.reserve_resume(ConversationResumeRequest("owner-a", first.conversation_id, 2, "resume-late"))

    stale = store.finalize_turn(first, completed_result())
    current = store.get(owner_id="owner-a", conversation_id=first.conversation_id)

    assert stale.dispatch_status == "stale_attempt_ignored"
    assert current.turn is not None
    assert current.turn["state"] == "running"
    assert current.turn["trace"]["attempt_id"] == resumed.attempt_id
    final = store.finalize_turn(resumed, completed_result())
    assert final.turn["state"] == "completed"


def test_waiting_capacity_resumes_without_creating_new_turn(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    first = store.reserve_start(start_request())
    waiting = store.finalize_turn(first, TurnExecutionResult.waiting_capacity())
    assert waiting.conversation["state"] == "waiting_capacity"
    assert waiting.conversation["version"] == 2

    resumed = store.reserve_resume(ConversationResumeRequest("owner-a", first.conversation_id, 2, "resume-capacity"))
    final = store.finalize_turn(resumed, completed_result())

    assert resumed.turn_id == first.turn_id
    assert final.conversation["usage"]["turns_started"] == 1
    assert final.turn["ordinal"] == 1
    assert final.turn["attempt_count"] == 2


def test_retention_expiry_is_terminal_and_deletes_content(tmp_path: Path) -> None:
    clock = MutableClock()
    store = ExpertConversationStore(tmp_path / "conversation.db", clock=clock)
    lease = store.reserve_start(start_request(retention_days=1))
    result = store.finalize_turn(lease, completed_result())
    clock.advance(days=2)

    expired = store.get(owner_id="owner-a", conversation_id=lease.conversation_id)
    events = store.list_events(owner_id="owner-a", conversation_id=lease.conversation_id)

    assert expired.conversation["state"] == "expired"
    assert expired.conversation["retention"]["content_deleted"] is True
    assert expired.turn is not None
    assert expired.turn["request"]["content"] is None
    assert expired.turn["artifact"] is None
    assert events[-1]["event_type"] == "conversation_expired"
    assert events[-1]["content_retained"] is False
    assert result.conversation["version"] + 1 == expired.conversation["version"]


def test_waiting_turn_is_cancelled_when_retention_expires(tmp_path: Path) -> None:
    clock = MutableClock()
    store = ExpertConversationStore(tmp_path / "conversation.db", clock=clock)
    lease = store.reserve_start(start_request(retention_days=1))
    waiting = store.finalize_turn(lease, TurnExecutionResult.waiting_capacity())
    clock.advance(days=2)

    assert store.expire_due() == 1
    expired = store.get(owner_id="owner-a", conversation_id=lease.conversation_id)
    assert expired.conversation["state"] == "expired"
    assert expired.conversation["current_turn_id"] is None
    assert expired.turn is not None
    assert expired.turn["state"] == "cancelled"
    assert waiting.conversation["version"] + 1 == expired.conversation["version"]


def test_waiting_capacity_retries_stop_at_attempt_ceiling(tmp_path: Path) -> None:
    store = ExpertConversationStore(tmp_path / "conversation.db")
    first = store.reserve_start(start_request())
    state = store.finalize_turn(first, TurnExecutionResult.waiting_capacity())

    for attempt_number in range(2, MAX_ATTEMPTS_PER_TURN + 1):
        resumed = store.reserve_resume(
            ConversationResumeRequest(
                "owner-a",
                first.conversation_id,
                state.conversation["version"],
                f"resume-{attempt_number}",
            )
        )
        state = store.finalize_turn(resumed, TurnExecutionResult.waiting_capacity())

    assert state.turn["attempt_count"] == MAX_ATTEMPTS_PER_TURN
    with pytest.raises(ConversationError) as raised:
        store.reserve_resume(
            ConversationResumeRequest(
                "owner-a",
                first.conversation_id,
                state.conversation["version"],
                "resume-over-limit",
            )
        )
    assert raised.value.code is ErrorCode.CAPACITY_EXHAUSTED
