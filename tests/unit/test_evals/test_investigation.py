"""Zero-cost structural evaluation coverage for investigations."""

from __future__ import annotations

from deepr.evals.investigation import COMPARISON_ARMS, run_investigation_eval


def test_investigation_eval_is_zero_io_and_explicitly_not_quality_proof() -> None:
    report = run_investigation_eval().to_dict()

    assert report["cost_usd"] == 0.0
    assert report["semantic_review_status"] == "unreviewed"
    assert report["quality_claim"] is False
    assert report["failed_cases"] == 0
    assert report["contract"] == {
        "execution_mode": "frozen_fixture",
        "provider_calls": 0,
        "network_access": False,
        "expert_store_reads": 0,
        "writes_expert_state": False,
        "writes_graph": False,
        "report_write_requires_opt_in": True,
        "semantic_verdict": False,
    }


def test_investigation_eval_freezes_six_comparison_arms_and_call_bounds() -> None:
    actual = {arm.arm_id: arm.maximum_generation_calls for arm in COMPARISON_ARMS}

    assert actual == {
        "single_expert": 4,
        "stored_packet_consult": 1,
        "independent_research": 8,
        "targeted_discussion": 11,
        "discussion_staged_learning": 17,
        "opaque_external_multi_agent": 0,
    }


def test_investigation_eval_preserves_safety_and_dissent_boundaries() -> None:
    outcomes = {item.case_id: item for item in run_investigation_eval().outcomes}

    assert outcomes["adversarial_inputs_are_inert"].detail["memory_write_authority"] is False
    assert outcomes["source_pack_learning_boundary"].detail["dialogue_is_evidence"] is False
    assert outcomes["source_pack_learning_boundary"].detail["domain_relevance_judgment"] == (
        "independent_verifier_model"
    )
    assert outcomes["source_pack_learning_boundary"].detail["deterministic_domain_relevance_verdict"] is False
    assert outcomes["source_pack_learning_boundary"].detail["domain_relevance_required_before_commit"] is True
    assert outcomes["dissent_and_minority_preserved"].detail["majority_vote_is_truth"] is False
    assert outcomes["paid_external_arm_disabled"].detail["provider_calls"] == 0
