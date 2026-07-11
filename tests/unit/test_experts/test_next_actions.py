"""Tests for deterministic expert next-action guidance."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from deepr.core.contracts import Claim, ExpertManifest, Gap
from deepr.experts.next_actions import (
    EXPERT_NEXT_KIND,
    EXPERT_NEXT_SCHEMA_VERSION,
    build_expert_next_actions,
)
from deepr.experts.profile import ExpertProfile


def _profile(**overrides):
    values = {
        "name": "Agent Harness Expert",
        "vector_store_id": "",
        "domain": "agent harnesses",
        "knowledge_cutoff_date": datetime.now(UTC),
    }
    values.update(overrides)
    return ExpertProfile(**values)


def _run(
    *,
    status: str,
    accepted_changes: int = 0,
    stop_reason: str = "",
    verifier_outcome: str = "",
):
    return SimpleNamespace(
        status=status,
        accepted_changes=accepted_changes,
        stop_reason=stop_reason,
        verifier_outcome=verifier_outcome,
    )


def test_empty_expert_gets_capacity_aware_foundation_plan_without_semantic_verdict():
    manifest = ExpertManifest(expert_name="Agent Harness Expert", domain="agent harnesses")

    payload = build_expert_next_actions(_profile(knowledge_cutoff_date=None), manifest)

    assert payload["schema_version"] == EXPERT_NEXT_SCHEMA_VERSION
    assert payload["kind"] == EXPERT_NEXT_KIND
    assert payload["contract"] == {
        "read_only": True,
        "cost_usd": 0.0,
        "structural_signals_only": True,
        "semantic_maturity_verdict": False,
        "default_policy_change_allowed": False,
    }
    assert payload["stage"] == "foundation"
    assert payload["next_actions"][0]["id"] == "seed_verified_knowledge"
    command_argv = payload["next_actions"][0]["command_argv"]
    assert command_argv[0] == [
        "deepr",
        "expert",
        "subscribe",
        "Agent Harness Expert",
        "agent harnesses",
    ]
    assert command_argv[1] == [
        "deepr",
        "capacity",
        "next",
        "--task-class",
        "sync",
        "--context-mode",
        "fresh",
        "--expert",
        "Agent Harness Expert",
        "--scheduled",
    ]
    assert command_argv[2][0:4] == ["deepr", "expert", "sync", "Agent Harness Expert"]
    assert "--scheduled" in command_argv[2]


def test_failed_loop_and_stale_state_prioritize_recovery_before_gap_fill():
    profile = _profile(knowledge_cutoff_date=datetime(2020, 1, 1, tzinfo=UTC))
    manifest = ExpertManifest(
        expert_name=profile.name,
        domain=profile.domain,
        claims=[Claim.create("Trace failures into evals.", profile.domain, 0.8)],
        gaps=[Gap.create("review failure clusters", questions=["Which failures repeat?"])],
    )

    payload = build_expert_next_actions(profile, manifest, loop_runs=[_run(status="failed")])

    assert payload["stage"] == "recovery"
    assert [item["id"] for item in payload["next_actions"][:2]] == [
        "inspect_loop_blockers",
        "refresh_knowledge",
    ]
    assert payload["evidence"]["learning_loops"]["failed_count"] == 1


def test_verified_learning_run_moves_healthy_expert_to_maintenance():
    profile = _profile()
    manifest = ExpertManifest(
        expert_name=profile.name,
        domain=profile.domain,
        claims=[Claim.create("Trace failures into evals.", profile.domain, 0.8)],
    )
    run = _run(
        status="completed",
        accepted_changes=2,
        stop_reason="verifier_passed",
        verifier_outcome="passed",
    )

    payload = build_expert_next_actions(profile, manifest, loop_runs=[run])

    assert payload["stage"] == "maintenance"
    assert payload["evidence"]["learning_loops"]["verified_improvement_count"] == 1
    assert [item["id"] for item in payload["next_actions"]] == [
        "review_metacognition",
        "refresh_derived_orientation",
    ]


def test_recovered_historical_failure_does_not_keep_blocking_new_work():
    profile = _profile()
    manifest = ExpertManifest(
        expert_name=profile.name,
        domain=profile.domain,
        claims=[Claim.create("Trace failures into evals.", profile.domain, 0.8)],
    )
    latest_success = _run(
        status="completed",
        accepted_changes=1,
        stop_reason="verifier_passed",
        verifier_outcome="passed",
    )
    historical_failure = _run(status="failed")

    payload = build_expert_next_actions(profile, manifest, loop_runs=[latest_success, historical_failure])

    assert payload["stage"] == "maintenance"
    assert payload["evidence"]["learning_loops"]["failed_count"] == 1
    assert "inspect_loop_blockers" not in {item["id"] for item in payload["next_actions"]}


def test_action_limit_must_be_positive():
    with pytest.raises(ValueError, match="max_actions must be positive"):
        build_expert_next_actions(
            _profile(),
            ExpertManifest(expert_name="Agent Harness Expert", domain="agent harnesses"),
            max_actions=0,
        )


def test_machine_action_argv_preserves_names_without_shell_reparsing():
    profile = _profile(name='$(Write-Output PWN) & `whoami` "Safety"', knowledge_cutoff_date=None)
    manifest = ExpertManifest(expert_name=profile.name, domain=profile.domain)

    payload = build_expert_next_actions(profile, manifest)

    action = payload["next_actions"][0]
    assert "commands" not in action
    assert action["command_argv"][0][3] == '$(Write-Output PWN) & `whoami` "Safety"'
