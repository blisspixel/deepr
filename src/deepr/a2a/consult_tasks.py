"""A2A task adapter for expert consult artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from deepr.a2a.constants import CONSULT_SKILL_NAME
from deepr.mcp.consult_tool import consult_experts_tool


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
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    backend_mode = str(metadata.get("synthesis_backend") or "local").strip().lower()
    budget = _budget_value(request.budget)
    error = _validate_capacity_request(backend_mode, budget, metadata)
    if error:
        return A2AConsultTaskResult(ok=False, error=error)

    payload = await consult_experts_tool(
        question=request.input,
        experts=_string_list(metadata.get("experts")),
        max_experts=_max_experts(metadata.get("max_experts")),
        budget=budget,
        synthesis_backend=backend_mode,
        local_model=_optional_string(metadata.get("local_model")),
        plan=_optional_string(metadata.get("plan")),
        plan_model=_optional_string(metadata.get("plan_model")),
    )
    if "error_code" in payload:
        return A2AConsultTaskResult(ok=False, error=payload)

    artifact = build_consult_artifact(payload)
    return A2AConsultTaskResult(
        ok=True,
        result=build_consult_result(payload, artifact_id=str(artifact["artifact_id"])),
        cost=round(float(payload.get("cost_usd", 0.0) or 0.0), 4),
        trace_id=_trace_id(payload),
        artifacts=[artifact],
    )


def build_consult_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap a consult payload as a host-inspectable A2A task artifact."""
    trace_id = _trace_id(payload)
    artifact_id = f"deepr-consult:{trace_id}" if trace_id else f"deepr-consult:{_payload_hash(payload)[:16]}"
    collaboration = payload.get("collaboration") if isinstance(payload.get("collaboration"), dict) else {}
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
    return {
        "status": "completed",
        "artifact_id": artifact_id,
        "consult_schema_version": payload.get("schema_version", ""),
        "consult_kind": payload.get("kind", ""),
        "answer": payload.get("answer", ""),
        "experts_consulted": list(payload.get("experts_consulted", []) or []),
        "agreements": list(payload.get("agreements", []) or []),
        "disagreements": list(payload.get("disagreements", []) or []),
        "cost_usd": round(float(payload.get("cost_usd", 0.0) or 0.0), 4),
        "capacity": _dict_value(payload.get("capacity")),
        "trace": _dict_value(payload.get("trace")),
        "collaboration": _dict_value(payload.get("collaboration")),
    }


def _validate_capacity_request(backend_mode: str, budget: float, metadata: dict[str, Any]) -> dict[str, Any] | None:
    if backend_mode not in {"api", "local", "plan"}:
        return _error("INVALID_BACKEND", "synthesis_backend must be one of: api, local, plan")
    if budget < 0:
        return _error("INVALID_BUDGET", "budget must be non-negative")
    if backend_mode == "api":
        if not bool(metadata.get("allow_metered_api", False)):
            return _error(
                "METERED_API_NOT_APPROVED",
                "A2A API consult requires metadata.allow_metered_api=true and a positive budget.",
            )
        if budget <= 0:
            return _error("INVALID_BUDGET", "A2A API consult requires a positive budget.")
    if backend_mode == "plan" and not _optional_string(metadata.get("plan")):
        return _error("INVALID_BACKEND", "plan is required when synthesis_backend='plan'")
    return None


def _budget_value(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _max_experts(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 3
    return max(1, min(parsed, 10))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (_optional_string(raw) for raw in value) if item]


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _trace_id(payload: dict[str, Any]) -> str:
    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
    collaboration = payload.get("collaboration") if isinstance(payload.get("collaboration"), dict) else {}
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
