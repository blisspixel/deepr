"""Scoped API-key contracts for remote MCP access."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from deepr.mcp.security.tool_allowlist import ResearchMode, ToolAllowlist

KEY_SCHEMA_VERSION = "deepr-mcp-key-v1"
AUDIT_SCHEMA_VERSION = "deepr-mcp-remote-audit-v1"
_HASH_ALGORITHM = "pbkdf2_sha256"
_HASH_ITERATIONS = 210_000
_EXPERT_ARG_NAMES = ("expert_name", "name")
_BUDGET_ARGUMENT_TOOLS = frozenset(
    {
        "deepr_agentic_research",
        "deepr_query_expert",
        "deepr_research",
    }
)
_FIXED_TOOL_COST_ESTIMATES_USD = {
    "deepr_expert_absorb": 0.03,
    "deepr_expert_validate": 0.02,
    "deepr_reflect": 0.02,
}


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


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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


def _coerce_nonnegative_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    if resolved < 0:
        return None
    return resolved


def _estimate_research_cost(arguments: dict[str, Any]) -> float:
    model = str(arguments.get("model") or "o4-mini-deep-research")
    try:
        from deepr.providers.registry import get_cost_estimate

        registry_cost = get_cost_estimate(model)
    except Exception:
        registry_cost = 0.20
    if "o4-mini" in model:
        return max(0.15, registry_cost)
    if "o3" in model:
        return max(0.50, registry_cost)
    if "deep-research" in model:
        return max(registry_cost, 1.00)
    return max(registry_cost, 0.20)


def estimate_scoped_mcp_tool_cost(tool_name: str, arguments: dict[str, Any]) -> float | None:
    """Return deterministic estimated spend for a scoped remote MCP call."""
    requested_budget = _coerce_nonnegative_float(arguments.get("budget"))
    if requested_budget is not None and tool_name in _BUDGET_ARGUMENT_TOOLS:
        return requested_budget
    if tool_name == "deepr_research":
        return _estimate_research_cost(arguments)
    if tool_name == "deepr_agentic_research":
        return 5.0
    if tool_name == "deepr_query_expert":
        return 10.0
    if tool_name == "deepr_reflect":
        try:
            depth = int(arguments.get("depth", 1) or 1)
        except (TypeError, ValueError):
            depth = 1
        if depth <= 0:
            return 0.0
    return _FIXED_TOOL_COST_ESTIMATES_USD.get(tool_name)


@dataclass(frozen=True)
class ScopedMCPKeyRecord:
    """Persisted scoped MCP key metadata. Secret values are never stored."""

    key_id: str
    secret_hash: str
    mode: ResearchMode = ResearchMode.STANDARD
    expert_allowlist: tuple[str, ...] = ()
    budget_limit_usd: float | None = None
    rate_limit_per_minute: int | None = None
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
        rate_limit = None
        if self.rate_limit_per_minute is not None:
            try:
                rate_limit = int(self.rate_limit_per_minute)
            except (TypeError, ValueError) as exc:
                raise ValueError("rate_limit_per_minute must be an integer when set") from exc
            if rate_limit < 1:
                raise ValueError("rate_limit_per_minute must be positive when set")
        experts = tuple(str(item).strip() for item in self.expert_allowlist if str(item).strip())
        object.__setattr__(self, "key_id", key_id)
        object.__setattr__(self, "rate_limit_per_minute", rate_limit)
        object.__setattr__(self, "expert_allowlist", experts)

    def to_dict(self, *, include_secret_hash: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "key_id": self.key_id,
            "mode": self.mode.value,
            "expert_allowlist": list(self.expert_allowlist),
            "budget_limit_usd": self.budget_limit_usd,
            "rate_limit_per_minute": self.rate_limit_per_minute,
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
            rate_limit_per_minute=data.get("rate_limit_per_minute"),
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
            rate_limit_per_minute=self.rate_limit_per_minute,
        )


@dataclass(frozen=True)
class ScopedMCPKeyContext:
    """Authenticated remote MCP caller context passed across transport boundaries."""

    key_id: str
    mode: ResearchMode
    expert_allowlist: tuple[str, ...] = ()
    budget_limit_usd: float | None = None
    rate_limit_per_minute: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "mode": self.mode.value,
            "expert_allowlist": list(self.expert_allowlist),
            "budget_limit_usd": self.budget_limit_usd,
            "rate_limit_per_minute": self.rate_limit_per_minute,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScopedMCPKeyContext:
        return cls(
            key_id=str(data["key_id"]),
            mode=ResearchMode(str(data["mode"])),
            expert_allowlist=tuple(str(item) for item in data.get("expert_allowlist", [])),
            budget_limit_usd=data.get("budget_limit_usd"),
            rate_limit_per_minute=data.get("rate_limit_per_minute"),
        )


@dataclass(frozen=True)
class ScopedMCPAuthzDecision:
    allowed: bool
    reason: str
    error_code: str = ""
    requires_confirmation: bool = False
    requested_experts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScopedMCPBudgetDecision:
    allowed: bool
    reason: str
    error_code: str = ""
    budget_limit_usd: float | None = None
    spent_usd: float = 0.0
    remaining_usd: float | None = None
    estimated_cost_usd: float | None = None


@dataclass(frozen=True)
class ScopedMCPRateLimitDecision:
    allowed: bool
    reason: str
    error_code: str = ""
    limit_per_minute: int | None = None
    calls_in_window: int = 0
    window_seconds: int = 60
    retry_after_seconds: int | None = None


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
        rate_limit_per_minute: int | None = None,
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
            rate_limit_per_minute=rate_limit_per_minute,
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
                    rate_limit_per_minute=record.rate_limit_per_minute,
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
                        rate_limit_per_minute=record.rate_limit_per_minute,
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


def constrain_scoped_mcp_budget_arguments(
    context: ScopedMCPKeyContext,
    tool_name: str,
    arguments: dict[str, Any],
    spent_usd: float,
) -> dict[str, Any]:
    """Inject the remaining key budget into budget-aware tools when omitted."""
    if context.budget_limit_usd is None or tool_name not in _BUDGET_ARGUMENT_TOOLS or "budget" in arguments:
        return arguments
    remaining = max(context.budget_limit_usd - spent_usd, 0.0)
    if remaining <= 0:
        return arguments
    return {**arguments, "budget": round(remaining, 4)}


def authorize_scoped_mcp_budget(
    context: ScopedMCPKeyContext,
    tool_name: str,
    arguments: dict[str, Any],
    spent_usd: float,
) -> ScopedMCPBudgetDecision:
    """Validate a scoped key's per-key budget before dispatch."""
    if context.budget_limit_usd is None:
        return ScopedMCPBudgetDecision(
            allowed=True,
            reason="No per-key budget ceiling configured",
            spent_usd=spent_usd,
        )
    remaining = max(context.budget_limit_usd - spent_usd, 0.0)
    estimated_cost = estimate_scoped_mcp_tool_cost(tool_name, arguments)
    if estimated_cost is None or estimated_cost <= 0:
        return ScopedMCPBudgetDecision(
            allowed=True,
            reason="Tool has no deterministic remote spend estimate",
            budget_limit_usd=context.budget_limit_usd,
            spent_usd=spent_usd,
            remaining_usd=remaining,
            estimated_cost_usd=estimated_cost,
        )
    if estimated_cost > remaining:
        return ScopedMCPBudgetDecision(
            allowed=False,
            reason=(
                f"Scoped key budget would be exceeded: estimated ${estimated_cost:.2f}, remaining ${remaining:.2f}"
            ),
            error_code="KEY_BUDGET_EXCEEDED",
            budget_limit_usd=context.budget_limit_usd,
            spent_usd=spent_usd,
            remaining_usd=remaining,
            estimated_cost_usd=estimated_cost,
        )
    return ScopedMCPBudgetDecision(
        allowed=True,
        reason="Scoped key budget allows this tool call",
        budget_limit_usd=context.budget_limit_usd,
        spent_usd=spent_usd,
        remaining_usd=remaining,
        estimated_cost_usd=estimated_cost,
    )


def authorize_scoped_mcp_rate_limit(
    context: ScopedMCPKeyContext,
    calls_in_window: int,
    *,
    window_seconds: int = 60,
    retry_after_seconds: int | None = None,
) -> ScopedMCPRateLimitDecision:
    """Validate a scoped key's per-minute call rate before dispatch."""
    limit = context.rate_limit_per_minute
    observed = max(int(calls_in_window), 0)
    if limit is None:
        return ScopedMCPRateLimitDecision(
            allowed=True,
            reason="No per-key rate limit configured",
            calls_in_window=observed,
            window_seconds=window_seconds,
        )
    if observed >= limit:
        return ScopedMCPRateLimitDecision(
            allowed=False,
            reason=f"Scoped key rate limit exceeded: {observed}/{limit} calls in the last {window_seconds} seconds",
            error_code="KEY_RATE_LIMIT_EXCEEDED",
            limit_per_minute=limit,
            calls_in_window=observed,
            window_seconds=window_seconds,
            retry_after_seconds=retry_after_seconds if retry_after_seconds is not None else window_seconds,
        )
    return ScopedMCPRateLimitDecision(
        allowed=True,
        reason="Scoped key rate limit allows this tool call",
        limit_per_minute=limit,
        calls_in_window=observed,
        window_seconds=window_seconds,
        retry_after_seconds=retry_after_seconds,
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

    def __post_init__(self) -> None:
        if self.cost_usd is not None:
            object.__setattr__(self, "cost_usd", max(float(self.cost_usd), 0.0))

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

    def count_for_key_since(self, key_id: str, since: datetime) -> int:
        """Return audited remote-call count for a key since the given timestamp."""
        threshold = _as_aware_utc(since)
        total = 0
        for event in self.read_recent(limit=1_000_000):
            if event.key_id == key_id and _as_aware_utc(event.timestamp) >= threshold:
                total += 1
        return total

    def retry_after_seconds_for_key(
        self,
        key_id: str,
        *,
        now: datetime | None = None,
        window_seconds: int = 60,
    ) -> int:
        """Return seconds until the oldest in-window key call leaves the window."""
        resolved_now = _as_aware_utc(now or _utc_now())
        threshold = resolved_now - timedelta(seconds=window_seconds)
        oldest: datetime | None = None
        for event in self.read_recent(limit=1_000_000):
            if event.key_id != key_id:
                continue
            timestamp = _as_aware_utc(event.timestamp)
            if timestamp < threshold:
                continue
            if oldest is None or timestamp < oldest:
                oldest = timestamp
        if oldest is None:
            return 0
        seconds = (oldest + timedelta(seconds=window_seconds) - resolved_now).total_seconds()
        return max(int(seconds) + (1 if seconds % 1 else 0), 1)

    def total_cost_for_key(self, key_id: str) -> float:
        """Return audited actual spend for a scoped key."""
        total = 0.0
        for event in self.read_recent(limit=1_000_000):
            if event.key_id == key_id and event.cost_usd is not None:
                total += event.cost_usd
        return round(total, 10)
