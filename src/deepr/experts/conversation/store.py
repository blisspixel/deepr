"""SQLite event and projection store for durable expert conversations."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import deepr.experts.conversation.reservations as conversation_reservations
import deepr.experts.conversation.transitions as conversation_transitions
from deepr.config import runtime_data_path
from deepr.experts.conversation.context import BoundedTurnContext, build_bounded_turn_context
from deepr.experts.conversation.database import connect_database, initialize_database, reader, transaction
from deepr.experts.conversation.models import (
    SNAPSHOT_KIND,
    SNAPSHOT_SCHEMA_VERSION,
    BackendSelection,
    ConsultationMode,
    ConversationBounds,
    ConversationContinueRequest,
    ConversationError,
    ConversationExecutionContext,
    ConversationNotFound,
    ConversationOperationResult,
    ConversationResumeRequest,
    ConversationStartRequest,
    ConversationState,
    ErrorCode,
    IdempotencyConflict,
    TurnExecutionResult,
    TurnLease,
    TurnUsage,
    VersionConflict,
    canonical_json,
    new_opaque_id,
    parse_datetime,
    remaining_capacity,
    require_utc,
    sha256_json,
    utc_now,
    utf8_size,
)


class ExpertConversationStore:
    """Durable protocol-neutral state with short explicit transactions."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[str], str] = new_opaque_id,
        busy_timeout_ms: int = 5_000,
    ) -> None:
        self.path = Path(path) if path is not None else runtime_data_path("expert_conversations", "conversations.db")
        self._clock = clock
        self._id_factory = id_factory
        self._busy_timeout_ms = busy_timeout_ms
        initialize_database(self.path, busy_timeout_ms=busy_timeout_ms)

    def _connect(self) -> sqlite3.Connection:
        return connect_database(self.path, busy_timeout_ms=self._busy_timeout_ms)

    def _transaction(self) -> AbstractContextManager[sqlite3.Connection]:
        return transaction(self.path, busy_timeout_ms=self._busy_timeout_ms)

    def _reader(self) -> AbstractContextManager[sqlite3.Connection]:
        return reader(self.path, busy_timeout_ms=self._busy_timeout_ms)

    def _new_id(self, prefix: str) -> str:
        return self._id_factory(prefix)

    def _now(self) -> datetime:
        return require_utc(self._clock())

    @staticmethod
    def _json(value: Any) -> str:
        return canonical_json(value)

    @staticmethod
    def _loads(value: str) -> Any:
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored conversation data is invalid.") from exc

    def _insert_content(
        self,
        connection: sqlite3.Connection,
        *,
        conversation_id: str,
        turn_id: str | None,
        kind: str,
        value: Any,
        now: datetime,
    ) -> tuple[str, str]:
        content_id = self._new_id("content")
        encoded = self._json(value)
        digest = sha256_json(value)
        connection.execute(
            """INSERT INTO conversation_contents
               (content_id, conversation_id, turn_id, content_kind, content_json,
                content_sha256, byte_count, created_at, deleted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
            (content_id, conversation_id, turn_id, kind, encoded, digest, utf8_size(encoded), now.isoformat()),
        )
        return content_id, digest

    @staticmethod
    def _content_value(connection: sqlite3.Connection, content_id: str | None) -> Any | None:
        if content_id is None:
            return None
        row = connection.execute(
            """SELECT content_json, content_sha256, byte_count, deleted_at
               FROM conversation_contents WHERE content_id = ?""",
            (content_id,),
        ).fetchone()
        if row is None:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored conversation content metadata is missing.")
        if row["content_json"] is None:
            if row["deleted_at"] is None:
                raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored conversation content is incomplete.")
            return None
        value = ExpertConversationStore._loads(str(row["content_json"]))
        try:
            encoded = canonical_json(value)
            digest = sha256_json(value)
        except ConversationError as exc:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored conversation content is invalid.") from exc
        try:
            byte_count = int(row["byte_count"])
        except (TypeError, ValueError) as exc:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored conversation content is invalid.") from exc
        if digest != row["content_sha256"] or utf8_size(encoded) != byte_count:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored conversation content failed integrity checks.")
        return value

    @staticmethod
    def _owned_row(
        connection: sqlite3.Connection,
        conversation_id: str,
        owner_hash: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM conversations WHERE conversation_id = ? AND owner_hash = ?",
            (conversation_id, owner_hash),
        ).fetchone()
        if row is None:
            raise ConversationNotFound()
        return cast(sqlite3.Row, row)

    @staticmethod
    def _usage(row: sqlite3.Row) -> dict[str, int | float]:
        return {
            "turns_started": int(row["turns_started"]),
            "turns_completed": int(row["turns_completed"]),
            "model_calls": int(row["model_calls"]),
            "input_tokens": int(row["input_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "elapsed_ms": int(row["elapsed_ms"]),
            "cost_usd": float(row["cost_usd"]),
        }

    @staticmethod
    def _bounds(row: sqlite3.Row) -> ConversationBounds:
        try:
            return ConversationBounds.from_dict(ExpertConversationStore._loads(str(row["bounds_json"])))
        except ConversationError as exc:
            if exc.code is ErrorCode.STORAGE_FAILED:
                raise
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored conversation bounds are invalid.") from exc

    @staticmethod
    def _backend(row: sqlite3.Row) -> BackendSelection:
        try:
            return BackendSelection.from_dict(ExpertConversationStore._loads(str(row["backend_json"])))
        except ConversationError as exc:
            if exc.code is ErrorCode.STORAGE_FAILED:
                raise
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored conversation backend is invalid.") from exc

    @staticmethod
    def _require_dispatch_capacity(row: sqlite3.Row, *, include_new_turn: bool) -> None:
        bounds = ExpertConversationStore._bounds(row)
        usage = ExpertConversationStore._usage(row)
        remaining = remaining_capacity(bounds, usage)
        exhausted = (
            (include_new_turn and int(remaining["turns"]) <= 0)
            or int(remaining["model_calls"]) <= 0
            or int(remaining["input_tokens"]) <= 0
            or int(remaining["output_tokens"]) <= 0
            or int(remaining["elapsed_ms"]) <= 0
            or (bounds.max_cost_usd > 0 and float(remaining["cost_usd"]) <= 0)
        )
        if exhausted:
            raise ConversationError(
                ErrorCode.CAPACITY_EXHAUSTED,
                "Conversation capacity is exhausted.",
                conversation_id=str(row["conversation_id"]),
                current_version=int(row["version"]),
                state=ConversationState(str(row["state"])),
            )

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        *,
        event_id: str,
        row: sqlite3.Row,
        event_type: str,
        projection_version: int,
        previous_state: ConversationState | None,
        current_state: ConversationState,
        now: datetime,
        turn_id: str | None = None,
        attempt_id: str | None = None,
        reason_code: str | None = None,
        request_sha256: str | None = None,
        artifact_sha256: str | None = None,
        content_retained: bool = True,
    ) -> None:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM conversation_events WHERE conversation_id = ?",
                (row["conversation_id"],),
            ).fetchone()[0]
        )
        connection.execute(
            """INSERT INTO conversation_events
               (event_id, conversation_id, sequence, projection_version, event_type,
                turn_id, attempt_id, previous_state, current_state, reason_code,
                request_sha256, artifact_sha256, owner_binding_sha256,
                content_retained, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                row["conversation_id"],
                sequence,
                projection_version,
                event_type,
                turn_id,
                attempt_id,
                previous_state.value if previous_state is not None else None,
                current_state.value,
                reason_code,
                request_sha256,
                artifact_sha256,
                row["owner_hash"],
                int(content_retained),
                now.isoformat(),
            ),
        )

    def _snapshot_payload(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        snapshot_row = connection.execute(
            "SELECT * FROM conversation_snapshots WHERE snapshot_id = ?",
            (row["snapshot_id"],),
        ).fetchone()
        if snapshot_row is None:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Conversation snapshot metadata is missing.")
        payload = self._content_value(connection, str(snapshot_row["content_id"]))
        if isinstance(payload, dict):
            return payload
        if payload is not None:
            raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored conversation snapshot is invalid.")
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "kind": SNAPSHOT_KIND,
            "snapshot_id": snapshot_row["snapshot_id"],
            "conversation_id": snapshot_row["conversation_id"],
            "created_at": snapshot_row["created_at"],
            "context_builder_version": snapshot_row["context_builder_version"],
            "roster_hash": snapshot_row["roster_hash"],
            "snapshot_sha256": snapshot_row["snapshot_sha256"],
            "total_bytes": int(snapshot_row["total_bytes"]),
            "content_available": False,
            "content_deleted_at": row["content_deleted_at"],
            "expert_snapshots": None,
        }

    def _decision_brief(self, connection: sqlite3.Connection, row: sqlite3.Row) -> str | None:
        value = self._content_value(connection, row["decision_brief_content_id"])
        if value is None or isinstance(value, str):
            return value
        raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored conversation decision brief is invalid.")

    def _recent_turn_candidates(
        self,
        connection: sqlite3.Connection,
        conversation_id: str,
        *,
        before_ordinal: int,
        exact_turn_ids: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        if exact_turn_ids is None:
            rows = connection.execute(
                """SELECT * FROM conversation_turns
                   WHERE conversation_id = ? AND ordinal < ?
                     AND state IN ('completed', 'input_required')
                   ORDER BY ordinal""",
                (conversation_id, before_ordinal),
            ).fetchall()
        elif not exact_turn_ids:
            return []
        else:
            placeholders = ",".join("?" for _ in exact_turn_ids)
            rows = connection.execute(
                f"""SELECT * FROM conversation_turns
                    WHERE conversation_id = ? AND turn_id IN ({placeholders})
                    ORDER BY ordinal""",  # noqa: S608 - placeholders only; values stay parameterized
                (conversation_id, *exact_turn_ids),
            ).fetchall()
            if [str(item["turn_id"]) for item in rows] != list(exact_turn_ids):
                raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored context lineage is incomplete.")
        candidates: list[dict[str, Any]] = []
        for item in rows:
            request = self._content_value(connection, str(item["request_content_id"]))
            artifact = self._content_value(connection, item["artifact_content_id"])
            if not isinstance(request, str) or not isinstance(artifact, dict):
                raise ConversationError(ErrorCode.STORAGE_FAILED, "Stored prior turn content is invalid.")
            candidates.append({"turn_id": item["turn_id"], "request": request, "artifact": artifact})
        return candidates

    def _build_context(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        message: str,
        ordinal: int,
        exact_turn_ids: Sequence[str] | None = None,
    ) -> BoundedTurnContext:
        return build_bounded_turn_context(
            snapshot=self._snapshot_payload(connection, row),
            decision_brief=self._decision_brief(connection, row),
            message=message,
            recent_turn_candidates=self._recent_turn_candidates(
                connection,
                str(row["conversation_id"]),
                before_ordinal=ordinal,
                exact_turn_ids=exact_turn_ids,
            ),
            max_context_bytes=self._bounds(row).max_context_bytes,
        )

    def _execution_context(
        self,
        row: sqlite3.Row,
        *,
        turn_id: str,
        attempt_id: str,
        message: str,
        bounded: BoundedTurnContext,
    ) -> ConversationExecutionContext:
        bounds = self._bounds(row)
        return ConversationExecutionContext(
            conversation_id=str(row["conversation_id"]),
            turn_id=turn_id,
            attempt_id=attempt_id,
            mode=ConsultationMode(str(row["mode"])),
            expert_names=tuple(self._loads(str(row["expert_names_json"]))),
            message=message,
            decision_brief=bounded.decision_brief,
            context_snapshot=bounded.snapshot,
            recent_turns=bounded.recent_turns,
            decision_ledger=bounded.decision_ledger,
            context_bytes=bounded.context_bytes,
            context_sha256=bounded.context_sha256,
            bounds=bounds,
            remaining=remaining_capacity(bounds, self._usage(row)),
        )

    def _existing_idempotency(
        self,
        connection: sqlite3.Connection,
        *,
        owner_hash: str,
        scope_id: str,
        key_hash: str,
        request_hash: str,
    ) -> TurnLease | None:
        idem = connection.execute(
            """SELECT * FROM conversation_idempotency
               WHERE owner_hash = ? AND scope_id = ? AND idempotency_key_sha256 = ?""",
            (owner_hash, scope_id, key_hash),
        ).fetchone()
        if idem is None:
            return None
        if idem["request_sha256"] != request_hash:
            raise IdempotencyConflict(str(idem["conversation_id"]))
        return TurnLease(
            conversation_id=str(idem["conversation_id"]),
            turn_id=str(idem["turn_id"]),
            attempt_id=str(idem["attempt_id"]),
            projection_version=int(idem["result_version"]),
            dispatch_required=False,
            replayed=True,
            execution_context=None,
        )

    def reserve_start(self, request: ConversationStartRequest) -> TurnLease:
        return conversation_reservations.reserve_start(self, request)

    def reserve_continue(self, request: ConversationContinueRequest) -> TurnLease:
        return conversation_reservations.reserve_continue(self, request)

    def reserve_resume(self, request: ConversationResumeRequest) -> TurnLease:
        return conversation_reservations.reserve_resume(self, request)

    def finalize_turn(self, lease: TurnLease, result: TurnExecutionResult) -> ConversationOperationResult:
        return conversation_transitions.finalize_turn(self, lease, result)

    def record_executor_failure(
        self,
        lease: TurnLease,
        *,
        cancelled: bool = False,
        usage: TurnUsage | None = None,
    ) -> ConversationOperationResult:
        return conversation_transitions.record_executor_failure(self, lease, cancelled=cancelled, usage=usage)

    def get(
        self, *, owner_id: str, conversation_id: str, turn_id: str | None = None, replayed: bool = False
    ) -> ConversationOperationResult:
        return conversation_transitions.get_operation(
            self, owner_id=owner_id, conversation_id=conversation_id, turn_id=turn_id, replayed=replayed
        )

    def get_snapshot(self, *, owner_id: str, conversation_id: str) -> dict[str, Any]:
        return conversation_transitions.get_snapshot(self, owner_id=owner_id, conversation_id=conversation_id)

    def close_conversation(
        self, *, owner_id: str, conversation_id: str, expected_version: int
    ) -> ConversationOperationResult:
        return conversation_transitions.close_conversation(
            self, owner_id=owner_id, conversation_id=conversation_id, expected_version=expected_version
        )

    def delete_content(
        self, *, owner_id: str, conversation_id: str, expected_version: int
    ) -> ConversationOperationResult:
        return conversation_transitions.delete_content(
            self, owner_id=owner_id, conversation_id=conversation_id, expected_version=expected_version
        )

    def recover_expired_leases(self) -> int:
        return conversation_transitions.recover_expired_leases(self)

    def expire_due(self) -> int:
        return conversation_transitions.expire_due(self)

    def list_events(self, *, owner_id: str, conversation_id: str) -> list[dict[str, Any]]:
        return conversation_transitions.list_events(self, owner_id=owner_id, conversation_id=conversation_id)

    def verify_projection(self, conversation_id: str) -> dict[str, Any]:
        return conversation_transitions.verify_projection(self, conversation_id)

    def rebuild_projection(self, conversation_id: str) -> dict[str, Any]:
        return conversation_transitions.rebuild_projection(self, conversation_id)

    def quick_check(self) -> str:
        return conversation_transitions.quick_check(self)

    @staticmethod
    def _require_version(row: sqlite3.Row, expected_version: int) -> None:
        current = int(row["version"])
        if current != expected_version:
            raise VersionConflict(
                str(row["conversation_id"]),
                expected_version=expected_version,
                current_version=current,
                state=ConversationState(str(row["state"])),
            )

    @staticmethod
    def _check_expired(row: sqlite3.Row, now: datetime) -> None:
        if parse_datetime(str(row["expires_at"])) <= now:
            raise ConversationError(
                ErrorCode.RETENTION_EXPIRED,
                "Conversation retention has expired.",
                conversation_id=str(row["conversation_id"]),
                current_version=int(row["version"]),
                state=ConversationState(str(row["state"])),
            )
