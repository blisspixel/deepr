"""MCP helper for expert council consultation."""

from __future__ import annotations

import asyncio
from math import isfinite
from typing import Any

from deepr.experts import consult as consult_core
from deepr.experts.consult_transaction import (
    DEFAULT_CONSULT_MAX_ELAPSED_SECONDS,
    MAX_CONSULT_MAX_ELAPSED_SECONDS,
    ConsultElapsedLimitError,
    ConsultStorageError,
    execute_consult_transaction,
    requested_consult_capacity,
)

CONSULT_EXPERTS_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "schema_version",
        "kind",
        "contract",
        "question",
        "answer",
        "experts_consulted",
        "perspectives",
        "agreements",
        "disagreements",
        "cost_usd",
        "capacity",
        "trace",
        "collaboration",
    ],
    "properties": {
        "schema_version": {"const": consult_core.CONSULT_SCHEMA_VERSION},
        "kind": {"const": consult_core.CONSULT_KIND},
        "synthesis_status": {"type": "string"},
        "synthesis_error_type": {"type": "string"},
        "synthesis_stop_reason": {"type": "string"},
        "cost_usd": {"type": "number", "minimum": 0},
        "capacity": {
            "type": "object",
            "required": ["synthesis_backend", "provider", "model", "live_metered_fallback"],
            "properties": {
                "synthesis_backend": {"type": "string", "enum": ["api", "local", "plan"]},
                "provider": {"type": "string"},
                "model": {"type": ["string", "null"]},
                "live_metered_fallback": {"type": "boolean"},
            },
            "additionalProperties": True,
        },
    },
    "additionalProperties": True,
}

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
        "provider": {
            "type": "string",
            "enum": ["openai", "anthropic"],
            "description": "API synthesis provider when synthesis_backend='api'. Defaults to openai.",
        },
        "model": {
            "type": "string",
            "description": "API synthesis model when synthesis_backend='api'.",
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
        "max_elapsed_seconds": {
            "type": "number",
            "exclusiveMinimum": 0,
            "maximum": MAX_CONSULT_MAX_ELAPSED_SECONDS,
            "default": DEFAULT_CONSULT_MAX_ELAPSED_SECONDS,
            "description": (
                "Cumulative ceiling for cancellable consult work and lifecycle checkpoints. "
                "Durable writes are awaited off the event loop and lock waits are bounded separately; "
                "no backend fallback occurs."
            ),
        },
    },
    "required": ["question"],
}


def _error(code: str, message: str, *, retryable: bool = False, trace_id: str = "") -> dict[str, Any]:
    payload = {
        "error_code": code,
        "category": "internal",
        "retryable": retryable,
        "message": message,
    }
    if trace_id:
        payload["trace_id"] = trace_id
    return payload


def _runtime_type_error(
    *,
    question: object,
    synthesis_backend: object,
    experts: object,
    budget: object,
    max_elapsed_seconds: object,
    provider: object,
    model: object,
    local_model: object,
    plan: object,
    plan_model: object,
) -> dict[str, Any] | None:
    if not isinstance(question, str):
        return _error("INVALID_QUESTION", "question must be a string")
    if not isinstance(synthesis_backend, str):
        return _error("INVALID_BACKEND", "synthesis_backend must be one of: api, local, plan")
    if experts is not None and not isinstance(experts, list):
        return _error("INVALID_EXPERT_LIMIT", "experts must be an array of strings")
    if isinstance(experts, list) and any(not isinstance(expert, str) for expert in experts):
        return _error("INVALID_EXPERT_LIMIT", "experts must be an array of strings")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)):
        return _error("INVALID_BUDGET", "budget must be positive")
    if isinstance(max_elapsed_seconds, bool) or not isinstance(max_elapsed_seconds, (int, float)):
        return _error(
            "INVALID_ELAPSED_LIMIT",
            "max_elapsed_seconds must be finite, greater than zero, and no more than 21600",
        )
    optional_strings = (provider, model, local_model, plan, plan_model)
    if any(value is not None and not isinstance(value, str) for value in optional_strings):
        return _error(
            "INVALID_BACKEND",
            "provider, model, local_model, plan, and plan_model must be strings when provided",
        )
    return None


def _request_validation_error(
    *,
    backend_mode: str,
    experts: list[str] | None,
    max_experts: int,
    budget: float,
    provider: str | None,
    model: str | None,
    plan: str | None,
    max_elapsed_seconds: float,
) -> dict[str, Any] | None:
    if backend_mode not in {"api", "local", "plan"}:
        return _error("INVALID_BACKEND", "synthesis_backend must be one of: api, local, plan")
    if isinstance(max_experts, bool) or not isinstance(max_experts, int) or not 1 <= max_experts <= 10:
        return _error("INVALID_EXPERT_LIMIT", "max_experts must be an integer between 1 and 10")
    if len(experts or []) > 10:
        return _error("INVALID_EXPERT_LIMIT", "explicit expert roster cannot exceed 10")
    if isinstance(budget, bool) or not isfinite(budget) or budget < 0 or (budget <= 0 and backend_mode == "api"):
        return _error("INVALID_BUDGET", "budget must be positive")
    if (
        isinstance(max_elapsed_seconds, bool)
        or not isfinite(max_elapsed_seconds)
        or max_elapsed_seconds <= 0
        or max_elapsed_seconds > MAX_CONSULT_MAX_ELAPSED_SECONDS
    ):
        return _error(
            "INVALID_ELAPSED_LIMIT",
            "max_elapsed_seconds must be finite, greater than zero, and no more than 21600",
        )
    if backend_mode == "plan" and not plan:
        return _error("INVALID_BACKEND", "plan is required when synthesis_backend='plan'")
    if backend_mode != "api" and (provider or model):
        return _error("INVALID_BACKEND", "provider and model are only valid when synthesis_backend='api'")
    return None


def _requested_capacity(
    *,
    backend_mode: str,
    provider: str | None,
    model: str | None,
    local_model: str | None,
    plan: str | None,
    plan_model: str | None,
) -> dict[str, Any]:
    if backend_mode == "local":
        capacity_provider = "local"
        capacity_model = local_model or ""
    elif backend_mode == "plan":
        capacity_provider = f"plan_quota:{plan}"
        capacity_model = plan_model or ""
    else:
        capacity_provider = provider or "openai"
        capacity_model = model or ""
    return requested_consult_capacity(
        backend_mode=backend_mode,
        provider=capacity_provider,
        model=capacity_model,
    )


async def consult_experts_tool(
    *,
    question: str,
    experts: list[str] | None = None,
    max_experts: int = 3,
    budget: float = 2.0,
    synthesis_backend: str = "api",
    provider: str | None = None,
    model: str | None = None,
    local_model: str | None = None,
    plan: str | None = None,
    plan_model: str | None = None,
    max_elapsed_seconds: float = DEFAULT_CONSULT_MAX_ELAPSED_SECONDS,
) -> dict[str, Any]:
    """Run the MCP expert council consult tool."""
    runtime_error = _runtime_type_error(
        question=question,
        synthesis_backend=synthesis_backend,
        experts=experts,
        budget=budget,
        max_elapsed_seconds=max_elapsed_seconds,
        provider=provider,
        model=model,
        local_model=local_model,
        plan=plan,
        plan_model=plan_model,
    )
    if runtime_error is not None:
        return runtime_error

    backend_mode = synthesis_backend.strip().lower()
    validation_error = _request_validation_error(
        backend_mode=backend_mode,
        experts=experts,
        max_experts=max_experts,
        budget=budget,
        provider=provider,
        model=model,
        plan=plan,
        max_elapsed_seconds=max_elapsed_seconds,
    )
    if validation_error is not None:
        return validation_error

    requested_experts = list(experts or [])
    capacity_request = _requested_capacity(
        backend_mode=backend_mode,
        provider=provider,
        model=model,
        local_model=local_model,
        plan=plan,
        plan_model=plan_model,
    )

    async def build_backend() -> consult_core.ConsultSynthesisBackend:
        resolved_local_model = local_model
        if backend_mode == "local" and not resolved_local_model:
            from deepr.backends.local import default_local_model_async

            resolved_local_model = await default_local_model_async()
        return await asyncio.to_thread(
            consult_core.build_synthesis_backend,
            use_local=backend_mode == "local",
            local_model=resolved_local_model,
            plan_backend=plan if backend_mode == "plan" else None,
            plan_model=plan_model,
            api_provider=provider if backend_mode == "api" else None,
            api_model=model if backend_mode == "api" else None,
        )

    try:
        return await execute_consult_transaction(
            question=question,
            requested_experts=requested_experts,
            max_experts=max_experts,
            budget=budget,
            backend_mode=backend_mode,
            backend_factory=build_backend,
            requested_capacity=capacity_request,
            max_elapsed_seconds=max_elapsed_seconds,
            run_consult_fn=consult_core.run_consult,
        )
    except consult_core.ConsultBackendError as exc:
        return _error(
            "CONSULT_BACKEND_UNAVAILABLE",
            str(exc),
            trace_id=str(getattr(exc, "consult_trace_id", "")),
        )
    except ConsultElapsedLimitError as exc:
        return _error(
            "CONSULT_ELAPSED_LIMIT",
            str(exc),
            retryable=exc.retryable,
            trace_id=exc.trace_id,
        )
    except ConsultStorageError as exc:
        return _error(
            exc.error_code,
            str(exc),
            retryable=exc.retryable,
            trace_id=exc.trace_id,
        )
    except Exception as exc:
        return _error(
            "CONSULT_FAILED",
            str(exc),
            trace_id=str(getattr(exc, "consult_trace_id", "")),
        )
