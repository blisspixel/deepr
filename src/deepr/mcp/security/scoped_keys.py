"""Scoped API-key contracts for remote MCP access."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.mcp.security.tool_allowlist import ResearchMode, ToolAllowlist

KEY_SCHEMA_VERSION = "deepr-mcp-key-v1"
AUDIT_SCHEMA_VERSION = "deepr-mcp-remote-audit-v1"
_HASH_ALGORITHM = "pbkdf2_sha256"
_HASH_ITERATIONS = 210_000
_EXPERT_ARG_NAMES = ("expert_name", "name")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _default_security_dir() -> Path:
    return Path(os.getenv("DEEPR_DATA_DIR", "data")) / "security"


def default_key_store_path() -> Path:
    return _default_security_dir() / "mcp_keys.json"


def default_remote_audit_path() -> Path:
    return _default_security_dir() / "mcp_remote_audit.jsonl"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError("timestamp must be an ISO datetime string")


def _hash_secret(secret: str, *, salt: str | None = None, iterations: int = _HASH_ITERATIONS) -> str:
    if not secret:
        raise ValueError("secret must not be empty")
    resolved_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        bytes.fromhex(resolved_salt),
        iterations,
    ).hex()
    return f"{_HASH_ALGORITHM}${iterations}${resolved_salt}${digest}"


def _verify_secret(secret: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt, expected = encoded_hash.split("$", 3)
        if algorithm != _HASH_ALGORITHM:
            return False
        candidate = _hash_secret(secret, salt=salt, iterations=int(iterations_raw)).split("$", 3)[3]
    except (TypeError, ValueError, UnicodeEncodeError):
        return False
    return hmac.compare_digest(candidate, expected)


def hash_arguments(arguments: dict[str, Any]) -> str:
    encoded = json.dumps(arguments, sort_keys=True, default=str, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScopedMCPKeyRecord:
    """Persisted scoped MCP key metadata. Secret values are never stored."""

    key_id: str
    secret_hash: str
    mode: ResearchMode = ResearchMode.STANDARD
    expert_allowlist: tuple[str, ...] = ()
    budget_limit_usd: float | None = None
    revoked: bool = False
    schema_version: str = KEY_SCHEMA_VERSION
    created_at: datetime = field(default_factory=_utc_now)
    last_used_at: datetime | None = None

    def __post_init__(self) -> None:
        key_id = self.key_id.strip()
        if not key_id:
            raise ValueError("key_id must not be empty")
        if self.budget_limit_usd is not None and self.budget_limit_usd < 0:
            raise ValueError("budget_limit_usd must be non-negative")
        experts = tuple(str(item).strip() for item in self.expert_allowlist if str(item).strip())
        object.__setattr__(self, "key_id", key_id)
        object.__setattr__(self, "expert_allowlist", experts)

    def to_dict(self, *, include_secret_hash: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "key_id": self.key_id,
            "mode": self.mode.value,
            "expert_allowlist": list(self.expert_allowlist),
            "budget_limit_usd": self.budget_limit_usd,
            "revoked": self.revoked,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }
        if include_secret_hash:
            data["secret_hash"] = self.secret_hash
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScopedMCPKeyRecord:
        mode = ResearchMode(str(data.get("mode", ResearchMode.STANDARD.value)))
        return cls(
            schema_version=str(data.get("schema_version", KEY_SCHEMA_VERSION)),
            key_id=str(data["key_id"]),
            secret_hash=str(data["secret_hash"]),
            mode=mode,
            expert_allowlist=tuple(str(item) for item in data.get("expert_allowlist", [])),
            budget_limit_usd=data.get("budget_limit_usd"),
            revoked=bool(data.get("revoked", False)),
            created_at=_parse_dt(data.get("created_at")) or _utc_now(),
            last_used_at=_parse_dt(data.get("last_used_at")),
        )

    def to_context(self) -> ScopedMCPKeyContext:
        return ScopedMCPKeyContext(
            key_id=self.key_id,
            mode=self.mode,
            expert_allowlist=self.expert_allowlist,
            budget_limit_usd=self.budget_limit_usd,
        )


@dataclass(frozen=True)
class ScopedMCPKeyContext:
    """Authenticated remote MCP caller context passed across transport boundaries."""

    key_id: str
    mode: ResearchMode
    expert_allowlist: tuple[str, ...] = ()
    budget_limit_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "mode": self.mode.value,
            "expert_allowlist": list(self.expert_allowlist),
            "budget_limit_usd": self.budget_limit_usd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScopedMCPKeyContext:
        return cls(
            key_id=str(data["key_id"]),
            mode=ResearchMode(str(data["mode"])),
            expert_allowlist=tuple(str(item) for item in data.get("expert_allowlist", [])),
            budget_limit_usd=data.get("budget_limit_usd"),
        )


@dataclass(frozen=True)
class ScopedMCPAuthzDecision:
    allowed: bool
    reason: str
    error_code: str = ""
    requires_confirmation: bool = False
    requested_experts: tuple[str, ...] = ()


class ScopedMCPKeyStore:
    """Local JSON key store for remote MCP API keys."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_key_store_path()
        self._lock = threading.Lock()

    def create_key(
        self,
        key_id: str | None = None,
        *,
        mode: ResearchMode = ResearchMode.STANDARD,
        expert_allowlist: list[str] | tuple[str, ...] | None = None,
        budget_limit_usd: float | None = None,
        secret: str | None = None,
    ) -> tuple[str, ScopedMCPKeyRecord]:
        resolved_id = key_id or f"mcp_{secrets.token_hex(6)}"
        resolved_secret = secret or f"deepr_mcp_{secrets.token_urlsafe(32)}"
        record = ScopedMCPKeyRecord(
            key_id=resolved_id,
            secret_hash=_hash_secret(resolved_secret),
            mode=mode,
            expert_allowlist=tuple(expert_allowlist or ()),
            budget_limit_usd=budget_limit_usd,
        )
        with self._lock:
            records = {item.key_id: item for item in self.list_keys()}
            if resolved_id in records:
                raise ValueError(f"MCP key already exists: {resolved_id}")
            records[record.key_id] = record
            self._write_records(list(records.values()))
        return resolved_secret, record

    def list_keys(self) -> list[ScopedMCPKeyRecord]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("MCP key store must contain a JSON list")
        return [ScopedMCPKeyRecord.from_dict(item) for item in raw if isinstance(item, dict)]

    def has_active_keys(self) -> bool:
        return any(not item.revoked for item in self.list_keys())

    def authenticate(self, secret: str | None) -> ScopedMCPKeyContext | None:
        if not secret:
            return None
        with self._lock:
            records = self.list_keys()
            for index, record in enumerate(records):
                if record.revoked or not _verify_secret(secret, record.secret_hash):
                    continue
                records[index] = ScopedMCPKeyRecord(
                    key_id=record.key_id,
                    secret_hash=record.secret_hash,
                    mode=record.mode,
                    expert_allowlist=record.expert_allowlist,
                    budget_limit_usd=record.budget_limit_usd,
                    revoked=record.revoked,
                    schema_version=record.schema_version,
                    created_at=record.created_at,
                    last_used_at=_utc_now(),
                )
                self._write_records(records)
                return records[index].to_context()
        return None

    def revoke(self, key_id: str) -> bool:
        with self._lock:
            records = self.list_keys()
            changed = False
            updated: list[ScopedMCPKeyRecord] = []
            for record in records:
                if record.key_id == key_id and not record.revoked:
                    record = ScopedMCPKeyRecord(
                        key_id=record.key_id,
                        secret_hash=record.secret_hash,
                        mode=record.mode,
                        expert_allowlist=record.expert_allowlist,
                        budget_limit_usd=record.budget_limit_usd,
                        revoked=True,
                        schema_version=record.schema_version,
                        created_at=record.created_at,
                        last_used_at=record.last_used_at,
                    )
                    changed = True
                updated.append(record)
            if changed:
                self._write_records(updated)
            return changed

    def _write_records(self, records: list[ScopedMCPKeyRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = [record.to_dict() for record in sorted(records, key=lambda item: item.key_id)]
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        tmp_path.replace(self.path)


def _extract_requested_experts(arguments: dict[str, Any]) -> tuple[str, ...]:
    experts: list[str] = []
    for key in _EXPERT_ARG_NAMES:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            experts.append(value.strip())
        elif isinstance(value, list | tuple | set):
            experts.extend(str(item).strip() for item in value if str(item).strip())
    return tuple(dict.fromkeys(experts))


def authorize_scoped_mcp_tool_call(
    context: ScopedMCPKeyContext,
    tool_name: str,
    arguments: dict[str, Any],
    allowlist: ToolAllowlist | None = None,
) -> ScopedMCPAuthzDecision:
    """Validate a tool call against a scoped remote MCP key."""
    policy = allowlist or ToolAllowlist()
    validation = policy.validate_tool_call(tool_name, mode=context.mode)
    requested_experts = _extract_requested_experts(arguments)
    if not validation["allowed"]:
        return ScopedMCPAuthzDecision(
            allowed=False,
            reason=str(validation["reason"]),
            error_code="TOOL_BLOCKED_BY_KEY_MODE",
            requested_experts=requested_experts,
        )
    if validation["requires_confirmation"] and not bool(arguments.get("_approved")):
        return ScopedMCPAuthzDecision(
            allowed=False,
            reason=str(validation["reason"]),
            error_code="CONFIRMATION_REQUIRED",
            requires_confirmation=True,
            requested_experts=requested_experts,
        )
    if context.expert_allowlist:
        allowed_experts = set(context.expert_allowlist)
        if tool_name == "deepr_list_experts":
            return ScopedMCPAuthzDecision(
                allowed=False,
                reason="Expert-scoped keys cannot list every expert",
                error_code="EXPERT_SCOPE_REQUIRED",
                requested_experts=requested_experts,
            )
        if requested_experts and any(expert not in allowed_experts for expert in requested_experts):
            return ScopedMCPAuthzDecision(
                allowed=False,
                reason="Tool call targets an expert outside this key's allowlist",
                error_code="EXPERT_SCOPE_DENIED",
                requested_experts=requested_experts,
            )
    return ScopedMCPAuthzDecision(
        allowed=True,
        reason="Tool call is allowed by scoped key",
        requires_confirmation=bool(validation["requires_confirmation"]),
        requested_experts=requested_experts,
    )


@dataclass(frozen=True)
class RemoteMCPAuditEvent:
    key_id: str
    tool: str
    args_hash: str
    outcome: str
    timestamp: datetime = field(default_factory=_utc_now)
    schema_version: str = AUDIT_SCHEMA_VERSION
    mode: ResearchMode = ResearchMode.STANDARD
    trace_id: str = ""
    error_code: str = ""
    expert_names: tuple[str, ...] = ()
    cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp.isoformat(),
            "key_id": self.key_id,
            "mode": self.mode.value,
            "tool": self.tool,
            "args_hash": self.args_hash,
            "trace_id": self.trace_id,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "expert_names": list(self.expert_names),
            "cost_usd": self.cost_usd,
        }


class RemoteMCPAuditLog:
    """Append-only JSONL audit log for authenticated remote MCP calls."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_remote_audit_path()
        self._lock = threading.Lock()

    def record(self, event: RemoteMCPAuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.to_dict(), sort_keys=True, ensure_ascii=True)
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def record_tool_call(
        self,
        context: ScopedMCPKeyContext,
        *,
        tool: str,
        arguments: dict[str, Any],
        outcome: str,
        error_code: str = "",
        cost_usd: float | None = None,
    ) -> None:
        trace_id = str(arguments.get("trace_id") or arguments.get("job_id") or "")
        self.record(
            RemoteMCPAuditEvent(
                key_id=context.key_id,
                mode=context.mode,
                tool=tool,
                args_hash=hash_arguments(arguments),
                trace_id=trace_id,
                outcome=outcome,
                error_code=error_code,
                expert_names=_extract_requested_experts(arguments),
                cost_usd=cost_usd,
            )
        )

    def read_recent(self, limit: int = 100) -> list[RemoteMCPAuditEvent]:
        if not self.path.exists():
            return []
        events: list[RemoteMCPAuditEvent] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                data = json.loads(line)
                events.append(
                    RemoteMCPAuditEvent(
                        key_id=str(data["key_id"]),
                        mode=ResearchMode(str(data.get("mode", ResearchMode.STANDARD.value))),
                        tool=str(data["tool"]),
                        args_hash=str(data["args_hash"]),
                        trace_id=str(data.get("trace_id", "")),
                        outcome=str(data["outcome"]),
                        error_code=str(data.get("error_code", "")),
                        expert_names=tuple(str(item) for item in data.get("expert_names", [])),
                        cost_usd=data.get("cost_usd"),
                        timestamp=_parse_dt(data.get("timestamp")) or _utc_now(),
                        schema_version=str(data.get("schema_version", AUDIT_SCHEMA_VERSION)),
                    )
                )
        return events[-limit:]
