from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from deepr.experts.investigation.inputs import compile_input_bundle
from deepr.experts.investigation.models import (
    PLAN_KIND,
    PLAN_SCHEMA_VERSION,
    InvestigationBounds,
    LearningMode,
    Phase,
    ProtocolMode,
    RunState,
    event_payload,
    sha256_json,
    validate_plan,
)
from deepr.experts.investigation.protocol import (
    compile_charter,
    compile_check,
    compile_discussion,
    compile_position,
    compile_result,
)

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "schemas"
NOW = "2026-07-17T00:00:00+00:00"


def _validate(name: str, payload: dict[str, Any]) -> None:
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_published_investigation_contracts_validate_runtime_shapes(tmp_path: Path) -> None:
    bundle = compile_input_bundle(input_root=tmp_path, inline_texts=["context"], created_at=NOW)
    snapshot = {"expert": {"name": "Fixture"}, "summary": {"claim_count": 0}}
    bounds = InvestigationBounds.for_plan(
        expert_count=1,
        protocol=ProtocolMode.INDEPENDENT,
        learning=LearningMode.OFF,
    )
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": PLAN_KIND,
        "run_id": "inv_schema_test",
        "created_at": NOW,
        "question": "Question",
        "experts": [
            {
                "name": "Fixture",
                "snapshot_sha256": sha256_json(snapshot),
                "snapshot": snapshot,
                "readiness": {},
            }
        ],
        "protocol": "independent",
        "learning": "off",
        "input_bundle": bundle,
        "capacity": {"class": "local", "model": "fixture", "fallback": "none"},
        "retrieval": {"max_queries_per_expert": 4, "max_pages_per_expert": 8},
        "bounds": bounds.to_dict(),
        "learning_contract": {
            "mode": "off",
            "source_pack_evidence_only": True,
            "dialogue_is_evidence": False,
            "domain_relevance_required": False,
            "domain_relevance_judgment": "not_applicable",
            "writes_expert_state": False,
            "writes_beliefs": False,
            "writes_graph": False,
            "human_reviewed": False,
        },
    }
    plan["plan_sha256"] = sha256_json(plan)
    validate_plan(plan)

    charter = compile_charter(
        json.dumps(
            {
                "research_focus": "Focus",
                "retrieval_query": "Query",
                "subquestions": [],
                "stop_criteria": [],
            }
        ),
        expert_name="Fixture",
        question="Question",
    )
    position = compile_position(
        json.dumps(
            {
                "answer": "Answer",
                "abstained": False,
                "claims": [
                    {
                        "claim_id": "c1",
                        "text": "Claim",
                        "basis": "caller_input",
                        "source_refs": ["input-0001"],
                        "confidence": 0.5,
                    }
                ],
            }
        ),
        expert_name="Fixture",
        allowed_refs={"input-0001"},
    )
    discussion = compile_discussion(
        json.dumps(
            {
                "selected_peer_alias": "Peer A",
                "crux": "Crux",
                "response": "Response",
                "stance": "retain",
                "source_refs": ["input-0001"],
                "new_evidence": False,
                "unresolved": [],
            }
        ),
        expert_name="Fixture",
        allowed_aliases={"Peer A"},
        allowed_refs={"input-0001"},
    )
    check = compile_check(
        json.dumps(
            {
                "assessments": [],
                "minority_evidence_preserved": True,
                "strongest_expert_diluted": False,
                "overall": "Checked",
            }
        ),
        allowed_experts={"Fixture"},
        allowed_refs={"input-0001"},
        independence="same_local_model_reduced_independence",
    )
    result = compile_result(
        json.dumps(
            {
                "answer": "Answer",
                "expert_contributions": [
                    {
                        "expert_name": "Fixture",
                        "status": "retained",
                        "contribution": "Contribution",
                        "reason": "Reason",
                        "source_refs": ["input-0001"],
                    }
                ],
                "claims": [],
                "open_gaps": [],
                "next_tests": [],
            }
        ),
        question="Question",
        allowed_refs={"input-0001"},
        expected_experts=["Fixture"],
    )
    learning = {
        "schema_version": "deepr-investigation-learning-manifest-v1",
        "kind": "deepr.expert.investigation_learning_manifest",
        "run_id": "inv_schema_test",
        "entries": [
            {
                "expert_name": "Fixture",
                "status": "no_op",
                "automatic_verifier_accepted": False,
                "human_reviewed": False,
                "writes_expert_state": False,
            }
        ],
        "summary": {
            "expert_count": 1,
            "ready_write_count": 0,
            "automatic_verifier_accepted_count": 0,
            "human_reviewed_count": 0,
            "expert_state_write_count": 0,
        },
        "contract": {
            "source_pack_evidence_only": True,
            "domain_relevance_required": True,
            "dialogue_is_evidence": False,
            "writes_expert_state": False,
            "human_reviewed": False,
            "apply_requires_explicit_command": True,
        },
        "generated_at": NOW,
    }
    event = event_payload(
        run_id="inv_schema_test",
        sequence=1,
        event_type="run_created",
        phase=Phase.PREFLIGHT,
        status=RunState.PLANNED,
    )

    for schema_name, payload in (
        ("investigation-input-bundle-v1.json", bundle),
        ("investigation-plan-v1.json", plan),
        ("investigation-charter-v1.json", charter),
        ("investigation-position-v1.json", position),
        ("investigation-discussion-v1.json", discussion),
        ("investigation-check-v1.json", check),
        ("investigation-result-v1.json", result),
        ("investigation-learning-manifest-v1.json", learning),
        ("investigation-event-v1.json", event),
    ):
        _validate(schema_name, payload)
