"""Tests for the cross-expert fleet-status rollup (read-only, $0).

The rollup folds per-expert loop runs + subscription cadence into one roster
view. Stores are injected (fakes) so these stay pure unit tests with no disk.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from deepr.experts.fleet_status import (
    FLEET_STATUS_SCHEMA_VERSION,
    build_fleet_status_rollup,
    fleet_needs_attention,
)
from deepr.experts.loop_runs import (
    ExpertLoopRun,
    ExpertLoopRunStore,
    LoopRunStatus,
    LoopStopReason,
    new_loop_run_id,
)
from deepr.experts.profile import ExpertProfile
from deepr.experts.profile_store import ExpertStore
from deepr.experts.sync import Subscription

NOW = datetime(2026, 6, 21, 12, 0, 0, tzinfo=UTC)


def _run(
    expert: str,
    status: LoopRunStatus,
    *,
    loop_type: str = "sync",
    stop_reason: LoopStopReason | None = None,
    budget: float = 0.0,
    accepted: int = 0,
    rejected: int = 0,
    trigger: str = "scheduled",
    next_action: dict | None = None,
    failure_reason: str = "",
    updated_at: datetime | None = None,
) -> ExpertLoopRun:
    return ExpertLoopRun(
        run_id=new_loop_run_id(),
        expert_name=expert,
        loop_type=loop_type,
        goal="g",
        trigger=trigger,
        status=status,
        stop_reason=stop_reason,
        budget_spent=budget,
        accepted_changes=accepted,
        rejected_changes=rejected,
        next_action=next_action or {},
        failure_reason=failure_reason,
        updated_at=updated_at or NOW,
    )


class _FakeLoopStore:
    def __init__(self, runs: list[ExpertLoopRun], *, load_failed: bool = False):
        # Newest first, as the real store returns.
        self._runs = runs
        self.load_failed = load_failed

    def list_runs(self, *, status=None, loop_type=None, limit=20):
        return self._runs[:limit]


class _FakeSubStore:
    def __init__(
        self,
        subscriptions: list[Subscription],
        due: list[Subscription],
        *,
        load_failed: bool = False,
    ):
        self.subscriptions = subscriptions
        self._due = due
        self.load_failed = load_failed

    def due(self, now=None):
        return self._due


def _build(experts, loops, subs, *, limit=20, loop_errors=frozenset(), subscription_errors=frozenset()):
    return build_fleet_status_rollup(
        expert_names=experts,
        now=NOW,
        limit=limit,
        loop_store_factory=lambda name: _FakeLoopStore(loops.get(name, []), load_failed=name in loop_errors),
        subscription_store_factory=lambda name: _FakeSubStore(
            *subs.get(name, ([], [])), load_failed=name in subscription_errors
        ),
    )


def _tree_snapshot(root):
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): ("directory", b"") if path.is_dir() else ("file", path.read_bytes())
        for path in sorted(root.rglob("*"))
    }


class TestEnvelope:
    def test_versioned_read_only_zero_cost_envelope(self):
        payload = _build(["A"], {}, {})
        assert payload["schema_version"] == FLEET_STATUS_SCHEMA_VERSION
        assert payload["kind"] == "deepr.expert.fleet_status"
        assert payload["contract"]["read_only"] is True
        assert payload["contract"]["cost_usd"] == 0.0
        assert payload["generated_at"] == NOW.isoformat()
        assert payload["complete"] is True
        assert payload["status"] == "completed"
        assert payload["exit_code"] == 0
        assert payload["state_errors"] == {"profiles": 0, "runs": 0, "subscriptions": 0}
        assert payload["state_error_refs"] == []
        assert payload["state_error_refs_omitted"] == 0
        assert payload["summary"]["observed"]["experts"] == 1

    def test_empty_roster(self):
        payload = _build([], {}, {})
        assert payload["summary"]["experts"] == 0
        assert payload["experts"] == []

    def test_missing_roster_is_verified_empty_without_creating_storage(self, tmp_path, monkeypatch):
        root = tmp_path / "missing-experts"
        monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(root))

        payload = build_fleet_status_rollup(now=NOW)

        assert payload["complete"] is True
        assert payload["status"] == "completed"
        assert payload["summary"]["experts"] == 0
        assert not root.exists()

    def test_invalid_roster_root_returns_bounded_incomplete_envelope(self, tmp_path, monkeypatch):
        root = tmp_path / "experts"
        root.write_text("not a directory", encoding="utf-8")
        monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(root))

        payload = build_fleet_status_rollup(now=NOW)

        assert payload["complete"] is False
        assert payload["status"] == "blocked_storage_state"
        assert payload["exit_code"] == 1
        assert payload["state_errors"] == {"profiles": 1, "runs": 0, "subscriptions": 0}
        assert payload["state_error_refs"] == [{"kind": "profiles_unreadable", "source": "experts-root"}]
        assert payload["next_action"]["source_field"] == "state_error_refs"
        assert payload["experts"] == []
        assert root.read_text(encoding="utf-8") == "not a directory"

    def test_limit_must_be_positive(self):
        with pytest.raises(ValueError):
            build_fleet_status_rollup(expert_names=["A"], limit=0)


class TestPerExpertRows:
    def test_never_run_expert(self):
        payload = _build(["Fresh"], {}, {})
        row = payload["experts"][0]
        assert row["has_runs"] is False
        assert row["last_run"] is None
        assert payload["summary"]["never_run"] == 1

    def test_latest_failed_raises_attention(self):
        loops = {"Broken": [_run("Broken", LoopRunStatus.FAILED, stop_reason=LoopStopReason.TOOL_FAILURE)]}
        payload = _build(["Broken"], loops, {})
        row = payload["experts"][0]
        assert row["attention"] is True
        assert payload["summary"]["attention"] == 1
        assert fleet_needs_attention(payload) is True

    def test_waiting_surfaces_next_action_without_attention(self):
        action = {"status": "wait", "title": "Wait for capacity"}
        loops = {
            "Paused": [
                _run(
                    "Paused",
                    LoopRunStatus.WAITING,
                    stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
                    next_action=action,
                )
            ]
        }
        payload = _build(["Paused"], loops, {})
        row = payload["experts"][0]
        assert row["waiting"] is True
        assert row["attention"] is False
        assert row["waiting_next_action"] == action
        assert payload["summary"]["waiting"] == 1
        assert fleet_needs_attention(payload) is False

    def test_maximum_supported_run_metadata_depth_is_preserved(self):
        nested: dict = {}
        for _ in range(64):
            nested = {"child": nested}
        loops = {
            "Deep": [
                _run(
                    "Deep",
                    LoopRunStatus.WAITING,
                    stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
                    next_action=nested,
                )
            ]
        }

        payload = _build(["Deep"], loops, {})

        current = payload["experts"][0]["waiting_next_action"]
        for _ in range(64):
            current = current["child"]
        assert current == {}
        assert "nesting limit exceeded" not in str(payload)
        assert payload["complete"] is True

    def test_unreadable_run_and_subscription_metrics_are_unknown(self):
        payload = _build(
            ["Unreadable"],
            {},
            {},
            loop_errors={"Unreadable"},
            subscription_errors={"Unreadable"},
        )
        row = payload["experts"][0]
        assert row["state_errors"] == ["runs_unreadable", "subscriptions_unreadable"]
        assert row["has_runs"] is None
        assert row["last_run"] is None
        assert row["attention"] is None
        assert row["subscriptions"] is None
        assert row["refresh_due"] is None
        assert row["due_topics"] is None
        assert payload["complete"] is False
        assert payload["state_errors"] == {"profiles": 0, "runs": 1, "subscriptions": 1}
        assert payload["summary"]["attention"] is None
        assert payload["summary"]["waiting"] is None
        assert payload["summary"]["refresh_due"] is None
        assert payload["summary"]["never_run"] is None
        assert payload["summary"]["budget_spent_window_total"] is None
        assert payload["summary"]["observed"] == {
            "experts": 1,
            "attention": 0,
            "waiting": 0,
            "refresh_due": 0,
            "never_run": 0,
            "budget_spent_window_total": 0.0,
        }
        assert fleet_needs_attention(payload) is True

    def test_state_error_references_are_bounded(self):
        experts = [f"Expert {index}" for index in range(25)]
        payload = _build(experts, {}, {}, subscription_errors=set(experts))

        assert payload["state_errors"]["subscriptions"] == 25
        assert len(payload["state_error_refs"]) == 20
        assert payload["state_error_refs_omitted"] == 5

    def test_only_affected_aggregate_dimension_becomes_unknown(self):
        failed = _run("Partial", LoopRunStatus.FAILED, stop_reason=LoopStopReason.TOOL_FAILURE)
        payload = _build(
            ["Partial"],
            {"Partial": [failed]},
            {},
            subscription_errors={"Partial"},
        )

        assert payload["summary"]["attention"] == 1
        assert payload["summary"]["waiting"] == 0
        assert payload["summary"]["never_run"] == 0
        assert payload["summary"]["budget_spent_window_total"] == 0.0
        assert payload["summary"]["refresh_due"] is None

    def test_refresh_due_from_subscriptions(self):
        subs = [Subscription(topic="LLMs"), Subscription(topic="Chips")]
        due = [subs[0]]
        payload = _build(["Tech"], {}, {"Tech": (subs, due)})
        row = payload["experts"][0]
        assert row["subscriptions"] == 2
        assert row["refresh_due"] == 1
        assert row["due_topics"] == ["LLMs"]
        assert payload["summary"]["refresh_due"] == 1

    def test_last_failure_found_even_when_latest_healthy(self):
        loops = {
            "Recovered": [
                _run("Recovered", LoopRunStatus.COMPLETED, stop_reason=LoopStopReason.VERIFIER_PASSED, accepted=3),
                _run("Recovered", LoopRunStatus.FAILED, stop_reason=LoopStopReason.VERIFIER_FAILED),
            ]
        }
        payload = _build(["Recovered"], loops, {})
        row = payload["experts"][0]
        assert row["attention"] is False  # latest is healthy
        assert row["last_failure"] is not None
        assert row["last_failure"]["status"] == "failed"

    def test_budget_aggregated_over_window(self):
        loops = {
            "Spendy": [
                _run("Spendy", LoopRunStatus.COMPLETED, stop_reason=LoopStopReason.NO_DUE_WORK, budget=0.10),
                _run("Spendy", LoopRunStatus.COMPLETED, stop_reason=LoopStopReason.NO_DUE_WORK, budget=0.05),
            ]
        }
        payload = _build(["Spendy"], loops, {})
        assert payload["experts"][0]["budget_spent_window"] == pytest.approx(0.15)
        assert payload["summary"]["budget_spent_window_total"] == pytest.approx(0.15)

    def test_acceptance_rate_on_last_run(self):
        loops = {
            "Loop": [
                _run(
                    "Loop",
                    LoopRunStatus.COMPLETED,
                    stop_reason=LoopStopReason.VERIFIER_PASSED,
                    accepted=3,
                    rejected=1,
                )
            ]
        }
        payload = _build(["Loop"], loops, {})
        assert payload["experts"][0]["last_run"]["acceptance_rate"] == pytest.approx(0.75)

    def test_host_payload_redacts_stored_credentials(self):
        loops = {
            "Secret": [
                _run(
                    "Secret",
                    LoopRunStatus.FAILED,
                    stop_reason=LoopStopReason.TOOL_FAILURE,
                    failure_reason=(
                        "token=top-secret-token https://example.test/result?X-Goog-Signature=signed-secret"
                    ),
                )
            ]
        }

        subscription = Subscription(topic="Safe topic")
        payload = _build(["Secret"], loops, {"Secret": ([subscription], [subscription])})
        encoded = str(payload)

        assert "top-secret-token" not in encoded
        assert "signed-secret" not in encoded
        assert "Safe topic" in encoded


class TestRealStorageIntegrity:
    def test_over_nested_run_metadata_is_fail_closed(self, tmp_path, monkeypatch):
        root = tmp_path / "experts"
        monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(root))
        store = ExpertStore(str(root))
        store.save(ExpertProfile(name="Nested", vector_store_id="vs-nested"))
        snapshot = _run(
            "Nested",
            LoopRunStatus.WAITING,
            stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
        ).to_dict()
        nested: dict = {}
        cursor = nested
        for _ in range(100):
            child: dict = {}
            cursor["child"] = child
            cursor = child
        snapshot["next_action"] = nested
        path = ExpertLoopRunStore("Nested").path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot) + "\n", encoding="utf-8")
        before = _tree_snapshot(root)

        payload = build_fleet_status_rollup(now=NOW)

        assert payload["complete"] is False
        assert payload["status"] == "blocked_storage_state"
        assert payload["exit_code"] == 1
        assert payload["state_errors"] == {"profiles": 0, "runs": 1, "subscriptions": 0}
        assert payload["experts"][0]["state_errors"] == ["runs_unreadable"]
        assert _tree_snapshot(root) == before

    def test_corruption_is_fail_closed_read_only_and_quiet(self, tmp_path, monkeypatch, caplog):
        root = tmp_path / "experts"
        monkeypatch.setenv("DEEPR_EXPERTS_PATH", str(root))
        store = ExpertStore(str(root))
        store.save(ExpertProfile(name="Subscription Broken", vector_store_id="vs-sub"))
        store.save(ExpertProfile(name="Runs Broken", vector_store_id="vs-run"))
        nested = "[" * 1500 + "]" * 1500
        (store.get_knowledge_dir("Subscription Broken") / "subscriptions.json").write_text(
            f'{{"subscriptions":{nested}}}', encoding="utf-8"
        )
        runs_path = ExpertLoopRunStore("Runs Broken").path
        runs_path.parent.mkdir(parents=True, exist_ok=True)
        runs_path.write_text(nested + "\n", encoding="utf-8")
        corrupt_profile = root / "unreadable-profile" / "profile.json"
        corrupt_profile.parent.mkdir(parents=True)
        corrupt_profile.write_text("{not-json", encoding="utf-8")
        before = _tree_snapshot(root)

        with caplog.at_level("ERROR"):
            payload = build_fleet_status_rollup(now=NOW)

        assert payload["complete"] is False
        assert payload["status"] == "blocked_storage_state"
        assert payload["exit_code"] == 1
        assert payload["state_errors"] == {"profiles": 1, "runs": 1, "subscriptions": 1}
        assert payload["summary"]["experts"] == 2
        assert payload["summary"]["state_errors"] == 3
        assert payload["summary"]["attention"] is None
        assert payload["summary"]["refresh_due"] is None
        assert payload["summary"]["budget_spent_window_total"] is None
        rows = {row["expert"]: row for row in payload["experts"]}
        assert rows["Subscription Broken"]["subscriptions"] is None
        assert rows["Subscription Broken"]["refresh_due"] is None
        assert rows["Runs Broken"]["has_runs"] is None
        assert fleet_needs_attention(payload) is True
        refs = payload["state_error_refs"]
        assert {ref["kind"] for ref in refs} == {
            "profile_unreadable",
            "runs_unreadable",
            "subscriptions_unreadable",
        }
        assert {ref["source"] for ref in refs} == {
            "unreadable-profile/profile.json",
            "loop_runs.jsonl",
            "knowledge/subscriptions.json",
        }
        assert all(str(root) not in str(ref) for ref in refs)
        assert _tree_snapshot(root) == before
        assert not [record for record in caplog.records if record.levelname == "ERROR"]


class TestOrdering:
    def test_anomalies_float_to_top(self):
        loops = {
            "Healthy": [_run("Healthy", LoopRunStatus.COMPLETED, stop_reason=LoopStopReason.NO_DUE_WORK)],
            "Broken": [_run("Broken", LoopRunStatus.FAILED, stop_reason=LoopStopReason.TOOL_FAILURE)],
        }
        subs = {"Healthy": ([Subscription(topic="X")], [Subscription(topic="X")])}
        payload = _build(["Healthy", "Broken"], loops, subs)
        order = [r["expert"] for r in payload["experts"]]
        # Broken (attention) must come before Healthy (only refresh-due).
        assert order == ["Broken", "Healthy"]
