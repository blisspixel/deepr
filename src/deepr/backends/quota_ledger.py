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
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

from deepr.backends.admission import default_capacity_data_dir
from deepr.backends.capacity import CostModel


def _utc_now() -> datetime:
    return datetime.now(UTC)


def quota_ledger_path(path: Path | None = None) -> Path:
    """Resolve the quota ledger path, honoring explicit test/deployment paths."""
    return path or default_capacity_data_dir() / "quota_ledger.jsonl"


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
        )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


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

    def __init__(self, ledger_path: Path | None = None):
        self.ledger_path = quota_ledger_path(ledger_path)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record_event(self, event: QuotaLedgerEvent) -> QuotaLedgerEvent:
        if not event.backend_id.strip():
            raise ValueError("backend_id is required")

        with self._lock:
            line = json.dumps(event.to_dict(), ensure_ascii=True)
            with self.ledger_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                with suppress(OSError):
                    os.fsync(f.fileno())
        return event

    def get_events(
        self,
        *,
        backend_id: str | None = None,
        account_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[QuotaLedgerEvent]:
        events: list[QuotaLedgerEvent] = []
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
