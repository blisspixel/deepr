from __future__ import annotations

import json

from deepr.experts.investigation.protocol import (
    charter_prompt,
    compile_check,
    compile_position,
    compile_result,
    synthesis_prompt,
)


def test_charter_prompt_treats_requested_urls_as_relevance_candidates() -> None:
    packet = charter_prompt(
        question="How should Deepr improve?",
        expert={
            "name": "Temporal Knowledge Graphs",
            "domain": "temporal knowledge graphs",
            "snapshot": {},
        },
        input_context="No caller text.",
        requested_urls=("https://example.com/mcp",),
    )

    user_prompt = packet.messages[-1]["content"]
    assert "only when it is materially relevant" in user_prompt
    assert "do not copy all requested URLs by default" in user_prompt


def test_claim_lineage_rejects_basis_reference_class_mismatch() -> None:
    payload = compile_position(
        json.dumps(
            {
                "answer": "Answer",
                "claims": [
                    {
                        "claim_id": "wrong",
                        "text": "An external claim with only a caller-input ref.",
                        "basis": "external_source",
                        "source_refs": ["input-0001"],
                        "confidence": 0.8,
                    },
                    {
                        "claim_id": "right",
                        "text": "An externally supported claim.",
                        "basis": "external_source",
                        "source_refs": ["E01-S1"],
                        "confidence": 0.8,
                    },
                ],
                "strongest_alternative": "Alternative",
                "disconfirming_test": "Test",
            }
        ),
        expert_name="Fixture",
        allowed_refs={"input-0001", "E01-S1"},
    )

    assert payload["claims"][0]["lineage_status"] == "basis_reference_class_mismatch"
    assert payload["claims"][1]["lineage_status"] == "recorded"
    assert "one_or_more_claims_missing_valid_lineage" in payload["form_warnings"]


def test_result_records_missing_expert_coverage_without_claiming_quality() -> None:
    payload = compile_result(
        json.dumps(
            {
                "answer": "Answer",
                "expert_contributions": [
                    {
                        "expert_name": "TKG",
                        "status": "retained",
                        "contribution": "Temporal provenance matters.",
                        "reason": "Supported",
                        "source_refs": ["E01-S1"],
                    }
                ],
                "claims": [],
            }
        ),
        question="Question",
        allowed_refs={"E01-S1"},
        expected_experts=["TKG", "MCP"],
    )

    assert payload["semantic_review_status"] == "unreviewed"
    assert payload["quality_claim"] is False
    assert payload["synthesis_audit"]["missing_experts"] == ["MCP"]
    assert payload["expert_contributions"][1]["status"] == "missing"
    assert "one_or_more_required_expert_contributions_missing" in payload["form_warnings"]


def test_checker_cannot_mark_unrecorded_lineage_sufficient() -> None:
    payload = compile_check(
        json.dumps(
            {
                "assessments": [
                    {
                        "expert_name": "Fixture",
                        "claim_id": "claim-1",
                        "status": "sufficient",
                        "reason": "Model says sufficient.",
                        "source_refs": ["input-0001"],
                    }
                ]
            }
        ),
        allowed_experts={"Fixture"},
        allowed_refs={"input-0001"},
        independence="same_local_model_reduced_independence",
        claim_lineage={("Fixture", "claim-1"): "basis_reference_class_mismatch"},
    )

    assert payload["assessments"][0]["status"] == "not_checked"
    assert payload["assessments"][0]["form_override"] == "lineage_not_recorded"


def test_synthesis_prompt_keeps_caller_files_in_the_caller_reference_class() -> None:
    packet = synthesis_prompt(
        question="Question",
        positions=[],
        check={},
        expected_experts=["Fixture"],
        source_catalog=[],
        caller_input_context="input-0001: supplied.md",
        source_evidence_context="",
        allowed_refs={"input-0001"},
    )

    assert "A caller-supplied file remains caller_input" in packet.messages[-1]["content"]
