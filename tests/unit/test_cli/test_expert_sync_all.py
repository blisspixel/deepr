"""CLI tests for `deepr expert sync-all`.

The roster loop is unit-tested in test_sync_all.py; here we exercise the command
layer (backend resolution, scheduled wait, rendering) with the engine and store
injected so nothing touches providers or disk.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from click.testing import CliRunner

from deepr.backends.local_capacity import LocalCapacityObservation, LocalCapacityState
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.sync import SyncOutcome, SyncResult


def _sync_result(*outcomes: SyncOutcome, cost: float = 0.0) -> SyncResult:
    return SyncResult(expert_name="x", started_at=datetime.now(UTC), outcomes=list(outcomes), total_cost=cost)


def _wire(
    monkeypatch,
    result: SyncResult,
    *,
    names=("Alpha", "Beta"),
    local_model="qwen-local",
    recorded=None,
    profiles=None,
    built=None,
    loop_events=None,
):
    profiles = profiles or [SimpleNamespace(name=n) for n in names]

    class FakeStore:
        def list_all(self, include_errors=False):
            return profiles

        def load(self, name):
            return next(profile for profile in profiles if profile.name == name)

    class FakeEngine:
        async def sync(self, **kwargs):
            return result

    class FakeSubscriptionStore:
        subscriptions = [SimpleNamespace(topic="t")]

        def __init__(self, name):
            pass

        def due(self):
            return list(self.subscriptions)

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)

    def fake_build_sync_engine(profile, **kw):
        if built is not None:
            built.append((profile.name, kw))
        if kw.get("use_plan"):
            return FakeEngine(), f"plan_quota:{kw['plan_adapter'].backend_id}"
        return FakeEngine(), "local" if kw.get("use_local") else "api_metered"

    monkeypatch.setattr("deepr.experts.maintenance_engine.build_sync_engine", fake_build_sync_engine)
    monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: local_model)
    monkeypatch.setattr(
        "deepr.backends.local_capacity.probe_local_gpu_occupancy",
        lambda: LocalCapacityObservation(
            state=LocalCapacityState.FREE,
            source="test",
            detail="local GPU capacity is free",
        ),
    )

    def fake_record(name, res, **kwargs):
        if loop_events is not None:
            loop_events.append(("completed", name, kwargs))
        if recorded is not None:
            recorded.append((name, kwargs.get("capacity_source")))

    monkeypatch.setattr("deepr.cli.commands.semantic.expert_maintenance._record_completed_sync_loop", fake_record)
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_sync_support._record_running_sync_loop",
        lambda name, **kwargs: loop_events.append(("running", name, kwargs)) if loop_events is not None else None,
    )
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_sync_support._record_failed_sync_execution",
        lambda name, **kwargs: loop_events.append(("failed", name, kwargs)) if loop_events is not None else None,
    )


class TestRegistration:
    def test_sync_all_registered(self):
        assert "sync-all" in expert.commands

    def test_rejects_local_and_api_together(self):
        r = CliRunner().invoke(expert, ["sync-all", "--local", "--api"])
        assert r.exit_code == 2

    def test_rejects_plan_model_without_plan(self):
        r = CliRunner().invoke(expert, ["sync-all", "--plan-model", "x"])
        assert r.exit_code == 2
        assert "Use --plan-model only with --plan" in r.output

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

    def test_forced_local_pass_uses_each_local_profiles_recorded_model(self, monkeypatch):
        profiles = [
            SimpleNamespace(name="Alpha", provider="local", model="alpha-model"),
            SimpleNamespace(name="Beta", provider="local", model="beta-model"),
        ]
        built: list = []
        _wire(
            monkeypatch,
            _sync_result(SyncOutcome("t", "synced"), cost=0.0),
            local_model="global-model",
            profiles=profiles,
            built=built,
        )

        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y", "--json"])

        assert r.exit_code == 0, r.output
        assert [(name, kwargs["local_model"]) for name, kwargs in built] == [
            ("Alpha", "alpha-model"),
            ("Beta", "beta-model"),
        ]

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

    def test_non_dry_records_running_then_completes_same_run_id(self, monkeypatch):
        loop_events: list = []
        _wire(
            monkeypatch,
            _sync_result(SyncOutcome("t", "synced"), cost=0.0),
            names=("Alpha",),
            loop_events=loop_events,
        )

        result = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y", "--json"])

        assert result.exit_code == 0, result.output
        assert [event[0] for event in loop_events] == ["running", "completed"]
        assert loop_events[0][2]["run_id"] == loop_events[1][2]["run_id"]
        assert loop_events[0][2]["started_at"] == loop_events[1][2]["started_at"]


class TestCapacity:
    def test_scheduled_waits_when_no_owned_capacity(self, monkeypatch):
        # Auto waterfall returns metered (not local) -> a scheduled pass waits.
        monkeypatch.setattr(
            "deepr.backends.waterfall.choose_maintenance_backend",
            lambda task_class: SimpleNamespace(is_local=False, is_plan_quota=False, reason=""),
        )
        _wire(monkeypatch, _sync_result(cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--scheduled", "--json"])
        assert r.exit_code == 0
        assert "waiting_for_capacity" in r.output

    def test_scheduled_uses_auto_selected_plan_capacity(self, monkeypatch):
        import json

        monkeypatch.setattr(
            "deepr.backends.waterfall.choose_maintenance_backend",
            lambda task_class: SimpleNamespace(
                is_local=False,
                is_plan_quota=True,
                plan_backend_id="codex",
                reason="plan-quota backend 'codex' (operator-admitted, quota-observed)",
            ),
        )
        recorded: list = []
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0), recorded=recorded)

        r = CliRunner().invoke(expert, ["sync-all", "--all", "--scheduled", "-y", "--json"])

        assert r.exit_code == 0, r.output
        payload = json.loads(r.output)
        assert payload["synced_experts"] == 2
        assert {row["capacity_source"] for row in payload["summaries"]} == {"plan_quota:codex"}
        assert recorded == [("Alpha", "plan_quota:codex"), ("Beta", "plan_quota:codex")]

    def test_explicit_plan_forces_roster_capacity(self, monkeypatch):
        import json

        recorded: list = []
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0), recorded=recorded)

        r = CliRunner().invoke(expert, ["sync-all", "--all", "--plan", "codex", "-y", "--json"])

        assert r.exit_code == 0, r.output
        payload = json.loads(r.output)
        assert {row["capacity_source"] for row in payload["summaries"]} == {"plan_quota:codex"}
        assert recorded == [("Alpha", "plan_quota:codex"), ("Beta", "plan_quota:codex")]

    def test_explicit_metered_at_margin_plan_is_rejected_for_roster(self, monkeypatch):
        _wire(monkeypatch, _sync_result(cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--plan", "copilot", "-y"])
        assert r.exit_code == 2
        assert "metered at the margin" in r.output

    def test_local_forced_without_model_errors(self, monkeypatch):
        _wire(monkeypatch, _sync_result(cost=0.0), local_model=None)
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y"])
        assert r.exit_code == 2
        assert "No local model" in r.output


class TestHeartbeat:
    def _capture(self, monkeypatch):
        pinged: list = []
        monkeypatch.setattr("deepr.experts.heartbeat.send_heartbeat", lambda **kw: pinged.append(kw) or True)
        return pinged

    def test_scheduled_success_pings_heartbeat(self, monkeypatch):
        pinged = self._capture(monkeypatch)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "--scheduled", "-y", "--json"])
        assert r.exit_code == 0
        assert pinged == [{"success": True}]

    def test_scheduled_failure_pings_fail(self, monkeypatch):
        pinged = self._capture(monkeypatch)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "failed", detail="boom"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "--scheduled", "-y", "--json"])
        assert r.exit_code == 0
        assert pinged == [{"success": False}]

    def test_non_scheduled_run_does_not_ping(self, monkeypatch):
        pinged = self._capture(monkeypatch)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y"])
        assert r.exit_code == 0
        assert pinged == []

    def test_dry_run_does_not_ping(self, monkeypatch):
        pinged = self._capture(monkeypatch)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "would_sync"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "--scheduled", "--dry-run"])
        assert r.exit_code == 0
        assert pinged == []


class TestBudgetTierGate:
    def _auto_metered(self, monkeypatch):
        monkeypatch.setattr(
            "deepr.backends.waterfall.choose_maintenance_backend",
            lambda task_class: SimpleNamespace(is_local=False, is_plan_quota=False, reason=""),
        )

    def _manager(self, monkeypatch, *, spent, cap=10.0):
        monkeypatch.setattr(
            "deepr.experts.cost_safety.get_cost_safety_manager",
            lambda: SimpleNamespace(monthly_cost=spent, max_monthly=cap),
        )

    def test_drained_pool_defers_auto_metered_pass(self, monkeypatch):
        self._auto_metered(monkeypatch)
        self._manager(monkeypatch, spent=9.6)  # 96% -> LOCAL_ONLY
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "-y", "--json"])
        assert r.exit_code == 0
        assert "metered_deferred" in r.output

    def test_normal_tier_allows_auto_metered_pass(self, monkeypatch):
        import json

        self._auto_metered(monkeypatch)
        self._manager(monkeypatch, spent=1.0)  # 10% -> NORMAL
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "-y", "--json"])
        assert r.exit_code == 0
        assert json.loads(r.output)["schema_version"] == "deepr-library-sync-v1"  # ran, not deferred

    def test_api_override_fails_closed_before_sync(self, monkeypatch):
        self._manager(monkeypatch, spent=9.6)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--api", "-y", "--json"])
        assert r.exit_code == 2
        assert "temporarily disabled" in r.output.lower()
        assert "--local" in r.output

    def test_api_dry_run_remains_available(self, monkeypatch):
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "would_sync"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--api", "--dry-run", "--json"])
        assert r.exit_code == 0, r.output
        assert "temporarily disabled" not in r.output.lower()

    def test_dry_run_previews_even_when_drained(self, monkeypatch):
        self._auto_metered(monkeypatch)
        self._manager(monkeypatch, spent=9.6)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "would_sync"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--dry-run", "--json"])
        assert r.exit_code == 0
        assert "metered_deferred" not in r.output
