"""Tests for metadata-only plan-quota availability probes."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import pytest

from deepr.backends.plan_quota.quota_probes import (
    QuotaProbeUnsupportedError,
    collect_codex_quota_snapshot,
    collect_plan_quota_snapshot,
    default_codex_sessions_dir,
    supported_quota_probe_backends,
)
from deepr.backends.quota_ledger import QuotaWindowKind

T0 = datetime(2026, 6, 25, 12, tzinfo=UTC)


def _write_rollout(path, payloads):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(payload) for payload in payloads), encoding="utf-8")


def _rate_limits(plan: str = "pro") -> dict[str, object]:
    return {
        "plan_type": plan,
        "primary": {"used_percent": 62.0, "window_minutes": 300, "resets_at": 1781935855},
        "secondary": {"used_percent": 98.0, "window_minutes": 10080, "resets_at": 1782335912},
    }


class TestCodexQuotaProbe:
    def test_default_sessions_dir_uses_codex_home(self, tmp_path):
        assert default_codex_sessions_dir(home=tmp_path) == tmp_path / ".codex" / "sessions"

    def test_missing_sessions_dir_returns_error_snapshot(self, tmp_path):
        snapshot = collect_codex_quota_snapshot(sessions_dir=tmp_path / "missing", now=T0)

        assert not snapshot.ok
        assert snapshot.backend_id == "codex"
        assert snapshot.error.startswith("no Codex sessions directory")
        assert snapshot.windows == ()

    def test_reads_nested_rate_limits_from_newest_rollout(self, tmp_path):
        rollout = tmp_path / "2026" / "06" / "25" / "rollout-new.jsonl"
        _write_rollout(
            rollout,
            [
                {"event": "start"},
                {"payload": {"rate_limits": _rate_limits()}},
            ],
        )

        snapshot = collect_codex_quota_snapshot(sessions_dir=tmp_path, now=T0)

        assert snapshot.ok
        assert snapshot.account_id == "pro"
        assert snapshot.plan == "pro"
        assert snapshot.metadata["source"] == "codex_rollout"
        assert snapshot.metadata["source_file"].endswith("rollout-new.jsonl")
        assert [w.label for w in snapshot.windows] == ["5h", "weekly"]
        assert [w.window_kind for w in snapshot.windows] == [QuotaWindowKind.ROLLING_5H, QuotaWindowKind.WEEKLY]
        assert snapshot.windows[0].used_fraction == pytest.approx(0.62)
        assert snapshot.windows[1].used_fraction == pytest.approx(0.98)
        assert snapshot.windows[1].reset_at == datetime.fromtimestamp(1782335912, tz=UTC)

    def test_scans_recent_files_until_rate_limits_found(self, tmp_path):
        stale = tmp_path / "rollout-stale.jsonl"
        newest = tmp_path / "rollout-newest.jsonl"
        _write_rollout(stale, [{"payload": {"rate_limits": _rate_limits("team")}}])
        _write_rollout(newest, [{"event": "no quota here"}])
        os.utime(stale, (1000, 1000))
        os.utime(newest, (2000, 2000))

        snapshot = collect_codex_quota_snapshot(sessions_dir=tmp_path, now=T0)

        assert snapshot.ok
        assert snapshot.account_id == "team"
        assert snapshot.metadata["source_file"].endswith("rollout-stale.jsonl")

    def test_no_rate_limits_returns_error_snapshot(self, tmp_path):
        _write_rollout(tmp_path / "rollout-empty.jsonl", [{"event": "no quota"}])

        snapshot = collect_codex_quota_snapshot(sessions_dir=tmp_path, now=T0)

        assert not snapshot.ok
        assert snapshot.error == "no rate_limits found in 1 recent rollout files"


class TestProbeRegistry:
    def test_supported_backends(self):
        assert supported_quota_probe_backends() == ("codex",)

    def test_collect_plan_quota_snapshot_dispatches_codex(self, tmp_path):
        _write_rollout(tmp_path / "rollout-codex.jsonl", [{"rate_limits": _rate_limits()}])

        snapshot = collect_plan_quota_snapshot("codex", now=T0, codex_sessions_dir=tmp_path)

        assert snapshot.ok
        assert snapshot.backend_id == "codex"

    def test_collect_plan_quota_snapshot_rejects_unsupported_backend(self):
        with pytest.raises(QuotaProbeUnsupportedError, match="no live quota probe"):
            collect_plan_quota_snapshot("claude", now=T0)
