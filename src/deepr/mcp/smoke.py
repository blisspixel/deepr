"""HTTP MCP endpoint smoke checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from deepr.mcp.http_client_policy import validated_mcp_http_timeout, validated_remote_mcp_url

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
            "contract": {
                "network_opened": False,
                "remote_tool_call_attempted": False,
                "remote_tool_cost_status": "not_submitted",
                "remote_tool_calls_metered_api": None,
            },
            "steps": [step.to_dict() for step in self.steps],
        }


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

    endpoint = validated_remote_mcp_url(url)
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
            "offline_validation_command": "deepr mcp validate-consult --json",
            "remote_smoke_status": "blocked_pending_cost_authority",
            "smoke_command": None,
            "free_smoke_tool": None,
        },
        "operational_contract": {
            "scoped_keys_required": True,
            "remote_audit_schema": "deepr-mcp-remote-audit-v1",
            "paid_tools_require_provider_keys": True,
            "provider_keys_included": False,
            "remote_tool_calls_blocked_without_cost_authority": True,
        },
    }
    if agent_name:
        payload["agent_name"] = agent_name
    if smoke_report is not None:
        payload["smoke"] = smoke_report.to_dict()
    return payload


async def run_http_smoke(
    url: str,
    *,
    auth_token: str | None = None,
    timeout_seconds: float = 10.0,
) -> MCPHttpSmokeReport:
    """Fail closed before remote smoke work until cost authority is attestable."""
    try:
        base_url = validated_remote_mcp_url(url)
        validated_mcp_http_timeout(timeout_seconds)
    except ValueError as exc:
        return MCPHttpSmokeReport(
            url="",
            steps=(MCPHttpSmokeStep("http_preflight", False, str(exc)),),
        )

    del auth_token
    detail = (
        "Remote MCP smoke is blocked until Deepr can verify an independently enforced cost "
        "authority before any endpoint request. Tool names and returned zero-cost metadata are "
        "self-reported and cannot prove that remote work avoided metered side effects."
    )
    return MCPHttpSmokeReport(
        url=base_url,
        steps=(MCPHttpSmokeStep("remote_cost_authority", False, detail),),
    )
