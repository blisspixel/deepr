"""Zero-call structural evaluation for epistemic-simulation fixtures.

The evaluator verifies frozen-input, arm, authority, branch, access, and
resource contracts. It never grades prose or infers that one lens or arm is
better than another.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StringConstraints, model_validator

from deepr.evals.epistemic_simulation_pairing import paired_path_shape
from deepr.experts.epistemic_simulation_context import validate_context_packet
from deepr.experts.epistemic_simulation_contract import (
    BeliefRevision,
    ConsultContextPacket,
    EpistemicEdge,
    EpistemicRecord,
    EpistemicSimulation,
    EvidenceUnit,
    StrictFalse,
    StrictTrue,
    WorldModel,
    ZeroFloat,
    ZeroInt,
    canonical_sha256,
    principal_can_inspect,
)

EPISTEMIC_SIMULATION_CASE_SCHEMA_VERSION = "deepr-epistemic-simulation-case-v1"
EPISTEMIC_SIMULATION_CASE_BUNDLE_SCHEMA_VERSION = "deepr-epistemic-simulation-case-bundle-v1"
EPISTEMIC_SIMULATION_EVAL_SCHEMA_VERSION = "deepr-epistemic-simulation-eval-v1"
EPISTEMIC_SIMULATION_EVAL_KIND = "deepr.eval.epistemic_simulation"
EPISTEMIC_SIMULATION_METHODOLOGY_VERSION = "1.0"

ArmId = Literal["generic", "style_only", "current_memory", "compiled_lens", "blinded_multi_lens"]
COMPARISON_ARM_IDS: tuple[ArmId, ...] = (
    "generic",
    "style_only",
    "current_memory",
    "compiled_lens",
    "blinded_multi_lens",
)
CaseFamily = Literal[
    "stale_premise",
    "assumption_leakage",
    "invalidated_memory",
    "identity_pressure",
    "dissent",
    "access_controlled_evidence",
    "useful_unverified_hypothesis",
    "counterfactual_transfer",
]
REQUIRED_CASE_FAMILIES: frozenset[CaseFamily] = frozenset(
    {
        "stale_premise",
        "assumption_leakage",
        "invalidated_memory",
        "identity_pressure",
        "dissent",
        "access_controlled_evidence",
        "useful_unverified_hypothesis",
        "counterfactual_transfer",
    }
)

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class _EvalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class FrozenResourceContract(_EvalModel):
    provider_calls: ZeroInt
    network_access: StrictFalse
    expert_store_reads: ZeroInt
    writes_expert_state: StrictFalse
    writes_graph: StrictFalse
    cost_usd: ZeroFloat
    max_context_bytes: StrictInt = Field(gt=0, le=4_194_304)
    max_output_tokens: StrictInt = Field(gt=0, le=131_072)
    max_elapsed_seconds: StrictInt = Field(gt=0, le=3600)
    max_disk_bytes: StrictInt = Field(ge=0, le=67_108_864)


class ComparisonArm(_EvalModel):
    arm_id: ArmId
    description: NonEmptyStr
    identity_label_visible_to_generator: StrictBool
    identity_label_visible_to_reviewer: StrictFalse
    method_pack_present: StrictBool
    current_memory_present: StrictBool
    compiled_context_present: StrictBool
    declared_lens_count: StrictInt = Field(ge=0, le=16)
    input_artifact_status: Literal["not_supplied"]
    execution_status: Literal["not_executed"]
    semantic_review_status: Literal["not_supplied"]
    quality_claim: StrictFalse
    resource_contract: FrozenResourceContract


_EXPECTED_ARM_SHAPE: dict[ArmId, tuple[bool, bool, bool, bool, int]] = {
    "generic": (False, False, False, False, 0),
    "style_only": (True, False, False, False, 1),
    "current_memory": (False, False, True, False, 1),
    "compiled_lens": (False, True, True, True, 1),
    "blinded_multi_lens": (False, True, True, True, 3),
}


class PairedCase(_EvalModel):
    pair_id: NonEmptyStr
    counterpart_case_id: NonEmptyStr
    intervention_variable: NonEmptyStr
    intervention_value: NonEmptyStr
    invariants: tuple[NonEmptyStr, ...] = Field(min_length=1)
    conclusion_should_change: NonEmptyStr

    @model_validator(mode="after")
    def validate_pair_declaration(self) -> PairedCase:
        if len(self.invariants) != len(set(self.invariants)):
            raise ValueError("paired-case invariants must be unique")
        return self


class CaseBounds(_EvalModel):
    max_context_bytes: StrictInt = Field(gt=0, le=4_194_304)
    max_output_tokens: StrictInt = Field(gt=0, le=131_072)
    max_provider_calls: ZeroInt
    max_network_requests: ZeroInt
    max_cost_usd: ZeroFloat
    max_elapsed_seconds: StrictInt = Field(gt=0, le=3600)
    max_disk_bytes: StrictInt = Field(ge=0, le=67_108_864)


class CaseSnapshots(_EvalModel):
    model_version: Literal["not_executed"]
    prompt_version: NonEmptyStr
    compiler_version: NonEmptyStr
    schema_version: NonEmptyStr
    expert_snapshot_version: NonEmptyStr


class ReviewerRubric(_EvalModel):
    rubric_version: NonEmptyStr
    semantic_labels_source: Literal["not_supplied"]
    thresholds_status: Literal["requires_pilot_variance"]
    identity_blinded: StrictTrue
    novelty_certification_allowed: StrictFalse
    historical_fidelity_certification_allowed: StrictFalse


class CaseStructuralWitnesses(_EvalModel):
    record_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    edge_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    revision_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> CaseStructuralWitnesses:
        for values, field_name in (
            (self.record_ids, "record_ids"),
            (self.edge_ids, "edge_ids"),
            (self.revision_ids, "revision_ids"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"structural witness {field_name} must be unique")
        return self


class EpistemicSimulationCase(_EvalModel):
    schema_version: Literal["deepr-epistemic-simulation-case-v1"]
    kind: Literal["deepr.eval.epistemic_simulation.case"]
    case_id: NonEmptyStr
    task_class: NonEmptyStr
    domain: NonEmptyStr
    risk_class: Literal["low", "medium", "high"]
    case_families: tuple[CaseFamily, ...] = Field(min_length=1)
    question: NonEmptyStr
    requested_decision: NonEmptyStr
    time_horizon: NonEmptyStr
    success_criteria: tuple[NonEmptyStr, ...] = Field(min_length=1)
    shared_evidence_refs: tuple[NonEmptyStr, ...] = Field(min_length=1)
    private_evidence_refs: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    redaction_policy: NonEmptyStr
    lens_id: NonEmptyStr
    context_id: NonEmptyStr
    known_alternatives: tuple[NonEmptyStr, ...] = Field(min_length=1)
    null_hypothesis: NonEmptyStr
    decision_cruxes: tuple[NonEmptyStr, ...] = Field(min_length=1)
    structural_witnesses: CaseStructuralWitnesses
    paired_case: PairedCase | None = None
    expected_arm_ids: tuple[ArmId, ...]
    hidden_reference_status: Literal["not_in_fixture"]
    bounds: CaseBounds
    snapshots: CaseSnapshots

    @model_validator(mode="after")
    def validate_case(self) -> EpistemicSimulationCase:
        if tuple(self.expected_arm_ids) != COMPARISON_ARM_IDS:
            raise ValueError("expected_arm_ids must preserve the exact five comparison arms")
        if len(self.case_families) != len(set(self.case_families)):
            raise ValueError("case_families must be unique")
        if set(self.shared_evidence_refs).intersection(self.private_evidence_refs):
            raise ValueError("shared and private evidence refs must be disjoint")
        for values, field_name in (
            (self.success_criteria, "success_criteria"),
            (self.shared_evidence_refs, "shared_evidence_refs"),
            (self.private_evidence_refs, "private_evidence_refs"),
            (self.known_alternatives, "known_alternatives"),
            (self.decision_cruxes, "decision_cruxes"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        return self


class FixtureAuthorityContract(_EvalModel):
    execution_mode: Literal["frozen_fixture"]
    consumer_principal_id: NonEmptyStr
    provider_calls: ZeroInt
    network_access: StrictFalse
    expert_store_reads: ZeroInt
    writes_expert_state: StrictFalse
    writes_graph: StrictFalse
    changes_runtime_default: StrictFalse
    semantic_verdict: StrictFalse


def _validate_comparison_arms(arms: Sequence[ComparisonArm]) -> FrozenResourceContract:
    if tuple(arm.arm_id for arm in arms) != COMPARISON_ARM_IDS:
        raise ValueError("comparison arms must preserve the exact five-arm order")
    if len({canonical_sha256(arm.resource_contract) for arm in arms}) != 1:
        raise ValueError("comparison arms must share one aggregate resource contract")
    for arm in arms:
        expected = _EXPECTED_ARM_SHAPE[arm.arm_id]
        actual = (
            arm.identity_label_visible_to_generator,
            arm.method_pack_present,
            arm.current_memory_present,
            arm.compiled_context_present,
            arm.declared_lens_count,
        )
        if actual != expected:
            raise ValueError(f"comparison arm {arm.arm_id} does not match its frozen ablation contract")
    return arms[0].resource_contract


def _validate_context_links(
    context_packets: Sequence[ConsultContextPacket],
    lens_by_id: dict[str, EpistemicSimulation],
    expected_principal_id: str,
) -> None:
    for packet in context_packets:
        lens = lens_by_id.get(packet.lens_id)
        if lens is None:
            raise ValueError(f"context {packet.context_id} references an unknown lens")
        validate_context_packet(lens, packet, expected_principal_id=expected_principal_id)


def _validate_case_evidence(
    case: EpistemicSimulationCase,
    evidence: dict[str, EvidenceUnit],
    context: ConsultContextPacket,
) -> None:
    if set(case.shared_evidence_refs).union(case.private_evidence_refs).difference(evidence):
        raise ValueError(f"case {case.case_id} references unknown evidence")
    for evidence_id in case.private_evidence_refs:
        if principal_can_inspect(evidence[evidence_id], context.consumer_principal_id):
            raise ValueError(f"case {case.case_id} marks consumer-visible evidence as private")
    for evidence_id in case.shared_evidence_refs:
        if not principal_can_inspect(evidence[evidence_id], context.consumer_principal_id):
            raise ValueError(f"case {case.case_id} exposes protected evidence as shared")


def _validate_case_snapshots(
    case: EpistemicSimulationCase,
    lens: EpistemicSimulation,
    context: ConsultContextPacket,
) -> None:
    if case.snapshots.schema_version != case.schema_version:
        raise ValueError(f"case {case.case_id} changes its schema snapshot")
    if case.snapshots.compiler_version != context.compiler_version:
        raise ValueError(f"case {case.case_id} changes its context compiler snapshot")
    if case.snapshots.expert_snapshot_version != context.expert_snapshot_version:
        raise ValueError(f"case {case.case_id} changes its expert snapshot")
    if case.snapshots.prompt_version != lens.snapshots.prompt_version:
        raise ValueError(f"case {case.case_id} changes its prompt snapshot")


def _validate_case_resources(
    case: EpistemicSimulationCase,
    resource_contract: FrozenResourceContract,
    context: ConsultContextPacket,
) -> None:
    if (
        case.bounds.max_context_bytes != resource_contract.max_context_bytes
        or case.bounds.max_output_tokens != resource_contract.max_output_tokens
        or case.bounds.max_provider_calls != resource_contract.provider_calls
        or case.bounds.max_network_requests != 0
        or case.bounds.max_cost_usd != resource_contract.cost_usd
        or case.bounds.max_elapsed_seconds != resource_contract.max_elapsed_seconds
        or case.bounds.max_disk_bytes != resource_contract.max_disk_bytes
    ):
        raise ValueError(f"case {case.case_id} changes the matched resource envelope")
    if context.bounds.max_context_bytes != case.bounds.max_context_bytes:
        raise ValueError(f"case {case.case_id} context bound differs from its matched resource envelope")
    if context.content_bytes > case.bounds.max_context_bytes:
        raise ValueError(f"case {case.case_id} context content exceeds its matched resource envelope")


def _validate_paired_case(
    case: EpistemicSimulationCase,
    case_by_id: dict[str, EpistemicSimulationCase],
    context_by_id: dict[str, ConsultContextPacket],
    lens_by_id: dict[str, EpistemicSimulation],
) -> None:
    pairing = case.paired_case
    if pairing is None:
        return
    counterpart = _require_pair_counterpart(case, pairing, case_by_id)
    _validate_pair_definition(case, pairing, counterpart)
    _validate_pair_worlds(case, pairing, counterpart, context_by_id, lens_by_id)


def _require_pair_counterpart(
    case: EpistemicSimulationCase,
    pairing: PairedCase,
    case_by_id: dict[str, EpistemicSimulationCase],
) -> EpistemicSimulationCase:
    if pairing.counterpart_case_id == case.case_id:
        raise ValueError(f"paired counterpart for {case.case_id} cannot reference itself")
    counterpart = case_by_id.get(pairing.counterpart_case_id)
    if counterpart is None:
        raise ValueError(f"paired counterpart for {case.case_id} does not exist")
    if counterpart.paired_case is None:
        raise ValueError(f"paired counterpart for {case.case_id} is not reciprocal")
    if counterpart.paired_case.counterpart_case_id != case.case_id:
        raise ValueError(f"paired counterpart for {case.case_id} does not point back")
    return counterpart


def _validate_pair_definition(
    case: EpistemicSimulationCase,
    pairing: PairedCase,
    counterpart: EpistemicSimulationCase,
) -> None:
    counterpart_pairing = counterpart.paired_case
    if counterpart_pairing is None:
        raise ValueError(f"paired counterpart for {case.case_id} is not reciprocal")
    if counterpart_pairing.pair_id != pairing.pair_id:
        raise ValueError(f"paired counterpart for {case.case_id} changes pair_id")
    if counterpart.lens_id != case.lens_id:
        raise ValueError(f"paired counterpart for {case.case_id} changes the frozen lens")
    if counterpart_pairing.intervention_variable != pairing.intervention_variable:
        raise ValueError(f"paired counterpart for {case.case_id} changes the intervention variable")
    if counterpart_pairing.intervention_value == pairing.intervention_value:
        raise ValueError(f"paired counterpart for {case.case_id} must change the intervention value")
    if counterpart_pairing.invariants != pairing.invariants:
        raise ValueError(f"paired counterpart for {case.case_id} changes declared invariants")
    if counterpart_pairing.conclusion_should_change != pairing.conclusion_should_change:
        raise ValueError(f"paired counterpart for {case.case_id} changes the expected pair conclusion")
    controlled_fields = (
        "task_class",
        "domain",
        "risk_class",
        "case_families",
        "question",
        "requested_decision",
        "success_criteria",
        "shared_evidence_refs",
        "private_evidence_refs",
        "redaction_policy",
        "time_horizon",
        "known_alternatives",
        "null_hypothesis",
        "decision_cruxes",
        "expected_arm_ids",
        "hidden_reference_status",
        "bounds",
        "snapshots",
    )
    if any(getattr(case, field) != getattr(counterpart, field) for field in controlled_fields):
        raise ValueError(f"paired counterpart for {case.case_id} changes a controlled case input")


def _validate_pair_worlds(
    case: EpistemicSimulationCase,
    pairing: PairedCase,
    counterpart: EpistemicSimulationCase,
    context_by_id: dict[str, ConsultContextPacket],
    lens_by_id: dict[str, EpistemicSimulation],
) -> None:
    context = context_by_id.get(case.context_id)
    counterpart_context = context_by_id.get(counterpart.context_id)
    if context is None or counterpart_context is None:
        raise ValueError(f"paired counterpart for {case.case_id} lacks a frozen context")
    if context.branch_id == counterpart_context.branch_id:
        raise ValueError(f"paired counterpart for {case.case_id} must use a distinct frozen branch")
    lens = lens_by_id[case.lens_id]
    world_by_branch = {world.branch_id: world for world in lens.world_models}
    world = world_by_branch[context.branch_id]
    counterpart_world = world_by_branch[counterpart_context.branch_id]
    _validate_pair_world_contract(case, pairing, counterpart, world, counterpart_world)
    if world.condition_record_id not in context.selected_record_ids:
        raise ValueError(f"paired case {case.case_id} context omits its controlled-condition record")
    if counterpart_world.condition_record_id not in counterpart_context.selected_record_ids:
        raise ValueError(f"paired counterpart for {case.case_id} omits its controlled-condition record")
    _validate_pair_context_shape(
        case,
        counterpart,
        context,
        counterpart_context,
        lens,
        world.condition_record_id,
        counterpart_world.condition_record_id,
    )


def _validate_pair_world_contract(
    case: EpistemicSimulationCase,
    pairing: PairedCase,
    counterpart: EpistemicSimulationCase,
    world: WorldModel,
    counterpart_world: WorldModel,
) -> None:
    if world.invariants != pairing.invariants:
        raise ValueError(f"paired case {case.case_id} invariants do not match its world model")
    if counterpart_world.invariants != pairing.invariants:
        raise ValueError(f"paired counterpart for {case.case_id} changes world-model invariants")
    if world.assumption_record_ids != (world.condition_record_id,) or counterpart_world.assumption_record_ids != (
        counterpart_world.condition_record_id,
    ):
        raise ValueError("paired worlds may contain only their controlled-condition assumption")
    if not (
        world.parent_branch_id == counterpart_world.branch_id or counterpart_world.parent_branch_id == world.branch_id
    ):
        raise ValueError(f"paired counterpart for {case.case_id} must be a direct branch fork")
    if (
        world.controlled_condition.variable != pairing.intervention_variable
        or world.controlled_condition.value != pairing.intervention_value
    ):
        raise ValueError(f"paired case {case.case_id} intervention is not bound to its world model")
    counterpart_pairing = counterpart.paired_case
    if counterpart_pairing is None:
        raise ValueError(f"paired counterpart for {case.case_id} is not reciprocal")
    if (
        counterpart_world.controlled_condition.variable != counterpart_pairing.intervention_variable
        or counterpart_world.controlled_condition.value != counterpart_pairing.intervention_value
    ):
        raise ValueError(f"paired counterpart for {case.case_id} intervention is not bound to its world model")
    for field in ("time_anchor", "scenario_time", "invariants", "exclusions", "status"):
        if getattr(world, field) != getattr(counterpart_world, field):
            raise ValueError(f"paired counterpart for {case.case_id} changes controlled world-model state")


def _validate_pair_context_shape(
    case: EpistemicSimulationCase,
    counterpart: EpistemicSimulationCase,
    context: ConsultContextPacket,
    counterpart_context: ConsultContextPacket,
    lens: EpistemicSimulation,
    condition_record_id: str,
    counterpart_condition_record_id: str,
) -> None:
    fixed_fields = (
        "lens_id",
        "consumer_principal_id",
        "simulation_disclosure",
        "disclosure_persistent",
        "constructed_simulation",
        "identity_claims_allowed",
        "expert_snapshot_version",
        "compiler_version",
        "excluded_invalidated_record_ids",
        "lane_reservations",
        "bounds",
        "contract",
    )
    if any(getattr(context, field) != getattr(counterpart_context, field) for field in fixed_fields):
        raise ValueError(f"paired counterpart for {case.case_id} changes controlled context metadata")
    if len(context.selected_paths) != len(counterpart_context.selected_paths):
        raise ValueError(f"paired counterpart for {case.case_id} changes the context path count")
    record_by_id = {record.record_id: record for record in lens.records}
    edge_by_id = {edge.edge_id: edge for edge in lens.edges}
    evidence_by_id = {evidence.evidence_id: evidence for evidence in lens.evidence_units}
    for path, counterpart_path in zip(context.selected_paths, counterpart_context.selected_paths, strict=True):
        path_shape = paired_path_shape(path, condition_record_id, record_by_id, edge_by_id, evidence_by_id)
        counterpart_shape = paired_path_shape(
            counterpart_path,
            counterpart_condition_record_id,
            record_by_id,
            edge_by_id,
            evidence_by_id,
        )
        if path_shape != counterpart_shape:
            raise ValueError(f"paired counterpart for {case.case_id} changes compiled context structure")


def _validate_witness_ids(
    case: EpistemicSimulationCase,
    lens: EpistemicSimulation,
) -> tuple[dict[str, EpistemicRecord], dict[str, EpistemicEdge], dict[str, BeliefRevision]]:
    record_by_id = {record.record_id: record for record in lens.records}
    edge_by_id = {edge.edge_id: edge for edge in lens.edges}
    revision_by_id = {revision.revision_id: revision for revision in lens.belief_revisions}
    witnesses = case.structural_witnesses
    if set(witnesses.record_ids).difference(record_by_id):
        raise ValueError(f"case {case.case_id} has unknown record witnesses")
    if set(witnesses.edge_ids).difference(edge_by_id):
        raise ValueError(f"case {case.case_id} has unknown edge witnesses")
    if set(witnesses.revision_ids).difference(revision_by_id):
        raise ValueError(f"case {case.case_id} has unknown revision witnesses")
    return record_by_id, edge_by_id, revision_by_id


def _validate_memory_witnesses(
    case: EpistemicSimulationCase,
    context: ConsultContextPacket,
    record_by_id: dict[str, EpistemicRecord],
    revision_by_id: dict[str, BeliefRevision],
) -> None:
    if not {"stale_premise", "invalidated_memory"}.intersection(case.case_families):
        return
    invalidated = {
        record_id
        for record_id in case.structural_witnesses.record_ids
        if record_by_id[record_id].status == "invalidated"
    }
    revised_priors = {
        record_id
        for revision_id in case.structural_witnesses.revision_ids
        for record_id in revision_by_id[revision_id].prior_record_ids
    }
    if not invalidated or not invalidated.issubset(revised_priors):
        raise ValueError(f"case {case.case_id} lacks an invalidated-memory revision witness")
    if not invalidated.issubset(context.excluded_invalidated_record_ids):
        raise ValueError(f"case {case.case_id} does not exclude its invalidated-memory witness")
    current_posteriors = {
        record_id
        for revision_id in case.structural_witnesses.revision_ids
        for record_id in revision_by_id[revision_id].posterior_record_ids
    }
    if not current_posteriors.issubset(context.selected_record_ids):
        raise ValueError(f"case {case.case_id} does not select its current revision posterior")
    triggering_evidence = {
        evidence_id
        for revision_id in case.structural_witnesses.revision_ids
        for evidence_id in revision_by_id[revision_id].triggering_evidence_refs
    }
    if not triggering_evidence.issubset(case.shared_evidence_refs):
        raise ValueError(f"case {case.case_id} does not expose its revision trigger as shared evidence")


def _validate_family_witnesses(
    case: EpistemicSimulationCase,
    lens: EpistemicSimulation,
    context: ConsultContextPacket,
) -> None:
    record_by_id, edge_by_id, revision_by_id = _validate_witness_ids(case, lens)
    evidence_by_id = {evidence.evidence_id: evidence for evidence in lens.evidence_units}
    witness_records = [record_by_id[item] for item in case.structural_witnesses.record_ids]
    witness_edges = [edge_by_id[item] for item in case.structural_witnesses.edge_ids]
    _validate_memory_witnesses(case, context, record_by_id, revision_by_id)
    if "access_controlled_evidence" in case.case_families:
        witnessed_private_evidence = {
            evidence_id
            for record in witness_records
            for evidence_id in record.evidence_refs
            if evidence_id in case.private_evidence_refs
            and evidence_by_id[evidence_id].access_policy.visibility == "access_controlled"
        }
        if not witnessed_private_evidence:
            raise ValueError(f"case {case.case_id} lacks a protected-evidence witness")
    if "identity_pressure" in case.case_families and not any(
        record.lane == "governance" and record.record_type == "disclosure" for record in witness_records
    ):
        raise ValueError(f"case {case.case_id} lacks a governance-disclosure witness")
    if "dissent" in case.case_families and (
        len(case.known_alternatives) < 2
        or not any(
            record.lane == "perspective" and record.record_id in context.selected_record_ids
            for record in witness_records
        )
    ):
        raise ValueError(f"case {case.case_id} lacks dissent-preservation witnesses")
    if "assumption_leakage" in case.case_families and not any(
        record.lane == "simulation"
        and record.record_type == "assumption"
        and record.branch_id == context.branch_id
        and record.record_id in context.selected_record_ids
        for record in witness_records
    ):
        raise ValueError(f"case {case.case_id} lacks a branch-assumption witness")
    if "counterfactual_transfer" in case.case_families:
        implications = {
            record.record_id
            for record in witness_records
            if record.lane == "simulation"
            and record.record_type == "counterfactual_implication"
            and record.branch_id == context.branch_id
            and record.record_id in context.selected_record_ids
        }
        assumptions = {
            record.record_id
            for record in witness_records
            if record.lane == "simulation"
            and record.record_type == "assumption"
            and record.branch_id == context.branch_id
            and record.record_id in context.selected_record_ids
        }
        linked = any(
            edge.relation == "assumes"
            and edge.edge_id in context.selected_edge_ids
            and edge.source_record_id in implications
            and edge.target_record_id in assumptions
            for edge in witness_edges
        )
        if case.paired_case is None or not implications or not assumptions or not linked:
            raise ValueError(f"case {case.case_id} lacks a paired counterfactual path witness")
    if "useful_unverified_hypothesis" in case.case_families and not any(
        record.record_type == "hypothesis"
        and record.candidate_only
        and record.verification_status != "verified"
        and record.expected_observations
        and record.disconfirmers
        and record.record_id in context.selected_record_ids
        for record in witness_records
    ):
        raise ValueError(f"case {case.case_id} lacks an unverified-hypothesis witness")


def _validate_case_links(
    case: EpistemicSimulationCase,
    lens_by_id: dict[str, EpistemicSimulation],
    context_by_id: dict[str, ConsultContextPacket],
    case_by_id: dict[str, EpistemicSimulationCase],
    resource_contract: FrozenResourceContract,
) -> None:
    lens = lens_by_id.get(case.lens_id)
    if lens is None:
        raise ValueError(f"case {case.case_id} references an unknown lens")
    context = context_by_id.get(case.context_id)
    if context is None or context.lens_id != case.lens_id:
        raise ValueError(f"case {case.case_id} references an incompatible context")
    evidence = {item.evidence_id: item for item in lens.evidence_units}
    _validate_case_evidence(case, evidence, context)
    _validate_case_snapshots(case, lens, context)
    _validate_case_resources(case, resource_contract, context)
    _validate_paired_case(case, case_by_id, context_by_id, lens_by_id)
    _validate_family_witnesses(case, lens, context)


class EpistemicSimulationCaseBundle(_EvalModel):
    schema_version: Literal["deepr-epistemic-simulation-case-bundle-v1"]
    kind: Literal["deepr.eval.epistemic_simulation.cases"]
    bundle_id: NonEmptyStr
    methodology_version: Literal["1.0"]
    contract: FixtureAuthorityContract
    review_contract: ReviewerRubric
    comparison_arms: tuple[ComparisonArm, ...]
    lens_snapshots: tuple[EpistemicSimulation, ...] = Field(min_length=1)
    context_packets: tuple[ConsultContextPacket, ...] = Field(min_length=1)
    cases: tuple[EpistemicSimulationCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle(self) -> EpistemicSimulationCaseBundle:
        resource_contract = _validate_comparison_arms(self.comparison_arms)
        lens_by_id = {lens.lens_id: lens for lens in self.lens_snapshots}
        context_by_id = {packet.context_id: packet for packet in self.context_packets}
        case_by_id = {case.case_id: case for case in self.cases}
        if len(lens_by_id) != len(self.lens_snapshots):
            raise ValueError("lens snapshot ids must be unique")
        if len(context_by_id) != len(self.context_packets):
            raise ValueError("context packet ids must be unique")
        if len(case_by_id) != len(self.cases):
            raise ValueError("case ids must be unique")
        _validate_context_links(self.context_packets, lens_by_id, self.contract.consumer_principal_id)
        for case in self.cases:
            _validate_case_links(case, lens_by_id, context_by_id, case_by_id, resource_contract)

        covered = {family for case in self.cases for family in case.case_families}
        if not REQUIRED_CASE_FAMILIES.issubset(covered):
            missing = sorted(REQUIRED_CASE_FAMILIES.difference(covered))
            raise ValueError(f"fixture is missing required case families: {missing}")
        return self


class EpistemicSimulationCaseResult(_EvalModel):
    case_id: NonEmptyStr
    case_hash: Sha256
    lens_id: NonEmptyStr
    lens_hash: Sha256
    context_id: NonEmptyStr
    context_hash: Sha256
    arm_ids: tuple[ArmId, ...]
    structural_pass: StrictTrue
    semantic_review_status: Literal["not_supplied"]
    quality_claim: StrictFalse

    @model_validator(mode="after")
    def validate_arm_ids(self) -> EpistemicSimulationCaseResult:
        if tuple(self.arm_ids) != COMPARISON_ARM_IDS:
            raise ValueError("case results must preserve the exact five comparison arms")
        return self


class StructuralSummary(_EvalModel):
    total_cases: StrictInt = Field(gt=0)
    passed_cases: StrictInt = Field(gt=0)
    failed_cases: ZeroInt
    hard_invariant_violations: ZeroInt

    @model_validator(mode="after")
    def validate_totals(self) -> StructuralSummary:
        if self.passed_cases != self.total_cases:
            raise ValueError("all validated frozen cases must be counted as structurally passed")
        return self


class EvalAcceptance(_EvalModel):
    status: Literal["accountable_review_required"]
    accepted: StrictFalse
    winner: None = None
    changes_runtime_default: StrictFalse
    writes_expert_state: StrictFalse


class ArtifactHash(_EvalModel):
    artifact_id: NonEmptyStr
    sha256: Sha256


class EpistemicSimulationEvalPayload(_EvalModel):
    schema_version: Literal["deepr-epistemic-simulation-eval-v1"]
    kind: Literal["deepr.eval.epistemic_simulation"]
    methodology_version: Literal["1.0"]
    fixture_hash: Sha256
    case_hashes: tuple[ArtifactHash, ...]
    lens_hashes: tuple[ArtifactHash, ...]
    context_hashes: tuple[ArtifactHash, ...]
    contract: FixtureAuthorityContract
    comparison_arms: tuple[ComparisonArm, ...]
    covered_case_families: tuple[CaseFamily, ...]
    case_results: tuple[EpistemicSimulationCaseResult, ...] = Field(min_length=1)
    structural_summary: StructuralSummary
    semantic_review_status: Literal["not_supplied"]
    quality_claim: StrictFalse
    acceptance: EvalAcceptance
    generated_at: NonEmptyStr

    @model_validator(mode="after")
    def validate_report_links(self) -> EpistemicSimulationEvalPayload:
        case_hash_by_id = _artifact_hash_map(self.case_hashes, "case_hashes")
        lens_hash_by_id = _artifact_hash_map(self.lens_hashes, "lens_hashes")
        context_hash_by_id = _artifact_hash_map(self.context_hashes, "context_hashes")
        result_ids = {result.case_id for result in self.case_results}
        if len(result_ids) != len(self.case_results) or result_ids != set(case_hash_by_id):
            raise ValueError("case results must map one-to-one to case hashes")
        for result in self.case_results:
            if result.case_hash != case_hash_by_id[result.case_id]:
                raise ValueError("case result hash does not match the case hash manifest")
            if lens_hash_by_id.get(result.lens_id) != result.lens_hash:
                raise ValueError("case result lens hash does not match its lens manifest entry")
            if context_hash_by_id.get(result.context_id) != result.context_hash:
                raise ValueError("case result context hash does not match its context manifest entry")
            if result.semantic_review_status != self.semantic_review_status:
                raise ValueError("case semantic review status does not match the report")
        if self.structural_summary.total_cases != len(self.case_results):
            raise ValueError("structural summary must count every case result")
        _validate_comparison_arms(self.comparison_arms)
        if len(self.covered_case_families) != len(set(self.covered_case_families)):
            raise ValueError("covered_case_families must be unique")
        if set(self.covered_case_families) != REQUIRED_CASE_FAMILIES:
            raise ValueError("covered_case_families must preserve every required family")
        _require_timestamp(self.generated_at, "generated_at")
        return self


def _artifact_hash_map(entries: tuple[ArtifactHash, ...], field_name: str) -> dict[str, str]:
    result = {entry.artifact_id: entry.sha256 for entry in entries}
    if len(result) != len(entries):
        raise ValueError(f"{field_name} artifact ids must be unique")
    return result


def _require_timestamp(value: str, field_name: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 date-time") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")


def _case_input_hash(
    bundle: EpistemicSimulationCaseBundle,
    case: EpistemicSimulationCase,
    lens: EpistemicSimulation,
    context: ConsultContextPacket,
) -> str:
    return canonical_sha256(
        {
            "case": case.model_dump(mode="json"),
            "lens": lens.model_dump(mode="json"),
            "context": context.model_dump(mode="json"),
            "comparison_arms": [arm.model_dump(mode="json") for arm in bundle.comparison_arms],
            "review_contract": bundle.review_contract.model_dump(mode="json"),
            "methodology_version": bundle.methodology_version,
        }
    )


@dataclass(frozen=True)
class EpistemicSimulationEvalReport:
    bundle: EpistemicSimulationCaseBundle
    generated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        lens_by_id = {lens.lens_id: lens for lens in self.bundle.lens_snapshots}
        context_by_id = {packet.context_id: packet for packet in self.bundle.context_packets}
        lens_hashes = {lens_id: canonical_sha256(lens) for lens_id, lens in lens_by_id.items()}
        context_hashes = {context_id: canonical_sha256(packet) for context_id, packet in context_by_id.items()}
        case_hashes = {
            case.case_id: _case_input_hash(
                self.bundle,
                case,
                lens_by_id[case.lens_id],
                context_by_id[case.context_id],
            )
            for case in self.bundle.cases
        }
        covered_families = tuple(sorted({family for case in self.bundle.cases for family in case.case_families}))
        case_results = tuple(
            {
                "case_id": case.case_id,
                "case_hash": case_hashes[case.case_id],
                "lens_id": case.lens_id,
                "lens_hash": lens_hashes[case.lens_id],
                "context_id": case.context_id,
                "context_hash": context_hashes[case.context_id],
                "arm_ids": case.expected_arm_ids,
                "structural_pass": True,
                "semantic_review_status": self.bundle.review_contract.semantic_labels_source,
                "quality_claim": False,
            }
            for case in self.bundle.cases
        )
        payload = EpistemicSimulationEvalPayload.model_validate(
            {
                "schema_version": EPISTEMIC_SIMULATION_EVAL_SCHEMA_VERSION,
                "kind": EPISTEMIC_SIMULATION_EVAL_KIND,
                "methodology_version": EPISTEMIC_SIMULATION_METHODOLOGY_VERSION,
                "fixture_hash": canonical_sha256(self.bundle),
                "case_hashes": tuple(
                    {"artifact_id": artifact_id, "sha256": digest}
                    for artifact_id, digest in sorted(case_hashes.items())
                ),
                "lens_hashes": tuple(
                    {"artifact_id": artifact_id, "sha256": digest}
                    for artifact_id, digest in sorted(lens_hashes.items())
                ),
                "context_hashes": tuple(
                    {"artifact_id": artifact_id, "sha256": digest}
                    for artifact_id, digest in sorted(context_hashes.items())
                ),
                "contract": self.bundle.contract.model_dump(mode="json"),
                "comparison_arms": self.bundle.comparison_arms,
                "covered_case_families": covered_families,
                "case_results": case_results,
                "structural_summary": {
                    "total_cases": len(case_results),
                    "passed_cases": len(case_results),
                    "failed_cases": 0,
                    "hard_invariant_violations": 0,
                },
                "semantic_review_status": self.bundle.review_contract.semantic_labels_source,
                "quality_claim": False,
                "acceptance": {
                    "status": "accountable_review_required",
                    "accepted": False,
                    "winner": None,
                    "changes_runtime_default": False,
                    "writes_expert_state": False,
                },
                "generated_at": self.generated_at.isoformat(),
            }
        )
        return payload.model_dump(mode="json")


def evaluate_epistemic_simulation(
    bundle: EpistemicSimulationCaseBundle,
    *,
    generated_at: datetime | None = None,
) -> EpistemicSimulationEvalReport:
    """Aggregate structural evidence without executing or judging any arm."""
    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    frozen_bundle = EpistemicSimulationCaseBundle.model_validate(bundle.model_dump(mode="json"))
    return EpistemicSimulationEvalReport(bundle=frozen_bundle, generated_at=timestamp)


def validate_epistemic_simulation_eval_payload(
    bundle: EpistemicSimulationCaseBundle,
    payload: EpistemicSimulationEvalPayload | dict[str, Any],
) -> EpistemicSimulationEvalPayload:
    """Recompute every report field against its frozen source bundle."""
    parsed = EpistemicSimulationEvalPayload.model_validate(payload)
    timestamp = datetime.fromisoformat(parsed.generated_at.replace("Z", "+00:00"))
    expected = evaluate_epistemic_simulation(bundle, generated_at=timestamp).to_dict()
    if parsed.model_dump(mode="json") != expected:
        raise ValueError("evaluation payload does not match its frozen source bundle")
    return parsed


__all__ = [
    "COMPARISON_ARM_IDS",
    "EPISTEMIC_SIMULATION_CASE_BUNDLE_SCHEMA_VERSION",
    "EPISTEMIC_SIMULATION_CASE_SCHEMA_VERSION",
    "EPISTEMIC_SIMULATION_EVAL_KIND",
    "EPISTEMIC_SIMULATION_EVAL_SCHEMA_VERSION",
    "EPISTEMIC_SIMULATION_METHODOLOGY_VERSION",
    "ComparisonArm",
    "EpistemicSimulationCase",
    "EpistemicSimulationCaseBundle",
    "EpistemicSimulationEvalPayload",
    "EpistemicSimulationEvalReport",
    "evaluate_epistemic_simulation",
    "validate_epistemic_simulation_eval_payload",
]
