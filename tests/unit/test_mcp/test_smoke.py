"""Tests for HTTP MCP smoke checks."""

from __future__ import annotations

import json
from typing import Any

import aiohttp
import pytest

from deepr.mcp import smoke
from deepr.mcp.smoke import (
    REGISTRATION_MANIFEST_KIND,
    REGISTRATION_MANIFEST_SCHEMA_VERSION,
    MCPHttpSmokeReport,
    MCPHttpSmokeStep,
    build_http_registration_manifest,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://127.0.0.1:8765/mcp/", "https://mcp.example.com/mcp"])
async def test_run_http_smoke_blocks_before_network(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_client(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise AssertionError("network client must not be constructed")

    monkeypatch.setattr(aiohttp, "ClientSession", fail_client)

    report = await smoke.run_http_smoke(
        url,
        auth_token="secret",
        timeout_seconds=2.0,
    )
    payload = report.to_dict()

    assert report.ok is False
    assert report.steps[0].name == "remote_cost_authority"
    assert payload["contract"]["network_opened"] is False
    assert payload["contract"]["remote_tool_call_attempted"] is False
    assert payload["contract"]["remote_tool_calls_metered_api"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 0.0, -1.0, 301.0])
async def test_run_http_smoke_rejects_timeout_before_network(timeout: float, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        aiohttp,
        "ClientSession",
        lambda *args, **kwargs: pytest.fail("network client must not be constructed"),
    )

    report = await smoke.run_http_smoke(
        "https://mcp.example.com/mcp",
        timeout_seconds=timeout,
    )

    assert report.ok is False
    assert report.steps[0].name == "http_preflight"


def test_smoke_report_serializes_status_code():
    step = MCPHttpSmokeStep("health", True, "healthy", status_code=200)

    assert step.to_dict() == {
        "name": "health",
        "ok": True,
        "detail": "healthy",
        "status_code": 200,
    }


def test_registration_manifest_redacts_auth_secret_and_embeds_smoke_report():
    report = MCPHttpSmokeReport(
        url="https://mcp.example.com/mcp",
        steps=(MCPHttpSmokeStep("health", True, "healthy", status_code=200),),
    )

    manifest = build_http_registration_manifest(
        "https://mcp.example.com/mcp/",
        smoke_report=report,
        agent_name="planner",
    )

    assert manifest["schema_version"] == REGISTRATION_MANIFEST_SCHEMA_VERSION
    assert manifest["kind"] == REGISTRATION_MANIFEST_KIND
    assert manifest["agent_name"] == "planner"
    assert manifest["transport"]["url"] == "https://mcp.example.com/mcp"
    assert manifest["transport"]["health_url"] == "https://mcp.example.com/mcp/health"
    assert manifest["auth"]["secret_included"] is False
    assert manifest["auth"]["token_env_var"] == "DEEPR_MCP_KEY"
    assert manifest["registration"]["smoke_command"] is None
    assert manifest["registration"]["free_smoke_tool"] is None
    assert manifest["registration"]["remote_smoke_status"] == "blocked_pending_cost_authority"
    assert manifest["smoke"]["ok"] is True
    assert "test-token-value" not in json.dumps(manifest)
