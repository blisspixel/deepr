"""Assemble the strict expert-value workbook from a rehearsal and its bound labels.

Execution facts come from the rehearsal's own records: answer bytes and
digests, worker timing, `$0` cost, and maintenance status. Semantic labels come
only from a frozen reviewer binding. The protocol attestation is an operator
statement; it is filled only when the operator supplies their identity, and
never inferred. The result must still pass ``deepr eval expert-value``.

Workbook v1 needs an answer and an attestation for every case and arm, so a
run with failed or blocked cells is refused with the missing cells listed.
The rehearsal summary keeps those failures; this bridge cannot represent them.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.evals.expert_value import ARM_ORDER, ExpertValueReview
from deepr.experts.blueprint import ExpertBlueprint

REVIEW_DIR = "review"
BASE_LABEL_FIELDS = (
    "correctness",
    "source_relevance",
    "factual_support",
    "uncertainty_calibration",
    "abstained",
    "false_support_observed",
    "rationale",
    "attested_at",
    "reviewer_minutes",
)
# Role-specific attestation fields the workbook requires to be null when not applicable.
_ROLE_FIELDS = (
    "invalidated_belief_reused",
    "negative_transfer_observed",
    "retained_correctness",
    "forward_transfer_observed",
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def label_fields(role: str, *, later_world: bool, invalidation_applies: bool) -> list[str]:
    """Fields a reviewer must supply for one case; mirrors the workbook's role rules."""
    fields = list(BASE_LABEL_FIELDS)
    if invalidation_applies:
        fields.append("invalidated_belief_reused")
    if later_world:
        fields.append("negative_transfer_observed")
    if role == "retention":
        fields.append("retained_correctness")
    if role == "forward_transfer":
        fields.append("forward_transfer_observed")
    return fields


def world_label_context(world_claims: dict[str, Any]) -> dict[str, dict[str, bool]]:
    """Per world: is it later than the first, and has any claim been invalidated by then."""
    context: dict[str, dict[str, bool]] = {}
    invalidated = False
    for index, world in enumerate(world_claims["source_worlds"]):
        invalidated = invalidated or bool(world.get("invalidated_claim_refs"))
        context[world["source_world_id"]] = {"later_world": index > 0, "invalidation_applies": invalidated}
    return context


def _update_measurements(role: str, cell: dict[str, Any], workers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Whether the arm's answer state incorporated the case world's update.

    Fresh research rebuilds over the current world and static history reads
    it raw, so both incorporate it; the compiled checkpoint never does; the
    maintained expert does only when its maintenance for that world completed.
    """
    if role != "update":
        return {"update_completed": None, "update_latency_hours": None}
    arm = cell["arm"]
    if arm == "compiled_expert":
        return {"update_completed": False, "update_latency_hours": None}
    if arm == "static_history":
        return {"update_completed": True, "update_latency_hours": 0.0}
    if arm == "fresh_research":
        build = workers.get(f"construct-fresh-{cell['acceptance_case_id']}", {})
        return {"update_completed": True, "update_latency_hours": round(build.get("wall_seconds", 0.0) / 3600, 6)}
    if cell.get("maintenance_status") == "completed":
        update = workers.get(f"maintain-{cell['source_world_id']}", {})
        return {"update_completed": True, "update_latency_hours": round(update.get("wall_seconds", 0.0) / 3600, 6)}
    return {"update_completed": False, "update_latency_hours": None}


def _worker_results(run_root: Path) -> dict[str, dict[str, Any]]:
    """The orchestrator's per-worker records, which carry timing and completion time."""
    results: dict[str, dict[str, Any]] = {}
    for path in (run_root / "workers").glob("*/orchestrator.json"):
        results[path.parent.name] = json.loads(path.read_text(encoding="utf-8"))
    return results


def _world_manifests(run_root: Path, cells: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """One answer worker's verified input manifest stands for each world's frozen copy."""
    manifests: dict[str, tuple[str, str]] = {}
    for cell in cells:
        if cell["status"] == "answered" and cell["source_world_id"] not in manifests:
            path = run_root / "workers" / cell["worker_id"] / "input" / "manifest.json"
            manifests[cell["source_world_id"]] = (path.relative_to(run_root).as_posix(), _sha(path.read_bytes()))
    return manifests


def _trial(
    run_root: Path,
    cell: dict[str, Any],
    bound: dict[str, Any] | None,
    roles: dict[str, dict[str, Any]],
    context: dict[str, dict[str, bool]],
    workers: dict[str, dict[str, Any]],
    reviewer: str,
) -> dict[str, Any]:
    """One workbook trial from a recorded cell and its label for exactly that answer."""
    case_id, arm = cell["acceptance_case_id"], cell["arm"]
    if bound is None or bound["answer_sha256"] != cell["answer_sha256"]:
        raise ValueError(f"no bound label for the exact answer of {case_id}/{arm}")
    label = bound["label"]
    role = roles[case_id]["evaluation_role_draft"]
    required = label_fields(role, **context[cell["source_world_id"]])
    absent = [name for name in required if name not in label]
    if absent:
        raise ValueError(f"label for {case_id}/{arm} is missing: {', '.join(absent)}")
    semantic: dict[str, Any] = dict.fromkeys(_ROLE_FIELDS)
    semantic.update({name: label[name] for name in required if name != "reviewer_minutes"})
    worker = workers[cell["worker_id"]]
    cell_path = run_root / "cells" / cell["source_world_id"] / case_id / f"{arm}.json"
    return {
        "acceptance_case_id": case_id,
        "arm": arm,
        "executed_at": worker["finished_at"],
        "run_artifact_ref": cell_path.relative_to(run_root).as_posix(),
        "run_artifact_sha256": _sha(cell_path.read_bytes()),
        "answer_artifact_ref": cell["answer_ref"],
        "answer_artifact_sha256": cell["answer_sha256"],
        "measurements": {
            "retrieval_cost_usd": 0.0,
            "generation_cost_usd": 0.0,
            "other_execution_cost_usd": 0.0,
            "response_latency_seconds": float(worker["wall_seconds"]),
            "reviewer_minutes": float(label["reviewer_minutes"]),
            **_update_measurements(role, cell, workers),
        },
        "semantic_attestation": {
            "attested_by": reviewer,
            "identity_verified": False,
            "human_authorship_claimed": False,
            **semantic,
        },
    }


def assemble_workbook(
    run_root: Path,
    *,
    blueprint: ExpertBlueprint,
    placement: dict[str, Any],
    world_claims: dict[str, Any],
    key_bytes: bytes,
    binding: dict[str, Any],
    review_set_id: str,
    protocol_attested_by: str | None = None,
) -> dict[str, Any]:
    """Return a workbook dict; validates it when the protocol attestation is supplied."""
    from deepr.evals.expert_value_blinding import load_cells

    cells = load_cells(run_root)
    missing = sorted(f"{c['acceptance_case_id']}/{c['arm']}" for c in cells if c["status"] != "answered")
    if missing:
        raise ValueError(f"workbook v1 needs every cell answered; not answered: {', '.join(missing)}")
    if binding.get("key_sha256") != _sha(key_bytes):
        raise ValueError("label binding was made with a different assignment key")
    blueprint_cases = {case.id for case in blueprint.acceptance_cases}
    if {c["acceptance_case_id"] for c in cells} != blueprint_cases:
        raise ValueError(
            "rehearsal cases do not match the current attested blueprint; apply the reviewed blueprint first"
        )
    labels = {(e["acceptance_case_id"], e["arm"]): e for e in binding["bound"]}
    roles = {case["acceptance_case_id"]: case for case in placement["cases"]}
    context = world_label_context(world_claims)
    workers = _worker_results(run_root)
    manifests = _world_manifests(run_root, cells)
    review_dir = run_root / REVIEW_DIR
    review_dir.mkdir(exist_ok=True)
    key_path = review_dir / "assignment-key.json"
    if not key_path.exists():
        key_path.write_bytes(key_bytes)
    elif key_path.read_bytes() != key_bytes:
        raise ValueError("a different assignment key is already stored with this run")
    policy_bytes = (run_root / "policy.json").read_bytes()
    reviewer = binding["reviewer"]["id"]
    trials = [
        _trial(run_root, cell, labels.get((cell["acceptance_case_id"], cell["arm"])), roles, context, workers, reviewer)
        for cell in cells
    ]
    workbook: dict[str, Any] = {
        "schema_version": "deepr-expert-value-review-v1",
        "kind": "deepr.eval.expert_value_review",
        "methodology_version": "1.0",
        "rubric_version": "expert-value-rubric-v1",
        "review_set_id": review_set_id,
        "expert_name": blueprint.expert_name,
        "blueprint_revision": blueprint.revision,
        "blueprint_content_hash": blueprint.content_hash,
        "source_worlds": [
            {
                "source_world_id": world["source_world_id"],
                "as_of": world["as_of"],
                "predecessor_source_world_id": world["predecessor_source_world_id"],
                "manifest_ref": manifests[world["source_world_id"]][0],
                "manifest_sha256": manifests[world["source_world_id"]][1],
                "supporting_source_count": world["supporting_source_count"],
                "distractor_source_count": world["distractor_source_count"],
                "noise_source_count": world["noise_source_count"],
                "introduced_claim_refs": world.get("introduced_claim_refs", []),
                "invalidated_claim_refs": world.get("invalidated_claim_refs", []),
            }
            for world in world_claims["source_worlds"]
        ],
        "cases": [
            {
                "acceptance_case_id": case_id,
                "source_world_id": roles[case_id]["source_world_id"],
                "evaluation_role": roles[case_id]["evaluation_role_draft"],
                "expected_abstention": roles[case_id]["expected_abstention_draft"],
                "observed_outcome": None,
            }
            for case_id in sorted(blueprint_cases)
        ],
        "arm_configurations": [
            {
                "arm": arm,
                "run_policy_ref": "policy.json",
                "run_policy_sha256": _sha(policy_bytes),
                "construction_cost_usd": 0.0,
                "maintenance_cost_usd": 0.0,
                "construction_reviewer_minutes": 0.0,
                "maintenance_reviewer_minutes": 0.0,
            }
            for arm in ARM_ORDER
        ],
        "trials": trials,
        "protocol_attestation": {
            "attested_by": protocol_attested_by or "",
            "attested_at": datetime.now(UTC).isoformat() if protocol_attested_by else "",
            "identity_verified": False,
            "human_authorship_claimed": False,
            "review_blinding": "blinded",
            "review_order_randomized": True,
            "review_assignment_ref": key_path.relative_to(run_root).as_posix(),
            "review_assignment_sha256": _sha(key_bytes),
            "same_cases_confirmed": bool(protocol_attested_by),
            "source_worlds_frozen": bool(protocol_attested_by),
            "arm_isolation_confirmed": bool(protocol_attested_by),
            "artifact_hashes_verified": bool(protocol_attested_by),
        },
    }
    if protocol_attested_by:
        ExpertValueReview.model_validate(workbook)
    return workbook
