"""Deterministic request and cost ceilings for provider-backed research."""

from __future__ import annotations

import json
import math
from dataclasses import asdict

from deepr.core.costs import CostEstimate
from deepr.providers.base import ResearchRequest
from deepr.providers.registry_pricing import get_resolved_model_capability

_MAX_INPUT_TOKENS = 1_050_000
_MAX_OUTPUT_TOKENS = 128_000
_MAX_TOOL_CALLS = 256
_MAX_PROVIDER_REQUESTS = 8
_MAX_REQUEST_BYTES = 4 * 1024 * 1024
_PROVIDER_WIRE_OVERHEAD_BYTES = 4096

# Official OpenAI built-in tool prices checked 2026-07-12:
# https://developers.openai.com/api/docs/pricing
_OPENAI_WEB_SEARCH_CALL_USD = 0.025
_OPENAI_FILE_SEARCH_CALL_USD = 0.0025
_OPENAI_CODE_INTERPRETER_1G_SESSION_USD = 0.03

_BOUND_METADATA_FIELDS = {
    "research_max_input_tokens": "max_input_tokens",
    "research_max_output_tokens": "max_output_tokens",
    "research_max_tool_calls": "max_tool_calls",
    "research_max_provider_requests": "max_provider_requests",
    "research_max_request_bytes": "max_request_bytes",
}


class ResearchRequestBoundsError(ValueError):
    """A provider request cannot prove a complete finite spend envelope."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = False


def require_research_storage_accounting() -> None:
    """Block provider file or vector storage until its full lifecycle is priced."""
    raise ResearchRequestBoundsError(
        "Provider file and vector storage are disabled until upload, indexing, retention, retrieval, and cleanup costs "
        "share the research reservation. Use local source packs or local expert learning instead.",
        code="research_file_storage_unbounded",
    )


def require_research_parent_budget_accounting(operation: str) -> None:
    """Block a metered multi-call workflow without one durable parent ceiling."""
    raise ResearchRequestBoundsError(
        f"{operation} execution is disabled until every nested provider call is bound to one durable parent "
        "reservation with exact per-call settlement. Use a dry run or submit bounded research jobs one at a time.",
        code="research_parent_budget_unavailable",
    )


def require_metered_interface_accounting(operation: str) -> None:
    """Block a direct metered interface that does not use durable settlement."""
    raise ResearchRequestBoundsError(
        f"{operation} is disabled until its provider call reserves before dispatch, enforces an output ceiling, "
        "and settles usage to the canonical cost ledger. Use a local or explicitly bounded alternative.",
        code="metered_interface_accounting_unavailable",
    )


def _exact_positive_int(value: object, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > maximum:
        raise ResearchRequestBoundsError(
            f"{name} must be a positive integer no greater than {maximum}",
            code="invalid_research_request_bound",
        )
    return value


def _provider_key(provider: str) -> str:
    normalized = provider.lower().replace("_", "").replace("-", "")
    if "azurefoundry" in normalized:
        return "azure-foundry"
    if "azure" in normalized:
        return "azure"
    if "openai" in normalized:
        return "openai"
    if "anthropic" in normalized or "claude" in normalized:
        return "anthropic"
    if "gemini" in normalized or "google" in normalized:
        return "gemini"
    if "grok" in normalized or "xai" in normalized:
        return "xai"
    return normalized


def _canonical_request_bytes(request: ResearchRequest) -> bytes:
    try:
        return json.dumps(
            asdict(request),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ResearchRequestBoundsError(
            "Research request must be deterministically JSON serializable",
            code="research_request_not_serializable",
        ) from exc


def validate_research_request_bounds(request: ResearchRequest) -> int:
    """Validate finite bounds and return the canonical serialized byte size."""
    max_input_tokens = _exact_positive_int(request.max_input_tokens, "max_input_tokens", _MAX_INPUT_TOKENS)
    _exact_positive_int(request.max_output_tokens, "max_output_tokens", _MAX_OUTPUT_TOKENS)
    max_tool_calls = _exact_positive_int(request.max_tool_calls, "max_tool_calls", _MAX_TOOL_CALLS)
    _exact_positive_int(
        request.max_provider_requests,
        "max_provider_requests",
        _MAX_PROVIDER_REQUESTS,
    )
    max_request_bytes = _exact_positive_int(request.max_request_bytes, "max_request_bytes", _MAX_REQUEST_BYTES)
    if len(request.tools) > max_tool_calls:
        raise ResearchRequestBoundsError(
            "Research tool definitions exceed max_tool_calls",
            code="research_tool_definition_limit_exceeded",
        )
    serialized = _canonical_request_bytes(request)
    bounded_wire_bytes = len(serialized) + _PROVIDER_WIRE_OVERHEAD_BYTES
    if bounded_wire_bytes > max_request_bytes:
        raise ResearchRequestBoundsError(
            f"Serialized research request plus provider envelope is {bounded_wire_bytes} bytes, "
            f"above the {max_request_bytes}-byte ceiling",
            code="research_request_bytes_exceeded",
        )
    # One UTF-8 byte can encode no more than one model token. Counting every
    # serialized byte as a token is deliberately conservative and tokenizer
    # independent.
    if bounded_wire_bytes > max_input_tokens:
        raise ResearchRequestBoundsError(
            "Serialized research request exceeds the conservative input-token ceiling",
            code="research_input_tokens_exceeded",
        )
    return bounded_wire_bytes


def validate_provider_payload_bytes(payload: object, max_request_bytes: int) -> int:
    """Check the exact provider payload immediately before SDK dispatch."""
    _exact_positive_int(max_request_bytes, "max_request_bytes", _MAX_REQUEST_BYTES)
    try:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ResearchRequestBoundsError(
            "Provider research payload must be deterministically JSON serializable",
            code="research_provider_payload_not_serializable",
        ) from exc
    if len(serialized) > max_request_bytes:
        raise ResearchRequestBoundsError(
            f"Final provider research payload is {len(serialized)} bytes, above the {max_request_bytes}-byte ceiling",
            code="research_provider_payload_bytes_exceeded",
        )
    return len(serialized)


def _tool_cost_bound(request: ResearchRequest, provider: str, context_window: int) -> float:
    tool_types = {tool.type for tool in request.tools}
    if not tool_types:
        return 0.0
    if provider not in {"openai", "azure"}:
        raise ResearchRequestBoundsError(
            f"{provider or 'unknown'} research tools have no complete provider-enforced cost ceiling",
            code="research_tool_pricing_unbounded",
        )
    unsupported = tool_types.difference({"web_search_preview", "code_interpreter", "file_search"})
    if unsupported:
        raise ResearchRequestBoundsError(
            f"Research tool pricing is unavailable for: {', '.join(sorted(unsupported))}",
            code="research_tool_pricing_unbounded",
        )
    if "file_search" in tool_types:
        raise ResearchRequestBoundsError(
            "File-search storage duration and size are not yet covered by the research reservation",
            code="research_file_storage_unbounded",
        )
    if request.max_input_tokens < context_window:
        raise ResearchRequestBoundsError(
            "Built-in tool result tokens can use the model context window; max_input_tokens must cover it",
            code="research_tool_input_unbounded",
        )

    per_request = 0.0
    if "web_search_preview" in tool_types:
        per_request += request.max_tool_calls * _OPENAI_WEB_SEARCH_CALL_USD
    if "file_search" in tool_types:
        per_request += request.max_tool_calls * _OPENAI_FILE_SEARCH_CALL_USD
    if "code_interpreter" in tool_types:
        per_request += _OPENAI_CODE_INTERPRETER_1G_SESSION_USD
    return per_request * request.max_provider_requests


def bounded_research_cost_estimate(
    *,
    request: ResearchRequest,
    provider: str,
) -> CostEstimate:
    """Return a maximum cost that covers every permitted provider dispatch."""
    serialized_bytes = validate_research_request_bounds(request)
    provider_key = _provider_key(provider)
    model_key = request.model.lower()
    if request.document_ids:
        raise ResearchRequestBoundsError(
            "Provider document storage and retrieved-token costs are not yet covered by the research reservation",
            code="research_document_cost_unbounded",
        )
    if provider_key == "gemini" and "deep-research" in model_key:
        raise ResearchRequestBoundsError(
            "Gemini Deep Research runs an autonomous tool loop without provider-enforced total budget, output, or tool ceilings",
            code="gemini_deep_research_budget_unbounded",
        )
    if provider_key == "azure-foundry":
        raise ResearchRequestBoundsError(
            "Azure Foundry Agent runs do not expose the complete output and tool ceiling required for paid dispatch",
            code="azure_foundry_research_budget_unbounded",
        )
    if provider_key == "xai" and "multi-agent" in model_key:
        raise ResearchRequestBoundsError(
            "xAI multi-agent research fan-out is not yet covered by one durable parent reservation",
            code="xai_multi_agent_research_budget_unbounded",
        )

    capability = get_resolved_model_capability(request.model)
    if capability is None:
        raise ResearchRequestBoundsError(
            f"No exact pricing and context contract exists for research model {request.model!r}",
            code="research_model_pricing_unavailable",
        )
    if request.max_input_tokens > capability.context_window:
        raise ResearchRequestBoundsError(
            "max_input_tokens exceeds the registered model context window",
            code="research_input_bound_unsupported",
        )

    tool_cost = _tool_cost_bound(request, provider_key, capability.context_window)
    # Reserve the declared input ceiling even when the current prompt is tiny.
    # Later queue handoff, retries, document references, or provider-added tool
    # context must never exceed a hold sized only from today's string length.
    input_tokens = request.max_input_tokens
    token_cost_per_request = (
        input_tokens * capability.input_cost_per_1m + request.max_output_tokens * capability.output_cost_per_1m
    ) / 1_000_000
    maximum = token_cost_per_request * request.max_provider_requests + tool_cost
    if not math.isfinite(maximum) or maximum < 0:
        raise ResearchRequestBoundsError(
            "Research cost envelope is not finite",
            code="research_cost_envelope_invalid",
        )
    return CostEstimate(
        min_cost=0.0,
        expected_cost=maximum,
        max_cost=maximum,
        model=request.model,
        reasoning=(
            f"Hard envelope: {input_tokens} input tokens + {request.max_output_tokens} output tokens "
            f"x {request.max_provider_requests} provider request(s), {request.max_tool_calls} tool-call ceiling, "
            f"{serialized_bytes} serialized bytes"
        ),
    )


def request_bound_metadata(request: ResearchRequest) -> dict[str, int]:
    """Return the request ceilings persisted beside the reservation identity."""
    validate_research_request_bounds(request)
    return {
        metadata_name: int(getattr(request, field_name)) for metadata_name, field_name in _BOUND_METADATA_FIELDS.items()
    }


def validate_persisted_request_bounds(job_metadata: object, request: ResearchRequest) -> None:
    """Require queue metadata to preserve the exact admitted request ceilings."""
    if not isinstance(job_metadata, dict):
        raise ResearchRequestBoundsError(
            "Queued research request bounds are missing",
            code="research_request_bounds_missing",
        )
    expected = request_bound_metadata(request)
    if any(job_metadata.get(key) != value for key, value in expected.items()):
        raise ResearchRequestBoundsError(
            "Queued research request bounds do not match the provider request",
            code="research_request_bounds_mismatch",
        )


__all__ = [
    "ResearchRequestBoundsError",
    "bounded_research_cost_estimate",
    "request_bound_metadata",
    "require_metered_interface_accounting",
    "require_research_parent_budget_accounting",
    "require_research_storage_accounting",
    "validate_persisted_request_bounds",
    "validate_provider_payload_bytes",
    "validate_research_request_bounds",
]
