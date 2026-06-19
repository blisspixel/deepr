"""HTTP MCP endpoint smoke checks."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import aiohttp

from deepr.mcp.transport.http import HttpClient, HttpMessage

REGISTRATION_MANIFEST_SCHEMA_VERSION = "deepr-mcp-registration-manifest-v1"
REGISTRATION_MANIFEST_KIND = "deepr.mcp.registration_manifest"


@dataclass(frozen=True)
class MCPHttpSmokeStep:
    """One smoke-test check result."""

    name: str
    ok: bool
    detail: str
    status_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
        }
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        return payload


@dataclass(frozen=True)
class MCPHttpSmokeReport:
    """Structured result for an HTTP MCP smoke run."""

    url: str
    steps: tuple[MCPHttpSmokeStep, ...]

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(step.ok for step in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "ok": self.ok,
            "steps": [step.to_dict() for step in self.steps],
        }


def _resolve_auth_token(auth_token: str | None) -> str | None:
    return auth_token or os.getenv("MCP_AUTH_TOKEN") or os.getenv("DEEPR_MCP_AUTH_TOKEN") or None


def _auth_headers(auth_token: str | None) -> dict[str, str]:
    token = _resolve_auth_token(auth_token)
    return {"Authorization": f"Bearer {token}"} if token else {}


def _health_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/health"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_http_registration_manifest(
    url: str,
    *,
    smoke_report: MCPHttpSmokeReport | None = None,
    agent_name: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a token-redacted registration manifest for a hosted HTTP MCP endpoint."""

    endpoint = url.rstrip("/")
    payload: dict[str, Any] = {
        "schema_version": REGISTRATION_MANIFEST_SCHEMA_VERSION,
        "kind": REGISTRATION_MANIFEST_KIND,
        "created_at": _format_timestamp(created_at or _utc_now()),
        "transport": {
            "type": "streamable_http",
            "url": endpoint,
            "health_url": _health_url(endpoint),
        },
        "auth": {
            "type": "bearer",
            "header": "Authorization",
            "alternate_header": "X-Api-Key",
            "token_env_var": "DEEPR_MCP_KEY",
            "secret_included": False,
        },
        "registration": {
            "smoke_command": f'deepr mcp smoke-http "{endpoint}" --auth-token "$DEEPR_MCP_KEY"',
            "free_smoke_tool": "deepr_tool_search",
        },
        "operational_contract": {
            "scoped_keys_required": True,
            "remote_audit_schema": "deepr-mcp-remote-audit-v1",
            "paid_tools_require_provider_keys": True,
            "provider_keys_included": False,
        },
    }
    if agent_name:
        payload["agent_name"] = agent_name
    if smoke_report is not None:
        payload["smoke"] = smoke_report.to_dict()
    return payload


async def _probe_health(base_url: str, auth_token: str | None, timeout_seconds: float) -> MCPHttpSmokeStep:
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_health_url(base_url), headers=_auth_headers(auth_token)) as response:
                status = response.status
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, json.JSONDecodeError):
                    payload = {}
                if status != 200:
                    return MCPHttpSmokeStep("health", False, f"HTTP {status}", status_code=status)
                if not isinstance(payload, dict) or payload.get("status") != "healthy":
                    return MCPHttpSmokeStep("health", False, "Health response was not healthy", status_code=status)
                active = payload.get("active_streams", 0)
                return MCPHttpSmokeStep("health", True, f"healthy, active_streams={active}", status_code=status)
    except (aiohttp.ClientError, TimeoutError, OSError) as exc:
        return MCPHttpSmokeStep("health", False, f"Health request failed: {exc}")


def _rpc_error_detail(response: HttpMessage) -> str:
    if not response.error:
        return "No JSON-RPC error"
    message = str(response.error.get("message") or "JSON-RPC error")
    data = response.error.get("data")
    if isinstance(data, dict) and data.get("error_code"):
        return f"{message} ({data['error_code']})"
    return message


async def _send_rpc(
    client: HttpClient,
    *,
    step_name: str,
    request_id: str,
    method: str,
    params: dict[str, Any],
) -> tuple[MCPHttpSmokeStep | None, Any | None]:
    try:
        response = await client.send(HttpMessage(id=request_id, method=method, params=params))
    except (aiohttp.ClientError, TimeoutError, OSError, RuntimeError) as exc:
        return MCPHttpSmokeStep(step_name, False, f"{method} failed: {exc}"), None
    if response is None:
        return MCPHttpSmokeStep(step_name, False, f"{method} returned no response"), None
    if response.error:
        return MCPHttpSmokeStep(step_name, False, _rpc_error_detail(response)), None
    return None, response.result


def _validate_initialize(result: Any) -> MCPHttpSmokeStep:
    if not isinstance(result, dict):
        return MCPHttpSmokeStep("initialize", False, "initialize result was not an object")
    server_info = result.get("serverInfo")
    if not isinstance(server_info, dict):
        return MCPHttpSmokeStep("initialize", False, "initialize result missed serverInfo")
    name = str(server_info.get("name") or "")
    version = str(server_info.get("version") or "unknown")
    if name != "deepr-research":
        return MCPHttpSmokeStep("initialize", False, f"unexpected server name {name!r}")
    return MCPHttpSmokeStep("initialize", True, f"{name} version {version}")


def _tool_names(tools: Any) -> list[str]:
    if not isinstance(tools, list):
        return []
    return [str(tool.get("name")) for tool in tools if isinstance(tool, dict) and tool.get("name")]


def _validate_tools_list(result: Any) -> MCPHttpSmokeStep:
    if not isinstance(result, dict):
        return MCPHttpSmokeStep("tools/list", False, "tools/list result was not an object")
    names = _tool_names(result.get("tools"))
    if "deepr_tool_search" not in names:
        return MCPHttpSmokeStep("tools/list", False, "deepr_tool_search was not advertised")
    return MCPHttpSmokeStep("tools/list", True, f"{len(names)} advertised tool(s)")


def _validate_tool_search(result: Any) -> MCPHttpSmokeStep:
    if not isinstance(result, dict):
        return MCPHttpSmokeStep("tools/call", False, "tools/call result was not an object")
    if result.get("isError") is True:
        return MCPHttpSmokeStep("tools/call", False, "deepr_tool_search returned an MCP tool error")
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return MCPHttpSmokeStep("tools/call", False, "deepr_tool_search returned no content")
    first = content[0]
    if not isinstance(first, dict) or not isinstance(first.get("text"), str):
        return MCPHttpSmokeStep("tools/call", False, "deepr_tool_search content was not text")
    try:
        payload = json.loads(first["text"])
    except json.JSONDecodeError:
        return MCPHttpSmokeStep("tools/call", False, "deepr_tool_search text was not JSON")
    if not isinstance(payload, dict):
        return MCPHttpSmokeStep("tools/call", False, "deepr_tool_search payload was not an object")
    count = payload.get("count", 0)
    return MCPHttpSmokeStep("tools/call", True, f"deepr_tool_search returned {count} match(es)")


async def run_http_smoke(
    url: str,
    *,
    auth_token: str | None = None,
    timeout_seconds: float = 10.0,
) -> MCPHttpSmokeReport:
    """Run free structural checks against a Deepr HTTP MCP endpoint."""

    base_url = url.rstrip("/")
    steps: list[MCPHttpSmokeStep] = []
    resolved_auth_token = _resolve_auth_token(auth_token)

    steps.append(await _probe_health(base_url, resolved_auth_token, timeout_seconds))

    client = HttpClient(base_url, timeout=timeout_seconds, auth_token=resolved_auth_token)
    try:
        await client.connect()

        init_step, init_result = await _send_rpc(
            client,
            step_name="initialize",
            request_id="smoke-initialize",
            method="initialize",
            params={},
        )
        steps.append(init_step if init_step is not None else _validate_initialize(init_result))

        tools_step, tools_result = await _send_rpc(
            client,
            step_name="tools/list",
            request_id="smoke-tools-list",
            method="tools/list",
            params={},
        )
        steps.append(tools_step if tools_step is not None else _validate_tools_list(tools_result))

        search_step, search_result = await _send_rpc(
            client,
            step_name="tools/call",
            request_id="smoke-tool-search",
            method="tools/call",
            params={
                "name": "deepr_tool_search",
                "arguments": {"query": "status health tools", "limit": 1},
            },
        )
        steps.append(search_step if search_step is not None else _validate_tool_search(search_result))
    except (aiohttp.ClientError, TimeoutError, OSError, RuntimeError) as exc:
        steps.append(MCPHttpSmokeStep("connect", False, f"Client setup failed: {exc}"))
    finally:
        await client.disconnect()

    return MCPHttpSmokeReport(url=base_url, steps=tuple(steps))
