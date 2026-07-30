"""Tests for no-metered MCP consult validation."""

from __future__ import annotations

from typing import Any

import aiohttp
import pytest

from deepr.mcp import consult_validation
from deepr.mcp.consult_validation import (
    MCPConsultValidationCheck,
    MCPConsultValidationReport,
    PlanConsultFleetTarget,
    build_offline_consult_fixture,
    run_http_consult_validation,
    run_in_process_consult_validation,
    run_in_process_plan_consult_fleet_validation,
    run_offline_consult_validation,
    validate_consult_payload,
)


def test_offline_consult_validation_passes_contract_checks():
    report = run_offline_consult_validation(experts=("AI Agent Harnesses",))
    payload = report.to_dict()

    assert report.ok is True
    assert payload["schema_version"] == "deepr-mcp-consult-validation-v1"
    assert payload["contract"]["calls_metered_api"] is False
    assert payload["consult_summary"]["schema_version"] == "deepr-consult-v1"
    assert payload["consult_summary"]["capacity"]["live_metered_fallback"] is False
    assert "no_metered_fallback" not in payload["summary"]["failed_checks"]


def test_consult_validation_rejects_metered_fallback():
    payload = build_offline_consult_fixture(experts=("A",))
    payload["capacity"]["live_metered_fallback"] = True
    payload["collaboration"]["budget_capacity_contract"]["metered_fallback_allowed"] = True

    checks = validate_consult_payload(payload, expected_backend="local")

    failed = {check.name for check in checks if check.status == "failed"}
    assert "no_metered_fallback" in failed


def test_consult_validation_detects_secret_echo():
    payload = build_offline_consult_fixture(experts=("A",))
    payload["answer"] = "leaked-secret"

    checks = validate_consult_payload(payload, expected_backend="local", forbidden_values=("leaked-secret",))

    failed = {check.name for check in checks if check.status == "failed"}
    assert "secret_redaction" in failed


def test_consult_validation_rejects_failed_synthesis_status():
    payload = build_offline_consult_fixture(experts=("A",))
    payload["synthesis_status"] = "failed"
    payload["synthesis_error_type"] = "PlanQuotaError"

    checks = validate_consult_payload(payload, expected_backend="local")

    failed = {check.name for check in checks if check.status == "failed"}
    assert "synthesis_status" in failed


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://127.0.0.1:8765/mcp/", "https://mcp.example.com/mcp"])
async def test_http_consult_validation_blocks_before_client_construction(url, monkeypatch):
    def fail_client(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("remote client must not be constructed")

    monkeypatch.setattr(aiohttp, "ClientSession", fail_client)

    report = await run_http_consult_validation(
        url,
        auth_token="secret-token",
        experts=("A",),
        timeout_seconds=2.0,
    )
    contract = report.to_dict()["contract"]

    assert report.ok is False
    assert report.error["error_code"] == "MCP_HTTP_CONSULT_VALIDATION_BLOCKED"
    assert contract["remote_tool_call_attempted"] is False
    assert contract["remote_tool_cost_status"] == "not_submitted"
    assert contract["remote_tool_calls_metered_api"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 0.0, -1.0, 301.0])
async def test_http_consult_validation_rejects_invalid_timeout_before_client(timeout, monkeypatch):
    monkeypatch.setattr(
        aiohttp,
        "ClientSession",
        lambda *args, **kwargs: pytest.fail("remote client must not be constructed"),
    )

    report = await run_http_consult_validation(
        "https://mcp.example.com/mcp",
        timeout_seconds=timeout,
    )

    assert report.ok is False
    assert report.error["error_code"] == "INVALID_HTTP_PREFLIGHT"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.01, "0", None, True])
@pytest.mark.parametrize("location", ["payload", "contract", "budget"])
def test_consult_validation_rejects_invalid_cost_fields(location: str, value: Any) -> None:
    payload = build_offline_consult_fixture(experts=("A",))
    if location == "payload":
        payload["cost_usd"] = value
    elif location == "contract":
        payload["contract"]["cost_usd"] = value
    else:
        payload["collaboration"]["budget_capacity_contract"]["actual_cost_usd"] = value

    checks = validate_consult_payload(payload, expected_backend="local")

    failed = {check.name for check in checks if check.status == "failed"}
    assert "cost_ceiling" in failed


@pytest.mark.parametrize("ceiling", [float("nan"), float("inf"), -0.01, "0", None, True])
def test_consult_validation_rejects_invalid_cost_ceiling(ceiling: Any) -> None:
    payload = build_offline_consult_fixture(experts=("A",))

    checks = validate_consult_payload(payload, expected_backend="local", cost_ceiling_usd=ceiling)

    failed = {check.name for check in checks if check.status == "failed"}
    assert "cost_ceiling" in failed


def test_validation_check_failure_marks_report_failed():
    report = consult_validation.MCPConsultValidationReport(
        mode="offline",
        backend="local",
        question="q",
        requested_experts=(),
        checks=(MCPConsultValidationCheck("x", "failed", "bad"),),
    )

    assert report.ok is False
    assert report.to_dict()["summary"]["failed_checks"] == ["x"]


@pytest.mark.asyncio
async def test_in_process_consult_validation_reports_timeout_detail(monkeypatch):
    async def fake_tool(**_kwargs):
        raise TimeoutError()

    monkeypatch.setattr(consult_validation, "consult_experts_tool", fake_tool)

    report = await run_in_process_consult_validation(backend="plan", plan="grok", timeout_seconds=1.5)

    assert report.ok is False
    assert report.error["message"] == "live plan consult plan=grok timed out after 1.5s"
    assert report.checks[0].detail == report.error["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 0.0, -1.0, 301.0])
async def test_in_process_consult_validation_rejects_invalid_timeout_before_tool(timeout, monkeypatch):
    async def fail_tool(**_kwargs):
        raise AssertionError("consult tool must not run")

    monkeypatch.setattr(consult_validation, "consult_experts_tool", fail_tool)

    report = await run_in_process_consult_validation(timeout_seconds=timeout)

    assert report.ok is False
    assert report.error["error_code"] == "INVALID_TIMEOUT"


@pytest.mark.asyncio
async def test_plan_consult_fleet_validation_runs_selected_targets(monkeypatch):
    calls: list[str | None] = []

    async def fake_validation(**kwargs):
        calls.append(kwargs["plan"])
        return MCPConsultValidationReport(
            mode="in_process",
            backend="plan",
            plan=kwargs["plan"],
            question=kwargs["question"],
            requested_experts=kwargs["experts"],
            checks=(MCPConsultValidationCheck("x", "passed", "ok"),),
        )

    monkeypatch.setattr(consult_validation, "run_in_process_consult_validation", fake_validation)

    payload = await run_in_process_plan_consult_fleet_validation(
        targets=(
            PlanConsultFleetTarget("codex", "Codex", installed=True),
            PlanConsultFleetTarget("claude", "Claude", installed=True),
        ),
        question="q",
        experts=("AI Agent Harnesses",),
        concurrency=2,
    )

    assert payload["schema_version"] == "deepr-mcp-consult-fleet-validation-v1"
    assert payload["ok_count"] == 2
    assert payload["failed_count"] == 0
    assert payload["summary"]["ok"] is True
    assert calls == ["codex", "claude"]


@pytest.mark.asyncio
async def test_plan_consult_fleet_validation_skips_without_call(monkeypatch):
    async def fake_validation(**_kwargs):
        raise AssertionError("skipped targets must not run a consult")

    monkeypatch.setattr(consult_validation, "run_in_process_consult_validation", fake_validation)

    payload = await run_in_process_plan_consult_fleet_validation(
        targets=(PlanConsultFleetTarget("copilot", "Copilot", installed=True, skip_reason="metered"),),
    )

    assert payload["validated_count"] == 0
    assert payload["skipped_count"] == 1
    assert payload["results"][0]["status"] == "skipped"
