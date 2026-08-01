"""Provider-enforceable maximum-charge contract for metered expert surfaces.

This module formalizes the ROADMAP / metered-expert-chat-reenable requirements
as a pure, offline-evaluable contract. A complete contract is a necessary
precondition for any future paid re-enable; it is not spend authority by itself.

Rules:

- Every billable dimension must carry an exact non-negative maximum, never an
  average or expected-only figure.
- Token and tool maxima are priced from the registry at the conservative high
  end (no tier under-estimate); missing pricing fails closed.
- The summed computed maximum must be finite and must not exceed the parent
  dollar ceiling.
- Client and transport posture must be Deepr-owned: no retries, no redirects,
  no injected client, official endpoint only, overage disabled (or hard limit
  <= remaining headroom - that last provider observation is a separate live
  proof and is not claimed by offline evaluation).
- Completeness never enables dispatch. ``METERED_EXPERT_CHAT_EXECUTION_ENABLED``
  remains the only runtime enable gate and stays false until a reviewed change.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# Required scalar maxima (exact units, not averages).
TOKEN_DIMENSIONS = (
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cache_write_tokens",
    "cache_read_tokens",
)
USD_DIMENSIONS = (
    "tool_usd",
    "hosted_storage_usd",
    "background_jobs_usd",
    "transport_surcharge_usd",
    "fallback_usd",
)
POSTURE_FLAGS = (
    "retries_disabled",
    "redirects_disabled",
    "deepr_owned_client",
    "official_endpoint_pinned",
    "injected_client_rejected",
    "overage_disabled",
)
IDENTITY_FIELDS = (
    "provider",
    "model",
    "endpoint",
    "account_scope",
    "credential_fingerprint",
    "request_digest",
)

# Absolute Deepr total ceiling for active examples / operator binding.
ABSOLUTE_DEEPR_CEILING_USD = 5.0


class MaximumChargeContractError(ValueError):
    """Raised when a contract cannot be priced or is structurally invalid."""


@dataclass(frozen=True)
class MaximumChargeEnvelope:
    """Exact maxima and posture for one parent metered reservation."""

    parent_ceiling_usd: float
    provider: str
    model: str
    endpoint: str
    account_scope: str
    credential_fingerprint: str
    request_digest: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    tool_usd: float
    hosted_storage_usd: float
    background_jobs_usd: float
    transport_surcharge_usd: float
    fallback_usd: float
    retries_disabled: bool
    redirects_disabled: bool
    deepr_owned_client: bool
    official_endpoint_pinned: bool
    injected_client_rejected: bool
    overage_disabled: bool
    remaining_monthly_headroom_usd: float | None = None
    provider_hard_limit_usd: float | None = None
    # Explicitly rejected when present: averages are not authority.
    expected_cost_usd: float | None = None
    average_cost_usd: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MaximumChargeVerdict:
    """Offline evaluation result for one envelope."""

    complete: bool
    computed_max_usd: float | None
    parent_ceiling_usd: float | None
    missing: tuple[str, ...]
    failures: tuple[str, ...]
    priced_components: Mapping[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "computed_max_usd": self.computed_max_usd,
            "parent_ceiling_usd": self.parent_ceiling_usd,
            "missing": list(self.missing),
            "failures": list(self.failures),
            "priced_components": dict(self.priced_components),
        }


def _require_finite_non_negative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MaximumChargeContractError(f"{name} must be a finite non-negative number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise MaximumChargeContractError(f"{name} must be a finite non-negative number")
    return number


def _require_non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MaximumChargeContractError(f"{name} must be a non-negative integer")
    if value < 0:
        raise MaximumChargeContractError(f"{name} must be a non-negative integer")
    return value


def _require_non_empty_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MaximumChargeContractError(f"{name} must be a non-empty string")
    return value.strip()


def _require_true(name: str, value: object) -> None:
    if value is not True:
        raise MaximumChargeContractError(f"{name} must be true")


def envelope_from_mapping(data: Mapping[str, Any]) -> MaximumChargeEnvelope:
    """Build a typed envelope from a mapping; raise on type errors."""
    if not isinstance(data, Mapping):
        raise MaximumChargeContractError("envelope must be a mapping")
    return MaximumChargeEnvelope(
        parent_ceiling_usd=_require_finite_non_negative("parent_ceiling_usd", data.get("parent_ceiling_usd")),
        provider=_require_non_empty_text("provider", data.get("provider")),
        model=_require_non_empty_text("model", data.get("model")),
        endpoint=_require_non_empty_text("endpoint", data.get("endpoint")),
        account_scope=_require_non_empty_text("account_scope", data.get("account_scope")),
        credential_fingerprint=_require_non_empty_text("credential_fingerprint", data.get("credential_fingerprint")),
        request_digest=_require_non_empty_text("request_digest", data.get("request_digest")),
        input_tokens=_require_non_negative_int("input_tokens", data.get("input_tokens")),
        output_tokens=_require_non_negative_int("output_tokens", data.get("output_tokens")),
        reasoning_tokens=_require_non_negative_int("reasoning_tokens", data.get("reasoning_tokens")),
        cache_write_tokens=_require_non_negative_int("cache_write_tokens", data.get("cache_write_tokens")),
        cache_read_tokens=_require_non_negative_int("cache_read_tokens", data.get("cache_read_tokens")),
        tool_usd=_require_finite_non_negative("tool_usd", data.get("tool_usd")),
        hosted_storage_usd=_require_finite_non_negative("hosted_storage_usd", data.get("hosted_storage_usd")),
        background_jobs_usd=_require_finite_non_negative("background_jobs_usd", data.get("background_jobs_usd")),
        transport_surcharge_usd=_require_finite_non_negative(
            "transport_surcharge_usd", data.get("transport_surcharge_usd")
        ),
        fallback_usd=_require_finite_non_negative("fallback_usd", data.get("fallback_usd")),
        retries_disabled=bool(data.get("retries_disabled")),
        redirects_disabled=bool(data.get("redirects_disabled")),
        deepr_owned_client=bool(data.get("deepr_owned_client")),
        official_endpoint_pinned=bool(data.get("official_endpoint_pinned")),
        injected_client_rejected=bool(data.get("injected_client_rejected")),
        overage_disabled=bool(data.get("overage_disabled")),
        remaining_monthly_headroom_usd=(
            None
            if data.get("remaining_monthly_headroom_usd") is None
            else _require_finite_non_negative(
                "remaining_monthly_headroom_usd", data.get("remaining_monthly_headroom_usd")
            )
        ),
        provider_hard_limit_usd=(
            None
            if data.get("provider_hard_limit_usd") is None
            else _require_finite_non_negative("provider_hard_limit_usd", data.get("provider_hard_limit_usd"))
        ),
        expected_cost_usd=(
            None
            if data.get("expected_cost_usd") is None
            else _require_finite_non_negative("expected_cost_usd", data.get("expected_cost_usd"))
        ),
        average_cost_usd=(
            None
            if data.get("average_cost_usd") is None
            else _require_finite_non_negative("average_cost_usd", data.get("average_cost_usd"))
        ),
        metadata=dict(data.get("metadata") or {}),
    )


def _price_token_components(envelope: MaximumChargeEnvelope) -> dict[str, float]:
    from deepr.core.costs import CostEstimator
    from deepr.providers.registry import get_cached_input_pricing, get_token_pricing

    pricing = get_token_pricing(envelope.model, input_tokens=envelope.input_tokens)
    if not pricing or float(pricing.get("input", 0) or 0) <= 0 or float(pricing.get("output", 0) or 0) <= 0:
        raise MaximumChargeContractError(
            f"model {envelope.model!r} has no trusted positive token pricing in the registry"
        )
    input_rate = float(pricing["input"])
    output_rate = float(pricing["output"])
    components = {
        "input_tokens": (envelope.input_tokens / 1_000_000.0) * input_rate,
        "output_tokens": (envelope.output_tokens / 1_000_000.0) * output_rate,
        # Reasoning is billed at the output tier in Deepr's conservative settlement.
        "reasoning_tokens": (envelope.reasoning_tokens / 1_000_000.0) * output_rate,
    }
    cached_rate = get_cached_input_pricing(envelope.model, input_tokens=envelope.input_tokens)
    if envelope.cache_read_tokens > 0 or envelope.cache_write_tokens > 0:
        if cached_rate is None or float(cached_rate) <= 0:
            # Fail closed: cache traffic without trusted cache pricing cannot be bounded.
            raise MaximumChargeContractError(
                f"model {envelope.model!r} has cache token maxima but no trusted cache pricing"
            )
        cache_rate = float(cached_rate)
    else:
        cache_rate = 0.0
    # Cache writes are priced at least at full input rate when cache-specific
    # write rates are not published separately (conservative upper bound).
    components["cache_read_tokens"] = (envelope.cache_read_tokens / 1_000_000.0) * cache_rate
    components["cache_write_tokens"] = (envelope.cache_write_tokens / 1_000_000.0) * max(cache_rate, input_rate)
    # Sanity: CostEstimator must agree that the model is known enough to price.
    _ = CostEstimator._get_pricing(envelope.model, input_tokens=envelope.input_tokens)
    return components


def _coerce_envelope(envelope: MaximumChargeEnvelope | Mapping[str, Any]) -> MaximumChargeEnvelope:
    if isinstance(envelope, Mapping):
        return envelope_from_mapping(envelope)
    if isinstance(envelope, MaximumChargeEnvelope):
        return envelope
    raise MaximumChargeContractError("envelope must be a MaximumChargeEnvelope or mapping")


def _parent_ceiling_failures(parent: float) -> list[str]:
    failures: list[str] = []
    if parent <= 0:
        failures.append("parent_ceiling_usd must be positive")
    if parent > ABSOLUTE_DEEPR_CEILING_USD:
        failures.append(
            f"parent_ceiling_usd ${parent:.4f} exceeds absolute Deepr ceiling ${ABSOLUTE_DEEPR_CEILING_USD:.2f}"
        )
    return failures


def _posture_and_authority_failures(typed: MaximumChargeEnvelope) -> list[str]:
    failures: list[str] = []
    if typed.expected_cost_usd is not None or typed.average_cost_usd is not None:
        failures.append("expected_cost_usd and average_cost_usd are not spend authority and are rejected")
    for flag in POSTURE_FLAGS:
        if getattr(typed, flag) is not True:
            failures.append(f"{flag} must be true")
    if (
        typed.provider_hard_limit_usd is not None
        and typed.remaining_monthly_headroom_usd is not None
        and typed.provider_hard_limit_usd > typed.remaining_monthly_headroom_usd + 1e-9
    ):
        failures.append("provider_hard_limit_usd exceeds remaining_monthly_headroom_usd; overage posture is unsafe")
    return failures


def _price_envelope_components(
    typed: MaximumChargeEnvelope,
) -> tuple[dict[str, float], list[str]]:
    priced: dict[str, float] = {name: float(getattr(typed, name)) for name in USD_DIMENSIONS}
    failures: list[str] = []
    try:
        priced.update(_price_token_components(typed))
    except MaximumChargeContractError as exc:
        failures.append(str(exc))
    return priced, failures


def _sum_against_parent(
    priced: Mapping[str, float],
    parent: float,
) -> tuple[float | None, list[str]]:
    if "input_tokens" not in priced:
        return None, []
    computed = sum(float(v) for v in priced.values())
    if not math.isfinite(computed):
        return None, ["computed_max_usd is not finite"]
    if computed > parent + 1e-9:
        return computed, [f"computed_max_usd ${computed:.6f} exceeds parent_ceiling_usd ${parent:.6f}"]
    return computed, []


def evaluate_maximum_charge_contract(
    envelope: MaximumChargeEnvelope | Mapping[str, Any],
) -> MaximumChargeVerdict:
    """Evaluate completeness of a maximum-charge envelope without side effects.

    A complete offline verdict still does not authorize paid dispatch: live
    provider overage-off observation and ``METERED_EXPERT_CHAT_EXECUTION_ENABLED``
    remain separate gates.
    """
    try:
        typed = _coerce_envelope(envelope)
    except MaximumChargeContractError as exc:
        return MaximumChargeVerdict(
            complete=False,
            computed_max_usd=None,
            parent_ceiling_usd=None,
            missing=(),
            failures=(str(exc),),
            priced_components={},
        )

    parent = float(typed.parent_ceiling_usd)
    failures = _parent_ceiling_failures(parent)
    failures.extend(_posture_and_authority_failures(typed))
    priced, price_failures = _price_envelope_components(typed)
    failures.extend(price_failures)
    computed, sum_failures = _sum_against_parent(priced, parent)
    failures.extend(sum_failures)

    complete = not failures and computed is not None
    return MaximumChargeVerdict(
        complete=complete,
        computed_max_usd=None if computed is None else round(computed, 6),
        parent_ceiling_usd=parent,
        missing=(),
        failures=tuple(failures),
        priced_components={key: round(float(value), 6) for key, value in priced.items()},
    )


def require_complete_maximum_charge_contract(
    envelope: MaximumChargeEnvelope | Mapping[str, Any],
) -> MaximumChargeVerdict:
    """Return a complete verdict or raise ``MaximumChargeContractError``."""
    verdict = evaluate_maximum_charge_contract(envelope)
    if not verdict.complete:
        detail = "; ".join(verdict.failures) or "contract incomplete"
        raise MaximumChargeContractError(detail)
    return verdict


def incomplete_contract_summary(
    envelope: MaximumChargeEnvelope | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Machine-readable summary for blocked metered chat paths."""
    if envelope is None:
        return {
            "complete": False,
            "reason": "no maximum-charge envelope supplied",
            "required_token_dimensions": list(TOKEN_DIMENSIONS),
            "required_usd_dimensions": list(USD_DIMENSIONS),
            "required_posture_flags": list(POSTURE_FLAGS),
            "required_identity_fields": list(IDENTITY_FIELDS),
            "absolute_deepr_ceiling_usd": ABSOLUTE_DEEPR_CEILING_USD,
        }
    verdict = evaluate_maximum_charge_contract(envelope)
    payload = verdict.to_dict()
    payload["absolute_deepr_ceiling_usd"] = ABSOLUTE_DEEPR_CEILING_USD
    return payload


__all__ = [
    "ABSOLUTE_DEEPR_CEILING_USD",
    "IDENTITY_FIELDS",
    "POSTURE_FLAGS",
    "TOKEN_DIMENSIONS",
    "USD_DIMENSIONS",
    "MaximumChargeContractError",
    "MaximumChargeEnvelope",
    "MaximumChargeVerdict",
    "envelope_from_mapping",
    "evaluate_maximum_charge_contract",
    "incomplete_contract_summary",
    "require_complete_maximum_charge_contract",
]
