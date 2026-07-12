"""Support helpers for the ``expert sync`` CLI command.

This module keeps the command registration file under the file-size ratchet
while preserving one shared implementation for capacity waits, loop records,
context builders, and overlap locking.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

from deepr.backends.local_capacity import LocalCapacityObservation, LocalCapacityState
from deepr.cli.colors import console, print_error, print_warning
from deepr.evals.recall_quality import (
    LEXICAL_ROUTE as RECALL_LEXICAL_ROUTE,
)
from deepr.evals.recall_quality import (
    RECALL_EVAL_REPORT_SCHEMA_VERSION,
    validate_recall_preference_evidence,
)
from deepr.evals.recall_quality import (
    VECTOR_ROUTE as RECALL_VECTOR_ROUTE,
)
from deepr.experts.recall_preference import belief_index_coverage, validate_preference_current_index

SYNC_CAPACITY_GATE_KIND = "deepr.expert.sync_capacity_gate"
SYNC_CAPACITY_GATE_SCHEMA_VERSION = "deepr-sync-capacity-gate-v1"


def _retry_flag(enabled: bool, flag: str) -> list[str]:
    return [flag] if enabled else []


def _retry_option(value: str | None, flag: str) -> list[str]:
    return [flag, value] if value else []


def _retry_backend_argv(*, local: bool, api: bool, plan: str | None) -> list[str]:
    if local:
        return ["--local"]
    if api:
        return ["--api"]
    if plan:
        return ["--plan", plan]
    return []


def _sync_retry_command_argv(
    *,
    name: str,
    budget: float,
    sync_all: bool,
    local: bool,
    api: bool,
    plan: str | None,
    plan_model: str | None,
    check_grounding: bool,
    compile_claims: bool,
    stage_compiled_claims: bool,
    apply_compiled_claims: bool,
    recall_embedding_model: str | None,
    recall_preference_report: str | None,
    checker_plan: str | None,
    checker_plan_model: str | None,
    second_checker_plan: str | None,
    second_checker_plan_model: str | None,
    fresh_context: bool,
    deep_context: bool,
    jitter: float,
    yes: bool,
    json_output: bool,
) -> list[str]:
    """Rebuild one scheduled sync request as argument-safe argv."""
    argv = ["deepr", "expert", "sync", name, "--scheduled", "--budget", f"{budget:g}"]
    argv += _retry_flag(sync_all, "--all")
    argv += _retry_backend_argv(local=local, api=api, plan=plan)
    argv += _retry_option(plan_model, "--plan-model")
    argv += _retry_flag(check_grounding, "--check-grounding")
    argv += _retry_flag(compile_claims, "--compile-claims")
    argv += _retry_flag(stage_compiled_claims, "--stage-compiled-claims")
    argv += _retry_flag(apply_compiled_claims, "--apply-compiled-claims")
    argv += _retry_option(recall_embedding_model, "--recall-embedding-model")
    argv += _retry_option(recall_preference_report, "--recall-preference-report")
    argv += _retry_option(checker_plan, "--checker-plan")
    argv += _retry_option(checker_plan_model, "--checker-plan-model")
    argv += _retry_option(second_checker_plan, "--second-checker-plan")
    argv += _retry_option(second_checker_plan_model, "--second-checker-plan-model")
    argv += _retry_flag(fresh_context, "--fresh-context")
    argv += _retry_flag(deep_context, "--deep-context")
    argv += _retry_option(f"{jitter:g}" if jitter > 0 else None, "--jitter")
    argv += _retry_flag(yes, "--yes")
    argv += _retry_flag(json_output, "--json")
    return argv


def _self_model_context(expert_name: str, *, profile: Any | None = None) -> dict[str, Any]:
    from deepr.experts.self_model import (
        build_expert_self_model_context,
        build_expert_self_model_context_from_profile,
    )

    if profile is not None:
        return build_expert_self_model_context_from_profile(profile, focus_limit=3)
    return build_expert_self_model_context(expert_name, focus_limit=3)


def _self_model_run_context(expert_name: str, *, profile: Any | None = None) -> dict[str, Any]:
    self_model = _self_model_context(expert_name, profile=profile)
    context = {"self_model": self_model} if self_model else {}
    from deepr.experts.self_model_updates import build_self_model_update_context

    update_context = build_self_model_update_context(expert_name)
    if update_context.get("accepted_record_count"):
        context["self_model_updates"] = update_context
    return context


def _source_note_run_context(result: Any) -> dict[str, Any]:
    artifacts = []
    for outcome in list(getattr(result, "outcomes", []) or []):
        source_note_artifact = str(getattr(outcome, "source_note_artifact", "") or "")
        if not source_note_artifact:
            continue
        artifact = {
            "topic": str(getattr(outcome, "topic", "") or ""),
            "status": str(getattr(outcome, "status", "") or ""),
            "source_note_artifact": source_note_artifact,
            "source_pack_artifact": str(getattr(outcome, "source_pack_artifact", "") or ""),
            "source_pack_manifest_artifact": str(getattr(outcome, "source_pack_manifest_artifact", "") or ""),
        }
        claim_extraction_artifact = str(getattr(outcome, "claim_extraction_artifact", "") or "")
        if claim_extraction_artifact:
            artifact["claim_extraction_artifact"] = claim_extraction_artifact
        claim_verification_artifact = str(getattr(outcome, "claim_verification_artifact", "") or "")
        if claim_verification_artifact:
            artifact["claim_verification_artifact"] = claim_verification_artifact
        graph_commit_envelope_artifact = str(getattr(outcome, "graph_commit_envelope_artifact", "") or "")
        if graph_commit_envelope_artifact:
            artifact["graph_commit_envelope_artifact"] = graph_commit_envelope_artifact
        graph_commit_apply_artifact = str(getattr(outcome, "graph_commit_apply_artifact", "") or "")
        if graph_commit_apply_artifact:
            artifact["graph_commit_apply_artifact"] = graph_commit_apply_artifact
            artifact["graph_commit_apply_status"] = str(getattr(outcome, "graph_commit_apply_status", "") or "")
        artifacts.append(artifact)
    if not artifacts:
        return {}
    return {
        "source_notes": {
            "schema_version": "deepr-source-note-v1",
            "kind": "deepr.expert.source_notes",
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
        }
    }


def _sync_run_context(expert_name: str, result: Any | None = None, *, profile: Any | None = None) -> dict[str, Any]:
    context = _self_model_run_context(expert_name, profile=profile)
    if result is not None:
        context.update(_source_note_run_context(result))
    return context


def _sync_context_mode(*, fresh_context: bool, deep_context: bool) -> str:
    if deep_context:
        return "deep"
    if fresh_context:
        return "fresh"
    return "none"


def _build_sync_capacity_payload(
    expert_name: str,
    *,
    context_mode: str,
    scheduled: bool,
    status: str,
    detail: str,
    profile: Any | None = None,
    local_capacity: LocalCapacityObservation | None = None,
    command_argv: list[str] | None = None,
) -> dict[str, Any]:
    from deepr.backends.admission import TASK_CLASS_SYNC
    from deepr.backends.capacity_actions import (
        CapacityJobContext,
        build_capacity_next_actions,
        build_capacity_next_payload,
    )

    job_context = CapacityJobContext(
        task_class=TASK_CLASS_SYNC,
        expert_name=expert_name,
        context_mode=context_mode,
        scheduled=scheduled,
    )
    if local_capacity is not None and local_capacity.state == LocalCapacityState.BUSY:
        from deepr.backends.capacity_actions import CapacityNextAction

        actions = [
            CapacityNextAction(
                1,
                "wait",
                "Local GPU capacity is busy",
                "The selected local GPU step is deferred; no plan or metered fallback was dispatched.",
            )
        ]
    else:
        actions = build_capacity_next_actions(
            task_class=TASK_CLASS_SYNC,
            job_context=job_context,
            local_capacity=local_capacity,
        )
    payload: dict[str, Any] = {
        "schema_version": SYNC_CAPACITY_GATE_SCHEMA_VERSION,
        "kind": SYNC_CAPACITY_GATE_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "stability": "experimental",
            "compatibility": {
                "additive_fields": True,
                "breaking_changes_require_new_schema_version": True,
                "deprecation_policy": "Fields in this v1 payload are additive within v1; removals use a new schema.",
            },
        },
        "status": status,
        "expert_name": expert_name,
        "detail": detail,
        "capacity_next": build_capacity_next_payload(
            job_context,
            actions,
            local_capacity=local_capacity,
        ),
    }
    if local_capacity is not None:
        payload["local_capacity"] = local_capacity.to_dict()
    if command_argv is not None:
        payload["requested_operation"] = {"command_argv": list(command_argv)}
        if payload["capacity_next"]["actions"]:
            payload["capacity_next"]["actions"][0]["command_argv"] = [list(command_argv)]
    self_model = _self_model_context(expert_name, profile=profile)
    if self_model:
        payload["self_model"] = self_model
    return payload


def _print_capacity_payload(payload: dict[str, Any]) -> None:
    for action in payload["capacity_next"]["actions"]:
        console.print(f"  [{action['rank']}] {action['status']}: {action['title']}")
        if action.get("detail"):
            console.print(f"      [dim]{action['detail']}[/dim]")
        if action.get("command"):
            console.print(f"      [dim]{action['command']}[/dim]")


def _emit_scheduled_capacity_wait(
    expert_name: str,
    *,
    context_mode: str,
    json_output: bool,
    detail: str,
    profile: Any | None = None,
    local_capacity: LocalCapacityObservation | None = None,
    budget_limit: float | None = None,
    command_argv: list[str] | None = None,
    capacity_source: str = "owned/prepaid",
    backend_profile_id: str = "",
) -> None:
    payload = _build_sync_capacity_payload(
        expert_name,
        context_mode=context_mode,
        scheduled=True,
        status="waiting_for_capacity",
        detail=detail,
        profile=profile,
        local_capacity=local_capacity,
        command_argv=command_argv,
    )
    if local_capacity is not None and local_capacity.state == LocalCapacityState.BUSY:
        from deepr.experts.scheduled_local_capacity import record_scheduled_local_capacity_wait

        if command_argv is None:
            raise ValueError("local-capacity waits require command_argv")
        wait = record_scheduled_local_capacity_wait(
            expert_name=expert_name,
            loop_type="sync",
            goal=f"Sync due subscriptions for {expert_name}",
            observation=local_capacity,
            command_argv=command_argv,
            budget_limit=budget_limit,
            base_run_context=_self_model_run_context(expert_name, profile=profile),
            capacity_source=capacity_source,
            backend_profile_id=backend_profile_id,
        )
        payload.update(wait.to_dict())
    else:
        from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

        next_action = dict(payload["capacity_next"]["actions"][0]) if payload["capacity_next"]["actions"] else {}
        run_context = _self_model_run_context(expert_name, profile=profile)
        if command_argv is not None:
            requested_operation = {
                "command_argv": list(command_argv),
                "capacity_source": capacity_source,
                "backend_profile_id": backend_profile_id,
            }
            next_action["command_argv"] = [list(command_argv)]
            run_context["requested_operation"] = requested_operation
            payload["requested_operation"] = requested_operation
        loop_run = record_loop_run(
            expert_name=expert_name,
            loop_type="sync",
            goal=f"Sync due subscriptions for {expert_name}",
            trigger="scheduled",
            status=LoopRunStatus.WAITING,
            stop_reason=LoopStopReason.CAPACITY_UNAVAILABLE,
            next_action=next_action,
            run_context=run_context,
            capacity_source=capacity_source,
            backend_profile_id=backend_profile_id,
        )
        payload["loop_run"] = loop_run.to_dict()
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    print_warning("Scheduled sync is waiting for cheap capacity.")
    console.print(f"[dim]{detail}.[/dim]")
    _print_capacity_payload(payload)


def _emit_capacity_block(
    expert_name: str,
    *,
    context_mode: str,
    json_output: bool,
    detail: str,
    profile: Any | None = None,
) -> None:
    payload = _build_sync_capacity_payload(
        expert_name,
        context_mode=context_mode,
        scheduled=False,
        status="capacity_blocked",
        detail=detail,
        profile=profile,
    )
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    print_error(f"{detail}. Use --local or admit a local model first.")
    _print_capacity_payload(payload)


def _record_completed_sync_loop(
    expert_name: str,
    result: Any,
    *,
    budget: float,
    scheduled: bool,
    sync_all: bool,
    capacity_source: str,
    profile: Any | None = None,
    run_id: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> Any:
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    if profile is not None and getattr(result, "knowledge_observed_at", None) is not None:
        from deepr.experts.profile import ExpertStore

        ExpertStore().save(profile)

    outcomes = list(getattr(result, "outcomes", []) or [])
    failed = [o for o in outcomes if getattr(o, "status", "") == "failed"]
    accepted = sum(
        max(int(getattr(o, "absorbed", 0) or 0), 0) + max(int(getattr(o, "flagged", 0) or 0), 0) for o in outcomes
    )
    if failed:
        status = LoopRunStatus.FAILED
        stop_reason = LoopStopReason.TOOL_FAILURE
        next_action = {
            "status": "inspect",
            "title": "Inspect failed sync outcomes",
            "detail": f"{len(failed)} topic(s) failed during sync.",
            "command": f'deepr expert sync "{expert_name}" --dry-run',
        }
    else:
        status = LoopRunStatus.COMPLETED
        stop_reason = LoopStopReason.VERIFIER_PASSED if accepted else LoopStopReason.NO_DUE_WORK
        next_action = {}

    return record_loop_run(
        run_id=run_id,
        expert_name=expert_name,
        loop_type="sync",
        goal=f"Sync {'all' if sync_all else 'due'} subscriptions for {expert_name}",
        trigger="scheduled" if scheduled else "manual",
        status=status,
        stop_reason=stop_reason,
        next_action=next_action,
        run_context=_sync_run_context(expert_name, result, profile=profile),
        budget_limit=budget,
        budget_spent=float(getattr(result, "total_cost", 0.0) or 0.0),
        capacity_source=capacity_source,
        accepted_changes=accepted,
        rejected_changes=len(failed),
        started_at=started_at,
        finished_at=finished_at,
    )


def _record_running_sync_loop(
    expert_name: str,
    *,
    run_id: str,
    started_at: datetime,
    budget: float,
    scheduled: bool,
    sync_all: bool,
    capacity_source: str,
    profile: Any | None = None,
) -> Any:
    from deepr.experts.loop_runs import LoopRunStatus, record_loop_run

    return record_loop_run(
        run_id=run_id,
        expert_name=expert_name,
        loop_type="sync",
        goal=f"Sync {'all' if sync_all else 'due'} subscriptions for {expert_name}",
        trigger="scheduled" if scheduled else "manual",
        status=LoopRunStatus.RUNNING,
        stop_reason=None,
        run_context=_self_model_run_context(expert_name, profile=profile),
        budget_limit=budget,
        budget_spent=0.0,
        capacity_source=capacity_source,
        started_at=started_at,
        updated_at=started_at,
    )


def _record_failed_sync_execution(
    expert_name: str,
    *,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    budget: float,
    scheduled: bool,
    sync_all: bool,
    capacity_source: str,
    exception: Exception,
    profile: Any | None = None,
    budget_spent: float | None = None,
) -> Any:
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    known_spent = _known_spent_cost(exception)
    if budget_spent is not None:
        known_spent = max(known_spent, budget_spent)
    return record_loop_run(
        run_id=run_id,
        expert_name=expert_name,
        loop_type="sync",
        goal=f"Sync {'all' if sync_all else 'due'} subscriptions for {expert_name}",
        trigger="scheduled" if scheduled else "manual",
        status=LoopRunStatus.FAILED,
        stop_reason=LoopStopReason.TOOL_FAILURE,
        next_action={
            "status": "inspect",
            "title": "Inspect interrupted sync execution",
            "detail": "Sync raised before it could produce a result.",
            "command": f'deepr expert sync "{expert_name}" --dry-run',
        },
        run_context=_self_model_run_context(expert_name, profile=profile),
        budget_limit=budget,
        budget_spent=known_spent,
        capacity_source=capacity_source,
        failure_reason=f"sync execution failed: {type(exception).__name__}",
        started_at=started_at,
        updated_at=finished_at,
        finished_at=finished_at,
    )


def _known_spent_cost(exception: Exception) -> float:
    """Return the greatest trustworthy non-negative cost carried by an error chain."""
    from deepr.experts.loop_runs import known_exception_cost

    return known_exception_cost(exception)


def _record_sync_overlap_loop(
    expert_name: str,
    *,
    budget: float,
    scheduled: bool,
    sync_all: bool,
    capacity_source: str,
    profile: Any | None = None,
) -> Any:
    from deepr.experts.loop_runs import LoopRunStatus, LoopStopReason, record_loop_run

    return record_loop_run(
        expert_name=expert_name,
        loop_type="sync",
        goal=f"Sync {'all' if sync_all else 'due'} subscriptions for {expert_name}",
        trigger="scheduled" if scheduled else "manual",
        status=LoopRunStatus.WAITING,
        stop_reason=LoopStopReason.OVERLAP_LOCKED,
        next_action={
            "status": "waiting_for_overlap",
            "title": "Another sync is already running",
            "detail": "This run skipped because the same expert sync verb already holds the overlap lock.",
            "command": f'deepr expert sync "{expert_name}" --scheduled',
        },
        run_context=_self_model_run_context(expert_name, profile=profile),
        budget_limit=budget,
        budget_spent=0.0,
        capacity_source=capacity_source,
    )


def _selected_sync_capacity_source(*, use_local: bool, use_plan: bool, plan_adapter: Any) -> str:
    if use_local:
        return "local"
    if use_plan and plan_adapter is not None:
        return f"plan_quota:{plan_adapter.backend_id}"
    return "api_metered"


def _sync_overlap_result(expert_name: str) -> Any:
    from deepr.experts.sync import SyncOutcome, SyncResult

    return SyncResult(
        expert_name=expert_name,
        started_at=datetime.now(UTC),
        outcomes=[
            SyncOutcome(
                topic="sync",
                status="skipped",
                detail="another sync for this expert is already running",
            )
        ],
    )


def validate_compiled_claims_flags(
    *,
    compile_claims: bool,
    stage_compiled_claims: bool,
    apply_compiled_claims: bool,
    dry_run: bool,
    recall_embedding_model: str | None,
) -> str | None:
    """Validate the --compile-claims flag family before any store work.

    Returns the normalized recall embedding model (or ``None``) and raises
    ``ValueError`` with the operator-facing message on any invalid combination.
    """
    if apply_compiled_claims and not compile_claims:
        raise ValueError("--apply-compiled-claims requires --compile-claims.")
    if apply_compiled_claims and dry_run:
        raise ValueError("--apply-compiled-claims cannot be combined with --dry-run.")
    if stage_compiled_claims and not compile_claims:
        raise ValueError("--stage-compiled-claims requires --compile-claims.")
    if stage_compiled_claims and apply_compiled_claims:
        raise ValueError("--stage-compiled-claims cannot be combined with --apply-compiled-claims.")
    if recall_embedding_model is None:
        return None
    normalized = recall_embedding_model.strip()
    if not normalized:
        raise ValueError("--recall-embedding-model must not be blank.")
    if not compile_claims:
        raise ValueError("--recall-embedding-model requires --compile-claims.")
    return normalized


def _read_recall_preference_report(normalized_path: str) -> dict[str, Any]:
    path = Path(normalized_path).expanduser()
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("--recall-preference-report file does not exist.") from exc
    except OSError as exc:
        raise ValueError(f"--recall-preference-report could not be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"--recall-preference-report must be valid JSON: {exc.msg}") from exc

    if not isinstance(report, dict):
        raise ValueError("--recall-preference-report must contain a recall eval report object.")
    if report.get("schema_version") != RECALL_EVAL_REPORT_SCHEMA_VERSION:
        raise ValueError(
            "--recall-preference-report must be a deepr-recall-eval-report-v2 artifact; "
            "rerun the local recall eval to replace legacy point-estimate evidence."
        )
    return report


def _validate_recall_preference_identity(
    report: dict[str, Any],
    *,
    expert_name: str,
    recall_embedding_model: str,
) -> None:
    report_expert = report.get("expert", {})
    report_name = str(report_expert.get("name", "") or "").strip() if isinstance(report_expert, dict) else ""
    if report_name.casefold() != expert_name.strip().casefold():
        raise ValueError("--recall-preference-report expert does not match the sync target.")

    request = report.get("request", {})
    report_model = str(request.get("embedding_model", "") or "").strip() if isinstance(request, dict) else ""
    if report_model != recall_embedding_model:
        raise ValueError("--recall-preference-report embedding model does not match --recall-embedding-model.")


def _validate_recall_preference_contract(report: dict[str, Any]) -> None:
    contract = report.get("contract", {})
    cost_usd = contract.get("cost_usd") if isinstance(contract, dict) else None
    if (
        not isinstance(contract, dict)
        or isinstance(cost_usd, bool)
        or not isinstance(cost_usd, (int, float))
        or float(cost_usd) != 0.0
        or contract.get("relevance_labels") != "operator_supplied"
        or any(
            contract.get(flag) is not expected
            for flag, expected in (
                ("writes_graph", False),
                ("writes_beliefs", False),
                ("writes_belief_vectors", False),
                ("semantic_verdict", False),
                ("routing_evidence_only", True),
            )
        )
    ):
        raise ValueError("--recall-preference-report must be a read-only routing-evidence report.")


def _scheduler_preference_from_report(report: dict[str, Any]) -> dict[str, Any]:
    preference = report.get("scheduler_preference", {})
    if not isinstance(preference, dict):
        raise ValueError("--recall-preference-report is missing scheduler_preference.")
    if preference.get("fallback_route") != RECALL_LEXICAL_ROUTE:
        raise ValueError("--recall-preference-report must declare lexical_router as fallback_route.")
    if preference.get("routing_evidence_only") is not True or preference.get("semantic_verdict") is not False:
        raise ValueError("--recall-preference-report scheduler preference must be routing evidence only.")
    if preference.get("eligible") is True and preference.get("preferred_route") != RECALL_VECTOR_ROUTE:
        raise ValueError("--recall-preference-report eligible preference must prefer vector_similarity.")
    if preference.get("eligible") is True:
        try:
            return validate_recall_preference_evidence(report)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"--recall-preference-report {exc}") from exc
    return dict(preference)


def load_recall_route_preference_report(
    report_path: str | None,
    *,
    expert_name: str,
    compile_claims: bool,
    recall_embedding_model: str | None,
) -> dict[str, Any] | None:
    """Load the scheduler preference from a local recall eval report.

    The returned object is only the machine-readable scheduler-preference block;
    local file paths are not copied into downstream artifacts.
    """
    if report_path is None:
        return None
    normalized_path = str(report_path).strip()
    if not normalized_path:
        raise ValueError("--recall-preference-report must not be blank.")
    if not compile_claims:
        raise ValueError("--recall-preference-report requires --compile-claims.")
    if not recall_embedding_model:
        raise ValueError("--recall-preference-report requires --recall-embedding-model.")
    report = _read_recall_preference_report(normalized_path)
    _validate_recall_preference_identity(
        report,
        expert_name=expert_name,
        recall_embedding_model=recall_embedding_model,
    )
    _validate_recall_preference_contract(report)
    preference = _scheduler_preference_from_report(report)
    if preference.get("eligible") is True:
        from deepr.experts.beliefs import BeliefStore

        try:
            current_index = belief_index_coverage(BeliefStore(expert_name), recall_embedding_model)
            validate_preference_current_index(
                preference,
                current_index,
                embedding_model=recall_embedding_model,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"--recall-preference-report {exc}") from exc
    return preference


def _run_sync_with_loop_guard(
    profile: Any,
    *,
    name: str,
    budget: float,
    sync_all: bool,
    dry_run: bool,
    scheduled: bool,
    jitter: float,
    use_local: bool,
    local_model: str | None,
    use_plan: bool,
    plan_adapter: Any,
    plan_model: str | None,
    context_builder: Any,
    grounding_checker: Any | None = None,
    grounding_escalator: Any | None = None,
    compile_claims: bool = False,
    apply_graph_commits: bool = False,
    spend_decision_fn: Any | None = None,
    recall_embedding_model: str | None = None,
    recall_route_preference: dict[str, Any] | None = None,
) -> tuple[Any, Any | None, str]:
    from deepr.experts.maintenance_engine import build_sync_engine

    def run_once() -> tuple[Any, str]:
        engine, capacity_source = build_sync_engine(
            profile,
            use_local=use_local,
            local_model=local_model,
            use_plan=use_plan,
            plan_adapter=plan_adapter,
            plan_model=plan_model,
            context_builder=context_builder,
            grounding_checker=grounding_checker,
            grounding_escalator=grounding_escalator,
            compile_claims=compile_claims,
            spend_decision_fn=spend_decision_fn,
            recall_embedding_model=recall_embedding_model,
            recall_route_preference=recall_route_preference,
        )
        result = asyncio.run(
            engine.sync(
                budget=budget,
                only_due=not sync_all,
                dry_run=dry_run,
                apply_graph_commits=apply_graph_commits,
            )
        )
        return result, capacity_source

    if dry_run:
        result, capacity_source = run_once()
        return result, None, capacity_source

    if jitter > 0:
        from deepr.experts.loop_lock import apply_startup_jitter

        apply_startup_jitter(name, jitter)

    from deepr.experts.loop_lock import expert_verb_lock

    capacity_source = _selected_sync_capacity_source(
        use_local=use_local,
        use_plan=use_plan,
        plan_adapter=plan_adapter,
    )
    with expert_verb_lock(name, "sync") as acquired:
        if not acquired:
            result = _sync_overlap_result(name)
            loop_run = _record_sync_overlap_loop(
                name,
                budget=budget,
                scheduled=scheduled,
                sync_all=sync_all,
                capacity_source=capacity_source,
                profile=profile,
            )
            return result, loop_run, capacity_source
        from deepr.experts.loop_runs import new_loop_run_id

        run_id = new_loop_run_id()
        started_at = datetime.now(UTC)
        _record_running_sync_loop(
            name,
            run_id=run_id,
            started_at=started_at,
            budget=budget,
            scheduled=scheduled,
            sync_all=sync_all,
            capacity_source=capacity_source,
            profile=profile,
        )
        try:
            result, capacity_source = run_once()
        except Exception as exc:
            _record_failed_sync_execution(
                name,
                run_id=run_id,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                budget=budget,
                scheduled=scheduled,
                sync_all=sync_all,
                capacity_source=capacity_source,
                exception=exc,
                profile=profile,
            )
            raise
        finished_at = datetime.now(UTC)
        loop_run = _record_completed_sync_loop(
            name,
            result,
            budget=budget,
            scheduled=scheduled,
            sync_all=sync_all,
            capacity_source=capacity_source,
            profile=profile,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
        )
        return result, loop_run, capacity_source


def _sync_context_builder(*, fresh_context: bool, deep_context: bool, json_output: bool) -> Any | None:
    """Build the optional free-only retrieval context builder for local/plan sync."""
    if deep_context:
        from deepr.backends.fresh_context import make_free_deep_context_builder

        if not json_output:
            console.print(
                "[dim]Deep context enabled: multi-query free-only web retrieval; "
                "API-key search providers are not used.[/dim]"
            )
        return make_free_deep_context_builder()
    if fresh_context:
        from deepr.backends.fresh_context import make_free_fresh_context_builder

        if not json_output:
            console.print(
                "[dim]Fresh context enabled: free-only web retrieval; API-key search providers are not used.[/dim]"
            )
        return make_free_fresh_context_builder()
    return None
