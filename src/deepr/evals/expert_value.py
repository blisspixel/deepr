"""Operator-attested longitudinal value evaluation for durable experts.

This module validates a frozen four-arm review workbook and performs only
deterministic aggregation. It does not run an arm, call a model, judge answer
text, write expert state, or select a winner. A caller may separately supply a
root-confined artifact verification result for inclusion in the report.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from deepr.experts.blueprint import ExpertBlueprint
from deepr.experts.outcomes import normalize_timestamp

EXPERT_VALUE_REVIEW_SCHEMA_VERSION = "deepr-expert-value-review-v1"
EXPERT_VALUE_REVIEW_KIND = "deepr.eval.expert_value_review"
EXPERT_VALUE_REPORT_SCHEMA_VERSION = "deepr-expert-value-report-v1"
EXPERT_VALUE_REPORT_KIND = "deepr.eval.expert_value_report"
EXPERT_VALUE_METHODOLOGY_VERSION = "1.0"
EXPERT_VALUE_RUBRIC_VERSION = "expert-value-rubric-v1"

type ArmName = Literal[
    "fresh_research",
    "static_history",
    "compiled_expert",
    "maintained_expert",
]
type EvaluationRole = Literal[
    "initial",
    "retention",
    "update",
    "forward_transfer",
    "hard_negative",
]

ARM_ORDER: tuple[ArmName, ...] = (
    "fresh_research",
    "static_history",
    "compiled_expert",
    "maintained_expert",
)
ROLE_ORDER: tuple[EvaluationRole, ...] = (
    "initial",
    "retention",
    "update",
    "forward_transfer",
    "hard_negative",
)

SCORE_RUBRIC: dict[str, tuple[str, ...]] = {
    "correctness": (
        "Unusable or contradicted by the frozen source world.",
        "Major errors prevent the answer from supporting the case.",
        "Partly correct, with material omissions or errors.",
        "Mostly correct, with only minor issues.",
        "Fully correct for the operator-accepted acceptance criteria.",
    ),
    "source_relevance": (
        "No relevant source use.",
        "Sources are mostly irrelevant to the claims they accompany.",
        "Source relevance is mixed or incomplete.",
        "Sources are mostly relevant, with minor gaps.",
        "Sources are directly relevant to the claims they accompany.",
    ),
    "factual_support": (
        "Claims are unsupported or contradicted by the cited material.",
        "Support is weak for major factual claims.",
        "Support is partial or uneven.",
        "Major claims are supported, with minor gaps.",
        "All material factual claims are supported by the frozen evidence.",
    ),
    "uncertainty_calibration": (
        "Confidence or abstention is dangerously mismatched to the evidence.",
        "Uncertainty has a major mismatch with the evidence.",
        "Uncertainty handling is mixed.",
        "Uncertainty is mostly appropriate, with minor issues.",
        "Confidence, caveats, and abstention are appropriate to the evidence.",
    ),
}

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


def _clean_text(value: str, *, field_name: str, max_length: int = 4000) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    if len(cleaned) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return cleaned


def _clean_id(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not _ID_PATTERN.fullmatch(cleaned):
        raise ValueError(f"{field_name} contains unsupported characters")
    return cleaned


def _clean_hash(value: str, *, field_name: str) -> str:
    if not _HASH_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _validation_field_name(info: ValidationInfo) -> str:
    if info.field_name is None:
        raise ValueError("validator field name is unavailable")
    return info.field_name.replace("_", " ")


def _clean_refs(values: list[str], *, field_name: str, max_items: int = 200) -> list[str]:
    if len(values) > max_items:
        raise ValueError(f"{field_name} must contain at most {max_items} items")
    cleaned = [_clean_text(value, field_name=field_name) for value in values]
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"{field_name} must not contain duplicates")
    return cleaned


class SourceWorld(_StrictModel):
    """One frozen evidence world in a linear longitudinal sequence."""

    source_world_id: str
    as_of: str
    predecessor_source_world_id: str | None
    manifest_ref: str
    manifest_sha256: str
    supporting_source_count: int = Field(ge=1, le=1_000_000)
    distractor_source_count: int = Field(ge=1, le=1_000_000)
    noise_source_count: int = Field(ge=1, le=1_000_000)
    introduced_claim_refs: list[str] = Field(default_factory=list, max_length=200)
    invalidated_claim_refs: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("source_world_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return _clean_id(value, field_name="source world id")

    @field_validator("predecessor_source_world_id")
    @classmethod
    def validate_predecessor(cls, value: str | None) -> str | None:
        return None if value is None else _clean_id(value, field_name="predecessor source world id")

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: str) -> str:
        return normalize_timestamp(value, field_name="source world as of")

    @field_validator("manifest_ref")
    @classmethod
    def validate_manifest_ref(cls, value: str) -> str:
        return _clean_text(value, field_name="source world manifest ref")

    @field_validator("manifest_sha256")
    @classmethod
    def validate_manifest_hash(cls, value: str) -> str:
        return _clean_hash(value, field_name="source world manifest hash")

    @field_validator("introduced_claim_refs", "invalidated_claim_refs")
    @classmethod
    def validate_claim_refs(cls, values: list[str], info: ValidationInfo) -> list[str]:
        return _clean_refs(values, field_name=_validation_field_name(info))


class ObservedOutcomeReference(_StrictModel):
    """Frozen link to a later observed outcome without causal attribution."""

    deployed_arm: ArmName
    outcome_id: str
    outcome_record_ref: str
    outcome_record_sha256: str
    result: Literal["succeeded", "mixed", "failed", "unresolved"]

    @field_validator("outcome_id")
    @classmethod
    def validate_outcome_id(cls, value: str) -> str:
        return _clean_id(value, field_name="outcome id")

    @field_validator("outcome_record_ref")
    @classmethod
    def validate_outcome_ref(cls, value: str) -> str:
        return _clean_text(value, field_name="outcome record ref")

    @field_validator("outcome_record_sha256")
    @classmethod
    def validate_outcome_hash(cls, value: str) -> str:
        return _clean_hash(value, field_name="outcome record hash")


class ExpertValueCase(_StrictModel):
    """Blueprint acceptance case placement in a frozen source world."""

    acceptance_case_id: str
    source_world_id: str
    evaluation_role: EvaluationRole
    expected_abstention: bool
    observed_outcome: ObservedOutcomeReference | None = None

    @field_validator("acceptance_case_id", "source_world_id")
    @classmethod
    def validate_ids(cls, value: str, info: ValidationInfo) -> str:
        return _clean_id(value, field_name=_validation_field_name(info))


class ArmConfiguration(_StrictModel):
    """Frozen arm policy and non-consultation overhead."""

    arm: ArmName
    run_policy_ref: str
    run_policy_sha256: str
    construction_cost_usd: float = Field(ge=0.0, le=1_000_000_000.0)
    maintenance_cost_usd: float = Field(ge=0.0, le=1_000_000_000.0)
    construction_reviewer_minutes: float = Field(ge=0.0, le=100_000_000.0)
    maintenance_reviewer_minutes: float = Field(ge=0.0, le=100_000_000.0)

    @field_validator("run_policy_ref")
    @classmethod
    def validate_policy_ref(cls, value: str) -> str:
        return _clean_text(value, field_name="run policy ref")

    @field_validator("run_policy_sha256")
    @classmethod
    def validate_policy_hash(cls, value: str) -> str:
        return _clean_hash(value, field_name="run policy hash")


class TrialMeasurements(_StrictModel):
    """Measured resource use for one arm and one acceptance case."""

    retrieval_cost_usd: float = Field(ge=0.0, le=1_000_000_000.0)
    generation_cost_usd: float = Field(ge=0.0, le=1_000_000_000.0)
    other_execution_cost_usd: float = Field(ge=0.0, le=1_000_000_000.0)
    response_latency_seconds: float = Field(ge=0.0, le=100_000_000.0)
    reviewer_minutes: float = Field(ge=0.0, le=100_000_000.0)
    update_completed: bool | None = None
    update_latency_hours: float | None = Field(default=None, ge=0.0, le=100_000_000.0)


class OperatorSemanticAttestation(_StrictModel):
    """Operator-attested semantic labels that deterministic code never infers."""

    attested_by: str
    attested_at: str
    identity_verified: Literal[False]
    human_authorship_claimed: Literal[False]
    correctness: int = Field(ge=0, le=4)
    source_relevance: int = Field(ge=0, le=4)
    factual_support: int = Field(ge=0, le=4)
    uncertainty_calibration: int = Field(ge=0, le=4)
    abstained: bool
    false_support_observed: bool
    invalidated_belief_reused: bool | None = None
    negative_transfer_observed: bool | None = None
    retained_correctness: bool | None = None
    forward_transfer_observed: bool | None = None
    rationale: str

    @field_validator("attested_by")
    @classmethod
    def validate_attester(cls, value: str) -> str:
        return _clean_text(value, field_name="attested by", max_length=200)

    @field_validator("attested_at")
    @classmethod
    def validate_attested_at(cls, value: str) -> str:
        return normalize_timestamp(value, field_name="attested at")

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _clean_text(value, field_name="review rationale", max_length=8000)


class ExpertValueTrial(_StrictModel):
    """One frozen arm result and its operator semantic attestation."""

    acceptance_case_id: str
    arm: ArmName
    executed_at: str
    run_artifact_ref: str
    run_artifact_sha256: str
    answer_artifact_ref: str
    answer_artifact_sha256: str
    measurements: TrialMeasurements
    semantic_attestation: OperatorSemanticAttestation

    @field_validator("acceptance_case_id")
    @classmethod
    def validate_case_id(cls, value: str) -> str:
        return _clean_id(value, field_name="acceptance case id")

    @field_validator("executed_at")
    @classmethod
    def validate_executed_at(cls, value: str) -> str:
        return normalize_timestamp(value, field_name="executed at")

    @field_validator("run_artifact_ref", "answer_artifact_ref")
    @classmethod
    def validate_artifact_refs(cls, value: str, info: ValidationInfo) -> str:
        return _clean_text(value, field_name=_validation_field_name(info))

    @field_validator("run_artifact_sha256", "answer_artifact_sha256")
    @classmethod
    def validate_artifact_hashes(cls, value: str, info: ValidationInfo) -> str:
        return _clean_hash(value, field_name=_validation_field_name(info))


class ProtocolAttestation(_StrictModel):
    """Operator assertions about protocol execution, not answer quality."""

    attested_by: str
    attested_at: str
    identity_verified: Literal[False]
    human_authorship_claimed: Literal[False]
    review_blinding: Literal["blinded", "not_blinded"]
    review_order_randomized: bool
    review_assignment_ref: str
    review_assignment_sha256: str
    same_cases_confirmed: Literal[True]
    source_worlds_frozen: Literal[True]
    arm_isolation_confirmed: Literal[True]
    artifact_hashes_verified: Literal[True]

    @field_validator("attested_by")
    @classmethod
    def validate_attester(cls, value: str) -> str:
        return _clean_text(value, field_name="protocol attester", max_length=200)

    @field_validator("attested_at")
    @classmethod
    def validate_attested_at(cls, value: str) -> str:
        return normalize_timestamp(value, field_name="protocol attested at")

    @field_validator("review_assignment_ref")
    @classmethod
    def validate_assignment_ref(cls, value: str) -> str:
        return _clean_text(value, field_name="review assignment ref")

    @field_validator("review_assignment_sha256")
    @classmethod
    def validate_assignment_hash(cls, value: str) -> str:
        return _clean_hash(value, field_name="review assignment hash")


def _validate_source_world_chain(
    source_worlds: list[SourceWorld],
) -> tuple[dict[str, int], dict[str, SourceWorld]]:
    world_ids = [world.source_world_id for world in source_worlds]
    if len(set(world_ids)) != len(world_ids):
        raise ValueError("source world ids must be unique")
    previous: SourceWorld | None = None
    for world in source_worlds:
        expected_predecessor = previous.source_world_id if previous is not None else None
        if world.predecessor_source_world_id != expected_predecessor:
            raise ValueError("source worlds must form one ordered predecessor chain")
        if previous is not None and datetime.fromisoformat(world.as_of) <= datetime.fromisoformat(previous.as_of):
            raise ValueError("source world timestamps must increase strictly")
        previous = world
    return (
        {world_id: index for index, world_id in enumerate(world_ids)},
        {world.source_world_id: world for world in source_worlds},
    )


def _validate_arm_configurations(configurations: list[ArmConfiguration]) -> None:
    arms = [configuration.arm for configuration in configurations]
    if len(set(arms)) != len(arms) or set(arms) != set(ARM_ORDER):
        raise ValueError("arm configurations must contain each frozen arm exactly once")


def _validate_case_placement(
    cases: list[ExpertValueCase],
    world_index: dict[str, int],
    world_by_id: dict[str, SourceWorld],
) -> dict[str, ExpertValueCase]:
    case_ids = [case.acceptance_case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("acceptance cases must appear exactly once")
    for case in cases:
        if case.source_world_id not in world_index:
            raise ValueError(f"case '{case.acceptance_case_id}' references an unknown source world")
        index = world_index[case.source_world_id]
        if case.evaluation_role == "initial" and index != 0:
            raise ValueError("initial cases must use the first source world")
        if case.evaluation_role in {"retention", "update", "forward_transfer"} and index == 0:
            raise ValueError(f"{case.evaluation_role} cases require a later source world")
        if case.evaluation_role == "update":
            world = world_by_id[case.source_world_id]
            if not world.introduced_claim_refs and not world.invalidated_claim_refs:
                raise ValueError("update cases require introduced or invalidated claim refs in their source world")
    return {case.acceptance_case_id: case for case in cases}


def _validate_trial_matrix(
    trials: list[ExpertValueTrial],
    case_by_id: dict[str, ExpertValueCase],
) -> None:
    pairs = [(trial.acceptance_case_id, trial.arm) for trial in trials]
    if len(set(pairs)) != len(pairs):
        raise ValueError("each acceptance case and arm pair must appear once")
    expected_pairs = {(case_id, arm) for case_id in case_by_id for arm in ARM_ORDER}
    if set(pairs) != expected_pairs:
        raise ValueError("trials must form a complete four-arm matrix over all acceptance cases")


def _validate_role_specific_fields(
    trials: list[ExpertValueTrial],
    case_by_id: dict[str, ExpertValueCase],
    world_by_id: dict[str, SourceWorld],
) -> None:
    for trial in trials:
        case = case_by_id[trial.acceptance_case_id]
        retained = trial.semantic_attestation.retained_correctness
        transferred = trial.semantic_attestation.forward_transfer_observed
        stale_reuse = trial.semantic_attestation.invalidated_belief_reused
        negative_transfer = trial.semantic_attestation.negative_transfer_observed
        update_completed = trial.measurements.update_completed
        update_latency = trial.measurements.update_latency_hours
        if (case.evaluation_role == "retention") != (retained is not None):
            raise ValueError("retained_correctness must be set only for retention trials")
        if (case.evaluation_role == "forward_transfer") != (transferred is not None):
            raise ValueError("forward_transfer_observed must be set only for forward-transfer trials")
        stale_reuse_applies = bool(world_by_id[case.source_world_id].invalidated_claim_refs)
        if stale_reuse_applies != (stale_reuse is not None):
            raise ValueError("invalidated_belief_reused must be set only when the source world invalidates claims")
        negative_transfer_applies = case.evaluation_role != "initial"
        if negative_transfer_applies != (negative_transfer is not None):
            raise ValueError("negative_transfer_observed must be set only for later-world trials")
        is_update = case.evaluation_role == "update"
        if is_update != (update_completed is not None):
            raise ValueError("update_completed must be set only for update trials")
        if update_completed is True and update_latency is None:
            raise ValueError("completed updates require update_latency_hours")
        if update_completed is not True and update_latency is not None:
            raise ValueError("update_latency_hours requires a completed update")


def _validate_trial_temporal_order(
    trials: list[ExpertValueTrial],
    case_by_id: dict[str, ExpertValueCase],
    world_by_id: dict[str, SourceWorld],
    protocol_attestation: ProtocolAttestation,
) -> None:
    protocol_attested_at = datetime.fromisoformat(protocol_attestation.attested_at)
    for trial in trials:
        executed_at = datetime.fromisoformat(trial.executed_at)
        attested_at = datetime.fromisoformat(trial.semantic_attestation.attested_at)
        world = world_by_id[case_by_id[trial.acceptance_case_id].source_world_id]
        if executed_at < datetime.fromisoformat(world.as_of):
            raise ValueError("trial execution cannot predate its frozen source world")
        if attested_at < executed_at:
            raise ValueError("trial semantic attestation cannot predate trial execution")
        if protocol_attested_at < attested_at:
            raise ValueError("protocol attestation cannot predate a trial semantic attestation")


class ExpertValueReview(_StrictModel):
    """Completed operator-attested input for the four-arm evaluator."""

    schema_version: Literal["deepr-expert-value-review-v1"]
    kind: Literal["deepr.eval.expert_value_review"]
    methodology_version: Literal["1.0"]
    rubric_version: Literal["expert-value-rubric-v1"]
    review_set_id: str
    expert_name: str
    blueprint_revision: int = Field(ge=1)
    blueprint_content_hash: str
    source_worlds: list[SourceWorld] = Field(min_length=2, max_length=50)
    cases: list[ExpertValueCase] = Field(min_length=1, max_length=500)
    arm_configurations: list[ArmConfiguration] = Field(min_length=4, max_length=4)
    trials: list[ExpertValueTrial] = Field(min_length=4, max_length=2000)
    protocol_attestation: ProtocolAttestation

    @field_validator("review_set_id")
    @classmethod
    def validate_review_set_id(cls, value: str) -> str:
        return _clean_id(value, field_name="review set id")

    @field_validator("expert_name")
    @classmethod
    def validate_expert_name(cls, value: str) -> str:
        return _clean_text(value, field_name="expert name", max_length=120)

    @field_validator("blueprint_content_hash")
    @classmethod
    def validate_blueprint_hash(cls, value: str) -> str:
        return _clean_hash(value, field_name="blueprint content hash")

    @model_validator(mode="after")
    def validate_protocol_matrix(self) -> Self:
        world_index, world_by_id = _validate_source_world_chain(self.source_worlds)
        _validate_arm_configurations(self.arm_configurations)
        case_by_id = _validate_case_placement(self.cases, world_index, world_by_id)
        _validate_trial_matrix(self.trials, case_by_id)
        _validate_role_specific_fields(self.trials, case_by_id, world_by_id)
        _validate_trial_temporal_order(self.trials, case_by_id, world_by_id, self.protocol_attestation)
        return self


def expert_value_review_template(blueprint: ExpertBlueprint) -> dict[str, Any]:
    """Return intentionally incomplete scaffolding bound to one blueprint."""
    arm_configurations = [
        {
            "arm": arm,
            "run_policy_ref": "",
            "run_policy_sha256": "",
            "construction_cost_usd": 0.0,
            "maintenance_cost_usd": 0.0,
            "construction_reviewer_minutes": 0.0,
            "maintenance_reviewer_minutes": 0.0,
        }
        for arm in ARM_ORDER
    ]
    cases = [
        {
            "acceptance_case_id": case.id,
            "source_world_id": "",
            "evaluation_role": "",
            "expected_abstention": None,
            "observed_outcome": None,
        }
        for case in blueprint.acceptance_cases
    ]
    trials = []
    for case in blueprint.acceptance_cases:
        for arm in ARM_ORDER:
            trials.append(
                {
                    "acceptance_case_id": case.id,
                    "arm": arm,
                    "executed_at": "",
                    "run_artifact_ref": "",
                    "run_artifact_sha256": "",
                    "answer_artifact_ref": "",
                    "answer_artifact_sha256": "",
                    "measurements": {
                        "retrieval_cost_usd": 0.0,
                        "generation_cost_usd": 0.0,
                        "other_execution_cost_usd": 0.0,
                        "response_latency_seconds": None,
                        "reviewer_minutes": None,
                        "update_completed": None,
                        "update_latency_hours": None,
                    },
                    "semantic_attestation": {
                        "attested_by": "",
                        "attested_at": "",
                        "identity_verified": False,
                        "human_authorship_claimed": False,
                        "correctness": None,
                        "source_relevance": None,
                        "factual_support": None,
                        "uncertainty_calibration": None,
                        "abstained": None,
                        "false_support_observed": None,
                        "invalidated_belief_reused": None,
                        "negative_transfer_observed": None,
                        "retained_correctness": None,
                        "forward_transfer_observed": None,
                        "rationale": "",
                    },
                }
            )
    return {
        "schema_version": EXPERT_VALUE_REVIEW_SCHEMA_VERSION,
        "kind": EXPERT_VALUE_REVIEW_KIND,
        "methodology_version": EXPERT_VALUE_METHODOLOGY_VERSION,
        "rubric_version": EXPERT_VALUE_RUBRIC_VERSION,
        "review_set_id": "",
        "expert_name": blueprint.expert_name,
        "blueprint_revision": blueprint.revision,
        "blueprint_content_hash": blueprint.content_hash,
        "source_worlds": [
            {
                "source_world_id": "source-world-1",
                "as_of": "",
                "predecessor_source_world_id": None,
                "manifest_ref": "",
                "manifest_sha256": "",
                "supporting_source_count": None,
                "distractor_source_count": None,
                "noise_source_count": None,
                "introduced_claim_refs": [],
                "invalidated_claim_refs": [],
            },
            {
                "source_world_id": "source-world-2",
                "as_of": "",
                "predecessor_source_world_id": "source-world-1",
                "manifest_ref": "",
                "manifest_sha256": "",
                "supporting_source_count": None,
                "distractor_source_count": None,
                "noise_source_count": None,
                "introduced_claim_refs": [],
                "invalidated_claim_refs": [],
            },
        ],
        "cases": cases,
        "arm_configurations": arm_configurations,
        "trials": trials,
        "protocol_attestation": {
            "attested_by": "",
            "attested_at": "",
            "identity_verified": False,
            "human_authorship_claimed": False,
            "review_blinding": "",
            "review_order_randomized": None,
            "review_assignment_ref": "",
            "review_assignment_sha256": "",
            "same_cases_confirmed": False,
            "source_worlds_frozen": False,
            "arm_isolation_confirmed": False,
            "artifact_hashes_verified": False,
        },
    }


def load_expert_value_review(path: Path) -> ExpertValueReview:
    """Load a strict completed review workbook from JSON."""
    return ExpertValueReview.model_validate(json.loads(path.read_text(encoding="utf-8")))


def validate_review_blueprint_binding(review: ExpertValueReview, blueprint: ExpertBlueprint) -> None:
    """Fail closed if a review does not bind to the exact current blueprint."""
    if review.expert_name != blueprint.expert_name:
        raise ValueError("review expert name does not match the operator-attested blueprint")
    if review.blueprint_revision != blueprint.revision:
        raise ValueError("review blueprint revision is stale")
    if review.blueprint_content_hash != blueprint.content_hash:
        raise ValueError("review blueprint content hash does not match")
    expected_case_ids = {case.id for case in blueprint.acceptance_cases}
    actual_case_ids = {case.acceptance_case_id for case in review.cases}
    if actual_case_ids != expected_case_ids:
        raise ValueError("review cases must match the blueprint acceptance cases exactly")


def expert_value_review_hash(review: ExpertValueReview) -> str:
    """Return a stable hash over the validated review content."""
    canonical = json.dumps(
        review.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _mean(values: list[float | int]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _rate(observed: int, eligible: int) -> float | None:
    return round(observed / eligible, 6) if eligible else None


def _binary_summary(values: list[bool]) -> dict[str, int | float | None]:
    observed = sum(values)
    return {"eligible_trials": len(values), "observed_trials": observed, "rate": _rate(observed, len(values))}


def _dimension_summary(trials: list[ExpertValueTrial], field_name: str) -> dict[str, int | float | None]:
    scores = [getattr(trial.semantic_attestation, field_name) for trial in trials]
    return {"attested_trials": len(scores), "mean_score": _mean(scores)}


def _arm_result(
    arm: ArmName,
    review: ExpertValueReview,
    case_by_id: dict[str, ExpertValueCase],
) -> dict[str, Any]:
    trials = [trial for trial in review.trials if trial.arm == arm]
    configuration = next(item for item in review.arm_configurations if item.arm == arm)
    stale_reuse = [
        trial.semantic_attestation.invalidated_belief_reused
        for trial in trials
        if trial.semantic_attestation.invalidated_belief_reused is not None
    ]
    negative_transfer = [
        trial.semantic_attestation.negative_transfer_observed
        for trial in trials
        if trial.semantic_attestation.negative_transfer_observed is not None
    ]
    retention = [
        trial.semantic_attestation.retained_correctness
        for trial in trials
        if case_by_id[trial.acceptance_case_id].evaluation_role == "retention"
    ]
    transfer = [
        trial.semantic_attestation.forward_transfer_observed
        for trial in trials
        if case_by_id[trial.acceptance_case_id].evaluation_role == "forward_transfer"
    ]
    update_trials = [trial for trial in trials if case_by_id[trial.acceptance_case_id].evaluation_role == "update"]
    completed_updates = [trial for trial in update_trials if trial.measurements.update_completed is True]
    retention_values = [value for value in retention if value is not None]
    transfer_values = [value for value in transfer if value is not None]
    latency_values = [
        trial.measurements.update_latency_hours
        for trial in completed_updates
        if trial.measurements.update_latency_hours is not None
    ]
    retrieval = sum(trial.measurements.retrieval_cost_usd for trial in trials)
    generation = sum(trial.measurements.generation_cost_usd for trial in trials)
    other = sum(trial.measurements.other_execution_cost_usd for trial in trials)
    fixed = configuration.construction_cost_usd + configuration.maintenance_cost_usd
    marginal_total = retrieval + generation + other
    trial_review_minutes = sum(trial.measurements.reviewer_minutes for trial in trials)
    overhead_minutes = configuration.construction_reviewer_minutes + configuration.maintenance_reviewer_minutes
    return {
        "arm": arm,
        "trial_count": len(trials),
        "dimensions": {
            name: _dimension_summary(trials, name)
            for name in ("correctness", "source_relevance", "factual_support", "uncertainty_calibration")
        },
        "false_support": _binary_summary([trial.semantic_attestation.false_support_observed for trial in trials]),
        "invalidated_belief_reuse": _binary_summary(stale_reuse),
        "negative_transfer": _binary_summary(negative_transfer),
        "expected_abstention_match": _binary_summary(
            [
                trial.semantic_attestation.abstained == case_by_id[trial.acceptance_case_id].expected_abstention
                for trial in trials
            ]
        ),
        "retained_correctness": _binary_summary(retention_values),
        "forward_transfer": _binary_summary(transfer_values),
        "update_latency_hours": {
            "eligible_trials": len(update_trials),
            "completed_trials": len(completed_updates),
            "completion_rate": _rate(len(completed_updates), len(update_trials)),
            "mean_completed": _mean(latency_values),
            "maximum_completed": round(max(latency_values), 6) if latency_values else None,
        },
        "response_latency_seconds": {
            "trial_count": len(trials),
            "mean": _mean([trial.measurements.response_latency_seconds for trial in trials]),
        },
        "costs_usd": {
            "construction": round(configuration.construction_cost_usd, 6),
            "maintenance": round(configuration.maintenance_cost_usd, 6),
            "retrieval": round(retrieval, 6),
            "generation": round(generation, 6),
            "other_execution": round(other, 6),
            "fixed_total": round(fixed, 6),
            "marginal_total": round(marginal_total, 6),
            "mean_marginal_per_consultation": _mean(
                [
                    trial.measurements.retrieval_cost_usd
                    + trial.measurements.generation_cost_usd
                    + trial.measurements.other_execution_cost_usd
                    for trial in trials
                ]
            ),
            "total_observed": round(fixed + marginal_total, 6),
        },
        "reviewer_effort_minutes": {
            "construction": round(configuration.construction_reviewer_minutes, 6),
            "maintenance": round(configuration.maintenance_reviewer_minutes, 6),
            "trial_review": round(trial_review_minutes, 6),
            "total": round(overhead_minutes + trial_review_minutes, 6),
        },
    }


def _delta(target: float | None, comparator: float | None) -> float | None:
    if target is None or comparator is None:
        return None
    return round(target - comparator, 6)


def _comparisons(arm_results: list[dict[str, Any]], review: ExpertValueReview) -> list[dict[str, Any]]:
    from deepr.evals.expert_value_statistics import expert_value_paired_bootstrap

    by_arm = {result["arm"]: result for result in arm_results}
    target = by_arm["maintained_expert"]
    comparisons = []
    for comparator_arm in ARM_ORDER[:-1]:
        comparator = by_arm[comparator_arm]
        comparisons.append(
            {
                "target_arm": "maintained_expert",
                "comparator_arm": comparator_arm,
                "paired_bootstrap": expert_value_paired_bootstrap(
                    review,
                    target_arm="maintained_expert",
                    comparator_arm=comparator_arm,
                ),
                "deltas": {
                    "mean_correctness": _delta(
                        target["dimensions"]["correctness"]["mean_score"],
                        comparator["dimensions"]["correctness"]["mean_score"],
                    ),
                    "mean_source_relevance": _delta(
                        target["dimensions"]["source_relevance"]["mean_score"],
                        comparator["dimensions"]["source_relevance"]["mean_score"],
                    ),
                    "mean_factual_support": _delta(
                        target["dimensions"]["factual_support"]["mean_score"],
                        comparator["dimensions"]["factual_support"]["mean_score"],
                    ),
                    "false_support_rate": _delta(target["false_support"]["rate"], comparator["false_support"]["rate"]),
                    "invalidated_belief_reuse_rate": _delta(
                        target["invalidated_belief_reuse"]["rate"],
                        comparator["invalidated_belief_reuse"]["rate"],
                    ),
                    "negative_transfer_rate": _delta(
                        target["negative_transfer"]["rate"], comparator["negative_transfer"]["rate"]
                    ),
                    "mean_marginal_cost_usd": _delta(
                        target["costs_usd"]["mean_marginal_per_consultation"],
                        comparator["costs_usd"]["mean_marginal_per_consultation"],
                    ),
                    "reviewer_effort_minutes": _delta(
                        target["reviewer_effort_minutes"]["total"],
                        comparator["reviewer_effort_minutes"]["total"],
                    ),
                },
            }
        )
    return comparisons


def _break_even_estimates(arm_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_arm = {result["arm"]: result for result in arm_results}
    target = by_arm["maintained_expert"]
    estimates = []
    for comparator_arm in ARM_ORDER[:-1]:
        comparator = by_arm[comparator_arm]
        fixed_delta = target["costs_usd"]["fixed_total"] - comparator["costs_usd"]["fixed_total"]
        target_marginal = target["costs_usd"]["mean_marginal_per_consultation"]
        comparator_marginal = comparator["costs_usd"]["mean_marginal_per_consultation"]
        savings = comparator_marginal - target_marginal
        if fixed_delta <= 0:
            status = "target_not_more_expensive_at_zero_consultations"
            consultations: int | None = 0
        elif savings > 0:
            status = "estimable"
            consultations = math.ceil(fixed_delta / savings)
        else:
            status = "not_recoverable_on_reported_marginal_costs"
            consultations = None
        estimates.append(
            {
                "target_arm": "maintained_expert",
                "comparator_arm": comparator_arm,
                "status": status,
                "fixed_cost_delta_usd": round(fixed_delta, 6),
                "marginal_savings_usd_per_consultation": round(savings, 6),
                "break_even_consultations": consultations,
                "cost_only": True,
                "quality_considered": False,
            }
        )
    return estimates


def build_expert_value_report(
    review: ExpertValueReview,
    blueprint: ExpertBlueprint,
    *,
    now: datetime | None = None,
    artifact_verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate an operator-attested review without a semantic verdict."""
    from deepr.evals.expert_value_artifacts import operator_attested_artifact_verification

    validate_review_blueprint_binding(review, blueprint)
    verification = artifact_verification or operator_attested_artifact_verification(review)
    case_by_id = {case.acceptance_case_id: case for case in review.cases}
    role_counts = {role: 0 for role in ROLE_ORDER}
    for case in review.cases:
        role_counts[case.evaluation_role] += 1
    arm_results = [_arm_result(arm, review, case_by_id) for arm in ARM_ORDER]
    outcomes = [case.observed_outcome for case in review.cases if case.observed_outcome is not None]
    deployed_counts = {arm: 0 for arm in ARM_ORDER}
    result_counts = {result: 0 for result in ("succeeded", "mixed", "failed", "unresolved")}
    for outcome in outcomes:
        deployed_counts[outcome.deployed_arm] += 1
        result_counts[outcome.result] += 1
    generated_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    return {
        "schema_version": EXPERT_VALUE_REPORT_SCHEMA_VERSION,
        "kind": EXPERT_VALUE_REPORT_KIND,
        "methodology_version": EXPERT_VALUE_METHODOLOGY_VERSION,
        "rubric_version": EXPERT_VALUE_RUBRIC_VERSION,
        "rubric": {name: list(anchors) for name, anchors in SCORE_RUBRIC.items()},
        "generated_at": generated_at,
        "review_input_sha256": expert_value_review_hash(review),
        "review_set_id": review.review_set_id,
        "expert": {
            "name": blueprint.expert_name,
            "blueprint_revision": blueprint.revision,
            "blueprint_content_hash": blueprint.content_hash,
        },
        "protocol": {
            "arms": list(ARM_ORDER),
            "source_world_count": len(review.source_worlds),
            "source_world_start": review.source_worlds[0].as_of,
            "source_world_end": review.source_worlds[-1].as_of,
            "acceptance_case_count": len(review.cases),
            "attested_trial_count": len(review.trials),
            "evaluation_role_case_counts": role_counts,
            "missing_evaluation_roles": [role for role in ROLE_ORDER if role_counts[role] == 0],
            "four_arm_matrix_complete": True,
            "review_blinding": review.protocol_attestation.review_blinding,
            "review_order_randomized": review.protocol_attestation.review_order_randomized,
            "review_assignment_ref": review.protocol_attestation.review_assignment_ref,
            "review_assignment_sha256": review.protocol_attestation.review_assignment_sha256,
            "protocol_attested_by": review.protocol_attestation.attested_by,
            "protocol_attested_at": review.protocol_attestation.attested_at,
            "statistical_sufficiency_assessed": False,
        },
        "arm_results": arm_results,
        "comparisons": _comparisons(arm_results, review),
        "break_even_estimates": _break_even_estimates(arm_results),
        "artifact_verification": verification,
        "observed_outcomes": {
            "linked_case_count": len(outcomes),
            "deployed_arm_counts": deployed_counts,
            "result_counts": result_counts,
            "causal_attribution": False,
        },
        "contract": {
            "input_semantic_review": "operator_attested",
            "reviewer_identity_verified": False,
            "evaluator_model_calls": 0,
            "evaluator_provider_calls": 0,
            "evaluator_network_access": False,
            "evaluator_cost_usd": 0.0,
            "artifact_references_opened": verification["independently_verified"],
            "writes_authoritative_state": False,
            "changes_defaults": False,
            "winner_selected": False,
            "causal_attribution": False,
            "semantic_verdict": False,
            "lexical_verdict_allowed": False,
            "report_write_requires_explicit_path": True,
        },
    }


__all__ = [
    "ARM_ORDER",
    "EXPERT_VALUE_METHODOLOGY_VERSION",
    "EXPERT_VALUE_REPORT_KIND",
    "EXPERT_VALUE_REPORT_SCHEMA_VERSION",
    "EXPERT_VALUE_REVIEW_KIND",
    "EXPERT_VALUE_REVIEW_SCHEMA_VERSION",
    "EXPERT_VALUE_RUBRIC_VERSION",
    "ROLE_ORDER",
    "SCORE_RUBRIC",
    "ArmConfiguration",
    "ExpertValueCase",
    "ExpertValueReview",
    "ExpertValueTrial",
    "ObservedOutcomeReference",
    "OperatorSemanticAttestation",
    "ProtocolAttestation",
    "SourceWorld",
    "TrialMeasurements",
    "build_expert_value_report",
    "expert_value_review_hash",
    "expert_value_review_template",
    "load_expert_value_review",
    "validate_review_blueprint_binding",
]
