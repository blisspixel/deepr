"""SQLite schema and migration boundary for expert conversations."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    owner_hash TEXT NOT NULL,
    state TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    mode TEXT NOT NULL,
    expert_names_json TEXT NOT NULL,
    snapshot_id TEXT NOT NULL UNIQUE,
    decision_brief_content_id TEXT,
    backend_json TEXT NOT NULL,
    bounds_json TEXT NOT NULL,
    turns_started INTEGER NOT NULL DEFAULT 0 CHECK (turns_started >= 0),
    turns_completed INTEGER NOT NULL DEFAULT 0 CHECK (turns_completed >= 0),
    model_calls INTEGER NOT NULL DEFAULT 0 CHECK (model_calls >= 0),
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    elapsed_ms INTEGER NOT NULL DEFAULT 0 CHECK (elapsed_ms >= 0),
    cost_usd REAL NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    retention_days INTEGER NOT NULL CHECK (retention_days BETWEEN 1 AND 365),
    expires_at TEXT NOT NULL,
    content_deleted_at TEXT,
    current_turn_id TEXT,
    latest_turn_id TEXT,
    pending_input_request_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_owner ON conversations(owner_hash, updated_at);
CREATE INDEX IF NOT EXISTS idx_conversations_expiry ON conversations(expires_at, state);

CREATE TABLE IF NOT EXISTS conversation_contents (
    content_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    turn_id TEXT,
    content_kind TEXT NOT NULL,
    content_json TEXT,
    content_sha256 TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    created_at TEXT NOT NULL,
    deleted_at TEXT,
    CHECK ((content_json IS NOT NULL AND deleted_at IS NULL)
        OR (content_json IS NULL AND deleted_at IS NOT NULL)),
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_conversation_contents_conversation
    ON conversation_contents(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conversation_contents_turn
    ON conversation_contents(turn_id, content_kind);

CREATE TRIGGER IF NOT EXISTS conversation_contents_purge_only
BEFORE UPDATE ON conversation_contents
WHEN NOT (
    NEW.content_id IS OLD.content_id
    AND NEW.conversation_id IS OLD.conversation_id
    AND NEW.turn_id IS OLD.turn_id
    AND NEW.content_kind IS OLD.content_kind
    AND NEW.content_sha256 IS OLD.content_sha256
    AND NEW.byte_count IS OLD.byte_count
    AND NEW.created_at IS OLD.created_at
    AND OLD.content_json IS NOT NULL
    AND NEW.content_json IS NULL
    AND OLD.deleted_at IS NULL
    AND NEW.deleted_at IS NOT NULL
)
BEGIN
    SELECT RAISE(ABORT, 'conversation content may only be purged');
END;

CREATE TRIGGER IF NOT EXISTS conversation_contents_no_delete
BEFORE DELETE ON conversation_contents
BEGIN
    SELECT RAISE(ABORT, 'conversation content metadata is append-only');
END;

CREATE TABLE IF NOT EXISTS conversation_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL UNIQUE,
    content_id TEXT NOT NULL UNIQUE,
    context_builder_version TEXT NOT NULL,
    roster_hash TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    total_bytes INTEGER NOT NULL CHECK (total_bytes >= 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE RESTRICT,
    FOREIGN KEY (content_id) REFERENCES conversation_contents(content_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
    state TEXT NOT NULL,
    request_content_id TEXT NOT NULL UNIQUE,
    request_sha256 TEXT NOT NULL,
    input_request_id TEXT,
    next_input_request_id TEXT,
    context_json TEXT NOT NULL,
    artifact_content_id TEXT UNIQUE,
    artifact_sha256 TEXT,
    stop_reason TEXT NOT NULL,
    retryable INTEGER NOT NULL DEFAULT 0 CHECK (retryable IN (0, 1)),
    capacity_json TEXT NOT NULL,
    trace_json TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 1 CHECK (attempt_count >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (conversation_id, ordinal),
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE RESTRICT,
    FOREIGN KEY (request_content_id) REFERENCES conversation_contents(content_id) ON DELETE RESTRICT,
    FOREIGN KEY (artifact_content_id) REFERENCES conversation_contents(content_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_conversation_turns_conversation
    ON conversation_turns(conversation_id, ordinal);

CREATE TABLE IF NOT EXISTS conversation_turn_attempts (
    attempt_id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL,
    attempt_ordinal INTEGER NOT NULL CHECK (attempt_ordinal >= 1),
    state TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    consult_trace_id TEXT,
    consult_lifecycle_trace_id TEXT,
    error_code TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (turn_id, attempt_ordinal),
    FOREIGN KEY (turn_id) REFERENCES conversation_turns(turn_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_conversation_attempt_leases
    ON conversation_turn_attempts(state, lease_expires_at);

CREATE TABLE IF NOT EXISTS conversation_idempotency (
    owner_hash TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    idempotency_key_sha256 TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    status TEXT NOT NULL,
    result_version INTEGER NOT NULL CHECK (result_version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (owner_hash, scope_id, idempotency_key_sha256),
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE RESTRICT,
    FOREIGN KEY (turn_id) REFERENCES conversation_turns(turn_id) ON DELETE RESTRICT,
    FOREIGN KEY (attempt_id) REFERENCES conversation_turn_attempts(attempt_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS conversation_events (
    event_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    projection_version INTEGER NOT NULL CHECK (projection_version >= 1),
    event_type TEXT NOT NULL,
    turn_id TEXT,
    attempt_id TEXT,
    previous_state TEXT,
    current_state TEXT NOT NULL,
    reason_code TEXT,
    request_sha256 TEXT,
    artifact_sha256 TEXT,
    owner_binding_sha256 TEXT NOT NULL,
    content_retained INTEGER NOT NULL CHECK (content_retained IN (0, 1)),
    created_at TEXT NOT NULL,
    UNIQUE (conversation_id, sequence),
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_conversation_events_conversation
    ON conversation_events(conversation_id, sequence);

CREATE TRIGGER IF NOT EXISTS conversation_events_no_update
BEFORE UPDATE ON conversation_events
BEGIN
    SELECT RAISE(ABORT, 'conversation events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS conversation_events_no_delete
BEFORE DELETE ON conversation_events
BEGIN
    SELECT RAISE(ABORT, 'conversation events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS conversation_snapshots_no_update
BEFORE UPDATE ON conversation_snapshots
BEGIN
    SELECT RAISE(ABORT, 'conversation snapshots are immutable');
END;

CREATE TRIGGER IF NOT EXISTS conversation_snapshots_no_delete
BEFORE DELETE ON conversation_snapshots
BEGIN
    SELECT RAISE(ABORT, 'conversation snapshots are immutable');
END;
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create the v1 schema or reject an unknown future database."""
    current = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current not in {0, SCHEMA_VERSION}:
        raise sqlite3.DatabaseError(f"unsupported expert conversation database version: {current}")
    connection.executescript(_DDL)
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
