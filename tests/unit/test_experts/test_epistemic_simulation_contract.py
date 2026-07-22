"""Authority and replay contracts for epistemic simulations."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from deepr.experts.epistemic_simulation_context import context_content_bytes, validate_context_packet
from deepr.experts.epistemic_simulation_contract import (
    ConsultContextPacket,
    EpistemicContractError,
    EpistemicSimulation,
    canonical_sha256,
)

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "data" / "epistemic_simulation" / "acceptance-v1.json"
CONSUMER_PRINCIPAL_ID = "consumer:public-fixture"


@pytest.fixture
def fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _record(payload: dict[str, object], record_id: str) -> dict[str, object]:
    lens = payload["lens_snapshots"][0]
    return next(record for record in lens["records"] if record["record_id"] == record_id)


def test_contract_round_trip_preserves_lanes_branches_and_stable_hash(fixture_payload) -> None:
    lens = EpistemicSimulation.model_validate(fixture_payload["lens_snapshots"][0])
    first = lens.model_dump(mode="json")
    second = EpistemicSimulation.model_validate(first).model_dump(mode="json")

    assert canonical_sha256(first) == canonical_sha256(second)
    assert {record["lane"] for record in second["records"]} == {
        "factual",
        "perspective",
        "simulation",
        "episodic",
        "governance",
    }
    simulation_records = [record for record in second["records"] if record["lane"] == "simulation"]
    assert {record["branch_id"] for record in simulation_records} == {
        "branch:abundant-default-v1",
        "branch:mechanism-transfer-v1",
    }


def test_validated_contract_is_deeply_immutable_and_detached_from_input(fixture_payload) -> None:
    raw_lens = fixture_payload["lens_snapshots"][0]
    lens = EpistemicSimulation.model_validate(raw_lens)
    original_record_count = len(lens.records)

    raw_lens["records"].append(copy.deepcopy(raw_lens["records"][0]))

    assert len(lens.records) == original_record_count
    assert isinstance(lens.records, tuple)
    assert isinstance(lens.records[0].evidence_refs, tuple)
    with pytest.raises(AttributeError):
        lens.records.append(lens.records[0])
    with pytest.raises(ValidationError, match="frozen"):
        lens.records[0].evidence_refs += ("evidence:untrusted",)


def test_contract_rejects_boolean_values_at_numeric_authority_boundaries(fixture_payload) -> None:
    lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    lens["memory_policy"]["spend_ceiling_usd"] = False

    with pytest.raises(ValidationError, match="spend_ceiling_usd"):
        EpistemicSimulation.model_validate(lens)

    boolean_sequence = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    boolean_sequence["belief_revisions"][0]["sequence"] = True
    with pytest.raises(ValidationError, match="sequence"):
        EpistemicSimulation.model_validate(boolean_sequence)

    string_bound = copy.deepcopy(fixture_payload["context_packets"][0])
    string_bound["bounds"]["max_context_bytes"] = "32768"
    with pytest.raises(ValidationError, match="max_context_bytes"):
        ConsultContextPacket.model_validate(string_bound)


def test_simulation_record_cannot_lose_branch_scope(fixture_payload) -> None:
    lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    target = next(record for record in lens["records"] if record["lane"] == "simulation")
    target["branch_id"] = None

    with pytest.raises(ValidationError, match="branch_id"):
        EpistemicSimulation.model_validate(lens)


def test_record_types_cannot_cross_authority_lanes(fixture_payload) -> None:
    lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    fact = _record({"lens_snapshots": [lens]}, "record:current-fact")
    fact["record_type"] = "assumption"

    with pytest.raises(ValidationError, match="incompatible with the factual authority lane"):
        EpistemicSimulation.model_validate(lens)

    unscoped_counterfactual = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    hypothesis = _record({"lens_snapshots": [unscoped_counterfactual]}, "record:perspective-hypothesis")
    hypothesis.update(
        {
            "record_type": "counterfactual_implication",
            "branch_id": None,
            "scenario_time": None,
            "assumption_refs": [],
        }
    )
    with pytest.raises(ValidationError, match="incompatible with the perspective authority lane"):
        EpistemicSimulation.model_validate(unscoped_counterfactual)


def test_artifact_identifier_namespaces_are_disjoint(fixture_payload) -> None:
    lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    colliding_evidence = copy.deepcopy(lens["evidence_units"][0])
    colliding_evidence.update(
        {
            "evidence_id": "record:current-fact",
            "claim_refs": ["record:current-fact"],
            "edge_refs": [],
            "revision_refs": [],
        }
    )
    lens["evidence_units"].append(colliding_evidence)
    fact = _record({"lens_snapshots": [lens]}, "record:current-fact")
    fact["evidence_refs"].append("record:current-fact")

    with pytest.raises(ValidationError, match="collides across record and evidence namespaces"):
        EpistemicSimulation.model_validate(lens)


def test_simulation_cannot_support_or_write_factual_state(fixture_payload) -> None:
    lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    lens["edges"].append(
        {
            "edge_id": "edge:forbidden-promotion",
            "relation": "supports",
            "source_record_id": "record:simulated-implication",
            "target_record_id": "record:current-fact",
            "branch_id": None,
            "scenario_time": None,
            "provenance_refs": ["record:simulation-governance"],
        }
    )

    with pytest.raises(ValidationError, match="non-factual-to-factual"):
        EpistemicSimulation.model_validate(lens)


def test_model_proposal_cannot_become_a_factual_evidence_root(fixture_payload) -> None:
    lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    fact = _record({"lens_snapshots": [lens]}, "record:current-fact")
    fact["provenance_class"] = "model_proposed"

    with pytest.raises(ValidationError, match="factual record"):
        EpistemicSimulation.model_validate(lens)


def test_factual_state_cannot_depend_on_simulation_or_record_provenance(fixture_payload) -> None:
    assumption_leak = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    fact = _record({"lens_snapshots": [assumption_leak]}, "record:current-fact")
    fact["assumption_refs"] = ["record:branch-assumption"]
    with pytest.raises(ValidationError, match="factual record cannot depend"):
        EpistemicSimulation.model_validate(assumption_leak)

    record_provenance = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    record_provenance["edges"].append(
        {
            "edge_id": "edge:factual-record-provenance",
            "relation": "supports",
            "source_record_id": "record:current-fact",
            "target_record_id": "record:invalidated-fact",
            "branch_id": None,
            "scenario_time": None,
            "provenance_refs": ["record:current-fact"],
        }
    )
    with pytest.raises(ValidationError, match="evidence-unit provenance"):
        EpistemicSimulation.model_validate(record_provenance)

    unrelated_evidence = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    public = next(
        evidence
        for evidence in unrelated_evidence["evidence_units"]
        if evidence["evidence_id"] == "evidence:public-observation"
    )
    public["edge_refs"].append("edge:unrelated-factual-support")
    unrelated_evidence["edges"].append(
        {
            "edge_id": "edge:unrelated-factual-support",
            "relation": "supports",
            "source_record_id": "record:current-fact",
            "target_record_id": "record:private-fact",
            "branch_id": None,
            "scenario_time": None,
            "provenance_refs": ["evidence:public-observation"],
        }
    )
    with pytest.raises(ValidationError, match="bind both endpoint records"):
        EpistemicSimulation.model_validate(unrelated_evidence)


def test_edge_evidence_and_method_provenance_are_resolved(fixture_payload) -> None:
    missing_edge_backlink = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    outcome = next(
        evidence
        for evidence in missing_edge_backlink["evidence_units"]
        if evidence["evidence_id"] == "evidence:outcome-observation"
    )
    outcome["edge_refs"].remove("edge:fact-inspired-hypothesis")
    with pytest.raises(ValidationError, match="reciprocal evidence edge_refs"):
        EpistemicSimulation.model_validate(missing_edge_backlink)

    unknown_method_source = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    unknown_method_source["method_pack"]["attributed_to_historical_subject"] = True
    unknown_method_source["method_pack"]["provenance_refs"] = ["evidence:missing"]
    with pytest.raises(ValidationError, match="frozen evidence units"):
        EpistemicSimulation.model_validate(unknown_method_source)

    record_revision_method_source = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    record_revision_method_source["belief_revisions"][0]["update_method_provenance_refs"] = [
        "record:simulation-governance"
    ]
    with pytest.raises(ValidationError, match="must reference evidence units"):
        EpistemicSimulation.model_validate(record_revision_method_source)


def test_evidence_and_supersession_links_are_reciprocal(fixture_payload) -> None:
    missing_claim_provenance = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    fact = _record({"lens_snapshots": [missing_claim_provenance]}, "record:current-fact")
    fact["evidence_refs"] = ["evidence:public-observation"]
    with pytest.raises(ValidationError, match="reciprocal claim provenance"):
        EpistemicSimulation.model_validate(missing_claim_provenance)

    unknown_replacement = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    prior = _record({"lens_snapshots": [unknown_replacement]}, "record:invalidated-fact")
    prior["superseded_by"] = "record:missing"
    with pytest.raises(ValidationError, match="unknown superseded_by"):
        EpistemicSimulation.model_validate(unknown_replacement)

    cyclic_assumption = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    assumption = _record({"lens_snapshots": [cyclic_assumption]}, "record:branch-assumption")
    assumption["assumption_refs"] = [assumption["record_id"]]
    with pytest.raises(ValidationError, match="cannot reference their own record"):
        EpistemicSimulation.model_validate(cyclic_assumption)

    multi_record_cycle = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    assumption = _record({"lens_snapshots": [multi_record_cycle]}, "record:branch-assumption")
    dependent = copy.deepcopy(assumption)
    dependent.update(
        {
            "record_id": "record:cyclic-dependent-assumption",
            "statement": "A second assumption closes a prohibited dependency cycle.",
            "branch_condition": None,
            "assumption_refs": [assumption["record_id"]],
        }
    )
    assumption["assumption_refs"] = [dependent["record_id"]]
    multi_record_cycle["records"].append(dependent)
    multi_record_cycle["world_models"][1]["assumption_record_ids"].append(dependent["record_id"])
    with pytest.raises(ValidationError, match="must be acyclic"):
        EpistemicSimulation.model_validate(multi_record_cycle)


def test_prospective_implications_remain_candidate_only(fixture_payload) -> None:
    lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    implication = _record({"lens_snapshots": [lens]}, "record:simulated-implication")
    implication["candidate_only"] = False

    with pytest.raises(ValidationError, match="candidate_only"):
        EpistemicSimulation.model_validate(lens)

    missing_review = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    implication = _record({"lens_snapshots": [missing_review]}, "record:simulated-implication")
    implication.pop("review_after")
    with pytest.raises(ValidationError, match="review timing"):
        EpistemicSimulation.model_validate(missing_review)

    stale_review = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    implication = _record({"lens_snapshots": [stale_review]}, "record:simulated-implication")
    implication["review_after"] = "2026-07-21T09:12:00+00:00"
    with pytest.raises(ValidationError, match="review_after must follow"):
        EpistemicSimulation.model_validate(stale_review)


def test_revision_chain_requires_reciprocity_order_and_matching_supersession(fixture_payload) -> None:
    missing_trigger_backlink = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    outcome = next(
        evidence
        for evidence in missing_trigger_backlink["evidence_units"]
        if evidence["evidence_id"] == "evidence:outcome-observation"
    )
    outcome["revision_refs"] = []
    with pytest.raises(ValidationError, match="reciprocally reference"):
        EpistemicSimulation.model_validate(missing_trigger_backlink)

    false_trigger_backlink = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    public = next(
        evidence
        for evidence in false_trigger_backlink["evidence_units"]
        if evidence["evidence_id"] == "evidence:public-observation"
    )
    public["revision_refs"] = ["revision:recovery-path-v1"]
    with pytest.raises(ValidationError, match="reciprocal trigger provenance"):
        EpistemicSimulation.model_validate(false_trigger_backlink)

    mismatched_posterior = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    mismatched_posterior["belief_revisions"][0]["posterior_record_ids"] = ["record:private-fact"]
    with pytest.raises(ValidationError, match="superseded_by"):
        EpistemicSimulation.model_validate(mismatched_posterior)

    duplicate_sequence = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    second_revision = copy.deepcopy(duplicate_sequence["belief_revisions"][0])
    second_revision["revision_id"] = "revision:duplicate-sequence"
    duplicate_sequence["belief_revisions"].append(second_revision)
    with pytest.raises(ValidationError, match="sequence values"):
        EpistemicSimulation.model_validate(duplicate_sequence)

    backdated = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    backdated["belief_revisions"][0]["recorded_at"] = "2000-01-01T00:00:00+00:00"
    with pytest.raises(ValidationError, match="cannot precede"):
        EpistemicSimulation.model_validate(backdated)


def test_reviewer_acceptance_requires_linked_review_artifact(fixture_payload) -> None:
    lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    governance = _record({"lens_snapshots": [lens]}, "record:simulation-governance")
    governance["provenance_class"] = "reviewer_accepted"

    with pytest.raises(ValidationError, match="review evidence artifact"):
        EpistemicSimulation.model_validate(lens)


def test_world_model_lineage_requires_a_root_and_rejects_cycles(fixture_payload) -> None:
    lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    lens["world_models"][0]["parent_branch_id"] = "branch:mechanism-transfer-v1"

    with pytest.raises(ValidationError, match="root branch"):
        EpistemicSimulation.model_validate(lens)

    mismatched_condition = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    mismatched_condition["world_models"][1]["controlled_condition"]["value"] = "abundant"
    with pytest.raises(ValidationError, match="controlled_condition"):
        EpistemicSimulation.model_validate(mismatched_condition)

    mismatched_time = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    branch_assumption = _record({"lens_snapshots": [mismatched_time]}, "record:branch-assumption")
    branch_assumption["scenario_time"] = "T-999"
    with pytest.raises(ValidationError, match="scenario_time must match"):
        EpistemicSimulation.model_validate(mismatched_time)

    second_condition = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    branch_assumption = _record({"lens_snapshots": [second_condition]}, "record:branch-assumption")
    additional = copy.deepcopy(branch_assumption)
    additional.update(
        {
            "record_id": "record:undeclared-regulation-condition",
            "statement": "An additional regulation condition changes only this branch.",
            "branch_condition": {"variable": "regulation", "value": "restrictive"},
        }
    )
    second_condition["records"].append(additional)
    second_condition["world_models"][1]["assumption_record_ids"].append(additional["record_id"])
    with pytest.raises(ValidationError, match="exactly one structured condition"):
        EpistemicSimulation.model_validate(second_condition)

    unlisted_assumption = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    branch_assumption = _record({"lens_snapshots": [unlisted_assumption]}, "record:branch-assumption")
    hidden = copy.deepcopy(branch_assumption)
    hidden.update(
        {
            "record_id": "record:unlisted-branch-assumption",
            "statement": "This assumption is omitted from its world manifest.",
            "branch_condition": None,
        }
    )
    unlisted_assumption["records"].append(hidden)
    with pytest.raises(ValidationError, match="must exactly cover current"):
        EpistemicSimulation.model_validate(unlisted_assumption)


def test_context_packet_rejects_invalidated_memory_and_cross_branch_paths(fixture_payload) -> None:
    lens = EpistemicSimulation.model_validate(fixture_payload["lens_snapshots"][0])
    original = fixture_payload["context_packets"][0]
    context = ConsultContextPacket.model_validate(original)
    validate_context_packet(lens, context, expected_principal_id=CONSUMER_PRINCIPAL_ID)

    invalidated = copy.deepcopy(original)
    invalidated["selected_paths"][0]["record_ids"].append("record:invalidated-fact")
    invalidated["selected_paths"][0]["lane_sequence"].append("factual")
    invalidated["selected_record_ids"].append("record:invalidated-fact")
    with pytest.raises(EpistemicContractError, match="invalidated"):
        validate_context_packet(
            lens,
            ConsultContextPacket.model_validate(invalidated),
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )

    cross_branch = copy.deepcopy(original)
    cross_branch["selected_paths"][1]["branch_id"] = "branch:other"
    with pytest.raises(EpistemicContractError, match="branch"):
        validate_context_packet(
            lens,
            ConsultContextPacket.model_validate(cross_branch),
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )

    dropped_disclosure = copy.deepcopy(original)
    dropped_disclosure["simulation_disclosure"] = "Generic context"
    with pytest.raises(EpistemicContractError, match="disclosure"):
        validate_context_packet(
            lens,
            ConsultContextPacket.model_validate(dropped_disclosure),
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )


def test_context_packet_rejects_evidence_outside_consumer_access(fixture_payload) -> None:
    lens = EpistemicSimulation.model_validate(fixture_payload["lens_snapshots"][0])
    context = copy.deepcopy(fixture_payload["context_packets"][0])
    context["selected_paths"].append(
        {
            "path_id": "path:forbidden-private-record",
            "record_ids": ["record:private-fact"],
            "edge_ids": [],
            "lane_sequence": ["factual"],
            "branch_id": None,
            "scenario_time": None,
            "why_this_lens": "Exercise access-policy enforcement without rendering protected content.",
            "provenance_refs": ["evidence:private-observation"],
        }
    )
    context["selected_record_ids"].append("record:private-fact")

    with pytest.raises(EpistemicContractError, match="access policy"):
        validate_context_packet(
            lens,
            ConsultContextPacket.model_validate(context),
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )

    private_provenance = copy.deepcopy(fixture_payload["context_packets"][0])
    private_provenance["selected_paths"][0]["provenance_refs"] = ["evidence:private-observation"]
    with pytest.raises(EpistemicContractError, match="access policy"):
        validate_context_packet(
            lens,
            ConsultContextPacket.model_validate(private_provenance),
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )

    authorized = copy.deepcopy(context)
    authorized["consumer_principal_id"] = "reviewer:authorized-fixture"
    provisional = ConsultContextPacket.model_validate(authorized)
    authorized["content_bytes"] = context_content_bytes(lens, provisional)
    with pytest.raises(EpistemicContractError, match="authenticated principal"):
        validate_context_packet(
            lens,
            ConsultContextPacket.model_validate(authorized),
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )
    validate_context_packet(
        lens,
        ConsultContextPacket.model_validate(authorized),
        expected_principal_id="reviewer:authorized-fixture",
    )


def test_context_record_provenance_obeys_access_and_memory_status(fixture_payload) -> None:
    for provenance_record_id, expected_error in (
        ("record:private-fact", "access policy"),
        ("record:invalidated-fact", "invalidated"),
    ):
        raw_lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
        edge = next(item for item in raw_lens["edges"] if item["edge_id"] == "edge:implication-assumes-branch")
        edge["provenance_refs"] = [provenance_record_id]
        lens = EpistemicSimulation.model_validate(raw_lens)
        raw_context = copy.deepcopy(fixture_payload["context_packets"][0])
        branch_path = next(
            item for item in raw_context["selected_paths"] if item["path_id"] == "path:branch-implication"
        )
        branch_path["provenance_refs"] = ["record:branch-assumption", provenance_record_id]
        context = ConsultContextPacket.model_validate(raw_context)

        with pytest.raises(EpistemicContractError, match=expected_error):
            validate_context_packet(
                lens,
                context,
                expected_principal_id=CONSUMER_PRINCIPAL_ID,
            )


def test_context_access_traverses_nested_assumption_provenance(fixture_payload) -> None:
    raw_lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    branch_assumption = _record({"lens_snapshots": [raw_lens]}, "record:branch-assumption")
    middle = copy.deepcopy(branch_assumption)
    middle.update(
        {
            "record_id": "record:nested-middle-assumption",
            "statement": "A middle assumption depends on a protected terminal premise.",
            "branch_condition": None,
            "assumption_refs": ["record:nested-protected-assumption"],
        }
    )
    protected = copy.deepcopy(branch_assumption)
    protected.update(
        {
            "record_id": "record:nested-protected-assumption",
            "statement": "A protected terminal premise anchors the dependency chain.",
            "branch_condition": None,
            "evidence_refs": ["evidence:private-observation"],
            "assumption_refs": [],
        }
    )
    raw_lens["records"].extend((middle, protected))
    raw_lens["world_models"][1]["assumption_record_ids"].extend((middle["record_id"], protected["record_id"]))
    implication = _record({"lens_snapshots": [raw_lens]}, "record:simulated-implication")
    implication["assumption_refs"] = [middle["record_id"]]
    private_evidence = next(
        evidence for evidence in raw_lens["evidence_units"] if evidence["evidence_id"] == "evidence:private-observation"
    )
    private_evidence["claim_refs"].append(protected["record_id"])
    lens = EpistemicSimulation.model_validate(raw_lens)

    raw_context = copy.deepcopy(fixture_payload["context_packets"][0])
    raw_context["selected_paths"] = [
        {
            "path_id": "path:nested-protected-assumption",
            "record_ids": ["record:simulated-implication"],
            "edge_ids": [],
            "lane_sequence": ["simulation"],
            "branch_id": "branch:mechanism-transfer-v1",
            "scenario_time": "T+1",
            "why_this_lens": "Exercise transitive access checks over assumption provenance.",
            "provenance_refs": [
                middle["record_id"],
                protected["record_id"],
                "evidence:private-observation",
            ],
        }
    ]
    raw_context["selected_record_ids"] = ["record:simulated-implication"]
    raw_context["selected_edge_ids"] = []
    context = ConsultContextPacket.model_validate(raw_context)

    with pytest.raises(EpistemicContractError, match="access policy"):
        validate_context_packet(
            lens,
            context,
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )


def test_context_requires_canonical_byte_count_and_connected_paths(fixture_payload) -> None:
    lens = EpistemicSimulation.model_validate(fixture_payload["lens_snapshots"][0])
    wrong_size = copy.deepcopy(fixture_payload["context_packets"][0])
    wrong_size["content_bytes"] += 1
    with pytest.raises(EpistemicContractError, match="content_bytes"):
        validate_context_packet(
            lens,
            ConsultContextPacket.model_validate(wrong_size),
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )

    disconnected = copy.deepcopy(fixture_payload["context_packets"][1])
    disconnected["selected_paths"][0]["edge_ids"] = []
    disconnected["selected_paths"][0]["provenance_refs"] = ["record:baseline-assumption"]
    disconnected["selected_edge_ids"] = []
    with pytest.raises(EpistemicContractError, match="connected"):
        validate_context_packet(
            lens,
            ConsultContextPacket.model_validate(disconnected),
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )

    incomplete_provenance = copy.deepcopy(fixture_payload["context_packets"][0])
    incomplete_provenance["selected_paths"][0]["provenance_refs"] = ["evidence:outcome-observation"]
    with pytest.raises(EpistemicContractError, match="exactly match"):
        validate_context_packet(
            lens,
            ConsultContextPacket.model_validate(incomplete_provenance),
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )

    wrong_scenario_time = copy.deepcopy(fixture_payload["context_packets"][0])
    wrong_scenario_time["selected_paths"][0]["scenario_time"] = "T+99"
    with pytest.raises(EpistemicContractError, match="scenario_time"):
        validate_context_packet(
            lens,
            ConsultContextPacket.model_validate(wrong_scenario_time),
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )

    invented_branch = copy.deepcopy(fixture_payload["context_packets"][0])
    invented_branch["selected_paths"].append(
        {
            "path_id": "path:invented-global-branch",
            "record_ids": ["record:current-fact"],
            "edge_ids": [],
            "lane_sequence": ["factual"],
            "branch_id": "branch:ghost",
            "scenario_time": "T0",
            "why_this_lens": "Exercise branch binding for a branchless factual record.",
            "provenance_refs": ["evidence:outcome-observation"],
        }
    )
    with pytest.raises(EpistemicContractError, match="outside its packet"):
        validate_context_packet(
            lens,
            ConsultContextPacket.model_validate(invented_branch),
            expected_principal_id=CONSUMER_PRINCIPAL_ID,
        )


def test_edges_cannot_invent_world_branches(fixture_payload) -> None:
    lens = copy.deepcopy(fixture_payload["lens_snapshots"][0])
    edge = next(item for item in lens["edges"] if item["edge_id"] == "edge:fact-inspired-hypothesis")
    edge["branch_id"] = "branch:ghost"

    with pytest.raises(ValidationError, match="unknown branch"):
        EpistemicSimulation.model_validate(lens)


def test_every_context_path_retains_why_and_provenance(fixture_payload) -> None:
    lens = EpistemicSimulation.model_validate(fixture_payload["lens_snapshots"][0])
    context = ConsultContextPacket.model_validate(fixture_payload["context_packets"][0])

    assert context.simulation_disclosure == lens.disclosure.text
    assert context.disclosure_persistent is True
    assert context.constructed_simulation is True
    assert context.identity_claims_allowed is False
    assert all(path.why_this_lens.strip() for path in context.selected_paths)
    assert all(path.provenance_refs for path in context.selected_paths)
