"""MCP helper for expert council consultation."""

from __future__ import annotations

from typing import Any

from deepr.core.errors import DeeprError
from deepr.experts import consult as consult_core
from deepr.experts.consult_traces import record_consult_trace

CONSULT_EXPERTS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "The question to put to the expert team"},
        "experts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional explicit expert names; omit to auto-select relevant experts",
        },
        "max_experts": {
            "type": "integer",
            "description": (
                "Max experts when auto-selecting (capped at 10). Default 3; pass a higher "
                "value for a wider cross-domain fan-out. Ignored when 'experts' is given."
            ),
            "default": 3,
            "minimum": 1,
            "maximum": 10,
        },
        "budget": {"type": "number", "description": "USD ceiling for API consults", "default": 2.0},
        "synthesis_backend": {
            "type": "string",
            "enum": ["api", "local", "plan"],
            "description": "Use local or explicit plan capacity to avoid live metered fallback.",
            "default": "api",
        },
        "local_model": {
            "type": "string",
            "description": "Optional Ollama model when synthesis_backend='local'.",
        },
        "plan": {
            "type": "string",
            "description": "Plan-quota backend id when synthesis_backend='plan' (for example codex).",
        },
        "plan_model": {
            "type": "string",
            "description": "Optional model hint for the plan-quota CLI.",
        },
    },
    "required": ["question"],
}


def _error(code: str, message: str) -> dict[str, Any]:
    return {
        "error_code": code,
        "category": "internal",
        "retryable": False,
        "message": message,
    }


def _capacity_payload(backend_mode: str, backend: consult_core.ConsultSynthesisBackend) -> dict[str, Any]:
    return {
        "synthesis_backend": backend_mode,
        "provider": backend.provider,
        "model": backend.model,
        "live_metered_fallback": backend.allow_live_fallback,
    }


async def consult_experts_tool(
    *,
    question: str,
    experts: list[str] | None = None,
    max_experts: int = 3,
    budget: float = 2.0,
    synthesis_backend: str = "api",
    local_model: str | None = None,
    plan: str | None = None,
    plan_model: str | None = None,
) -> dict[str, Any]:
    """Run the MCP expert council consult tool."""
    backend_mode = (synthesis_backend or "api").strip().lower()
    if backend_mode not in {"api", "local", "plan"}:
        return _error("INVALID_BACKEND", "synthesis_backend must be one of: api, local, plan")
    if budget < 0 or (budget <= 0 and backend_mode == "api"):
        return _error("INVALID_BUDGET", "budget must be positive")
    if backend_mode == "plan" and not plan:
        return _error("INVALID_BACKEND", "plan is required when synthesis_backend='plan'")

    backend: consult_core.ConsultSynthesisBackend | None = None
    requested_experts = list(experts or [])
    try:
        backend = consult_core.build_synthesis_backend(
            use_local=backend_mode == "local",
            local_model=local_model,
            plan_backend=plan if backend_mode == "plan" else None,
            plan_model=plan_model,
        )
        result = await consult_core.run_consult(
            question,
            requested_experts,
            max_experts,
            budget,
            synthesis_client=backend.client,
            synthesis_model=backend.model,
            synthesis_provider=backend.provider,
            allow_live_fallback=backend.allow_live_fallback,
        )
    except consult_core.ConsultBackendError as exc:
        return _error("CONSULT_BACKEND_UNAVAILABLE", str(exc))
    except (OSError, KeyError, ValueError, DeeprError) as exc:
        if backend is not None:
            record_consult_trace(
                question=question,
                requested_experts=requested_experts,
                max_experts=max_experts,
                budget=budget,
                capacity=_capacity_payload(backend_mode, backend),
                failure={"stage": "run_consult", "error_type": type(exc).__name__, "message": str(exc)},
            )
        return _error("CONSULT_FAILED", str(exc))

    payload = consult_core.build_consult_payload(question, result)
    payload["capacity"] = _capacity_payload(backend_mode, backend)
    payload["trace"] = record_consult_trace(
        question=question,
        requested_experts=requested_experts,
        max_experts=max_experts,
        budget=budget,
        payload=payload,
        result=result,
        capacity=payload["capacity"],
    )
    return payload
