"""Tests for the cross-expert fleet-status rollup (read-only, $0).

The rollup folds per-expert loop runs + subscription cadence into one roster
view. Stores are injected (fakes) so these stay pure unit tests with no disk.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deepr.experts.fleet_status import (
    FLEET_STATUS_SCHEMA_VERSION,
    build_fleet_status_rollup,
    fleet_needs_attention,
)
from deepr.experts.loop_runs import ExpertLoopRun, LoopRunStatus, LoopStopReason, new_loop_run_id
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
        updated_at=updated_at or NOW,
    )


class _FakeLoopStore:
    def __init__(self, runs: list[ExpertLoopRun]):
        # Newest first, as the real store returns.
        self._runs = runs

    def list_runs(self, *, status=None, loop_type=None, limit=20):
        return self._runs[:limit]


class _FakeSubStore:
    def __init__(self, subscriptions: list[Subscription], due: list[Subscription]):
        self.subscriptions = subscriptions
        self._due = due

    def due(self, now=None):
        return self._due


def _build(experts, loops, subs, *, limit=20):
    return build_fleet_status_rollup(
        expert_names=experts,
        now=NOW,
        limit=limit,
        loop_store_factory=lambda name: _FakeLoopStore(loops.get(name, [])),
        subscription_store_factory=lambda name: _FakeSubStore(*subs.get(name, ([], []))),
    )


class TestEnvelope:
    def test_versioned_read_only_zero_cost_envelope(self):
        payload = _build(["A"], {}, {})
        assert payload["schema_version"] == FLEET_STATUS_SCHEMA_VERSION
        assert payload["kind"] == "deepr.expert.fleet_status"
        assert payload["contract"]["read_only"] is True
        assert payload["contract"]["cost_usd"] == 0.0
        assert payload["generated_at"] == NOW.isoformat()

    def test_empty_roster(self):
        payload = _build([], {}, {})
        assert payload["summary"]["experts"] == 0
        assert payload["experts"] == []

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
