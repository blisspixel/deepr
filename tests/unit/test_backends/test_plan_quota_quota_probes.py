"""Tests for metadata-only plan-quota availability probes."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import pytest

from deepr.backends.plan_quota.quota_probes import (
    QuotaProbeUnsupportedError,
    collect_claude_quota_snapshot,
    collect_codex_quota_snapshot,
    collect_plan_quota_snapshot,
    default_claude_credentials_path,
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


class _FakeResponse:
    def __init__(self, status_code: int, payload: object | None = None, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


def _write_claude_credentials(config_dir, *, token: str = "sk-ant-oat01-test", plan: str = "max_20x"):
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": token, "subscriptionType": plan}}),
        encoding="utf-8",
    )


def _claude_usage_payload() -> dict[str, object]:
    return {
        "five_hour": {"utilization": 25.0, "resets_at": "2026-06-25T17:00:00Z"},
        "seven_day": {"utilization": 80.0, "resets_at": "2026-06-30T00:00:00Z"},
        "seven_day_opus": {"utilization": 5.0, "resets_at": "2026-06-30T00:00:00Z"},
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


class TestClaudeQuotaProbe:
    def test_default_credentials_path_uses_claude_config_dir(self, tmp_path):
        assert (
            default_claude_credentials_path(env={"CLAUDE_CONFIG_DIR": str(tmp_path)}) == tmp_path / ".credentials.json"
        )

    def test_default_credentials_path_uses_home_when_unconfigured(self, tmp_path):
        assert default_claude_credentials_path(env={}, home=tmp_path) == tmp_path / ".claude" / ".credentials.json"

    def test_missing_credentials_returns_error_snapshot(self, tmp_path):
        snapshot = collect_claude_quota_snapshot(config_dir=tmp_path / "missing", now=T0, http_get=lambda **_: None)

        assert not snapshot.ok
        assert snapshot.backend_id == "claude"
        assert "no Claude Code credentials file" in snapshot.error
        assert snapshot.windows == ()

    def test_missing_oauth_token_returns_error_snapshot(self, tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {}}), encoding="utf-8")

        snapshot = collect_claude_quota_snapshot(config_dir=tmp_path, now=T0, http_get=lambda **_: None)

        assert not snapshot.ok
        assert "no OAuth access token" in snapshot.error

    def test_reads_usage_windows_from_oauth_usage_endpoint(self, tmp_path):
        _write_claude_credentials(tmp_path, plan="max_20x")
        seen: dict[str, object] = {}

        def fake_get(url, *, headers, timeout):
            seen["url"] = url
            seen["auth"] = headers["Authorization"]
            seen["timeout"] = timeout
            return _FakeResponse(200, _claude_usage_payload())

        snapshot = collect_claude_quota_snapshot(config_dir=tmp_path, now=T0, http_get=fake_get)

        assert snapshot.ok
        assert snapshot.backend_id == "claude"
        assert snapshot.account_id == "max_20x"
        assert snapshot.plan == "max_20x"
        assert snapshot.metadata == {"source": "claude_oauth_usage"}
        assert seen["url"] == "https://api.anthropic.com/api/oauth/usage"
        assert seen["auth"] == "Bearer sk-ant-oat01-test"
        assert seen["timeout"] == 10.0
        assert [w.label for w in snapshot.windows] == ["5h", "weekly", "opus"]
        assert [w.window_kind for w in snapshot.windows] == [
            QuotaWindowKind.ROLLING_5H,
            QuotaWindowKind.WEEKLY,
            QuotaWindowKind.WEEKLY,
        ]
        assert snapshot.windows[0].used_fraction == pytest.approx(0.25)
        assert snapshot.windows[1].used_fraction == pytest.approx(0.80)
        assert snapshot.windows[1].reset_at == datetime(2026, 6, 30, tzinfo=UTC)

    def test_unauthorized_response_reports_relogin(self, tmp_path):
        _write_claude_credentials(tmp_path, plan="pro")

        snapshot = collect_claude_quota_snapshot(
            config_dir=tmp_path,
            now=T0,
            http_get=lambda *_, **__: _FakeResponse(401, {}),
        )

        assert not snapshot.ok
        assert snapshot.account_id == "pro"
        assert "re-run claude login" in snapshot.error

    def test_rate_limited_response_keeps_retry_after_metadata(self, tmp_path):
        _write_claude_credentials(tmp_path, plan="pro")

        snapshot = collect_claude_quota_snapshot(
            config_dir=tmp_path,
            now=T0,
            http_get=lambda *_, **__: _FakeResponse(429, {}, headers={"retry-after": "120"}),
        )

        assert not snapshot.ok
        assert snapshot.error == "Claude usage endpoint rate-limited; retry after 120s"
        assert snapshot.metadata["retry_after"] == "120"

    def test_payload_without_usable_windows_is_ok_but_unbound(self, tmp_path):
        _write_claude_credentials(tmp_path)

        snapshot = collect_claude_quota_snapshot(
            config_dir=tmp_path,
            now=T0,
            http_get=lambda *_, **__: _FakeResponse(200, {"five_hour": {}}),
        )

        assert snapshot.ok
        assert snapshot.windows == ()


class TestProbeRegistry:
    def test_supported_backends(self):
        assert supported_quota_probe_backends() == ("codex", "claude")

    def test_collect_plan_quota_snapshot_dispatches_codex(self, tmp_path):
        _write_rollout(tmp_path / "rollout-codex.jsonl", [{"rate_limits": _rate_limits()}])

        snapshot = collect_plan_quota_snapshot("codex", now=T0, codex_sessions_dir=tmp_path)

        assert snapshot.ok
        assert snapshot.backend_id == "codex"

    def test_collect_plan_quota_snapshot_dispatches_claude(self, tmp_path):
        _write_claude_credentials(tmp_path)

        snapshot = collect_plan_quota_snapshot(
            "claude",
            now=T0,
            claude_config_dir=tmp_path,
            claude_http_get=lambda *_, **__: _FakeResponse(200, _claude_usage_payload()),
        )

        assert snapshot.ok
        assert snapshot.backend_id == "claude"

    def test_collect_plan_quota_snapshot_rejects_unsupported_backend(self):
        with pytest.raises(QuotaProbeUnsupportedError, match="no live quota probe"):
            collect_plan_quota_snapshot("grok", now=T0)
