"""One-shot OpenRouter chat completion with a fail-closed routing contract.

This is not an OpenAI SDK base-URL shim. The request pins one catalog slug,
one upstream tag, no tools, no fallbacks, and cache-off headers. Settlement
uses the provider's reported ``usage.cost``. Missing routing or cost evidence
fails closed.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import requests

from deepr.providers.dispatch_authority import default_paid_endpoint, require_official_paid_endpoint
from deepr.providers.openrouter_catalog import OPENROUTER_UPSTREAM_TAGS
from deepr.providers.registry_pricing import get_resolved_model_capability
from deepr.utils.pinned_http import close_pinned_response, pinned_post

OPENROUTER_COMPLETIONS_PATH = "/chat/completions"
_MAX_RESPONSE_BYTES = 512 * 1024
_MAX_CONTENT_CHARS = 64 * 1024
_PROVIDER_FAMILY = {
    "alibaba": "alibaba",
    "anthropic": "anthropic",
    "deepseek": "deepseek",
    "google-ai-studio": "google",
    "moonshotai/mxfp4": "moonshot",
    "openai": "openai",
    "xai/zdr": "xai",
}


class OpenRouterCompletionError(RuntimeError):
    """The OpenRouter completion could not be admitted or settled."""


@dataclass(frozen=True)
class OpenRouterCompletionResult:
    """Settled one-shot completion with provider cost evidence."""

    content: str
    model: str
    provider_name: str
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int
    generation_id: str
    finish_reason: str


def _money(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpenRouterCompletionError(f"OpenRouter {field_name} must be finite USD")
    amount = float(value)
    if not math.isfinite(amount) or amount < 0:
        raise OpenRouterCompletionError(f"OpenRouter {field_name} must be finite USD")
    return amount


def _mapping(value: object, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OpenRouterCompletionError(f"OpenRouter {field_name} must be an object")
    return value


def _message_content(value: object) -> str:
    if isinstance(value, str):
        return _text(value, field_name="message.content")
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text")
                if isinstance(text, str) and text.strip() and item.get("type") in (None, "text"):
                    parts.append(text)
        if parts:
            return _text("\n".join(parts), field_name="message.content")
    raise OpenRouterCompletionError(f"OpenRouter message.content must be text, got {type(value).__name__}")


def _text(value: object, *, field_name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise OpenRouterCompletionError(f"OpenRouter {field_name} must be text")
    if not allow_empty and not value.strip():
        raise OpenRouterCompletionError(f"OpenRouter {field_name} must be non-empty")
    if len(value) > _MAX_CONTENT_CHARS:
        raise OpenRouterCompletionError(f"OpenRouter {field_name} exceeds the content bound")
    return value


def _nonneg_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OpenRouterCompletionError(f"OpenRouter {field_name} must be a non-negative integer")
    return value


def build_openrouter_completion_request(
    *,
    model: str,
    system_message: str,
    prompt: str,
    max_tokens: int,
    prompt_max_price: float,
    completion_max_price: float,
) -> dict[str, Any]:
    """Build the exact JSON body. No tools, plugins, fallbacks, or cache."""
    capability = get_resolved_model_capability(model)
    if capability is None or capability.provider != "openrouter":
        raise OpenRouterCompletionError(f"No OpenRouter catalog contract for model {model!r}")
    slug = capability.model
    tag = OPENROUTER_UPSTREAM_TAGS.get(slug)
    if not tag:
        raise OpenRouterCompletionError(f"No pinned upstream tag for OpenRouter model {slug!r}")
    if max_tokens <= 0 or max_tokens > 16_000:
        raise OpenRouterCompletionError("OpenRouter max_tokens is outside the attended bound")
    return {
        "model": slug,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": False,
        "provider": {
            "order": [tag],
            "allow_fallbacks": False,
            "require_parameters": True,
        },
        "max_price": {
            "prompt": prompt_max_price,
            "completion": completion_max_price,
        },
    }


def _reject_forbidden_headers(headers: Mapping[str, Any]) -> None:
    for name, value in headers.items():
        key = str(name).casefold()
        if key == "x-openrouter-cache-status":
            raise OpenRouterCompletionError(
                f"OpenRouter cache status {value!r} is present; cache-off dispatch is required"
            )


def _parse_completion_payload(payload: object, *, expected_slug: str, expected_tag: str) -> OpenRouterCompletionResult:
    document = _mapping(payload, field_name="response")
    model = _text(document.get("model"), field_name="model")
    if model.casefold() != expected_slug.casefold() and not model.casefold().endswith(expected_slug.casefold()):
        raise OpenRouterCompletionError(f"OpenRouter returned model {model!r}, not {expected_slug!r}")
    provider_name = _text(document.get("provider"), field_name="provider")
    family = _PROVIDER_FAMILY.get(expected_tag, expected_tag.split("/", 1)[0])
    if family not in provider_name.casefold().replace(" ", "").replace("-", ""):
        if family not in provider_name.casefold():
            raise OpenRouterCompletionError(
                f"OpenRouter provider {provider_name!r} does not match pinned tag {expected_tag!r}"
            )
    usage = _mapping(document.get("usage"), field_name="usage")
    cost = _money(usage.get("cost"), field_name="usage.cost")
    if usage.get("is_byok") is True:
        raise OpenRouterCompletionError("OpenRouter completion used BYOK")
    choices = document.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise OpenRouterCompletionError("OpenRouter completion must return exactly one choice")
    choice = _mapping(choices[0], field_name="choices[0]")
    message = _mapping(choice.get("message"), field_name="message")
    content = _message_content(message.get("content"))
    finish_reason = _text(choice.get("finish_reason"), field_name="finish_reason")
    generation_id = _text(document.get("id"), field_name="id")
    return OpenRouterCompletionResult(
        content=content,
        model=model,
        provider_name=provider_name,
        cost_usd=cost,
        prompt_tokens=_nonneg_int(usage.get("prompt_tokens"), field_name="prompt_tokens"),
        completion_tokens=_nonneg_int(usage.get("completion_tokens"), field_name="completion_tokens"),
        generation_id=generation_id,
        finish_reason=finish_reason,
    )


def complete_openrouter_chat(
    *,
    api_key: str,
    model: str,
    system_message: str,
    prompt: str,
    max_tokens: int,
    prompt_max_price: float,
    completion_max_price: float,
) -> OpenRouterCompletionResult:
    """POST one pinned completion. Caller holds reservation and key release."""
    capability = get_resolved_model_capability(model)
    if capability is None or capability.provider != "openrouter":
        raise OpenRouterCompletionError(f"No OpenRouter catalog contract for model {model!r}")
    slug = capability.model
    tag = OPENROUTER_UPSTREAM_TAGS[slug]
    endpoint = require_official_paid_endpoint("openrouter", default_paid_endpoint("openrouter"))
    url = f"{endpoint}{OPENROUTER_COMPLETIONS_PATH}"
    body = build_openrouter_completion_request(
        model=model,
        system_message=system_message,
        prompt=prompt,
        max_tokens=max_tokens,
        prompt_max_price=prompt_max_price,
        completion_max_price=completion_max_price,
    )
    raw_body = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    try:
        response = pinned_post(
            url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "deepr-openrouter-attended/1",
                "X-OpenRouter-Cache": "false",
                "X-OpenRouter-Metadata": "enabled",
                "HTTP-Referer": "https://github.com/blisspixel/deepr",
                "X-Title": "Deepr",
            },
            data=raw_body,
            timeout=(5.0, 120.0),
            allow_redirects=False,
            stream=True,
            redact_request_target=True,
        )
    except (requests.RequestException, OSError, ValueError) as exc:
        raise OpenRouterCompletionError("OpenRouter completion request failed") from exc
    try:
        _reject_forbidden_headers(response.headers)
        if response.status_code != 200:
            raise OpenRouterCompletionError(f"OpenRouter completion returned HTTP {response.status_code}")
        content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().casefold()
        if content_type != "application/json":
            raise OpenRouterCompletionError("OpenRouter completion did not return application/json")
        chunks = bytearray()
        for chunk in response.iter_content(chunk_size=16 * 1024):
            if not isinstance(chunk, bytes):
                raise OpenRouterCompletionError("OpenRouter completion returned a non-byte chunk")
            chunks.extend(chunk)
            if len(chunks) > _MAX_RESPONSE_BYTES:
                raise OpenRouterCompletionError("OpenRouter completion exceeds the response byte ceiling")
        payload = json.loads(bytes(chunks).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise OpenRouterCompletionError("OpenRouter completion is not strict UTF-8 JSON") from exc
    finally:
        close_pinned_response(response)
    return _parse_completion_payload(payload, expected_slug=slug, expected_tag=tag)


__all__ = [
    "OpenRouterCompletionError",
    "OpenRouterCompletionResult",
    "build_openrouter_completion_request",
    "complete_openrouter_chat",
]
