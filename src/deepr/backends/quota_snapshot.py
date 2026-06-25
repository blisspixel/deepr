"""Normalized quota snapshots for plan-capacity probes.

Live vendor probes report quota in different shapes: percentages, absolute
usage counts, rolling windows, weekly pools, stale cache snapshots, and
sometimes an error with no usable window. This module keeps that provider
surface deterministic and testable before a probe writes Deepr's append-only
quota ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from deepr.backends.capacity import CostModel
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedgerEvent,
    QuotaWindowKind,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _clamp_fraction(value: float) -> float:
    return min(1.0, max(0.0, value))


@dataclass(frozen=True)
class QuotaWindowSnapshot:
    """One provider-reported quota window.

    ``used_fraction`` is 0.0 to 1.0 when the provider reports percent used.
    ``units_used`` and ``units_limit`` cover providers that expose raw counts.
    If both forms are present, ``used_fraction`` wins because it is the
    provider's direct normalized signal.
    """

    label: str
    window_kind: QuotaWindowKind = QuotaWindowKind.UNKNOWN
    used_fraction: float | None = None
    units_used: float | None = None
    units_limit: float | None = None
    reset_at: datetime | None = None
    unit_name: str = "quota_unit"
    metadata: dict[str, Any] = field(default_factory=dict)

    def effective_used_fraction(self, *, now: datetime) -> float | None:
        """Return the current used fraction, treating past resets as fresh."""
        if self.reset_at is not None and self.reset_at <= now:
            return 0.0
        if self.used_fraction is not None:
            return _clamp_fraction(self.used_fraction)
        if self.units_used is None or self.units_limit is None or self.units_limit <= 0:
            return None
        return _clamp_fraction(self.units_used / self.units_limit)

    def remaining_fraction(self, *, now: datetime) -> float | None:
        used = self.effective_used_fraction(now=now)
        if used is None:
            return None
        return _clamp_fraction(1.0 - used)

    def effective_units_used(self, *, now: datetime) -> float | None:
        if self.reset_at is not None and self.reset_at <= now:
            return 0.0
        if self.units_used is not None:
            return self.units_used
        if self.used_fraction is not None and self.units_limit is not None:
            return self.units_limit * _clamp_fraction(self.used_fraction)
        return None

    def effective_units_remaining(self, *, now: datetime) -> float | None:
        if self.units_limit is None:
            return None
        used = self.effective_units_used(now=now)
        if used is None:
            return None
        return max(0.0, self.units_limit - used)

    def to_metadata(self, *, now: datetime) -> dict[str, Any]:
        return {
            "label": self.label,
            "window_kind": self.window_kind.value,
            "used_fraction": self.effective_used_fraction(now=now),
            "remaining_fraction": self.remaining_fraction(now=now),
            "units_used": self.effective_units_used(now=now),
            "units_limit": self.units_limit,
            "reset_at": self.reset_at.isoformat() if self.reset_at else None,
            "unit_name": self.unit_name,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class QuotaSnapshot:
    """One account's normalized quota observation before ledger persistence."""

    backend_id: str
    display_name: str
    account_id: str = ""
    plan: str | None = None
    cost_model: CostModel | None = None
    ok: bool = True
    error: str = ""
    windows: tuple[QuotaWindowSnapshot, ...] = ()
    as_of: datetime = field(default_factory=_utc_now)
    stale: bool = False
    overage_enabled: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_windows(self) -> bool:
        return bool(self.windows)


@dataclass(frozen=True)
class QuotaAvailability:
    """Usability summary derived from a quota snapshot."""

    available: bool
    headroom_fraction: float | None
    binding_window: QuotaWindowSnapshot | None
    reset_at: datetime | None
    reason: str


def window_headroom(window: QuotaWindowSnapshot, *, now: datetime) -> float | None:
    """Remaining fraction for one window, with reset rollover applied."""
    return window.remaining_fraction(now=now)


def binding_window(snapshot: QuotaSnapshot, *, now: datetime | None = None) -> QuotaWindowSnapshot | None:
    """Return the usable window with the lowest remaining fraction."""
    stamp = now or _utc_now()
    worst: QuotaWindowSnapshot | None = None
    worst_headroom = 1.1
    for window in snapshot.windows:
        headroom = window_headroom(window, now=stamp)
        if headroom is None:
            continue
        if headroom < worst_headroom:
            worst = window
            worst_headroom = headroom
    return worst


def snapshot_headroom(snapshot: QuotaSnapshot, *, now: datetime | None = None) -> float | None:
    """Remaining headroom for a provider, governed by its tightest window."""
    stamp = now or _utc_now()
    window = binding_window(snapshot, now=stamp)
    if window is None:
        return None
    return window_headroom(window, now=stamp)


def snapshot_availability(
    snapshot: QuotaSnapshot,
    *,
    now: datetime | None = None,
    minimum_headroom_fraction: float = 0.005,
) -> QuotaAvailability:
    """Return conservative availability from a normalized quota snapshot."""
    stamp = now or _utc_now()
    if not snapshot.ok:
        return QuotaAvailability(
            available=False,
            headroom_fraction=None,
            binding_window=None,
            reset_at=None,
            reason=snapshot.error or "quota probe failed",
        )

    window = binding_window(snapshot, now=stamp)
    if window is None:
        return QuotaAvailability(
            available=False,
            headroom_fraction=None,
            binding_window=None,
            reset_at=None,
            reason="no usable quota windows reported",
        )

    headroom = window_headroom(window, now=stamp)
    available = headroom is not None and headroom > minimum_headroom_fraction
    reason = "quota available" if available else "quota exhausted"
    return QuotaAvailability(
        available=available,
        headroom_fraction=headroom,
        binding_window=window,
        reset_at=window.reset_at,
        reason=reason,
    )


def snapshot_to_ledger_event(
    snapshot: QuotaSnapshot,
    *,
    now: datetime | None = None,
    reserve_floor_fraction: float | None = None,
) -> QuotaLedgerEvent:
    """Convert a provider snapshot into one conservative quota ledger event.

    The event uses the binding window because that is the only value the
    waterfall needs to decide whether a backend may receive work. The complete
    window list is preserved in metadata for display and later auditing.
    """
    stamp = now or _utc_now()
    availability = snapshot_availability(snapshot, now=stamp)
    window = availability.binding_window

    event_type = QuotaEventType.USAGE_OBSERVED
    if not snapshot.ok or window is None:
        event_type = QuotaEventType.WINDOW_OBSERVED
    elif availability.headroom_fraction is not None and availability.headroom_fraction <= 0.0:
        event_type = QuotaEventType.EXHAUSTED

    metadata: dict[str, Any] = {
        "display_name": snapshot.display_name,
        "plan": snapshot.plan,
        "snapshot_as_of": snapshot.as_of.isoformat(),
        "snapshot_stale": snapshot.stale,
        "snapshot_ok": snapshot.ok,
        "headroom_fraction": availability.headroom_fraction,
        "binding_window_label": window.label if window else None,
        "quota_windows": [w.to_metadata(now=stamp) for w in snapshot.windows],
        **snapshot.metadata,
    }
    if window and window.units_limit is not None:
        metadata["units_total"] = window.units_limit

    detail = availability.reason
    if snapshot.error and snapshot.error not in detail:
        detail = f"{detail}: {snapshot.error}" if detail else snapshot.error

    return QuotaLedgerEvent(
        backend_id=snapshot.backend_id,
        account_id=snapshot.account_id,
        event_type=event_type,
        timestamp=stamp,
        cost_model=snapshot.cost_model,
        window_kind=window.window_kind if window else QuotaWindowKind.UNKNOWN,
        units_used=window.effective_units_used(now=stamp) if window else None,
        units_remaining=window.effective_units_remaining(now=stamp) if window else None,
        unit_name=window.unit_name if window else "quota_unit",
        remaining_confidence=QuotaConfidence.VENDOR_REPORTED if window else QuotaConfidence.UNKNOWN,
        reset_at=availability.reset_at,
        reserve_floor_fraction=reserve_floor_fraction,
        overage_enabled=snapshot.overage_enabled,
        detail=detail,
        metadata=metadata,
    )
