"""Explicit bulk apply for staged investigation learning envelopes."""

from __future__ import annotations

from contextlib import ExitStack
from datetime import UTC, datetime
from typing import Any

from deepr.experts.beliefs import BeliefStore
from deepr.experts.graph_commit_apply import apply_graph_commit_envelope
from deepr.experts.graph_commit_provenance import verify_graph_commit_provenance
from deepr.experts.investigation.store import InvestigationStore
from deepr.experts.knowledge_freshness import advance_knowledge_freshness
from deepr.experts.loop_lock import expert_verb_lock
from deepr.experts.metacognition import MetaCognitionTracker
from deepr.experts.profile import ExpertStore


class InvestigationLearningApplyError(RuntimeError):
    """Raised when staged learning cannot be applied safely."""


def _artifact_reference(
    state: dict[str, Any],
    *,
    path: str,
    prefix: str,
) -> dict[str, Any]:
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        raise InvestigationLearningApplyError("investigation artifact index is invalid")
    matches = [
        reference
        for key, reference in artifacts.items()
        if key.startswith(prefix) and isinstance(reference, dict) and reference.get("path") == path
    ]
    if len(matches) != 1:
        raise InvestigationLearningApplyError("staged learning envelope is not uniquely indexed")
    return matches[0]


def _selected_names(plan: dict[str, Any], requested: tuple[str, ...]) -> list[str]:
    available = [str(expert.get("name", "") or "") for expert in plan.get("experts", []) if isinstance(expert, dict)]
    if not requested:
        return available
    by_key = {name.casefold(): name for name in available}
    selected: list[str] = []
    for raw_name in requested:
        name = by_key.get(raw_name.strip().casefold())
        if name is None:
            raise InvestigationLearningApplyError(f"expert is not in the investigation plan: {raw_name}")
        if name not in selected:
            selected.append(name)
    return selected


def _manifest_entries(manifest: dict[str, Any], selected_names: list[str]) -> list[dict[str, Any]]:
    by_name = {
        str(entry.get("expert_name", "") or ""): entry
        for entry in manifest.get("entries", []) or []
        if isinstance(entry, dict)
    }
    missing = [name for name in selected_names if name not in by_name]
    if missing:
        raise InvestigationLearningApplyError("learning manifest omits selected expert state")
    return [by_name[name] for name in selected_names]


def _entry_envelopes(
    store: InvestigationStore,
    run_id: str,
    state: dict[str, Any],
    entry: dict[str, Any],
    *,
    facts: bool,
    perspectives: bool,
) -> list[tuple[str, dict[str, Any], str]]:
    envelopes: list[tuple[str, dict[str, Any], str]] = []
    fields: list[tuple[str, str, str]] = []
    if facts:
        fields.append(("facts", "graph_commit_envelope_artifact", "learning:envelope:"))
    if perspectives:
        fields.append(
            (
                "perspectives",
                "perspective_graph_commit_envelope_artifact",
                "learning:perspective-envelope:",
            )
        )
    for channel, field, prefix in fields:
        path = str(entry.get(field, "") or "")
        if not path:
            continue
        reference = _artifact_reference(state, path=path, prefix=prefix)
        envelopes.append((channel, store.read_artifact(run_id, reference), path))
    return envelopes


def _blocked_result(run_id: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": "deepr-investigation-learning-apply-v1",
        "kind": "deepr.expert.investigation_learning_apply",
        "run_id": run_id,
        "contract": {
            "model_calls": False,
            "cost_usd": 0.0,
            "human_reviewed": False,
            "operator_confirmed_apply": False,
        },
        "summary": {
            "status": "blocked",
            "dry_run": True,
            "planned_write_count": 0,
            "applied_write_count": 0,
            "failure_reasons": [reason],
        },
        "results": [],
    }


def _acquire_learning_locks(locks: ExitStack, selected_names: list[str]) -> str | None:
    """Acquire the whole selected roster before any preflight or write."""
    for name in sorted(selected_names, key=str.casefold):
        acquired = locks.enter_context(expert_verb_lock(name, "investigation-learning-apply"))
        if not acquired:
            return f"expert_learning_apply_locked:{name}"
    return None


def _is_producer_empty_no_op(envelope: dict[str, Any], failures: list[str]) -> bool:
    """Recognize a provenance-verified semantic no-op, never an empty ready write."""
    envelope_status = str((envelope.get("summary", {}) or {}).get("status", "") or "")
    return (
        envelope_status in {"blocked", "empty"}
        and not envelope.get("operations")
        and set(failures) == {"empty_operations", "envelope_not_ready_for_commit"}
    )


def _preflight_entry(
    *,
    run_store: InvestigationStore,
    run_id: str,
    state: dict[str, Any],
    entry: dict[str, Any],
    facts: bool,
    perspectives: bool,
    profile_store: ExpertStore,
) -> tuple[list[dict[str, Any]], str | None]:
    """Validate one expert and return its fully preflighted envelopes."""
    expert_name = str(entry["expert_name"])
    profile = profile_store.load(expert_name)
    expert_root = profile_store.find_existing_dir(expert_name)
    if profile is None or expert_root is None:
        return [], f"expert_not_found:{expert_name}"
    belief_store = BeliefStore(expert_name)
    tracker = MetaCognitionTracker(expert_name)
    prepared: list[dict[str, Any]] = []
    for channel, envelope, relative_path in _entry_envelopes(
        run_store,
        run_id,
        state,
        entry,
        facts=facts,
        perspectives=perspectives,
    ):
        envelope_path = run_store.run_dir(run_id) / relative_path
        provenance = verify_graph_commit_provenance(
            expert_root,
            envelope_path=envelope_path,
            envelope=envelope,
            expected_expert=expert_name,
        )
        if not provenance.valid:
            reason = (provenance.failure_reasons or ("untrusted_graph_commit_provenance",))[0]
            return [], f"{expert_name}:{channel}:{reason}"
        preview = apply_graph_commit_envelope(envelope, belief_store, gap_tracker=tracker, dry_run=True)
        if preview.get("summary", {}).get("status") == "blocked":
            failures = preview.get("summary", {}).get("failure_reasons", []) or ["graph_commit_blocked"]
            if not _is_producer_empty_no_op(envelope, failures):
                return [], f"{expert_name}:{channel}:{failures[0]}"
            preview = _no_op_result(preview, dry_run=True)
        prepared.append(
            {
                "expert_name": expert_name,
                "channel": channel,
                "envelope": envelope,
                "belief_store": belief_store,
                "tracker": tracker,
                "profile": profile,
                "preview": preview,
                "no_op": preview.get("summary", {}).get("status") == "empty",
            }
        )
    return prepared, None


def _preflight_selected_entries(
    *,
    run_store: InvestigationStore,
    run_id: str,
    state: dict[str, Any],
    entries: list[dict[str, Any]],
    facts: bool,
    perspectives: bool,
    profile_store: ExpertStore,
) -> tuple[list[dict[str, Any]], str | None]:
    """Preflight the complete selected set before any apply operation."""
    prepared: list[dict[str, Any]] = []
    for entry in entries:
        entry_prepared, failure = _preflight_entry(
            run_store=run_store,
            run_id=run_id,
            state=state,
            entry=entry,
            facts=facts,
            perspectives=perspectives,
            profile_store=profile_store,
        )
        if failure:
            return [], failure
        prepared.extend(entry_prepared)
    return prepared, None


def _apply_prepared(
    prepared: list[dict[str, Any]],
    *,
    dry_run: bool,
    profile_store: ExpertStore,
) -> list[dict[str, Any]]:
    """Apply a completely preflighted set while roster locks are held."""
    results: list[dict[str, Any]] = []
    for item in prepared:
        result = item["preview"]
        if not dry_run and item["no_op"]:
            result = _no_op_result(result, dry_run=False)
        elif not dry_run:
            result = apply_graph_commit_envelope(
                item["envelope"],
                item["belief_store"],
                gap_tracker=item["tracker"],
                dry_run=False,
            )
            factual_write = item["channel"] == "facts" and result.get("contract", {}).get("writes_graph") is True
            if factual_write:
                advance_knowledge_freshness(item["profile"], datetime.now(UTC))
                profile_store.save(item["profile"])
        results.append({"expert_name": item["expert_name"], "channel": item["channel"], "result": result})
    return results


def _no_op_result(preview: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    """Reclassify a producer-blocked empty envelope without weakening the writer."""
    contract = preview.get("contract", {})
    summary = preview.get("summary", {})
    return {
        **preview,
        "contract": {
            **contract,
            "read_only": True,
            "writes_graph": False,
            "writes_expert_state": False,
        },
        "summary": {
            **summary,
            "status": "empty",
            "dry_run": dry_run,
            "failure_reasons": [],
            "no_op_reasons": ["producer_blocked_or_empty"],
        },
    }


def _apply_status(*, prepared: list[dict[str, Any]], dry_run: bool, applied: int, already: int) -> str:
    actionable = [item for item in prepared if not item["no_op"]]
    if not actionable:
        return "empty"
    if dry_run:
        return "dry_run"
    if applied == 0 and already > 0:
        return "already_applied"
    return "applied"


def apply_investigation_learning(
    run_id: str,
    *,
    dry_run: bool,
    expert_names: tuple[str, ...] = (),
    facts: bool = True,
    perspectives: bool = True,
    store: InvestigationStore | None = None,
) -> dict[str, Any]:
    """Preflight every selected envelope, then apply under expert locks."""
    if not facts and not perspectives:
        raise InvestigationLearningApplyError("select facts, perspectives, or both")
    run_store = store or InvestigationStore()
    plan = run_store.load_plan(run_id)
    state = run_store.load_state(run_id)
    if state.get("state") != "completed":
        return _blocked_result(run_id, "investigation_run_not_completed")
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get("learning:manifest"), dict):
        return _blocked_result(run_id, "learning_manifest_missing")
    manifest = run_store.read_artifact(run_id, artifacts["learning:manifest"])
    selected_names = _selected_names(plan, expert_names)
    entries = _manifest_entries(manifest, selected_names)
    profile_store = ExpertStore()

    with ExitStack() as locks:
        failure = _acquire_learning_locks(locks, selected_names)
        if failure:
            return _blocked_result(run_id, failure)
        prepared, failure = _preflight_selected_entries(
            run_store=run_store,
            run_id=run_id,
            state=state,
            entries=entries,
            facts=facts,
            perspectives=perspectives,
            profile_store=profile_store,
        )
        if failure:
            return _blocked_result(run_id, failure)
        results = _apply_prepared(prepared, dry_run=dry_run, profile_store=profile_store)

    planned = sum(int(item["preview"].get("summary", {}).get("planned_write_count", 0) or 0) for item in prepared)
    applied = sum(int(item["result"].get("summary", {}).get("applied_write_count", 0) or 0) for item in results)
    already = sum(int(item["result"].get("summary", {}).get("already_applied_count", 0) or 0) for item in results)
    no_op_envelopes = sum(1 for item in prepared if item["no_op"])
    status = _apply_status(prepared=prepared, dry_run=dry_run, applied=applied, already=already)
    return {
        "schema_version": "deepr-investigation-learning-apply-v1",
        "kind": "deepr.expert.investigation_learning_apply",
        "run_id": run_id,
        "contract": {
            "model_calls": False,
            "cost_usd": 0.0,
            "human_reviewed": False,
            "operator_confirmed_apply": not dry_run,
            "facts_require_source_verifier": True,
            "perspectives_are_non_factual": True,
            "perspective_truth_or_novelty_verified": False,
        },
        "summary": {
            "status": status,
            "dry_run": dry_run,
            "expert_count": len(selected_names),
            "envelope_count": len(results),
            "no_op_envelope_count": no_op_envelopes,
            "planned_write_count": planned,
            "applied_write_count": applied,
            "already_applied_count": already,
            "failure_reasons": [],
        },
        "results": results,
    }


__all__ = [
    "InvestigationLearningApplyError",
    "apply_investigation_learning",
]
