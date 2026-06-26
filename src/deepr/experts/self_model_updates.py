"""Verifier-gated self-model update records."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepr.config import default_data_dir
from deepr.experts.loop_runs import ExpertLoopRunStore
from deepr.experts.metacognitive_monitor import (
    METACOGNITIVE_MONITOR_SCHEMA_VERSION,
    build_consult_trace_candidates_for_expert,
    build_metacognitive_monitor_report,
)
from deepr.utils.atomic_io import atomic_write_json

if TYPE_CHECKING:
    from deepr.experts.profile import ExpertProfile

SELF_MODEL_UPDATE_SCHEMA_VERSION = "deepr-expert-self-model-update-v1"
SELF_MODEL_UPDATE_KIND = "deepr.expert.self_model_update"

_ALLOWED_PROPOSAL_TARGETS = {
    "calibration_review": {"self_model.calibration"},
    "capacity_strategy_review": {"self_model.learning_strategy.capacity_order"},
    "learning_strategy_update": {"self_model.learning_strategy"},
    "self_model_review": {"self_model.blocked_capabilities"},
}
_ALLOWED_EVIDENCE_PREFIXES = {"loop_run", "self_model"}
_SAFE_FRAGMENT = re.compile(r"[^A-Za-z0-9_.-]+")


class SelfModelUpdateError(ValueError):
    """Raised when a self-model update record cannot be written safely."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def default_self_model_update_dir() -> Path:
    """Return the default append-only directory for self-model update records."""
    configured = os.getenv("DEEPR_DATA_DIR")
    base = Path(configured) if configured else default_data_dir()
    return base / "self_model_updates"


def _contract(*, apply: bool) -> dict[str, Any]:
    return {
        "read_only": not apply,
        "cost_usd": 0.0,
        "derived_from": METACOGNITIVE_MONITOR_SCHEMA_VERSION,
        "requires_human_review": True,
        "auto_apply": False,
        "apply_required": True,
        "mutates_derived_self_model": False,
        "writes_review_record_only": True,
        "authority_changes_allowed": False,
    }


def _proposal_for_id(monitor_payload: dict[str, Any], proposal_id: str) -> dict[str, Any]:
    for proposal in monitor_payload.get("proposals", []) or []:
        if isinstance(proposal, dict) and proposal.get("proposal_id") == proposal_id:
            return proposal
    raise SelfModelUpdateError(f"No monitor proposal found for id '{proposal_id}'.")


def _evidence_prefix(ref: str) -> str:
    prefix, _, _ = ref.partition(":")
    return prefix


def _verifier_checks(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    proposal_type = str(proposal.get("proposal_type", ""))
    target = str(proposal.get("target", ""))
    evidence_refs = [str(ref) for ref in proposal.get("evidence_refs", []) or []]
    allowed_targets = _ALLOWED_PROPOSAL_TARGETS.get(proposal_type, set())
    evidence_prefixes = {_evidence_prefix(ref) for ref in evidence_refs}
    return [
        {
            "name": "allowed_proposal_type",
            "passed": proposal_type in _ALLOWED_PROPOSAL_TARGETS,
            "detail": proposal_type,
        },
        {
            "name": "allowed_target_path",
            "passed": target in allowed_targets,
            "detail": target,
        },
        {
            "name": "evidence_refs_present",
            "passed": bool(evidence_refs),
            "detail": str(len(evidence_refs)),
        },
        {
            "name": "evidence_refs_structural",
            "passed": bool(evidence_refs) and evidence_prefixes <= _ALLOWED_EVIDENCE_PREFIXES,
            "detail": ",".join(sorted(evidence_prefixes)),
        },
        {
            "name": "human_review_required",
            "passed": proposal.get("status") == "review_required"
            and proposal.get("requires_human_review") is True
            and proposal.get("auto_apply") is False,
            "detail": str(proposal.get("status", "")),
        },
        {
            "name": "no_cost",
            "passed": True,
            "detail": "0.0",
        },
        {
            "name": "no_authority_change",
            "passed": True,
            "detail": "review_record_only",
        },
    ]


def _verify_or_raise(proposal_id: str, checks: list[dict[str, Any]]) -> None:
    failed = [str(check["name"]) for check in checks if not check.get("passed")]
    if failed:
        joined = ", ".join(failed)
        raise SelfModelUpdateError(f"Proposal '{proposal_id}' failed self-model update verifier: {joined}.")


def _update_kind(proposal_type: str) -> str:
    return {
        "calibration_review": "review_calibration",
        "capacity_strategy_review": "review_capacity_strategy",
        "learning_strategy_update": "review_learning_strategy",
        "self_model_review": "review_blockers_and_risks",
    }[proposal_type]


def _safe_fragment(value: str) -> str:
    fragment = _SAFE_FRAGMENT.sub("_", value).strip("._")
    return fragment[:96] or "unknown"


def _record_path(record: dict[str, Any], *, output_dir: Path | None) -> Path:
    root = output_dir or default_self_model_update_dir()
    timestamp = _utc_now().strftime("%Y%m%d_%H%M%S_%f")
    expert = _safe_fragment(str(record["expert_name"]))
    proposal_id = _safe_fragment(str(record["proposal_id"]))
    return root / expert / f"self_model_update_{proposal_id}_{timestamp}.json"


def _build_record(
    profile: ExpertProfile,
    proposal: dict[str, Any],
    monitor: dict[str, Any],
    *,
    apply: bool,
) -> dict[str, Any]:
    proposal_type = str(proposal["proposal_type"])
    evidence_refs = [str(ref) for ref in proposal.get("evidence_refs", []) or []]
    checks = _verifier_checks(proposal)
    _verify_or_raise(str(proposal["proposal_id"]), checks)
    return {
        "schema_version": SELF_MODEL_UPDATE_SCHEMA_VERSION,
        "kind": SELF_MODEL_UPDATE_KIND,
        "contract": _contract(apply=apply),
        "expert_name": profile.name,
        "proposal_id": str(proposal["proposal_id"]),
        "proposal_type": proposal_type,
        "target": str(proposal["target"]),
        "applied": apply,
        "status": "recorded" if apply else "preview",
        "proposed_update": {
            "update_kind": _update_kind(proposal_type),
            "target_path": str(proposal["target"]),
            "title": str(proposal["title"]),
            "rationale": str(proposal["rationale"]),
            "expected_effect": str(proposal["expected_effect"]),
            "review_action": "operator_review_required",
        },
        "verifier": {
            "status": "passed",
            "checks": checks,
        },
        "source": {
            "monitor_schema_version": str(monitor["schema_version"]),
            "evidence_refs": evidence_refs,
        },
        "generated_at": _utc_now().isoformat(),
    }


def propose_self_model_update(
    profile: ExpertProfile,
    proposal_id: str,
    *,
    apply: bool = False,
    trace_path: Path | None = None,
    limit: int = 20,
    max_proposals: int = 20,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Preview or write one verifier-gated self-model update record."""
    scan_limit = max(0, limit)
    proposal_limit = max(0, max_proposals)
    candidates = build_consult_trace_candidates_for_expert(
        profile.name,
        path=trace_path,
        limit=scan_limit,
        max_candidates=proposal_limit,
    )
    loop_runs = [] if scan_limit == 0 else ExpertLoopRunStore(profile.name).list_runs(limit=scan_limit)
    monitor = build_metacognitive_monitor_report(
        profile,
        loop_runs=loop_runs,
        consult_trace_candidates=candidates,
        max_proposals=proposal_limit,
    )
    proposal = _proposal_for_id(monitor, proposal_id)
    record = _build_record(profile, proposal, monitor, apply=apply)
    path = _record_path(record, output_dir=output_dir)
    if apply:
        record["artifact_path"] = str(path)
        record["actions"] = [{"action": "write_self_model_update_record", "status": "written", "path": str(path)}]
        atomic_write_json(path, record, fsync=True)
    else:
        record["actions"] = [
            {"action": "write_self_model_update_record", "status": "preview", "would_write": str(path.parent)}
        ]
    return record


__all__ = [
    "SELF_MODEL_UPDATE_KIND",
    "SELF_MODEL_UPDATE_SCHEMA_VERSION",
    "SelfModelUpdateError",
    "default_self_model_update_dir",
    "propose_self_model_update",
]
