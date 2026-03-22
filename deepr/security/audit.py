"""Append-only structured audit log for security-relevant events.

Records permission checks, budget overrides, tool executions, auth events,
and policy changes. Designed for compliance and forensics.

Events are written to a JSONL file and are immutable once written.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditEventType(str, Enum):
    """Categories of auditable events."""

    # Auth
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"

    # Permissions
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"

    # Tools
    TOOL_EXECUTED = "tool_executed"
    TOOL_BLOCKED = "tool_blocked"

    # Budget
    BUDGET_CHECK = "budget_check"
    BUDGET_EXCEEDED = "budget_exceeded"
    BUDGET_OVERRIDE = "budget_override"

    # Policy
    POLICY_CHANGED = "policy_changed"
    POLICY_LOADED = "policy_loaded"

    # Research
    RESEARCH_SUBMITTED = "research_submitted"
    RESEARCH_COMPLETED = "research_completed"

    # Expert
    EXPERT_CREATED = "expert_created"
    EXPERT_MODIFIED = "expert_modified"
    EXPERT_DELETED = "expert_deleted"

    # System
    CONFIG_CHANGED = "config_changed"
    ANOMALY_DETECTED = "anomaly_detected"


@dataclass
class AuditEvent:
    """A single immutable audit event."""

    event_type: AuditEventType
    timestamp: datetime = field(default_factory=_utc_now)
    actor: str = ""  # User, session, or system component
    resource: str = ""  # What was acted on (tool name, expert name, etc.)
    action: str = ""  # What happened (short verb phrase)
    outcome: str = "success"  # success | denied | error
    details: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "resource": self.resource,
            "action": self.action,
            "outcome": self.outcome,
            "details": self.details,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEvent:
        return cls(
            event_type=AuditEventType(data["event_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else _utc_now(),
            actor=data.get("actor", ""),
            resource=data.get("resource", ""),
            action=data.get("action", ""),
            outcome=data.get("outcome", "success"),
            details=data.get("details", {}),
            session_id=data.get("session_id", ""),
            trace_id=data.get("trace_id", ""),
        )


class AuditLog:
    """Append-only audit log backed by JSONL.

    Thread-safe. Events cannot be modified or deleted once written.

    Usage::

        audit = AuditLog()
        audit.record(AuditEvent(
            event_type=AuditEventType.TOOL_EXECUTED,
            actor="user@example.com",
            resource="deep_research",
            action="executed tool",
            details={"cost": 0.50},
        ))

        events = audit.query(event_type=AuditEventType.PERMISSION_DENIED)
    """

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or Path("data/security/audit.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, event: AuditEvent) -> None:
        """Append an audit event to the log."""
        with self._lock:
            line = json.dumps(event.to_dict(), ensure_ascii=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def query(
        self,
        event_type: AuditEventType | None = None,
        actor: str | None = None,
        outcome: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> list[AuditEvent]:
        """Query audit events with optional filters."""
        if not self.log_path.exists():
            return []

        events: list[AuditEvent] = []
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    ev = AuditEvent.from_dict(data)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

                if event_type and ev.event_type != event_type:
                    continue
                if actor and ev.actor != actor:
                    continue
                if outcome and ev.outcome != outcome:
                    continue
                if start and ev.timestamp < start:
                    continue
                if end and ev.timestamp > end:
                    continue

                events.append(ev)
                if len(events) >= limit:
                    break

        return events

    def count_by_type(self, limit: int = 10000) -> dict[str, int]:
        """Count events by type."""
        events = self.query(limit=limit)
        counts: dict[str, int] = {}
        for ev in events:
            counts[ev.event_type.value] = counts.get(ev.event_type.value, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def recent_denials(self, limit: int = 20) -> list[AuditEvent]:
        """Get recent permission denials for security review."""
        return self.query(outcome="denied", limit=limit)

    def health(self) -> dict[str, Any]:
        """Audit log health summary."""
        exists = self.log_path.exists()
        event_count = 0
        if exists:
            with open(self.log_path, encoding="utf-8") as f:
                event_count = sum(1 for line in f if line.strip())

        return {
            "path": str(self.log_path),
            "exists": exists,
            "event_count": event_count,
            "writable": True,  # We created the dir in __init__
        }
