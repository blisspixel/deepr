"""Legacy contract inputs for production-frozen paid MCP tool calls."""

from __future__ import annotations

from math import isfinite
from typing import Any

_METERED_AUTHORIZATION_PROPERTIES: dict[str, Any] = {
    "budget": {
        "type": "number",
        "exclusiveMinimum": 0,
        "description": (
            "Required finite maximum cost in USD for contract validation. It does not authorize "
            "production metered dispatch."
        ),
    },
    "allow_metered_api": {
        "type": "boolean",
        "description": "Legacy acknowledgement. Production paid API dispatch remains blocked.",
    },
    "confirm_metered_cost": {
        "type": "boolean",
        "description": ("Legacy acknowledgement of the stated ceiling. It does not authorize provider dispatch."),
    },
}
_METERED_AUTHORIZATION_REQUIRED = ["budget", "allow_metered_api", "confirm_metered_cost"]

PAID_RESEARCH_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "Research question or topic. Be specific rather than generic.",
        },
        "model": {
            "type": "string",
            "default": "o4-mini-deep-research",
            "description": "Research model; pricing is provider- and model-specific.",
        },
        "provider": {
            "type": "string",
            "default": "openai",
            "description": "Provider selector for the production-frozen API path.",
        },
        **_METERED_AUTHORIZATION_PROPERTIES,
        "enable_web_search": {"type": "boolean", "default": True},
    },
    "required": ["prompt", *_METERED_AUTHORIZATION_REQUIRED],
}

PAID_EXPERT_VALIDATE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "expert_name": {"type": "string", "description": "Name of the expert to consult"},
        "claim": {
            "type": "string",
            "description": "Statement to assess against the expert's accumulated knowledge.",
        },
        "model": {
            "type": "string",
            "description": "Optional validation-model override from the bounded allowlist.",
        },
        "max_evidence": {
            "type": "integer",
            "default": 8,
            "description": "Maximum expert beliefs to include as grounding evidence",
        },
        **_METERED_AUTHORIZATION_PROPERTIES,
    },
    "required": ["expert_name", "claim", *_METERED_AUTHORIZATION_REQUIRED],
}


class MeteredMCPContractError(ValueError):
    """A paid MCP request is missing authority or a safe dollar ceiling."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def require_metered_api_contract(
    *,
    budget: object,
    allow_metered_api: object,
    confirm_metered_cost: object,
) -> float:
    """Validate a requested ceiling or fail before provider setup.

    Consent and cost confirmation are deliberately separate. A scoped key,
    generic MCP approval token, configured API key, or positive global budget
    does not substitute for either acknowledgement on this individual call.
    The returned ceiling is necessary contract data, not provider dispatch
    authority. Production metered dispatch remains blocked at the provider
    boundary.
    """
    if allow_metered_api is not True or confirm_metered_cost is not True:
        raise MeteredMCPContractError(
            code="METERED_API_NOT_APPROVED",
            message=(
                "Metered MCP contract validation requires allow_metered_api=true and "
                "confirm_metered_cost=true; a budget is a ceiling, not permission to spend, "
                "and these fields do not authorize production provider dispatch."
            ),
        )
    if isinstance(budget, bool) or not isinstance(budget, (int, float)):
        raise MeteredMCPContractError(
            code="INVALID_BUDGET",
            message=(
                "Metered MCP contract validation requires an explicit finite positive budget; "
                "production provider dispatch remains blocked."
            ),
        )
    ceiling = float(budget)
    if not isfinite(ceiling) or ceiling <= 0:
        raise MeteredMCPContractError(
            code="INVALID_BUDGET",
            message=(
                "Metered MCP contract validation requires an explicit finite positive budget; "
                "production provider dispatch remains blocked."
            ),
        )

    try:
        from deepr.core.cost_caps import resolve_spend_caps

        caps = resolve_spend_caps()
        per_call_cap = float(caps["per_job"])
    except Exception as exc:
        raise MeteredMCPContractError(
            code="BUDGET_UNAVAILABLE",
            message="Global operator spend authority is unavailable; paid MCP contract validation is blocked.",
        ) from exc

    if not isfinite(per_call_cap) or per_call_cap <= 0:
        raise MeteredMCPContractError(
            code="BUDGET_EXCEEDED",
            message="Paid MCP execution is frozen by the global operator spend authority.",
        )
    if ceiling > per_call_cap:
        raise MeteredMCPContractError(
            code="BUDGET_EXCEEDED",
            message=(f"Requested MCP ceiling ${ceiling:.2f} exceeds the global per-call cap of ${per_call_cap:.2f}."),
        )
    return ceiling


__all__ = [
    "PAID_EXPERT_VALIDATE_INPUT_SCHEMA",
    "PAID_RESEARCH_INPUT_SCHEMA",
    "MeteredMCPContractError",
    "require_metered_api_contract",
]
