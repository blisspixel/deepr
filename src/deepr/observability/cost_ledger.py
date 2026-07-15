"""Canonical append-only cost ledger for Deepr."""

import importlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")
_REQUIRED_EVENT_FIELDS = frozenset({"timestamp", "operation", "provider", "cost_usd"})


class CostLedgerLockTimeout(TimeoutError):
    """A bounded cost-ledger lock attempt expired."""


class CostLedgerIdempotencyConflict(ValueError):
    """An idempotency key was reused for a materially different cost event."""


class CostLedgerReadError(RuntimeError):
    """The canonical ledger could not be read safely before an append."""


class CostLedgerDurabilityError(RuntimeError):
    """A required ledger flush could not be confirmed durable."""


def _acquire_os_lock(acquire: Callable[[], None], timeout: float | None) -> None:
    if timeout is None:
        acquire()
        return
    deadline = time.monotonic() + timeout
    while True:
        try:
            acquire()
            return
        except OSError as error:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CostLedgerLockTimeout("cost ledger lock unavailable within the configured timeout") from error
            time.sleep(min(0.01, remaining))


def _windows_region_lock(handle: Any, msvcrt: Any, mode: int) -> None:
    handle.seek(0)
    msvcrt.locking(handle.fileno(), mode, 1)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def default_cost_data_dir() -> Path:
    """Resolve the cost-data directory.

    Honors DEEPR_COST_DATA_DIR so deployments can relocate cost state and -
    critically - so the test suite can isolate itself: the default is
    CWD-relative, and unit tests running from the repo root were appending
    fabricated cost events to the user's real canonical ledger.
    """
    base = os.environ.get("DEEPR_COST_DATA_DIR", "").strip()
    return Path(base) if base else Path("data/costs")


@dataclass
class CostLedgerEvent:
    """Single immutable cost event in the canonical ledger."""

    operation: str
    provider: str
    cost_usd: float
    timestamp: datetime = field(default_factory=_utc_now)
    model: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    task_id: str = ""
    session_id: str = ""
    request_id: str = ""
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    agent_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {
            "timestamp": self.timestamp.isoformat(),
            "operation": self.operation,
            "provider": self.provider,
            "model": self.model,
            "cost_usd": self.cost_usd,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "source": self.source,
            "metadata": self.metadata,
            "idempotency_key": self.idempotency_key,
        }
        if self.agent_id:
            d["agent_id"] = self.agent_id
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CostLedgerEvent":
        if not isinstance(data, dict):
            raise TypeError("cost ledger event must be a JSON object")
        missing_fields = _REQUIRED_EVENT_FIELDS.difference(data)
        if missing_fields:
            raise ValueError("cost ledger event is missing required fields")
        return cls(
            timestamp=_validated_timestamp(data.get("timestamp")),
            operation=_validated_text_field(data, "operation"),
            provider=_validated_text_field(data, "provider"),
            model=_validated_text_field(data, "model"),
            cost_usd=_validated_cost(data.get("cost_usd", 0.0), field_name="cost_usd"),
            tokens_input=_validated_token_count(data.get("tokens_input", 0), field_name="tokens_input"),
            tokens_output=_validated_token_count(data.get("tokens_output", 0), field_name="tokens_output"),
            task_id=_validated_text_field(data, "task_id"),
            session_id=_validated_text_field(data, "session_id"),
            request_id=_validated_text_field(data, "request_id"),
            source=_validated_text_field(data, "source"),
            metadata=_validated_metadata(data.get("metadata")),
            idempotency_key=_validated_text_field(data, "idempotency_key"),
            agent_id=_validated_text_field(data, "agent_id"),
        )


class CostLedger:
    """Append-only cost ledger with idempotency support."""

    def __init__(
        self,
        ledger_path: Path | None = None,
        *,
        lock_timeout_seconds: float | None = None,
    ):
        self.ledger_path = ledger_path or default_cost_data_dir() / "cost_ledger.jsonl"
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._lock_timeout_seconds = _validated_lock_timeout(lock_timeout_seconds)
        self._idempotency_keys: set[str] = set()
        self._idempotency_events: dict[str, CostLedgerEvent] = {}
        self._idempotency_conflicts: set[str] = set()
        with self._interprocess_lock():
            self._load_idempotency_index()

    @contextmanager
    def _thread_lock(self, *, deadline: float | None = None) -> Iterator[None]:
        timeout = _remaining_timeout(deadline)
        if deadline is None:
            timeout = self._lock_timeout_seconds
        acquired = self._lock.acquire() if timeout is None else self._lock.acquire(timeout=timeout)
        if not acquired:
            raise CostLedgerLockTimeout("cost ledger lock unavailable within the configured timeout")
        try:
            yield
        finally:
            self._lock.release()

    @contextmanager
    def _interprocess_lock(self, *, deadline: float | None = None) -> Iterator[None]:
        """Serialize ledger reads and writes across Windows and POSIX processes."""
        timeout = _remaining_timeout(deadline)
        if deadline is None:
            timeout = self._lock_timeout_seconds
        lock_path = self.ledger_path.with_name(f"{self.ledger_path.name}.lock")
        with open(lock_path, "a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                mode = msvcrt.LK_LOCK if timeout is None else msvcrt.LK_NBLCK
                _acquire_os_lock(
                    lambda: _windows_region_lock(handle, msvcrt, mode),
                    timeout,
                )
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl: Any = importlib.import_module("fcntl")
                mode = fcntl.LOCK_EX if timeout is None else fcntl.LOCK_EX | fcntl.LOCK_NB
                _acquire_os_lock(
                    lambda: fcntl.flock(handle.fileno(), mode),
                    timeout,
                )
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _load_idempotency_index(self, *, fail_closed: bool = False) -> None:
        if not self.ledger_path.exists():
            return
        try:
            with open(self.ledger_path, encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    event = self._parse_index_event(line, line_no=line_no, fail_closed=fail_closed)
                    if event is not None:
                        self._index_idempotent_event(event)
        except OSError as e:
            logger.warning("Failed loading cost ledger index (%s)", type(e).__name__)
            if fail_closed:
                raise CostLedgerReadError("cost ledger idempotency index could not be read") from e

    @staticmethod
    def _parse_index_event(
        line: str,
        *,
        line_no: int,
        fail_closed: bool,
    ) -> CostLedgerEvent | None:
        try:
            return CostLedgerEvent.from_dict(_loads_strict_json(line))
        except (AttributeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error("Corrupted cost ledger line %d (%s)", line_no, type(exc).__name__)
            if fail_closed:
                raise CostLedgerReadError("cost ledger contains a malformed event") from exc
            return None

    def _index_idempotent_event(self, event: CostLedgerEvent) -> None:
        key = event.idempotency_key
        if not key:
            return
        self._idempotency_keys.add(key)
        existing = self._idempotency_events.get(key)
        if existing is None:
            self._idempotency_events[key] = event
        elif not _same_idempotent_cost_event(existing, event):
            self._idempotency_conflicts.add(key)
            logger.error("Conflicting cost ledger events reuse one idempotency key")

    def record_event(
        self,
        operation: str,
        provider: str,
        cost_usd: float,
        model: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        task_id: str = "",
        session_id: str = "",
        request_id: str = "",
        source: str = "",
        metadata: dict[str, Any] | None = None,
        idempotency_key: str = "",
        agent_id: str = "",
        lock_timeout_seconds: float | None = None,
        require_fsync: bool = False,
    ) -> tuple[CostLedgerEvent, bool]:
        cost_usd = _validated_cost(cost_usd, field_name="cost_usd")
        if not isinstance(require_fsync, bool):
            raise ValueError("require_fsync must be a boolean")
        timeout = self._lock_timeout_seconds
        if lock_timeout_seconds is not None:
            timeout = _validated_lock_timeout(lock_timeout_seconds)
        deadline = None if timeout is None else time.monotonic() + timeout

        event = CostLedgerEvent(
            operation=_validated_text_value(operation, field_name="operation"),
            provider=_validated_text_value(provider, field_name="provider"),
            cost_usd=cost_usd,
            model=_validated_text_value(model, field_name="model"),
            tokens_input=_validated_token_count(tokens_input, field_name="tokens_input"),
            tokens_output=_validated_token_count(tokens_output, field_name="tokens_output"),
            task_id=_validated_text_value(task_id, field_name="task_id"),
            session_id=_validated_text_value(session_id, field_name="session_id"),
            request_id=_validated_text_value(request_id, field_name="request_id"),
            source=_validated_text_value(source, field_name="source"),
            metadata=_validated_metadata(metadata),
            idempotency_key=_validated_text_value(idempotency_key, field_name="idempotency_key"),
            agent_id=_validated_text_value(agent_id, field_name="agent_id"),
        )

        with self._thread_lock(deadline=deadline):
            with self._interprocess_lock(deadline=deadline):
                return self._record_event_locked(event, require_fsync=require_fsync)

    def _record_event_locked(
        self,
        event: CostLedgerEvent,
        *,
        require_fsync: bool,
    ) -> tuple[CostLedgerEvent, bool]:
        self._idempotency_keys.clear()
        self._idempotency_events.clear()
        self._idempotency_conflicts.clear()
        self._load_idempotency_index(fail_closed=True)
        if self._idempotency_conflicts:
            raise CostLedgerIdempotencyConflict("cost ledger contains conflicting idempotency events")
        existing = self._matching_idempotent_event(event)
        if existing is not None:
            if require_fsync:
                self._require_durable_file()
            return existing, False
        self._append_event(event, require_fsync=require_fsync)
        self._index_idempotent_event(event)
        return event, True

    def _matching_idempotent_event(self, event: CostLedgerEvent) -> CostLedgerEvent | None:
        key = event.idempotency_key
        if not key or key not in self._idempotency_keys:
            return None
        existing = self._idempotency_events[key]
        if not _same_idempotent_cost_event(existing, event):
            raise CostLedgerIdempotencyConflict("idempotency key conflicts with an existing cost event")
        return existing

    def _append_event(self, event: CostLedgerEvent, *, require_fsync: bool) -> None:
        line = json.dumps(event.to_dict(), ensure_ascii=True, allow_nan=False)
        with open(self.ledger_path, "a", encoding="utf-8") as ledger_file:
            ledger_file.write(line + "\n")
            ledger_file.flush()
            try:
                os.fsync(ledger_file.fileno())
            except OSError as exc:
                if require_fsync:
                    raise CostLedgerDurabilityError("cost ledger durability could not be confirmed") from exc
                logger.debug("Cost ledger fsync unavailable: %s", type(exc).__name__)

    def _require_durable_file(self) -> None:
        """Reconfirm durability when a required append replays an existing key."""
        try:
            with open(self.ledger_path, "a+b") as ledger_file:
                os.fsync(ledger_file.fileno())
        except OSError as exc:
            raise CostLedgerDurabilityError("cost ledger durability could not be confirmed") from exc

    def get_events(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        source: str | None = None,
    ) -> list[CostLedgerEvent]:
        return self.with_locked_events(
            lambda events: events,
            start_date=start_date,
            end_date=end_date,
            source=source,
        )

    def get_attributed_events(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        source: str | None = None,
    ) -> list[CostLedgerEvent]:
        """Return the validated provider/model attribution derived view.

        Reconciliation is resolved over the complete locked ledger before the
        requested spend-period filter is applied. This keeps a later append-only
        correction effective for an earlier charge without moving the charge's
        timestamp or changing any dollar total.
        """
        from deepr.observability.cost_attribution import project_cost_attribution

        def project(events: list[CostLedgerEvent]) -> list[CostLedgerEvent]:
            attributed = project_cost_attribution(events)
            return [
                event
                for event in attributed
                if (source is None or event.source == source)
                and (start_date is None or event.timestamp >= start_date)
                and (end_date is None or event.timestamp <= end_date)
            ]

        return self.with_locked_events(project)

    def _get_events_unlocked(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        source: str | None = None,
    ) -> list[CostLedgerEvent]:
        events: list[CostLedgerEvent] = []
        if not self.ledger_path.exists():
            return events

        with open(self.ledger_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = _loads_strict_json(line)
                    event = CostLedgerEvent.from_dict(data)
                except (json.JSONDecodeError, TypeError, ValueError):
                    # Intent: one corrupted cost ledger line must not prevent loading the rest of the billing history; partial results still allow usage queries and caps.
                    continue

                if source and event.source != source:
                    continue
                if start_date and event.timestamp < start_date:
                    continue
                if end_date and event.timestamp > end_date:
                    continue
                events.append(event)

        return events

    def with_locked_events(
        self,
        operation: Callable[[list[CostLedgerEvent]], T],
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        source: str | None = None,
    ) -> T:
        """Run an operation against a stable snapshot under the ledger lock."""
        with self._thread_lock():
            with self._interprocess_lock():
                events = self._get_events_unlocked(start_date=start_date, end_date=end_date, source=source)
                return operation(events)

    def with_locked_accounting_events(
        self,
        operation: Callable[[list[CostLedgerEvent]], T],
        *,
        lock_timeout_seconds: float = 5.0,
    ) -> T:
        """Run a spend decision against one strict, locked ledger snapshot."""
        timeout = _validated_lock_timeout(lock_timeout_seconds)
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._thread_lock(deadline=deadline):
            with self._interprocess_lock(deadline=deadline):
                self._idempotency_keys.clear()
                self._idempotency_events.clear()
                self._idempotency_conflicts.clear()
                self._load_idempotency_index(fail_closed=True)
                if self._idempotency_conflicts:
                    raise CostLedgerIdempotencyConflict("cost ledger contains conflicting idempotency events")
                if self.ledger_path.exists():
                    self._require_durable_file()
                return operation(self._get_events_unlocked())

    def get_total_cost(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        source: str | None = None,
    ) -> float:
        return sum(e.cost_usd for e in self.get_events(start_date=start_date, end_date=end_date, source=source))

    def has_idempotency_key(self, idempotency_key: str) -> bool:
        """Check a canonical event key against a fresh locked ledger index."""
        if not idempotency_key:
            return False
        with self._thread_lock():
            with self._interprocess_lock():
                self._idempotency_keys.clear()
                self._idempotency_events.clear()
                self._idempotency_conflicts.clear()
                self._load_idempotency_index(fail_closed=True)
                return idempotency_key in self._idempotency_keys

    def get_health(self) -> dict[str, Any]:
        writable = False
        error = ""
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8"):
                pass
            writable = True
        except OSError as e:
            error = str(e)

        accounting_ready = False
        events: list[CostLedgerEvent] = []
        if writable:
            try:
                events = self.with_locked_accounting_events(list)
                accounting_ready = True
            except (
                CostLedgerDurabilityError,
                CostLedgerIdempotencyConflict,
                CostLedgerLockTimeout,
                CostLedgerReadError,
                OSError,
            ) as exc:
                error = error or f"{type(exc).__name__}: {exc}"
        if not accounting_ready:
            try:
                events = self.get_events()
            except (CostLedgerLockTimeout, OSError) as exc:
                error = error or f"{type(exc).__name__}: {exc}"
        return {
            "path": str(self.ledger_path),
            "exists": self.ledger_path.exists(),
            "writable": writable,
            "accounting_ready": accounting_ready,
            "event_count": len(events),
            "total_cost_usd": sum(e.cost_usd for e in events),
            "latest_timestamp": events[-1].timestamp.isoformat() if events else None,
            "idempotency_keys_loaded": len(self._idempotency_keys),
            "error": error,
        }


def _validated_lock_timeout(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError("lock_timeout_seconds must be finite and non-negative")
    return float(value)


def _remaining_timeout(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


def _validated_cost(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return numeric


def _validated_token_count(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _validated_text_value(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _validated_text_field(data: dict[str, Any], field_name: str) -> str:
    return _validated_text_value(data.get(field_name, ""), field_name=field_name)


def _validated_metadata(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object")
    return value


def _validated_timestamp(value: object) -> datetime:
    if value is None:
        return _utc_now()
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return timestamp


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value!r} is not allowed")


def _loads_strict_json(line: str) -> dict[str, Any]:
    data = json.loads(line, parse_constant=_reject_json_constant)
    if not isinstance(data, dict):
        raise TypeError("cost ledger event must be a JSON object")
    return data


def _same_idempotent_cost_event(existing: CostLedgerEvent, proposed: CostLedgerEvent) -> bool:
    """Compare event identity while ignoring only the append timestamp."""
    return (
        existing.operation == proposed.operation
        and existing.provider == proposed.provider
        and existing.cost_usd == proposed.cost_usd
        and existing.model == proposed.model
        and existing.tokens_input == proposed.tokens_input
        and existing.tokens_output == proposed.tokens_output
        and existing.task_id == proposed.task_id
        and existing.session_id == proposed.session_id
        and existing.request_id == proposed.request_id
        and existing.source == proposed.source
        and existing.metadata == proposed.metadata
        and existing.agent_id == proposed.agent_id
    )
