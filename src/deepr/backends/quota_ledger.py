"""Append-only quota observations for plan-capacity backends.

Plan quota is prepaid capacity, not free capacity. Vendor CLIs and credit
programs rarely expose perfect remaining quota, so Deepr records observations
instead of assuming limits: window sightings, usage reports, exhaustion
signals, overage state, and quarantine decisions. Future adapters and
schedulers consume this ledger before considering a plan backend available.

The ledger is machine-local, like local admissions, because authenticated CLI
state and quota windows are per machine/account. It honors
``DEEPR_CAPACITY_DATA_DIR`` and defaults to ``data/capacity/quota_ledger.jsonl``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import Any, TypeVar

from filelock import FileLock
from filelock import Timeout as FileLockTimeout

from deepr.backends.admission import default_capacity_data_dir
from deepr.backends.capacity import CostModel

_PATH_LOCKS: dict[Path, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()
_CANONICAL_EVENT_FIELDS = {
    "timestamp",
    "backend_id",
    "account_id",
    "event_type",
    "cost_model",
    "window_kind",
    "units_used",
    "units_remaining",
    "unit_name",
    "remaining_confidence",
    "window_start",
    "window_end",
    "reset_at",
    "reserve_floor_fraction",
    "overage_enabled",
    "detail",
    "metadata",
    "idempotency_key",
}
_PRE_IDEMPOTENCY_EVENT_FIELDS = _CANONICAL_EVENT_FIELDS - {"idempotency_key"}


class QuotaLedgerLockTimeout(TimeoutError):
    """A bounded quota-ledger lock attempt expired."""


class QuotaLedgerStorageError(RuntimeError):
    """Quota-ledger storage failed without exposing its configured path."""


class QuotaLedgerLockError(QuotaLedgerStorageError):
    """The quota ledger's interprocess lock could not be acquired."""


class QuotaLedgerReadError(QuotaLedgerStorageError):
    """The quota ledger could not be parsed safely before an append."""


class QuotaLedgerWriteError(QuotaLedgerStorageError):
    """The quota ledger could not accept a complete append."""


class QuotaLedgerDurabilityError(QuotaLedgerStorageError):
    """A required quota-ledger durability barrier failed."""


class QuotaLedgerIdempotencyConflict(ValueError):
    """An idempotency key was reused for a different quota observation."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def quota_ledger_path(path: Path | None = None) -> Path:
    """Resolve the quota ledger path, honoring explicit test/deployment paths."""
    return path or default_capacity_data_dir() / "quota_ledger.jsonl"


def _shared_path_lock(path: Path) -> threading.Lock:
    """Return one process-local lock for every resolved ledger path."""
    resolved = path.resolve()
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(resolved, threading.Lock())


class QuotaWindowKind(str, Enum):
    """Observed quota-window shape."""

    UNKNOWN = "unknown"
    ROLLING_5H = "rolling_5h"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY_CREDIT_POOL = "monthly_credit_pool"


class QuotaEventType(str, Enum):
    """What an adapter observed about a quota source."""

    WINDOW_OBSERVED = "window_observed"
    ATTEMPT_OBSERVED = "attempt_observed"
    USAGE_OBSERVED = "usage_observed"
    EXHAUSTED = "exhausted"
    RESET_OBSERVED = "reset_observed"
    OVERAGE_STATE_OBSERVED = "overage_state_observed"
    QUARANTINED = "quarantined"


class QuotaConfidence(str, Enum):
    """How trustworthy ``units_remaining`` is."""

    VENDOR_REPORTED = "vendor_reported"
    OBSERVED = "observed"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


EnumT = TypeVar("EnumT", bound=Enum)


def _enum_or_default(enum_type: type[EnumT], value: object, default: EnumT) -> EnumT:
    try:
        return enum_type(str(value))
    except ValueError:
        return default


def _cost_model_or_none(value: object) -> CostModel | None:
    if value is None:
        return None
    try:
        return CostModel(str(value))
    except ValueError:
        return None


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value))


def _dt_to_str(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


@dataclass(frozen=True)
class QuotaLedgerEvent:
    """One immutable quota observation for a backend/account pair."""

    backend_id: str
    event_type: QuotaEventType
    timestamp: datetime = field(default_factory=_utc_now)
    account_id: str = ""
    cost_model: CostModel | None = None
    window_kind: QuotaWindowKind = QuotaWindowKind.UNKNOWN
    units_used: float | None = None
    units_remaining: float | None = None
    unit_name: str = "unknown"
    remaining_confidence: QuotaConfidence = QuotaConfidence.UNKNOWN
    window_start: datetime | None = None
    window_end: datetime | None = None
    reset_at: datetime | None = None
    reserve_floor_fraction: float | None = None
    overage_enabled: bool | None = None
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "backend_id": self.backend_id,
            "account_id": self.account_id,
            "event_type": self.event_type.value,
            "cost_model": self.cost_model.value if self.cost_model else None,
            "window_kind": self.window_kind.value,
            "units_used": self.units_used,
            "units_remaining": self.units_remaining,
            "unit_name": self.unit_name,
            "remaining_confidence": self.remaining_confidence.value,
            "window_start": _dt_to_str(self.window_start),
            "window_end": _dt_to_str(self.window_end),
            "reset_at": _dt_to_str(self.reset_at),
            "reserve_floor_fraction": self.reserve_floor_fraction,
            "overage_enabled": self.overage_enabled,
            "detail": self.detail,
            "metadata": self.metadata,
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuotaLedgerEvent:
        return cls(
            timestamp=_parse_dt(data.get("timestamp")) or _utc_now(),
            backend_id=str(data["backend_id"]),
            account_id=str(data.get("account_id", "")),
            event_type=_enum_or_default(
                QuotaEventType,
                data.get("event_type"),
                QuotaEventType.USAGE_OBSERVED,
            ),
            cost_model=_cost_model_or_none(data.get("cost_model")),
            window_kind=_enum_or_default(
                QuotaWindowKind,
                data.get("window_kind"),
                QuotaWindowKind.UNKNOWN,
            ),
            units_used=_optional_float(data.get("units_used")),
            units_remaining=_optional_float(data.get("units_remaining")),
            unit_name=str(data.get("unit_name", "unknown")),
            remaining_confidence=_enum_or_default(
                QuotaConfidence,
                data.get("remaining_confidence"),
                QuotaConfidence.UNKNOWN,
            ),
            window_start=_parse_dt(data.get("window_start")),
            window_end=_parse_dt(data.get("window_end")),
            reset_at=_parse_dt(data.get("reset_at")),
            reserve_floor_fraction=_optional_float(data.get("reserve_floor_fraction")),
            overage_enabled=_optional_bool(data.get("overage_enabled")),
            detail=str(data.get("detail", "")),
            metadata=_metadata_or_empty(data.get("metadata")),
            idempotency_key=str(data.get("idempotency_key", "") or ""),
        )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise TypeError("quota numeric field must be an int, float, or string")
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError("quota numeric field must be finite")
    return parsed


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"true", "1", "yes"}:
            return True
        if lower in {"false", "0", "no"}:
            return False
    return bool(value)


def _metadata_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class QuotaState:
    """Latest known quota state for one backend/account pair."""

    backend_id: str
    account_id: str
    latest_event: QuotaLedgerEvent
    exhausted: bool
    quarantined: bool

    @property
    def key(self) -> str:
        return f"{self.backend_id}:{self.account_id}" if self.account_id else self.backend_id

    def to_dict(self) -> dict[str, Any]:
        e = self.latest_event
        return {
            "backend_id": self.backend_id,
            "account_id": self.account_id,
            "event_type": e.event_type.value,
            "timestamp": e.timestamp.isoformat(),
            "cost_model": e.cost_model.value if e.cost_model else None,
            "window_kind": e.window_kind.value,
            "units_used": e.units_used,
            "units_remaining": e.units_remaining,
            "unit_name": e.unit_name,
            "remaining_confidence": e.remaining_confidence.value,
            "reset_at": _dt_to_str(e.reset_at),
            "reserve_floor_fraction": e.reserve_floor_fraction,
            "overage_enabled": e.overage_enabled,
            "exhausted": self.exhausted,
            "quarantined": self.quarantined,
            "detail": e.detail,
        }


class QuotaLedger:
    """Durable append-only quota ledger."""

    def __init__(
        self,
        ledger_path: Path | None = None,
        *,
        lock_timeout_seconds: float | None = None,
    ):
        self.ledger_path = quota_ledger_path(ledger_path)
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise QuotaLedgerWriteError("quota ledger parent directory could not be created") from error
        self._lock = _shared_path_lock(self.ledger_path)
        resolved_path = self.ledger_path.resolve()
        self._file_lock = FileLock(str(resolved_path.with_name(f"{resolved_path.name}.lock")))
        self._lock_timeout_seconds = _validated_lock_timeout(lock_timeout_seconds)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        timeout = self._lock_timeout_seconds
        if timeout is None:
            with self._lock:
                try:
                    self._file_lock.acquire()
                except OSError as error:
                    raise QuotaLedgerLockError("quota ledger lock could not be acquired") from error
                try:
                    yield
                finally:
                    try:
                        self._file_lock.release()
                    except OSError as error:
                        raise QuotaLedgerLockError("quota ledger lock could not be released") from error
            return

        started = time.monotonic()
        if not self._lock.acquire(timeout=timeout):
            raise QuotaLedgerLockTimeout("quota ledger lock unavailable within the configured timeout")
        try:
            remaining = max(0.0, timeout - (time.monotonic() - started))
            try:
                self._file_lock.acquire(timeout=remaining)
            except FileLockTimeout as error:
                raise QuotaLedgerLockTimeout("quota ledger lock unavailable within the configured timeout") from error
            except OSError as error:
                raise QuotaLedgerLockError("quota ledger lock could not be acquired") from error
            try:
                yield
            finally:
                try:
                    self._file_lock.release()
                except OSError as error:
                    raise QuotaLedgerLockError("quota ledger lock could not be released") from error
        finally:
            self._lock.release()

    def record_event(
        self,
        event: QuotaLedgerEvent,
        *,
        require_fsync: bool = False,
    ) -> QuotaLedgerEvent:
        _validate_record_request(event, require_fsync=require_fsync)
        line = _serialize_event(event)

        with self._locked():
            matching_event = self._find_idempotent_event(event)
            if matching_event is not None:
                return self._accept_replay(
                    matching_event,
                    require_fsync=require_fsync,
                )
            self._append_line(line, require_fsync=require_fsync)
        return event

    def _accept_replay(
        self,
        matching_event: QuotaLedgerEvent,
        *,
        require_fsync: bool,
    ) -> QuotaLedgerEvent:
        if require_fsync:
            self._require_existing_durability()
        return matching_event

    def _append_line(self, line: str, *, require_fsync: bool) -> None:
        try:
            with self.ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                if require_fsync:
                    self._require_handle_durability(handle)
        except QuotaLedgerDurabilityError:
            raise
        except OSError as error:
            raise QuotaLedgerWriteError("quota ledger append failed") from error

    @staticmethod
    def _require_handle_durability(handle: Any) -> None:
        try:
            os.fsync(handle.fileno())
        except OSError as error:
            raise QuotaLedgerDurabilityError("quota ledger durability barrier failed") from error

    def _find_idempotent_event(self, proposed: QuotaLedgerEvent) -> QuotaLedgerEvent | None:
        """Scan strictly before append so corruption cannot bypass replay safety."""
        if not self.ledger_path.exists():
            return None
        matching_event: QuotaLedgerEvent | None = None
        try:
            with self.ledger_path.open(encoding="utf-8") as existing_file:
                for line_no, raw_line in enumerate(existing_file, start=1):
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line, parse_constant=_reject_json_constant)
                        if not isinstance(data, dict):
                            raise TypeError("quota ledger record must be an object")
                        _validate_accounting_record_shape(data)
                        existing = QuotaLedgerEvent.from_dict(data)
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                        raise QuotaLedgerReadError(
                            f"quota ledger contains an invalid record at line {line_no}"
                        ) from error
                    if not proposed.idempotency_key or existing.idempotency_key != proposed.idempotency_key:
                        continue
                    if not _same_idempotent_observation(existing, proposed):
                        raise QuotaLedgerIdempotencyConflict(
                            "idempotency key conflicts with an existing quota observation"
                        )
                    matching_event = existing
        except QuotaLedgerReadError:
            raise
        except (OSError, UnicodeError) as error:
            raise QuotaLedgerReadError("quota ledger could not be read before append") from error
        return matching_event

    def _require_existing_durability(self) -> None:
        """Retry the durability barrier before accepting an existing replay."""
        try:
            with self.ledger_path.open("a", encoding="utf-8") as handle:
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as error:
            raise QuotaLedgerDurabilityError("quota ledger durability barrier failed") from error

    def get_events(
        self,
        *,
        backend_id: str | None = None,
        account_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[QuotaLedgerEvent]:
        events: list[QuotaLedgerEvent] = []
        with self._locked():
            if not self.ledger_path.exists():
                return events
            with self.ledger_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = QuotaLedgerEvent.from_dict(json.loads(line))
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                        continue

                    if backend_id and event.backend_id != backend_id:
                        continue
                    if account_id is not None and event.account_id != account_id:
                        continue
                    if start_date and event.timestamp < start_date:
                        continue
                    if end_date and event.timestamp > end_date:
                        continue
                    events.append(event)

        return events

    def latest_by_backend(self) -> dict[tuple[str, str], QuotaLedgerEvent]:
        latest: dict[tuple[str, str], QuotaLedgerEvent] = {}
        for event in self.get_events():
            key = (event.backend_id, event.account_id)
            prev = latest.get(key)
            if prev is None or event.timestamp >= prev.timestamp:
                latest[key] = event
        return latest

    def summarize(self) -> list[QuotaState]:
        states = []
        for (backend_id, account_id), event in self.latest_by_backend().items():
            states.append(
                QuotaState(
                    backend_id=backend_id,
                    account_id=account_id,
                    latest_event=event,
                    exhausted=event.event_type == QuotaEventType.EXHAUSTED,
                    quarantined=event.event_type == QuotaEventType.QUARANTINED,
                )
            )
        return sorted(states, key=lambda state: state.key)


def record_quota_event(event: QuotaLedgerEvent, *, path: Path | None = None) -> QuotaLedgerEvent:
    return QuotaLedger(path).record_event(event)


def load_quota_events(path: Path | None = None) -> list[QuotaLedgerEvent]:
    return QuotaLedger(path).get_events()


def latest_quota_by_backend(path: Path | None = None) -> dict[tuple[str, str], QuotaLedgerEvent]:
    return QuotaLedger(path).latest_by_backend()


def summarize_quota_state(path: Path | None = None) -> list[QuotaState]:
    return QuotaLedger(path).summarize()


def _validated_lock_timeout(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError("lock_timeout_seconds must be finite and non-negative")
    return float(value)


def _validate_accounting_record_shape(data: dict[str, Any]) -> None:
    """Reject shapes that could make an idempotency scan misclassify a row."""
    _validate_canonical_record_header(data)
    _validate_canonical_quota_fields(data)
    _validate_canonical_window_fields(data)
    _validate_canonical_identity_fields(data)


def _validate_canonical_record_header(data: dict[str, Any]) -> None:
    if not _PRE_IDEMPOTENCY_EVENT_FIELDS.issubset(data):
        raise ValueError("quota ledger record is incomplete")
    backend_id = data.get("backend_id")
    if not isinstance(backend_id, str) or not backend_id.strip():
        raise ValueError("quota ledger backend_id must be a non-empty string")
    timestamp = data.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp:
        raise ValueError("quota ledger timestamp must be a non-empty string")
    event_type = data.get("event_type")
    if not isinstance(event_type, str):
        raise TypeError("quota ledger event_type must be a string")
    try:
        QuotaEventType(event_type)
    except ValueError as error:
        raise ValueError("quota ledger event_type is unknown") from error


def _validate_canonical_quota_fields(data: dict[str, Any]) -> None:
    account_id = data.get("account_id")
    if not isinstance(account_id, str):
        raise TypeError("quota ledger account_id must be a string")
    _validate_optional_enum(data.get("cost_model"), CostModel, field_name="cost_model")
    _validate_required_enum(data.get("window_kind"), QuotaWindowKind, field_name="window_kind")
    _validate_optional_raw_number(data.get("units_used"), field_name="units_used")
    _validate_optional_raw_number(data.get("units_remaining"), field_name="units_remaining")
    unit_name = data.get("unit_name")
    if not isinstance(unit_name, str):
        raise TypeError("quota ledger unit_name must be a string")
    _validate_required_enum(
        data.get("remaining_confidence"),
        QuotaConfidence,
        field_name="remaining_confidence",
    )


def _validate_canonical_window_fields(data: dict[str, Any]) -> None:
    for field_name in ("window_start", "window_end", "reset_at"):
        value = data.get(field_name)
        if value is not None and not isinstance(value, str):
            raise TypeError(f"quota ledger {field_name} must be a string or null")
    _validate_optional_raw_number(
        data.get("reserve_floor_fraction"),
        field_name="reserve_floor_fraction",
    )
    overage_enabled = data.get("overage_enabled")
    if overage_enabled is not None and not isinstance(overage_enabled, bool):
        raise TypeError("quota ledger overage_enabled must be a boolean or null")
    detail = data.get("detail")
    if not isinstance(detail, str):
        raise TypeError("quota ledger detail must be a string")


def _validate_canonical_identity_fields(data: dict[str, Any]) -> None:
    idempotency_key = data.get("idempotency_key", "")
    if not isinstance(idempotency_key, str):
        raise TypeError("quota ledger idempotency_key must be a string")
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise TypeError("quota ledger metadata must be an object")
    if idempotency_key and not _CANONICAL_EVENT_FIELDS.issubset(data):
        raise ValueError("idempotent quota ledger record is incomplete")


def _validate_record_request(event: QuotaLedgerEvent, *, require_fsync: bool) -> None:
    if not isinstance(event.backend_id, str) or not event.backend_id.strip():
        raise ValueError("backend_id is required")
    if not isinstance(event.idempotency_key, str):
        raise TypeError("idempotency_key must be a string")
    if not isinstance(require_fsync, bool):
        raise TypeError("require_fsync must be a boolean")
    _validate_proposed_event(event)


def _serialize_event(event: QuotaLedgerEvent) -> str:
    try:
        return json.dumps(event.to_dict(), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("quota event must be JSON serializable with finite values") from error


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant is not allowed: {value}")


def _validate_optional_raw_number(value: object, *, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"quota ledger {field_name} must be numeric or null")
    if not isfinite(value):
        raise ValueError(f"quota ledger {field_name} must be finite")


def _validate_required_enum(
    value: object,
    enum_type: type[EnumT],
    *,
    field_name: str,
) -> None:
    if not isinstance(value, str):
        raise TypeError(f"quota ledger {field_name} must be a string")
    try:
        enum_type(value)
    except ValueError as error:
        raise ValueError(f"quota ledger {field_name} is unknown") from error


def _validate_optional_enum(
    value: object,
    enum_type: type[EnumT],
    *,
    field_name: str,
) -> None:
    if value is None:
        return
    _validate_required_enum(value, enum_type, field_name=field_name)


def _validate_proposed_event(event: QuotaLedgerEvent) -> None:
    for field_name in (
        "units_used",
        "units_remaining",
        "reserve_floor_fraction",
    ):
        value = getattr(event, field_name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{field_name} must be an int or float")
        if not isfinite(value):
            raise ValueError(f"{field_name} must be finite")


def _same_idempotent_observation(existing: QuotaLedgerEvent, proposed: QuotaLedgerEvent) -> bool:
    """Compare quota-event identity while ignoring timestamp and prose detail."""
    return (
        existing.backend_id == proposed.backend_id
        and existing.account_id == proposed.account_id
        and existing.event_type == proposed.event_type
        and existing.cost_model == proposed.cost_model
        and existing.window_kind == proposed.window_kind
        and existing.units_used == proposed.units_used
        and existing.units_remaining == proposed.units_remaining
        and existing.unit_name == proposed.unit_name
        and existing.remaining_confidence == proposed.remaining_confidence
        and existing.window_start == proposed.window_start
        and existing.window_end == proposed.window_end
        and existing.reset_at == proposed.reset_at
        and existing.reserve_floor_fraction == proposed.reserve_floor_fraction
        and existing.overage_enabled == proposed.overage_enabled
        and existing.metadata == proposed.metadata
    )
