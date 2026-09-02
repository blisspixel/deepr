"""OpenRouter public catalog proof tests."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

import pytest

from deepr.providers.openrouter_catalog import (
    OPENROUTER_CACHE_WRITE_PRICE_SOURCES,
    OPENROUTER_CAPABILITIES,
    OPENROUTER_UPSTREAM_TAGS,
)
from deepr.providers.openrouter_catalog_check import (
    FetchedOpenRouterDocument,
    OpenRouterCatalogCheckError,
    build_openrouter_routing_policy,
    check_openrouter_catalog,
    evaluate_openrouter_endpoint_document,
    fetch_openrouter_endpoint_document,
    openrouter_models,
)

_SOURCE_SHA256 = "a" * 64


def _per_token(per_million: float) -> str:
    return format(Decimal(str(per_million)) / Decimal(1_000_000), "f")


def _document(
    model: str,
    *,
    tag: str | None = None,
    input_price: float | None = None,
    output_price: float | None = None,
    cache_read_price: float | None = None,
    cache_write_price: float | None = None,
    reasoning_price: float | None = None,
    request_price: float | None = None,
    omit_cache_write_price: bool = False,
    status: int = 0,
    context_length: int = 1_050_000,
    max_prompt_tokens: int | None = 900_000,
    max_completion_tokens: int | None = 128_000,
    parameters: list[str] | None = None,
    overrides: list[dict[str, Any]] | None = None,
    extra_endpoints: list[dict[str, Any]] | None = None,
) -> FetchedOpenRouterDocument:
    capability = OPENROUTER_CAPABILITIES[f"openrouter/{model}"]
    pricing: dict[str, Any] = {
        "prompt": _per_token(input_price if input_price is not None else capability.input_cost_per_1m),
        "completion": _per_token(output_price if output_price is not None else capability.output_cost_per_1m),
    }
    pricing["input_cache_read"] = _per_token(
        cache_read_price if cache_read_price is not None else capability.cached_input_cost_per_1m or 0.0
    )
    if reasoning_price is not None:
        pricing["internal_reasoning"] = _per_token(reasoning_price)
    if request_price is not None:
        pricing["request"] = format(Decimal(str(request_price)), "f")
    if OPENROUTER_CACHE_WRITE_PRICE_SOURCES[model] == "endpoint_metadata" and not omit_cache_write_price:
        pricing["input_cache_write"] = _per_token(
            cache_write_price if cache_write_price is not None else capability.cache_write_cost_per_1m or 0.0
        )
    if overrides is not None:
        pricing["overrides"] = overrides
    endpoint = {
        "tag": tag or OPENROUTER_UPSTREAM_TAGS[model],
        "provider_name": "Exact Provider",
        "status": status,
        "context_length": context_length,
        "max_prompt_tokens": max_prompt_tokens,
        "max_completion_tokens": max_completion_tokens,
        "supported_parameters": parameters or ["max_tokens", "response_format"],
        "pricing": pricing,
    }
    return FetchedOpenRouterDocument(
        payload={"data": {"id": model, "endpoints": [endpoint, *(extra_endpoints or [])]}},
        source_sha256=_SOURCE_SHA256,
    )


def test_routing_policies_pin_one_endpoint_and_disable_fallbacks() -> None:
    assert openrouter_models() == tuple(sorted(OPENROUTER_UPSTREAM_TAGS))
    for model, upstream_tag in OPENROUTER_UPSTREAM_TAGS.items():
        capability = OPENROUTER_CAPABILITIES[f"openrouter/{model}"]
        policy = build_openrouter_routing_policy(model)
        assert policy == {
            "order": [upstream_tag],
            "only": [upstream_tag],
            "allow_fallbacks": False,
            "require_parameters": True,
            "data_collection": "deny",
            "max_price": {
                "prompt": capability.input_cost_per_1m,
                "completion": capability.output_cost_per_1m,
                "request": 0.0,
            },
        }


@pytest.mark.parametrize("model", openrouter_models())
def test_exact_catalog_route_is_eligible(model: str) -> None:
    proof = evaluate_openrouter_endpoint_document(model, _document(model))
    assert proof.catalog_eligible is True
    assert proof.failures == ()
    assert proof.upstream_tag == OPENROUTER_UPSTREAM_TAGS[model]
    assert proof.matched_endpoint_tags == (OPENROUTER_UPSTREAM_TAGS[model],)
    assert len(proof.routing_policy_sha256) == 64
    assert proof.to_dict()["dispatch_authorized"] is False
    assert proof.to_dict()["paid_requests"] == 0
    assert proof.observed_cache_write_cost_per_1m is not None
    assert proof.to_dict()["proposed_request_headers"] == {
        "X-OpenRouter-Cache": "false",
        "X-OpenRouter-Metadata": "enabled",
    }
    assert "explicit_prompt_cache_control" in proof.to_dict()["forbidden_request_features"]


def test_route_requires_one_exact_upstream_tag() -> None:
    model = "openai/gpt-5.6-sol"
    missing = evaluate_openrouter_endpoint_document(model, _document(model, tag="azure"))
    assert missing.catalog_eligible is False
    assert "one standard endpoint metadata record" in missing.failures[0]

    duplicate = _document(model)
    endpoint = duplicate.payload["data"]["endpoints"][0]  # type: ignore[index]
    duplicate = _document(model, extra_endpoints=[dict(endpoint)])
    proof = evaluate_openrouter_endpoint_document(model, duplicate)
    assert proof.catalog_eligible is False
    assert "one standard endpoint metadata record" in proof.failures[0]


def test_base_route_rejects_an_additional_non_tier_variant() -> None:
    model = "openai/gpt-5.6-sol"
    sibling = _document(model).payload["data"]["endpoints"][0]  # type: ignore[index]
    proof = evaluate_openrouter_endpoint_document(
        model,
        _document(model, extra_endpoints=[{**sibling, "tag": "openai/us-east"}]),
    )
    assert proof.catalog_eligible is False
    assert "one standard endpoint metadata record" in proof.failures[0]


@pytest.mark.parametrize("suffix", ["fast", "flex", "priority"])
def test_base_route_excludes_opt_in_service_tiers(suffix: str) -> None:
    model = "openai/gpt-5.6-sol"
    tier = _document(model).payload["data"]["endpoints"][0]  # type: ignore[index]
    proof = evaluate_openrouter_endpoint_document(
        model,
        _document(model, extra_endpoints=[{**tier, "tag": f"openai/{suffix}"}]),
    )
    assert proof.catalog_eligible is True


@pytest.mark.parametrize(
    ("changes", "failure"),
    [
        ({"status": -2}, "status is -2"),
        ({"context_length": 143_999}, "context is below"),
        ({"max_prompt_tokens": 127_999}, "prompt ceiling"),
        ({"max_completion_tokens": 15_999}, "completion ceiling"),
        ({"max_completion_tokens": None}, "completion ceiling"),
        ({"parameters": ["max_tokens"]}, "response_format"),
    ],
)
def test_route_fails_closed_on_endpoint_posture(changes: dict[str, Any], failure: str) -> None:
    model = "openai/gpt-5.6-sol"
    proof = evaluate_openrouter_endpoint_document(model, _document(model, **changes))
    assert proof.catalog_eligible is False
    assert any(failure in item for item in proof.failures)


def test_route_fails_when_base_price_exceeds_registered_cap() -> None:
    model = "google/gemini-3.6-flash"
    capability = OPENROUTER_CAPABILITIES[f"openrouter/{model}"]
    proof = evaluate_openrouter_endpoint_document(
        model,
        _document(
            model,
            input_price=capability.input_cost_per_1m + 0.01,
            output_price=capability.output_cost_per_1m + 0.01,
        ),
    )
    assert proof.catalog_eligible is False
    assert any("prompt price" in failure for failure in proof.failures)
    assert any("completion price" in failure for failure in proof.failures)


def test_route_fails_when_cache_write_price_exceeds_registered_cap() -> None:
    model = "qwen/qwen3.8-flash"
    capability = OPENROUTER_CAPABILITIES[f"openrouter/{model}"]
    proof = evaluate_openrouter_endpoint_document(
        model,
        _document(
            model,
            cache_write_price=(capability.cache_write_cost_per_1m or 0.0) + 0.01,
        ),
    )
    assert proof.catalog_eligible is False
    assert any("cache-write price" in failure for failure in proof.failures)


def test_route_fails_when_cache_read_price_exceeds_registered_cache_cap() -> None:
    model = "openai/gpt-5.6-sol"
    proof = evaluate_openrouter_endpoint_document(model, _document(model, cache_read_price=0.21))
    assert proof.catalog_eligible is False
    assert any("cache-read price" in failure for failure in proof.failures)


@pytest.mark.parametrize(
    ("changes", "failure"),
    [
        ({"reasoning_price": 10.01}, "reasoning price"),
        ({"request_price": 0.001}, "fixed request price"),
    ],
)
def test_route_fails_when_text_inference_price_bucket_exceeds_cap(
    changes: dict[str, Any],
    failure: str,
) -> None:
    model = "openai/gpt-5.6-sol"
    proof = evaluate_openrouter_endpoint_document(model, _document(model, **changes))
    assert proof.catalog_eligible is False
    assert any(failure in item for item in proof.failures)


def test_route_requires_metadata_cache_write_price_when_registered_as_source() -> None:
    model = "openai/gpt-5.6-sol"
    proof = evaluate_openrouter_endpoint_document(
        model,
        _document(model, omit_cache_write_price=True),
    )
    assert proof.catalog_eligible is False
    assert "omits the required cache-write price" in proof.failures[0]


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("x-ai/grok-4.6", 0.0),
        ("moonshotai/kimi-k3", 0.0),
        ("deepseek/deepseek-v4-flash-0731", 0.44),
    ],
)
def test_documented_cache_write_fallbacks_are_explicit(model: str, expected: float) -> None:
    proof = evaluate_openrouter_endpoint_document(model, _document(model))
    assert proof.catalog_eligible is True
    assert proof.observed_cache_write_cost_per_1m == pytest.approx(expected)


def test_reachable_override_uses_the_most_expensive_price() -> None:
    model = "x-ai/grok-4.6"
    proof = evaluate_openrouter_endpoint_document(
        model,
        _document(
            model,
            overrides=[
                {
                    "min_prompt_tokens": 100_000,
                    "prompt": _per_token(4.0),
                    "completion": _per_token(12.0),
                    "input_cache_write": _per_token(1.0),
                }
            ],
        ),
    )
    assert proof.catalog_eligible is False
    assert proof.observed_input_cost_per_1m == 4.0
    assert proof.observed_output_cost_per_1m == 12.0


def test_reachable_override_uses_the_most_expensive_cache_write_price() -> None:
    model = "openai/gpt-5.6-sol"
    proof = evaluate_openrouter_endpoint_document(
        model,
        _document(
            model,
            overrides=[
                {
                    "min_prompt_tokens": 100_000,
                    "input_cache_write": _per_token(3.0),
                }
            ],
        ),
    )
    assert proof.catalog_eligible is False
    assert proof.observed_cache_write_cost_per_1m == 3.0
    assert any("cache-write price" in failure for failure in proof.failures)


@pytest.mark.parametrize(
    ("field", "value", "failure"),
    [
        ("input_cache_read", _per_token(0.21), "cache-read price"),
        ("internal_reasoning", _per_token(10.01), "reasoning price"),
        ("request", "0.001", "fixed request price"),
    ],
)
def test_reachable_override_checks_auxiliary_text_prices(field: str, value: str, failure: str) -> None:
    model = "openai/gpt-5.6-sol"
    proof = evaluate_openrouter_endpoint_document(
        model,
        _document(model, overrides=[{"min_prompt_tokens": 100_000, field: value}]),
    )
    assert proof.catalog_eligible is False
    assert any(failure in item for item in proof.failures)


@pytest.mark.parametrize("discount", [-0.1, 1.0, "0"])
def test_route_rejects_unsafe_or_malformed_discount(discount: object) -> None:
    model = "openai/gpt-5.6-sol"
    document = _document(model)
    document.payload["data"]["endpoints"][0]["pricing"]["discount"] = discount  # type: ignore[index]
    proof = evaluate_openrouter_endpoint_document(model, document)
    assert proof.catalog_eligible is False
    assert "discount" in proof.failures[0]


def test_route_rejects_unclassified_pricing_field() -> None:
    model = "openai/gpt-5.6-sol"
    document = _document(model)
    document.payload["data"]["endpoints"][0]["pricing"]["new_billable_unit"] = "0.01"  # type: ignore[index]
    proof = evaluate_openrouter_endpoint_document(model, document)
    assert proof.catalog_eligible is False
    assert "unclassified pricing field" in proof.failures[0]


def test_unreachable_long_context_override_does_not_inflate_bounded_route() -> None:
    model = "openai/gpt-5.6-sol"
    proof = evaluate_openrouter_endpoint_document(
        model,
        _document(
            model,
            overrides=[
                {
                    "min_prompt_tokens": 272_000,
                    "prompt": _per_token(100.0),
                    "completion": _per_token(100.0),
                }
            ],
        ),
    )
    assert proof.catalog_eligible is True


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": {"id": "wrong/model", "endpoints": []}},
        {"data": {"id": "openai/gpt-5.6-sol", "endpoints": "opaque"}},
    ],
)
def test_malformed_documents_return_non_authorizing_proof(payload: object) -> None:
    model = "openai/gpt-5.6-sol"
    proof = evaluate_openrouter_endpoint_document(
        model,
        FetchedOpenRouterDocument(payload=payload, source_sha256=_SOURCE_SHA256),
    )
    assert proof.catalog_eligible is False
    assert proof.to_dict()["dispatch_authorized"] is False


def test_catalog_check_continues_after_one_fetch_failure() -> None:
    models = ("openai/gpt-5.6-sol", "qwen/qwen3.8-flash")

    def fetcher(model: str) -> FetchedOpenRouterDocument:
        if model == models[0]:
            raise OpenRouterCatalogCheckError("metadata unavailable")
        return _document(model)

    proofs = check_openrouter_catalog(models, fetcher=fetcher)
    assert [proof.catalog_eligible for proof in proofs] == [False, True]
    assert proofs[0].failures == ("metadata unavailable",)


@pytest.mark.parametrize("models", [(), ("unknown/model",), ("openai/gpt-5.6-sol",) * 2])
def test_catalog_check_rejects_invalid_model_sequences(models: tuple[str, ...]) -> None:
    with pytest.raises(OpenRouterCatalogCheckError):
        check_openrouter_catalog(models, fetcher=lambda model: _document(model))


class _FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status_code: int = 200,
        content_type: str = "application/json",
        content_length: str | None = None,
    ) -> None:
        self.body = body
        self.status_code = status_code
        self.headers: dict[str, str] = {"Content-Type": content_type}
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [self.body[index : index + chunk_size] for index in range(0, len(self.body), chunk_size)]


def test_fetch_is_public_bounded_and_closes_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    model = "openai/gpt-5.6-sol"
    raw = json.dumps(_document(model).payload).encode()
    response = _FakeResponse(raw, content_length=str(len(raw)))
    captured: dict[str, Any] = {}
    closed: list[object] = []

    def fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        captured.update({"url": url, **kwargs})
        return response

    monkeypatch.setattr("deepr.providers.openrouter_catalog_check.pinned_get", fake_get)
    monkeypatch.setattr("deepr.providers.openrouter_catalog_check.close_pinned_response", closed.append)
    document = fetch_openrouter_endpoint_document(model)

    assert captured["url"].endswith("/openai/gpt-5.6-sol/endpoints")
    assert captured["allow_redirects"] is False
    assert captured["stream"] is True
    assert "Authorization" not in captured["headers"]
    assert document.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert closed == [response]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_FakeResponse(b"{}", status_code=500), "HTTP 500"),
        (_FakeResponse(b"{}", content_type="text/html"), "application/json"),
        (_FakeResponse(b"{}", content_length=str(3 * 1024 * 1024)), "byte ceiling"),
        (_FakeResponse(b"{}", content_length="opaque"), "Content-Length"),
        (_FakeResponse(b'{"data":1,"data":2}'), "duplicate object key"),
    ],
)
def test_fetch_fails_closed_on_untrusted_response(
    monkeypatch: pytest.MonkeyPatch,
    response: _FakeResponse,
    message: str,
) -> None:
    monkeypatch.setattr("deepr.providers.openrouter_catalog_check.pinned_get", lambda *args, **kwargs: response)
    monkeypatch.setattr("deepr.providers.openrouter_catalog_check.close_pinned_response", lambda value: None)
    with pytest.raises(OpenRouterCatalogCheckError, match=message):
        fetch_openrouter_endpoint_document("openai/gpt-5.6-sol")
