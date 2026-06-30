"""Tests for no-metered MCP consult validation."""

from __future__ import annotations

import json

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
from deepr.mcp.transport.http import HttpMessage


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


class _FakeHttpClient:
    instances: list[_FakeHttpClient] = []

    def __init__(self, base_url: str, timeout: float = 30.0, auth_token: str | None = None):
        self.base_url = base_url
        self.timeout = timeout
        self.auth_token = auth_token
        self.sent: list[HttpMessage] = []
        self.disconnected = False
        _FakeHttpClient.instances.append(self)

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        self.disconnected = True

    async def send(self, message: HttpMessage) -> HttpMessage:
        self.sent.append(message)
        if message.method == "initialize":
            return HttpMessage(id=message.id, result={"serverInfo": {"name": "deepr-research"}})
        if message.method == "tools/call":
            payload = build_offline_consult_fixture(experts=("A",))
            return HttpMessage(
                id=message.id,
                result={
                    "content": [{"type": "text", "text": json.dumps(payload)}],
                    "structuredContent": payload,
                    "isError": False,
                },
            )
        raise AssertionError(f"unexpected method {message.method}")


@pytest.mark.asyncio
async def test_http_consult_validation_calls_remote_consult_tool(monkeypatch):
    _FakeHttpClient.instances = []
    monkeypatch.setattr(consult_validation, "HttpClient", _FakeHttpClient)

    report = await run_http_consult_validation(
        "http://127.0.0.1:8765/mcp/",
        auth_token="secret-token",
        experts=("A",),
        timeout_seconds=2.0,
    )

    assert report.ok is True
    assert report.endpoint == "http://127.0.0.1:8765/mcp"
    assert _FakeHttpClient.instances[0].auth_token == "secret-token"
    assert _FakeHttpClient.instances[0].disconnected is True
    assert [message.method for message in _FakeHttpClient.instances[0].sent] == ["initialize", "tools/call"]
    call = _FakeHttpClient.instances[0].sent[1]
    assert call.params["name"] == "deepr_consult_experts"
    assert call.params["arguments"]["_approved"] is True
    assert call.params["arguments"]["budget"] == 0
    assert call.params["arguments"]["synthesis_backend"] == "local"


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
