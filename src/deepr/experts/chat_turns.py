"""Small helpers for expert chat turn accounting and routing traces."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from deepr.experts.router import ModelConfig
from deepr.experts.thought_stream import ThoughtType


def chat_generation_estimate(selected_model: ModelConfig) -> float:
    """Return a conservative preflight estimate for one expert chat turn."""
    estimate = float(getattr(selected_model, "cost_estimate", 0.0) or 0.0)
    if estimate <= 0:
        try:
            from deepr.providers.registry import get_cost_estimate

            estimate = float(get_cost_estimate(selected_model.model))
        except Exception:
            estimate = 0.05
    return max(estimate, 0.01)


def check_chat_generation_budget(
    cost_safety: Any,
    session_id: str,
    selected_model: ModelConfig,
) -> tuple[bool, str, float]:
    """Check cost safety before dispatching any metered chat-turn path."""
    estimated_cost = chat_generation_estimate(selected_model)
    allowed, reason, _needs_confirmation = cost_safety.check_operation(
        session_id=session_id,
        operation_type="expert_chat",
        estimated_cost=estimated_cost,
        require_confirmation=False,
    )
    return allowed, reason, estimated_cost


def chat_generation_budget_denial(
    selected_model: ModelConfig,
    reason: str,
    estimated_cost: float,
) -> dict[str, Any]:
    """Build the reasoning-trace record for a denied chat turn."""
    return {
        "step": "chat_generation_budget",
        "timestamp": datetime.now(UTC).isoformat(),
        "selected_provider": selected_model.provider,
        "selected_model": selected_model.model,
        "estimated_cost": estimated_cost,
        "allowed": False,
        "reason": reason,
    }


def record_named_chat_cost(
    *,
    cost_safety: Any,
    session_id: str,
    usage: Any | None,
    model_name: str,
    operation_type: str,
    fallback_cost: float,
    cost_calculator: Callable[[Any, str], float],
    details: str = "",
) -> float:
    """Record cost for auxiliary chat calls that keep their own operation name."""
    cost = cost_calculator(usage, model_name) if usage else fallback_cost
    cost_safety.record_cost(
        session_id=session_id,
        operation_type=operation_type,
        actual_cost=cost,
        provider="openai",
        model=model_name,
        tokens_input=getattr(usage, "prompt_tokens", 0) if usage else 0,
        tokens_output=getattr(usage, "completion_tokens", 0) if usage else 0,
        details=details,
    )
    return cost


def record_model_routing(
    *,
    reasoning_trace: list[dict[str, Any]],
    thought_stream: Any,
    selected_model: ModelConfig,
    query: str,
) -> None:
    """Append the standard model-routing trace and thought-stream event."""
    reasoning_trace.append(
        {
            "step": "model_routing",
            "timestamp": datetime.now(UTC).isoformat(),
            "query": query[:100],
            "selected_provider": selected_model.provider,
            "selected_model": selected_model.model,
            "cost_estimate": selected_model.cost_estimate,
            "confidence": selected_model.confidence,
            "reasoning_effort": selected_model.reasoning_effort,
        }
    )
    thought_stream.emit(
        ThoughtType.PLAN_STEP,
        f"Selected model: {selected_model.model}",
        private_payload={
            "provider": selected_model.provider,
            "cost_estimate": selected_model.cost_estimate,
            "reasoning_effort": selected_model.reasoning_effort,
        },
        confidence=selected_model.confidence,
    )
