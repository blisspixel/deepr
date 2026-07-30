"""Opaque one-use authority for provider-backed research dispatch."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from hmac import compare_digest
from typing import Any
from urllib.parse import urlsplit


class PaidDispatchAuthorityError(RuntimeError):
    """A paid provider call lacks the one-use durable dispatch authority."""


_GRANT_SEAL = object()


@dataclass
class _PaidDispatchGrant:
    provider: str
    model: str
    reservation_id: str
    job_id: str
    request_sha256: str
    seal: object = field(repr=False)
    consumed: bool = False


@dataclass
class _PaidDispatchAuthority:
    grant: _PaidDispatchGrant
    provider_identity: int
    request_sha256: str
    used: bool = False


_PAID_DISPATCH_AUTHORITY: ContextVar[_PaidDispatchAuthority | None] = ContextVar(
    "deepr_paid_dispatch_authority",
    default=None,
)
_PROXY_ENV_NAMES = frozenset({"http_proxy", "https_proxy", "all_proxy"})
_OFFICIAL_FIXED_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "xai": "https://api.x.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com",
}
_ENDPOINT_OVERRIDE_ENV_PROVIDERS = {
    "openai_base_url": "openai",
    "openai_api_base": "openai",
    "anthropic_base_url": "anthropic",
    "xai_base_url": "xai",
    "xai_api_base": "xai",
    "google_gemini_base_url": "gemini",
    "azure_openai_endpoint": "azure",
    "azure_openai_base_url": "azure",
    "azure_project_endpoint": "azure-foundry",
    "azure_ai_project_endpoint": "azure-foundry",
    "azure_foundry_project_endpoint": "azure-foundry",
}
_UNSUPPORTED_ENDPOINT_MODE_ENV_NAMES = frozenset(
    {
        "google_vertex_base_url",
        "google_genai_use_vertexai",
        "google_genai_use_enterprise",
    }
)
_UNACCOUNTED_IDENTITY_ENV_NAMES = frozenset(
    {
        "openai_custom_headers",
        "openai_org_id",
        "openai_project_id",
        "anthropic_custom_headers",
    }
)
_AZURE_OPENAI_SUFFIXES = (
    ".openai.azure.com",
    ".openai.azure.us",
    ".openai.azure.cn",
    ".cognitiveservices.azure.com",
    ".cognitiveservices.azure.us",
    ".cognitiveservices.azure.cn",
)
_AZURE_FOUNDRY_SUFFIXES = (
    ".services.ai.azure.com",
    ".services.ai.azure.us",
    ".services.ai.azure.cn",
)
_FOUNDRY_PROJECT_PATH = re.compile(r"/api/projects/[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?/?\Z")
_PAID_ENDPOINT_PROVIDERS = frozenset({"openai", "anthropic", "xai", "gemini", "azure", "azure-foundry"})
_MAX_UNTIERED_OPENAI_INPUT_TOKENS = 128_000
_SUPPORTED_SDK_CLIENT_TYPES = {
    "openai": frozenset({("openai", "OpenAI"), ("openai", "AsyncOpenAI")}),
    "xai": frozenset({("openai", "OpenAI"), ("openai", "AsyncOpenAI")}),
    "azure": frozenset(
        {
            ("openai", "OpenAI"),
            ("openai", "AsyncOpenAI"),
            ("openai.lib.azure", "AzureOpenAI"),
            ("openai.lib.azure", "AsyncAzureOpenAI"),
        }
    ),
    "anthropic": frozenset({("anthropic", "Anthropic"), ("anthropic", "AsyncAnthropic")}),
    "gemini": frozenset({("google.genai.client", "Client")}),
    "azure-foundry": frozenset(
        {
            ("azure.ai.projects._patch", "AIProjectClient"),
            ("azure.ai.agents._patch", "AgentsClient"),
        }
    ),
}


def default_paid_endpoint(provider: str) -> str:
    """Return the one supported public endpoint for a fixed-host provider."""
    canonical = canonical_provider_key(provider)
    try:
        return _OFFICIAL_FIXED_ENDPOINTS[canonical]
    except KeyError as exc:
        raise PaidDispatchAuthorityError(f"Provider {canonical!r} has no fixed official endpoint") from exc


def require_official_paid_endpoint(provider: str, endpoint: object, *, source: str = "configuration") -> str:
    """Validate and normalize a provider endpoint whose price identity is known.

    Deepr does not currently expose an attestation format that can bind a
    custom gateway to both a credential identity and an independently priced
    model catalog. Custom gateways therefore fail closed.
    """
    canonical = canonical_provider_key(provider)
    if canonical not in _PAID_ENDPOINT_PROVIDERS:
        raise PaidDispatchAuthorityError(f"Paid endpoint provider {canonical!r} is not classified")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise PaidDispatchAuthorityError(f"Paid provider endpoint from {source} is missing or opaque")
    raw = endpoint.strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise PaidDispatchAuthorityError(f"Paid provider endpoint from {source} is invalid") from exc
    host = parsed.hostname
    if (
        parsed.scheme.casefold() != "https"
        or not host
        or host != host.casefold()
        or not host.isascii()
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or "%" in parsed.path
    ):
        raise PaidDispatchAuthorityError(
            f"Paid provider endpoint from {source} is not an official HTTPS pricing endpoint"
        )

    normalized_host = host.casefold()
    path = parsed.path
    if canonical in _OFFICIAL_FIXED_ENDPOINTS:
        expected = urlsplit(_OFFICIAL_FIXED_ENDPOINTS[canonical])
        valid_paths = {expected.path, f"{expected.path}/"} if expected.path else {"", "/"}
        if normalized_host != expected.hostname or path not in valid_paths:
            raise PaidDispatchAuthorityError(
                f"Paid {canonical} endpoint from {source} is not the official priced endpoint"
            )
        return _OFFICIAL_FIXED_ENDPOINTS[canonical]

    if canonical == "azure":
        valid_host = any(
            normalized_host.endswith(suffix) and normalized_host != suffix[1:] for suffix in _AZURE_OPENAI_SUFFIXES
        )
        if not valid_host or path not in {"", "/", "/openai", "/openai/", "/openai/v1", "/openai/v1/"}:
            raise PaidDispatchAuthorityError(
                f"Paid Azure OpenAI endpoint from {source} is not an official resource endpoint"
            )
        return f"https://{normalized_host}"

    valid_host = any(
        normalized_host.endswith(suffix) and normalized_host != suffix[1:] for suffix in _AZURE_FOUNDRY_SUFFIXES
    )
    if not valid_host or _FOUNDRY_PROJECT_PATH.fullmatch(path) is None:
        raise PaidDispatchAuthorityError(
            f"Paid Azure Foundry endpoint from {source} is not an official project endpoint"
        )
    return f"https://{normalized_host}{path.rstrip('/')}"


def _plain_endpoint_attribute(value: object, name: str) -> str | None:
    try:
        candidate = getattr(value, name)
    except (AttributeError, TypeError):
        return None
    if isinstance(candidate, str):
        return candidate
    if type(candidate).__module__.startswith("httpx") and type(candidate).__name__ == "URL":
        return str(candidate)
    return None


def _paid_client_endpoint_value(client: object, provider: str) -> str | None:
    canonical = canonical_provider_key(provider)
    endpoint: str | None = None
    if canonical == "gemini":
        api_client = getattr(client, "_api_client", None)
        options = getattr(api_client, "_http_options", None)
        endpoint = _plain_endpoint_attribute(options, "base_url") if options is not None else None
    elif canonical == "azure-foundry":
        endpoint = _plain_endpoint_attribute(client, "endpoint")
        if endpoint is None:
            config = getattr(client, "_config", None)
            endpoint = _plain_endpoint_attribute(config, "endpoint") if config is not None else None
    elif canonical == "azure":
        endpoint = _plain_endpoint_attribute(client, "_azure_endpoint")
        if endpoint is None:
            endpoint = _plain_endpoint_attribute(client, "base_url")
    else:
        endpoint = _plain_endpoint_attribute(client, "base_url")
    return endpoint


def paid_client_endpoint(client: object, provider: str) -> str:
    """Extract and validate the live endpoint from a supported provider SDK."""
    canonical = canonical_provider_key(provider)
    client_identity = (type(client).__module__, type(client).__name__)
    if client_identity not in _SUPPORTED_SDK_CLIENT_TYPES.get(canonical, frozenset()):
        raise PaidDispatchAuthorityError(
            f"Paid {canonical} dispatch requires a recognized provider SDK client; wrappers and test fakes fail closed"
        )
    endpoint = _paid_client_endpoint_value(client, canonical)
    if endpoint is None:
        raise PaidDispatchAuthorityError(
            f"Paid {canonical} client does not expose a verifiable endpoint; injected clients fail closed"
        )
    return require_official_paid_endpoint(canonical, endpoint, source="injected SDK client")


def require_official_paid_client(client: object, provider: str) -> str:
    """Hard-block generic clients until Deepr can prove the whole account scope."""
    require_unproxied_paid_transport()
    endpoint = paid_client_endpoint(client, provider)
    del endpoint
    raise PaidDispatchAuthorityError(
        "Generic or injected paid SDK clients are disabled until an opaque Deepr-minted attestation binds "
        "client identity, endpoint, retries, redirects, proxy policy, provider model, credential account, "
        "and a provider hard no-overage ceiling"
    )


def require_exact_provider_model(provider_instance: object, requested_model: object) -> str:
    """Require the outbound model to share the reservation's priced contract."""
    if not isinstance(requested_model, str) or not requested_model:
        raise PaidDispatchAuthorityError("Paid provider request has no exact model identity")
    resolver = getattr(provider_instance, "get_model_name", None)
    if not callable(resolver):
        raise PaidDispatchAuthorityError("Paid provider cannot prove its outbound model identity")
    try:
        resolved = resolver(requested_model)
    except Exception as exc:
        raise PaidDispatchAuthorityError("Paid provider model resolution failed before dispatch") from exc
    if not isinstance(resolved, str) or not resolved:
        raise PaidDispatchAuthorityError("Paid provider returned no outbound model identity")
    if resolved == requested_model:
        return resolved

    # Registry aliases are safe only when both names independently resolve to
    # the exact same provider and canonical priced model contract. Opaque
    # Azure deployment mappings and unregistered aliases return ``None`` and
    # therefore remain blocked.
    from .registry_pricing import get_resolved_model_contract_identity

    requested_contract = get_resolved_model_contract_identity(requested_model)
    resolved_contract = get_resolved_model_contract_identity(resolved)
    if requested_contract is None or resolved_contract != requested_contract:
        raise PaidDispatchAuthorityError(
            f"Paid provider resolved model {resolved!r} does not share the priced contract "
            f"reserved for {requested_model!r}"
        )
    return resolved


def require_no_unaccounted_paid_webhook(request: object) -> None:
    """Reject provider callbacks until callback infrastructure has cost authority."""
    webhook = getattr(request, "webhook_url", None)
    if webhook not in (None, ""):
        raise PaidDispatchAuthorityError(
            "Paid provider webhooks are disabled until callback compute, ingress, retries, and side effects share "
            "a separately enforced cost ceiling"
        )


def require_bounded_paid_request_payload(request: object, *, provider: str | None = None) -> None:
    """Reject request features whose maximum provider charge is not provable."""
    previous_response_id = getattr(request, "previous_response_id", None)
    if previous_response_id not in (None, ""):
        raise PaidDispatchAuthorityError(
            "Paid previous_response_id is disabled because inherited provider context is not bounded by the "
            "reserved request input-token ceiling"
        )

    tools = getattr(request, "tools", None)
    if tools is None:
        tools = ()
    try:
        has_code_interpreter = any(getattr(tool, "type", None) == "code_interpreter" for tool in tools)
    except TypeError as exc:
        raise PaidDispatchAuthorityError("Paid provider tools are not a verifiable finite sequence") from exc
    if has_code_interpreter:
        raise PaidDispatchAuthorityError(
            "Paid code_interpreter is disabled until container memory and the number of billable 20-minute "
            "sessions are both provider-enforced and reserved"
        )

    if provider is None:
        return
    canonical = canonical_provider_key(provider)
    if canonical not in {"openai", "azure"}:
        return
    max_input_tokens = getattr(request, "max_input_tokens", None)
    if (
        isinstance(max_input_tokens, bool)
        or not isinstance(max_input_tokens, int)
        or max_input_tokens > _MAX_UNTIERED_OPENAI_INPUT_TOKENS
    ):
        raise PaidDispatchAuthorityError(
            "Paid OpenAI-compatible context above 128,000 input tokens is disabled until every long-context "
            "pricing threshold and rate is represented in the reservation contract"
        )
    for attribute in ("service_tier", "processing_tier", "sku"):
        value = getattr(request, attribute, None)
        if value not in (None, ""):
            raise PaidDispatchAuthorityError(
                f"Paid OpenAI-compatible {attribute} is disabled until the provider account SKU and exact "
                "pricing tier are bound to the reservation"
            )


def require_official_provider_transport(provider_instance: object, provider: str) -> str:
    """Validate a provider adapter's declared and live SDK endpoints."""
    require_unproxied_paid_transport()
    canonical = canonical_provider_key(provider)
    declared = _plain_endpoint_attribute(provider_instance, "_paid_endpoint")
    if declared is None:
        raise PaidDispatchAuthorityError(f"Paid {canonical} provider has no endpoint pricing identity")
    normalized = require_official_paid_endpoint(canonical, declared, source="provider adapter")
    clients = [getattr(provider_instance, "client", None)]
    if canonical == "azure-foundry":
        clients.extend(
            [
                getattr(provider_instance, "_project_client", None),
                getattr(provider_instance, "_agents_client", None),
            ]
        )
    for client in clients:
        if client is None:
            continue
        if canonical in {"openai", "xai", "azure"}:
            for attribute in ("organization", "project"):
                scope = _plain_endpoint_attribute(client, attribute)
                if scope:
                    raise PaidDispatchAuthorityError(
                        f"Paid {canonical} provider has an unbound OpenAI-compatible billing {attribute} scope"
                    )
        live_value = _paid_client_endpoint_value(client, canonical)
        if live_value is None:
            continue
        live = require_official_paid_endpoint(canonical, live_value, source="provider SDK client")
        if live != normalized:
            raise PaidDispatchAuthorityError("Paid provider SDK endpoint changed after pricing identity validation")
    return normalized


def require_unproxied_paid_transport() -> None:
    """Reject paid dispatch when ambient transport can change price identity."""
    configured = sorted(
        name for name, value in os.environ.items() if name.casefold() in _PROXY_ENV_NAMES and value.strip()
    )
    if configured:
        names = ", ".join(configured)
        raise PaidDispatchAuthorityError(
            f"Paid provider dispatch refuses unaccounted proxy environment variables: {names}"
        )
    unsupported_modes: list[str] = []
    unaccounted_identity: list[str] = []
    for name, value in os.environ.items():
        if not value.strip():
            continue
        folded = name.casefold()
        provider = _ENDPOINT_OVERRIDE_ENV_PROVIDERS.get(folded)
        if provider is not None:
            require_official_paid_endpoint(provider, value, source=name)
        elif folded in _UNSUPPORTED_ENDPOINT_MODE_ENV_NAMES:
            if folded.startswith("google_genai_use_") and value.strip().casefold() in {"0", "false", "no", "off"}:
                continue
            unsupported_modes.append(name)
        elif folded in _UNACCOUNTED_IDENTITY_ENV_NAMES:
            unaccounted_identity.append(name)
    if unsupported_modes:
        names = ", ".join(sorted(unsupported_modes))
        raise PaidDispatchAuthorityError(
            "Paid provider dispatch refuses endpoint modes without a priced credential identity: " + names
        )
    if unaccounted_identity:
        names = ", ".join(sorted(unaccounted_identity))
        raise PaidDispatchAuthorityError(
            "Paid provider dispatch refuses custom routing headers outside its credential identity: " + names
        )


def canonical_provider_key(provider: str) -> str:
    """Normalize the finite provider identities used by durable reservations."""
    normalized = provider.strip().casefold().replace("_", "-")
    collapsed = normalized.replace("-", "")
    if collapsed == "azurefoundry":
        return "azure-foundry"
    if collapsed in {"grok", "xai"}:
        return "xai"
    return normalized


def _mint_paid_dispatch_grant(
    *,
    provider: str,
    model: str,
    reservation_id: str,
    job_id: str,
    request_sha256: str,
) -> _PaidDispatchGrant:
    """Seal a grant after the durable reservation transition succeeds."""
    if len(request_sha256) != 64 or any(character not in "0123456789abcdef" for character in request_sha256):
        raise PaidDispatchAuthorityError("Paid dispatch request digest is invalid")
    return _PaidDispatchGrant(
        provider=canonical_provider_key(provider),
        model=model,
        reservation_id=reservation_id,
        job_id=job_id,
        request_sha256=request_sha256,
        seal=_GRANT_SEAL,
    )


def research_request_sha256(request: Any) -> str:
    """Return the canonical digest bound to a paid dispatch reservation."""
    try:
        payload = json.dumps(
            asdict(request),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PaidDispatchAuthorityError(
            "Research request cannot be bound to a deterministic dispatch authority"
        ) from exc
    return hashlib.sha256(payload).hexdigest()


@contextmanager
def authorized_paid_dispatch(
    *,
    grant: object,
    provider_instance: object,
    provider_key: str,
    request: Any,
) -> Iterator[None]:
    """Install one task-local authority from a durably minted grant."""
    require_unproxied_paid_transport()
    if not isinstance(grant, _PaidDispatchGrant) or grant.seal is not _GRANT_SEAL:
        raise PaidDispatchAuthorityError("Paid provider dispatch grant was not minted by durable accounting")
    expected_provider = canonical_provider_key(provider_key)
    if grant.consumed:
        raise PaidDispatchAuthorityError("Paid provider dispatch grant has already been consumed")
    if grant.provider != expected_provider:
        raise PaidDispatchAuthorityError("Paid provider dispatch grant belongs to another provider")
    if grant.model != getattr(request, "model", None):
        raise PaidDispatchAuthorityError("Paid provider dispatch grant belongs to another model")
    request_sha256 = research_request_sha256(request)
    if not compare_digest(grant.request_sha256, request_sha256):
        raise PaidDispatchAuthorityError("Paid provider dispatch request does not match its durable reservation")
    require_official_provider_transport(provider_instance, expected_provider)
    require_exact_provider_model(provider_instance, grant.model)
    require_no_unaccounted_paid_webhook(request)
    require_bounded_paid_request_payload(request, provider=expected_provider)
    grant.consumed = True
    authority = _PaidDispatchAuthority(
        grant=grant,
        provider_identity=id(provider_instance),
        request_sha256=request_sha256,
    )
    token = _PAID_DISPATCH_AUTHORITY.set(authority)
    try:
        yield
    finally:
        _PAID_DISPATCH_AUTHORITY.reset(token)


def consume_paid_dispatch(provider_instance: object, provider_key: str, request: Any) -> None:
    """Consume the current grant at the non-overridable public boundary."""
    authority = _matching_authority(provider_instance, provider_key, request)
    if authority.used:
        raise PaidDispatchAuthorityError("Paid provider dispatch authority has already been used")
    authority.used = True


def require_consumed_paid_dispatch(provider_instance: object, provider_key: str, request: Any) -> None:
    """Protect the adapter execution seam as well as the public method."""
    authority = _matching_authority(provider_instance, provider_key, request)
    if not authority.used:
        raise PaidDispatchAuthorityError("Paid provider adapter execution requires the consumed public authority")


def _matching_authority(provider_instance: object, provider_key: str, request: Any) -> _PaidDispatchAuthority:
    require_unproxied_paid_transport()
    authority = _PAID_DISPATCH_AUTHORITY.get()
    if authority is None:
        raise PaidDispatchAuthorityError("Paid provider dispatch requires a durable reservation and dispatch mark")
    if authority.provider_identity != id(provider_instance):
        raise PaidDispatchAuthorityError("Paid provider dispatch authority belongs to another provider instance")
    if authority.grant.provider != canonical_provider_key(provider_key):
        raise PaidDispatchAuthorityError("Paid provider dispatch authority belongs to another provider")
    if authority.grant.model != getattr(request, "model", None):
        raise PaidDispatchAuthorityError("Paid provider dispatch authority belongs to another model")
    if not compare_digest(authority.request_sha256, research_request_sha256(request)):
        raise PaidDispatchAuthorityError("Research request changed after its paid dispatch authority was minted")
    require_official_provider_transport(provider_instance, provider_key)
    require_exact_provider_model(provider_instance, authority.grant.model)
    require_no_unaccounted_paid_webhook(request)
    require_bounded_paid_request_payload(request, provider=provider_key)
    return authority
