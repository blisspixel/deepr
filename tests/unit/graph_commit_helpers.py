"""Unit-test fixtures for graph commit contracts."""

from __future__ import annotations

from deepr.experts.graph_commit_envelope import GRAPH_COMMIT_ENVELOPE_KIND, GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION


def graph_commit_operation(
    belief_id: str,
    claim: str,
    idempotency_key: str,
    *,
    confidence: float = 0.6,
    edges: list[dict[str, str]] | None = None,
) -> dict:
    return {
        "operation_id": f"op_{belief_id}",
        "operation": "add_belief",
        "candidate_id": f"candidate_{belief_id}",
        "decision_status": "ready_for_commit",
        "belief": {
            "id": belief_id,
            "claim": claim,
            "domain": "compiler",
            "confidence": confidence,
            "evidence_refs": [f"source_note:note_{belief_id}:w0"],
            "source_type": "compiled_source_claim",
            "trust_class": "tertiary",
            "grounding_assurance": "unverified",
        },
        "edges": edges or [],
        "idempotency_key": idempotency_key,
        "provenance": {"source_refs": [{"note_id": f"note_{belief_id}", "window_id": f"note_{belief_id}:w0"}]},
    }


def graph_commit_gap_operation(
    topic: str,
    idempotency_key: str,
    *,
    gap_id: str = "gap_test",
    candidate_id: str = "candidate_gap",
) -> dict:
    return {
        "operation_id": f"op_{gap_id}",
        "operation": "promote_gap",
        "candidate_id": candidate_id,
        "decision_status": "ready_for_commit",
        "gap": {
            "id": gap_id,
            "topic": topic,
            "questions": [topic],
            "priority": 3,
            "estimated_cost": 0.0,
            "expected_value": 0.7,
            "ev_cost_ratio": 700.0,
            "times_asked": 1,
            "identified_at": "2026-06-26T12:00:00+00:00",
            "filled": False,
            "filled_at": None,
            "filled_by_job": None,
        },
        "idempotency_key": idempotency_key,
        "provenance": {"source_refs": [{"note_id": "note_gap", "window_id": "note_gap:w0"}]},
    }


def graph_commit_agenda_operation(
    title: str,
    idempotency_key: str,
    *,
    agenda_id: str = "agenda_test",
    candidate_id: str = "candidate_agenda",
) -> dict:
    return {
        "operation_id": f"op_{agenda_id}",
        "operation": "promote_exploration_agenda",
        "candidate_id": candidate_id,
        "decision_status": "ready_for_commit",
        "agenda": {
            "id": agenda_id,
            "title": title,
            "questions": [title],
            "origin": "A verifier-approved source note raised the exploration direction.",
            "rationale": "The expert needs a durable research direction before widening state writes.",
            "uncertainty": "The best next evidence remains unresolved.",
            "priority": 4,
            "estimated_cost": 0.0,
            "expected_value": 0.8,
            "ev_cost_ratio": 800.0,
            "success_criteria": ["A follow-up source pack resolves the direction."],
            "expected_observations": ["Future source packs expose reusable acceptance criteria."],
            "disconfirming_signals": ["No repeated consults need this agenda."],
            "created_at": "2026-06-26T12:00:00+00:00",
            "status": "open",
        },
        "idempotency_key": idempotency_key,
        "provenance": {"source_refs": [{"note_id": "note_agenda", "window_id": "note_agenda:w0"}]},
    }


def graph_commit_envelope(
    *operations: dict,
    expert_name: str = "Compiler Expert",
    status: str = "ready_for_commit",
) -> dict:
    return {
        "schema_version": GRAPH_COMMIT_ENVELOPE_SCHEMA_VERSION,
        "kind": GRAPH_COMMIT_ENVELOPE_KIND,
        "contract": {
            "read_only": True,
            "derived_view": True,
            "semantic_judgment": False,
            "model_calls": False,
            "cost_usd": 0.0,
            "writes_graph": False,
            "apply_requires_explicit_command": True,
            "idempotent_operations": True,
            "breaking_changes_require_new_schema_version": True,
        },
        "input": {
            "claim_extraction_artifact": "sync_artifacts/claim_extractions/pack.json",
            "claim_extraction_schema_version": "deepr-semantic-claim-extraction-v1",
            "claim_verification_artifact": "sync_artifacts/claim_verifications/pack.json",
            "claim_verification_schema_version": "deepr-claim-verification-v1",
            "claim_verification_kind": "deepr.expert.claim_verification",
            "decision_count": len(operations),
        },
        "target": {
            "expert_name": expert_name,
            "domain": "compiler",
            "trust_class": "tertiary",
            "grounding_assurance": "unverified",
        },
        "summary": {
            "status": status,
            "ready_write_count": len(operations) if status == "ready_for_commit" else 0,
            "blocked_decision_count": 0 if status == "ready_for_commit" else len(operations),
            "failure_reasons": [],
        },
        "operations": list(operations),
        "blocked_decisions": [],
        "compiler": {
            "stage": "graph_commit_envelope",
            "previous_stage": "claim_verification",
            "previous_schema_version": "deepr-claim-verification-v1",
            "next_stage": "graph_commit_apply",
            "next_stage_requires_model_judgment": False,
            "graph_writes_require_explicit_apply": True,
        },
        "generated_at": "2026-06-26T12:00:00+00:00",
    }
