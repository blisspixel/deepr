"""Durable consult trace records.

Consult is Deepr's primary knowledge transaction for host agents. The returned
artifact is useful, but improvement loops need a replayable local record with
the inputs, selected context, capacity posture, checks that ran, and failure
events. These records are append-only and local to the operator's data root.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.config import default_data_dir
from deepr.utils.atomic_io import append_jsonl_durable

CONSULT_TRACE_SCHEMA_VERSION = "deepr-consult-trace-v1"
CONSULT_TRACE_KIND = "deepr.expert.consult_trace"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    context_count = len(_perspective_contexts(payload))
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
