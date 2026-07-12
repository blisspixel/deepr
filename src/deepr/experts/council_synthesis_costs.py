"""Exact pricing and conservative bounds for metered council synthesis."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from math import isfinite
from typing import Any

# UTF-8 payload bytes are a conservative token ceiling for the visible request.
# This additional allowance covers provider chat wrappers and hidden protocol
# tokens without relying on a model-specific tokenizer at the spend boundary.
_CHAT_PROTOCOL_TOKEN_ALLOWANCE = 4096


class CouncilSynthesisCostError(ValueError):
    """Raised when metered synthesis cannot be bounded before dispatch."""


@dataclass(frozen=True)
class SynthesisCostBound:
    """Exact rates and conservative token ceilings for one synthesis call."""

    provider: str
    model: str
    input_rate_per_1m: float
    output_rate_per_1m: float
    input_token_ceiling: int
    output_token_ceiling: int
    worst_case_cost_usd: float
    cached_input_rate_per_1m: float | None = None

    def conservative_usage(self, *, reason: str) -> dict[str, Any]:
        return {
            "cost": self.worst_case_cost_usd,
            "tokens_input": self.input_token_ceiling,
            "tokens_output": self.output_token_ceiling,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cost_estimated": True,
            "cost_estimate_reason": reason,
            "input_token_ceiling": self.input_token_ceiling,
            "output_token_ceiling": self.output_token_ceiling,
            "cost_bound_exceeded": False,
            "cost_bound_violation": "",
        }


def _exact_capability(provider: str, model: str) -> Any:
    from deepr.providers.registry import get_model_capability

    capability = get_model_capability(provider, model)
    if capability is None:
        raise CouncilSynthesisCostError(
            f"Metered council synthesis model {provider}/{model} has no exact pricing contract"
        )
    rates = (float(capability.input_cost_per_1m), float(capability.output_cost_per_1m))
    if not all(isfinite(rate) and rate > 0 for rate in rates):
        raise CouncilSynthesisCostError(
            f"Metered council synthesis model {provider}/{model} has no positive token pricing contract"
        )
    cached_rate = getattr(capability, "cached_input_cost_per_1m", None)
    if cached_rate is not None and (not isfinite(float(cached_rate)) or float(cached_rate) < 0):
        raise CouncilSynthesisCostError(
            f"Metered council synthesis model {provider}/{model} has an invalid cached-input pricing contract"
        )
    return capability


def _anthropic_cache_write_rate(model: str, input_rate: float) -> float:
    from deepr.providers.anthropic_provider import ANTHROPIC_CACHE_PRICING

    for registered_model, rates in ANTHROPIC_CACHE_PRICING.items():
        if model.startswith(registered_model):
            return float(rates["cache_write"])
    return input_rate * 1.25


def metered_synthesis_cost_bound(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    output_token_ceiling: int,
    budget: float,
) -> SynthesisCostBound:
    """Return a worst-case bound or reject before metered dispatch."""
    if provider not in {"openai", "anthropic"}:
        raise CouncilSynthesisCostError(f"Unsupported metered council synthesis provider {provider!r}")
    capability = _exact_capability(provider, model)
    input_rate = float(capability.input_cost_per_1m)
    output_rate = float(capability.output_cost_per_1m)
    cached_input_rate = getattr(capability, "cached_input_cost_per_1m", None)
    cached_input_rate = float(cached_input_rate) if cached_input_rate is not None else None
    if provider == "anthropic":
        priced_input_rate = max(input_rate, _anthropic_cache_write_rate(model, input_rate))
    else:
        priced_input_rate = max(input_rate, cached_input_rate or 0.0)
    payload: dict[str, Any] = {
        "model": model,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    if provider == "openai":
        payload["messages"] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payload["temperature"] = 0.3
    payload_bytes = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    input_token_ceiling = payload_bytes + _CHAT_PROTOCOL_TOKEN_ALLOWANCE
    context_window = int(capability.context_window)
    if context_window <= 0 or input_token_ceiling + output_token_ceiling > context_window:
        raise CouncilSynthesisCostError(
            f"Metered council synthesis input exceeds the priced context bound for {provider}/{model}"
        )
    worst_case_cost = (input_token_ceiling / 1_000_000) * priced_input_rate + (
        output_token_ceiling / 1_000_000
    ) * output_rate
    if not isfinite(budget) or budget < 0 or worst_case_cost > budget + 1e-12:
        raise CouncilSynthesisCostError(
            f"Metered council synthesis worst-case cost ${worst_case_cost:.6f} exceeds "
            f"the ${budget:.6f} synthesis budget slice"
        )
    return SynthesisCostBound(
        provider=provider,
        model=model,
        input_rate_per_1m=input_rate,
        output_rate_per_1m=output_rate,
        input_token_ceiling=input_token_ceiling,
        output_token_ceiling=output_token_ceiling,
        worst_case_cost_usd=worst_case_cost,
        cached_input_rate_per_1m=cached_input_rate,
    )


def _observed_usage_int(usage: Any, *names: str) -> tuple[int, str]:
    missing = object()
    for name in names:
        value: Any = getattr(usage, name, missing)
        if value is missing or value is None:
            continue
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not numeric or not isfinite(float(value)) or not float(value).is_integer() or int(value) < 0:
            return 0, "invalid"
        return int(value), "available"
    return 0, "missing"


def _bound_violation(
    bound: SynthesisCostBound,
    *,
    input_tokens: int,
    output_tokens: int,
    cost: float,
) -> tuple[bool, str]:
    violations: list[str] = []
    if input_tokens > bound.input_token_ceiling:
        violations.append("input_tokens")
    if output_tokens > bound.output_token_ceiling:
        violations.append("output_tokens")
    if cost > bound.worst_case_cost_usd + 1e-12:
        violations.append("cost_usd")
    return bool(violations), ",".join(violations)


def openai_completion_usage(usage: Any, bound: SynthesisCostBound) -> dict[str, Any]:
    """Price observed OpenAI usage, conservatively settling absent usage."""
    if usage is None:
        return bound.conservative_usage(reason="usage_unavailable")
    input_tokens, input_state = _observed_usage_int(usage, "prompt_tokens", "input_tokens")
    output_tokens, output_state = _observed_usage_int(usage, "completion_tokens", "output_tokens")
    states = {input_state, output_state}
    if "invalid" in states:
        return bound.conservative_usage(reason="provider_usage_invalid")
    if "missing" in states or input_tokens <= 0:
        return bound.conservative_usage(reason="provider_usage_incomplete")

    details = getattr(usage, "prompt_tokens_details", None)
    cached_value_missing = object()
    if isinstance(details, dict):
        cached_value = details.get("cached_tokens", cached_value_missing)
    else:
        cached_value = getattr(details, "cached_tokens", cached_value_missing)

    cache_details_state = (
        "available"
        if details is not None and cached_value is not cached_value_missing and cached_value is not None
        else "unavailable"
    )
    cached_tokens = 0
    if cache_details_state == "available":
        numeric_cached_value = isinstance(cached_value, (int, float)) and not isinstance(cached_value, bool)
        integer_cached_value = numeric_cached_value and float(cached_value).is_integer()
        if not integer_cached_value or not 0 <= int(cached_value) <= input_tokens:
            cache_details_state = "invalid"
        else:
            cached_tokens = int(cached_value)

    uncached_tokens = input_tokens - cached_tokens
    cost_estimated = input_tokens > 0 and cache_details_state != "available"
    estimate_reason = f"provider_usage_cache_details_{cache_details_state}" if cost_estimated else "provider_usage"
    cached_rate = bound.cached_input_rate_per_1m
    uncached_rate = bound.input_rate_per_1m
    if cache_details_state != "available":
        # Preserve trustworthy provider totals even when the optional cache
        # breakdown is unusable. Pricing every observed input token at the
        # higher known input rate is conservative and still exposes an
        # actual-over-bound provider response.
        uncached_rate = max(uncached_rate, cached_rate or 0.0)
    if cached_tokens > 0 and cached_rate is None:
        # Full input pricing is a conservative ceiling when the provider reports
        # cached tokens but the exact model contract lacks a cached rate.
        cached_rate = bound.input_rate_per_1m
        cost_estimated = True
        estimate_reason = "provider_usage_cached_rate_unavailable"
    elif cached_rate is None:
        cached_rate = bound.input_rate_per_1m

    cost = (
        (uncached_tokens / 1_000_000) * uncached_rate
        + (cached_tokens / 1_000_000) * cached_rate
        + (output_tokens / 1_000_000) * bound.output_rate_per_1m
    )
    bound_exceeded, violation = _bound_violation(
        bound,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
    )
    return {
        "cost": cost,
        "tokens_input": input_tokens,
        "tokens_output": output_tokens,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": cached_tokens,
        "cost_estimated": cost_estimated,
        "cost_estimate_reason": estimate_reason,
        "input_token_ceiling": bound.input_token_ceiling,
        "output_token_ceiling": bound.output_token_ceiling,
        "cost_bound_exceeded": bound_exceeded,
        "cost_bound_violation": violation,
    }


def anthropic_completion_usage(usage: Any, bound: SynthesisCostBound) -> dict[str, Any]:
    """Price observed Anthropic usage across regular and cache buckets."""
    if usage is None:
        return bound.conservative_usage(reason="usage_unavailable")
    input_tokens, input_state = _observed_usage_int(usage, "input_tokens")
    output_tokens, output_state = _observed_usage_int(usage, "output_tokens")
    cache_creation_tokens, creation_state = _observed_usage_int(usage, "cache_creation_input_tokens")
    cache_read_tokens, read_state = _observed_usage_int(usage, "cache_read_input_tokens")
    if "invalid" in {input_state, output_state, creation_state, read_state}:
        return bound.conservative_usage(reason="provider_usage_invalid")
    if "missing" in {input_state, output_state}:
        return bound.conservative_usage(reason="provider_usage_incomplete")
    cache_creation_tokens = 0 if creation_state == "missing" else cache_creation_tokens
    cache_read_tokens = 0 if read_state == "missing" else cache_read_tokens
    if input_tokens + cache_creation_tokens + cache_read_tokens <= 0:
        return bound.conservative_usage(reason="provider_usage_incomplete")
    cache_write_rate = _anthropic_cache_write_rate(bound.model, bound.input_rate_per_1m)
    cache_read_rate = bound.input_rate_per_1m * 0.10
    cost = (
        (input_tokens / 1_000_000) * bound.input_rate_per_1m
        + (output_tokens / 1_000_000) * bound.output_rate_per_1m
        + (cache_creation_tokens / 1_000_000) * cache_write_rate
        + (cache_read_tokens / 1_000_000) * cache_read_rate
    )
    total_input_tokens = input_tokens + cache_creation_tokens + cache_read_tokens
    bound_exceeded, violation = _bound_violation(
        bound,
        input_tokens=total_input_tokens,
        output_tokens=output_tokens,
        cost=cost,
    )
    return {
        "cost": cost,
        "tokens_input": total_input_tokens,
        "tokens_output": output_tokens,
        "cache_creation_input_tokens": cache_creation_tokens,
        "cache_read_input_tokens": cache_read_tokens,
        "cost_estimated": False,
        "cost_estimate_reason": "provider_usage",
        "input_token_ceiling": bound.input_token_ceiling,
        "output_token_ceiling": bound.output_token_ceiling,
        "cost_bound_exceeded": bound_exceeded,
        "cost_bound_violation": violation,
    }


def failed_synthesis(
    error: BaseException,
    *,
    cost_bound: SynthesisCostBound | None,
    dispatched: bool,
) -> dict[str, Any]:
    """Build a typed failure with conservative cost after dispatch."""
    usage = (
        cost_bound.conservative_usage(reason="post_dispatch_failure")
        if dispatched and cost_bound is not None
        else {
            "cost": 0.0,
            "tokens_input": 0,
            "tokens_output": 0,
            "cost_estimated": False,
            "cost_estimate_reason": "owned_capacity_failure" if dispatched else "pre_dispatch_failure",
        }
    )
    return {
        "text": "Synthesis unavailable.",
        "agreements": [],
        "disagreements": [],
        **usage,
        "dispatch_status": "outcome_unknown" if dispatched else "not_dispatched",
        "synthesis_status": "failed",
        "synthesis_error_type": type(error).__name__,
    }


def _ledger_metadata(
    synthesis: dict[str, Any],
    *,
    expert_count: int,
    perspective_count: int,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "expert_count": expert_count,
        "perspective_count": perspective_count,
        "estimated": bool(synthesis.get("cost_estimated", False)),
        "cost_bound_exceeded": bool(synthesis.get("cost_bound_exceeded", False)),
    }
    for field_name in (
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "input_token_ceiling",
        "output_token_ceiling",
    ):
        field_value = int(synthesis.get(field_name, 0) or 0)
        if field_value > 0:
            metadata[field_name] = field_value
    for field_name in (
        "provider_request_id",
        "stop_reason",
        "cost_estimate_reason",
        "dispatch_status",
        "cost_bound_violation",
    ):
        field_text = str(synthesis.get(field_name, "") or "")
        if field_text:
            metadata[field_name] = field_text
    return metadata


def record_synthesis_cost(
    cost_safety: Any,
    *,
    council_session_id: str,
    reservation_id: str,
    synthesis: dict[str, Any],
    provider: str,
    model: str,
    expert_count: int,
    perspective_count: int,
) -> bool:
    """Settle one positive synthesis cost into the existing reservation."""
    synthesis_cost = _validated_synthesis_cost(synthesis)
    if synthesis_cost <= 0:
        return False
    cost_safety.record_cost(
        session_id=council_session_id,
        operation_type="council_synthesis",
        actual_cost=synthesis_cost,
        provider=provider,
        model=model,
        tokens_input=int(synthesis.get("tokens_input", 0) or 0),
        tokens_output=int(synthesis.get("tokens_output", 0) or 0),
        request_id=council_session_id,
        idempotency_key=f"{council_session_id}:synthesis",
        source="expert_council.synthesis",
        metadata=_ledger_metadata(
            synthesis,
            expert_count=expert_count,
            perspective_count=perspective_count,
        ),
        reservation_id=reservation_id,
        require_ledger=True,
    )
    return True


def _validated_synthesis_cost(synthesis: dict[str, Any]) -> float:
    value = synthesis.get("cost", 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CouncilSynthesisCostError("council synthesis cost must be a finite non-negative number")
    cost = float(value)
    if not isfinite(cost) or cost < 0:
        raise CouncilSynthesisCostError("council synthesis cost must be a finite non-negative number")
    return cost


def attach_synthesis_settlement(
    error: BaseException,
    synthesis: dict[str, Any],
    *,
    council_session_id: str,
    settled: bool,
) -> dict[str, Any]:
    """Attach path-safe settlement state to a propagated operation error."""
    settlement = synthesis_accounting_envelope(synthesis)
    settlement["idempotency_key"] = f"{council_session_id}:synthesis"
    settlement["settled"] = settled
    error.__dict__["council_synthesis_settlement"] = settlement
    return settlement


def _attach_settlement_recovery(
    error: BaseException,
    *,
    council_session_id: str,
    reservation_id: str,
) -> None:
    error.__dict__["council_synthesis_recovery"] = {
        "action": "retry_settlement_only",
        "do_not_retry_provider": True,
        "idempotency_key": f"{council_session_id}:synthesis",
        "reservation_id": reservation_id,
    }


def synthesis_accounting_envelope(synthesis: dict[str, Any]) -> dict[str, Any]:
    """Return only bounded accounting fields safe to attach to an error."""
    fields = (
        "cost",
        "tokens_input",
        "tokens_output",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "cost_estimated",
        "cost_estimate_reason",
        "input_token_ceiling",
        "output_token_ceiling",
        "cost_bound_exceeded",
        "cost_bound_violation",
        "dispatch_status",
        "synthesis_status",
        "synthesis_error_type",
    )
    return {field: synthesis[field] for field in fields if field in synthesis}


async def _finish_settlement_task(
    task: asyncio.Task[bool],
    cancellation_error: BaseException,
) -> bool:
    """Await a shielded writer to completion despite repeated cancellation."""
    repeated_cancellations = 0
    while True:
        try:
            result = await asyncio.shield(task)
            if repeated_cancellations:
                cancellation_error.__dict__["council_synthesis_repeated_cancellations"] = repeated_cancellations
            return result
        except asyncio.CancelledError:
            repeated_cancellations += 1


def _settlement_task(
    cost_safety: Any,
    *,
    council_session_id: str,
    reservation_id: str,
    synthesis: dict[str, Any],
    provider: str,
    model: str,
    expert_count: int,
    perspective_count: int,
) -> asyncio.Task[bool]:
    return asyncio.create_task(
        asyncio.to_thread(
            record_synthesis_cost,
            cost_safety,
            council_session_id=council_session_id,
            reservation_id=reservation_id,
            synthesis=synthesis,
            provider=provider,
            model=model,
            expert_count=expert_count,
            perspective_count=perspective_count,
        ),
        name=f"council-cost-settlement-{council_session_id}",
    )


async def settle_synthesis_cost(
    cost_safety: Any,
    *,
    council_session_id: str,
    reservation_id: str,
    synthesis: dict[str, Any],
    provider: str,
    model: str,
    expert_count: int,
    perspective_count: int,
) -> bool:
    """Settle off-loop and finish the durable writer before cancellation exits."""
    task = _settlement_task(
        cost_safety,
        council_session_id=council_session_id,
        reservation_id=reservation_id,
        synthesis=synthesis,
        provider=provider,
        model=model,
        expert_count=expert_count,
        perspective_count=perspective_count,
    )
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation_error:
        try:
            recorded = await _finish_settlement_task(task, cancellation_error)
        except Exception as settlement_error:
            attach_synthesis_settlement(
                cancellation_error,
                synthesis,
                council_session_id=council_session_id,
                settled=False,
            )
            cancellation_error.__dict__["council_synthesis_settlement_error"] = settlement_error
            _attach_settlement_recovery(
                cancellation_error,
                council_session_id=council_session_id,
                reservation_id=reservation_id,
            )
            cancellation_error.add_note(f"Council synthesis cancellation settlement failed: {settlement_error}")
        else:
            settlement = attach_synthesis_settlement(
                cancellation_error,
                synthesis,
                council_session_id=council_session_id,
                settled=recorded,
            )
            if recorded:
                cancellation_error.add_note(
                    f"Metered council synthesis cancellation settled as ${float(settlement['cost']):.6f}."
                )
        raise
    except Exception as settlement_error:
        attach_synthesis_settlement(
            settlement_error,
            synthesis,
            council_session_id=council_session_id,
            settled=False,
        )
        _attach_settlement_recovery(
            settlement_error,
            council_session_id=council_session_id,
            reservation_id=reservation_id,
        )
        raise


async def settle_cancelled_synthesis(
    cancellation_error: BaseException,
    cost_safety: Any,
    *,
    council_session_id: str,
    reservation_id: str,
    provider: str,
    model: str,
    expert_count: int,
    perspective_count: int,
) -> str:
    """Settle attached ambiguous cost while preserving cancellation."""
    settlement = cancellation_error.__dict__.get("council_synthesis_settlement")
    if not isinstance(settlement, dict):
        return reservation_id
    if settlement.get("settled") is True:
        return ""
    settlement["idempotency_key"] = f"{council_session_id}:synthesis"
    task = _settlement_task(
        cost_safety,
        council_session_id=council_session_id,
        reservation_id=reservation_id,
        synthesis=settlement,
        provider=provider,
        model=model,
        expert_count=expert_count,
        perspective_count=perspective_count,
    )
    try:
        recorded = await _finish_settlement_task(task, cancellation_error)
    except Exception as settlement_error:
        cancellation_error.__dict__["council_synthesis_settlement_error"] = settlement_error
        _attach_settlement_recovery(
            cancellation_error,
            council_session_id=council_session_id,
            reservation_id=reservation_id,
        )
        cancellation_error.add_note(f"Council synthesis cancellation settlement failed: {settlement_error}")
        return reservation_id
    if not recorded:
        return reservation_id
    settlement["settled"] = True
    cancellation_error.add_note(
        f"Metered council synthesis cancellation settled conservatively as ${float(settlement['cost']):.6f}."
    )
    return ""


__all__ = [
    "CouncilSynthesisCostError",
    "SynthesisCostBound",
    "anthropic_completion_usage",
    "attach_synthesis_settlement",
    "failed_synthesis",
    "metered_synthesis_cost_bound",
    "openai_completion_usage",
    "record_synthesis_cost",
    "settle_cancelled_synthesis",
    "settle_synthesis_cost",
    "synthesis_accounting_envelope",
]
