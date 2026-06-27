"""Durable consult trace records.

Consult is Deepr's primary knowledge transaction for host agents. The returned
artifact is useful, but improvement loops need a replayable local record with
the inputs, selected context, capacity posture, checks that ran, and failure
events. These records are append-only and local to the operator's data root.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.config import default_data_dir
from deepr.core.contracts import Gap
from deepr.experts.gap_scorer import score_gap
from deepr.utils.atomic_io import append_jsonl_durable

CONSULT_TRACE_SCHEMA_VERSION = "deepr-consult-trace-v1"
CONSULT_TRACE_KIND = "deepr.expert.consult_trace"
CONSULT_TRACE_CANDIDATES_SCHEMA_VERSION = "deepr-consult-trace-candidates-v1"
CONSULT_TRACE_CANDIDATES_KIND = "deepr.expert.consult_trace_candidates"
CONSULT_QUALITY_EVAL_CASE_SCHEMA_VERSION = "deepr-consult-quality-eval-case-v1"
CONSULT_QUALITY_EVAL_CASE_KIND = "deepr.eval.consult_quality_case"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _preview(value: str, *, limit: int = 160) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _trace_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    explicit = os.getenv("DEEPR_CONSULT_TRACE_PATH")
    if explicit:
        return Path(explicit)
    return default_data_dir() / "consult_traces" / "consult_traces.jsonl"


def new_consult_trace_id() -> str:
    return f"consult_{uuid.uuid4().hex[:12]}"


def _contract() -> dict[str, Any]:
    return {
        "read_only": False,
        "cost_usd": 0.0,
        "stability": "experimental",
        "compatibility": {
            "additive_fields": True,
            "breaking_changes_require_new_schema_version": True,
            "deprecation_policy": "Fields in this v1 payload are additive within v1; removals use a new schema.",
        },
    }


def _capacity_block(capacity: dict[str, Any] | None) -> dict[str, Any]:
    if not capacity:
        return {
            "synthesis_backend": "api",
            "provider": "openai",
            "model": "",
            "live_metered_fallback": True,
        }
    return {
        "synthesis_backend": str(capacity.get("synthesis_backend", "api")),
        "provider": str(capacity.get("provider", "")),
        "model": str(capacity.get("model") or ""),
        "live_metered_fallback": bool(capacity.get("live_metered_fallback", True)),
    }


def _perspective_contexts(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for perspective in (payload or {}).get("perspectives", []) or []:
        if not isinstance(perspective, dict):
            continue
        context = perspective.get("context")
        contexts.append(
            {
                "expert": str(perspective.get("expert", "")),
                "confidence": float(perspective.get("confidence", 0.0) or 0.0),
                "context": context if isinstance(context, dict) else {},
            }
        )
    return contexts


def _checks(
    *,
    payload: dict[str, Any] | None,
    capacity: dict[str, Any],
    synthesis_status: str,
    status: str,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    payload_ok = bool(
        payload
        and payload.get("schema_version") == "deepr-consult-v1"
        and payload.get("kind") == "deepr.expert.consult"
    )
    checks.append(
        {
            "name": "consult_payload_contract",
            "status": "passed" if payload_ok else "failed",
            "detail": "payload schema_version and kind checked",
        }
    )
    cost = float((payload or {}).get("cost_usd", 0.0) or 0.0)
    checks.append(
        {
            "name": "cost_contract",
            "status": "passed" if cost >= 0 else "failed",
            "detail": f"cost_usd={cost:.4f}",
        }
    )
    if capacity["synthesis_backend"] in {"local", "plan"}:
        no_metered_fallback = not capacity["live_metered_fallback"]
        checks.append(
            {
                "name": "owned_capacity_no_metered_fallback",
                "status": "passed" if no_metered_fallback else "failed",
                "detail": f"synthesis_backend={capacity['synthesis_backend']}",
            }
        )
    else:
        checks.append(
            {
                "name": "owned_capacity_no_metered_fallback",
                "status": "skipped",
                "detail": "api synthesis backend may use metered fallback under budget",
            }
        )
    context_count = sum(1 for item in _perspective_contexts(payload) if item["context"])
    checks.append(
        {
            "name": "perspective_context_packet",
            "status": "passed" if context_count else "warning",
            "detail": f"perspective_context_count={context_count}",
        }
    )
    checks.append(
        {
            "name": "synthesis_status",
            "status": "passed" if synthesis_status in {"completed", "skipped_no_valid_perspectives"} else "failed",
            "detail": synthesis_status or status,
        }
    )
    return checks


def _events(result: dict[str, Any] | None, failure: dict[str, Any] | None) -> list[dict[str, Any]]:
    now = _utc_now().isoformat()
    events = [{"name": "consult_started", "timestamp": now, "attributes": {}}]
    if failure:
        events.append({"name": "consult_failed", "timestamp": now, "attributes": failure})
        return events

    perspectives = (result or {}).get("perspectives", []) or []
    events.append(
        {
            "name": "perspectives_collected",
            "timestamp": now,
            "attributes": {"count": len(perspectives)},
        }
    )
    synthesis_status = str((result or {}).get("synthesis_status", "completed"))
    event_name = "synthesis_failed" if synthesis_status == "failed" else "synthesis_finished"
    events.append(
        {
            "name": event_name,
            "timestamp": now,
            "attributes": {
                "status": synthesis_status,
                "error_type": str((result or {}).get("synthesis_error_type", "")),
            },
        }
    )
    return events


def build_consult_trace(
    *,
    question: str,
    requested_experts: list[str],
    max_experts: int,
    budget: float,
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    capacity: dict[str, Any] | None = None,
    failure: dict[str, Any] | None = None,
    trace_id: str | None = None,
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a replayable consult trace record without writing it."""
    capacity_record = _capacity_block(capacity)
    synthesis_status = str((result or {}).get("synthesis_status", "failed" if failure else "completed"))
    status = "failed" if failure else "completed"
    perspective_contexts = _perspective_contexts(payload)
    checked = _checks(payload=payload, capacity=capacity_record, synthesis_status=synthesis_status, status=status)
    record = {
        "schema_version": CONSULT_TRACE_SCHEMA_VERSION,
        "kind": CONSULT_TRACE_KIND,
        "contract": _contract(),
        "trace_id": trace_id or new_consult_trace_id(),
        "recorded_at": (recorded_at or _utc_now()).isoformat(),
        "status": status,
        "input": {
            "question": question,
            "question_hash": _sha256(question),
            "requested_experts": list(requested_experts),
            "max_experts": int(max_experts),
            "budget_usd": float(budget),
        },
        "capacity": capacity_record,
        "context_packet": {
            "always": {
                "experts_consulted": list((payload or {}).get("experts_consulted", []) or []),
                "perspective_count": len((payload or {}).get("perspectives", []) or []),
                "cost_usd": float((payload or {}).get("cost_usd", 0.0) or 0.0),
            },
            "selected": perspective_contexts,
        },
        "output": payload or {},
        "checks": checked,
        "events": _events(result, failure),
        "failure": failure or {},
    }
    return record


def public_trace_ref(record: dict[str, Any]) -> dict[str, Any]:
    """Return the safe reference embedded in CLI/MCP consult artifacts."""
    return {
        "schema_version": record["schema_version"],
        "kind": record["kind"],
        "trace_id": record["trace_id"],
        "status": record["status"],
        "recorded": True,
        "checks_ran": [check["name"] for check in record.get("checks", []) if isinstance(check, dict)],
    }


def record_consult_trace(*, path: Path | None = None, **kwargs: Any) -> dict[str, Any]:
    """Append a consult trace and return its safe public reference."""
    record = build_consult_trace(**kwargs)
    append_jsonl_durable(_trace_path(path), record, fsync=True)
    return public_trace_ref(record)


def load_consult_traces(*, path: Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Load the newest consult traces from the local JSONL trace store."""
    resolved = _trace_path(path)
    if limit <= 0 or not resolved.exists():
        return []

    records: list[dict[str, Any]] = []
    with resolved.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
    return records[-limit:]


def _check_names_by_status(trace: dict[str, Any], statuses: set[str]) -> list[str]:
    names: list[str] = []
    for check in trace.get("checks", []) or []:
        if not isinstance(check, dict):
            continue
        if str(check.get("status", "")) in statuses:
            names.append(str(check.get("name", "")))
    return [name for name in names if name]


def _selected_context_count(trace: dict[str, Any]) -> int:
    packet = trace.get("context_packet", {})
    selected = packet.get("selected", []) if isinstance(packet, dict) else []
    if not isinstance(selected, list):
        return 0
    return sum(1 for item in selected if isinstance(item, dict) and bool(item.get("context")))


def _candidate_reason(trace: dict[str, Any], *, low_context_threshold: int) -> tuple[str, int] | None:
    if trace.get("status") == "failed":
        return "failed_consult", 5

    failed_checks = _check_names_by_status(trace, {"failed"})
    if failed_checks:
        return "failed_check", 4

    if _selected_context_count(trace) < low_context_threshold:
        return "low_context", 3

    return None


def _gap_for_trace(trace: dict[str, Any], reason: str, priority: int) -> Gap:
    question = str((trace.get("input") or {}).get("question", ""))
    label = {
        "failed_consult": "Consult failed",
        "failed_check": "Consult trace check failed",
        "low_context": "Consult lacked selected context",
    }[reason]
    gap = Gap.create(
        f"{label}: {_preview(question, limit=120)}",
        questions=[question] if question else [],
        priority=priority,
        times_asked=1,
    )
    return score_gap(gap)


def _eval_case_for_trace(trace: dict[str, Any], reason: str) -> dict[str, Any]:
    input_block = trace.get("input") if isinstance(trace.get("input"), dict) else {}
    question = str(input_block.get("question", ""))
    return {
        "case_id": f"{trace.get('trace_id', 'consult_unknown')}_{reason}",
        "category": "consult_trace_regression",
        "source_trace_id": str(trace.get("trace_id", "")),
        "input": {
            "question_hash": str(input_block.get("question_hash", _sha256(question))),
            "question_preview": _preview(question),
        },
        "expected_failure_mode": reason,
        "acceptance_check": "future consult run should avoid this structural failure",
    }


def _check_status(trace: dict[str, Any], name: str) -> str:
    for check in trace.get("checks", []) or []:
        if not isinstance(check, dict):
            continue
        if str(check.get("name", "")) == name:
            return str(check.get("status", ""))
    return ""


def _semantic_eval_case_for_trace(trace: dict[str, Any], reason: str) -> dict[str, Any]:
    input_block = trace.get("input") if isinstance(trace.get("input"), dict) else {}
    question = str(input_block.get("question", ""))
    return {
        "schema_version": CONSULT_QUALITY_EVAL_CASE_SCHEMA_VERSION,
        "kind": CONSULT_QUALITY_EVAL_CASE_KIND,
        "case_id": f"{trace.get('trace_id', 'consult_unknown')}_{reason}_quality",
        "source_trace_id": str(trace.get("trace_id", "")),
        "category": "consult_semantic_quality",
        "contract": {
            "cost_usd": 0.0,
            "writes_state": False,
            "semantic_verdict": False,
            "requires_human_or_calibrated_model_judge": True,
            "lexical_verdict_allowed": False,
        },
        "input": {
            "question_hash": str(input_block.get("question_hash", _sha256(question))),
            "question_preview": _preview(question),
            "reason": reason,
            "capacity": _capacity_block(trace.get("capacity") if isinstance(trace.get("capacity"), dict) else None),
            "selected_context_count": _selected_context_count(trace),
            "failed_checks": _check_names_by_status(trace, {"failed"}),
            "warning_checks": _check_names_by_status(trace, {"warning"}),
            "synthesis_status": _check_status(trace, "synthesis_status"),
        },
        "rubric": [
            {
                "dimension": "uses_expert_state",
                "score_min": 1,
                "score_max": 5,
                "judge_question": "Does the answer use the expert perspectives and current stored context when available?",
            },
            {
                "dimension": "surfaces_uncertainty",
                "score_min": 1,
                "score_max": 5,
                "judge_question": "Does the answer distinguish knowns, unknowns, stale context, hypotheses, and open questions?",
            },
            {
                "dimension": "preserves_dissent",
                "score_min": 1,
                "score_max": 5,
                "judge_question": "Does the answer preserve meaningful disagreements instead of flattening them into false consensus?",
            },
            {
                "dimension": "actionability",
                "score_min": 1,
                "score_max": 5,
                "judge_question": "Does the answer give useful next actions, decision criteria, or research directions for the host agent?",
            },
            {
                "dimension": "grounded_when_factual",
                "score_min": 1,
                "score_max": 5,
                "judge_question": "Are external factual claims grounded or clearly labeled as unverified, stale, or hypothetical?",
            },
            {
                "dimension": "original_thought",
                "score_min": 1,
                "score_max": 5,
                "judge_question": "Does the answer allow useful synthesis, stance, and hypotheses without pretending they are verified facts?",
            },
        ],
        "failure_labels": [
            "missing_current_context",
            "unsupported_factual_claim",
            "stale_claim_promoted_as_current",
            "false_consensus",
            "ignored_dissent",
            "thin_or_generic_answer",
            "unlabeled_hypothesis",
            "not_actionable_for_host_agent",
        ],
        "acceptance_policy": {
            "minimum_mean_score": 4.0,
            "requires_reviewer": True,
            "eligible_promotions": ["gap_candidate", "eval_artifact"],
            "never_commits_beliefs": True,
        },
    }


def _candidate_for_trace(
    trace: dict[str, Any],
    *,
    reason: str,
    priority: int,
) -> dict[str, Any]:
    gap = _gap_for_trace(trace, reason, priority)
    input_block = trace.get("input") if isinstance(trace.get("input"), dict) else {}
    return {
        "trace_id": str(trace.get("trace_id", "")),
        "recorded_at": str(trace.get("recorded_at", "")),
        "reason": reason,
        "severity": priority,
        "question_hash": str(input_block.get("question_hash", "")),
        "question_preview": _preview(str(input_block.get("question", ""))),
        "failed_checks": _check_names_by_status(trace, {"failed"}),
        "warning_checks": _check_names_by_status(trace, {"warning"}),
        "selected_context_count": _selected_context_count(trace),
        "gap": gap.to_dict(),
        "eval_case": _eval_case_for_trace(trace, reason),
        "semantic_eval_case": _semantic_eval_case_for_trace(trace, reason),
    }


def build_consult_trace_candidates(
    traces: list[dict[str, Any]],
    *,
    max_candidates: int = 20,
    low_context_threshold: int = 1,
) -> dict[str, Any]:
    """Build sanitized gap and eval candidates from local consult traces."""
    max_candidates = max(0, max_candidates)
    low_context_threshold = max(0, low_context_threshold)
    candidates: list[dict[str, Any]] = []
    failed_trace_count = 0
    failed_check_count = 0
    low_context_count = 0
    seen_trace_ids: set[str] = set()

    for trace in traces:
        trace_id = str(trace.get("trace_id", ""))
        if trace_id in seen_trace_ids:
            continue
        seen_trace_ids.add(trace_id)
        reason = _candidate_reason(trace, low_context_threshold=low_context_threshold)
        if reason is None:
            continue
        reason_name, priority = reason
        if reason_name == "failed_consult":
            failed_trace_count += 1
        if reason_name == "failed_check":
            failed_check_count += 1
        if reason_name == "low_context":
            low_context_count += 1
        candidates.append(_candidate_for_trace(trace, reason=reason_name, priority=priority))

    candidates = sorted(
        candidates,
        key=lambda item: (int(item["severity"]), str(item["recorded_at"])),
        reverse=True,
    )[:max_candidates]
    return {
        "schema_version": CONSULT_TRACE_CANDIDATES_SCHEMA_VERSION,
        "kind": CONSULT_TRACE_CANDIDATES_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "stability": "experimental",
            "path_exposed": False,
        },
        "trace_count": len(traces),
        "candidate_count": len(candidates),
        "failed_trace_count": failed_trace_count,
        "failed_check_count": failed_check_count,
        "low_context_trace_count": low_context_count,
        "semantic_eval_case_count": len(candidates),
        "candidates": candidates,
    }


def review_consult_traces(
    *,
    path: Path | None = None,
    limit: int = 50,
    max_candidates: int = 20,
    low_context_threshold: int = 1,
) -> dict[str, Any]:
    """Load local traces and return sanitized gap and eval candidates."""
    return build_consult_trace_candidates(
        load_consult_traces(path=path, limit=limit),
        max_candidates=max_candidates,
        low_context_threshold=low_context_threshold,
    )
