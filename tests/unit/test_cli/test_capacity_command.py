"""Tests for `deepr capacity probe-plan` - plan-quota backend validation.

The gate is deterministic and $0; the actual vendor round-trip is mocked so these
run with no CLI installed and no spend.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from click.testing import CliRunner

from deepr.backends.capacity import CostModel
from deepr.backends.quota_ledger import load_quota_events
from deepr.backends.quota_snapshot import QuotaSnapshot, QuotaWindowSnapshot
from deepr.cli.commands.capacity import capacity

_CLEAN = ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")
T0 = datetime(2026, 6, 25, 12, tzinfo=UTC)


def _clean_env(monkeypatch):
    for var in _CLEAN:
        monkeypatch.delenv(var, raising=False)


def _stub_probe(monkeypatch, **result):
    async def fake(adapter, *, model=None, **_):
        return {"backend": adapter.backend_id, "reply": "", "latency_ms": 1, "error": "", **result}

    monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", fake)


class TestFleet:
    def test_registered(self):
        assert "fleet" in capacity.commands

    def test_human_table_lists_all_backends(self):
        r = CliRunner().invoke(capacity, ["fleet"])
        assert r.exit_code == 0
        for backend in ("codex", "claude", "opencode", "kiro", "grok", "antigravity", "copilot"):
            assert backend in r.output

    def test_json_payload(self):
        r = CliRunner().invoke(capacity, ["fleet", "--json"])
        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload["schema_version"] == "deepr-plan-fleet-v1"
        assert payload["contract"]["cost_usd"] == 0.0
        assert len(payload["backends"]) == 7


class TestAdmitPlan:
    def test_registered(self):
        assert "admit-plan" in capacity.commands
        assert "revoke-plan" in capacity.commands

    def test_admit_then_revoke_round_trip(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        for var in _CLEAN:
            monkeypatch.delenv(var, raising=False)
        from deepr.backends.admission import is_admitted

        r = CliRunner().invoke(capacity, ["admit-plan", "codex", "--task-class", "sync"])
        assert r.exit_code == 0, r.output
        assert is_admitted("plan:codex", "sync")

        r2 = CliRunner().invoke(capacity, ["revoke-plan", "codex", "--task-class", "sync"])
        assert r2.exit_code == 0
        assert not is_admitted("plan:codex", "sync")

    def test_admit_blocked_when_api_key_present(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENAI_API_KEY", "sk-should-block")
        r = CliRunner().invoke(capacity, ["admit-plan", "codex"])
        assert r.exit_code == 2
        assert "OPENAI_API_KEY" in r.output

    def test_admit_choice_restricted_to_auto_routable(self):
        # ToS-gray / metered backends cannot be admitted for auto-routing.
        for backend in ("kiro", "grok", "antigravity", "copilot"):
            r = CliRunner().invoke(capacity, ["admit-plan", backend])
            assert r.exit_code != 0, backend

    def test_revoke_when_not_admitted_is_graceful(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))
        r = CliRunner().invoke(capacity, ["revoke-plan", "codex", "--task-class", "sync"])
        assert r.exit_code == 0
        assert "Nothing to revoke" in r.output


class TestProbePlan:
    def test_registered(self):
        assert "probe-plan" in capacity.commands

    def test_blocked_when_api_key_present(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-should-block")
        r = CliRunner().invoke(capacity, ["probe-plan", "codex"])
        assert r.exit_code == 2
        assert "OPENAI_API_KEY" in r.output
        assert "--api" in r.output

    def test_ok_round_trip(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_probe(monkeypatch, ok=True, reply="OK", latency_ms=7)
        r = CliRunner().invoke(capacity, ["probe-plan", "codex"])
        assert r.exit_code == 0
        assert "OK" in r.output
        assert "plan" in r.output

    def test_failed_round_trip_exits_nonzero(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_probe(monkeypatch, ok=False, error="not installed")
        r = CliRunner().invoke(capacity, ["probe-plan", "codex"])
        assert r.exit_code == 1
        assert "FAILED" in r.output

    def test_json_payload(self, monkeypatch):
        _clean_env(monkeypatch)
        _stub_probe(monkeypatch, ok=True, reply="OK", latency_ms=7)
        r = CliRunner().invoke(capacity, ["probe-plan", "codex", "--json"])
        assert r.exit_code == 0
        payload = json.loads(r.output)
        assert payload["backend"] == "codex"
        assert payload["auth_mode"] == "plan"
        assert payload["ok"] is True

    def test_metered_backend_requires_ack(self, monkeypatch):
        # copilot is metered-at-margin: without -y it asks first (declined here).
        _clean_env(monkeypatch)
        _stub_probe(monkeypatch, ok=True, reply="OK")
        r = CliRunner().invoke(capacity, ["probe-plan", "copilot"], input="n\n")
        assert r.exit_code == 0
        assert "Cancelled" in r.output


class TestRefreshQuota:
    def test_registered(self):
        assert "refresh-quota" in capacity.commands

    def test_refresh_quota_records_snapshot(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        def fake(backend):
            assert backend == "codex"
            return QuotaSnapshot(
                backend_id="codex",
                display_name="Codex",
                account_id="pro",
                plan="pro",
                cost_model=CostModel.ROLLING_WINDOW,
                windows=(
                    QuotaWindowSnapshot(
                        label="5h",
                        used_fraction=0.25,
                        unit_name="plan_request",
                    ),
                ),
                as_of=T0,
            )

        monkeypatch.setattr("deepr.backends.plan_quota.collect_plan_quota_snapshot", fake)

        r = CliRunner().invoke(capacity, ["refresh-quota", "codex"])

        assert r.exit_code == 0, r.output
        assert "Codex quota snapshot recorded" in r.output
        events = load_quota_events(tmp_path / "quota_ledger.jsonl")
        assert len(events) == 1
        assert events[0].backend_id == "codex"
        assert events[0].units_remaining is None
        assert events[0].metadata["headroom_fraction"] == 0.75

    def test_refresh_quota_json_payload(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        def fake(_backend):
            return QuotaSnapshot(
                backend_id="codex",
                display_name="Codex",
                account_id="pro",
                plan="pro",
                cost_model=CostModel.ROLLING_WINDOW,
                windows=(QuotaWindowSnapshot(label="weekly", used_fraction=0.9),),
                as_of=T0,
            )

        monkeypatch.setattr("deepr.backends.plan_quota.collect_plan_quota_snapshot", fake)

        r = CliRunner().invoke(capacity, ["refresh-quota", "codex", "--json"])

        assert r.exit_code == 0, r.output
        payload = json.loads(r.output)
        assert payload["schema_version"] == "deepr-plan-quota-refresh-v1"
        assert payload["backend"] == "codex"
        assert payload["binding_window"] == "weekly"
        assert payload["ledger_event"]["remaining_confidence"] == "vendor_reported"

    def test_refresh_quota_failure_exits_nonzero_and_records_event(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        def fake(_backend):
            return QuotaSnapshot(
                backend_id="codex",
                display_name="Codex",
                account_id="unknown",
                cost_model=CostModel.ROLLING_WINDOW,
                ok=False,
                error="no rollout files",
                as_of=T0,
            )

        monkeypatch.setattr("deepr.backends.plan_quota.collect_plan_quota_snapshot", fake)

        r = CliRunner().invoke(capacity, ["refresh-quota", "codex"])

        assert r.exit_code == 1
        assert "no rollout files" in r.output
        events = load_quota_events(tmp_path / "quota_ledger.jsonl")
        assert len(events) == 1
        assert events[0].remaining_confidence.value == "unknown"

    def test_refresh_quota_without_usable_windows_exits_nonzero(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEEPR_CAPACITY_DATA_DIR", str(tmp_path))

        def fake(_backend):
            return QuotaSnapshot(
                backend_id="codex",
                display_name="Codex",
                account_id="pro",
                cost_model=CostModel.ROLLING_WINDOW,
                ok=True,
                windows=(),
                as_of=T0,
            )

        monkeypatch.setattr("deepr.backends.plan_quota.collect_plan_quota_snapshot", fake)

        r = CliRunner().invoke(capacity, ["refresh-quota", "codex"])

        assert r.exit_code == 1
        assert "no usable quota windows reported" in r.output
