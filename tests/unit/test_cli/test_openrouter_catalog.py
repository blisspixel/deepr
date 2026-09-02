"""CLI coverage for the write-free OpenRouter catalog proof."""

from __future__ import annotations

import json
from typing import Any

import pytest
from click.testing import CliRunner

from deepr.cli.commands.providers import providers
from deepr.providers.openrouter_catalog_check import (
    OpenRouterCatalogCheckError,
    OpenRouterCatalogProof,
    openrouter_models,
)


def _proof(*, eligible: bool = True) -> OpenRouterCatalogProof:
    return OpenRouterCatalogProof(
        model="openai/gpt-5.6-sol",
        upstream_tag="openai",
        provider_name="OpenAI",
        catalog_eligible=eligible,
        failures=() if eligible else ("price drift",),
        observed_input_cost_per_1m=2.0,
        observed_output_cost_per_1m=10.0,
        observed_cache_read_cost_per_1m=0.2,
        observed_cache_write_cost_per_1m=2.5,
        observed_reasoning_cost_per_1m=10.0,
        observed_request_cost_usd=0.0,
        registered_input_cap_per_1m=2.0,
        registered_output_cap_per_1m=10.0,
        registered_cache_read_cap_per_1m=0.2,
        registered_cache_write_cap_per_1m=2.5,
        cache_write_price_source="endpoint_metadata",
        context_length=1_050_000,
        max_prompt_tokens=922_000,
        max_completion_tokens=128_000,
        endpoint_status=0,
        source_sha256="a" * 64,
        routing_policy_sha256="b" * 64,
        matched_endpoint_tags=("openai",),
    )


def test_openrouter_check_json_is_explicitly_non_authorizing(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, ...]] = []

    def fake_check(models: tuple[str, ...]) -> tuple[OpenRouterCatalogProof, ...]:
        captured.append(models)
        return (_proof(),)

    monkeypatch.setattr("deepr.cli.commands.openrouter_catalog.check_openrouter_catalog", fake_check)
    result = CliRunner().invoke(
        providers,
        ["openrouter-check", "--model", "openai/gpt-5.6-sol", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert captured == [("openai/gpt-5.6-sol",)]
    assert payload["schema_version"] == "deepr-openrouter-catalog-check-v2"
    assert payload["all_catalog_eligible"] is True
    assert payload["paid_requests"] == 0
    assert payload["api_key_loaded"] is False
    assert payload["dispatch_authorized"] is False
    assert payload["proofs"][0]["routing_policy_sha256"] == "b" * 64
    assert payload["proofs"][0]["proposed_provider_routing"] == {
        "order": ["openai"],
        "only": ["openai"],
        "allow_fallbacks": False,
        "require_parameters": True,
        "data_collection": "deny",
        "max_price": {"prompt": 2.0, "completion": 10.0, "request": 0.0},
    }
    assert payload["proofs"][0]["proposed_request_headers"] == {
        "X-OpenRouter-Cache": "false",
        "X-OpenRouter-Metadata": "enabled",
    }


def test_openrouter_check_defaults_to_every_registered_route(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, ...]] = []

    def fake_check(models: tuple[str, ...]) -> tuple[OpenRouterCatalogProof, ...]:
        captured.append(models)
        return (_proof(),)

    monkeypatch.setattr("deepr.cli.commands.openrouter_catalog.check_openrouter_catalog", fake_check)
    result = CliRunner().invoke(providers, ["openrouter-check"])
    assert result.exit_code == 0, result.output
    assert captured == [openrouter_models()]
    assert "0 paid requests" in result.output
    assert "no API key loaded" in result.output
    assert "dispatch remains blocked" in result.output


def test_openrouter_check_returns_nonzero_when_a_route_drifts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deepr.cli.commands.openrouter_catalog.check_openrouter_catalog",
        lambda models: (_proof(eligible=False),),
    )
    result = CliRunner().invoke(
        providers,
        ["openrouter-check", "--model", "openai/gpt-5.6-sol", "--json"],
    )
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["all_catalog_eligible"] is False
    assert payload["proofs"][0]["failures"] == ["price drift"]


def test_openrouter_check_reports_contract_errors_without_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(models: tuple[str, ...]) -> Any:
        raise OpenRouterCatalogCheckError("bounded public metadata failure")

    monkeypatch.setattr("deepr.cli.commands.openrouter_catalog.check_openrouter_catalog", fail)
    result = CliRunner().invoke(providers, ["openrouter-check"])
    assert result.exit_code == 1
    assert "bounded public metadata failure" in result.output
    assert "Traceback" not in result.output
