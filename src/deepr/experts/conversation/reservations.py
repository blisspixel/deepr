"""Atomic admission and replay reservations for expert conversations."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from typing import TYPE_CHECKING

from deepr.experts.conversation.context import build_frozen_snapshot
from deepr.experts.conversation.models import (
    MAX_ATTEMPTS_PER_TURN,
    ConversationBusy,
    ConversationContinueRequest,
    ConversationError,
    ConversationResumeRequest,
    ConversationStartRequest,
    ConversationState,
    ErrorCode,
    TurnLease,
    TurnState,
    TurnUsage,
    lease_expiry,
    remaining_capacity,
    sha256_json,
)

if TYPE_CHECKING:
    from deepr.experts.conversation.store import ExpertConversationStore

_START_SCOPE = "start"
_RESUMABLE_TURN_STATES = {TurnState.WAITING_CAPACITY, TurnState.INTERRUPTED}


def reserve_start(store: ExpertConversationStore, request: ConversationStartRequest) -> TurnLease:
    """Atomically record a new conversation before executor construction."""
    self = store
    request_hash = sha256_json(request.request_material())
    now = self._now()
    with self._transaction() as connection:
        existing = self._existing_idempotency(
            connection,
            owner_hash=request.owner_hash,
            scope_id=_START_SCOPE,
            key_hash=request.idempotency_hash,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing

        conversation_id = self._new_id("conv")
        snapshot_id = self._new_id("snap")
        turn_id = self._new_id("turn")
        attempt_id = self._new_id("attempt")
        expires_at = now + timedelta(days=request.retention_days)
        connection.execute(
            """INSERT INTO conversations
               (conversation_id, owner_hash, state, version, mode, expert_names_json,
                snapshot_id, decision_brief_content_id, backend_json, bounds_json,
                turns_started, turns_completed, model_calls, input_tokens,
                output_tokens, elapsed_ms, cost_usd, retention_days, expires_at,
                content_deleted_at, current_turn_id, latest_turn_id,
                pending_input_request_id, created_at, updated_at)
               VALUES (?, ?, 'open', 1, ?, ?, ?, NULL, ?, ?, 1, 0, 0, 0,
                       0, 0, 0, ?, ?, NULL, ?, ?, NULL, ?, ?)""",
            (
                conversation_id,
                request.owner_hash,
                request.mode.value,
                self._json([snapshot.expert_name for snapshot in request.expert_snapshots]),
                snapshot_id,
                self._json(request.backend.to_dict()),
                self._json(request.bounds.to_dict()),
                request.retention_days,
                expires_at.isoformat(),
                turn_id,
                turn_id,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        row = self._owned_row(connection, conversation_id, request.owner_hash)
        decision_content_id: str | None = None
        if request.decision_brief is not None:
            decision_content_id, _ = self._insert_content(
                connection,
                conversation_id=conversation_id,
                turn_id=None,
                kind="decision_brief",
                value=request.decision_brief,
                now=now,
            )
            connection.execute(
                "UPDATE conversations SET decision_brief_content_id = ? WHERE conversation_id = ?",
                (decision_content_id, conversation_id),
            )
            row = self._owned_row(connection, conversation_id, request.owner_hash)

        snapshot = build_frozen_snapshot(
            conversation_id=conversation_id,
            snapshot_id=snapshot_id,
            expert_snapshots=request.expert_snapshots,
            created_at=now,
        )
        snapshot_content_id, _ = self._insert_content(
            connection,
            conversation_id=conversation_id,
            turn_id=None,
            kind="context_snapshot",
            value=snapshot,
            now=now,
        )
        connection.execute(
            """INSERT INTO conversation_snapshots
               (snapshot_id, conversation_id, content_id, context_builder_version,
                roster_hash, snapshot_sha256, total_bytes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                conversation_id,
                snapshot_content_id,
                snapshot["context_builder_version"],
                snapshot["roster_hash"],
                snapshot["snapshot_sha256"],
                snapshot["total_bytes"],
                now.isoformat(),
            ),
        )
        request_content_id, message_hash = self._insert_content(
            connection,
            conversation_id=conversation_id,
            turn_id=turn_id,
            kind="turn_request",
            value=request.message,
            now=now,
        )
        bounded = self._build_context(connection, row, message=request.message, ordinal=1)
        remaining = remaining_capacity(request.bounds, self._usage(row))
        capacity = {"turn": TurnUsage().to_dict(), "remaining": remaining}
        trace = {
            "attempt_id": attempt_id,
            "consult_trace_id": None,
            "consult_lifecycle_trace_id": None,
        }
        connection.execute(
            """INSERT INTO conversation_turns
               (turn_id, conversation_id, ordinal, state, request_content_id,
                request_sha256, input_request_id, next_input_request_id, context_json,
                artifact_content_id, artifact_sha256, stop_reason, retryable,
                capacity_json, trace_json, attempt_count, created_at, updated_at)
               VALUES (?, ?, 1, 'running', ?, ?, NULL, NULL, ?, NULL, NULL,
                       'running', 0, ?, ?, 1, ?, ?)""",
            (
                turn_id,
                conversation_id,
                request_content_id,
                message_hash,
                self._json(bounded.lineage_payload()),
                self._json(capacity),
                self._json(trace),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        connection.execute(
            """INSERT INTO conversation_turn_attempts
               (attempt_id, turn_id, attempt_ordinal, state, lease_expires_at,
                started_at, completed_at)
               VALUES (?, ?, 1, 'running', ?, ?, NULL)""",
            (attempt_id, turn_id, lease_expiry(now, request.bounds).isoformat(), now.isoformat()),
        )
        connection.execute(
            """INSERT INTO conversation_idempotency
               (owner_hash, scope_id, idempotency_key_sha256, request_sha256,
                conversation_id, turn_id, attempt_id, status, result_version,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'running', 1, ?, ?)""",
            (
                request.owner_hash,
                _START_SCOPE,
                request.idempotency_hash,
                request_hash,
                conversation_id,
                turn_id,
                attempt_id,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        self._event(
            connection,
            event_id=self._new_id("evt"),
            row=row,
            event_type="conversation_started",
            projection_version=1,
            previous_state=None,
            current_state=ConversationState.OPEN,
            now=now,
        )
        self._event(
            connection,
            event_id=self._new_id("evt"),
            row=row,
            event_type="turn_started",
            projection_version=1,
            previous_state=ConversationState.OPEN,
            current_state=ConversationState.OPEN,
            now=now,
            turn_id=turn_id,
            attempt_id=attempt_id,
            reason_code="running",
            request_sha256=message_hash,
        )
        return TurnLease(
            conversation_id=conversation_id,
            turn_id=turn_id,
            attempt_id=attempt_id,
            projection_version=1,
            dispatch_required=True,
            replayed=False,
            execution_context=self._execution_context(
                row,
                turn_id=turn_id,
                attempt_id=attempt_id,
                message=request.message,
                bounded=bounded,
            ),
        )


def reserve_continue(store: ExpertConversationStore, request: ConversationContinueRequest) -> TurnLease:
    """Reserve one new logical turn under optimistic concurrency."""
    self = store
    request_hash = sha256_json(request.request_material())
    now = self._now()
    with self._transaction() as connection:
        existing = self._existing_idempotency(
            connection,
            owner_hash=request.owner_hash,
            scope_id=request.conversation_id,
            key_hash=request.idempotency_hash,
            request_hash=request_hash,
        )
        if existing is not None:
            return existing
        row = self._owned_row(connection, request.conversation_id, request.owner_hash)
        state = ConversationState(str(row["state"]))
        self._check_expired(row, now)
        if row["content_deleted_at"] is not None:
            raise ConversationError(ErrorCode.CONTENT_DELETED, "Conversation content has been deleted.")
        self._require_version(row, request.expected_version)
        if row["current_turn_id"] is not None:
            raise ConversationBusy(request.conversation_id, int(row["version"]), state)
        if state not in {ConversationState.OPEN, ConversationState.INPUT_REQUIRED}:
            raise _invalid_state(row, "The conversation does not accept a new turn.")
        pending_input = row["pending_input_request_id"]
        if state is ConversationState.INPUT_REQUIRED and request.input_request_id != pending_input:
            raise ConversationError(
                ErrorCode.INVALID_STATE,
                "The continuation does not match the pending input request.",
                conversation_id=request.conversation_id,
                current_version=int(row["version"]),
                state=state,
            )
        if state is ConversationState.OPEN and request.input_request_id is not None:
            raise ConversationError(
                ErrorCode.INVALID_STATE,
                "No input request is pending for this conversation.",
                conversation_id=request.conversation_id,
                current_version=int(row["version"]),
                state=state,
            )
        bounds = self._bounds(row)
        usage = self._usage(row)
        self._require_dispatch_capacity(row, include_new_turn=True)
        ordinal = int(row["turns_started"]) + 1
        turn_id = self._new_id("turn")
        attempt_id = self._new_id("attempt")
        request_content_id, message_hash = self._insert_content(
            connection,
            conversation_id=request.conversation_id,
            turn_id=turn_id,
            kind="turn_request",
            value=request.message,
            now=now,
        )
        bounded = self._build_context(connection, row, message=request.message, ordinal=ordinal)
        new_version = int(row["version"]) + 1
        usage["turns_started"] = ordinal
        remaining = remaining_capacity(bounds, usage)
        capacity = {"turn": TurnUsage().to_dict(), "remaining": remaining}
        trace = {
            "attempt_id": attempt_id,
            "consult_trace_id": None,
            "consult_lifecycle_trace_id": None,
        }
        connection.execute(
            """INSERT INTO conversation_turns
               (turn_id, conversation_id, ordinal, state, request_content_id,
                request_sha256, input_request_id, next_input_request_id, context_json,
                artifact_content_id, artifact_sha256, stop_reason, retryable,
                capacity_json, trace_json, attempt_count, created_at, updated_at)
               VALUES (?, ?, ?, 'running', ?, ?, ?, NULL, ?, NULL, NULL,
                       'running', 0, ?, ?, 1, ?, ?)""",
            (
                turn_id,
                request.conversation_id,
                ordinal,
                request_content_id,
                message_hash,
                request.input_request_id,
                self._json(bounded.lineage_payload()),
                self._json(capacity),
                self._json(trace),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        connection.execute(
            """INSERT INTO conversation_turn_attempts
               (attempt_id, turn_id, attempt_ordinal, state, lease_expires_at,
                started_at, completed_at)
               VALUES (?, ?, 1, 'running', ?, ?, NULL)""",
            (
                attempt_id,
                turn_id,
                lease_expiry(now, bounds, elapsed_ms=int(usage["elapsed_ms"])).isoformat(),
                now.isoformat(),
            ),
        )
        connection.execute(
            """UPDATE conversations
               SET state = 'open', version = ?, turns_started = ?,
                   current_turn_id = ?, latest_turn_id = ?,
                   pending_input_request_id = NULL, updated_at = ?
               WHERE conversation_id = ? AND version = ?""",
            (
                new_version,
                ordinal,
                turn_id,
                turn_id,
                now.isoformat(),
                request.conversation_id,
                request.expected_version,
            ),
        )
        connection.execute(
            """INSERT INTO conversation_idempotency
               (owner_hash, scope_id, idempotency_key_sha256, request_sha256,
                conversation_id, turn_id, attempt_id, status, result_version,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)""",
            (
                request.owner_hash,
                request.conversation_id,
                request.idempotency_hash,
                request_hash,
                request.conversation_id,
                turn_id,
                attempt_id,
                new_version,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        self._event(
            connection,
            event_id=self._new_id("evt"),
            row=row,
            event_type="turn_started",
            projection_version=new_version,
            previous_state=state,
            current_state=ConversationState.OPEN,
            now=now,
            turn_id=turn_id,
            attempt_id=attempt_id,
            reason_code="running",
            request_sha256=message_hash,
        )
        updated = self._owned_row(connection, request.conversation_id, request.owner_hash)
        return TurnLease(
            conversation_id=request.conversation_id,
            turn_id=turn_id,
            attempt_id=attempt_id,
            projection_version=new_version,
            dispatch_required=True,
            replayed=False,
            execution_context=self._execution_context(
                updated,
                turn_id=turn_id,
                attempt_id=attempt_id,
                message=request.message,
                bounded=bounded,
            ),
        )


def reserve_resume(store: ExpertConversationStore, request: ConversationResumeRequest) -> TurnLease:
    """Reserve a new attempt for the same waiting or interrupted turn."""
    self = store
    now = self._now()
    with self._transaction() as connection:
        row = self._owned_row(connection, request.conversation_id, request.owner_hash)
        prior_idempotency = connection.execute(
            """SELECT turn_id FROM conversation_idempotency
               WHERE owner_hash = ? AND scope_id = ? AND idempotency_key_sha256 = ?""",
            (request.owner_hash, request.conversation_id, request.idempotency_hash),
        ).fetchone()
        if prior_idempotency is not None:
            prior_turn_id = str(prior_idempotency["turn_id"])
            existing = self._existing_idempotency(
                connection,
                owner_hash=request.owner_hash,
                scope_id=request.conversation_id,
                key_hash=request.idempotency_hash,
                request_hash=sha256_json(request.request_material(prior_turn_id)),
            )
            if existing is None:
                raise ConversationError(ErrorCode.STORAGE_FAILED, "Idempotency index is inconsistent.")
            return existing
        current_turn_id = row["current_turn_id"]
        if current_turn_id is None:
            raise _invalid_state(row, "The conversation has no resumable turn.")
        turn = connection.execute(
            "SELECT * FROM conversation_turns WHERE turn_id = ?",
            (current_turn_id,),
        ).fetchone()
        if turn is None:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Current turn metadata is missing.")
        request_hash = sha256_json(request.request_material(str(current_turn_id)))
        self._check_expired(row, now)
        self._require_version(row, request.expected_version)
        turn_state = TurnState(str(turn["state"]))
        if turn_state not in _RESUMABLE_TURN_STATES:
            raise _invalid_state(row, "The current turn is not resumable.")
        if int(turn["attempt_count"]) >= MAX_ATTEMPTS_PER_TURN:
            raise ConversationError(
                ErrorCode.CAPACITY_EXHAUSTED,
                "The turn attempt ceiling is exhausted.",
                conversation_id=request.conversation_id,
                current_version=int(row["version"]),
                state=ConversationState(str(row["state"])),
            )
        if row["content_deleted_at"] is not None:
            raise ConversationError(ErrorCode.CONTENT_DELETED, "Conversation content has been deleted.")
        self._require_dispatch_capacity(row, include_new_turn=False)
        message = self._content_value(connection, str(turn["request_content_id"]))
        if not isinstance(message, str):
            raise ConversationError(ErrorCode.CONTENT_DELETED, "Turn request content has been deleted.")
        lineage = self._loads(str(turn["context_json"]))
        exact_turn_ids = tuple(str(item) for item in lineage["recent_turn_ids"])
        bounded = self._build_context(
            connection,
            row,
            message=message,
            ordinal=int(turn["ordinal"]),
            exact_turn_ids=exact_turn_ids,
        )
        if bounded.context_sha256 != lineage["context_sha256"]:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored turn context cannot be replayed exactly.")
        attempt_id = self._new_id("attempt")
        attempt_ordinal = int(turn["attempt_count"]) + 1
        new_version = int(row["version"]) + 1
        bounds = self._bounds(row)
        usage = self._usage(row)
        trace = {
            "attempt_id": attempt_id,
            "consult_trace_id": None,
            "consult_lifecycle_trace_id": None,
        }
        connection.execute(
            """INSERT INTO conversation_turn_attempts
               (attempt_id, turn_id, attempt_ordinal, state, lease_expires_at,
                started_at, completed_at)
               VALUES (?, ?, ?, 'running', ?, ?, NULL)""",
            (
                attempt_id,
                current_turn_id,
                attempt_ordinal,
                lease_expiry(now, bounds, elapsed_ms=int(usage["elapsed_ms"])).isoformat(),
                now.isoformat(),
            ),
        )
        connection.execute(
            """UPDATE conversation_turns
               SET state = 'running', stop_reason = 'running', retryable = 0,
                   trace_json = ?, attempt_count = ?, updated_at = ?
               WHERE turn_id = ?""",
            (self._json(trace), attempt_ordinal, now.isoformat(), current_turn_id),
        )
        prior_state = ConversationState(str(row["state"]))
        connection.execute(
            """UPDATE conversations SET state = 'open', version = ?, updated_at = ?
               WHERE conversation_id = ? AND version = ?""",
            (new_version, now.isoformat(), request.conversation_id, request.expected_version),
        )
        connection.execute(
            """INSERT INTO conversation_idempotency
               (owner_hash, scope_id, idempotency_key_sha256, request_sha256,
                conversation_id, turn_id, attempt_id, status, result_version,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?)""",
            (
                request.owner_hash,
                request.conversation_id,
                request.idempotency_hash,
                request_hash,
                request.conversation_id,
                current_turn_id,
                attempt_id,
                new_version,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        self._event(
            connection,
            event_id=self._new_id("evt"),
            row=row,
            event_type="turn_resumed",
            projection_version=new_version,
            previous_state=prior_state,
            current_state=ConversationState.OPEN,
            now=now,
            turn_id=str(current_turn_id),
            attempt_id=attempt_id,
            reason_code="resumed",
            request_sha256=str(turn["request_sha256"]),
        )
        updated = self._owned_row(connection, request.conversation_id, request.owner_hash)
        return TurnLease(
            conversation_id=request.conversation_id,
            turn_id=str(current_turn_id),
            attempt_id=attempt_id,
            projection_version=new_version,
            dispatch_required=True,
            replayed=False,
            execution_context=self._execution_context(
                updated,
                turn_id=str(current_turn_id),
                attempt_id=attempt_id,
                message=message,
                bounded=bounded,
            ),
        )


def _invalid_state(row: sqlite3.Row, message: str) -> ConversationError:
    return ConversationError(
        ErrorCode.INVALID_STATE,
        message,
        conversation_id=str(row["conversation_id"]),
        current_version=int(row["version"]),
        state=ConversationState(str(row["state"])),
    )
