"""Tests for `deepr capacity probe-plan` - plan-quota backend validation.

The gate is deterministic and $0; the actual vendor round-trip is mocked so these
run with no CLI installed and no spend.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from deepr.cli.commands.capacity import capacity

_CLEAN = ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN")


def _clean_env(monkeypatch):
    for var in _CLEAN:
        monkeypatch.delenv(var, raising=False)


def _stub_probe(monkeypatch, **result):
    async def fake(adapter, *, model=None, **_):
        return {"backend": adapter.backend_id, "reply": "", "latency_ms": 1, "error": "", **result}

    monkeypatch.setattr("deepr.backends.plan_quota.probe_plan_quota", fake)


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
