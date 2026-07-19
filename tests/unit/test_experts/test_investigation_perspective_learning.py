from __future__ import annotations

from deepr.experts.beliefs import BeliefStore
from deepr.experts.graph_commit_apply import apply_graph_commit_envelope
from deepr.experts.investigation.perspective_learning import build_perspective_graph_commit_envelope
from deepr.experts.metacognition import MetaCognitionTracker


def _position() -> dict:
    return {
        "schema_version": "deepr-investigation-position-v1",
        "expert_name": "TKG",
        "generated_at": "2026-07-16T00:00:00+00:00",
        "perspective_candidates": [
            {
                "candidate_id": "theory-1",
                "declared_kind": "theory",
                "state_type": "hypothesis",
                "title": "Selective temporal memory improves repeated decisions",
                "statement": "Relevant temporal state may reduce repeated reasoning errors.",
                "rationale": "It retains corrections across related work.",
                "uncertainty": "Poor retrieval may create negative transfer.",
                "assumptions": ["Retrieval remains selective."],
                "implications": ["Evaluate downstream decisions."],
                "expected_observations": ["Repeated held-out decisions improve."],
                "disconfirming_signals": ["Unrelated-task errors rise."],
                "priority": 4,
                "confidence": 0.61,
                "source_refs": [],
                "structurally_ready": True,
                "form_failure_reasons": [],
            }
        ],
    }


def _check(status: str = "well_formed") -> dict:
    return {
        "schema_version": "deepr-investigation-check-v1",
        "perspective_assessments": [
            {
                "expert_name": "TKG",
                "candidate_id": "theory-1",
                "status": status,
            }
        ],
    }


def test_perspective_envelope_can_apply_as_non_factual_state_without_sources(tmp_path) -> None:
    envelope = build_perspective_graph_commit_envelope(
        run_id="inv_fixture",
        expert_name="TKG",
        domain="temporal knowledge graphs",
        position=_position(),
        check=_check(),
        position_artifact="artifacts/revisions/tkg.json",
        check_artifact="artifacts/check/independent.json",
    )

    assert envelope["summary"]["status"] == "ready_for_commit"
    assert envelope["summary"]["ready_write_count"] == 1
    assert envelope["contract"]["factual_belief_writes"] is False
    assert envelope["contract"]["truth_verified"] is False
    assert envelope["contract"]["novelty_verified"] is False
    operation = envelope["operations"][0]
    assert operation["operation"] == "promote_hypothesis"
    assert operation["provenance"]["source_refs"] == []

    store = BeliefStore("TKG", storage_dir=tmp_path / "beliefs")
    tracker = MetaCognitionTracker("TKG", base_path=str(tmp_path / "experts"))
    preview = apply_graph_commit_envelope(envelope, store, gap_tracker=tracker, dry_run=True)
    assert preview["summary"]["planned_write_count"] == 1

    result = apply_graph_commit_envelope(envelope, store, gap_tracker=tracker, dry_run=False)
    assert result["summary"]["status"] == "applied"
    assert "Selective temporal memory improves repeated decisions" in tracker.hypotheses
    assert store.beliefs == {}


def test_perspective_envelope_blocks_candidate_not_assessed_well_formed() -> None:
    envelope = build_perspective_graph_commit_envelope(
        run_id="inv_fixture",
        expert_name="TKG",
        domain="temporal knowledge graphs",
        position=_position(),
        check=_check("needs_refinement"),
        position_artifact="artifacts/positions/tkg.json",
        check_artifact="artifacts/check/independent.json",
    )

    assert envelope["summary"]["status"] == "blocked"
    assert envelope["summary"]["ready_write_count"] == 0
    assert envelope["blocked_decisions"][0]["failure_reasons"] == ["perspective_not_model_assessed_well_formed"]
