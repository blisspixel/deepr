"""CLI tests for `deepr expert sync-all`.

The roster loop is unit-tested in test_sync_all.py; here we exercise the command
layer (backend resolution, scheduled wait, rendering) with the engine and store
injected so nothing touches providers or disk.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from deepr.backends.local_capacity import LocalCapacityObservation, LocalCapacityState
from deepr.cli.commands.semantic.experts import expert
from deepr.experts.heartbeat import HeartbeatDelivery
from deepr.experts.sync import Subscription, SyncOutcome, SyncResult


def _tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | None]]:
    """Capture relative path kinds and file bytes without unstable metadata."""
    return {
        path.relative_to(root).as_posix(): ("directory", None) if path.is_dir() else ("file", path.read_bytes())
        for path in sorted(root.rglob("*"), key=lambda candidate: candidate.as_posix())
    }


def _sync_result(*outcomes: SyncOutcome, cost: float = 0.0) -> SyncResult:
    return SyncResult(expert_name="x", started_at=datetime.now(UTC), outcomes=list(outcomes), total_cost=cost)


def _assert_aggregate_invariants(payload: dict, *, roster_experts: int) -> None:
    assert payload["experts"] == len(payload["summaries"])
    assert sum(payload["status_counts"].values()) == payload["experts"]
    assert payload["roster_experts"] == roster_experts


def _delivered_heartbeat() -> HeartbeatDelivery:
    return HeartbeatDelivery(attempted=True, delivered=True, http_status=204)


def _failed_heartbeat(*, failure_kind: str = "network_error", http_status: int | None = None) -> HeartbeatDelivery:
    return HeartbeatDelivery(
        attempted=True,
        delivered=False,
        failure_kind=failure_kind,
        http_status=http_status,
    )


def test_scheduled_sync_all_rejects_metered_api_before_roster_access(monkeypatch):
    monkeypatch.setattr(
        "deepr.cli.commands.semantic.expert_sync_all._inspect_roster",
        lambda **_: pytest.fail("scheduled metered refusal must happen before roster access"),
    )

    result = CliRunner().invoke(expert, ["sync-all", "--scheduled", "--api", "--json"])

    assert result.exit_code == 2
    assert "--scheduled cannot use --api" in result.output
    assert "work a person is" in result.output
    assert "watching" in result.output


def _assert_heartbeat_evidence(
    evidence: dict,
    *,
    configured: bool,
    configuration_valid: bool | None,
    scheduled: bool,
    dry_run: bool,
    attempted: bool,
    delivered: bool,
    reported_status: str | None,
    disposition: str,
    failure_kind: str | None = None,
    http_status: int | None = None,
) -> None:
    assert set(evidence) == {
        "configured",
        "configuration_valid",
        "scheduled",
        "dry_run",
        "attempted",
        "attempt_count",
        "attempted_at",
        "duration_ms",
        "delivered",
        "reported_status",
        "disposition",
        "failure_kind",
        "http_status",
    }
    assert evidence["configured"] is configured
    assert evidence["configuration_valid"] is configuration_valid
    assert evidence["scheduled"] is scheduled
    assert evidence["dry_run"] is dry_run
    assert evidence["attempted"] is attempted
    assert evidence["attempt_count"] == int(attempted)
    assert evidence["delivered"] is delivered
    assert evidence["reported_status"] == reported_status
    assert evidence["disposition"] == disposition
    assert evidence["failure_kind"] == failure_kind
    assert evidence["http_status"] == http_status
    if attempted:
        assert datetime.fromisoformat(evidence["attempted_at"]).tzinfo is not None
        assert isinstance(evidence["duration_ms"], int)
        assert evidence["duration_ms"] >= 0
    else:
        assert evidence["attempted_at"] is None
        assert evidence["duration_ms"] is None


def _wire(
    monkeypatch,
    result: SyncResult,
    *,
    names=("Alpha", "Beta"),
    local_model="qwen-local",
    recorded=None,
    profiles=None,
    built=None,
    loaded=None,
    loop_events=None,
    due_names=None,
    subscribed_names=None,
    profile_errors=(),
    subscription_failures=(),
    due_failures=(),
):
    profiles = profiles or [SimpleNamespace(name=n) for n in names]
    due_names = set(names if due_names is None else due_names)
    subscribed_names = set(names if subscribed_names is None else subscribed_names)
    subscription_failures = set(subscription_failures)
    due_failures = set(due_failures)

    class FakeProfiles(list):
        errors = list(profile_errors)

    profile_rows = FakeProfiles(profiles)

    class FakeStore:
        def __init__(self, *args, **kwargs):
            self.read_only = kwargs.get("create") is False

        def list_all(self, include_errors=False):
            return profile_rows

        def load(self, name, *args, **kwargs):
            if loaded is not None:
                loaded.append((name, kwargs))
            return next(profile for profile in profiles if profile.name == name)

    class FakeEngine:
        async def sync(self, **kwargs):
            return result

    class FakeSubscriptionStore:
        def __init__(self, name):
            self.name = name
            self.load_failed = name in subscription_failures
            self.subscriptions = [Subscription(topic="t")] if name in subscribed_names else []

        def due(self, now=None):
            if self.name in due_failures:
                raise ValueError("invalid persisted cadence token=private")
            return list(self.subscriptions) if self.name in due_names else []

    monkeypatch.setattr("deepr.experts.profile.ExpertStore", FakeStore)
    monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", FakeSubscriptionStore)
    monkeypatch.setattr("deepr.experts.sync_all.SubscriptionStore", FakeSubscriptionStore)

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
            def __init__(self, *args, **kwargs):
                assert kwargs.get("create") is False

            def list_all(self, include_errors=False):
                return []

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", EmptyStore)
        r = CliRunner().invoke(expert, ["sync-all", "--local", "-y"])
        assert r.exit_code == 0
        assert "No experts yet" in r.output
        assert "deepr expert make NAME --local" in r.output

    def test_no_experts_json_is_a_versioned_completion_with_next_action(self, monkeypatch):
        class EmptyStore:
            def __init__(self, *args, **kwargs):
                assert kwargs.get("create") is False

            def list_all(self, include_errors=False):
                return []

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", EmptyStore)
        result = CliRunner().invoke(expert, ["sync-all", "--local", "-y", "--json"])

        assert result.exit_code == 0
        import json

        payload = json.loads(result.output)
        assert payload["schema_version"] == "deepr-library-sync-v1"
        assert payload["status"] == "completed"
        assert payload["experts"] == 0
        assert payload["next_action"] == {
            "kind": "create_expert",
            "command_argv": ["deepr", "expert", "make", "NAME", "--local"],
            "requires_user_input": ["NAME"],
        }
        _assert_heartbeat_evidence(
            payload["heartbeat"],
            configured=False,
            configuration_valid=None,
            scheduled=False,
            dry_run=False,
            attempted=False,
            delivered=False,
            reported_status=None,
            disposition="not_configured",
        )
        _assert_aggregate_invariants(payload, roster_experts=0)

    def test_empty_roster_dry_run_is_an_explicit_zero_change_preview(self, monkeypatch):
        class EmptyStore:
            def __init__(self, *args, **kwargs):
                assert kwargs.get("create") is False

            def list_all(self, include_errors=False):
                return []

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", EmptyStore)

        result = CliRunner().invoke(expert, ["sync-all", "--api", "--dry-run", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["dry_run"] is True
        assert payload["state_changes"] == 0
        assert payload["status"] == "completed"
        _assert_aggregate_invariants(payload, roster_experts=0)

    def test_scheduled_empty_roster_reports_success_heartbeat(self, monkeypatch):
        class EmptyStore:
            def __init__(self, *args, **kwargs):
                assert kwargs.get("create") is False

            def list_all(self, include_errors=False):
                return []

        pinged = []
        monkeypatch.setattr("deepr.experts.profile.ExpertStore", EmptyStore)
        monkeypatch.setenv("DEEPR_HEARTBEAT_URL", "https://hc.example/secret")
        monkeypatch.setattr(
            "deepr.experts.heartbeat.deliver_heartbeat",
            lambda **kw: pinged.append(kw) or _delivered_heartbeat(),
        )

        result = CliRunner().invoke(expert, ["sync-all", "--scheduled", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["status"] == "completed"
        _assert_heartbeat_evidence(
            payload["heartbeat"],
            configured=True,
            configuration_valid=True,
            scheduled=True,
            dry_run=False,
            attempted=True,
            delivered=True,
            reported_status="success",
            disposition="delivered",
            http_status=204,
        )
        _assert_aggregate_invariants(payload, roster_experts=0)
        assert pinged == [{"success": True, "url": "https://hc.example/secret"}]

    @pytest.mark.parametrize(
        "option,value",
        [
            ("--budget", "-1"),
            ("--budget", "nan"),
            ("--budget", "inf"),
            ("--per-expert-budget", "-1"),
            ("--per-expert-budget", "nan"),
            ("--per-expert-budget", "inf"),
        ],
    )
    def test_rejects_invalid_budget_before_roster_work(self, monkeypatch, option, value):
        touched = False

        class UntouchedStore:
            def list_all(self, include_errors=False):
                nonlocal touched
                touched = True
                return []

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", UntouchedStore)
        result = CliRunner().invoke(expert, ["sync-all", option, value, "--local", "-y"])

        assert result.exit_code == 2
        assert "finite and non-negative" in result.output
        assert touched is False

    def test_help_describes_current_gates_and_complete_examples(self):
        result = CliRunner().invoke(expert, ["sync-all", "--help"], terminal_width=120)
        normalized = " ".join(result.output.split())

        assert result.exit_code == 0
        assert "--plan claude -y" in normalized
        assert "--plan codex -y" not in normalized
        assert "execution is currently gated" in normalized
        assert "continues after individual failures" in normalized
        assert "Sync every subscription regardless of cadence" in normalized
        assert "expected terminal outcomes" in normalized
        assert "dead-man's-switch" in normalized

    def test_profile_corruption_blocks_before_backend_resolution(self, monkeypatch):
        touched_backend = False
        pinged = []

        class BrokenProfiles(list):
            errors = [(Path("broken/profile.json"), "token=private")]

        class BrokenStore:
            def __init__(self, *args, **kwargs):
                assert kwargs.get("create") is False

            def list_all(self, include_errors=False):
                return BrokenProfiles()

        def fail_backend(*args, **kwargs):
            nonlocal touched_backend
            touched_backend = True
            raise AssertionError("backend resolution must not run")

        monkeypatch.setattr("deepr.experts.profile.ExpertStore", BrokenStore)
        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_sync_all._resolve_pass_backend",
            fail_backend,
        )
        monkeypatch.setenv("DEEPR_HEARTBEAT_URL", "https://hc.example/secret")
        monkeypatch.setattr(
            "deepr.experts.heartbeat.deliver_heartbeat",
            lambda **kw: pinged.append(kw) or _delivered_heartbeat(),
        )

        result = CliRunner().invoke(expert, ["sync-all", "--scheduled", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["schema_version"] == "deepr-library-sync-v1"
        assert payload["status"] == "blocked_storage_state"
        assert payload["exit_code"] == 1
        assert payload["state_errors"] == {"profiles": 1, "subscriptions": 0}
        assert payload["heartbeat"]["reported_status"] == "failure"
        _assert_aggregate_invariants(payload, roster_experts=0)
        assert "private" not in result.output
        assert touched_backend is False
        assert pinged == [{"success": False, "url": "https://hc.example/secret"}]

    def test_non_directory_experts_root_is_blocked_state(self, monkeypatch, tmp_path):
        invalid_root = tmp_path / "experts"
        invalid_root.write_text("not a directory", encoding="utf-8")
        touched_backend = False
        pinged = []

        def fail_backend(*args, **kwargs):
            nonlocal touched_backend
            touched_backend = True
            raise AssertionError("backend resolution must not run")

        monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(invalid_root))
        monkeypatch.setenv("DEEPR_HEARTBEAT_URL", "https://hc.example/secret")
        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_sync_all._resolve_pass_backend",
            fail_backend,
        )
        monkeypatch.setattr(
            "deepr.experts.heartbeat.deliver_heartbeat",
            lambda **kw: pinged.append(kw) or _delivered_heartbeat(),
        )

        result = CliRunner().invoke(expert, ["sync-all", "--scheduled", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["status"] == "blocked_storage_state"
        assert payload["state_errors"] == {"profiles": 1, "subscriptions": 0}
        assert payload["heartbeat"]["reported_status"] == "failure"
        _assert_aggregate_invariants(payload, roster_experts=0)
        assert touched_backend is False
        assert pinged == [{"success": False, "url": "https://hc.example/secret"}]


class TestRun:
    def test_local_pass_syncs_roster_and_records_loops(self, monkeypatch):
        recorded: list = []
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced", absorbed=2), cost=0.0), recorded=recorded)

        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y", "--json"])

        assert r.exit_code == 0, r.output
        import json

        payload = json.loads(r.output)
        assert payload["schema_version"] == "deepr-library-sync-v1"
        assert payload["status"] == "completed"
        assert payload["exit_code"] == 0
        assert payload["synced_experts"] == 2
        assert {row["expert"] for row in payload["summaries"]} == {"Alpha", "Beta"}
        _assert_aggregate_invariants(payload, roster_experts=2)
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

    def test_human_render_escapes_literal_expert_markup(self, monkeypatch):
        _wire(
            monkeypatch,
            _sync_result(SyncOutcome("t", "synced"), cost=0.0),
            names=("[red]Literal[/red]",),
        )

        result = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y"])

        assert result.exit_code == 0, result.output
        assert "[red]Literal[/red]" in result.output

    def test_human_render_makes_expert_control_characters_visible(self, monkeypatch):
        name = "Alpha\nBeta\rGamma\tDelta\x1b[31m"
        _wire(
            monkeypatch,
            _sync_result(SyncOutcome("t", "synced"), cost=0.0),
            names=(name,),
        )

        result = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y"])

        assert result.exit_code == 0, result.output
        assert "Alpha\\nBeta\\rGamma\\tDelta\\x1b[31m" in result.output
        assert "\x1b[31m" not in result.output

    def test_json_cancellation_keeps_stdout_machine_parseable(self, monkeypatch):
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0), names=("Alpha",))

        result = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "--json"], input="n\n")

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["schema_version"] == "deepr-library-sync-v1"
        assert payload["status"] == "cancelled"
        assert payload["exit_code"] == 0
        _assert_aggregate_invariants(payload, roster_experts=1)
        assert "Sync up to 1 expert" in result.stderr
        assert "Cancelled." not in result.stdout
        assert payload["next_action"]["command_argv"] == [
            "deepr",
            "expert",
            "sync-all",
            "--budget",
            "5",
            "--per-expert-budget",
            "0.5",
            "--all",
            "--local",
            "--json",
        ]

    def test_scheduled_cancellation_reports_failed_heartbeat_and_retry_mode(self, monkeypatch):
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0), names=("Alpha",))
        pinged = []
        monkeypatch.setenv("DEEPR_HEARTBEAT_URL", "https://hc.example/secret")
        monkeypatch.setattr(
            "deepr.experts.heartbeat.deliver_heartbeat",
            lambda **kw: pinged.append(kw) or _delivered_heartbeat(),
        )

        result = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "--json"],
            input="n\n",
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["status"] == "cancelled"
        assert "--scheduled" in payload["next_action"]["command_argv"]
        assert payload["heartbeat"]["reported_status"] == "failure"
        _assert_aggregate_invariants(payload, roster_experts=1)
        assert pinged == [{"success": False, "url": "https://hc.example/secret"}]

    def test_mixed_roster_cancellation_separates_pending_and_roster_counts(self, monkeypatch):
        _wire(
            monkeypatch,
            _sync_result(SyncOutcome("t", "synced"), cost=0.0),
            names=("Subscribed", "Empty"),
            subscribed_names=("Subscribed",),
        )

        result = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--json"],
            input="n\n",
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert "Sync up to 1 expert" in result.stderr
        _assert_aggregate_invariants(payload, roster_experts=2)

    def test_subscription_corruption_blocks_before_backend_resolution(self, monkeypatch):
        _wire(
            monkeypatch,
            _sync_result(SyncOutcome("t", "synced"), cost=0.0),
            names=("Alpha",),
            subscription_failures=("Alpha",),
        )
        touched_backend = False

        def fail_backend(*args, **kwargs):
            nonlocal touched_backend
            touched_backend = True
            raise AssertionError("backend resolution must not run")

        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_sync_all._resolve_pass_backend",
            fail_backend,
        )

        result = CliRunner().invoke(expert, ["sync-all", "--scheduled", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["status"] == "blocked_storage_state"
        assert payload["state_errors"] == {"profiles": 0, "subscriptions": 1}
        _assert_aggregate_invariants(payload, roster_experts=1)
        assert touched_backend is False

    def test_due_evaluation_failure_blocks_before_backend_resolution(self, monkeypatch):
        _wire(
            monkeypatch,
            _sync_result(SyncOutcome("t", "synced"), cost=0.0),
            names=("Alpha",),
            due_failures=("Alpha",),
        )
        touched_backend = False

        def fail_backend(*args, **kwargs):
            nonlocal touched_backend
            touched_backend = True
            raise AssertionError("backend resolution must not run")

        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_sync_all._resolve_pass_backend",
            fail_backend,
        )

        result = CliRunner().invoke(expert, ["sync-all", "--scheduled", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload["status"] == "blocked_storage_state"
        assert payload["state_errors"] == {"profiles": 0, "subscriptions": 1}
        _assert_aggregate_invariants(payload, roster_experts=1)
        assert "private" not in result.output
        assert touched_backend is False

    def test_all_skips_engine_construction_for_experts_without_subscriptions(self, monkeypatch):
        built: list = []
        _wire(
            monkeypatch,
            _sync_result(SyncOutcome("t", "synced"), cost=0.0),
            names=("Subscribed", "Empty"),
            subscribed_names=("Subscribed",),
            built=built,
        )

        result = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert [(row["expert"], row["status"]) for row in payload["summaries"]] == [
            ("Subscribed", "synced"),
            ("Empty", "no_changes"),
        ]
        assert [name for name, _ in built] == ["Subscribed"]
        _assert_aggregate_invariants(payload, roster_experts=2)

    def test_human_partial_failure_preserves_success_and_failure_counts(self, monkeypatch):
        _wire(
            monkeypatch,
            _sync_result(
                SyncOutcome("good", "synced", absorbed=2, flagged=1),
                SyncOutcome("bad", "failed", detail="private provider detail"),
                cost=0.25,
            ),
            names=("Alpha",),
        )

        result = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y"])

        assert result.exit_code == 1
        assert "partial failure" in result.output
        assert "1 topic synced" in result.output
        assert "1 failed" in result.output
        assert "+2 beliefs" in result.output
        assert "$0.250 local" in result.output
        assert "private provider detail" not in result.output
        assert "deepr expert loop-status NAME --json" in result.output

    def test_dry_run_does_not_record(self, monkeypatch):
        recorded: list = []
        built: list = []
        loaded: list = []
        _wire(
            monkeypatch,
            _sync_result(SyncOutcome("t", "would_sync"), cost=0.0),
            recorded=recorded,
            built=built,
            loaded=loaded,
        )
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "--dry-run", "--json"])
        assert r.exit_code == 0
        import json

        payload = json.loads(r.output)
        assert payload["status_counts"]["would_sync"] == 2
        assert {row["status"] for row in payload["summaries"]} == {"would_sync"}
        assert payload["dry_run"] is True
        assert payload["state_changes"] == 0
        assert recorded == []
        assert loaded == []
        assert built == []

    def test_dry_run_human_output_is_visibly_a_preview(self, monkeypatch):
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "would_sync"), cost=0.0), names=("Alpha",))

        result = CliRunner().invoke(expert, ["sync-all", "--all", "--api", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "Library sync preview" in result.output
        assert "1 expert reviewed" in result.output
        assert "Preview only: no research, spend, or expert files changed." in result.output
        assert "$0.000 spent" not in result.output

    @pytest.mark.parametrize("belief_state", ["missing", "legacy"])
    def test_dry_run_preserves_every_expert_tree_path_and_byte(self, monkeypatch, tmp_path, belief_state):
        from deepr.experts.beliefs import Belief
        from deepr.experts.profile import ExpertProfile, ExpertStore
        from deepr.experts.sync import Subscription, SubscriptionStore

        experts_root = tmp_path / "experts"
        monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(experts_root))
        name = "Preview Expert"
        profiles = ExpertStore()
        profiles.save(ExpertProfile(name=name, vector_store_id="vs-preview"))
        expert_dir = profiles.find_existing_dir(name)
        assert expert_dir is not None

        profile_path = expert_dir / "profile.json"
        profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
        profile_data["schema_version"] = 3
        profile_data.pop("portrait_url", None)
        profile_path.write_text(json.dumps(profile_data, indent=2), encoding="utf-8")
        SubscriptionStore(name).add(Subscription(topic="Current model releases"))
        beliefs_dir = expert_dir / "beliefs"
        if belief_state == "missing":
            beliefs_dir.rmdir()
        else:
            belief = Belief(claim="A legacy contradiction", confidence=0.8, domain="testing")
            belief.contradictions_with.append("missing-peer")
            (beliefs_dir / "beliefs.json").write_text(
                json.dumps(
                    {
                        "edges": [],
                        "beliefs": {belief.id: belief.to_dict()},
                        "changes": [],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        before = _tree_snapshot(experts_root)

        result = CliRunner().invoke(expert, ["sync-all", "--all", "--api", "--dry-run", "--json"])

        assert result.exit_code == 0, result.output
        assert _tree_snapshot(experts_root) == before
        payload = json.loads(result.stdout)
        assert payload["dry_run"] is True
        assert payload["state_changes"] == 0
        assert payload["status_counts"]["would_sync"] == 1

    def test_completed_failure_renders_safe_recovery_then_exits_one(self, monkeypatch):
        _wire(
            monkeypatch,
            _sync_result(
                SyncOutcome(
                    "private-topic",
                    "failed",
                    detail="signed_url=https://secret.example?token=abc",
                    retryable=True,
                    no_metered_fallback=True,
                ),
                cost=0.0,
            ),
            names=("Alpha",),
        )

        result = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "-y", "--json"])

        assert result.exit_code == 1
        import json

        payload = json.loads(result.output)
        assert payload["status"] == "completed_with_failures"
        assert payload["exit_code"] == 1
        assert payload["failed_experts"] == 1
        assert "secret.example" not in result.output
        assert payload["summaries"][0]["failures"] == [
            {
                "topic": "private-topic",
                "error_code": "EXPERT_SYNC_TOPIC_FAILED",
                "retryable": True,
                "no_metered_fallback": True,
                "inspect_command_argv": ["deepr", "expert", "loop-status", "Alpha", "--json"],
            }
        ]

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

    def test_non_dry_reloads_subscription_state_before_dispatch(self, monkeypatch):
        built: list = []
        _wire(
            monkeypatch,
            _sync_result(SyncOutcome("t", "synced"), cost=0.0),
            names=("Alpha",),
            built=built,
        )
        constructed: list[str] = []

        class ChangingSubscriptionStore:
            load_failed = False

            def __init__(self, name):
                self.name = name
                self.snapshot = len(constructed)
                self.subscriptions = [Subscription(topic="t")]
                constructed.append(name)

            def due(self, now=None):
                return list(self.subscriptions) if self.snapshot == 0 else []

        monkeypatch.setattr("deepr.experts.sync.SubscriptionStore", ChangingSubscriptionStore)
        monkeypatch.setattr("deepr.experts.sync_all.SubscriptionStore", ChangingSubscriptionStore)

        result = CliRunner().invoke(expert, ["sync-all", "--local", "-y", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["status_counts"]["not_due"] == 1
        assert built == []
        assert constructed == ["Alpha", "Alpha"]


class TestCapacity:
    def test_scheduled_waits_when_no_owned_capacity(self, monkeypatch):
        # Auto waterfall returns metered (not local) -> a scheduled pass waits.
        monkeypatch.setattr(
            "deepr.backends.waterfall.choose_maintenance_backend",
            lambda task_class: SimpleNamespace(is_local=False, is_plan_quota=False, reason=""),
        )
        _wire(monkeypatch, _sync_result(cost=0.0))
        pinged = []
        monkeypatch.setenv("DEEPR_HEARTBEAT_URL", "https://hc.example/secret")
        monkeypatch.setattr(
            "deepr.experts.heartbeat.deliver_heartbeat",
            lambda **kw: pinged.append(kw) or _delivered_heartbeat(),
        )
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--scheduled", "--json"])
        assert r.exit_code == 0
        payload = json.loads(r.stdout)
        assert payload["schema_version"] == "deepr-library-sync-v1"
        assert payload["status"] == "waiting_for_capacity"
        assert payload["exit_code"] == 0
        _assert_aggregate_invariants(payload, roster_experts=2)
        _assert_heartbeat_evidence(
            payload["heartbeat"],
            configured=True,
            configuration_valid=True,
            scheduled=True,
            dry_run=False,
            attempted=True,
            delivered=True,
            reported_status="failure",
            disposition="delivered",
            http_status=204,
        )
        assert pinged == [{"success": False, "url": "https://hc.example/secret"}]

    def test_scheduled_dry_run_wait_is_visibly_a_preview(self, monkeypatch):
        monkeypatch.setattr(
            "deepr.backends.waterfall.choose_maintenance_backend",
            lambda task_class: SimpleNamespace(is_local=False, is_plan_quota=False, reason=""),
        )
        _wire(monkeypatch, _sync_result(cost=0.0), names=("Alpha",))

        result = CliRunner().invoke(expert, ["sync-all", "--all", "--scheduled", "--dry-run"])

        assert result.exit_code == 0, result.output
        assert "Library sync preview" in result.output
        assert "waiting for owned/prepaid capacity" in result.output
        assert "Preview only: no research, spend, or expert files changed." in result.output

    def test_scheduled_no_due_work_completes_before_backend_resolution(self, monkeypatch):
        _wire(
            monkeypatch,
            _sync_result(cost=0.0),
            names=("Alpha", "Beta"),
            due_names=(),
        )
        touched_backend = False
        pinged = []

        def fail_backend(*args, **kwargs):
            nonlocal touched_backend
            touched_backend = True
            raise AssertionError("backend resolution must not run")

        monkeypatch.setattr(
            "deepr.cli.commands.semantic.expert_sync_all._resolve_pass_backend",
            fail_backend,
        )
        monkeypatch.setenv("DEEPR_HEARTBEAT_URL", "https://hc.example/secret")
        monkeypatch.setattr(
            "deepr.experts.heartbeat.deliver_heartbeat",
            lambda **kw: pinged.append(kw) or _delivered_heartbeat(),
        )

        result = CliRunner().invoke(expert, ["sync-all", "--scheduled", "--json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["status"] == "completed"
        assert payload["status_counts"]["not_due"] == 2
        assert {row["status"] for row in payload["summaries"]} == {"not_due"}
        assert payload["heartbeat"]["reported_status"] == "success"
        _assert_aggregate_invariants(payload, roster_experts=2)
        assert pinged == [{"success": True, "url": "https://hc.example/secret"}]
        assert touched_backend is False

    def test_scheduled_local_busy_wait_uses_versioned_envelope(self, monkeypatch):
        _wire(monkeypatch, _sync_result(cost=0.0), names=("Alpha",))
        busy = LocalCapacityObservation(
            state=LocalCapacityState.BUSY,
            source="test",
            detail="GPU is occupied",
        )
        retry_at = datetime(2026, 7, 22, 21, 0, tzinfo=UTC)
        wait = SimpleNamespace(
            retry_at=retry_at,
            retry_after_seconds=60,
            to_dict=lambda: {"expert": "Alpha", "retry_at": retry_at.isoformat()},
        )
        pinged = []
        monkeypatch.setattr("deepr.backends.local_capacity.probe_local_gpu_occupancy", lambda: busy)
        monkeypatch.setattr(
            "deepr.experts.scheduled_local_capacity.record_scheduled_local_capacity_wait",
            lambda **kwargs: wait,
        )
        monkeypatch.setenv("DEEPR_HEARTBEAT_URL", "https://hc.example/secret")
        monkeypatch.setattr(
            "deepr.experts.heartbeat.deliver_heartbeat",
            lambda **kw: pinged.append(kw) or _delivered_heartbeat(),
        )

        result = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "-y", "--json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["schema_version"] == "deepr-library-sync-v1"
        assert payload["status"] == "waiting_for_capacity"
        assert payload["exit_code"] == 0
        assert payload["capacity_unavailable_reason"] == "local_gpu_busy"
        assert payload["heartbeat"]["reported_status"] == "failure"
        _assert_aggregate_invariants(payload, roster_experts=1)
        assert pinged == [{"success": False, "url": "https://hc.example/secret"}]

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

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        recorded: list = []
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0), recorded=recorded)

        r = CliRunner().invoke(expert, ["sync-all", "--all", "--plan", "claude", "-y", "--json"])

        assert r.exit_code == 0, r.output
        payload = json.loads(r.output)
        assert {row["capacity_source"] for row in payload["summaries"]} == {"plan_quota:claude"}
        assert recorded == [("Alpha", "plan_quota:claude"), ("Beta", "plan_quota:claude")]

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
        monkeypatch.setenv("DEEPR_HEARTBEAT_URL", "https://hc.example/secret")
        monkeypatch.setattr(
            "deepr.experts.heartbeat.deliver_heartbeat",
            lambda **kw: pinged.append(kw) or _delivered_heartbeat(),
        )
        return pinged

    def test_scheduled_success_pings_heartbeat(self, monkeypatch):
        pinged = self._capture(monkeypatch)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "--scheduled", "-y", "--json"])
        assert r.exit_code == 0
        assert pinged == [{"success": True, "url": "https://hc.example/secret"}]
        _assert_heartbeat_evidence(
            json.loads(r.stdout)["heartbeat"],
            configured=True,
            configuration_valid=True,
            scheduled=True,
            dry_run=False,
            attempted=True,
            delivered=True,
            reported_status="success",
            disposition="delivered",
            http_status=204,
        )

    def test_scheduled_failure_pings_fail(self, monkeypatch):
        pinged = self._capture(monkeypatch)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "failed", detail="boom"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "--scheduled", "-y", "--json"])
        assert r.exit_code == 1
        assert pinged == [{"success": False, "url": "https://hc.example/secret"}]

    def test_scheduled_partial_failure_pings_fail_and_exits_one(self, monkeypatch):
        pinged = self._capture(monkeypatch)
        _wire(
            monkeypatch,
            _sync_result(SyncOutcome("ok", "synced"), SyncOutcome("bad", "failed"), cost=0.0),
            names=("Alpha",),
        )

        result = CliRunner().invoke(expert, ["sync-all", "--all", "--local", "--scheduled", "-y", "--json"])

        assert result.exit_code == 1
        assert pinged == [{"success": False, "url": "https://hc.example/secret"}]
        import json

        payload = json.loads(result.output)
        assert payload["summaries"][0]["status"] == "partial_failure"
        assert payload["partial_failure_experts"] == 1
        assert payload["heartbeat"]["reported_status"] == "failure"

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

    def test_scheduled_dry_run_validates_configuration_without_delivery(self, monkeypatch):
        pinged = self._capture(monkeypatch)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "would_sync"), cost=0.0))

        structured = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "--dry-run", "--json"],
        )
        human = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "--dry-run"],
        )

        assert structured.exit_code == 0, structured.output
        heartbeat = json.loads(structured.stdout)["heartbeat"]
        assert heartbeat["configuration_valid"] is True
        assert heartbeat["disposition"] == "validated_not_sent"
        assert heartbeat["attempt_count"] == 0
        assert heartbeat["attempted_at"] is None
        assert heartbeat["duration_ms"] is None
        assert human.exit_code == 0, human.output
        assert "configuration is valid" in human.output
        assert "did not contact it" in human.output
        assert pinged == []

    def test_invalid_configuration_is_visible_and_never_requested(self, monkeypatch):
        monkeypatch.setenv("DEEPR_HEARTBEAT_URL", "http://hc.example/secret")
        pinged = []
        monkeypatch.setattr(
            "deepr.experts.heartbeat.deliver_heartbeat",
            lambda **kw: pinged.append(kw) or _delivered_heartbeat(),
        )
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "would_sync"), cost=0.0))

        structured = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "--dry-run", "--json"],
        )
        human = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "--dry-run"],
        )

        heartbeat = json.loads(structured.stdout)["heartbeat"]
        assert heartbeat["configured"] is True
        assert heartbeat["configuration_valid"] is False
        assert heartbeat["attempted"] is False
        assert heartbeat["disposition"] == "invalid_configuration"
        assert heartbeat["failure_kind"] == "invalid_configuration"
        assert "public HTTPS URL" in human.output
        assert "secret" not in human.output
        assert pinged == []

    def test_scheduled_human_output_confirms_missing_and_delivered_states(self, monkeypatch):
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0), names=("Alpha",))
        monkeypatch.delenv("DEEPR_HEARTBEAT_URL", raising=False)
        missing = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "-y"],
        )

        pinged = self._capture(monkeypatch)
        delivered = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "-y"],
        )

        assert missing.exit_code == 0, missing.output
        assert "heartbeat is not configured" in missing.output
        assert delivered.exit_code == 0, delivered.output
        assert "heartbeat delivered" in delivered.output
        assert "success" in delivered.output
        assert pinged == [{"success": True, "url": "https://hc.example/secret"}]

    def test_configured_delivery_failure_is_visible_but_non_fatal(self, monkeypatch):
        monkeypatch.setenv("DEEPR_HEARTBEAT_URL", "https://hc.example/secret")
        monkeypatch.setattr(
            "deepr.experts.heartbeat.deliver_heartbeat",
            lambda **kwargs: _failed_heartbeat(),
        )
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0), names=("Alpha",))

        structured = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "-y", "--json"],
        )
        human = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "-y"],
        )

        assert structured.exit_code == 0, structured.output
        _assert_heartbeat_evidence(
            json.loads(structured.stdout)["heartbeat"],
            configured=True,
            configuration_valid=True,
            scheduled=True,
            dry_run=False,
            attempted=True,
            delivered=False,
            reported_status="success",
            disposition="delivery_failed",
            failure_kind="network_error",
        )
        assert human.exit_code == 0, human.output
        assert "heartbeat delivery failed" in human.output
        assert "secret" not in human.output

    @pytest.mark.parametrize(
        ("delivery", "disposition", "message"),
        [
            (
                HeartbeatDelivery(attempted=False, delivered=False, failure_kind="unsafe_target"),
                "blocked_unsafe_target",
                "not a public address",
            ),
            (
                _failed_heartbeat(failure_kind="http_error", http_status=503),
                "delivery_failed",
                "HTTP 503",
            ),
        ],
    )
    def test_blocked_and_http_delivery_states_are_typed_and_secret_safe(
        self,
        monkeypatch,
        delivery,
        disposition,
        message,
    ):
        monkeypatch.setenv("DEEPR_HEARTBEAT_URL", "https://hc.example/secret")
        monkeypatch.setattr("deepr.experts.heartbeat.deliver_heartbeat", lambda **kwargs: delivery)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0), names=("Alpha",))

        structured = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "-y", "--json"],
        )
        human = CliRunner().invoke(
            expert,
            ["sync-all", "--all", "--local", "--scheduled", "-y"],
        )

        assert structured.exit_code == 0, structured.output
        heartbeat = json.loads(structured.stdout)["heartbeat"]
        assert heartbeat["disposition"] == disposition
        assert heartbeat["failure_kind"] == delivery.failure_kind
        assert heartbeat["http_status"] == delivery.http_status
        assert human.exit_code == 0, human.output
        assert message in human.output
        assert "secret" not in human.output


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

    def test_drained_pool_cannot_create_auto_metered_pass(self, monkeypatch):
        self._auto_metered(monkeypatch)
        self._manager(monkeypatch, spent=9.6)  # 96% -> LOCAL_ONLY
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "-y", "--json"])
        assert r.exit_code == 2
        assert "No owned or prepaid sync capacity" in r.output

    def test_drained_pool_human_path_still_requires_explicit_capacity(self, monkeypatch):
        self._auto_metered(monkeypatch)
        self._manager(monkeypatch, spent=9.6)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0))

        result = CliRunner().invoke(expert, ["sync-all", "--all", "-y"])

        assert result.exit_code == 2
        assert "No owned or prepaid sync capacity" in result.output

    def test_normal_tier_still_requires_explicit_api_selection(self, monkeypatch):
        self._auto_metered(monkeypatch)
        self._manager(monkeypatch, spent=1.0)  # 10% -> NORMAL
        built: list = []
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "synced"), cost=0.0), built=built)
        r = CliRunner().invoke(expert, ["sync-all", "--all", "-y", "--json"])
        assert r.exit_code == 2
        assert "No owned or prepaid sync capacity" in r.output
        assert built == []

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

    def test_dry_run_still_requires_explicit_capacity_selection(self, monkeypatch):
        self._auto_metered(monkeypatch)
        self._manager(monkeypatch, spent=9.6)
        _wire(monkeypatch, _sync_result(SyncOutcome("t", "would_sync"), cost=0.0))
        r = CliRunner().invoke(expert, ["sync-all", "--all", "--dry-run", "--json"])
        assert r.exit_code == 2
        assert "No owned or prepaid sync capacity" in r.output
