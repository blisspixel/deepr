"""Read-only authority contracts for inspectable epistemic simulations.

The models in this module validate representation, provenance, lane, branch,
and replay shape. They do not judge whether a statement is true, useful,
coherent, novel, or relevant. No function here performs I/O or writes expert
state.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_validator,
)

EPISTEMIC_SIMULATION_SCHEMA_VERSION = "deepr-epistemic-simulation-v1"
CONSULT_CONTEXT_SCHEMA_VERSION = "deepr-consult-context-v2"

AuthorityLane = Literal["factual", "perspective", "simulation", "episodic", "governance"]
AUTHORITY_LANES: tuple[AuthorityLane, ...] = (
    "factual",
    "perspective",
    "simulation",
    "episodic",
    "governance",
)
EvidenceClass = Literal[
    "public_source",
    "private_document",
    "experiment",
    "tool_observation",
    "sensor_observation",
    "testimony",
    "formal_derivation",
    "outcome_observation",
]
VerificationStatus = Literal[
    "verified",
    "not_publicly_verifiable",
    "source_withheld",
    "not_yet_tested",
    "lost_source",
    "contested_observation",
    "in_principle_untestable",
    "not_applicable",
]
RecordType = Literal[
    "factual_claim",
    "interpretation",
    "hypothesis",
    "assumption",
    "counterfactual_implication",
    "forecast",
    "episode",
    "disclosure",
    "policy",
]
RecordStatus = Literal["current", "invalidated", "retired"]
ProvenanceClass = Literal[
    "source_derived",
    "user_supplied",
    "model_proposed",
    "reviewer_accepted",
    "simulation_derived",
    "outcome_observed",
]
Relation = Literal[
    "supports",
    "contradicts",
    "enables",
    "derived_from",
    "assumes",
    "implies_within",
    "analogizes_to",
    "predicts",
    "tested_by",
    "disconfirmed_by",
    "inspired_by",
    "forked_from",
]

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def _require_true(value: bool) -> bool:
    if not value:
        raise ValueError("value must be true")
    return value


def _require_false(value: bool) -> bool:
    if value:
        raise ValueError("value must be false")
    return value


StrictTrue = Annotated[
    bool,
    Field(strict=True, json_schema_extra={"const": True}),
    AfterValidator(_require_true),
]
StrictFalse = Annotated[
    bool,
    Field(strict=True, json_schema_extra={"const": False}),
    AfterValidator(_require_false),
]
ZeroInt = Annotated[int, Field(strict=True, ge=0, le=0, json_schema_extra={"const": 0})]
ZeroFloat = Annotated[float, Field(strict=True, ge=0.0, le=0.0, json_schema_extra={"const": 0.0})]

_FACTUAL_RELATIONS = frozenset({"supports", "contradicts", "enables", "derived_from"})
_SIMULATION_RELATIONS = frozenset(
    {
        "assumes",
        "implies_within",
        "analogizes_to",
        "predicts",
        "tested_by",
        "disconfirmed_by",
        "inspired_by",
        "forked_from",
    }
)
_PROSPECTIVE_TYPES = frozenset({"counterfactual_implication", "forecast"})
_NON_EVIDENCE_PROVENANCE = frozenset({"model_proposed", "simulation_derived"})
_RECORD_TYPES_BY_LANE: dict[AuthorityLane, frozenset[RecordType]] = {
    "factual": frozenset({"factual_claim"}),
    "perspective": frozenset({"interpretation", "hypothesis"}),
    "simulation": frozenset({"assumption", "counterfactual_implication", "forecast", "hypothesis"}),
    "episodic": frozenset({"episode"}),
    "governance": frozenset({"disclosure", "policy"}),
}


class EpistemicContractError(ValueError):
    """Raised when linked records violate an authority or branch invariant."""


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


def _require_unique(values: Sequence[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique values")


def _parse_iso_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 date-time") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _canonical_json_bytes(value: BaseModel | dict[str, Any] | list[Any] | tuple[Any, ...]) -> bytes:
    payload: Any = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: BaseModel | dict[str, Any] | list[Any] | tuple[Any, ...]) -> str:
    """Return a deterministic digest over a JSON-compatible value."""
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


class AccessPolicy(_ContractModel):
    visibility: Literal["public", "access_controlled", "withheld"]
    authorized_principal_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    redacted_description: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_access(self) -> AccessPolicy:
        _require_unique(self.authorized_principal_ids, "authorized_principal_ids")
        if self.visibility == "public" and self.authorized_principal_ids:
            raise ValueError("public evidence cannot carry an authorization list")
        if self.visibility == "access_controlled":
            if not self.authorized_principal_ids or self.redacted_description is None:
                raise ValueError("access-controlled evidence requires principals and a redacted description")
        if self.visibility == "withheld" and self.authorized_principal_ids:
            raise ValueError("withheld evidence cannot carry an authorization list")
        return self


class EvidenceUnit(_ContractModel):
    evidence_id: NonEmptyStr
    evidence_class: EvidenceClass
    content_sha256: Sha256
    creator_or_observer: NonEmptyStr
    observed_at: NonEmptyStr
    valid_time: NonEmptyStr
    access_policy: AccessPolicy
    independence_root_id: NonEmptyStr
    verification_status: VerificationStatus
    claim_refs: tuple[NonEmptyStr, ...] = Field(min_length=1)
    edge_refs: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    revision_refs: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_evidence(self) -> EvidenceUnit:
        _parse_iso_datetime(self.observed_at, "observed_at")
        _require_unique(self.claim_refs, "claim_refs")
        _require_unique(self.edge_refs, "edge_refs")
        _require_unique(self.revision_refs, "revision_refs")
        return self


def principal_can_inspect(evidence: EvidenceUnit, principal_id: str) -> bool:
    """Return whether one named principal may inspect an evidence unit."""
    policy = evidence.access_policy
    if policy.visibility == "public":
        return True
    if policy.visibility == "access_controlled":
        return principal_id in policy.authorized_principal_ids
    return False


class SimulationDisclosure(_ContractModel):
    text: NonEmptyStr
    persistent: StrictTrue
    constructed_simulation: StrictTrue
    identity_claims_allowed: StrictFalse
    prohibited_claims: tuple[NonEmptyStr, ...] = Field(min_length=6)

    @model_validator(mode="after")
    def validate_prohibited_claims(self) -> SimulationDisclosure:
        required = {
            "historical_identity",
            "alien_origin",
            "interdimensional_perception",
            "future_observation",
            "consciousness",
            "invented_memory",
        }
        if not required.issubset(self.prohibited_claims):
            raise ValueError("simulation disclosure must preserve every prohibited identity claim")
        _require_unique(self.prohibited_claims, "prohibited_claims")
        return self


class BranchCondition(_ContractModel):
    variable: NonEmptyStr
    value: NonEmptyStr


class WorldModel(_ContractModel):
    world_model_id: NonEmptyStr
    branch_id: NonEmptyStr
    parent_branch_id: NonEmptyStr | None = None
    fork_reason: NonEmptyStr
    time_anchor: NonEmptyStr
    scenario_time: NonEmptyStr
    controlled_condition: BranchCondition
    condition_record_id: NonEmptyStr
    assumption_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    invariants: tuple[NonEmptyStr, ...] = Field(min_length=1)
    exclusions: tuple[NonEmptyStr, ...] = Field(min_length=1)
    status: Literal["active", "retired"] = "active"

    @model_validator(mode="after")
    def validate_branch_lineage(self) -> WorldModel:
        if self.parent_branch_id == self.branch_id:
            raise ValueError("parent_branch_id must differ from branch_id")
        if self.condition_record_id not in self.assumption_record_ids:
            raise ValueError("condition_record_id must be one of the branch assumptions")
        _require_unique(self.assumption_record_ids, "assumption_record_ids")
        _require_unique(self.invariants, "invariants")
        _require_unique(self.exclusions, "exclusions")
        return self


class MethodPack(_ContractModel):
    method_pack_id: NonEmptyStr
    version: NonEmptyStr
    operations: tuple[NonEmptyStr, ...] = Field(min_length=1)
    provenance_refs: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    attributed_to_historical_subject: StrictBool = False

    @model_validator(mode="after")
    def validate_method_pack(self) -> MethodPack:
        _require_unique(self.operations, "operations")
        if self.attributed_to_historical_subject and not self.provenance_refs:
            raise ValueError("historically attributed method operations require provenance_refs")
        return self


class MemoryPolicy(_ContractModel):
    allowed_lanes: tuple[AuthorityLane, ...]
    read_scope: Literal["frozen_fixture_only"]
    write_policy: Literal["none"]
    tool_scope: Literal["none"]
    spend_ceiling_usd: ZeroFloat
    prospective_authority: Literal["candidate_only"]

    @model_validator(mode="after")
    def validate_lanes(self) -> MemoryPolicy:
        if tuple(self.allowed_lanes) != AUTHORITY_LANES:
            raise ValueError("allowed_lanes must preserve the canonical five-lane order")
        return self


class SnapshotRefs(_ContractModel):
    schema_version: NonEmptyStr
    lens_version: NonEmptyStr
    expert_snapshot_version: NonEmptyStr
    context_compiler_version: NonEmptyStr
    prompt_version: NonEmptyStr
    model_id: NonEmptyStr | None = None


class EpistemicRecord(_ContractModel):
    record_id: NonEmptyStr
    lane: AuthorityLane
    record_type: RecordType
    statement: NonEmptyStr
    valid_time: NonEmptyStr
    recorded_at: NonEmptyStr
    branch_id: NonEmptyStr | None = None
    scenario_time: NonEmptyStr | None = None
    branch_condition: BranchCondition | None = None
    provenance_class: ProvenanceClass
    verification_status: VerificationStatus
    evidence_refs: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    assumption_refs: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    expected_observations: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    disconfirmers: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    review_after: NonEmptyStr | None = None
    expires_at: NonEmptyStr | None = None
    status: RecordStatus = "current"
    superseded_by: NonEmptyStr | None = None
    candidate_only: StrictBool = False

    @model_validator(mode="after")
    def validate_authority(self) -> EpistemicRecord:
        _validate_record_lane_type(self)
        _validate_record_time_and_scope(self)
        _validate_factual_record(self)
        _validate_candidate_record(self)
        _validate_record_status(self)
        _require_unique(self.evidence_refs, "evidence_refs")
        _require_unique(self.assumption_refs, "assumption_refs")
        _require_unique(self.expected_observations, "expected_observations")
        _require_unique(self.disconfirmers, "disconfirmers")
        return self


def _validate_record_lane_type(record: EpistemicRecord) -> None:
    if record.record_type not in _RECORD_TYPES_BY_LANE[record.lane]:
        raise ValueError(f"record_type {record.record_type} is incompatible with the {record.lane} authority lane")


def _validate_record_time_and_scope(record: EpistemicRecord) -> None:
    recorded_at = _parse_iso_datetime(record.recorded_at, "recorded_at")
    if record.review_after is not None:
        if _parse_iso_datetime(record.review_after, "review_after") <= recorded_at:
            raise ValueError("review_after must follow recorded_at")
    if record.expires_at is not None:
        if _parse_iso_datetime(record.expires_at, "expires_at") <= recorded_at:
            raise ValueError("expires_at must follow recorded_at")
    if (record.branch_id is None) != (record.scenario_time is None):
        raise ValueError("branch_id and scenario_time must be supplied together")
    if record.lane in {"simulation", "episodic"} and record.branch_id is None:
        raise ValueError(f"{record.lane} record requires branch_id and scenario_time")
    if record.record_type in _PROSPECTIVE_TYPES and record.branch_id is None:
        raise ValueError("counterfactual implications and forecasts require branch_id and scenario_time")
    if record.branch_condition is not None and (record.lane != "simulation" or record.record_type != "assumption"):
        raise ValueError("branch_condition is restricted to simulation assumption records")


def _validate_factual_record(record: EpistemicRecord) -> None:
    if record.lane != "factual":
        return
    if record.branch_id is not None:
        raise ValueError("factual record cannot inherit a simulation branch_id or scenario_time")
    if record.provenance_class in _NON_EVIDENCE_PROVENANCE or not record.evidence_refs:
        raise ValueError("factual record requires an external evidence provenance root")
    if record.candidate_only:
        raise ValueError("factual record cannot have candidate_only authority")
    if record.assumption_refs:
        raise ValueError("factual record cannot depend on simulation assumptions")


def _validate_candidate_record(record: EpistemicRecord) -> None:
    if record.record_type in _PROSPECTIVE_TYPES and not record.candidate_only:
        raise ValueError("prospective records require candidate_only authority")
    if record.candidate_only and (
        not record.expected_observations
        or not record.disconfirmers
        or (record.review_after is None and record.expires_at is None)
    ):
        raise ValueError("candidate records require observations, disconfirmers, and review timing")


def _validate_record_status(record: EpistemicRecord) -> None:
    if record.status == "invalidated" and record.superseded_by is None:
        raise ValueError("invalidated records require superseded_by")
    if record.status != "invalidated" and record.superseded_by is not None:
        raise ValueError("only invalidated records may declare superseded_by")


class EpistemicEdge(_ContractModel):
    edge_id: NonEmptyStr
    relation: Relation
    source_record_id: NonEmptyStr
    target_record_id: NonEmptyStr
    branch_id: NonEmptyStr | None = None
    scenario_time: NonEmptyStr | None = None
    provenance_refs: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_relation_shape(self) -> EpistemicEdge:
        if self.relation in _SIMULATION_RELATIONS and (self.branch_id is None or self.scenario_time is None):
            raise ValueError("simulation-aware edges require branch_id and scenario_time")
        if self.relation in _FACTUAL_RELATIONS and (self.branch_id is not None or self.scenario_time is not None):
            raise ValueError("factual edges cannot inherit simulation branch metadata")
        _require_unique(self.provenance_refs, "provenance_refs")
        return self


class BeliefRevision(_ContractModel):
    revision_id: NonEmptyStr
    sequence: StrictInt = Field(ge=1)
    valid_time: NonEmptyStr
    recorded_at: NonEmptyStr
    branch_id: NonEmptyStr | None = None
    scenario_time: NonEmptyStr | None = None
    prior_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    posterior_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    triggering_evidence_refs: tuple[NonEmptyStr, ...] = Field(min_length=1)
    alternatives_preserved: tuple[NonEmptyStr, ...] = Field(min_length=1)
    update_method: NonEmptyStr
    update_method_provenance_refs: tuple[NonEmptyStr, ...] = Field(min_length=1)
    calibration_scope: NonEmptyStr | None = None
    numeric_values_are_probabilities: StrictBool = False

    @model_validator(mode="after")
    def validate_revision(self) -> BeliefRevision:
        _parse_iso_datetime(self.recorded_at, "recorded_at")
        if (self.branch_id is None) != (self.scenario_time is None):
            raise ValueError("revision branch_id and scenario_time must be supplied together")
        if set(self.prior_record_ids).intersection(self.posterior_record_ids):
            raise ValueError("revision prior and posterior records must be immutable and disjoint")
        if self.numeric_values_are_probabilities and self.calibration_scope is None:
            raise ValueError("probability revisions require calibration_scope")
        _require_unique(self.prior_record_ids, "prior_record_ids")
        _require_unique(self.posterior_record_ids, "posterior_record_ids")
        _require_unique(self.triggering_evidence_refs, "triggering_evidence_refs")
        _require_unique(self.alternatives_preserved, "alternatives_preserved")
        _require_unique(self.update_method_provenance_refs, "update_method_provenance_refs")
        return self


class SimulationAuthorityContract(_ContractModel):
    read_only: StrictTrue
    writes_expert_state: StrictFalse
    writes_graph: StrictFalse
    simulation_to_factual_transition: StrictFalse
    transcript_is_evidence: StrictFalse
    consensus_is_evidence: StrictFalse
    semantic_verdict: StrictFalse


class EpistemicSimulation(_ContractModel):
    schema_version: Literal["deepr-epistemic-simulation-v1"]
    kind: Literal["deepr.expert.epistemic_simulation"]
    representation_mode: Literal["epistemic_simulation"]
    lens_id: NonEmptyStr
    display_label: NonEmptyStr
    purpose: NonEmptyStr
    disclosure: SimulationDisclosure
    world_models: tuple[WorldModel, ...] = Field(min_length=1)
    method_pack: MethodPack
    memory_policy: MemoryPolicy
    evidence_units: tuple[EvidenceUnit, ...] = Field(min_length=1)
    records: tuple[EpistemicRecord, ...] = Field(min_length=5)
    edges: tuple[EpistemicEdge, ...]
    belief_revisions: tuple[BeliefRevision, ...]
    snapshots: SnapshotRefs
    contract: SimulationAuthorityContract

    @model_validator(mode="after")
    def validate_linked_authority(self) -> EpistemicSimulation:
        record_by_id = {record.record_id: record for record in self.records}
        evidence_by_id = {item.evidence_id: item for item in self.evidence_units}
        edge_by_id = {edge.edge_id: edge for edge in self.edges}
        world_model_by_branch = {world.branch_id: world for world in self.world_models}
        revision_by_id = {revision.revision_id: revision for revision in self.belief_revisions}
        _validate_lens_identifiers(
            self,
            record_by_id,
            evidence_by_id,
            edge_by_id,
            world_model_by_branch,
            revision_by_id,
        )
        _validate_revision_order(self.belief_revisions)
        if set(record.lane for record in self.records) != set(AUTHORITY_LANES):
            raise ValueError("records must exercise all five authority lanes")
        if self.snapshots.schema_version != self.schema_version:
            raise ValueError("snapshot schema_version must match the lens schema_version")
        _validate_record_links(self, record_by_id, evidence_by_id, set(world_model_by_branch))
        _validate_method_pack_links(self.method_pack, evidence_by_id)
        _validate_evidence_links(self.evidence_units, record_by_id, edge_by_id, revision_by_id)
        _validate_world_model_links(self.world_models, record_by_id)
        _validate_edge_links(self.edges, record_by_id, evidence_by_id, set(world_model_by_branch))
        _validate_revision_links(
            self.belief_revisions,
            record_by_id,
            evidence_by_id,
            set(world_model_by_branch),
        )
        return self


def _validate_lens_identifiers(
    lens: EpistemicSimulation,
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
    edge_by_id: dict[str, EpistemicEdge],
    world_model_by_branch: dict[str, WorldModel],
    revision_by_id: dict[str, BeliefRevision],
) -> None:
    if len(record_by_id) != len(lens.records):
        raise ValueError("record_id values must be unique")
    if len(evidence_by_id) != len(lens.evidence_units):
        raise ValueError("evidence_id values must be unique")
    if len(world_model_by_branch) != len(lens.world_models):
        raise ValueError("world-model branch_id values must be unique")
    _require_unique([world.world_model_id for world in lens.world_models], "world_model_id values")
    if len(edge_by_id) != len(lens.edges):
        raise ValueError("edge_id values must be unique")
    if len(revision_by_id) != len(lens.belief_revisions):
        raise ValueError("revision_id values must be unique")
    namespaces = (
        ("record", set(record_by_id)),
        ("evidence", set(evidence_by_id)),
        ("edge", set(edge_by_id)),
        ("world_model", {world.world_model_id for world in lens.world_models}),
        ("revision", set(revision_by_id)),
    )
    owners: dict[str, str] = {}
    for namespace, identifiers in namespaces:
        for identifier in identifiers:
            prior_owner = owners.setdefault(identifier, namespace)
            if prior_owner != namespace:
                raise ValueError(
                    f"artifact identifier {identifier} collides across {prior_owner} and {namespace} namespaces"
                )


def _validate_revision_order(revisions: tuple[BeliefRevision, ...]) -> None:
    if len({revision.sequence for revision in revisions}) != len(revisions):
        raise ValueError("belief revision sequence values must be unique")
    expected_sequences = tuple(range(1, len(revisions) + 1))
    if tuple(revision.sequence for revision in revisions) != expected_sequences:
        raise ValueError("belief revisions must preserve contiguous sequence order")
    revision_times = tuple(_parse_iso_datetime(revision.recorded_at, "recorded_at") for revision in revisions)
    if revision_times != tuple(sorted(revision_times)):
        raise ValueError("belief revision recorded_at values must preserve sequence chronology")


def _validate_record_links(
    lens: EpistemicSimulation,
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
    branch_ids: set[str],
) -> None:
    for record in lens.records:
        if set(record.evidence_refs).difference(evidence_by_id):
            raise ValueError(f"record {record.record_id} has unknown evidence_refs")
        if any(record.record_id not in evidence_by_id[item].claim_refs for item in record.evidence_refs):
            raise ValueError(f"record {record.record_id} has evidence_refs without reciprocal claim provenance")
        if set(record.assumption_refs).difference(record_by_id):
            raise ValueError(f"record {record.record_id} has unknown assumption_refs")
        if record.provenance_class == "reviewer_accepted" and not record.evidence_refs:
            raise ValueError("reviewer-accepted records require a linked review evidence artifact")
        if record.branch_id is not None and record.branch_id not in branch_ids:
            raise ValueError(f"record {record.record_id} references an unknown branch_id")
        for assumption_id in record.assumption_refs:
            assumption = record_by_id[assumption_id]
            if assumption.record_type != "assumption" or assumption.lane != "simulation":
                raise ValueError("assumption_refs must reference simulation assumption records")
            if assumption.status != "current" or assumption.branch_id != record.branch_id:
                raise ValueError("assumption_refs must preserve current branch-local authority")
        _validate_supersession(record, record_by_id)
    _validate_assumption_dependencies(record_by_id)


def _validate_assumption_dependencies(record_by_id: dict[str, EpistemicRecord]) -> None:
    dependency_count = {record_id: len(record.assumption_refs) for record_id, record in record_by_id.items()}
    dependents: dict[str, set[str]] = {record_id: set() for record_id in record_by_id}
    for record_id, record in record_by_id.items():
        if record_id in record.assumption_refs:
            raise ValueError("assumption dependencies cannot reference their own record")
        for dependency_id in record.assumption_refs:
            dependents[dependency_id].add(record_id)
    ready = [record_id for record_id, count in dependency_count.items() if count == 0]
    processed = 0
    while ready:
        dependency_id = ready.pop()
        processed += 1
        for dependent_id in dependents[dependency_id]:
            dependency_count[dependent_id] -= 1
            if dependency_count[dependent_id] == 0:
                ready.append(dependent_id)
    if processed != len(record_by_id):
        raise ValueError("assumption dependencies must be acyclic")


def _validate_supersession(record: EpistemicRecord, record_by_id: dict[str, EpistemicRecord]) -> None:
    if record.superseded_by is None:
        return
    replacement = record_by_id.get(record.superseded_by)
    if replacement is None:
        raise ValueError(f"record {record.record_id} has unknown superseded_by")
    if replacement.status != "current" or replacement.lane != record.lane:
        raise ValueError("superseded records require a current replacement in the same authority lane")


def _validate_evidence_links(
    evidence_units: tuple[EvidenceUnit, ...],
    record_by_id: dict[str, EpistemicRecord],
    edge_by_id: dict[str, EpistemicEdge],
    revision_by_id: dict[str, BeliefRevision],
) -> None:
    for evidence in evidence_units:
        if set(evidence.claim_refs).difference(record_by_id):
            raise ValueError(f"evidence {evidence.evidence_id} has unknown claim_refs")
        if any(evidence.evidence_id not in record_by_id[item].evidence_refs for item in evidence.claim_refs):
            raise ValueError(f"evidence {evidence.evidence_id} has claim_refs without reciprocal provenance")
        if set(evidence.edge_refs).difference(edge_by_id):
            raise ValueError(f"evidence {evidence.evidence_id} has unknown edge_refs")
        if any(evidence.evidence_id not in edge_by_id[item].provenance_refs for item in evidence.edge_refs):
            raise ValueError(f"evidence {evidence.evidence_id} has edge_refs without reciprocal provenance")
        if set(evidence.revision_refs).difference(revision_by_id):
            raise ValueError(f"evidence {evidence.evidence_id} has unknown revision_refs")
        if any(
            evidence.evidence_id not in revision_by_id[item].triggering_evidence_refs for item in evidence.revision_refs
        ):
            raise ValueError(f"evidence {evidence.evidence_id} has revision_refs without reciprocal trigger provenance")


def _validate_method_pack_links(method_pack: MethodPack, evidence_by_id: dict[str, EvidenceUnit]) -> None:
    if set(method_pack.provenance_refs).difference(evidence_by_id):
        raise ValueError("method_pack provenance_refs must reference frozen evidence units")


def _validate_world_model_links(
    world_models: tuple[WorldModel, ...],
    record_by_id: dict[str, EpistemicRecord],
) -> None:
    branch_ids = {world.branch_id for world in world_models}
    declared_assumption_ids: set[str] = set()
    for world_model in world_models:
        _validate_world_model(world_model, record_by_id, branch_ids)
        declared_assumption_ids.update(world_model.assumption_record_ids)
    actual_assumption_ids = {
        record.record_id
        for record in record_by_id.values()
        if record.lane == "simulation" and record.record_type == "assumption" and record.status == "current"
    }
    if declared_assumption_ids != actual_assumption_ids:
        raise ValueError("world-model assumption manifests must exactly cover current simulation assumption records")
    _validate_world_model_lineage(world_models)


def _validate_world_model(
    world_model: WorldModel,
    record_by_id: dict[str, EpistemicRecord],
    branch_ids: set[str],
) -> None:
    if world_model.parent_branch_id is not None and world_model.parent_branch_id not in branch_ids:
        raise ValueError("world_model parent_branch_id must reference a frozen branch")
    if set(world_model.assumption_record_ids).difference(record_by_id):
        raise ValueError("world_model assumption_record_ids must reference records")
    for assumption_id in world_model.assumption_record_ids:
        assumption = record_by_id[assumption_id]
        if assumption.lane != "simulation" or assumption.record_type != "assumption":
            raise ValueError("world_model assumptions must reference simulation assumption records")
        if assumption.branch_id != world_model.branch_id or assumption.status != "current":
            raise ValueError("world_model assumptions must preserve current branch-local authority")
    condition_record = record_by_id[world_model.condition_record_id]
    structured_condition_ids = tuple(
        assumption_id
        for assumption_id in world_model.assumption_record_ids
        if record_by_id[assumption_id].branch_condition is not None
    )
    if structured_condition_ids != (world_model.condition_record_id,):
        raise ValueError("world_model requires exactly one structured condition record")
    if condition_record.branch_condition != world_model.controlled_condition:
        raise ValueError("world_model controlled_condition must match its condition record")
    if condition_record.scenario_time != world_model.scenario_time:
        raise ValueError("world_model scenario_time must match its condition record")


def _validate_world_model_lineage(world_models: tuple[WorldModel, ...]) -> None:
    parent_by_branch = {world.branch_id: world.parent_branch_id for world in world_models}
    if not any(parent is None for parent in parent_by_branch.values()):
        raise ValueError("world models require at least one root branch")
    for branch_id in parent_by_branch:
        visited: set[str] = set()
        current: str | None = branch_id
        while current is not None:
            if current in visited:
                raise ValueError("world-model parent branches must be acyclic")
            visited.add(current)
            current = parent_by_branch[current]


def _validate_edge_links(
    edges: tuple[EpistemicEdge, ...],
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
    branch_ids: set[str],
) -> None:
    provenance_ids = set(record_by_id).union(evidence_by_id)
    for edge in edges:
        _validate_edge(edge, record_by_id, evidence_by_id, provenance_ids, branch_ids)


def _validate_edge(
    edge: EpistemicEdge,
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
    provenance_ids: set[str],
    branch_ids: set[str],
) -> None:
    if edge.source_record_id not in record_by_id or edge.target_record_id not in record_by_id:
        raise ValueError(f"edge {edge.edge_id} references an unknown record")
    if set(edge.provenance_refs).difference(provenance_ids):
        raise ValueError(f"edge {edge.edge_id} has unknown provenance_refs")
    source = record_by_id[edge.source_record_id]
    target = record_by_id[edge.target_record_id]
    _validate_edge_authority(edge, source, target, evidence_by_id)
    _validate_edge_branch(edge, source, target, branch_ids)


def _validate_edge_authority(
    edge: EpistemicEdge,
    source: EpistemicRecord,
    target: EpistemicRecord,
    evidence_by_id: dict[str, EvidenceUnit],
) -> None:
    if source.lane != "factual" and target.lane == "factual":
        raise ValueError("non-factual-to-factual edges are prohibited")
    if edge.relation in _FACTUAL_RELATIONS and (source.lane != "factual" or target.lane != "factual"):
        raise ValueError("factual relations require factual source and target records")
    evidence_refs = set(edge.provenance_refs).intersection(evidence_by_id)
    if edge.relation in _FACTUAL_RELATIONS and set(edge.provenance_refs).difference(evidence_by_id):
        raise ValueError("factual relations require evidence-unit provenance only")
    if any(edge.edge_id not in evidence_by_id[item].edge_refs for item in evidence_refs):
        raise ValueError("edge evidence provenance requires reciprocal evidence edge_refs")
    if edge.relation in _FACTUAL_RELATIONS:
        endpoint_ids = {edge.source_record_id, edge.target_record_id}
        claimed_ids = {claim_id for item in evidence_refs for claim_id in evidence_by_id[item].claim_refs}
        if not endpoint_ids.issubset(claimed_ids):
            raise ValueError("factual edge evidence must bind both endpoint records")


def _validate_edge_branch(
    edge: EpistemicEdge,
    source: EpistemicRecord,
    target: EpistemicRecord,
    branch_ids: set[str],
) -> None:
    if edge.branch_id is not None and edge.branch_id not in branch_ids:
        raise ValueError(f"edge {edge.edge_id} references an unknown branch")
    endpoint_branch_ids = {record.branch_id for record in (source, target) if record.branch_id is not None}
    if endpoint_branch_ids and (len(endpoint_branch_ids) != 1 or edge.branch_id not in endpoint_branch_ids):
        raise ValueError(f"edge {edge.edge_id} leaks across branch scope")
    if edge.relation in _SIMULATION_RELATIONS and edge.branch_id not in endpoint_branch_ids:
        raise ValueError("simulation-aware edges require a branch-scoped endpoint")


def _validate_revision_links(
    revisions: tuple[BeliefRevision, ...],
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
    branch_ids: set[str],
) -> None:
    for revision in revisions:
        _validate_revision(revision, record_by_id, evidence_by_id, branch_ids)
    invalidated_ids = {record.record_id for record in record_by_id.values() if record.status == "invalidated"}
    revision_prior_ids = tuple(record_id for revision in revisions for record_id in revision.prior_record_ids)
    if set(revision_prior_ids) != invalidated_ids or len(revision_prior_ids) != len(set(revision_prior_ids)):
        raise ValueError("every invalidated record must appear exactly once in belief revision priors")


def _validate_revision(
    revision: BeliefRevision,
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
    branch_ids: set[str],
) -> None:
    revision_records = set(revision.prior_record_ids).union(revision.posterior_record_ids)
    _validate_revision_references(revision, revision_records, record_by_id, evidence_by_id)
    _validate_revision_states(revision, revision_records, record_by_id, evidence_by_id)
    _validate_revision_chronology(revision, revision_records, record_by_id, evidence_by_id)
    _validate_revision_scope(revision, revision_records, record_by_id, branch_ids)


def _validate_revision_references(
    revision: BeliefRevision,
    revision_records: set[str],
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
) -> None:
    if revision_records.difference(record_by_id):
        raise ValueError(f"revision {revision.revision_id} references an unknown record")
    if set(revision.triggering_evidence_refs).difference(evidence_by_id):
        raise ValueError(f"revision {revision.revision_id} references unknown evidence")
    if set(revision.update_method_provenance_refs).difference(evidence_by_id):
        raise ValueError(f"revision {revision.revision_id} update-method provenance must reference evidence units")


def _validate_revision_states(
    revision: BeliefRevision,
    revision_records: set[str],
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
) -> None:
    if any(record_by_id[item].status != "invalidated" for item in revision.prior_record_ids):
        raise ValueError("revision prior records must retain invalidated state")
    if any(record_by_id[item].status != "current" for item in revision.posterior_record_ids):
        raise ValueError("revision posterior records must retain current state")
    if any(record_by_id[item].superseded_by not in revision.posterior_record_ids for item in revision.prior_record_ids):
        raise ValueError("revision posterior records must match prior superseded_by links")
    if any(
        revision.revision_id not in evidence_by_id[item].revision_refs for item in revision.triggering_evidence_refs
    ):
        raise ValueError("triggering evidence must reciprocally reference its belief revision")
    if len({record_by_id[item].lane for item in revision_records}) != 1:
        raise ValueError("belief revisions cannot cross authority lanes")


def _validate_revision_scope(
    revision: BeliefRevision,
    revision_records: set[str],
    record_by_id: dict[str, EpistemicRecord],
    branch_ids: set[str],
) -> None:
    if revision.branch_id is not None and revision.branch_id not in branch_ids:
        raise ValueError(f"revision {revision.revision_id} references an unknown branch")
    revision_branch_ids = {record_by_id[item].branch_id for item in revision_records}
    if revision_branch_ids != {revision.branch_id}:
        raise ValueError(f"revision {revision.revision_id} loses branch scope")


def _validate_revision_chronology(
    revision: BeliefRevision,
    revision_records: set[str],
    record_by_id: dict[str, EpistemicRecord],
    evidence_by_id: dict[str, EvidenceUnit],
) -> None:
    causal_times = [
        *(_parse_iso_datetime(record_by_id[item].recorded_at, "recorded_at") for item in revision_records),
        *(
            _parse_iso_datetime(evidence_by_id[item].observed_at, "observed_at")
            for item in revision.triggering_evidence_refs
        ),
    ]
    if _parse_iso_datetime(revision.recorded_at, "recorded_at") < max(causal_times):
        raise ValueError("belief revision recorded_at cannot precede its records or triggering evidence")


class ContextBounds(_ContractModel):
    max_context_bytes: StrictInt = Field(gt=0, le=4_194_304)
    max_paths: StrictInt = Field(gt=0, le=128)
    max_records: StrictInt = Field(gt=0, le=1024)


class CompiledContextPath(_ContractModel):
    path_id: NonEmptyStr
    record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    edge_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    lane_sequence: tuple[AuthorityLane, ...] = Field(min_length=1)
    branch_id: NonEmptyStr | None = None
    scenario_time: NonEmptyStr | None = None
    why_this_lens: NonEmptyStr
    provenance_refs: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_path_shape(self) -> CompiledContextPath:
        if len(self.lane_sequence) != len(self.record_ids):
            raise ValueError("lane_sequence must align one-to-one with record_ids")
        _require_unique(self.record_ids, "record_ids")
        _require_unique(self.edge_ids, "edge_ids")
        _require_unique(self.provenance_refs, "provenance_refs")
        if (self.branch_id is None) != (self.scenario_time is None):
            raise ValueError("branch_id and scenario_time must be supplied together")
        return self


class ContextAuthorityContract(_ContractModel):
    read_only: StrictTrue
    candidate_context_only: StrictTrue
    writes_expert_state: StrictFalse
    writes_graph: StrictFalse
    decides_relevance: StrictFalse
    decides_truth: StrictFalse
    semantic_verdict: StrictFalse


class LaneReservations(_ContractModel):
    factual: StrictInt = Field(ge=0)
    perspective: StrictInt = Field(ge=0)
    simulation: StrictInt = Field(ge=0)
    episodic: StrictInt = Field(ge=0)
    governance: StrictInt = Field(ge=0)

    @property
    def total_bytes(self) -> int:
        return self.factual + self.perspective + self.simulation + self.episodic + self.governance


class ConsultContextPacket(_ContractModel):
    schema_version: Literal["deepr-consult-context-v2"]
    kind: Literal["deepr.consult.context"]
    context_id: NonEmptyStr
    query_id: NonEmptyStr
    lens_id: NonEmptyStr
    branch_id: NonEmptyStr
    consumer_principal_id: NonEmptyStr
    simulation_disclosure: NonEmptyStr
    disclosure_persistent: StrictTrue
    constructed_simulation: StrictTrue
    identity_claims_allowed: StrictFalse
    expert_snapshot_version: NonEmptyStr
    compiler_version: NonEmptyStr
    selected_paths: tuple[CompiledContextPath, ...] = Field(min_length=1)
    selected_record_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)
    selected_edge_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    excluded_invalidated_record_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    lane_reservations: LaneReservations
    content_bytes: StrictInt = Field(gt=0)
    bounds: ContextBounds
    contract: ContextAuthorityContract

    @model_validator(mode="after")
    def validate_packet_shape(self) -> ConsultContextPacket:
        if len(self.selected_paths) > self.bounds.max_paths:
            raise ValueError("selected_paths exceed max_paths")
        if len(self.selected_record_ids) > self.bounds.max_records:
            raise ValueError("selected_record_ids exceed max_records")
        if self.content_bytes > self.bounds.max_context_bytes:
            raise ValueError("content_bytes exceed max_context_bytes")
        if self.lane_reservations.total_bytes > self.bounds.max_context_bytes:
            raise ValueError("lane reservations exceed max_context_bytes")
        _require_unique(self.selected_record_ids, "selected_record_ids")
        _require_unique(self.selected_edge_ids, "selected_edge_ids")
        _require_unique(self.excluded_invalidated_record_ids, "excluded_invalidated_record_ids")
        _require_unique([path.path_id for path in self.selected_paths], "path_id values")
        return self


__all__ = [
    "AUTHORITY_LANES",
    "CONSULT_CONTEXT_SCHEMA_VERSION",
    "EPISTEMIC_SIMULATION_SCHEMA_VERSION",
    "CompiledContextPath",
    "ConsultContextPacket",
    "EpistemicContractError",
    "EpistemicSimulation",
    "canonical_sha256",
    "principal_can_inspect",
]
