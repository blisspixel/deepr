from __future__ import annotations

import json

from deepr.experts.investigation.protocol import (
    charter_prompt,
    checker_prompt,
    compile_check,
    compile_position,
    compile_result,
    position_prompt,
    synthesis_prompt,
)

_DEFAULT_32K_PROMPT_BYTE_LIMIT = (32_768 - 4_096) * 4


def _packet_bytes(packet) -> int:
    return len(json.dumps(packet.messages, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def test_charter_prompt_marks_model_retrieval_query_as_non_authoritative() -> None:
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
    system_prompt = packet.messages[0]["content"]
    assert "https://example.com/mcp" in user_prompt
    assert "It is not executed" in user_prompt
    assert "never receives network authority" in system_prompt


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


def test_position_preserves_testable_theory_without_promoting_it_to_fact() -> None:
    payload = compile_position(
        json.dumps(
            {
                "answer": "A theory is worth testing.",
                "claims": [],
                "perspective_candidates": [
                    {
                        "candidate_id": "theory-1",
                        "kind": "theory",
                        "title": "Selective memory can improve repeated decisions",
                        "statement": "Relevant temporal memory may reduce repeated reasoning errors.",
                        "rationale": "It can retain corrections that a stateless run loses.",
                        "uncertainty": "Retrieval errors may create negative transfer.",
                        "assumptions": ["Memory retrieval is selective."],
                        "implications": ["Evaluate downstream decision utility."],
                        "expected_observations": ["Repeated held-out decisions improve."],
                        "disconfirming_signals": ["Unrelated-task errors rise."],
                        "confidence": float("nan"),
                        "source_refs": [],
                    }
                ],
                "strongest_alternative": "Stateless execution is enough.",
                "null_hypothesis": "Memory has no effect on held-out decisions.",
                "disconfirming_test": "Compare repeated held-out tasks.",
            }
        ),
        expert_name="Fixture",
        allowed_refs=set(),
    )

    candidate = payload["perspective_candidates"][0]
    assert candidate["state_type"] == "hypothesis"
    assert candidate["declared_kind"] == "theory"
    assert candidate["truth_status"] == "not_a_factual_claim"
    assert candidate["novelty_status"] == "not_assessed"
    assert candidate["confidence"] == 0.0
    assert candidate["structurally_ready"] is True
    assert payload["claims"] == []


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


def test_checker_perspective_assessment_has_no_truth_or_novelty_authority() -> None:
    payload = compile_check(
        json.dumps(
            {
                "perspective_assessments": [
                    {
                        "expert_name": "Fixture",
                        "candidate_id": "theory-1",
                        "status": "well_formed",
                        "reason": "The proposal is testable.",
                        "suggested_test": "Run a temporal holdout.",
                    }
                ]
            }
        ),
        allowed_experts={"Fixture"},
        allowed_refs=set(),
        independence="same_local_model_reduced_independence",
        perspective_candidates={("Fixture", "theory-1")},
    )

    assessment = payload["perspective_assessments"][0]
    assert assessment["status"] == "well_formed"
    assert assessment["truth_or_novelty_verified"] is False
    assert payload["perspective_assessment_contract"]["absence_of_external_support_is_refutation"] is False


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
    assert "a draft, proposal, release candidate" in packet.messages[0]["content"]
    assert "is not a final or shipped capability" in packet.messages[0]["content"]


def test_deep_protocol_packets_fit_the_default_32k_context_budget() -> None:
    large = "context " * 20_000
    expert = {"name": "MCP", "domain": "protocol security", "snapshot": {"history": large}}
    refs = {f"E{expert_index:02d}-S{source_index}" for expert_index in range(1, 4) for source_index in range(1, 9)}
    refs.add("input-0001")

    revision = position_prompt(
        question="How should Deepr improve?",
        expert=expert,
        charter={"research_focus": large},
        input_context=large,
        source_context=large,
        allowed_refs=refs,
        operation="revision",
        prior_position={"answer": large},
        discussion={"response": large},
    )
    checker = checker_prompt(
        question="How should Deepr improve?",
        positions=[{"expert_name": name, "answer": large} for name in ("TKG", "Consciousness", "MCP")],
        source_catalog=[{"ref": ref, "title": large} for ref in sorted(refs)],
        caller_input_context=large,
        source_evidence_context=large,
        allowed_refs=refs,
        model_independence="same_local_model_reduced_independence",
    )
    synthesis = synthesis_prompt(
        question="How should Deepr improve?",
        positions=[{"expert_name": name, "answer": large} for name in ("TKG", "Consciousness", "MCP")],
        check={"overall": large},
        expected_experts=["TKG", "Consciousness", "MCP"],
        source_catalog=[{"ref": ref, "title": large} for ref in sorted(refs)],
        caller_input_context=large,
        source_evidence_context=large,
        allowed_refs=refs,
    )

    assert _packet_bytes(revision) <= _DEFAULT_32K_PROMPT_BYTE_LIMIT
    assert _packet_bytes(checker) <= _DEFAULT_32K_PROMPT_BYTE_LIMIT
    assert _packet_bytes(synthesis) <= _DEFAULT_32K_PROMPT_BYTE_LIMIT
