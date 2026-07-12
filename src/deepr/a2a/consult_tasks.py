"""A2A task adapter for expert consult artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import isfinite
from typing import Any

from deepr.a2a.constants import CONSULT_SKILL_NAME
from deepr.experts.consult import MAX_CONSULT_EXPERTS
from deepr.mcp.consult_tool import consult_experts_tool

_MISSING = object()


@dataclass(frozen=True)
class A2AConsultTaskResult:
    """Result material needed to complete or fail an A2A consult task."""

    ok: bool
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    cost: float = 0.0
    trace_id: str = ""
    artifacts: list[dict[str, Any]] | None = None


def is_consult_skill(skill: str) -> bool:
    """Return whether an A2A skill name maps to expert consult."""
    return skill == CONSULT_SKILL_NAME


async def run_consult_task(request: Any) -> A2AConsultTaskResult:
    """Run a no-surprise-bills expert consult for an A2A task request."""
    raw_metadata = getattr(request, "metadata", _MISSING)
    if raw_metadata is _MISSING:
        metadata: dict[str, Any] = {}
    elif not isinstance(raw_metadata, dict):
        return A2AConsultTaskResult(
            ok=False,
            error=_error("INVALID_METADATA", "metadata must be an object"),
        )
    else:
        metadata = raw_metadata
    type_error = _metadata_type_error(metadata)
    if type_error:
        return A2AConsultTaskResult(ok=False, error=type_error)
    backend_value = metadata.get("synthesis_backend")
    backend_mode = "local" if backend_value is None else backend_value.strip().lower()
    budget = _budget_value(request.budget)
    try:
        max_experts = _max_experts(metadata.get("max_experts"))
    except ValueError:
        return A2AConsultTaskResult(
            ok=False,
            error=_error(
                "INVALID_MAX_EXPERTS",
                f"max_experts must be an integer between 1 and {MAX_CONSULT_EXPERTS}",
            ),
        )
    error = _validate_capacity_request(backend_mode, budget, metadata)
    if error:
        return A2AConsultTaskResult(ok=False, error=error)

    payload = await consult_experts_tool(
        question=request.input,
        experts=_string_list(metadata.get("experts")),
        max_experts=max_experts,
        budget=budget,
        synthesis_backend=backend_mode,
        local_model=_optional_string(metadata.get("local_model")),
        plan=_optional_string(metadata.get("plan")),
        plan_model=_optional_string(metadata.get("plan_model")),
    )
    if "error_code" in payload:
        return A2AConsultTaskResult(ok=False, error=payload)

    artifact = build_consult_artifact(payload)
    result = build_consult_result(payload, artifact_id=str(artifact["artifact_id"]))
    terminal_error = _consult_terminal_error(payload)
    return A2AConsultTaskResult(
        ok=terminal_error is None,
        result=result,
        error=terminal_error,
        cost=float(payload.get("cost_usd", 0.0) or 0.0),
        trace_id=_trace_id(payload),
        artifacts=[artifact],
    )


def build_consult_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap a consult payload as a host-inspectable A2A task artifact."""
    trace_id = _trace_id(payload)
    artifact_id = f"deepr-consult:{trace_id}" if trace_id else f"deepr-consult:{_payload_hash(payload)[:16]}"
    collaboration = _dict_value(payload.get("collaboration"))
    dissent = _dict_value(collaboration.get("dissent_handling"))
    contract = _dict_value(collaboration.get("contract"))
    return {
        "artifact_id": artifact_id,
        "name": "deepr-consult-v1",
        "mime_type": "application/json",
        "schema_version": payload.get("schema_version", ""),
        "kind": payload.get("kind", ""),
        "content": payload,
        "metadata": {
            "a2a_result_role": "expert_consult",
            "collaboration_schema_version": collaboration.get("schema_version", ""),
            "dissent_preserved": bool(dissent.get("dissent_preserved", False)),
            "host_orchestrated": bool(contract.get("host_orchestrated", True)),
            "deepr_enacts_downstream_actions": bool(contract.get("deepr_enacts_downstream_actions", False)),
            "result_untrusted": True,
        },
    }


def build_consult_result(payload: dict[str, Any], *, artifact_id: str) -> dict[str, Any]:
    """Build the compact A2A task result that points to the consult artifact."""
    synthesis_status = str(payload.get("synthesis_status", "failed") or "failed")
    task_status = "completed" if synthesis_status in {"completed", "skipped_no_valid_perspectives"} else "incomplete"
    return {
        "status": task_status,
        "synthesis_status": synthesis_status,
        "synthesis_error_type": str(payload.get("synthesis_error_type", "") or ""),
        "synthesis_stop_reason": str(payload.get("synthesis_stop_reason", "") or ""),
        "artifact_id": artifact_id,
        "consult_schema_version": payload.get("schema_version", ""),
        "consult_kind": payload.get("kind", ""),
        "answer": payload.get("answer", ""),
        "experts_consulted": list(payload.get("experts_consulted", []) or []),
        "agreements": list(payload.get("agreements", []) or []),
        "disagreements": list(payload.get("disagreements", []) or []),
        "cost_usd": float(payload.get("cost_usd", 0.0) or 0.0),
        "capacity": _dict_value(payload.get("capacity")),
        "trace": _dict_value(payload.get("trace")),
        "collaboration": _dict_value(payload.get("collaboration")),
    }


def _consult_terminal_error(payload: dict[str, Any]) -> dict[str, Any] | None:
    synthesis_status = str(payload.get("synthesis_status", "failed") or "failed")
    if synthesis_status in {"completed", "skipped_no_valid_perspectives"}:
        return None
    error_type = str(payload.get("synthesis_error_type", "") or "")
    stop_reason = str(payload.get("synthesis_stop_reason", "") or "")
    incomplete = synthesis_status == "truncated"
    error = _error(
        "CONSULT_INCOMPLETE" if incomplete else "CONSULT_FAILED",
        "Expert consult synthesis was incomplete." if incomplete else "Expert consult synthesis failed.",
    )
    error.update(
        {
            "synthesis_status": synthesis_status,
            "synthesis_error_type": error_type,
            "synthesis_stop_reason": stop_reason,
            "artifact_preserved": True,
        }
    )
    return error


def _validate_capacity_request(backend_mode: str, budget: float, metadata: dict[str, Any]) -> dict[str, Any] | None:
    if backend_mode not in {"api", "local", "plan"}:
        return _error("INVALID_BACKEND", "synthesis_backend must be one of: api, local, plan")
    if not isfinite(budget) or budget < 0:
        return _error("INVALID_BUDGET", "budget must be non-negative")
    if backend_mode == "api":
        if metadata.get("allow_metered_api") is not True:
            return _error(
                "METERED_API_NOT_APPROVED",
                "A2A API consult requires metadata.allow_metered_api=true and a positive budget.",
            )
        if budget <= 0:
            return _error("INVALID_BUDGET", "A2A API consult requires a positive budget.")
    if backend_mode == "plan" and not _optional_string(metadata.get("plan")):
        return _error("INVALID_BACKEND", "plan is required when synthesis_backend='plan'")
    return None


def _metadata_type_error(metadata: dict[str, Any]) -> dict[str, Any] | None:
    if "synthesis_backend" in metadata and not isinstance(metadata["synthesis_backend"], str):
        return _error("INVALID_BACKEND", "synthesis_backend must be one of: api, local, plan")
    if "experts" in metadata:
        experts = metadata["experts"]
        if (
            not isinstance(experts, list)
            or any(not isinstance(expert, str) or not expert.strip() for expert in experts)
            or len(experts) > MAX_CONSULT_EXPERTS
        ):
            return _error(
                "INVALID_EXPERT_LIMIT",
                f"experts must be an array of 0 to {MAX_CONSULT_EXPERTS} non-empty strings",
            )
    for key in ("local_model", "plan", "plan_model"):
        if key in metadata and not isinstance(metadata[key], str):
            return _error(
                "INVALID_BACKEND",
                "local_model, plan, plan_model, and synthesis_backend must be strings when provided",
            )
    return None


def _budget_value(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return -1.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _max_experts(value: Any) -> int:
    if value is None:
        return 3
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_CONSULT_EXPERTS:
        raise ValueError("invalid max_experts")
    return value


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [raw.strip() for raw in value if isinstance(raw, str) and raw.strip()]


def _optional_string(value: Any) -> str | None:
    if value is None or not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _trace_id(payload: dict[str, Any]) -> str:
    trace = _dict_value(payload.get("trace"))
    collaboration = _dict_value(payload.get("collaboration"))
    task = _dict_value(collaboration.get("task"))
    return str(trace.get("trace_id") or task.get("consult_trace_id") or "")


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _payload_hash(payload: dict[str, Any]) -> str:
    material = repr(
        (
            payload.get("schema_version", ""),
            payload.get("kind", ""),
            payload.get("question", ""),
            payload.get("answer", ""),
            payload.get("experts_consulted", []),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _error(code: str, message: str) -> dict[str, Any]:
    return {
        "error_code": code,
        "category": "a2a_consult",
        "retryable": False,
        "message": message,
    }
