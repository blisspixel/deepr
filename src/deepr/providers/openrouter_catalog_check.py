"""Write-free proof of the bounded OpenRouter preview catalog.

This module fetches only public model endpoint metadata. It never reads an API
key, constructs an inference client, or enables OpenRouter dispatch.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from deepr.providers.model_capability import ModelCapability
from deepr.providers.openrouter_catalog import (
    OPENROUTER_BASE_ROUTE_TAGS,
    OPENROUTER_CACHE_WRITE_PRICE_SOURCES,
    OPENROUTER_CAPABILITIES,
    OPENROUTER_UPSTREAM_TAGS,
)
from deepr.utils.pinned_http import close_pinned_response, pinned_get

OPENROUTER_CATALOG_CHECK_KIND = "deepr.providers.openrouter_catalog_check"
OPENROUTER_CATALOG_CHECK_SCHEMA_VERSION = "deepr-openrouter-catalog-check-v2"
OPENROUTER_ENDPOINTS_BASE_URL = "https://openrouter.ai/api/v1/models"

_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_ENDPOINTS = 128
_MAX_OVERRIDES = 32
_MAX_INPUT_TOKENS = 128_000
_MAX_OUTPUT_TOKENS = 16_000
_REQUIRED_PARAMETERS = ("max_tokens", "response_format")
_SERVICE_TIER_SUFFIXES = ("/fast", "/flex", "/priority")
_FEATURE_GATED_PRICE_KEYS = frozenset({"audio", "image", "input_audio_cache", "web_search"})
_TEXT_PRICE_KEYS = frozenset({"completion", "internal_reasoning", "prompt", "request"})
_PRICE_METADATA_KEYS = frozenset({"discount", "overrides"})
_OVERRIDE_CONDITION_KEYS = frozenset({"min_prompt_tokens", "utc_days", "utc_end", "utc_start"})
_PROPOSED_REQUEST_HEADERS = {
    "X-OpenRouter-Cache": "false",
    "X-OpenRouter-Metadata": "enabled",
}
_FORBIDDEN_REQUEST_FEATURES = (
    "account_default_plugins",
    "background_execution",
    "explicit_prompt_cache_control",
    "fallback_models",
    "media_input_or_output",
    "plugins",
    "presets",
    "service_tier_or_speed",
    "server_tools",
    "tier_model_variants",
    "usage_opt_in_parameters",
)
_DECIMAL_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,24})?$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class OpenRouterCatalogCheckError(RuntimeError):
    """Public endpoint metadata cannot prove the registered route."""


@dataclass(frozen=True)
class FetchedOpenRouterDocument:
    """One bounded public endpoint document and its content digest."""

    payload: object
    source_sha256: str


@dataclass(frozen=True)
class _ParsedOpenRouterEndpoint:
    provider_name: str
    status: int
    context_length: int
    max_prompt_tokens: int | None
    max_completion_tokens: int | None
    parameters: tuple[str, ...]
    input_cost_per_1m: Decimal
    output_cost_per_1m: Decimal
    cache_read_cost_per_1m: Decimal
    cache_write_cost_per_1m: Decimal
    reasoning_cost_per_1m: Decimal
    request_cost_usd: Decimal
    matched_endpoint_tags: tuple[str, ...]


@dataclass(frozen=True)
class OpenRouterCatalogProof:
    """Result for one exact model and named provider route proposal."""

    model: str
    upstream_tag: str
    provider_name: str
    catalog_eligible: bool
    failures: tuple[str, ...]
    observed_input_cost_per_1m: float | None
    observed_output_cost_per_1m: float | None
    observed_cache_read_cost_per_1m: float | None
    observed_cache_write_cost_per_1m: float | None
    observed_reasoning_cost_per_1m: float | None
    observed_request_cost_usd: float | None
    registered_input_cap_per_1m: float
    registered_output_cap_per_1m: float
    registered_cache_read_cap_per_1m: float
    registered_cache_write_cap_per_1m: float
    cache_write_price_source: str
    context_length: int | None
    max_prompt_tokens: int | None
    max_completion_tokens: int | None
    endpoint_status: int | None
    source_sha256: str
    routing_policy_sha256: str
    matched_endpoint_tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": OPENROUTER_CATALOG_CHECK_SCHEMA_VERSION,
            "kind": OPENROUTER_CATALOG_CHECK_KIND,
            "model": self.model,
            "upstream_tag": self.upstream_tag,
            "provider_name": self.provider_name,
            "catalog_eligible": self.catalog_eligible,
            "failures": list(self.failures),
            "observed_input_cost_per_1m": self.observed_input_cost_per_1m,
            "observed_output_cost_per_1m": self.observed_output_cost_per_1m,
            "observed_cache_read_cost_per_1m": self.observed_cache_read_cost_per_1m,
            "observed_cache_write_cost_per_1m": self.observed_cache_write_cost_per_1m,
            "observed_reasoning_cost_per_1m": self.observed_reasoning_cost_per_1m,
            "observed_request_cost_usd": self.observed_request_cost_usd,
            "registered_input_cap_per_1m": self.registered_input_cap_per_1m,
            "registered_output_cap_per_1m": self.registered_output_cap_per_1m,
            "registered_cache_read_cap_per_1m": self.registered_cache_read_cap_per_1m,
            "registered_cache_write_cap_per_1m": self.registered_cache_write_cap_per_1m,
            "cache_write_price_source": self.cache_write_price_source,
            "context_length": self.context_length,
            "max_prompt_tokens": self.max_prompt_tokens,
            "max_completion_tokens": self.max_completion_tokens,
            "endpoint_status": self.endpoint_status,
            "source_sha256": self.source_sha256,
            "routing_policy_sha256": self.routing_policy_sha256,
            "matched_endpoint_tags": list(self.matched_endpoint_tags),
            "proposed_provider_routing": build_openrouter_routing_policy(self.model),
            "proposed_request_headers": dict(_PROPOSED_REQUEST_HEADERS),
            "forbidden_request_features": list(_FORBIDDEN_REQUEST_FEATURES),
            "paid_requests": 0,
            "api_key_loaded": False,
            "dispatch_authorized": False,
        }


def openrouter_models() -> tuple[str, ...]:
    """Return the exact preview model slugs in stable order."""
    return tuple(sorted(OPENROUTER_UPSTREAM_TAGS))


def _capability(model: str) -> ModelCapability:
    try:
        return OPENROUTER_CAPABILITIES[f"openrouter/{model}"]
    except KeyError as exc:
        raise OpenRouterCatalogCheckError(f"OpenRouter model {model!r} is not in the bounded preview catalog") from exc


def _upstream_tag(model: str) -> str:
    try:
        return OPENROUTER_UPSTREAM_TAGS[model]
    except KeyError as exc:
        raise OpenRouterCatalogCheckError(f"OpenRouter model {model!r} has no provider route proposal") from exc


def _cache_write_price_source(model: str) -> str:
    try:
        return OPENROUTER_CACHE_WRITE_PRICE_SOURCES[model]
    except KeyError as exc:
        raise OpenRouterCatalogCheckError(f"OpenRouter model {model!r} has no cache-write price source") from exc


def build_openrouter_routing_policy(model: str) -> dict[str, Any]:
    """Build the exact fail-closed provider routing object for a future call."""
    capability = _capability(model)
    tag = _upstream_tag(model)
    return {
        "order": [tag],
        "only": [tag],
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "deny",
        "max_price": {
            "prompt": float(capability.input_cost_per_1m),
            "completion": float(capability.output_cost_per_1m),
            "request": 0.0,
        },
    }


def _routing_policy_sha256(model: str) -> str:
    payload = json.dumps(
        build_openrouter_routing_policy(model),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata contains a duplicate object key")
        result[key] = value
    return result


def _read_bounded_body(response: requests.Response) -> bytes:
    declared_length = response.headers.get("Content-Length")
    if declared_length is not None:
        try:
            length = int(declared_length)
        except (TypeError, ValueError) as exc:
            raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata has an invalid Content-Length") from exc
        if length < 0 or length > _MAX_RESPONSE_BYTES:
            raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata exceeds the response byte ceiling")
    body = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not isinstance(chunk, bytes):
            raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata returned a non-byte response chunk")
        body.extend(chunk)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata exceeds the response byte ceiling")
    return bytes(body)


def fetch_openrouter_endpoint_document(model: str) -> FetchedOpenRouterDocument:
    """Fetch one known model document without credentials, redirects, or proxies."""
    if model not in OPENROUTER_UPSTREAM_TAGS:
        raise OpenRouterCatalogCheckError(f"OpenRouter model {model!r} is not in the bounded preview catalog")
    url = f"{OPENROUTER_ENDPOINTS_BASE_URL}/{model}/endpoints"
    try:
        response = pinned_get(
            url,
            headers={"Accept": "application/json", "User-Agent": "deepr-openrouter-catalog-check/1"},
            timeout=(5.0, 15.0),
            allow_redirects=False,
            stream=True,
        )
    except (requests.RequestException, OSError) as exc:
        raise OpenRouterCatalogCheckError("OpenRouter public endpoint metadata request failed") from exc
    try:
        if response.status_code != 200:
            raise OpenRouterCatalogCheckError(
                f"OpenRouter public endpoint metadata returned HTTP {response.status_code}"
            )
        content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().casefold()
        if content_type != "application/json":
            raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata did not return application/json")
        raw = _read_bounded_body(response)
    finally:
        close_pinned_response(response)
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_guard)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata is not strict UTF-8 JSON") from exc
    return FetchedOpenRouterDocument(payload=payload, source_sha256=hashlib.sha256(raw).hexdigest())


def _mapping(value: object, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OpenRouterCatalogCheckError(f"OpenRouter endpoint metadata {field_name} must be an object")
    return value


def _text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or not value.isascii():
        raise OpenRouterCatalogCheckError(f"OpenRouter endpoint metadata {field_name} must be bounded ASCII text")
    return value


def _integer(value: object, *, field_name: str, allow_none: bool = False) -> int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OpenRouterCatalogCheckError(f"OpenRouter endpoint metadata {field_name} must be a non-negative integer")
    return value


def _status(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata endpoint.status must be an integer")
    return value


def _price(value: object, *, field_name: str) -> Decimal:
    if not isinstance(value, str) or _DECIMAL_PATTERN.fullmatch(value) is None:
        raise OpenRouterCatalogCheckError(f"OpenRouter endpoint metadata {field_name} must be a decimal string")
    try:
        result = Decimal(value) * Decimal(1_000_000)
    except InvalidOperation as exc:  # pragma: no cover - guarded by the pattern
        raise OpenRouterCatalogCheckError(f"OpenRouter endpoint metadata {field_name} is invalid") from exc
    if not result.is_finite() or result < 0:
        raise OpenRouterCatalogCheckError(f"OpenRouter endpoint metadata {field_name} must be finite and non-negative")
    return result


def _optional_token_price(
    pricing: Mapping[str, Any],
    key: str,
    *,
    field_name: str,
    fallback: Decimal,
) -> Decimal:
    if key not in pricing:
        return fallback
    value = pricing[key]
    return _price(value, field_name=f"{field_name}.{key}")


def _request_price(pricing: Mapping[str, Any], *, field_name: str, fallback: Decimal) -> Decimal:
    if "request" not in pricing:
        return fallback
    value = pricing["request"]
    if not isinstance(value, str) or _DECIMAL_PATTERN.fullmatch(value) is None:
        raise OpenRouterCatalogCheckError(f"OpenRouter endpoint metadata {field_name}.request must be decimal USD")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - guarded by the pattern
        raise OpenRouterCatalogCheckError(f"OpenRouter endpoint metadata {field_name}.request is invalid") from exc
    if not result.is_finite() or result < 0:
        raise OpenRouterCatalogCheckError(
            f"OpenRouter endpoint metadata {field_name}.request must be finite and non-negative"
        )
    return result


def _validate_pricing_shape(
    pricing: Mapping[str, Any],
    *,
    field_name: str,
    allow_conditions: bool,
) -> None:
    known = _FEATURE_GATED_PRICE_KEYS | _TEXT_PRICE_KEYS
    if allow_conditions:
        known |= _OVERRIDE_CONDITION_KEYS
    else:
        known |= _PRICE_METADATA_KEYS
    unknown = [
        key
        for key in pricing
        if not isinstance(key, str)
        or (key not in known and not key.startswith("input_cache_read") and not key.startswith("input_cache_write"))
    ]
    if unknown:
        raise OpenRouterCatalogCheckError(
            f"OpenRouter endpoint metadata {field_name} has unclassified pricing field {unknown[0]!r}"
        )
    for key in _FEATURE_GATED_PRICE_KEYS:
        if key in pricing:
            _price(pricing[key], field_name=f"{field_name}.{key}")
    if "discount" in pricing:
        value = pricing["discount"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise OpenRouterCatalogCheckError(
                f"OpenRouter endpoint metadata {field_name}.discount must be a finite non-negative number below 1"
            )
        discount = Decimal(str(value))
        if not discount.is_finite() or discount < 0 or discount >= 1:
            raise OpenRouterCatalogCheckError(
                f"OpenRouter endpoint metadata {field_name}.discount must be a finite non-negative number below 1"
            )


def _cache_read_price(pricing: Mapping[str, Any], *, field_name: str, fallback: Decimal) -> Decimal:
    values = [
        _price(value, field_name=f"{field_name}.{key}")
        for key, value in pricing.items()
        if isinstance(key, str) and key.startswith("input_cache_read")
    ]
    return max(values, default=fallback)


def _cache_write_price(
    pricing: Mapping[str, Any],
    *,
    field_name: str,
    fallback: Decimal | None,
) -> Decimal | None:
    values = [
        _price(value, field_name=f"{field_name}.{key}")
        for key, value in pricing.items()
        if isinstance(key, str) and key.startswith("input_cache_write")
    ]
    if values:
        return max(values)
    return fallback


def _cache_write_fallback(source: str, prompt: Decimal) -> Decimal | None:
    if source == "official_free":
        return Decimal(0)
    if source == "prompt_equivalent":
        return prompt
    if source == "endpoint_metadata":
        return None
    raise OpenRouterCatalogCheckError("OpenRouter cache-write price source is invalid")


def _override_is_reachable(override: Mapping[str, Any], index: int) -> bool:
    minimum = override.get("min_prompt_tokens")
    if minimum is None:
        return True
    parsed = _integer(minimum, field_name=f"pricing.overrides[{index}].min_prompt_tokens")
    return parsed is not None and parsed <= _MAX_INPUT_TOKENS


def _apply_price_override(
    *,
    source: str,
    pricing: Mapping[str, Any],
    override: Mapping[str, Any],
    index: int,
    prompt: Decimal,
    completion: Decimal,
    cache_read: Decimal,
    cache_write: Decimal,
    reasoning: Decimal,
    request: Decimal,
    base_has_reasoning_price: bool,
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    override_prompt = _price(
        override.get("prompt", pricing.get("prompt")),
        field_name=f"pricing.overrides[{index}].prompt",
    )
    override_completion = _price(
        override.get("completion", pricing.get("completion")),
        field_name=f"pricing.overrides[{index}].completion",
    )
    override_cache_read = _cache_read_price(
        override,
        field_name=f"pricing.overrides[{index}]",
        fallback=cache_read,
    )
    override_fallback = override_prompt if source == "prompt_equivalent" else cache_write
    override_cache_write = _cache_write_price(
        override,
        field_name=f"pricing.overrides[{index}]",
        fallback=override_fallback,
    )
    if override_cache_write is None:  # pragma: no cover - fallback is always finite
        raise OpenRouterCatalogCheckError("OpenRouter cache-write override price is missing")
    reasoning_fallback = reasoning if base_has_reasoning_price else override_completion
    override_reasoning = _optional_token_price(
        override,
        "internal_reasoning",
        field_name=f"pricing.overrides[{index}]",
        fallback=reasoning_fallback,
    )
    override_request = _request_price(
        override,
        field_name=f"pricing.overrides[{index}]",
        fallback=request,
    )
    return (
        max(prompt, override_prompt),
        max(completion, override_completion),
        max(cache_read, override_cache_read),
        max(cache_write, override_cache_write),
        max(reasoning, override_reasoning),
        max(request, override_request),
    )


def _effective_price_caps(
    model: str,
    pricing: Mapping[str, Any],
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    _validate_pricing_shape(pricing, field_name="pricing", allow_conditions=False)
    prompt = _price(pricing.get("prompt"), field_name="pricing.prompt")
    completion = _price(pricing.get("completion"), field_name="pricing.completion")
    cache_read = _cache_read_price(pricing, field_name="pricing", fallback=prompt)
    source = _cache_write_price_source(model)
    cache_write = _cache_write_price(
        pricing,
        field_name="pricing",
        fallback=_cache_write_fallback(source, prompt),
    )
    if cache_write is None:
        raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata omits the required cache-write price")
    base_has_reasoning_price = pricing.get("internal_reasoning") is not None
    reasoning = _optional_token_price(
        pricing,
        "internal_reasoning",
        field_name="pricing",
        fallback=completion,
    )
    request = _request_price(pricing, field_name="pricing", fallback=Decimal(0))
    overrides = pricing.get("overrides", [])
    if not isinstance(overrides, list) or len(overrides) > _MAX_OVERRIDES:
        raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata pricing.overrides is not a bounded list")
    for index, raw_override in enumerate(overrides):
        override = _mapping(raw_override, field_name=f"pricing.overrides[{index}]")
        _validate_pricing_shape(
            override,
            field_name=f"pricing.overrides[{index}]",
            allow_conditions=True,
        )
        if not _override_is_reachable(override, index):
            continue
        prompt, completion, cache_read, cache_write, reasoning, request = _apply_price_override(
            source=source,
            pricing=pricing,
            override=override,
            index=index,
            prompt=prompt,
            completion=completion,
            cache_read=cache_read,
            cache_write=cache_write,
            reasoning=reasoning,
            request=request,
            base_has_reasoning_price=base_has_reasoning_price,
        )
    return prompt, completion, cache_read, cache_write, reasoning, request


def _route_tag_matches(route_tag: str, endpoint_tag: object) -> bool:
    if not isinstance(endpoint_tag, str):
        return False
    if route_tag not in OPENROUTER_BASE_ROUTE_TAGS:
        return endpoint_tag == route_tag
    if endpoint_tag == route_tag:
        return True
    return endpoint_tag.startswith(f"{route_tag}/") and not endpoint_tag.endswith(_SERVICE_TIER_SUFFIXES)


def _parse_endpoint_document(model: str, document: FetchedOpenRouterDocument) -> _ParsedOpenRouterEndpoint:
    if _SHA256_PATTERN.fullmatch(document.source_sha256) is None:
        raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata source digest is invalid")
    root = _mapping(document.payload, field_name="document")
    data = _mapping(root.get("data"), field_name="data")
    if _text(data.get("id"), field_name="data.id") != model:
        raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata model identity does not match the request")
    endpoints = data.get("endpoints")
    if not isinstance(endpoints, list) or not 1 <= len(endpoints) <= _MAX_ENDPOINTS:
        raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata endpoints is not a bounded non-empty list")
    tag = _upstream_tag(model)
    matches = [
        _mapping(endpoint, field_name="endpoint")
        for endpoint in endpoints
        if isinstance(endpoint, Mapping) and _route_tag_matches(tag, endpoint.get("tag"))
    ]
    if len(matches) != 1:
        raise OpenRouterCatalogCheckError(
            "OpenRouter provider route does not resolve to one standard endpoint metadata record"
        )
    endpoint = matches[0]
    matched_endpoint_tag = _text(endpoint.get("tag"), field_name="endpoint.tag")
    parameters = endpoint.get("supported_parameters")
    if (
        not isinstance(parameters, list)
        or len(parameters) > 128
        or any(not isinstance(item, str) or not item.isascii() or len(item) > 128 for item in parameters)
    ):
        raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata supported_parameters is invalid")
    (
        observed_input,
        observed_output,
        observed_cache_read,
        observed_cache_write,
        observed_reasoning,
        observed_request,
    ) = _effective_price_caps(model, _mapping(endpoint.get("pricing"), field_name="endpoint.pricing"))
    context_length = _integer(endpoint.get("context_length"), field_name="endpoint.context_length")
    if context_length is None:  # pragma: no cover - allow_none is false
        raise OpenRouterCatalogCheckError("OpenRouter endpoint metadata context length is missing")
    return _ParsedOpenRouterEndpoint(
        provider_name=_text(endpoint.get("provider_name"), field_name="endpoint.provider_name"),
        status=_status(endpoint.get("status")),
        context_length=context_length,
        max_prompt_tokens=_integer(
            endpoint.get("max_prompt_tokens"), field_name="endpoint.max_prompt_tokens", allow_none=True
        ),
        max_completion_tokens=_integer(
            endpoint.get("max_completion_tokens"), field_name="endpoint.max_completion_tokens", allow_none=True
        ),
        parameters=tuple(parameters),
        input_cost_per_1m=observed_input,
        output_cost_per_1m=observed_output,
        cache_read_cost_per_1m=observed_cache_read,
        cache_write_cost_per_1m=observed_cache_write,
        reasoning_cost_per_1m=observed_reasoning,
        request_cost_usd=observed_request,
        matched_endpoint_tags=(matched_endpoint_tag,),
    )


def _endpoint_failures(
    endpoint: _ParsedOpenRouterEndpoint,
    *,
    input_cap: Decimal,
    output_cap: Decimal,
    cache_read_cap: Decimal,
    cache_write_cap: Decimal,
) -> list[str]:
    failures: list[str] = []
    if endpoint.status != 0:
        failures.append(f"upstream endpoint status is {endpoint.status}, not 0")
    if endpoint.context_length < _MAX_INPUT_TOKENS + _MAX_OUTPUT_TOKENS:
        failures.append("upstream endpoint context is below the bounded request envelope")
    if endpoint.max_prompt_tokens is not None and endpoint.max_prompt_tokens < _MAX_INPUT_TOKENS:
        failures.append("upstream endpoint prompt ceiling is below 128000 tokens")
    if endpoint.max_completion_tokens is None or endpoint.max_completion_tokens < _MAX_OUTPUT_TOKENS:
        failures.append("upstream endpoint completion ceiling is below 16000 tokens")
    missing_parameters = [parameter for parameter in _REQUIRED_PARAMETERS if parameter not in endpoint.parameters]
    if missing_parameters:
        failures.append("upstream endpoint is missing required parameters: " + ", ".join(missing_parameters))
    failures.extend(
        _price_failures(
            endpoint,
            input_cap=input_cap,
            output_cap=output_cap,
            cache_read_cap=cache_read_cap,
            cache_write_cap=cache_write_cap,
        )
    )
    return failures


def _price_failures(
    endpoint: _ParsedOpenRouterEndpoint,
    *,
    input_cap: Decimal,
    output_cap: Decimal,
    cache_read_cap: Decimal,
    cache_write_cap: Decimal,
) -> list[str]:
    failures: list[str] = []
    if endpoint.input_cost_per_1m > input_cap:
        failures.append(
            "upstream prompt price "
            f"${float(endpoint.input_cost_per_1m):.6f}/M exceeds registered cap ${float(input_cap):.6f}/M"
        )
    if endpoint.output_cost_per_1m > output_cap:
        failures.append(
            "upstream completion price "
            f"${float(endpoint.output_cost_per_1m):.6f}/M exceeds registered cap ${float(output_cap):.6f}/M"
        )
    if endpoint.cache_read_cost_per_1m > cache_read_cap:
        failures.append(
            "upstream cache-read price "
            f"${float(endpoint.cache_read_cost_per_1m):.6f}/M exceeds registered cap "
            f"${float(cache_read_cap):.6f}/M"
        )
    if endpoint.cache_write_cost_per_1m > cache_write_cap:
        failures.append(
            "upstream cache-write price "
            f"${float(endpoint.cache_write_cost_per_1m):.6f}/M exceeds registered cap "
            f"${float(cache_write_cap):.6f}/M"
        )
    if endpoint.reasoning_cost_per_1m > output_cap:
        failures.append(
            "upstream reasoning price "
            f"${float(endpoint.reasoning_cost_per_1m):.6f}/M exceeds completion cap ${float(output_cap):.6f}/M"
        )
    if endpoint.request_cost_usd > 0:
        failures.append(f"upstream fixed request price ${float(endpoint.request_cost_usd):.6f} exceeds zero cap")
    return failures


def _failed_proof(model: str, failure: str, *, source_sha256: str = "") -> OpenRouterCatalogProof:
    capability = _capability(model)
    return OpenRouterCatalogProof(
        model=model,
        upstream_tag=_upstream_tag(model),
        provider_name="",
        catalog_eligible=False,
        failures=(failure,),
        observed_input_cost_per_1m=None,
        observed_output_cost_per_1m=None,
        observed_cache_read_cost_per_1m=None,
        observed_cache_write_cost_per_1m=None,
        observed_reasoning_cost_per_1m=None,
        observed_request_cost_usd=None,
        registered_input_cap_per_1m=float(capability.input_cost_per_1m),
        registered_output_cap_per_1m=float(capability.output_cost_per_1m),
        registered_cache_read_cap_per_1m=float(capability.cached_input_cost_per_1m or 0.0),
        registered_cache_write_cap_per_1m=float(capability.cache_write_cost_per_1m or 0.0),
        cache_write_price_source=_cache_write_price_source(model),
        context_length=None,
        max_prompt_tokens=None,
        max_completion_tokens=None,
        endpoint_status=None,
        source_sha256=source_sha256,
        routing_policy_sha256=_routing_policy_sha256(model),
        matched_endpoint_tags=(),
    )


def evaluate_openrouter_endpoint_document(
    model: str,
    document: FetchedOpenRouterDocument,
) -> OpenRouterCatalogProof:
    """Evaluate one untrusted public metadata document against the registry."""
    capability = _capability(model)
    try:
        endpoint = _parse_endpoint_document(model, document)
        if capability.cached_input_cost_per_1m is None:
            raise OpenRouterCatalogCheckError("OpenRouter route has no registered cache-read cap")
        if capability.cache_write_cost_per_1m is None:
            raise OpenRouterCatalogCheckError("OpenRouter route has no registered cache-write cap")
    except OpenRouterCatalogCheckError as exc:
        return _failed_proof(model, str(exc), source_sha256=document.source_sha256)

    input_cap = Decimal(str(capability.input_cost_per_1m))
    output_cap = Decimal(str(capability.output_cost_per_1m))
    cache_read_cap = Decimal(str(capability.cached_input_cost_per_1m))
    cache_write_cap = Decimal(str(capability.cache_write_cost_per_1m))
    failures = _endpoint_failures(
        endpoint,
        input_cap=input_cap,
        output_cap=output_cap,
        cache_read_cap=cache_read_cap,
        cache_write_cap=cache_write_cap,
    )
    return OpenRouterCatalogProof(
        model=model,
        upstream_tag=_upstream_tag(model),
        provider_name=endpoint.provider_name,
        catalog_eligible=not failures,
        failures=tuple(failures),
        observed_input_cost_per_1m=float(endpoint.input_cost_per_1m),
        observed_output_cost_per_1m=float(endpoint.output_cost_per_1m),
        observed_cache_read_cost_per_1m=float(endpoint.cache_read_cost_per_1m),
        observed_cache_write_cost_per_1m=float(endpoint.cache_write_cost_per_1m),
        observed_reasoning_cost_per_1m=float(endpoint.reasoning_cost_per_1m),
        observed_request_cost_usd=float(endpoint.request_cost_usd),
        registered_input_cap_per_1m=float(input_cap),
        registered_output_cap_per_1m=float(output_cap),
        registered_cache_read_cap_per_1m=float(cache_read_cap),
        registered_cache_write_cap_per_1m=float(cache_write_cap),
        cache_write_price_source=_cache_write_price_source(model),
        context_length=endpoint.context_length,
        max_prompt_tokens=endpoint.max_prompt_tokens,
        max_completion_tokens=endpoint.max_completion_tokens,
        endpoint_status=endpoint.status,
        source_sha256=document.source_sha256,
        routing_policy_sha256=_routing_policy_sha256(model),
        matched_endpoint_tags=endpoint.matched_endpoint_tags,
    )


def check_openrouter_catalog(
    models: Sequence[str] | None = None,
    *,
    fetcher: Callable[[str], FetchedOpenRouterDocument] = fetch_openrouter_endpoint_document,
) -> tuple[OpenRouterCatalogProof, ...]:
    """Check known routes independently so one failure cannot hide the rest."""
    requested = tuple(models) if models is not None else openrouter_models()
    if not requested or len(set(requested)) != len(requested):
        raise OpenRouterCatalogCheckError("OpenRouter catalog check models must be a unique non-empty sequence")
    unknown = [model for model in requested if model not in OPENROUTER_UPSTREAM_TAGS]
    if unknown:
        raise OpenRouterCatalogCheckError(f"OpenRouter model {unknown[0]!r} is not in the bounded preview catalog")
    proofs: list[OpenRouterCatalogProof] = []
    for model in requested:
        try:
            document = fetcher(model)
        except OpenRouterCatalogCheckError as exc:
            proofs.append(_failed_proof(model, str(exc)))
            continue
        proofs.append(evaluate_openrouter_endpoint_document(model, document))
    return tuple(proofs)


__all__ = [
    "OPENROUTER_CATALOG_CHECK_KIND",
    "OPENROUTER_CATALOG_CHECK_SCHEMA_VERSION",
    "FetchedOpenRouterDocument",
    "OpenRouterCatalogCheckError",
    "OpenRouterCatalogProof",
    "build_openrouter_routing_policy",
    "check_openrouter_catalog",
    "evaluate_openrouter_endpoint_document",
    "fetch_openrouter_endpoint_document",
    "openrouter_models",
]
