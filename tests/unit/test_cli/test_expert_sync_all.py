"""CLI tests for `deepr expert sync-all`.

The roster loop is unit-tested in test_sync_all.py; here we exercise the command
layer (backend resolution, scheduled wait, rendering) with the engine and store
injected so nothing touches providers or disk.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from click.testing import CliRunner

from deepr.cli.commands.semantic.experts import expert
from deepr.experts.sync import SyncOutcome, SyncResult


def _sync_result(*outcomes: SyncOutcome, cost: float = 0.0) -> SyncResult:
    return SyncResult(expert_name="x", started_at=datetime.now(UTC), outcomes=list(outcomes), total_cost=cost)


def _wire(monkeypatch, result: SyncResult, *, names=("Alpha", "Beta"), local_model="qwen-local", recorded=None):
    profiles = [SimpleNamespace(name=n) for n in names]

    class FakeStore:
        def list_all(self, include_errors=False):
            return profiles

        def load(self, name):
            return SimpleNamespace(name=name)

    class FakeEngine:
        async def sync(self, **kwargs):
            return result

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    monkeypatch.setattr(
        "deepr.experts.maintenance_engine.build_sync_engine",
        lambda profile, **kw: (FakeEngine(), "local" if kw.get("use_local") else "api_metered"),
    )
    monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: local_model)

    def fake_record(name, res, **kwargs):
        if recorded is not None:
            recorded.append((name, kwargs.get("capacity_source")))

    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_maintenance._record_completed_sync_loop", fake_record
    )


class TestRegistration:
    def test_sync_all_registered(self):
        assert "sync-all" in expert.commands

    def test_rejects_local_and_api_together(self):
        r = CliRunner().invoke(expert, ["sync-all", "--local", "--api"])
        assert r.exit_code == 2

    def test_no_experts_is_friendly(self, monkeypatch):
        class EmptyStore:
            def list_all(self, include_errors=False):
                return []

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", EmptyStore)
        r = CliRunner().invoke(expert, ["sync-all", "--local", "-y"])
        assert r.exit_code == 0
        assert "No experts yet" in r.output


class TestRun:
    def test_local_pass_syncs_roster_and_records_loops(self, monkeypatch):
        recorded: list = []
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced", absorbed=2), cost=0.0), recorded=recorded)

        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y", "--json"])

        assert r.exit_code == 0, r.output
        import json

        payload = json.loads(r.output)
        assert payload["schema_version"] == "deepr-library-sync-v1"
        assert payload["synced_experts"] == 2
        assert {row["expert"] for row in payload["summaries"]} == {"Alpha", "Beta"}
        # Each synced expert recorded a per-expert loop run (fleet status sees it).
        assert [name for name, _ in recorded] == ["Alpha", "Beta"]

    def test_human_render_summarizes(self, monkeypatch):
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced", absorbed=1), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y"])
        assert r.exit_code == 0
        assert "synced" in r.output
        assert "2 experts" in r.output

    def test_dry_run_does_not_record(self, monkeypatch):
        recorded: list = []
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "would_sync"), cost=0.0), recorded=recorded)
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "--dry-run"])
        assert r.exit_code == 0
        assert recorded == []  # dry run writes nothing


class TestCapacity:
    def test_scheduled_waits_when_no_owned_capacity(self, monkeypatch):
        # Auto waterfall returns metered (not local) -> a scheduled pass waits.
        monkeypatch.setattr(
            "deepr.backends.waterfall.choose_maintenance_backend",
            lambda task_class: SimpleNamespace(is_local=False, reason=""),
        )
        _wire(monkeypatch, _sync_result(cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--scheduled", "--json"])
        assert r.exit_code == 0
        assert "waiting_for_capacity" in r.output

    def test_local_forced_without_model_errors(self, monkeypatch):
        _wire(monkeypatch, _sync_result(cost=0.0), local_model=None)
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y"])
        assert r.exit_code == 2
        assert "No local model" in r.output
