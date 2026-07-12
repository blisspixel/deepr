"""Regressions for verified knowledge-time propagation and repair."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from click.testing import CliRunner

from deepr.cli.main import cli
from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.health_check import ExpertHealthChecker
from deepr.experts.knowledge_freshness import (
    advance_from_absorption,
    advance_knowledge_freshness,
    apply_freshness_reconciliation,
    plan_freshness_reconciliation,
)
from deepr.experts.profile import ExpertProfile, ExpertStore, get_expert_system_message


def _profile(name: str = "Freshness Repair Expert") -> ExpertProfile:
    return ExpertProfile(
        name=name,
        vector_store_id=f"local-only:{name}",
        domain="testing",
        knowledge_cutoff_date=None,
        last_knowledge_refresh=None,
        system_message=get_expert_system_message(None, "medium"),
    )


def test_advance_keeps_both_timestamps_and_derived_message_consistent() -> None:
    profile = _profile()
    observed = datetime.now(UTC) - timedelta(minutes=1)

    effective = advance_knowledge_freshness(profile, observed)

    assert effective == observed
    assert profile.knowledge_cutoff_date == observed
    assert profile.last_knowledge_refresh == observed
    assert profile.temporal_state.last_learning == observed
    assert f"- Your knowledge cutoff: {observed:%Y-%m-%d}" in profile.system_message
    assert "- Your knowledge cutoff: UNKNOWN" not in profile.system_message


def test_advance_does_not_replace_custom_system_instructions() -> None:
    profile = _profile()
    profile.system_message = "Keep this operator-authored instruction."

    advance_knowledge_freshness(profile, datetime.now(UTC))

    assert profile.system_message == "Keep this operator-authored instruction."


def test_absorption_requires_a_real_accepted_write() -> None:
    observed = datetime.now(UTC)
    rejected = _profile("Rejected Expert")
    dry_run = _profile("Dry Run Expert")
    accepted = _profile("Accepted Expert")

    assert not advance_from_absorption(
        rejected,
        SimpleNamespace(dry_run=False, absorbed=[], flagged=[], generated_at=observed),
    )
    assert not advance_from_absorption(
        dry_run,
        SimpleNamespace(dry_run=True, absorbed=[object()], flagged=[], generated_at=observed),
    )
    assert advance_from_absorption(
        accepted,
        SimpleNamespace(dry_run=False, absorbed=[], flagged=[object()], generated_at=observed),
    )
    assert rejected.knowledge_cutoff_date is None
    assert dry_run.knowledge_cutoff_date is None
    assert accepted.knowledge_cutoff_date == observed


def test_reconciliation_uses_latest_live_accepted_event(tmp_path) -> None:
    profile = _profile()
    beliefs = BeliefStore(profile.name, storage_dir=tmp_path / "beliefs")
    first, _ = beliefs.add_belief(Belief("First accepted claim", 0.8), check_conflicts=False)
    second, _ = beliefs.add_belief(Belief("Second accepted claim", 0.8), check_conflicts=False)
    beliefs.archive_belief(second.id, reason="test archive")

    plan = plan_freshness_reconciliation(profile, beliefs)

    first_event = next(event for event in beliefs.iter_events() if event.belief_id == first.id)
    assert plan.status == "repair_available"
    assert plan.belief_id == first.id
    assert plan.observed_at == first_event.timestamp
    assert apply_freshness_reconciliation(profile, plan)
    assert profile.knowledge_cutoff_date == first_event.timestamp
    assert profile.last_knowledge_refresh == first_event.timestamp


def test_reconcile_freshness_command_repairs_health_without_provider_calls() -> None:
    store = ExpertStore()
    profile = _profile()
    store.save(profile)
    beliefs = BeliefStore(profile.name)
    _stored, event = beliefs.add_belief(Belief("Verified persisted learning", 0.8), check_conflicts=False)
    assert event is not None
    expert_dir = store.find_existing_dir(profile.name)
    assert expert_dir is not None
    profile_path = expert_dir / "profile.json"
    events_path = expert_dir / "beliefs" / "events.jsonl"
    profile_before_preview = profile_path.read_bytes()
    events_before_preview = events_path.read_bytes()

    preview = CliRunner().invoke(cli, ["expert", "reconcile-freshness", profile.name, "--json"])
    before = store.load(profile.name)
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.output)["writes"] == "none"
    assert profile_path.read_bytes() == profile_before_preview
    assert events_path.read_bytes() == events_before_preview
    assert before is not None
    assert before.knowledge_cutoff_date is None

    applied = CliRunner().invoke(
        cli,
        ["expert", "reconcile-freshness", profile.name, "--apply", "-y", "--json"],
    )
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output)["applied"] is True

    repaired = store.load(profile.name)
    assert repaired is not None
    assert repaired.knowledge_cutoff_date == event.timestamp
    assert repaired.last_knowledge_refresh == event.timestamp
    assert "UNKNOWN" not in repaired.system_message
    assert repaired.get_freshness_status()["status"] == "fresh"
    freshness = next(
        finding for finding in ExpertHealthChecker(repaired).run().findings if finding.category == "freshness"
    )
    assert freshness.severity == "ok"


def test_reconcile_freshness_refuses_profiles_without_event_evidence() -> None:
    profile = _profile("No Evidence Expert")
    ExpertStore().save(profile)

    result = CliRunner().invoke(
        cli,
        ["expert", "reconcile-freshness", profile.name, "--apply", "-y", "--json"],
    )

    assert result.exit_code == 2
    assert json.loads(result.output)["status"] == "no_accepted_event_evidence"
    unchanged = ExpertStore().load(profile.name)
    assert unchanged is not None
    assert unchanged.knowledge_cutoff_date is None
