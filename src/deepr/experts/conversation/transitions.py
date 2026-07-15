"""Post-reservation state transitions and read models for conversations."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from deepr.experts.conversation.models import (
    CONVERSATION_KIND,
    CONVERSATION_SCHEMA_VERSION,
    EVENT_KIND,
    EVENT_SCHEMA_VERSION,
    HOST_ACTION_BOUNDARY,
    TURN_KIND,
    TURN_SCHEMA_VERSION,
    ConversationError,
    ConversationNotFound,
    ConversationOperationResult,
    ConversationState,
    ErrorCode,
    TurnExecutionResult,
    TurnLease,
    TurnState,
    TurnUsage,
    owner_binding_sha256,
    parse_datetime,
    remaining_capacity,
)

if TYPE_CHECKING:
    from deepr.experts.conversation.store import ExpertConversationStore

_COMPLETED = {TurnState.COMPLETED, TurnState.INPUT_REQUIRED}
_ACTIVE = {TurnState.RUNNING, TurnState.WAITING_CAPACITY, TurnState.INTERRUPTED}
_TERMINAL_CONVERSATIONS = {
    ConversationState.CLOSED,
    ConversationState.EXPIRED,
    ConversationState.CANCELLED,
    ConversationState.FAILED,
}


def _conversation_payload(store: ExpertConversationStore, row: sqlite3.Row) -> dict[str, Any]:
    return {
        "schema_version": CONVERSATION_SCHEMA_VERSION,
        "kind": CONVERSATION_KIND,
        "conversation_id": row["conversation_id"],
        "state": row["state"],
        "version": int(row["version"]),
        "mode": row["mode"],
        "expert_names": store._loads(str(row["expert_names_json"])),
        "context_snapshot_id": row["snapshot_id"],
        "backend": store._loads(str(row["backend_json"])),
        "bounds": store._loads(str(row["bounds_json"])),
        "usage": store._usage(row),
        "retention": {
            "retention_days": int(row["retention_days"]),
            "expires_at": row["expires_at"],
            "content_deleted": row["content_deleted_at"] is not None,
            "content_deleted_at": row["content_deleted_at"],
        },
        "current_turn_id": row["current_turn_id"],
        "latest_turn_id": row["latest_turn_id"],
        "pending_input_request_id": row["pending_input_request_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "host_action_boundary": HOST_ACTION_BOUNDARY,
    }


def _turn_payload(
    store: ExpertConversationStore,
    connection: sqlite3.Connection,
    turn: sqlite3.Row,
) -> dict[str, Any]:
    request = store._content_value(connection, str(turn["request_content_id"]))
    artifact = store._content_value(connection, turn["artifact_content_id"])
    return {
        "schema_version": TURN_SCHEMA_VERSION,
        "kind": TURN_KIND,
        "conversation_id": turn["conversation_id"],
        "turn_id": turn["turn_id"],
        "ordinal": int(turn["ordinal"]),
        "state": turn["state"],
        "attempt_count": int(turn["attempt_count"]),
        "request": {
            "content_available": isinstance(request, str),
            "content": request if isinstance(request, str) else None,
            "content_sha256": turn["request_sha256"],
            "input_request_id": turn["input_request_id"],
        },
        "context": store._loads(str(turn["context_json"])),
        "artifact_available": isinstance(artifact, dict),
        "artifact": artifact if isinstance(artifact, dict) else None,
        "artifact_sha256": turn["artifact_sha256"],
        "stop": {"reason": turn["stop_reason"], "retryable": bool(turn["retryable"])},
        "capacity": store._loads(str(turn["capacity_json"])),
        "trace": store._loads(str(turn["trace_json"])),
        "created_at": turn["created_at"],
        "updated_at": turn["updated_at"],
    }


def _bundle(
    store: ExpertConversationStore,
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    turn_id: str | None,
    replayed: bool,
    dispatch_status: str | None = None,
) -> ConversationOperationResult:
    turn: sqlite3.Row | None = None
    selected_turn_id = turn_id or row["latest_turn_id"]
    if selected_turn_id is not None:
        turn = connection.execute(
            "SELECT * FROM conversation_turns WHERE turn_id = ? AND conversation_id = ?",
            (selected_turn_id, row["conversation_id"]),
        ).fetchone()
        if turn_id is not None and turn is None:
            raise ConversationError(ErrorCode.NOT_FOUND, "Conversation turn not found.")
    return ConversationOperationResult(
        conversation=_conversation_payload(store, row),
        turn=_turn_payload(store, connection, turn) if turn is not None else None,
        replayed=replayed,
        dispatch_status=dispatch_status or (str(turn["state"]) if turn is not None else str(row["state"])),
    )


def get_operation(
    store: ExpertConversationStore,
    *,
    owner_id: str,
    conversation_id: str,
    turn_id: str | None = None,
    replayed: bool = False,
) -> ConversationOperationResult:
    expire_due(store, conversation_id=conversation_id)
    with store._reader() as connection:
        row = store._owned_row(connection, conversation_id, owner_binding_sha256(owner_id))
        return _bundle(store, connection, row, turn_id=turn_id, replayed=replayed)


def get_snapshot(
    store: ExpertConversationStore,
    *,
    owner_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    expire_due(store, conversation_id=conversation_id)
    with store._reader() as connection:
        row = store._owned_row(connection, conversation_id, owner_binding_sha256(owner_id))
        return store._snapshot_payload(connection, row)


def _usage_with_result(row: sqlite3.Row, result: TurnExecutionResult) -> dict[str, int | float]:
    usage = {
        "turns_started": int(row["turns_started"]),
        "turns_completed": int(row["turns_completed"]),
        "model_calls": int(row["model_calls"]) + result.usage.model_calls,
        "input_tokens": int(row["input_tokens"]) + result.usage.input_tokens,
        "output_tokens": int(row["output_tokens"]) + result.usage.output_tokens,
        "elapsed_ms": int(row["elapsed_ms"]) + result.usage.elapsed_ms,
        "cost_usd": float(row["cost_usd"]) + float(result.usage.cost_usd),
    }
    if result.state in _COMPLETED:
        usage["turns_completed"] = int(usage["turns_completed"]) + 1
    return usage


def _usage_within_bounds(store: ExpertConversationStore, row: sqlite3.Row, result: TurnExecutionResult) -> bool:
    bounds = store._bounds(row)
    backend = store._backend(row)
    usage = _usage_with_result(row, result)
    if result.state is TurnState.WAITING_CAPACITY and result.usage.to_dict() != _zero_usage():
        return False
    return (
        (backend.capacity_source != "local_owned" or float(result.usage.cost_usd) == 0.0)
        and int(usage["model_calls"]) <= bounds.max_model_calls
        and int(usage["input_tokens"]) <= bounds.max_input_tokens
        and int(usage["output_tokens"]) <= bounds.max_output_tokens
        and int(usage["elapsed_ms"]) <= bounds.max_elapsed_seconds * 1000
        and float(usage["cost_usd"]) <= float(bounds.max_cost_usd)
    )


def _cumulative_turn_usage(
    store: ExpertConversationStore,
    turn: sqlite3.Row,
    current_usage: TurnUsage,
) -> dict[str, int | float]:
    prior = store._loads(str(turn["capacity_json"]))
    if not isinstance(prior, dict) or not isinstance(prior.get("turn"), dict):
        raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored turn capacity is invalid.")
    turn_usage = dict(prior["turn"])
    current = current_usage.to_dict()
    try:
        for key in ("model_calls", "input_tokens", "output_tokens", "elapsed_ms"):
            turn_usage[key] = int(turn_usage[key]) + int(current[key])
        turn_usage["cost_usd"] = float(turn_usage["cost_usd"]) + float(current["cost_usd"])
        return TurnUsage(**turn_usage).to_dict()
    except (KeyError, TypeError, ValueError, ConversationError) as exc:
        raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored turn capacity is invalid.") from exc


def finalize_turn(
    store: ExpertConversationStore,
    lease: TurnLease,
    result: TurnExecutionResult,
) -> ConversationOperationResult:
    """Commit one executor result only while its exact attempt still owns the turn."""
    now = store._now()
    with store._transaction() as connection:
        row = connection.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (lease.conversation_id,),
        ).fetchone()
        turn = connection.execute(
            "SELECT * FROM conversation_turns WHERE turn_id = ? AND conversation_id = ?",
            (lease.turn_id, lease.conversation_id),
        ).fetchone()
        attempt = connection.execute(
            "SELECT * FROM conversation_turn_attempts WHERE attempt_id = ? AND turn_id = ?",
            (lease.attempt_id, lease.turn_id),
        ).fetchone()
        if row is None or turn is None or attempt is None:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Reserved conversation turn metadata is missing.")
        if (
            attempt["state"] != "running"
            or turn["state"] != "running"
            or row["current_turn_id"] != lease.turn_id
            or store._loads(str(turn["trace_json"]))["attempt_id"] != lease.attempt_id
        ):
            return _bundle(
                store,
                connection,
                row,
                turn_id=lease.turn_id,
                replayed=True,
                dispatch_status="stale_attempt_ignored",
            )
        try:
            attempt_expired = parse_datetime(str(attempt["lease_expires_at"])) <= now
        except ConversationError as exc:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored attempt lease is invalid.") from exc
        if attempt_expired:
            updated = _interrupt_expired_attempt(store, connection, row, turn, attempt, now=now)
            return _bundle(
                store,
                connection,
                updated,
                turn_id=lease.turn_id,
                replayed=True,
                dispatch_status="lease_expired_result_ignored",
            )

        if not _usage_within_bounds(store, row, result):
            result = TurnExecutionResult(
                state=TurnState.VERIFIER_FAILED,
                stop_reason="verifier_failed",
                retryable=False,
                usage=result.usage,
                consult_trace_id=result.consult_trace_id,
                consult_lifecycle_trace_id=result.consult_lifecycle_trace_id,
            )

        artifact_content_id: str | None = None
        artifact_sha256: str | None = None
        if result.artifact is not None:
            artifact_content_id, artifact_sha256 = store._insert_content(
                connection,
                conversation_id=lease.conversation_id,
                turn_id=lease.turn_id,
                kind="turn_artifact",
                value=result.artifact,
                now=now,
            )

        previous_state = ConversationState(str(row["state"]))
        conversation_state, current_turn_id, pending_input_request_id = _projection_for_result(
            store, result, lease.turn_id
        )
        new_version = int(row["version"]) + 1
        usage = _usage_with_result(row, result)
        bounds = store._bounds(row)
        capacity = {
            "turn": _cumulative_turn_usage(store, turn, result.usage),
            "remaining": remaining_capacity(bounds, usage),
        }
        trace = {
            "attempt_id": lease.attempt_id,
            "consult_trace_id": result.consult_trace_id,
            "consult_lifecycle_trace_id": result.consult_lifecycle_trace_id,
        }
        connection.execute(
            """UPDATE conversation_turns
               SET state = ?, next_input_request_id = ?, artifact_content_id = ?,
                   artifact_sha256 = ?, stop_reason = ?, retryable = ?,
                   capacity_json = ?, trace_json = ?, updated_at = ?
               WHERE turn_id = ?""",
            (
                result.state.value,
                pending_input_request_id,
                artifact_content_id,
                artifact_sha256,
                result.stop_reason,
                int(result.retryable),
                store._json(capacity),
                store._json(trace),
                now.isoformat(),
                lease.turn_id,
            ),
        )
        connection.execute(
            """UPDATE conversation_turn_attempts
               SET state = ?, consult_trace_id = ?, consult_lifecycle_trace_id = ?,
                   completed_at = ? WHERE attempt_id = ?""",
            (
                result.state.value,
                result.consult_trace_id,
                result.consult_lifecycle_trace_id,
                now.isoformat(),
                lease.attempt_id,
            ),
        )
        connection.execute(
            """UPDATE conversations
               SET state = ?, version = ?, turns_completed = ?, model_calls = ?,
                   input_tokens = ?, output_tokens = ?, elapsed_ms = ?, cost_usd = ?,
                   current_turn_id = ?, pending_input_request_id = ?, updated_at = ?
               WHERE conversation_id = ?""",
            (
                conversation_state.value,
                new_version,
                usage["turns_completed"],
                usage["model_calls"],
                usage["input_tokens"],
                usage["output_tokens"],
                usage["elapsed_ms"],
                usage["cost_usd"],
                current_turn_id,
                pending_input_request_id,
                now.isoformat(),
                lease.conversation_id,
            ),
        )
        connection.execute(
            """UPDATE conversation_idempotency
               SET status = ?, result_version = ?, updated_at = ?
               WHERE attempt_id = ?""",
            (result.state.value, new_version, now.isoformat(), lease.attempt_id),
        )
        store._event(
            connection,
            event_id=store._new_id("evt"),
            row=row,
            event_type=_event_type_for_result(result.state),
            projection_version=new_version,
            previous_state=previous_state,
            current_state=conversation_state,
            now=now,
            turn_id=lease.turn_id,
            attempt_id=lease.attempt_id,
            reason_code=result.stop_reason,
            request_sha256=str(turn["request_sha256"]),
            artifact_sha256=artifact_sha256,
        )
        updated = connection.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (lease.conversation_id,),
        ).fetchone()
        if updated is None:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Conversation projection disappeared.")
        return _bundle(store, connection, updated, turn_id=lease.turn_id, replayed=False)


def record_executor_failure(
    store: ExpertConversationStore,
    lease: TurnLease,
    *,
    cancelled: bool = False,
    usage: TurnUsage | None = None,
) -> ConversationOperationResult:
    state = TurnState.CANCELLED if cancelled else TurnState.FAILED
    return finalize_turn(
        store,
        lease,
        TurnExecutionResult(state=state, stop_reason=state.value, retryable=False, usage=usage or TurnUsage()),
    )


def _projection_for_result(
    store: ExpertConversationStore,
    result: TurnExecutionResult,
    turn_id: str,
) -> tuple[ConversationState, str | None, str | None]:
    if result.state is TurnState.COMPLETED:
        return ConversationState.OPEN, None, None
    if result.state is TurnState.INPUT_REQUIRED:
        return ConversationState.INPUT_REQUIRED, None, store._new_id("input")
    if result.state is TurnState.WAITING_CAPACITY:
        return ConversationState.WAITING_CAPACITY, turn_id, None
    if result.state is TurnState.CANCELLED:
        return ConversationState.CANCELLED, None, None
    return ConversationState.FAILED, None, None


def _event_type_for_result(state: TurnState) -> str:
    return {
        TurnState.COMPLETED: "turn_completed",
        TurnState.INPUT_REQUIRED: "turn_input_required",
        TurnState.WAITING_CAPACITY: "turn_waiting_capacity",
        TurnState.CANCELLED: "turn_cancelled",
        TurnState.BUDGET_EXHAUSTED: "turn_budget_exhausted",
        TurnState.VERIFIER_FAILED: "turn_verifier_failed",
        TurnState.FAILED: "turn_failed",
    }[state]


def close_conversation(
    store: ExpertConversationStore,
    *,
    owner_id: str,
    conversation_id: str,
    expected_version: int,
) -> ConversationOperationResult:
    now = store._now()
    with store._transaction() as connection:
        row = store._owned_row(connection, conversation_id, owner_binding_sha256(owner_id))
        state = ConversationState(str(row["state"]))
        if state is ConversationState.CLOSED:
            return _bundle(store, connection, row, turn_id=None, replayed=True)
        store._require_version(row, expected_version)
        if row["current_turn_id"] is not None:
            raise ConversationError(
                ErrorCode.CONVERSATION_BUSY,
                "The active turn must finish or be cancelled before close.",
                retryable=True,
                conversation_id=conversation_id,
                current_version=int(row["version"]),
                state=state,
            )
        if state in _TERMINAL_CONVERSATIONS:
            raise ConversationError(
                ErrorCode.INVALID_STATE,
                "The conversation is already terminal.",
                conversation_id=conversation_id,
                current_version=int(row["version"]),
                state=state,
            )
        version = int(row["version"]) + 1
        connection.execute(
            """UPDATE conversations
               SET state = 'closed', version = ?, pending_input_request_id = NULL, updated_at = ?
               WHERE conversation_id = ?""",
            (version, now.isoformat(), conversation_id),
        )
        store._event(
            connection,
            event_id=store._new_id("evt"),
            row=row,
            event_type="conversation_closed",
            projection_version=version,
            previous_state=state,
            current_state=ConversationState.CLOSED,
            reason_code="closed",
            now=now,
        )
        updated = store._owned_row(connection, conversation_id, owner_binding_sha256(owner_id))
        return _bundle(store, connection, updated, turn_id=None, replayed=False)


def delete_content(
    store: ExpertConversationStore,
    *,
    owner_id: str,
    conversation_id: str,
    expected_version: int,
) -> ConversationOperationResult:
    now = store._now()
    with store._transaction() as connection:
        row = store._owned_row(connection, conversation_id, owner_binding_sha256(owner_id))
        if row["content_deleted_at"] is not None:
            return _bundle(store, connection, row, turn_id=None, replayed=True)
        store._require_version(row, expected_version)
        if row["current_turn_id"] is not None:
            raise ConversationError(
                ErrorCode.CONVERSATION_BUSY,
                "The active turn must finish or be cancelled before deleting content.",
                retryable=True,
                conversation_id=conversation_id,
                current_version=int(row["version"]),
                state=ConversationState(str(row["state"])),
            )
        prior_state = ConversationState(str(row["state"]))
        version = int(row["version"]) + 1
        _purge_content(connection, conversation_id, now)
        connection.execute(
            """UPDATE conversations
               SET state = 'closed', version = ?, content_deleted_at = ?,
                   pending_input_request_id = NULL, updated_at = ?
               WHERE conversation_id = ?""",
            (version, now.isoformat(), now.isoformat(), conversation_id),
        )
        store._event(
            connection,
            event_id=store._new_id("evt"),
            row=row,
            event_type="content_deleted",
            projection_version=version,
            previous_state=prior_state,
            current_state=ConversationState.CLOSED,
            reason_code="content_deleted",
            content_retained=False,
            now=now,
        )
        updated = store._owned_row(connection, conversation_id, owner_binding_sha256(owner_id))
        result = _bundle(store, connection, updated, turn_id=None, replayed=False)
    _truncate_wal(store)
    return result


def _interrupt_expired_attempt(
    store: ExpertConversationStore,
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    turn: sqlite3.Row,
    attempt: sqlite3.Row,
    *,
    now: datetime,
) -> sqlite3.Row:
    """Revoke an expired attempt and charge one conservative ambiguous call."""
    version = int(row["version"]) + 1
    usage = store._usage(row)
    usage["model_calls"] = int(usage["model_calls"]) + 1
    bounds = store._bounds(row)
    capacity = {
        "turn": _cumulative_turn_usage(store, turn, TurnUsage(model_calls=1)),
        "remaining": remaining_capacity(bounds, usage),
    }
    connection.execute(
        """UPDATE conversation_turn_attempts
           SET state = 'interrupted', error_code = 'lease_expired', completed_at = ?
           WHERE attempt_id = ? AND state = 'running'""",
        (now.isoformat(), attempt["attempt_id"]),
    )
    connection.execute(
        """UPDATE conversation_turns
           SET state = 'interrupted', stop_reason = 'interrupted', retryable = 1,
               capacity_json = ?, updated_at = ?
           WHERE turn_id = ?""",
        (store._json(capacity), now.isoformat(), turn["turn_id"]),
    )
    connection.execute(
        """UPDATE conversations
           SET state = 'waiting_capacity', version = ?, model_calls = ?, updated_at = ?
           WHERE conversation_id = ?""",
        (version, usage["model_calls"], now.isoformat(), row["conversation_id"]),
    )
    connection.execute(
        """UPDATE conversation_idempotency
           SET status = 'interrupted', result_version = ?, updated_at = ?
           WHERE attempt_id = ?""",
        (version, now.isoformat(), attempt["attempt_id"]),
    )
    store._event(
        connection,
        event_id=store._new_id("evt"),
        row=row,
        event_type="turn_interrupted",
        projection_version=version,
        previous_state=ConversationState(str(row["state"])),
        current_state=ConversationState.WAITING_CAPACITY,
        reason_code="lease_expired",
        turn_id=str(turn["turn_id"]),
        attempt_id=str(attempt["attempt_id"]),
        request_sha256=str(turn["request_sha256"]),
        now=now,
    )
    updated = connection.execute(
        "SELECT * FROM conversations WHERE conversation_id = ?",
        (row["conversation_id"],),
    ).fetchone()
    if updated is None:
        raise ConversationError(ErrorCode.STORAGE_FAILED, "Conversation projection disappeared.")
    return cast(sqlite3.Row, updated)


def recover_expired_leases(store: ExpertConversationStore) -> int:
    """Mark attempts interrupted only after their durable lease has expired."""
    now = store._now()
    recovered = 0
    with store._transaction() as connection:
        rows = connection.execute(
            """SELECT a.attempt_id, a.turn_id, t.conversation_id
               FROM conversation_turn_attempts a
               JOIN conversation_turns t ON t.turn_id = a.turn_id
               JOIN conversations c ON c.conversation_id = t.conversation_id
               WHERE a.state = 'running' AND a.lease_expires_at <= ?
                 AND t.state = 'running' AND c.current_turn_id = t.turn_id""",
            (now.isoformat(),),
        ).fetchall()
        for item in rows:
            row = connection.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?",
                (item["conversation_id"],),
            ).fetchone()
            turn = connection.execute(
                "SELECT * FROM conversation_turns WHERE turn_id = ?",
                (item["turn_id"],),
            ).fetchone()
            attempt = connection.execute(
                "SELECT * FROM conversation_turn_attempts WHERE attempt_id = ?",
                (item["attempt_id"],),
            ).fetchone()
            if row is None or turn is None or attempt is None:
                raise ConversationError(ErrorCode.STORAGE_FAILED, "Running attempt metadata is missing.")
            if attempt["state"] != "running" or turn["state"] != "running" or row["current_turn_id"] != turn["turn_id"]:
                continue
            _interrupt_expired_attempt(store, connection, row, turn, attempt, now=now)
            recovered += 1
    return recovered


def expire_due(store: ExpertConversationStore, *, conversation_id: str | None = None) -> int:
    recover_expired_leases(store)
    now = store._now()
    expired = 0
    with store._transaction() as connection:
        query = "SELECT * FROM conversations WHERE expires_at <= ? AND content_deleted_at IS NULL"
        params: tuple[Any, ...] = (now.isoformat(),)
        if conversation_id is not None:
            query += " AND conversation_id = ?"
            params = (now.isoformat(), conversation_id)
        rows = connection.execute(query, params).fetchall()
        for row in rows:
            current_turn_id = row["current_turn_id"]
            if current_turn_id is not None:
                turn = connection.execute(
                    "SELECT * FROM conversation_turns WHERE turn_id = ?",
                    (current_turn_id,),
                ).fetchone()
                if turn is not None and turn["state"] == "running":
                    continue
                if turn is not None:
                    connection.execute(
                        """UPDATE conversation_turns
                           SET state = 'cancelled', stop_reason = 'cancelled', retryable = 0, updated_at = ?
                           WHERE turn_id = ?""",
                        (now.isoformat(), current_turn_id),
                    )
            version = int(row["version"]) + 1
            _purge_content(connection, str(row["conversation_id"]), now)
            connection.execute(
                """UPDATE conversations
                   SET state = 'expired', version = ?, content_deleted_at = ?,
                       current_turn_id = NULL, pending_input_request_id = NULL, updated_at = ?
                   WHERE conversation_id = ?""",
                (version, now.isoformat(), now.isoformat(), row["conversation_id"]),
            )
            connection.execute(
                """UPDATE conversation_idempotency
                   SET status = 'expired', result_version = ?, updated_at = ?
                   WHERE conversation_id = ?""",
                (version, now.isoformat(), row["conversation_id"]),
            )
            store._event(
                connection,
                event_id=store._new_id("evt"),
                row=row,
                event_type="conversation_expired",
                projection_version=version,
                previous_state=ConversationState(str(row["state"])),
                current_state=ConversationState.EXPIRED,
                reason_code="retention_expired",
                content_retained=False,
                now=now,
            )
            expired += 1
    if expired:
        _truncate_wal(store)
    return expired


def list_events(
    store: ExpertConversationStore,
    *,
    owner_id: str,
    conversation_id: str,
) -> list[dict[str, Any]]:
    with store._reader() as connection:
        store._owned_row(connection, conversation_id, owner_binding_sha256(owner_id))
        rows = connection.execute(
            "SELECT * FROM conversation_events WHERE conversation_id = ? ORDER BY sequence",
            (conversation_id,),
        ).fetchall()
        return [
            {
                "schema_version": EVENT_SCHEMA_VERSION,
                "kind": EVENT_KIND,
                "event_id": row["event_id"],
                "conversation_id": row["conversation_id"],
                "sequence": int(row["sequence"]),
                "projection_version": int(row["projection_version"]),
                "event_type": row["event_type"],
                "turn_id": row["turn_id"],
                "attempt_id": row["attempt_id"],
                "previous_state": row["previous_state"],
                "current_state": row["current_state"],
                "reason_code": row["reason_code"],
                "request_sha256": row["request_sha256"],
                "artifact_sha256": row["artifact_sha256"],
                "owner_binding_sha256": row["owner_binding_sha256"],
                "content_retained": bool(row["content_retained"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]


def verify_projection(store: ExpertConversationStore, conversation_id: str) -> dict[str, Any]:
    with store._reader() as connection:
        row = connection.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise ConversationNotFound()
        expected = _derive_projection(store, connection, row)
        actual = {key: row[key] for key in expected}
        return {
            "conversation_id": conversation_id,
            "matches": actual == expected,
            "actual": actual,
            "expected": expected,
        }


def rebuild_projection(store: ExpertConversationStore, conversation_id: str) -> dict[str, Any]:
    with store._transaction() as connection:
        row = connection.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise ConversationNotFound()
        expected = _derive_projection(store, connection, row)
        assignments = ", ".join(f"{key} = ?" for key in expected)
        connection.execute(
            f"UPDATE conversations SET {assignments} WHERE conversation_id = ?",  # noqa: S608 - fixed internal keys
            (*expected.values(), conversation_id),
        )
    return verify_projection(store, conversation_id)


def quick_check(store: ExpertConversationStore) -> str:
    with store._reader() as connection:
        return str(connection.execute("PRAGMA quick_check").fetchone()[0])


def _derive_projection(
    store: ExpertConversationStore,
    connection: sqlite3.Connection,
    row: sqlite3.Row,
) -> dict[str, Any]:
    latest_event = connection.execute(
        "SELECT * FROM conversation_events WHERE conversation_id = ? ORDER BY sequence DESC LIMIT 1",
        (row["conversation_id"],),
    ).fetchone()
    if latest_event is None:
        raise ConversationError(ErrorCode.STORAGE_FAILED, "Conversation event history is empty.")
    turns = connection.execute(
        "SELECT * FROM conversation_turns WHERE conversation_id = ? ORDER BY ordinal",
        (row["conversation_id"],),
    ).fetchall()
    usage = {
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "elapsed_ms": 0,
        "cost_usd": 0.0,
    }
    for turn in turns:
        turn_usage = store._loads(str(turn["capacity_json"]))["turn"]
        for key in usage:
            usage[key] += turn_usage[key]
    latest_turn = turns[-1] if turns else None
    current_turn_id = None
    if latest_turn is not None and TurnState(str(latest_turn["state"])) in _ACTIVE:
        current_turn_id = latest_turn["turn_id"]
    deletion_event = connection.execute(
        """SELECT created_at FROM conversation_events
           WHERE conversation_id = ? AND content_retained = 0
           ORDER BY sequence LIMIT 1""",
        (row["conversation_id"],),
    ).fetchone()
    return {
        "state": latest_event["current_state"],
        "version": int(latest_event["projection_version"]),
        "turns_started": len(turns),
        "turns_completed": sum(TurnState(str(turn["state"])) in _COMPLETED for turn in turns),
        "model_calls": int(usage["model_calls"]),
        "input_tokens": int(usage["input_tokens"]),
        "output_tokens": int(usage["output_tokens"]),
        "elapsed_ms": int(usage["elapsed_ms"]),
        "cost_usd": float(usage["cost_usd"]),
        "content_deleted_at": deletion_event["created_at"] if deletion_event is not None else None,
        "current_turn_id": current_turn_id,
        "latest_turn_id": latest_turn["turn_id"] if latest_turn is not None else None,
        "pending_input_request_id": (
            latest_turn["next_input_request_id"]
            if latest_turn is not None and latest_turn["state"] == "input_required"
            else None
        ),
        "updated_at": latest_event["created_at"],
    }


def _purge_content(connection: sqlite3.Connection, conversation_id: str, now: datetime) -> None:
    connection.execute(
        """UPDATE conversation_contents
           SET content_json = NULL, deleted_at = ?
           WHERE conversation_id = ? AND content_json IS NOT NULL""",
        (now.isoformat(), conversation_id),
    )


def _truncate_wal(store: ExpertConversationStore) -> None:
    connection: sqlite3.Connection | None = None
    try:
        connection = store._connect()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        # Logical deletion is already committed. A busy reader can delay the
        # physical WAL checkpoint without restoring application-level access.
        return
    finally:
        if connection is not None:
            connection.close()


def _zero_usage() -> dict[str, int | float]:
    return {"model_calls": 0, "input_tokens": 0, "output_tokens": 0, "elapsed_ms": 0, "cost_usd": 0.0}
