"""Append-only audit records for expert belief mutations."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.utils.atomic_io import append_jsonl_durable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "deepr-expert-mutation-audit-v1"
KIND = "deepr.expert.mutation_audit"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware(timestamp: datetime) -> datetime:
    return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)


def _stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def state_hash(snapshot: dict[str, Any] | None) -> str | None:
    """Stable SHA-256 hash of a belief state snapshot."""
    if snapshot is None:
        return None
    return hashlib.sha256(_stable_json(snapshot).encode("utf-8")).hexdigest()


def belief_snapshot(belief: Any) -> dict[str, Any]:
    """Detached JSON snapshot suitable for before/after state hashing."""
    return json.loads(json.dumps(belief.to_dict(), ensure_ascii=True))


@dataclass(frozen=True)
class ExpertMutationAuditEntry:
    """A tamper-evident pointer to a belief mutation.

    The audit stores hashes of before/after state, not full belief text. The
    full details remain in `events.jsonl` and `beliefs.json`; this file exists
    to prove who changed which belief, when, and under which operation.
    """

    operation: str
    expert: str
    actor: str
    belief_id: str
    change_hash: str
    timestamp: datetime = field(default_factory=_utc_now)
    before_hash: str | None = None
    after_hash: str | None = None
    reason: str = ""
    schema_version: str = SCHEMA_VERSION
    kind: str = KIND

    def to_dict(self) -> dict[str, Any]:
        out = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "timestamp": _aware(self.timestamp).isoformat(),
            "operation": self.operation,
            "expert": self.expert,
            "actor": self.actor,
            "belief_id": self.belief_id,
            "change_hash": self.change_hash,
        }
        if self.before_hash is not None:
            out["before_hash"] = self.before_hash
        if self.after_hash is not None:
            out["after_hash"] = self.after_hash
        if self.reason:
            out["reason"] = self.reason
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpertMutationAuditEntry:
        return cls(
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
            kind=str(data.get("kind", KIND)),
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else _utc_now(),
            operation=str(data["operation"]),
            expert=str(data["expert"]),
            actor=str(data.get("actor", "deepr")),
            belief_id=str(data["belief_id"]),
            before_hash=data.get("before_hash"),
            after_hash=data.get("after_hash"),
            change_hash=str(data["change_hash"]),
            reason=str(data.get("reason", "")),
        )


def build_mutation_audit_entry(
    *,
    expert: str,
    actor: str,
    operation: str,
    belief_id: str,
    timestamp: datetime,
    change: dict[str, Any],
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    reason: str = "",
) -> ExpertMutationAuditEntry:
    """Create an audit entry for a committed belief mutation."""
    return ExpertMutationAuditEntry(
        timestamp=_aware(timestamp),
        operation=operation,
        expert=expert,
        actor=actor,
        belief_id=belief_id,
        before_hash=state_hash(before),
        after_hash=state_hash(after),
        change_hash=hashlib.sha256(_stable_json(change).encode("utf-8")).hexdigest(),
        reason=reason,
    )


def append_mutation_audit(path: Path, entry: ExpertMutationAuditEntry) -> None:
    """Append one audit entry durably."""
    append_jsonl_durable(path, entry.to_dict(), fsync=True)


def iter_mutation_audit(path: Path, since: datetime | None = None) -> list[ExpertMutationAuditEntry]:
    """Read audit entries from an append-only JSONL file."""
    if since is not None:
        since = _aware(since)

    entries: list[ExpertMutationAuditEntry] = []
    if not path.exists():
        return entries

    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = ExpertMutationAuditEntry.from_dict(json.loads(line))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Skipping malformed expert mutation audit entry (%s:%d): %s", path, line_no, exc)
                continue
            if since is not None and _aware(entry.timestamp) <= since:
                continue
            entries.append(entry)
    return entries


__all__ = [
    "KIND",
    "SCHEMA_VERSION",
    "ExpertMutationAuditEntry",
    "append_mutation_audit",
    "belief_snapshot",
    "build_mutation_audit_entry",
    "iter_mutation_audit",
    "state_hash",
]
