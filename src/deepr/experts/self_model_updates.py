"""Verifier-gated self-model update records."""

from __future__ import annotations

import json
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
SELF_MODEL_UPDATE_ACCEPTANCE_SCHEMA_VERSION = "deepr-expert-self-model-update-acceptance-v1"
SELF_MODEL_UPDATE_ACCEPTANCE_KIND = "deepr.expert.self_model_update_acceptance"
SELF_MODEL_UPDATE_CONTEXT_SCHEMA_VERSION = "deepr-expert-self-model-update-context-v1"
SELF_MODEL_UPDATE_CONTEXT_KIND = "deepr.expert.self_model_update_context"

_ALLOWED_PROPOSAL_TARGETS = {
    "calibration_review": {"self_model.calibration"},
    "capacity_strategy_review": {"self_model.learning_strategy.capacity_order"},
    "learning_strategy_update": {"self_model.learning_strategy"},
    "self_model_review": {"self_model.blocked_capabilities"},
}
_ALLOWED_EVIDENCE_PREFIXES = {"loop_run", "self_model"}
_ALLOWED_OUTCOME_EVIDENCE_PREFIXES = {"eval", "human_review", "loop_run", "source_pack"}
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


def default_self_model_update_acceptance_dir() -> Path:
    """Return the default append-only directory for accepted update records."""
    return default_self_model_update_dir() / "accepted"


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


def _evidence_parts(ref: str) -> tuple[str, str]:
    prefix, separator, value = ref.partition(":")
    if not separator:
        return prefix, ""
    return prefix, value


def _valid_evidence_refs(evidence_refs: list[str], *, allowed_prefixes: set[str]) -> bool:
    if not evidence_refs:
        return False
    for ref in evidence_refs:
        prefix, value = _evidence_parts(ref)
        if prefix not in allowed_prefixes or not value.strip():
            return False
    return True


def _evidence_prefix(ref: str) -> str:
    prefix, _ = _evidence_parts(ref)
    return prefix


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_zero_cost(value: Any) -> bool:
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return False


def _has_text(value: Any) -> bool:
    if value is None:
        return False
    return bool(str(value).strip())


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
            "passed": _valid_evidence_refs(evidence_refs, allowed_prefixes=_ALLOWED_EVIDENCE_PREFIXES),
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


def _acceptance_path(acceptance: dict[str, Any], *, output_dir: Path | None) -> Path:
    root = output_dir or default_self_model_update_acceptance_dir()
    timestamp = _utc_now().strftime("%Y%m%d_%H%M%S_%f")
    expert = _safe_fragment(str(acceptance["expert_name"]))
    proposal_id = _safe_fragment(str(acceptance["proposal_id"]))
    return root / expert / f"self_model_update_acceptance_{proposal_id}_{timestamp}.json"


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


def _load_update_record(record_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SelfModelUpdateError(f"Could not read self-model update record '{record_path}': {exc}") from exc
    if not isinstance(payload, dict):
        raise SelfModelUpdateError(f"Self-model update record '{record_path}' is not a JSON object.")
    return payload


def _acceptance_contract(*, apply: bool) -> dict[str, Any]:
    return {
        "read_only": not apply,
        "cost_usd": 0.0,
        "derived_from": SELF_MODEL_UPDATE_SCHEMA_VERSION,
        "requires_human_review": True,
        "auto_apply": False,
        "apply_required": True,
        "mutates_derived_self_model": False,
        "writes_acceptance_record_only": True,
        "authority_changes_allowed": False,
    }


def _acceptance_checks(
    record: dict[str, Any],
    *,
    expert_name: str,
    outcome_evidence_refs: list[str],
    reviewer: str,
) -> list[dict[str, Any]]:
    contract = _dict_or_empty(record.get("contract"))
    verifier = _dict_or_empty(record.get("verifier"))
    verifier_checks = verifier.get("checks") if isinstance(verifier.get("checks"), list) else []
    proposed_update = _dict_or_empty(record.get("proposed_update"))
    outcome_prefixes = {_evidence_prefix(ref) for ref in outcome_evidence_refs}
    proposal_type = str(record.get("proposal_type", ""))
    target = str(record.get("target", ""))
    return [
        {
            "name": "record_schema",
            "passed": record.get("schema_version") == SELF_MODEL_UPDATE_SCHEMA_VERSION
            and record.get("kind") == SELF_MODEL_UPDATE_KIND,
            "detail": str(record.get("schema_version", "")),
        },
        {
            "name": "recorded_update",
            "passed": record.get("status") == "recorded" and record.get("applied") is True,
            "detail": str(record.get("status", "")),
        },
        {
            "name": "expert_matches_record",
            "passed": str(record.get("expert_name", "")) == expert_name,
            "detail": str(record.get("expert_name", "")),
        },
        {
            "name": "record_identity_present",
            "passed": _has_text(record.get("proposal_id"))
            and proposal_type in _ALLOWED_PROPOSAL_TARGETS
            and target in _ALLOWED_PROPOSAL_TARGETS.get(proposal_type, set()),
            "detail": f"{proposal_type}:{target}",
        },
        {
            "name": "proposed_update_complete",
            "passed": all(
                _has_text(proposed_update.get(field))
                for field in ("update_kind", "target_path", "title", "expected_effect")
            )
            and str(proposed_update.get("target_path", "")) == target,
            "detail": str(proposed_update.get("target_path", "")),
        },
        {
            "name": "record_verifier_passed",
            "passed": verifier.get("status") == "passed"
            and bool(verifier_checks)
            and all(isinstance(check, dict) and check.get("passed") is True for check in verifier_checks),
            "detail": str(verifier.get("status", "")),
        },
        {
            "name": "record_policy_bounds",
            "passed": contract.get("requires_human_review") is True
            and contract.get("auto_apply") is False
            and contract.get("mutates_derived_self_model") is False
            and contract.get("writes_review_record_only") is True
            and contract.get("authority_changes_allowed") is False
            and _is_zero_cost(contract.get("cost_usd")),
            "detail": "review_record_only",
        },
        {
            "name": "outcome_evidence_present",
            "passed": bool(outcome_evidence_refs),
            "detail": str(len(outcome_evidence_refs)),
        },
        {
            "name": "outcome_evidence_structural",
            "passed": _valid_evidence_refs(
                outcome_evidence_refs,
                allowed_prefixes=_ALLOWED_OUTCOME_EVIDENCE_PREFIXES,
            ),
            "detail": ",".join(sorted(outcome_prefixes)),
        },
        {
            "name": "reviewer_present",
            "passed": bool(reviewer.strip()),
            "detail": "provided" if reviewer.strip() else "",
        },
        {
            "name": "no_authority_change",
            "passed": True,
            "detail": "acceptance_record_only",
        },
    ]


def _acceptance_status(checks: list[dict[str, Any]], *, apply: bool) -> str:
    failed = [check for check in checks if not check.get("passed")]
    if failed:
        return "blocked"
    return "accepted" if apply else "preview"


def _acceptance_or_raise(record_path: Path, checks: list[dict[str, Any]]) -> None:
    failed = [str(check["name"]) for check in checks if not check.get("passed")]
    if failed:
        joined = ", ".join(failed)
        raise SelfModelUpdateError(f"Self-model update record '{record_path}' failed acceptance gate: {joined}.")


def accept_self_model_update_record(
    record_path: Path,
    *,
    expert_name: str,
    outcome_evidence_refs: list[str],
    reviewer: str,
    apply: bool = False,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Preview or write an acceptance artifact for a recorded self-model update."""
    record_path = Path(record_path)
    record = _load_update_record(record_path)
    evidence_refs = [str(ref) for ref in outcome_evidence_refs]
    checks = _acceptance_checks(
        record,
        expert_name=expert_name,
        outcome_evidence_refs=evidence_refs,
        reviewer=reviewer,
    )
    _acceptance_or_raise(record_path, checks)
    proposed_update = _dict_or_empty(record.get("proposed_update"))
    acceptance = {
        "schema_version": SELF_MODEL_UPDATE_ACCEPTANCE_SCHEMA_VERSION,
        "kind": SELF_MODEL_UPDATE_ACCEPTANCE_KIND,
        "contract": _acceptance_contract(apply=apply),
        "expert_name": expert_name,
        "proposal_id": str(record.get("proposal_id", "")),
        "proposal_type": str(record.get("proposal_type", "")),
        "target": str(record.get("target", "")),
        "applied": apply,
        "status": _acceptance_status(checks, apply=apply),
        "accepted_update": {
            "record_path": str(record_path),
            "update_kind": str(proposed_update.get("update_kind", "")),
            "target_path": str(proposed_update.get("target_path", "")),
            "title": str(proposed_update.get("title", "")),
            "expected_effect": str(proposed_update.get("expected_effect", "")),
        },
        "policy_gate": {
            "status": "passed",
            "checks": checks,
        },
        "review": {
            "reviewer": reviewer,
            "outcome_evidence_refs": evidence_refs,
        },
        "generated_at": _utc_now().isoformat(),
    }
    path = _acceptance_path(acceptance, output_dir=output_dir)
    if apply:
        acceptance["artifact_path"] = str(path)
        acceptance["actions"] = [
            {"action": "write_self_model_update_acceptance", "status": "written", "path": str(path)}
        ]
        atomic_write_json(path, acceptance, fsync=True)
    else:
        acceptance["actions"] = [
            {"action": "write_self_model_update_acceptance", "status": "preview", "would_write": str(path.parent)}
        ]
    return acceptance


def _load_acceptance_records(root: Path, expert_name: str, *, limit: int) -> list[dict[str, Any]]:
    expert_dir = root / _safe_fragment(expert_name)
    if not expert_dir.is_dir() or limit <= 0:
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(expert_dir.glob("self_model_update_acceptance_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("schema_version") != SELF_MODEL_UPDATE_ACCEPTANCE_SCHEMA_VERSION:
            continue
        if payload.get("kind") != SELF_MODEL_UPDATE_ACCEPTANCE_KIND:
            continue
        if payload.get("status") != "accepted" or payload.get("applied") is not True:
            continue
        if str(payload.get("expert_name", "")) != expert_name:
            continue
        payload = dict(payload)
        payload.setdefault("artifact_path", str(path))
        records.append(payload)
        if len(records) >= limit:
            break
    return records


def build_self_model_update_context(
    expert_name: str,
    *,
    limit: int = 3,
    acceptance_dir: Path | None = None,
) -> dict[str, Any]:
    """Return a compact read-only context block for accepted self-model updates."""
    root = acceptance_dir or default_self_model_update_acceptance_dir()
    records = _load_acceptance_records(root, expert_name, limit=max(0, limit))
    return {
        "schema_version": SELF_MODEL_UPDATE_CONTEXT_SCHEMA_VERSION,
        "kind": SELF_MODEL_UPDATE_CONTEXT_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "derived_view": True,
            "mutates_derived_self_model": False,
            "authority_changes_allowed": False,
        },
        "expert_name": expert_name,
        "accepted_record_count": len(records),
        "accepted_records": [
            {
                "proposal_id": str(record.get("proposal_id", "")),
                "proposal_type": str(record.get("proposal_type", "")),
                "target": str(record.get("target", "")),
                "update_kind": str(_dict_or_empty(record.get("accepted_update")).get("update_kind", "")),
                "artifact_path": str(record.get("artifact_path", "")),
                "outcome_evidence_refs": [
                    str(ref) for ref in _dict_or_empty(record.get("review")).get("outcome_evidence_refs", []) or []
                ],
            }
            for record in records
        ],
    }


__all__ = [
    "SELF_MODEL_UPDATE_ACCEPTANCE_KIND",
    "SELF_MODEL_UPDATE_ACCEPTANCE_SCHEMA_VERSION",
    "SELF_MODEL_UPDATE_CONTEXT_KIND",
    "SELF_MODEL_UPDATE_CONTEXT_SCHEMA_VERSION",
    "SELF_MODEL_UPDATE_KIND",
    "SELF_MODEL_UPDATE_SCHEMA_VERSION",
    "SelfModelUpdateError",
    "accept_self_model_update_record",
    "build_self_model_update_context",
    "default_self_model_update_acceptance_dir",
    "default_self_model_update_dir",
    "propose_self_model_update",
]
