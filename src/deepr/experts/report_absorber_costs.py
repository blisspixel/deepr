"""Pure request bounds for metered report-absorption completions."""

from __future__ import annotations

import json
from math import isfinite
from typing import Any

from deepr.experts.report_absorber_contracts import ReportAbsorberCostError

_CHAT_PROTOCOL_TOKEN_ALLOWANCE = 4096
_OPERATION_OUTPUT_TOKEN_LIMITS = {
    "extraction": 8192,
    "contradiction": 16,
    "contradiction_confirmation": 384,
    "dedup": 16,
    "adjudication": 1024,
}


def bounded_metered_completion_kwargs(
    *,
    operation: str,
    model: str,
    call_ceiling: float,
    kwargs: dict[str, Any],
) -> tuple[dict[str, Any], float]:
    """Bound one OpenAI request so its worst-case token bill fits a hold."""
    from deepr.providers.registry import get_model_capability

    capability = get_model_capability("openai", model)
    if capability is None:
        raise ReportAbsorberCostError(f"Metered absorb model {model!r} has no exact OpenAI pricing contract")
    input_rate = float(capability.input_cost_per_1m)
    output_rate = float(capability.output_cost_per_1m)
    if not all(isfinite(rate) and rate > 0 for rate in (input_rate, output_rate)):
        raise ReportAbsorberCostError(f"Metered absorb model {model!r} has no positive token pricing contract")

    bounded = dict(kwargs)
    request_model = str(bounded.get("model") or model)
    if request_model != model:
        raise ReportAbsorberCostError(
            f"Metered absorb request model {request_model!r} does not match accounted model {model!r}"
        )
    if "max_tokens" in bounded:
        raise ReportAbsorberCostError("Metered absorb requires max_completion_tokens, not legacy max_tokens")

    priced_payload = {
        "messages": bounded.get("messages", []),
        "response_format": bounded.get("response_format"),
        "reasoning_effort": bounded.get("reasoning_effort"),
    }
    payload_bytes = len(
        json.dumps(priced_payload, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
    )
    input_token_ceiling = payload_bytes + _CHAT_PROTOCOL_TOKEN_ALLOWANCE
    if capability.context_window > 0 and input_token_ceiling >= capability.context_window:
        raise ReportAbsorberCostError(f"Metered absorb {operation} input exceeds the priced context bound for {model}")
    input_cost_ceiling = (input_token_ceiling / 1_000_000) * input_rate
    output_budget = call_ceiling - input_cost_ceiling
    max_from_cost = int((output_budget * 1_000_000) / output_rate)
    max_from_context = max(int(capability.context_window) - input_token_ceiling, 0)
    requested_cap = bounded.get("max_completion_tokens")
    if requested_cap is not None:
        try:
            requested_limit = int(requested_cap)
        except (TypeError, ValueError) as exc:
            raise ReportAbsorberCostError("max_completion_tokens must be a positive integer") from exc
    else:
        requested_limit = _OPERATION_OUTPUT_TOKEN_LIMITS.get(operation, 1024)
    output_token_ceiling = min(requested_limit, max_from_cost, max_from_context)
    if output_token_ceiling < 1:
        raise ReportAbsorberCostError(
            f"Metered absorb {operation} input leaves no output token inside the ${call_ceiling:.6f} call ceiling"
        )
    bounded["max_completion_tokens"] = output_token_ceiling
    worst_case_cost = input_cost_ceiling + (output_token_ceiling / 1_000_000) * output_rate
    if worst_case_cost > call_ceiling + 1e-12:
        raise ReportAbsorberCostError("Metered absorb request bound exceeds its reserved call ceiling")
    return bounded, worst_case_cost
