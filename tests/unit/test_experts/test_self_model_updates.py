"""Tests for verifier-gated self-model update records."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deepr.core.contracts import Claim, ExpertManifest, Gap
from deepr.experts.consult_traces import build_consult_trace
from deepr.experts.metacognitive_monitor import (
    build_consult_trace_candidates_for_expert,
    build_metacognitive_monitor_report,
)
from deepr.experts.profile import ExpertProfile
from deepr.experts.self_model_updates import (
    SELF_MODEL_UPDATE_ACCEPTANCE_KIND,
    SELF_MODEL_UPDATE_ACCEPTANCE_SCHEMA_VERSION,
    SELF_MODEL_UPDATE_CONTEXT_KIND,
    SELF_MODEL_UPDATE_KIND,
    SELF_MODEL_UPDATE_SCHEMA_VERSION,
    SelfModelUpdateError,
    accept_self_model_update_record,
    build_self_model_update_context,
    default_self_model_update_acceptance_dir,
    default_self_model_update_dir,
    propose_self_model_update,
)


def _profile(manifest: ExpertManifest) -> ExpertProfile:
    profile = ExpertProfile(
        name="Self Model Update Expert",
        vector_store_id="",
        domain="self-model updates",
        knowledge_cutoff_date=datetime(2026, 6, 26, tzinfo=UTC),
        last_knowledge_refresh=datetime(2026, 6, 26, tzinfo=UTC),
    )
    profile.get_manifest = lambda: manifest  # type: ignore[method-assign]
    return profile


def _self_model_proposal_id(profile: ExpertProfile) -> str:
    monitor = build_metacognitive_monitor_report(
        profile,
        loop_runs=[],
        consult_trace_candidates={"candidate_count": 0, "candidates": []},
    )
    return str(monitor["proposals"][0]["proposal_id"])


def test_default_self_model_update_dir_honors_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPR_DATA_DIR", str(tmp_path))

    assert default_self_model_update_dir() == tmp_path / "self_model_updates"
    assert default_self_model_update_acceptance_dir() == tmp_path / "self_model_updates" / "accepted"


def test_self_model_update_preview_does_not_write(tmp_path):
    manifest = ExpertManifest(
        expert_name="Self Model Update Expert",
        domain="self-model updates",
        gaps=[Gap.create("missing evaluator baseline", questions=["What failed?"], ev_cost_ratio=4.0)],
    )
    profile = _profile(manifest)
    profile.vector_store_id = "vs-self-model-update"
    proposal_id = _self_model_proposal_id(profile)

    payload = propose_self_model_update(
        profile,
        proposal_id,
        apply=False,
        limit=0,
        trace_path=tmp_path / "consult_traces.jsonl",
        output_dir=tmp_path / "updates",
    )

    assert payload["schema_version"] == SELF_MODEL_UPDATE_SCHEMA_VERSION
    assert payload["kind"] == SELF_MODEL_UPDATE_KIND
    assert payload["status"] == "preview"
    assert payload["applied"] is False
    assert payload["contract"]["cost_usd"] == 0.0
    assert payload["contract"]["mutates_derived_self_model"] is False
    assert payload["contract"]["writes_review_record_only"] is True
    assert payload["proposed_update"]["update_kind"] == "review_blockers_and_risks"
    assert payload["verifier"]["status"] == "passed"
    assert all(check["passed"] is True for check in payload["verifier"]["checks"])
    assert payload["actions"][0]["status"] == "preview"
    assert not (tmp_path / "updates").exists()


def test_self_model_update_apply_writes_review_record(tmp_path):
    manifest = ExpertManifest(
        expert_name="Self Model Update Expert",
        domain="self-model updates",
        gaps=[Gap.create("missing evaluator baseline", questions=["What failed?"], ev_cost_ratio=4.0)],
    )
    profile = _profile(manifest)
    proposal_id = _self_model_proposal_id(profile)

    payload = propose_self_model_update(
        profile,
        proposal_id,
        apply=True,
        limit=0,
        trace_path=tmp_path / "consult_traces.jsonl",
        output_dir=tmp_path / "updates",
    )

    path = Path(payload["artifact_path"])
    artifact = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "recorded"
    assert payload["actions"][0]["status"] == "written"
    assert artifact["schema_version"] == SELF_MODEL_UPDATE_SCHEMA_VERSION
    assert artifact["proposal_id"] == proposal_id
    assert artifact["contract"]["authority_changes_allowed"] is False
    assert artifact["actions"][0]["path"] == str(path)


def test_self_model_update_acceptance_requires_outcome_evidence(tmp_path):
    manifest = ExpertManifest(
        expert_name="Self Model Update Expert",
        domain="self-model updates",
        gaps=[Gap.create("missing evaluator baseline", questions=["What failed?"], ev_cost_ratio=4.0)],
    )
    profile = _profile(manifest)
    proposal_id = _self_model_proposal_id(profile)
    record = propose_self_model_update(
        profile,
        proposal_id,
        apply=True,
        limit=0,
        trace_path=tmp_path / "consult_traces.jsonl",
        output_dir=tmp_path / "updates",
    )

    with pytest.raises(SelfModelUpdateError, match="outcome_evidence_present"):
        accept_self_model_update_record(
            Path(record["artifact_path"]),
            expert_name=profile.name,
            outcome_evidence_refs=[],
            reviewer="operator",
            apply=True,
            output_dir=tmp_path / "accepted",
        )


def test_self_model_update_acceptance_apply_writes_record_and_context(tmp_path):
    manifest = ExpertManifest(
        expert_name="Self Model Update Expert",
        domain="self-model updates",
        gaps=[Gap.create("missing evaluator baseline", questions=["What failed?"], ev_cost_ratio=4.0)],
    )
    profile = _profile(manifest)
    proposal_id = _self_model_proposal_id(profile)
    record = propose_self_model_update(
        profile,
        proposal_id,
        apply=True,
        limit=0,
        trace_path=tmp_path / "consult_traces.jsonl",
        output_dir=tmp_path / "updates",
    )

    acceptance = accept_self_model_update_record(
        Path(record["artifact_path"]),
        expert_name=profile.name,
        outcome_evidence_refs=["loop_run:loop_123", "human_review:review_1"],
        reviewer="operator",
        apply=True,
        output_dir=tmp_path / "accepted",
    )

    path = Path(acceptance["artifact_path"])
    artifact = json.loads(path.read_text(encoding="utf-8"))
    context = build_self_model_update_context(profile.name, acceptance_dir=tmp_path / "accepted")
    assert acceptance["schema_version"] == SELF_MODEL_UPDATE_ACCEPTANCE_SCHEMA_VERSION
    assert acceptance["kind"] == SELF_MODEL_UPDATE_ACCEPTANCE_KIND
    assert acceptance["status"] == "accepted"
    assert artifact["policy_gate"]["status"] == "passed"
    assert artifact["contract"]["authority_changes_allowed"] is False
    assert context["kind"] == SELF_MODEL_UPDATE_CONTEXT_KIND
    assert context["accepted_record_count"] == 1
    assert context["accepted_records"][0]["proposal_id"] == proposal_id
    assert context["accepted_records"][0]["outcome_evidence_refs"] == ["loop_run:loop_123", "human_review:review_1"]


def test_self_model_update_acceptance_rejects_malformed_record_update(tmp_path):
    manifest = ExpertManifest(
        expert_name="Self Model Update Expert",
        domain="self-model updates",
        gaps=[Gap.create("missing evaluator baseline", questions=["What failed?"], ev_cost_ratio=4.0)],
    )
    profile = _profile(manifest)
    proposal_id = _self_model_proposal_id(profile)
    record = propose_self_model_update(
        profile,
        proposal_id,
        apply=True,
        limit=0,
        trace_path=tmp_path / "consult_traces.jsonl",
        output_dir=tmp_path / "updates",
    )
    record_path = Path(record["artifact_path"])
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    payload["proposed_update"] = {"target_path": payload["target"]}
    record_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SelfModelUpdateError, match="proposed_update_complete"):
        accept_self_model_update_record(
            record_path,
            expert_name=profile.name,
            outcome_evidence_refs=["loop_run:loop_123"],
            reviewer="operator",
            apply=True,
            output_dir=tmp_path / "accepted",
        )


def test_self_model_update_rejects_gap_eval_promotion_proposal(tmp_path):
    manifest = ExpertManifest(
        expert_name="Self Model Update Expert",
        domain="self-model updates",
        claims=[Claim.create("Consult failures should become reviewed gaps.", "self-model updates", 0.86)],
    )
    profile = _profile(manifest)
    trace = build_consult_trace(
        question="What failed in the consult?",
        requested_experts=[profile.name],
        max_experts=3,
        budget=0.0,
        failure={"error_type": "RuntimeError", "message": "synthesis failed"},
        trace_id="consult_self_model_update",
        recorded_at=datetime(2026, 6, 26, tzinfo=UTC),
    )
    trace_path = tmp_path / "consult_traces.jsonl"
    trace_path.write_text(json.dumps(trace) + "\n", encoding="utf-8")
    candidates = build_consult_trace_candidates_for_expert(profile.name, path=trace_path)
    monitor = build_metacognitive_monitor_report(profile, loop_runs=[], consult_trace_candidates=candidates)
    proposal = next(item for item in monitor["proposals"] if item["proposal_type"] == "gap_or_eval_candidate")
    proposal_id = str(proposal["proposal_id"])

    with pytest.raises(SelfModelUpdateError, match="allowed_proposal_type"):
        propose_self_model_update(
            profile,
            proposal_id,
            apply=True,
            trace_path=trace_path,
            output_dir=tmp_path / "updates",
        )


def test_self_model_update_rejects_empty_evidence_ref_value(monkeypatch, tmp_path):
    manifest = ExpertManifest(
        expert_name="Self Model Update Expert",
        domain="self-model updates",
        gaps=[Gap.create("missing evaluator baseline", questions=["What failed?"], ev_cost_ratio=4.0)],
    )
    profile = _profile(manifest)
    proposal_id = _self_model_proposal_id(profile)
    original = build_metacognitive_monitor_report(
        profile,
        loop_runs=[],
        consult_trace_candidates={"candidate_count": 0, "candidates": []},
    )
    broken = {**original, "proposals": [{**original["proposals"][0], "evidence_refs": ["self_model:"]}]}

    monkeypatch.setattr(
        "deepr.experts.self_model_updates.build_metacognitive_monitor_report",
        lambda *_, **__: broken,
    )

    with pytest.raises(SelfModelUpdateError, match="evidence_refs_structural"):
        propose_self_model_update(
            profile,
            proposal_id,
            apply=True,
            limit=0,
            trace_path=tmp_path / "consult_traces.jsonl",
            output_dir=tmp_path / "updates",
        )
