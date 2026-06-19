"""Tests for HTTP MCP smoke checks."""

from __future__ import annotations

import json
from typing import Any

import pytest

from deepr.mcp import smoke
from deepr.mcp.smoke import MCPHttpSmokeStep
from deepr.mcp.transport.http import HttpMessage


class _FakeHttpClient:
    instances: list["_FakeHttpClient"] = []

    def __init__(self, base_url: str, timeout: float = 30.0, auth_token: str | None = None):
        self.base_url = base_url
        self.timeout = timeout
        self.auth_token = auth_token
        self.sent: list[HttpMessage] = []
        self.connected = False
        self.disconnected = False
        _FakeHttpClient.instances.append(self)

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def send(self, message: HttpMessage) -> HttpMessage | None:
        self.sent.append(message)
        if message.method == "initialize":
            return HttpMessage(
                id=message.id,
                result={"serverInfo": {"name": "deepr-research", "version": "test"}},
            )
        if message.method == "tools/list":
            return HttpMessage(id=message.id, result={"tools": [{"name": "deepr_tool_search"}]})
        if message.method == "tools/call":
            payload = {"count": 1, "tools": [{"name": "deepr_status"}]}
            return HttpMessage(
                id=message.id,
                result={
                    "content": [{"type": "text", "text": json.dumps(payload)}],
                    "isError": False,
                },
            )
        raise AssertionError(f"Unexpected method: {message.method}")


async def _healthy_probe(_base_url: str, _auth_token: str | None, _timeout_seconds: float) -> MCPHttpSmokeStep:
    return MCPHttpSmokeStep("health", True, "healthy", status_code=200)


@pytest.mark.asyncio
async def test_run_http_smoke_passes_core_checks(monkeypatch):
    _FakeHttpClient.instances = []
    monkeypatch.setattr(smoke, "HttpClient", _FakeHttpClient)
    monkeypatch.setattr(smoke, "_probe_health", _healthy_probe)

    report = await smoke.run_http_smoke(
        "http://127.0.0.1:8765/mcp/",
        auth_token="secret",
        timeout_seconds=2.0,
    )

    assert report.ok is True
    assert report.url == "http://127.0.0.1:8765/mcp"
    assert [step.name for step in report.steps] == ["health", "initialize", "tools/list", "tools/call"]
    assert _FakeHttpClient.instances[0].base_url == "http://127.0.0.1:8765/mcp"
    assert _FakeHttpClient.instances[0].auth_token == "secret"
    assert _FakeHttpClient.instances[0].disconnected is True
    assert [message.method for message in _FakeHttpClient.instances[0].sent] == [
        "initialize",
        "tools/list",
        "tools/call",
    ]


@pytest.mark.asyncio
async def test_run_http_smoke_reports_rpc_error(monkeypatch):
    class DenyingHttpClient(_FakeHttpClient):
        async def send(self, message: HttpMessage) -> HttpMessage | None:
            if message.method == "tools/call":
                return HttpMessage(
                    id=message.id,
                    error={
                        "code": -32003,
                        "message": "Denied",
                        "data": {"error_code": "KEY_SCOPE_DENIED"},
                    },
                )
            return await super().send(message)

    monkeypatch.setattr(smoke, "HttpClient", DenyingHttpClient)
    monkeypatch.setattr(smoke, "_probe_health", _healthy_probe)

    report = await smoke.run_http_smoke("http://127.0.0.1:8765/mcp")

    assert report.ok is False
    assert report.steps[-1].name == "tools/call"
    assert report.steps[-1].ok is False
    assert "KEY_SCOPE_DENIED" in report.steps[-1].detail


def test_smoke_report_serializes_status_code():
    step = MCPHttpSmokeStep("health", True, "healthy", status_code=200)

    assert step.to_dict() == {
        "name": "health",
        "ok": True,
        "detail": "healthy",
        "status_code": 200,
    }
