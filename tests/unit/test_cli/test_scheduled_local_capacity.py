from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from deepr.backends.capacity_actions import CapacityNextAction
from deepr.backends.local_capacity import LocalCapacityObservation, LocalCapacityState
from deepr.cli.commands.semantic.expert_sync_support import _run_sync_with_loop_guard
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.sync import SyncOutcome, SyncResult


def _observation(state: LocalCapacityState) -> LocalCapacityObservation:
    return LocalCapacityObservation(
        state=state,
        source="nvidia-smi" if state != LocalCapacityState.UNKNOWN else "unsupported",
        detail=f"local GPU capacity is {state.value}",
        gpu_utilization_percent=(90.0,) if state == LocalCapacityState.BUSY else (),
    )


def _wire_single_sync(monkeypatch, tmp_path, *, engine_must_not_build: bool = False):
    profile = SimpleNamespace(name="GPU Expert", provider="local", model="local-model")

    class FakeExpertStore:
        def load(self, name):
            return profile

    class FakeSubscriptionStore:
        subscriptions = [SimpleNamespace(topic="GPU scheduling", budget=0.5)]

        def __init__(self, name):
            pass

        def due(self):
            return list(self.subscriptions)

    class FakeEngine:
        async def sync(self, **kwargs):
            return SyncResult(
                expert_name="GPU Expert",
                started_at=datetime.now(UTC),
                outcomes=[SyncOutcome("GPU scheduling", "no_changes")],
                total_cost=0.0,
            )

    def build_engine(*args, **kwargs):
        if engine_must_not_build:
            raise AssertionError("busy scheduled work must stop before engine construction")
        return FakeEngine(), "local"

    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(tmp_path / "experts"))
    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeExpertStore)
    monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)
    monkeypatch.setattr("deepr.experts.maintenance_engine.build_sync_engine", build_engine)
    monkeypatch.setattr("deepr.backends.local.resolve_local_maintenance_model", lambda *args, **kwargs: "local-model")
    monkeypatch.setattr(
        "deepr.backends.capacity_actions.build_capacity_next_actions",
        lambda **kwargs: [CapacityNextAction(1, "wait", "Local GPU capacity is busy", "wait")],
    )


def test_scheduled_single_sync_busy_records_wait_before_dispatch(monkeypatch, tmp_path):
    _wire_single_sync(monkeypatch, tmp_path, engine_must_not_build=True)
    monkeypatch.setattr(
        "deepr.backends.local_capacity.probe_local_gpu_occupancy",
        lambda: _observation(LocalCapacityState.BUSY),
    )

    result = CliRunner().invoke(
        expert,
        ["sync", "GPU Expert", "--local", "--scheduled", "-y", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "waiting_for_capacity"
    assert payload["capacity_unavailable_reason"] == "local_gpu_busy"
    assert payload["retry_after_seconds"] == 1800
    assert payload["local_capacity"]["state"] == "busy"
    assert payload["loop_run"]["status"] == "waiting"
    assert payload["loop_run"]["stop_reason"] == "capacity_unavailable"
    argv = payload["requested_operation"]["command_argv"]
    assert argv[:4] == ["deepr", "expert", "sync", "GPU Expert"]
    assert {"--scheduled", "--local", "--yes", "--json"} <= set(argv)
    assert payload["loop_run"]["next_action"]["command_argv"] == [argv]
    assert [action["status"] for action in payload["capacity_next"]["actions"]] == ["wait"]
    assert payload["capacity_next"]["actions"][0]["command_argv"] == [argv]
    assert not any(action["status"] == "fallback" for action in payload["capacity_next"]["actions"])


def test_scheduled_sync_busy_preserves_context_compile_and_model_options(monkeypatch, tmp_path):
    _wire_single_sync(monkeypatch, tmp_path, engine_must_not_build=True)
    monkeypatch.setattr(
        "deepr.backends.local_capacity.probe_local_gpu_occupancy",
        lambda: _observation(LocalCapacityState.BUSY),
    )

    result = CliRunner().invoke(
        expert,
        [
            "sync",
            "GPU Expert",
            "--local",
            "--scheduled",
            "--all",
            "--deep-context",
            "--compile-claims",
            "--stage-compiled-claims",
            "--recall-embedding-model",
            "nomic-embed-text",
            "-y",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    argv = payload["requested_operation"]["command_argv"]
    assert {"--local", "--scheduled", "--all", "--deep-context", "--compile-claims"} <= set(argv)
    assert "--stage-compiled-claims" in argv
    assert argv[argv.index("--recall-embedding-model") + 1] == "nomic-embed-text"
    assert payload["loop_run"]["backend_profile_id"] == "local-model"


def test_scheduled_plan_compile_waits_for_busy_local_recall_embedder(monkeypatch, tmp_path):
    _wire_single_sync(monkeypatch, tmp_path, engine_must_not_build=True)
    monkeypatch.setattr(
        "deepr.backends.waterfall.choose_plan_quota_backend",
        lambda *args, **kwargs: SimpleNamespace(
            is_plan_quota=True,
            plan_backend_id="codex",
            reason="explicit non-metered plan backend",
        ),
    )
    monkeypatch.setattr(
        "deepr.backends.local_capacity.probe_local_gpu_occupancy",
        lambda: _observation(LocalCapacityState.BUSY),
    )

    result = CliRunner().invoke(
        expert,
        [
            "sync",
            "GPU Expert",
            "--plan",
            "codex",
            "--scheduled",
            "--compile-claims",
            "--recall-embedding-model",
            "nomic-embed-text",
            "-y",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "waiting_for_capacity"
    assert payload["loop_run"]["capacity_source"] == "plan_quota:codex+local_embedding"
    assert payload["loop_run"]["backend_profile_id"] == "nomic-embed-text"
    argv = payload["requested_operation"]["command_argv"]
    assert argv[argv.index("--plan") + 1] == "codex"
    assert argv[argv.index("--recall-embedding-model") + 1] == "nomic-embed-text"


def test_scheduled_plan_compile_unknown_local_probe_dispatches(monkeypatch, tmp_path):
    _wire_single_sync(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "deepr.backends.waterfall.choose_plan_quota_backend",
        lambda *args, **kwargs: SimpleNamespace(
            is_plan_quota=True,
            plan_backend_id="codex",
            reason="explicit non-metered plan backend",
        ),
    )
    monkeypatch.setattr(
        "deepr.backends.local_capacity.probe_local_gpu_occupancy",
        lambda: _observation(LocalCapacityState.UNKNOWN),
    )

    result = CliRunner().invoke(
        expert,
        [
            "sync",
            "GPU Expert",
            "--plan",
            "codex",
            "--scheduled",
            "--compile-claims",
            "--recall-embedding-model",
            "nomic-embed-text",
            "-y",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["outcomes"][0]["status"] == "no_changes"


def test_manual_local_sync_is_an_occupancy_override(monkeypatch, tmp_path):
    _wire_single_sync(monkeypatch, tmp_path)

    def exploding_probe():
        raise AssertionError("manual --local must not inspect scheduled occupancy")

    monkeypatch.setattr("deepr.backends.local_capacity.probe_local_gpu_occupancy", exploding_probe)

    result = CliRunner().invoke(expert, ["sync", "GPU Expert", "--local", "-y", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["outcomes"][0]["status"] == "no_changes"


def test_scheduled_single_sync_unknown_probe_dispatches(monkeypatch, tmp_path):
    _wire_single_sync(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "deepr.backends.local_capacity.probe_local_gpu_occupancy",
        lambda: _observation(LocalCapacityState.UNKNOWN),
    )

    result = CliRunner().invoke(
        expert,
        ["sync", "GPU Expert", "--local", "--scheduled", "-y", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["outcomes"][0]["status"] == "no_changes"


def test_scheduled_sync_all_busy_records_each_expert_and_never_builds_engine(monkeypatch, tmp_path):
    profiles = [SimpleNamespace(name="Alpha"), SimpleNamespace(name="Beta"), SimpleNamespace(name="Idle")]

    class FakeStore:
        def list_all(self, include_errors=False):
            return profiles

        def load(self, name):
            return next(profile for profile in profiles if profile.name == name)

    class FakeSubscriptionStore:
        def __init__(self, name):
            self.subscriptions = [] if name == "Idle" else [SimpleNamespace(topic="GPU scheduling")]

        def due(self):
            return list(self.subscriptions)

    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(tmp_path / "experts"))
    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)
    monkeypatch.setattr("deepr.backends.local.default_local_model", lambda: "local-model")
    monkeypatch.setattr(
        "deepr.backends.local_capacity.probe_local_gpu_occupancy",
        lambda: _observation(LocalCapacityState.BUSY),
    )
    monkeypatch.setattr(
        "deepr.experts.maintenance_engine.build_sync_engine",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("engine must not build")),
    )

    result = CliRunner().invoke(
        expert,
        ["sync-all", "--all", "--local", "--scheduled", "-y", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "waiting_for_capacity"
    assert payload["capacity_unavailable_reason"] == "local_gpu_busy"
    assert payload["retry_after_seconds"] == 1800
    assert [row["loop_run"]["expert_name"] for row in payload["waiting_experts"]] == ["Alpha", "Beta"]
    argv = payload["requested_operation"]["command_argv"]
    assert {"sync-all", "--scheduled", "--all", "--local", "--yes", "--json"} <= set(argv)
    assert all(row["requested_operation"]["command_argv"] == argv for row in payload["waiting_experts"])
    assert {row["loop_run"]["backend_profile_id"] for row in payload["waiting_experts"]} == {"local-model"}
    assert payload["requested_operation"]["backend_profile_ids"] == {
        "Alpha": "local-model",
        "Beta": "local-model",
    }


def _wire_route_gaps(monkeypatch, tmp_path, *, engine_must_not_build: bool = False):
    from deepr.experts.gap_fill import GapFillResult
    from deepr.experts.gap_router import GapRoute

    route = GapRoute(
        topic="GPU scheduling",
        instrument="research",
        available=True,
        estimated_cost=0.2,
        rationale="general research",
        suggestion="deepr research GPU scheduling",
        priority=5,
        ev_cost_ratio=2.0,
        matched_keywords=[],
    )
    profile = SimpleNamespace(
        name="GPU Expert",
        provider="local",
        model="local-model",
        get_manifest=lambda: SimpleNamespace(top_gaps=lambda top_n: [SimpleNamespace(topic="GPU scheduling")]),
    )

    class FakeStore:
        def load(self, name):
            return profile

    class FakeRouter:
        def route(self, gaps):
            return [route]

    class FakeEngine:
        async def execute(self, routes, **kwargs):
            return GapFillResult(expert_name="GPU Expert", started_at=datetime.now(UTC), outcomes=[])

    def build_engine(*args, **kwargs):
        if engine_must_not_build:
            raise AssertionError("busy scheduled route-gaps must stop before engine construction")
        return FakeEngine(), "local"

    monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(tmp_path / "experts"))
    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    monkeypatch.setattr("deepr.experts.gap_router.GapRouter", FakeRouter)
    monkeypatch.setattr("deepr.backends.local.resolve_local_maintenance_model", lambda *args, **kwargs: "local-model")
    monkeypatch.setattr("deepr.cli.commands.semantic.expert_gap_routes._build_gap_fill_engine", build_engine)


def test_scheduled_local_route_gaps_busy_waits_with_exact_argv(monkeypatch, tmp_path):
    _wire_route_gaps(monkeypatch, tmp_path, engine_must_not_build=True)
    monkeypatch.setattr(
        "deepr.backends.local_capacity.probe_local_gpu_occupancy",
        lambda: _observation(LocalCapacityState.BUSY),
    )

    result = CliRunner().invoke(
        expert,
        [
            "route-gaps",
            "GPU Expert",
            "--execute",
            "--scheduled",
            "--local",
            "--top",
            "3",
            "--budget",
            "1",
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "waiting_for_capacity"
    assert payload["local_capacity"]["state"] == "busy"
    argv = payload["requested_operation"]["command_argv"]
    assert argv[:4] == ["deepr", "expert", "route-gaps", "GPU Expert"]
    assert {"--execute", "--scheduled", "--local", "--yes", "--json"} <= set(argv)
    assert argv[argv.index("--top") + 1] == "3"
    assert argv[argv.index("--budget") + 1] == "1"
    assert payload["loop_run"]["backend_profile_id"] == "local-model"
    assert payload["next_actions"][0]["command_argv"] == [argv]


def test_scheduled_local_route_gaps_unknown_probe_dispatches(monkeypatch, tmp_path):
    _wire_route_gaps(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "deepr.backends.local_capacity.probe_local_gpu_occupancy",
        lambda: _observation(LocalCapacityState.UNKNOWN),
    )

    result = CliRunner().invoke(
        expert,
        ["route-gaps", "GPU Expert", "--execute", "--scheduled", "--local", "--yes", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["total_cost"] == 0.0


def test_manual_local_route_gaps_is_an_occupancy_override(monkeypatch, tmp_path):
    _wire_route_gaps(monkeypatch, tmp_path)

    def exploding_probe():
        raise AssertionError("manual route-gaps must not inspect scheduled occupancy")

    monkeypatch.setattr("deepr.backends.local_capacity.probe_local_gpu_occupancy", exploding_probe)

    result = CliRunner().invoke(
        expert,
        ["route-gaps", "GPU Expert", "--execute", "--local", "--yes", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["total_cost"] == 0.0


def _wire_running_snapshot_test(monkeypatch, tmp_path, engine):
    loop_path = tmp_path / "loop_runs.jsonl"

    @contextmanager
    def acquired_lock(name, verb):
        yield True

    monkeypatch.setattr("deepr.experts.loop_lock.expert_verb_lock", acquired_lock)
    monkeypatch.setattr("deepr.experts.maintenance_engine.build_sync_engine", lambda *args, **kwargs: (engine, "local"))
    monkeypatch.setattr("deepr.experts.loop_runs.loop_runs_path", lambda expert_name, path=None: loop_path)
    monkeypatch.setattr(
        "deepr.experts.self_model.build_expert_self_model_context_from_profile",
        lambda profile, *, focus_limit=3: {},
    )
    monkeypatch.setattr(
        "deepr.experts.self_model_updates.build_self_model_update_context",
        lambda expert_name: {"accepted_record_count": 0},
    )
    return loop_path


def test_sync_appends_running_before_dispatch_then_completes_same_run(monkeypatch, tmp_path):
    captured = {}

    class FakeEngine:
        async def sync(self, **kwargs):
            rows = [json.loads(line) for line in captured["loop_path"].read_text(encoding="utf-8").splitlines()]
            captured["during_dispatch"] = rows
            return SyncResult(
                expert_name="GPU Expert",
                started_at=datetime.now(UTC),
                outcomes=[SyncOutcome("GPU scheduling", "no_changes")],
                total_cost=0.0,
            )

    captured["loop_path"] = _wire_running_snapshot_test(monkeypatch, tmp_path, FakeEngine())

    _, loop_run, capacity_source = _run_sync_with_loop_guard(
        SimpleNamespace(name="GPU Expert"),
        name="GPU Expert",
        budget=0.5,
        sync_all=False,
        dry_run=False,
        scheduled=True,
        jitter=0.0,
        use_local=True,
        local_model="local-model",
        use_plan=False,
        plan_adapter=None,
        plan_model=None,
        context_builder=None,
    )

    rows = [json.loads(line) for line in captured["loop_path"].read_text(encoding="utf-8").splitlines()]
    assert [row["status"] for row in captured["during_dispatch"]] == ["running"]
    assert [row["status"] for row in rows] == ["running", "completed"]
    assert rows[0]["run_id"] == rows[1]["run_id"] == loop_run.run_id
    assert rows[1]["finished_at"] is not None
    assert capacity_source == "local"


def test_sync_execution_error_transitions_running_snapshot_to_failed(monkeypatch, tmp_path):
    class CostedRuntimeError(RuntimeError):
        actual_cost = 0.17

    class ExplodingEngine:
        async def sync(self, **kwargs):
            raise CostedRuntimeError("provider detail must not be persisted")

    loop_path = _wire_running_snapshot_test(monkeypatch, tmp_path, ExplodingEngine())

    with pytest.raises(RuntimeError, match="provider detail"):
        _run_sync_with_loop_guard(
            SimpleNamespace(name="GPU Expert"),
            name="GPU Expert",
            budget=0.5,
            sync_all=False,
            dry_run=False,
            scheduled=True,
            jitter=0.0,
            use_local=True,
            local_model="local-model",
            use_plan=False,
            plan_adapter=None,
            plan_model=None,
            context_builder=None,
        )

    rows = [json.loads(line) for line in loop_path.read_text(encoding="utf-8").splitlines()]
    assert [row["status"] for row in rows] == ["running", "failed"]
    assert rows[0]["run_id"] == rows[1]["run_id"]
    assert rows[1]["stop_reason"] == "tool_failure"
    assert rows[1]["failure_reason"] == "sync execution failed: CostedRuntimeError"
    assert rows[1]["budget_spent"] == 0.17
    assert "provider detail" not in rows[1]["failure_reason"]


def test_sync_all_failure_reuses_running_id_and_preserves_known_spend(monkeypatch):
    from deepr.cli.commands.semantic.expert_sync_all import _make_sync_one, _PassBackend

    captured = []
    profile = SimpleNamespace(name="GPU Expert")

    class FakeStore:
        def load(self, name):
            return profile

    class CostedRuntimeError(RuntimeError):
        actual_cost = 0.23

    class ExplodingEngine:
        async def sync(self, **kwargs):
            raise CostedRuntimeError("private provider detail")

    def fake_record_loop_run(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(to_dict=lambda: {"run_id": kwargs["run_id"]})

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    monkeypatch.setattr(
        "deepr.experts.maintenance_engine.build_sync_engine",
        lambda *args, **kwargs: (ExplodingEngine(), "local"),
    )
    monkeypatch.setattr("deepr.experts.loop_runs.record_loop_run", fake_record_loop_run)
    monkeypatch.setattr(
        "deepr.experts.self_model.build_expert_self_model_context_from_profile",
        lambda profile, *, focus_limit=3: {},
    )
    monkeypatch.setattr(
        "deepr.experts.self_model_updates.build_self_model_update_context",
        lambda expert_name: {"accepted_record_count": 0},
    )
    sync_one = _make_sync_one(
        backend=_PassBackend(use_local=True, local_model="local-model"),
        include_all=True,
        scheduled=True,
    )

    with pytest.raises(CostedRuntimeError, match="private provider detail"):
        asyncio.run(sync_one("GPU Expert", 0.5, False))

    assert [record["status"].value for record in captured] == ["running", "failed"]
    assert captured[0]["run_id"] == captured[1]["run_id"]
    assert captured[1]["budget_spent"] == 0.23
    assert captured[1]["failure_reason"] == "sync execution failed: CostedRuntimeError"
    assert "private provider detail" not in captured[1]["failure_reason"]
