"""Five-arm frozen-fixture evaluation for epistemic simulations."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from deepr.evals.epistemic_simulation import (
    COMPARISON_ARM_IDS,
    EpistemicSimulationCaseBundle,
    EpistemicSimulationEvalPayload,
    evaluate_epistemic_simulation,
    validate_epistemic_simulation_eval_payload,
)
from deepr.experts.epistemic_simulation_context import context_content_bytes
from deepr.experts.epistemic_simulation_contract import ConsultContextPacket, EpistemicSimulation

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "data" / "epistemic_simulation" / "acceptance-v1.json"


@pytest.fixture
def fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _hash_map(report: dict[str, object], field_name: str) -> dict[str, str]:
    return {entry["artifact_id"]: entry["sha256"] for entry in report[field_name]}


def test_frozen_bundle_covers_required_cases_and_exact_five_arms(fixture_payload) -> None:
    bundle = EpistemicSimulationCaseBundle.model_validate(fixture_payload)

    assert tuple(arm.arm_id for arm in bundle.comparison_arms) == COMPARISON_ARM_IDS
    assert {family for case in bundle.cases for family in case.case_families} >= {
        "stale_premise",
        "assumption_leakage",
        "invalidated_memory",
        "identity_pressure",
        "dissent",
        "access_controlled_evidence",
        "useful_unverified_hypothesis",
        "counterfactual_transfer",
    }
    assert all(tuple(case.expected_arm_ids) == COMPARISON_ARM_IDS for case in bundle.cases)
    assert all(arm.input_artifact_status == "not_supplied" for arm in bundle.comparison_arms)
    assert all(arm.execution_status == "not_executed" for arm in bundle.comparison_arms)


def test_frozen_bundle_is_deeply_immutable(fixture_payload) -> None:
    bundle = EpistemicSimulationCaseBundle.model_validate(fixture_payload)

    assert isinstance(bundle.cases, tuple)
    assert isinstance(bundle.cases[0].case_families, tuple)
    with pytest.raises(AttributeError):
        bundle.cases.append(bundle.cases[0])
    with pytest.raises(ValidationError, match="frozen"):
        bundle.cases[0].case_families += ("dissent",)


def test_evaluator_is_zero_call_read_only_and_does_not_claim_quality(fixture_payload) -> None:
    bundle = EpistemicSimulationCaseBundle.model_validate(fixture_payload)
    report = evaluate_epistemic_simulation(
        bundle,
        generated_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    ).to_dict()

    assert report["contract"] == {
        "execution_mode": "frozen_fixture",
        "consumer_principal_id": "consumer:public-fixture",
        "provider_calls": 0,
        "network_access": False,
        "expert_store_reads": 0,
        "writes_expert_state": False,
        "writes_graph": False,
        "changes_runtime_default": False,
        "semantic_verdict": False,
    }
    assert report["structural_summary"]["failed_cases"] == 0
    assert report["semantic_review_status"] == "not_supplied"
    assert report["quality_claim"] is False
    assert report["acceptance"]["status"] == "accountable_review_required"
    assert report["acceptance"]["accepted"] is False
    assert report["acceptance"]["winner"] is None
    EpistemicSimulationEvalPayload.model_validate(report)
    validate_epistemic_simulation_eval_payload(bundle, report)


def test_identical_frozen_input_produces_stable_case_and_context_hashes(fixture_payload) -> None:
    bundle = EpistemicSimulationCaseBundle.model_validate(fixture_payload)
    first = evaluate_epistemic_simulation(bundle).to_dict()
    second = evaluate_epistemic_simulation(bundle).to_dict()

    assert first["fixture_hash"] == second["fixture_hash"]
    assert first["case_hashes"] == second["case_hashes"]
    assert first["context_hashes"] == second["context_hashes"]


def test_case_hash_commits_to_linked_lens_method_and_review_contract(fixture_payload) -> None:
    baseline = EpistemicSimulationCaseBundle.model_validate(fixture_payload)
    baseline_hashes = _hash_map(evaluate_epistemic_simulation(baseline).to_dict(), "case_hashes")

    changed = copy.deepcopy(fixture_payload)
    changed["lens_snapshots"][0]["method_pack"]["operations"].append("bound an additional frozen operation")
    changed["review_contract"]["rubric_version"] = "epistemic-simulation-review-v1.1"
    changed_bundle = EpistemicSimulationCaseBundle.model_validate(changed)
    changed_hashes = _hash_map(evaluate_epistemic_simulation(changed_bundle).to_dict(), "case_hashes")

    assert baseline_hashes.keys() == changed_hashes.keys()
    assert all(baseline_hashes[case_id] != changed_hashes[case_id] for case_id in baseline_hashes)


def test_bundle_rejects_missing_arm_and_nonzero_resource_authority(fixture_payload) -> None:
    missing_arm = copy.deepcopy(fixture_payload)
    missing_arm["comparison_arms"].pop()
    with pytest.raises(ValidationError, match="comparison arms"):
        EpistemicSimulationCaseBundle.model_validate(missing_arm)

    paid = copy.deepcopy(fixture_payload)
    paid["comparison_arms"][0]["resource_contract"]["provider_calls"] = 1
    with pytest.raises(ValidationError, match="provider_calls"):
        EpistemicSimulationCaseBundle.model_validate(paid)

    boolean_call_count = copy.deepcopy(fixture_payload)
    boolean_call_count["comparison_arms"][0]["resource_contract"]["provider_calls"] = False
    with pytest.raises(ValidationError, match="provider_calls"):
        EpistemicSimulationCaseBundle.model_validate(boolean_call_count)

    boolean_lens_count = copy.deepcopy(fixture_payload)
    boolean_lens_count["comparison_arms"][0]["declared_lens_count"] = False
    with pytest.raises(ValidationError, match="declared_lens_count"):
        EpistemicSimulationCaseBundle.model_validate(boolean_lens_count)

    string_case_bound = copy.deepcopy(fixture_payload)
    string_case_bound["cases"][0]["bounds"]["max_context_bytes"] = "32768"
    with pytest.raises(ValidationError, match="max_context_bytes"):
        EpistemicSimulationCaseBundle.model_validate(string_case_bound)

    undeclared_artifact = copy.deepcopy(fixture_payload)
    undeclared_artifact["comparison_arms"][4]["input_artifact_status"] = "supplied"
    with pytest.raises(ValidationError, match="input_artifact_status"):
        EpistemicSimulationCaseBundle.model_validate(undeclared_artifact)


def test_bundle_rejects_visible_identity_and_broken_pair_lineage(fixture_payload) -> None:
    identity_visible = copy.deepcopy(fixture_payload)
    identity_visible["comparison_arms"][1]["identity_label_visible_to_reviewer"] = True
    with pytest.raises(ValidationError, match="reviewer"):
        EpistemicSimulationCaseBundle.model_validate(identity_visible)

    broken_pair = copy.deepcopy(fixture_payload)
    paired = next(case for case in broken_pair["cases"] if case["paired_case"] is not None)
    paired["paired_case"]["counterpart_case_id"] = "case:missing"
    with pytest.raises(ValidationError, match="counterpart"):
        EpistemicSimulationCaseBundle.model_validate(broken_pair)

    same_branch = copy.deepcopy(fixture_payload)
    default_case = next(case for case in same_branch["cases"] if case["case_id"] == "case:counterfactual-default-v1")
    default_case["context_id"] = "context:mechanism-transfer-v1"
    with pytest.raises(ValidationError, match="distinct frozen branch"):
        EpistemicSimulationCaseBundle.model_validate(same_branch)

    unrelated_roots = copy.deepcopy(fixture_payload)
    unrelated_roots["lens_snapshots"][0]["world_models"][1]["parent_branch_id"] = None
    with pytest.raises(ValidationError, match="direct branch fork"):
        EpistemicSimulationCaseBundle.model_validate(unrelated_roots)

    unbound_intervention = copy.deepcopy(fixture_payload)
    default_case = next(
        case for case in unbound_intervention["cases"] if case["case_id"] == "case:counterfactual-default-v1"
    )
    intervention_case = next(
        case for case in unbound_intervention["cases"] if case["case_id"] == "case:counterfactual-intervention-v1"
    )
    default_case["paired_case"].update({"intervention_variable": "unbound_color", "intervention_value": "red"})
    intervention_case["paired_case"].update({"intervention_variable": "unbound_color", "intervention_value": "blue"})
    with pytest.raises(ValidationError, match="not bound to its world model"):
        EpistemicSimulationCaseBundle.model_validate(unbound_intervention)

    changed_world = copy.deepcopy(fixture_payload)
    changed_world["lens_snapshots"][0]["world_models"][1]["time_anchor"] = "2027-01-01"
    with pytest.raises(ValidationError, match="controlled world-model state"):
        EpistemicSimulationCaseBundle.model_validate(changed_world)

    undeclared_assumption = copy.deepcopy(fixture_payload)
    raw_lens = undeclared_assumption["lens_snapshots"][0]
    branch_assumption = next(
        record for record in raw_lens["records"] if record["record_id"] == "record:branch-assumption"
    )
    additional = copy.deepcopy(branch_assumption)
    additional.update(
        {
            "record_id": "record:undeclared-branch-assumption",
            "statement": "An undeclared branch assumption changes the paired intervention.",
            "branch_condition": None,
        }
    )
    raw_lens["records"].append(additional)
    raw_lens["world_models"][1]["assumption_record_ids"].append(additional["record_id"])
    with pytest.raises(ValidationError, match="only their controlled-condition assumption"):
        EpistemicSimulationCaseBundle.model_validate(undeclared_assumption)

    changed_case_evidence = copy.deepcopy(fixture_payload)
    default_case = next(
        case for case in changed_case_evidence["cases"] if case["case_id"] == "case:counterfactual-default-v1"
    )
    default_case["shared_evidence_refs"].pop()
    with pytest.raises(ValidationError, match="controlled case input"):
        EpistemicSimulationCaseBundle.model_validate(changed_case_evidence)

    changed_question = copy.deepcopy(fixture_payload)
    default_case = next(
        case for case in changed_question["cases"] if case["case_id"] == "case:counterfactual-default-v1"
    )
    default_case["question"] = "Answer a different task."
    with pytest.raises(ValidationError, match="controlled case input"):
        EpistemicSimulationCaseBundle.model_validate(changed_question)

    changed_pair_conclusion = copy.deepcopy(fixture_payload)
    default_case = next(
        case for case in changed_pair_conclusion["cases"] if case["case_id"] == "case:counterfactual-default-v1"
    )
    default_case["paired_case"]["conclusion_should_change"] = "An unrelated conclusion should change."
    with pytest.raises(ValidationError, match="expected pair conclusion"):
        EpistemicSimulationCaseBundle.model_validate(changed_pair_conclusion)

    confounded_context = copy.deepcopy(fixture_payload)
    intervention_case = next(
        case for case in confounded_context["cases"] if case["case_id"] == "case:counterfactual-intervention-v1"
    )
    intervention_case["context_id"] = "context:mechanism-transfer-v1"
    with pytest.raises(ValidationError, match="controlled context metadata"):
        EpistemicSimulationCaseBundle.model_validate(confounded_context)

    omitted_condition = copy.deepcopy(fixture_payload)
    default_context = next(
        context
        for context in omitted_condition["context_packets"]
        if context["context_id"] == "context:abundant-default-v1"
    )
    default_context["selected_paths"][0]["record_ids"] = ["record:baseline-implication"]
    default_context["selected_paths"][0]["edge_ids"] = []
    default_context["selected_paths"][0]["lane_sequence"] = ["simulation"]
    default_context["selected_paths"][0]["scenario_time"] = "T+1"
    default_context["selected_paths"][0]["provenance_refs"] = ["record:baseline-assumption"]
    default_context["selected_record_ids"] = ["record:baseline-implication"]
    default_context["selected_edge_ids"] = []
    lens = EpistemicSimulation.model_validate(omitted_condition["lens_snapshots"][0])
    provisional = ConsultContextPacket.model_validate(default_context)
    default_context["content_bytes"] = context_content_bytes(lens, provisional)
    with pytest.raises(ValidationError, match="controlled-condition record"):
        EpistemicSimulationCaseBundle.model_validate(omitted_condition)


def test_bundle_rejects_access_snapshot_and_resource_drift(fixture_payload) -> None:
    protected_as_shared = copy.deepcopy(fixture_payload)
    case = next(item for item in protected_as_shared["cases"] if item["private_evidence_refs"])
    case["shared_evidence_refs"].append(case["private_evidence_refs"].pop())
    with pytest.raises(ValidationError, match="protected evidence"):
        EpistemicSimulationCaseBundle.model_validate(protected_as_shared)

    withheld_instead_of_access_controlled = copy.deepcopy(fixture_payload)
    private_evidence = next(
        evidence
        for evidence in withheld_instead_of_access_controlled["lens_snapshots"][0]["evidence_units"]
        if evidence["evidence_id"] == "evidence:private-observation"
    )
    private_evidence["access_policy"]["visibility"] = "withheld"
    private_evidence["access_policy"]["authorized_principal_ids"] = []
    with pytest.raises(ValidationError, match="protected-evidence witness"):
        EpistemicSimulationCaseBundle.model_validate(withheld_instead_of_access_controlled)

    changed_snapshot = copy.deepcopy(fixture_payload)
    changed_snapshot["cases"][0]["snapshots"]["compiler_version"] = "compiler:other"
    with pytest.raises(ValidationError, match="compiler snapshot"):
        EpistemicSimulationCaseBundle.model_validate(changed_snapshot)

    changed_bounds = copy.deepcopy(fixture_payload)
    changed_bounds["cases"][0]["bounds"]["max_context_bytes"] += 1
    with pytest.raises(ValidationError, match="matched resource envelope"):
        EpistemicSimulationCaseBundle.model_validate(changed_bounds)


def test_pair_rejects_temporal_and_evidence_provenance_confounds(fixture_payload) -> None:
    temporal_drift = copy.deepcopy(fixture_payload)
    intervention_record = next(
        record
        for record in temporal_drift["lens_snapshots"][0]["records"]
        if record["record_id"] == "record:simulated-implication"
    )
    intervention_record["valid_time"] = "scenario:T+999"
    lens = EpistemicSimulation.model_validate(temporal_drift["lens_snapshots"][0])
    for context in temporal_drift["context_packets"]:
        provisional = ConsultContextPacket.model_validate(context)
        context["content_bytes"] = context_content_bytes(lens, provisional)
    with pytest.raises(ValidationError, match="compiled context structure"):
        EpistemicSimulationCaseBundle.model_validate(temporal_drift)

    evidence_drift = copy.deepcopy(fixture_payload)
    raw_lens = evidence_drift["lens_snapshots"][0]
    bindings = (
        ("record:baseline-implication", "evidence:public-observation"),
        ("record:simulated-implication", "evidence:outcome-observation"),
    )
    for record_id, evidence_id in bindings:
        record = next(item for item in raw_lens["records"] if item["record_id"] == record_id)
        evidence = next(item for item in raw_lens["evidence_units"] if item["evidence_id"] == evidence_id)
        record["evidence_refs"] = [evidence_id]
        evidence["claim_refs"].append(record_id)
        for context in evidence_drift["context_packets"]:
            for path in context["selected_paths"]:
                if record_id in path["record_ids"] and evidence_id not in path["provenance_refs"]:
                    path["provenance_refs"].append(evidence_id)
    lens = EpistemicSimulation.model_validate(raw_lens)
    for context in evidence_drift["context_packets"]:
        provisional = ConsultContextPacket.model_validate(context)
        context["content_bytes"] = context_content_bytes(lens, provisional)
    with pytest.raises(ValidationError, match="compiled context structure"):
        EpistemicSimulationCaseBundle.model_validate(evidence_drift)


def test_pair_rejects_undeclared_branch_specific_inputs(fixture_payload) -> None:
    confounded = copy.deepcopy(fixture_payload)
    raw_lens = confounded["lens_snapshots"][0]
    template = next(record for record in raw_lens["records"] if record["record_id"] == "record:perspective-hypothesis")
    branches = (
        (
            "record:hidden-baseline-perspective",
            "A hidden baseline premise favors the original recovery test.",
            "branch:abundant-default-v1",
            "record:baseline-assumption",
            "context:abundant-default-v1",
        ),
        (
            "record:hidden-intervention-perspective",
            "A hidden intervention premise favors an unrelated recovery test.",
            "branch:mechanism-transfer-v1",
            "record:branch-assumption",
            "context:scarcity-intervention-v1",
        ),
    )
    for record_id, statement, branch_id, assumption_id, context_id in branches:
        hidden = copy.deepcopy(template)
        hidden.update(
            {
                "record_id": record_id,
                "statement": statement,
                "branch_id": branch_id,
                "assumption_refs": [assumption_id],
            }
        )
        raw_lens["records"].append(hidden)
        context = next(item for item in confounded["context_packets"] if item["context_id"] == context_id)
        context["selected_paths"].append(
            {
                "path_id": f"path:{record_id}",
                "record_ids": [record_id],
                "edge_ids": [],
                "lane_sequence": ["perspective"],
                "branch_id": branch_id,
                "scenario_time": "T0",
                "why_this_lens": "Hold every non-intervention record fixed across the pair.",
                "provenance_refs": [assumption_id],
            }
        )
        context["selected_record_ids"].append(record_id)
    lens = EpistemicSimulation.model_validate(raw_lens)
    for context in confounded["context_packets"]:
        if context["context_id"] not in {branch[4] for branch in branches}:
            continue
        provisional = ConsultContextPacket.model_validate(context)
        context["content_bytes"] = context_content_bytes(lens, provisional)

    with pytest.raises(ValidationError, match="compiled context structure"):
        EpistemicSimulationCaseBundle.model_validate(confounded)


def test_pair_rejects_edge_provenance_mapping_confounds(fixture_payload) -> None:
    confounded = copy.deepcopy(fixture_payload)
    raw_lens = confounded["lens_snapshots"][0]
    edge_specs = (
        (
            "context:abundant-default-v1",
            "edge:baseline-swap-1",
            "edge:baseline-swap-2",
            "record:baseline-implication",
            "record:baseline-assumption",
            "branch:abundant-default-v1",
            "evidence:public-observation",
            "evidence:outcome-observation",
        ),
        (
            "context:scarcity-intervention-v1",
            "edge:intervention-swap-1",
            "edge:intervention-swap-2",
            "record:simulated-implication",
            "record:branch-assumption",
            "branch:mechanism-transfer-v1",
            "evidence:outcome-observation",
            "evidence:public-observation",
        ),
    )
    evidence_edge_refs: dict[str, list[str]] = {}
    for context_id, first_id, second_id, source_id, target_id, branch_id, first_ref, second_ref in edge_specs:
        new_edges = (
            {
                "edge_id": first_id,
                "relation": "inspired_by",
                "source_record_id": source_id,
                "target_record_id": target_id,
                "branch_id": branch_id,
                "scenario_time": "T+1",
                "provenance_refs": [first_ref],
            },
            {
                "edge_id": second_id,
                "relation": "predicts",
                "source_record_id": source_id,
                "target_record_id": target_id,
                "branch_id": branch_id,
                "scenario_time": "T+1",
                "provenance_refs": [second_ref],
            },
        )
        raw_lens["edges"].extend(new_edges)
        evidence_edge_refs.setdefault(first_ref, []).append(first_id)
        evidence_edge_refs.setdefault(second_ref, []).append(second_id)
        context = next(item for item in confounded["context_packets"] if item["context_id"] == context_id)
        context["selected_edge_ids"].extend((first_id, second_id))
        path = context["selected_paths"][0]
        path["edge_ids"].extend((first_id, second_id))
        path["provenance_refs"].extend(("evidence:public-observation", "evidence:outcome-observation"))

    for evidence in raw_lens["evidence_units"]:
        evidence["edge_refs"].extend(evidence_edge_refs.get(evidence["evidence_id"], ()))
    lens = EpistemicSimulation.model_validate(raw_lens)
    for context_id, *_ in edge_specs:
        context = next(item for item in confounded["context_packets"] if item["context_id"] == context_id)
        provisional = ConsultContextPacket.model_validate(context)
        context["content_bytes"] = context_content_bytes(lens, provisional)

    with pytest.raises(ValidationError, match="compiled context structure"):
        EpistemicSimulationCaseBundle.model_validate(confounded)


def test_semantic_labels_cannot_be_self_certified_by_the_evaluator(fixture_payload) -> None:
    self_certified = copy.deepcopy(fixture_payload)
    self_certified["review_contract"]["semantic_labels_source"] = "evaluator_inferred"

    with pytest.raises(ValidationError, match="semantic_labels_source"):
        EpistemicSimulationCaseBundle.model_validate(self_certified)


def test_stale_memory_requires_selected_posterior_and_dissent_requires_unique_alternatives(fixture_payload) -> None:
    missing_posterior = copy.deepcopy(fixture_payload)
    stale_case = next(case for case in missing_posterior["cases"] if case["case_id"] == "case:stale-premise-v1")
    stale_case["context_id"] = "context:abundant-default-v1"
    with pytest.raises(ValidationError, match="current revision posterior"):
        EpistemicSimulationCaseBundle.model_validate(missing_posterior)

    duplicate_dissent = copy.deepcopy(fixture_payload)
    dissent_case = next(case for case in duplicate_dissent["cases"] if case["case_id"] == "case:dissent-v1")
    dissent_case["known_alternatives"] = ["One alternative", "One alternative"]
    with pytest.raises(ValidationError, match="known_alternatives must be unique"):
        EpistemicSimulationCaseBundle.model_validate(duplicate_dissent)


@pytest.mark.parametrize(
    ("case_id", "mutation", "error"),
    [
        (
            "case:stale-premise-v1",
            lambda case: case["structural_witnesses"].update({"revision_ids": []}),
            "invalidated-memory revision witness",
        ),
        (
            "case:private-evidence-v1",
            lambda case: case.update({"private_evidence_refs": []}),
            "protected-evidence witness",
        ),
        (
            "case:counterfactual-intervention-v1",
            lambda case: case["structural_witnesses"].update(
                {"record_ids": ["record:simulation-governance"], "edge_ids": []}
            ),
            "branch-assumption witness",
        ),
        (
            "case:unverified-hypothesis-v1",
            lambda case: case["structural_witnesses"].update({"record_ids": ["record:simulation-governance"]}),
            "unverified-hypothesis witness",
        ),
    ],
)
def test_case_family_labels_require_structural_witnesses(fixture_payload, case_id, mutation, error) -> None:
    changed = copy.deepcopy(fixture_payload)
    case = next(item for item in changed["cases"] if item["case_id"] == case_id)
    mutation(case)

    with pytest.raises(ValidationError, match=error):
        EpistemicSimulationCaseBundle.model_validate(changed)


def test_eval_payload_rejects_tampered_arm_hash_status_and_timestamp(fixture_payload) -> None:
    bundle = EpistemicSimulationCaseBundle.model_validate(fixture_payload)
    report = evaluate_epistemic_simulation(
        bundle,
        generated_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    ).to_dict()

    broken_arm = copy.deepcopy(report)
    broken_arm["comparison_arms"][4]["declared_lens_count"] = 2
    with pytest.raises(ValidationError, match="ablation contract"):
        EpistemicSimulationEvalPayload.model_validate(broken_arm)

    broken_case_hash = copy.deepcopy(report)
    broken_case_hash["case_results"][0]["case_hash"] = "0" * 64
    with pytest.raises(ValidationError, match="case result hash"):
        EpistemicSimulationEvalPayload.model_validate(broken_case_hash)

    broken_context_binding = copy.deepcopy(report)
    result = next(
        item for item in broken_context_binding["case_results"] if item["context_id"] == "context:abundant-default-v1"
    )
    result["context_id"] = "context:mechanism-transfer-v1"
    with pytest.raises(ValidationError, match="context hash"):
        EpistemicSimulationEvalPayload.model_validate(broken_context_binding)

    broken_status = copy.deepcopy(report)
    broken_status["case_results"][0]["semantic_review_status"] = "passed"
    with pytest.raises(ValidationError, match="semantic_review_status"):
        EpistemicSimulationEvalPayload.model_validate(broken_status)

    missing_timezone = copy.deepcopy(report)
    missing_timezone["generated_at"] = "2026-07-22T12:00:00"
    with pytest.raises(ValidationError, match="timezone"):
        EpistemicSimulationEvalPayload.model_validate(missing_timezone)

    wrong_fixture = copy.deepcopy(report)
    wrong_fixture["fixture_hash"] = "f" * 64
    with pytest.raises(ValueError, match="frozen source bundle"):
        validate_epistemic_simulation_eval_payload(bundle, wrong_fixture)
