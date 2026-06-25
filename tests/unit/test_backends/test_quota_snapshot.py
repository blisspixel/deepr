"""Tests for normalized plan-quota snapshots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deepr.backends.capacity import CostModel
from deepr.backends.quota_ledger import QuotaConfidence, QuotaEventType, QuotaWindowKind
from deepr.backends.quota_snapshot import (
    QuotaSnapshot,
    QuotaWindowSnapshot,
    binding_window,
    snapshot_availability,
    snapshot_headroom,
    snapshot_to_ledger_event,
)

T0 = datetime(2026, 6, 25, 12, tzinfo=UTC)


def _window(
    label: str = "5h",
    *,
    used_fraction: float | None = 0.25,
    units_used: float | None = None,
    units_limit: float | None = None,
    reset_at: datetime | None = None,
    window_kind: QuotaWindowKind = QuotaWindowKind.ROLLING_5H,
) -> QuotaWindowSnapshot:
    return QuotaWindowSnapshot(
        label=label,
        window_kind=window_kind,
        used_fraction=used_fraction,
        units_used=units_used,
        units_limit=units_limit,
        reset_at=reset_at,
        unit_name="request",
    )


def _snapshot(*windows: QuotaWindowSnapshot, ok: bool = True, error: str = "") -> QuotaSnapshot:
    return QuotaSnapshot(
        backend_id="codex",
        display_name="Codex",
        account_id="nick",
        plan="pro",
        cost_model=CostModel.ROLLING_WINDOW,
        ok=ok,
        error=error,
        windows=windows,
        as_of=T0,
    )


class TestQuotaWindowSnapshot:
    def test_percent_window_reports_remaining_fraction(self):
        window = _window(used_fraction=0.62)
        assert window.effective_used_fraction(now=T0) == 0.62
        assert window.remaining_fraction(now=T0) == 0.38

    def test_absolute_counts_derive_fraction(self):
        window = _window(used_fraction=None, units_used=30, units_limit=120)
        assert window.effective_used_fraction(now=T0) == 0.25
        assert window.effective_units_remaining(now=T0) == 90

    def test_past_reset_is_treated_as_fresh(self):
        window = _window(used_fraction=0.99, units_used=99, units_limit=100, reset_at=T0 - timedelta(minutes=1))
        assert window.effective_used_fraction(now=T0) == 0.0
        assert window.effective_units_used(now=T0) == 0.0
        assert window.effective_units_remaining(now=T0) == 100.0

    def test_future_reset_does_not_clear_usage(self):
        window = _window(used_fraction=0.99, units_used=99, units_limit=100, reset_at=T0 + timedelta(minutes=1))
        assert window.remaining_fraction(now=T0) == 0.010000000000000009
        assert window.effective_units_remaining(now=T0) == 1


class TestSnapshotHeadroom:
    def test_binding_window_is_most_constrained_window(self):
        five_hour = _window("5h", used_fraction=0.40)
        weekly = _window("weekly", used_fraction=0.98, window_kind=QuotaWindowKind.WEEKLY)
        snap = _snapshot(five_hour, weekly)

        assert binding_window(snap, now=T0) == weekly
        assert snapshot_headroom(snap, now=T0) == pytest.approx(0.02)

    def test_unknown_windows_are_ignored_for_binding(self):
        unknown = _window("unknown", used_fraction=None, units_used=None, units_limit=None)
        usable = _window("weekly", used_fraction=0.5, window_kind=QuotaWindowKind.WEEKLY)
        snap = _snapshot(unknown, usable)

        assert binding_window(snap, now=T0) == usable
        assert snapshot_headroom(snap, now=T0) == 0.5

    def test_snapshot_without_usable_windows_has_no_headroom(self):
        snap = _snapshot(_window(used_fraction=None, units_used=None, units_limit=None))
        availability = snapshot_availability(snap, now=T0)

        assert snapshot_headroom(snap, now=T0) is None
        assert not availability.available
        assert availability.reason == "no usable quota windows reported"

    def test_failed_probe_is_unavailable_even_with_no_windows(self):
        snap = _snapshot(ok=False, error="token expired")
        availability = snapshot_availability(snap, now=T0)

        assert not availability.available
        assert availability.headroom_fraction is None
        assert availability.reason == "token expired"


class TestLedgerConversion:
    def test_snapshot_to_event_uses_binding_window_and_preserves_all_windows(self):
        five_hour = _window("5h", used_fraction=0.4, units_used=40, units_limit=100)
        weekly = _window("weekly", used_fraction=0.9, window_kind=QuotaWindowKind.WEEKLY)
        event = snapshot_to_ledger_event(_snapshot(five_hour, weekly), now=T0, reserve_floor_fraction=0.1)

        assert event.backend_id == "codex"
        assert event.account_id == "nick"
        assert event.event_type == QuotaEventType.USAGE_OBSERVED
        assert event.remaining_confidence == QuotaConfidence.VENDOR_REPORTED
        assert event.window_kind == QuotaWindowKind.WEEKLY
        assert event.units_used is None
        assert event.units_remaining is None
        assert event.reserve_floor_fraction == 0.1
        assert event.metadata["headroom_fraction"] == pytest.approx(0.1)
        assert event.metadata["binding_window_label"] == "weekly"
        assert [w["label"] for w in event.metadata["quota_windows"]] == ["5h", "weekly"]

    def test_exhausted_snapshot_becomes_exhausted_event(self):
        event = snapshot_to_ledger_event(_snapshot(_window(used_fraction=1.0)), now=T0)

        assert event.event_type == QuotaEventType.EXHAUSTED
        assert event.detail == "quota exhausted"

    def test_error_snapshot_becomes_unknown_window_event(self):
        event = snapshot_to_ledger_event(_snapshot(ok=False, error="auth failed"), now=T0)

        assert event.event_type == QuotaEventType.WINDOW_OBSERVED
        assert event.remaining_confidence == QuotaConfidence.UNKNOWN
        assert event.window_kind == QuotaWindowKind.UNKNOWN
        assert event.detail == "auth failed"

    def test_absolute_counts_set_units_total_for_reserve_floor(self):
        event = snapshot_to_ledger_event(
            _snapshot(_window(used_fraction=None, units_used=90, units_limit=100)),
            now=T0,
            reserve_floor_fraction=0.2,
        )

        assert event.units_used == 90
        assert event.units_remaining == 10
        assert event.metadata["units_total"] == 100
