"""Read-only, content-free projections over durable investigation runs.

These builders are the Bridge 3/4 observation seam. They never mutate a run,
never return artifact bodies, never include local paths, and never imply
semantic acceptance. MCP tools wrap them later; this module is the contract.
"""

from __future__ import annotations

from typing import Any

from deepr import __version__ as DEEPR_VERSION
from deepr.experts.investigation.models import (
    CHARTER_KIND,
    CHARTER_SCHEMA_VERSION,
    CHECK_KIND,
    CHECK_SCHEMA_VERSION,
    DISCUSSION_KIND,
    DISCUSSION_SCHEMA_VERSION,
    EVENT_KIND,
    EVENT_SCHEMA_VERSION,
    INPUT_BUNDLE_KIND,
    INPUT_BUNDLE_SCHEMA_VERSION,
    LEARNING_MANIFEST_KIND,
    LEARNING_MANIFEST_SCHEMA_VERSION,
    PLAN_KIND,
    PLAN_SCHEMA_VERSION,
    POSITION_KIND,
    POSITION_SCHEMA_VERSION,
    RESULT_KIND,
    RESULT_SCHEMA_VERSION,
    RUN_KIND,
    RUN_SCHEMA_VERSION,
    TERMINAL_STATES,
    InvestigationBounds,
    InvestigationContractError,
    Phase,
    remaining_capacity,
    sha256_json,
    validate_sha256,
)
from deepr.experts.investigation.store import (
    InvestigationStorageError,
    InvestigationStore,
)

CAPABILITY_SNAPSHOT_SCHEMA_VERSION = "deepr-investigation-capability-snapshot-v1"
CAPABILITY_SNAPSHOT_KIND = "deepr.expert.investigation_capability_snapshot"
CONTROL_EVIDENCE_SCHEMA_VERSION = "deepr-investigation-control-evidence-v1"
CONTROL_EVIDENCE_KIND = "deepr.expert.investigation_control_evidence"
STATUS_PROJECTION_SCHEMA_VERSION = "deepr-investigation-status-projection-v1"
STATUS_PROJECTION_KIND = "deepr.expert.investigation_status_projection"
EVENT_PAGE_SCHEMA_VERSION = "deepr-investigation-event-page-v1"
EVENT_PAGE_KIND = "deepr.expert.investigation_event_page"
ARTIFACT_PAGE_SCHEMA_VERSION = "deepr-investigation-artifact-page-v1"
ARTIFACT_PAGE_KIND = "deepr.expert.investigation_artifact_page"
FOLLOW_UP_SCHEMA_VERSION = "deepr-investigation-follow-up-v1"
FOLLOW_UP_KIND = "deepr.expert.investigation_follow_up"
FORK_LINEAGE_SCHEMA_VERSION = "deepr-investigation-fork-lineage-v1"
FORK_LINEAGE_KIND = "deepr.expert.investigation_fork_lineage"

DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 50
ALLOWED_OBSERVE_VERBS = ("observe",)
DENIED_MUTATING_VERBS = (
    "start",
    "control",
    "steer",
    "learn",
    "spend",
    "read_artifact_content",
)
_ALLOWED_EVENT_DETAIL_KEYS = frozenset(
    {
        "plan_sha256",
        "operation",
        "expert_name",
        "expert_key",
        "model",
        "context_window_tokens",
        "prompt_bytes",
        "estimated_input_tokens",
        "generation_call",
        "error_type",
        "call_counted_conservatively",
        "input_tokens",
        "output_tokens",
        "provider_request_id",
        "stop_reason",
        "cost_usd",
        "search_queries",
        "page_fetches",
        "logical_key",
        "sha256",
        "artifact_bytes",
    }
)
_PATH_DETAIL_KEYS = frozenset({"path", "run_dir", "prompt", "messages", "text", "answer", "content", "credential"})


def _page_limit(limit: int | None) -> int:
    value = DEFAULT_PAGE_LIMIT if limit is None else limit
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_PAGE_LIMIT:
        raise InvestigationStorageError(f"limit must be an integer from 1 to {MAX_PAGE_LIMIT}")
    return value


def _non_negative_sequence(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvestigationStorageError("after_sequence must be an integer >= 0")
    return value


def _safe_after_name(value: str) -> str:
    if not isinstance(value, str):
        raise InvestigationStorageError("after_name must be a string")
    if len(value) > 200:
        raise InvestigationStorageError("after_name exceeds the projection bound")
    return value


def _lifecycle(state: dict[str, Any]) -> dict[str, Any]:
    status = str(state.get("state") or "")
    errors = state.get("errors") if isinstance(state.get("errors"), list) else []
    terminal_reason = None
    if status in {item.value for item in TERMINAL_STATES} and errors:
        last = errors[-1]
        if isinstance(last, dict):
            reason = last.get("error_type")
            if isinstance(reason, str) and reason.strip():
                terminal_reason = reason.strip()[:80]
    return {
        "state": status,
        "phase": str(state.get("phase") or ""),
        "attempt": 1,
        "terminal_reason": terminal_reason,
    }


def _ceilings(plan: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    bounds = InvestigationBounds.from_dict(plan["bounds"])
    usage = state.get("usage")
    if not isinstance(usage, dict):
        raise InvestigationStorageError("investigation usage state is invalid")
    remaining = remaining_capacity(bounds, usage)
    remaining["elapsed_seconds"] = max(
        0.0, float(bounds.max_elapsed_seconds) - float(usage.get("elapsed_seconds", 0.0) or 0.0)
    )
    observed = {
        "generation_calls": int(usage.get("generation_calls", 0)),
        "search_queries": int(usage.get("search_queries", 0)),
        "page_fetches": int(usage.get("page_fetches", 0)),
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "artifact_bytes": int(usage.get("artifact_bytes", 0)),
        "elapsed_seconds": float(usage.get("elapsed_seconds", 0.0) or 0.0),
        "cost_usd": float(usage.get("cost_usd", 0.0) or 0.0),
    }
    return observed, remaining


def _projected_errors(state: dict[str, Any]) -> list[dict[str, str]]:
    raw = state.get("errors")
    if not isinstance(raw, list):
        return []
    projected: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        phase = item.get("phase")
        error_type = item.get("error_type")
        if isinstance(phase, str) and isinstance(error_type, str):
            projected.append({"phase": phase, "error_type": error_type})
    return projected


def _project_event_detail(detail: Any) -> dict[str, Any]:
    if not isinstance(detail, dict):
        return {}
    projected: dict[str, Any] = {}
    for key, value in detail.items():
        if key in _PATH_DETAIL_KEYS or key not in _ALLOWED_EVENT_DETAIL_KEYS:
            continue
        if isinstance(value, str) and ("/" in value or "\\" in value):
            continue
        projected[key] = value
    return projected


def _project_event(event: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    if event.get("run_id") != run_id:
        raise InvestigationStorageError("event journal contains a cross-run record")
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "run_id": run_id,
        "sequence": int(event["sequence"]),
        "event_type": str(event.get("event_type") or ""),
        "phase": str(event.get("phase") or ""),
        "status": str(event.get("status") or ""),
        "detail": _project_event_detail(event.get("detail")),
        "created_at": str(event.get("created_at") or ""),
    }


def _artifact_entries(state: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = state.get("artifacts")
    if artifacts is None:
        return []
    if not isinstance(artifacts, dict):
        raise InvestigationStorageError("investigation artifact index is invalid")
    entries: list[dict[str, Any]] = []
    for name, reference in artifacts.items():
        if not isinstance(name, str) or not isinstance(reference, dict):
            raise InvestigationStorageError("investigation artifact index is invalid")
        digest = validate_sha256(reference.get("sha256"), field_name="artifact sha256")
        phase = str(reference.get("phase") or "")
        media_type = "text/plain" if phase == "sources" else "application/json"
        taint = "external_retrieval" if phase == "sources" else "run_derived"
        entries.append(
            {
                "name": name,
                "phase": phase,
                "key": str(reference.get("key") or ""),
                "sha256": digest,
                "bytes": int(reference.get("bytes") or 0),
                "media_type": media_type,
                "taint": taint,
            }
        )
    entries.sort(key=lambda item: item["name"].casefold())
    return entries


def build_capability_snapshot(plan: dict[str, Any]) -> dict[str, Any]:
    """Derive a run-start capability record. It cannot create authority."""
    capacity = plan["capacity"]
    snapshot = {
        "schema_version": CAPABILITY_SNAPSHOT_SCHEMA_VERSION,
        "kind": CAPABILITY_SNAPSHOT_KIND,
        "deepr": {
            "version": DEEPR_VERSION,
            "source_revision": None,
            "source_revision_status": "not_collected",
        },
        "investigation_schema_versions": {
            "input_bundle": INPUT_BUNDLE_SCHEMA_VERSION,
            "plan": PLAN_SCHEMA_VERSION,
            "run": RUN_SCHEMA_VERSION,
            "charter": CHARTER_SCHEMA_VERSION,
            "position": POSITION_SCHEMA_VERSION,
            "discussion": DISCUSSION_SCHEMA_VERSION,
            "check": CHECK_SCHEMA_VERSION,
            "result": RESULT_SCHEMA_VERSION,
            "learning_manifest": LEARNING_MANIFEST_SCHEMA_VERSION,
            "event": EVENT_SCHEMA_VERSION,
        },
        "investigation_kinds": {
            "input_bundle": INPUT_BUNDLE_KIND,
            "plan": PLAN_KIND,
            "run": RUN_KIND,
            "charter": CHARTER_KIND,
            "position": POSITION_KIND,
            "discussion": DISCUSSION_KIND,
            "check": CHECK_KIND,
            "result": RESULT_KIND,
            "learning_manifest": LEARNING_MANIFEST_KIND,
            "event": EVENT_KIND,
        },
        "capacity": {
            "class": capacity["class"],
            "model": capacity["model"],
            "review_model": capacity.get("review_model", capacity["model"]),
            "auth_mode": "owned_local",
            "fallback": capacity["fallback"],
        },
        "allowed_verbs": list(ALLOWED_OBSERVE_VERBS),
        "denied_verbs": list(DENIED_MUTATING_VERBS),
        "retrieval": {
            "max_queries_per_expert": int(plan["retrieval"]["max_queries_per_expert"]),
            "max_pages_per_expert": int(plan["retrieval"]["max_pages_per_expert"]),
        },
        "network_policy": {
            "public_web_retrieval": True,
            "metered_providers": False,
            "fallback": "none",
        },
        "roster": [
            {"name": expert["name"], "snapshot_sha256": expert["snapshot_sha256"]} for expert in plan["experts"]
        ],
        "parent_ceilings": InvestigationBounds.from_dict(plan["bounds"]).to_dict(),
        "configuration_hash": plan["plan_sha256"],
        "approval_posture": "local_explicit_confirmation",
        "creates_authority": False,
    }
    snapshot["snapshot_sha256"] = sha256_json(
        {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    )
    return snapshot


def build_control_evidence(
    plan: dict[str, Any],
    state: dict[str, Any],
    control: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    capability_snapshot_sha256: str,
) -> dict[str, Any]:
    """Join canonical identities into a generated audit projection."""
    event_head = events[-1]["sequence"] if events else 0
    evidence = {
        "schema_version": CONTROL_EVIDENCE_SCHEMA_VERSION,
        "kind": CONTROL_EVIDENCE_KIND,
        "run_id": plan["run_id"],
        "plan_sha256": plan["plan_sha256"],
        "capability_snapshot_sha256": capability_snapshot_sha256,
        "event_head_sequence": event_head,
        "artifact_manifest_sha256": sha256_json(_artifact_entries(state)),
        "control": {
            "requested": str(control.get("requested") or "run"),
            "revision": int(control.get("revision") or 0),
            "updated_at": str(control.get("updated_at") or ""),
        },
        "lifecycle": _lifecycle(state),
        "learning_disposition": {
            "mode": plan["learning"],
            "writes_expert_state": False,
            "human_reviewed": False,
            "truth_verified": False,
            "novelty_verified": False,
        },
        "verification_disposition": {
            "semantic_acceptance": False,
            "human_reviewed": False,
        },
        "projection_only": True,
        "semantic_acceptance": False,
        "canonical_store": False,
    }
    evidence["evidence_sha256"] = sha256_json(
        {key: value for key, value in evidence.items() if key != "evidence_sha256"}
    )
    return evidence


def _envelope(
    *,
    schema_version: str,
    kind: str,
    plan: dict[str, Any],
    state: dict[str, Any],
    snapshot: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    observed, remaining = _ceilings(plan, state)
    return {
        "schema_version": schema_version,
        "kind": kind,
        "projection_only": True,
        "semantic_acceptance": False,
        "mutates_run": False,
        "cost_usd": 0.0,
        "run_id": plan["run_id"],
        "plan_sha256": plan["plan_sha256"],
        "lifecycle": _lifecycle(state),
        "observed_ceilings": observed,
        "remaining_ceilings": remaining,
        "capability_snapshot_sha256": snapshot["snapshot_sha256"],
        "control_evidence_sha256": evidence["evidence_sha256"],
    }


def _load_projection_inputs(
    store: InvestigationStore, run_id: str
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
]:
    plan = store.load_plan(run_id)
    state = store.load_state(run_id)
    if state.get("run_id") != run_id or plan.get("run_id") != run_id:
        raise InvestigationStorageError("investigation identity mismatch")
    control = store.load_control(run_id)
    events = store.load_events(run_id)
    snapshot = build_capability_snapshot(plan)
    evidence = build_control_evidence(
        plan,
        state,
        control,
        events,
        capability_snapshot_sha256=snapshot["snapshot_sha256"],
    )
    return plan, state, control, events, snapshot, evidence


def project_status(store: InvestigationStore, run_id: str) -> dict[str, Any]:
    """Project lifecycle status for one run. Read-only."""
    plan, state, control, events, snapshot, evidence = _load_projection_inputs(store, run_id)
    payload = _envelope(
        schema_version=STATUS_PROJECTION_SCHEMA_VERSION,
        kind=STATUS_PROJECTION_KIND,
        plan=plan,
        state=state,
        snapshot=snapshot,
        evidence=evidence,
    )
    payload.update(
        {
            "control": {
                "requested": str(control.get("requested") or "run"),
                "revision": int(control.get("revision") or 0),
            },
            "event_cursor": len(events),
            "artifact_count": len(_artifact_entries(state)),
            "errors": _projected_errors(state),
            "capability_snapshot": snapshot,
            "control_evidence": evidence,
        }
    )
    return payload


def project_events(
    store: InvestigationStore,
    run_id: str,
    *,
    after_sequence: int = 0,
    limit: int | None = None,
) -> dict[str, Any]:
    """Project a content-free event page. Read-only."""
    page_limit = _page_limit(limit)
    cursor = _non_negative_sequence(after_sequence)
    plan, state, _control, events, snapshot, evidence = _load_projection_inputs(store, run_id)
    projected = [_project_event(event, run_id=run_id) for event in events if int(event["sequence"]) > cursor]
    page = projected[:page_limit]
    next_sequence = page[-1]["sequence"] if page else None
    payload = _envelope(
        schema_version=EVENT_PAGE_SCHEMA_VERSION,
        kind=EVENT_PAGE_KIND,
        plan=plan,
        state=state,
        snapshot=snapshot,
        evidence=evidence,
    )
    payload.update(
        {
            "after_sequence": cursor,
            "limit": page_limit,
            "count": len(page),
            "next_sequence": next_sequence,
            "complete": len(projected) <= page_limit,
            "events": page,
        }
    )
    return payload


def project_artifacts(
    store: InvestigationStore,
    run_id: str,
    *,
    after_name: str = "",
    limit: int | None = None,
) -> dict[str, Any]:
    """Project artifact metadata only. Read-only and content-free."""
    page_limit = _page_limit(limit)
    cursor = _safe_after_name(after_name)
    plan, state, _control, _events, snapshot, evidence = _load_projection_inputs(store, run_id)
    entries = _artifact_entries(state)
    if cursor:
        remaining = [item for item in entries if item["name"].casefold() > cursor.casefold()]
    else:
        remaining = entries
    page = remaining[:page_limit]
    next_name = page[-1]["name"] if page else None
    payload = _envelope(
        schema_version=ARTIFACT_PAGE_SCHEMA_VERSION,
        kind=ARTIFACT_PAGE_KIND,
        plan=plan,
        state=state,
        snapshot=snapshot,
        evidence=evidence,
    )
    payload.update(
        {
            "after_name": cursor,
            "limit": page_limit,
            "count": len(page),
            "next_name": next_name,
            "complete": len(remaining) <= page_limit,
            "read_content": False,
            "artifacts": page,
        }
    )
    return payload


def preview_follow_up(store: InvestigationStore, parent_run_id: str) -> dict[str, Any]:
    """Describe a later follow-up request without creating a run."""
    plan, state, _control, _events, snapshot, evidence = _load_projection_inputs(store, parent_run_id)
    if state["state"] not in {item.value for item in TERMINAL_STATES}:
        raise InvestigationStorageError("follow-up preview requires a terminal parent run")
    return {
        "schema_version": FOLLOW_UP_SCHEMA_VERSION,
        "kind": FOLLOW_UP_KIND,
        "projection_only": True,
        "semantic_acceptance": False,
        "implemented": False,
        "creates_run": False,
        "mutates_parent": False,
        "requires_fresh_capacity": True,
        "parent_run_id": parent_run_id,
        "parent_plan_sha256": plan["plan_sha256"],
        "parent_lifecycle": _lifecycle(state),
        "capability_snapshot_sha256": snapshot["snapshot_sha256"],
        "control_evidence_sha256": evidence["evidence_sha256"],
        "request": "run.follow_up",
    }


def preview_fork(store: InvestigationStore, parent_run_id: str, *, phase: str) -> dict[str, Any]:
    """Describe a checkpoint fork without creating a run or editing the parent."""
    try:
        named_phase = Phase(phase)
    except ValueError as exc:
        raise InvestigationContractError("fork phase must be a published investigation phase") from exc
    plan, state, _control, _events, snapshot, evidence = _load_projection_inputs(store, parent_run_id)
    return {
        "schema_version": FORK_LINEAGE_SCHEMA_VERSION,
        "kind": FORK_LINEAGE_KIND,
        "projection_only": True,
        "semantic_acceptance": False,
        "implemented": False,
        "creates_run": False,
        "mutates_parent": False,
        "requires_fresh_capacity": True,
        "parent_run_id": parent_run_id,
        "parent_plan_sha256": plan["plan_sha256"],
        "parent_phase": named_phase.value,
        "parent_lifecycle": _lifecycle(state),
        "capability_snapshot_sha256": snapshot["snapshot_sha256"],
        "control_evidence_sha256": evidence["evidence_sha256"],
        "request": "run.fork",
    }


__all__ = [
    "ALLOWED_OBSERVE_VERBS",
    "ARTIFACT_PAGE_KIND",
    "ARTIFACT_PAGE_SCHEMA_VERSION",
    "CAPABILITY_SNAPSHOT_KIND",
    "CAPABILITY_SNAPSHOT_SCHEMA_VERSION",
    "CONTROL_EVIDENCE_KIND",
    "CONTROL_EVIDENCE_SCHEMA_VERSION",
    "DEFAULT_PAGE_LIMIT",
    "DENIED_MUTATING_VERBS",
    "EVENT_PAGE_KIND",
    "EVENT_PAGE_SCHEMA_VERSION",
    "FOLLOW_UP_KIND",
    "FOLLOW_UP_SCHEMA_VERSION",
    "FORK_LINEAGE_KIND",
    "FORK_LINEAGE_SCHEMA_VERSION",
    "MAX_PAGE_LIMIT",
    "STATUS_PROJECTION_KIND",
    "STATUS_PROJECTION_SCHEMA_VERSION",
    "build_capability_snapshot",
    "build_control_evidence",
    "preview_follow_up",
    "preview_fork",
    "project_artifacts",
    "project_events",
    "project_status",
]
