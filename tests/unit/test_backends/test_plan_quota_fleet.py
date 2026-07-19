"""Tests for the plan-quota fleet status view (read-only, $0)."""

from __future__ import annotations

from datetime import UTC, datetime

from deepr.backends.capacity import CostModel
from deepr.backends.plan_quota.fleet import (
    FLEET_KIND,
    FLEET_SCHEMA_VERSION,
    build_fleet_payload,
    build_fleet_status,
)
from deepr.backends.quota_ledger import (
    QuotaConfidence,
    QuotaEventType,
    QuotaLedger,
    QuotaLedgerEvent,
    QuotaWindowKind,
)

T0 = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)


def _which(*present):
    found = set(present)
    return lambda exe: f"/usr/bin/{exe}" if exe in found else None


def _record(path, backend_id, event_type, *, reset_at=None, ts=T0):
    QuotaLedger(path).record_event(
        QuotaLedgerEvent(
            backend_id=backend_id,
            event_type=event_type,
            timestamp=ts,
            cost_model=CostModel.ROLLING_WINDOW,
            window_kind=QuotaWindowKind.ROLLING_5H,
            remaining_confidence=QuotaConfidence.UNKNOWN,
            reset_at=reset_at,
        )
    )


def _row(rows, backend):
    return next(r for r in rows if r["backend"] == backend)


class TestFleetStatus:
    def test_all_seven_backends_listed(self, tmp_path):
        rows = build_fleet_status(which=_which(), env={}, quota_ledger_path=tmp_path / "q.jsonl")
        assert {r["backend"] for r in rows} == {"codex", "claude", "opencode", "kiro", "grok", "antigravity", "copilot"}

    def test_installed_reflects_path(self, tmp_path):
        rows = build_fleet_status(which=_which("codex"), env={}, quota_ledger_path=tmp_path / "q.jsonl")
        assert _row(rows, "codex")["installed"] is True
        assert _row(rows, "claude")["installed"] is False

    def test_auth_mode_truthfully_reports_metered_key_when_present(self, tmp_path):
        rows = build_fleet_status(
            which=_which("codex"), env={"OPENAI_API_KEY": "sk-x"}, quota_ledger_path=tmp_path / "q.jsonl"
        )
        assert _row(rows, "codex")["auth_mode"] == "metered"
        assert _row(rows, "codex")["raw_auth_mode"] == "metered"

    def test_auth_mode_reports_unverified_stored_provider_as_unknown(self, tmp_path):
        rows = build_fleet_status(which=_which("opencode"), env={}, quota_ledger_path=tmp_path / "q.jsonl")
        assert _row(rows, "opencode")["auth_mode"] == "unknown"
        assert _row(rows, "opencode")["raw_auth_mode"] == "unknown"

    def test_auth_mode_plan_when_clean(self, tmp_path):
        rows = build_fleet_status(which=_which("codex"), env={}, quota_ledger_path=tmp_path / "q.jsonl")
        assert _row(rows, "codex")["auth_mode"] == "plan"
        assert _row(rows, "codex")["raw_auth_mode"] == "plan"

    def test_auth_mode_none_when_not_installed(self, tmp_path):
        rows = build_fleet_status(which=_which(), env={}, quota_ledger_path=tmp_path / "q.jsonl")
        assert _row(rows, "codex")["auth_mode"] is None
        assert _row(rows, "codex")["raw_auth_mode"] is None

    def test_routability_classes(self, tmp_path):
        rows = build_fleet_status(which=_which(), env={}, quota_ledger_path=tmp_path / "q.jsonl")
        assert _row(rows, "claude")["routable"] == "auto"
        assert _row(rows, "antigravity")["routable"] == "blocked"
        assert _row(rows, "codex")["routable"] == "blocked"
        assert _row(rows, "opencode")["routable"] == "blocked"
        assert _row(rows, "kiro")["routable"] == "blocked"
        assert _row(rows, "copilot")["routable"] == "metered"

    def test_unobserved_by_default(self, tmp_path):
        rows = build_fleet_status(which=_which("codex"), env={}, quota_ledger_path=tmp_path / "q.jsonl")
        assert _row(rows, "codex")["status"] == "unobserved"

    def test_exhausted_with_reset_surfaced(self, tmp_path):
        p = tmp_path / "q.jsonl"
        reset = datetime(2026, 6, 20, 15, 0, tzinfo=UTC)
        _record(p, "codex", QuotaEventType.EXHAUSTED, reset_at=reset)
        rows = build_fleet_status(which=_which("codex"), env={}, quota_ledger_path=p)
        row = _row(rows, "codex")
        assert row["status"] == "exhausted"
        assert row["reset_at"] == reset.isoformat()

    def test_active_after_usage(self, tmp_path):
        p = tmp_path / "q.jsonl"
        _record(p, "codex", QuotaEventType.USAGE_OBSERVED)
        assert (
            _row(build_fleet_status(which=_which("codex"), env={}, quota_ledger_path=p), "codex")["status"] == "active"
        )

    def test_failed_attempt_is_not_reported_as_active(self, tmp_path):
        p = tmp_path / "q.jsonl"
        _record(p, "codex", QuotaEventType.ATTEMPT_OBSERVED)
        row = _row(build_fleet_status(which=_which("codex"), env={}, quota_ledger_path=p), "codex")
        assert row["status"] == "attempt_failed"

    def test_latest_event_wins(self, tmp_path):
        p = tmp_path / "q.jsonl"
        _record(p, "codex", QuotaEventType.EXHAUSTED, ts=T0)
        _record(p, "codex", QuotaEventType.USAGE_OBSERVED, ts=datetime(2026, 6, 20, 13, 0, tzinfo=UTC))
        assert (
            _row(build_fleet_status(which=_which("codex"), env={}, quota_ledger_path=p), "codex")["status"] == "active"
        )


class TestFleetPayload:
    def test_versioned_envelope(self, tmp_path):
        rows = build_fleet_status(which=_which(), env={}, quota_ledger_path=tmp_path / "q.jsonl")
        payload = build_fleet_payload(rows)
        assert payload["schema_version"] == FLEET_SCHEMA_VERSION
        assert payload["kind"] == FLEET_KIND
        assert payload["contract"]["cost_usd"] == 0.0
        assert len(payload["backends"]) == 7
