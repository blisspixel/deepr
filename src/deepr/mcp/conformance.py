"""Offline, machine-checkable MCP host-interop conformance report.

Aggregates form and side-effect checks that prove Deepr's dual-era MCP posture
without opening remote connections, calling models, spending money, or starting
the full MCP server (no expert-store session, no durable job state). Semantic
answer quality is intentionally out of scope (AGENTIC_BALANCE).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from deepr.mcp.consult_validation import run_offline_consult_validation
from deepr.mcp.protocol_compat import LEGACY_METHOD_MAP
from deepr.mcp.protocol_modern import (
    LEGACY_PROTOCOL_VERSIONS,
    MODERN_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
)
from deepr.mcp.smoke import build_http_registration_manifest, run_http_smoke

CONFORMANCE_SCHEMA_VERSION = "deepr-mcp-conformance-v1"
CONFORMANCE_KIND = "deepr.mcp.conformance"

CheckStatus = Literal["passed", "failed"]

_PROBE_URL = "http://127.0.0.1:9/mcp"


@dataclass(frozen=True)
class ConformanceCheck:
    """One deterministic form or side-effect assertion."""

    name: str
    status: CheckStatus
    detail: str
    expected: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "expected": self.expected,
        }


@dataclass(frozen=True)
class MCPConformanceReport:
    """Secret-free offline conformance rollup."""

    checks: tuple[ConformanceCheck, ...]
    generated_at: datetime
    server_version: str

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.status == "passed" for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        failed = [check.name for check in self.checks if check.status != "passed"]
        return {
            "schema_version": CONFORMANCE_SCHEMA_VERSION,
            "kind": CONFORMANCE_KIND,
            "generated_at": self.generated_at.isoformat(),
            "server_version": self.server_version,
            "mode": "offline",
            "ok": self.ok,
            "cost_usd": 0.0,
            "contract": {
                "cost_usd": 0.0,
                "network_opened": False,
                "calls_metered_api": False,
                "writes_state": False,
                "semantic_verdict": False,
                "checks_form_and_side_effects_only": True,
                "live_model_required": False,
            },
            "protocol": {
                "modern": MODERN_PROTOCOL_VERSION,
                "legacy": list(LEGACY_PROTOCOL_VERSIONS),
                "supported": list(SUPPORTED_PROTOCOL_VERSIONS),
            },
            "summary": {
                "ok": self.ok,
                "check_count": len(self.checks),
                "failed_checks": failed,
            },
            "checks": [check.to_dict() for check in self.checks],
        }


def _passed(name: str, detail: str, *, expected: str) -> ConformanceCheck:
    return ConformanceCheck(name=name, status="passed", detail=detail, expected=expected)


def _failed(name: str, detail: str, *, expected: str) -> ConformanceCheck:
    return ConformanceCheck(name=name, status="failed", detail=detail, expected=expected)


def _check_dual_era_protocol() -> ConformanceCheck:
    expected = f"modern={MODERN_PROTOCOL_VERSION}; legacy includes {', '.join(LEGACY_PROTOCOL_VERSIONS)}"
    if MODERN_PROTOCOL_VERSION != "2026-07-28":
        return _failed(
            "dual_era_protocol",
            f"modern version is {MODERN_PROTOCOL_VERSION!r}",
            expected=expected,
        )
    if MODERN_PROTOCOL_VERSION not in SUPPORTED_PROTOCOL_VERSIONS:
        return _failed(
            "dual_era_protocol",
            "modern version missing from SUPPORTED_PROTOCOL_VERSIONS",
            expected=expected,
        )
    missing_legacy = [v for v in LEGACY_PROTOCOL_VERSIONS if v not in SUPPORTED_PROTOCOL_VERSIONS]
    if missing_legacy:
        return _failed(
            "dual_era_protocol",
            f"legacy versions missing from supported list: {missing_legacy}",
            expected=expected,
        )
    if not LEGACY_METHOD_MAP:
        return _failed(
            "dual_era_protocol",
            "legacy method alias map is empty",
            expected=expected,
        )
    bad_aliases = {
        legacy: canonical for legacy, canonical in LEGACY_METHOD_MAP.items() if not str(canonical).startswith("deepr_")
    }
    if bad_aliases:
        return _failed(
            "dual_era_protocol",
            f"legacy aliases must map to deepr_ tools: {bad_aliases}",
            expected=expected,
        )
    return _passed(
        "dual_era_protocol",
        (f"supported {list(SUPPORTED_PROTOCOL_VERSIONS)}; {len(LEGACY_METHOD_MAP)} legacy tool aliases"),
        expected=expected,
    )


def _check_offline_consult() -> ConformanceCheck:
    expected = "offline consult validation summary.ok=true with cost_usd=0"
    try:
        report = run_offline_consult_validation()
        payload = report.to_dict()
    except Exception as exc:
        return _failed("offline_consult_validation", f"{type(exc).__name__}: {exc}", expected=expected)
    summary = payload.get("summary") if isinstance(payload, dict) else None
    ok = isinstance(summary, dict) and summary.get("ok") is True
    contract = payload.get("contract") if isinstance(payload, dict) else {}
    cost = contract.get("cost_usd") if isinstance(contract, dict) else None
    if not ok:
        failed = summary.get("failed_checks") if isinstance(summary, dict) else []
        return _failed(
            "offline_consult_validation",
            f"summary.ok is not true; failed_checks={failed!r}",
            expected=expected,
        )
    if cost != 0.0:
        return _failed(
            "offline_consult_validation",
            f"contract.cost_usd={cost!r}",
            expected=expected,
        )
    check_count = summary.get("check_count") if isinstance(summary, dict) else 0
    return _passed(
        "offline_consult_validation",
        f"{check_count} form checks passed; cost_usd=0.0",
        expected=expected,
    )


def _check_remote_smoke_fail_closed() -> ConformanceCheck:
    expected = "smoke blocked before network; remote_tool_call_attempted=false"
    try:
        report = asyncio.run(run_http_smoke(_PROBE_URL))
        payload = report.to_dict()
    except Exception as exc:
        return _failed("remote_smoke_fail_closed", f"{type(exc).__name__}: {exc}", expected=expected)
    contract = payload.get("contract") if isinstance(payload, dict) else {}
    network_opened = contract.get("network_opened") if isinstance(contract, dict) else None
    remote_attempted = contract.get("remote_tool_call_attempted") if isinstance(contract, dict) else None
    # Pass means the gate blocked: report.ok is False and no network/tool attempt.
    if payload.get("ok") is True:
        return _failed(
            "remote_smoke_fail_closed",
            "smoke reported ok=true without cost authority proof",
            expected=expected,
        )
    if network_opened is not False or remote_attempted is not False:
        return _failed(
            "remote_smoke_fail_closed",
            f"network_opened={network_opened!r} remote_tool_call_attempted={remote_attempted!r}",
            expected=expected,
        )
    return _passed(
        "remote_smoke_fail_closed",
        "remote smoke blocked with no network open",
        expected=expected,
    )


def _check_managed_conversation_fail_closed() -> ConformanceCheck:
    expected = "managed loopback conversation validation blocked without cost authority"
    try:
        from deepr.mcp.conversation_validation_managed import (
            run_managed_loopback_conversation_validation,
        )

        report = asyncio.run(run_managed_loopback_conversation_validation())
        payload = report.to_dict()
    except Exception as exc:
        return _failed(
            "managed_conversation_fail_closed",
            f"{type(exc).__name__}: {exc}",
            expected=expected,
        )
    if payload.get("ok") is True:
        return _failed(
            "managed_conversation_fail_closed",
            "managed conversation validation unexpectedly passed",
            expected=expected,
        )
    if payload.get("remote_tool_call_attempted") is not False:
        return _failed(
            "managed_conversation_fail_closed",
            f"remote_tool_call_attempted={payload.get('remote_tool_call_attempted')!r}",
            expected=expected,
        )
    error_raw = payload.get("error")
    error: dict[str, Any] = error_raw if isinstance(error_raw, dict) else {}
    code = str(error.get("error_code", "") or "")
    if "BLOCKED" not in code:
        return _failed(
            "managed_conversation_fail_closed",
            f"error_code={code!r} is not a blocked posture",
            expected=expected,
        )
    return _passed(
        "managed_conversation_fail_closed",
        f"blocked with error_code={code}",
        expected=expected,
    )


def _check_registration_manifest() -> ConformanceCheck:
    expected = "network-free registration manifest with remote smoke blocked"
    try:
        payload = build_http_registration_manifest(_PROBE_URL)
    except Exception as exc:
        return _failed("registration_manifest_offline", f"{type(exc).__name__}: {exc}", expected=expected)
    registration = payload.get("registration") if isinstance(payload, dict) else {}
    status = registration.get("remote_smoke_status") if isinstance(registration, dict) else None
    if status != "blocked_pending_cost_authority":
        return _failed(
            "registration_manifest_offline",
            f"remote_smoke_status={status!r}",
            expected=expected,
        )
    operational = payload.get("operational_contract") if isinstance(payload, dict) else {}
    if (
        not isinstance(operational, dict)
        or operational.get("remote_tool_calls_blocked_without_cost_authority") is not True
    ):
        return _failed(
            "registration_manifest_offline",
            "operational_contract.remote_tool_calls_blocked_without_cost_authority is not true",
            expected=expected,
        )
    return _passed(
        "registration_manifest_offline",
        "manifest built without network; remote smoke blocked pending cost authority",
        expected=expected,
    )


def _check_capabilities_map(*, version: str) -> ConformanceCheck:
    expected = "deepr-capabilities-v1 map builds with zero-cost synthesis paths"
    try:
        from deepr.mcp.capabilities import CAPABILITIES_SCHEMA_VERSION, build_capabilities
        from deepr.mcp.search.registry import create_default_registry
        from deepr.mcp.server import _register_new_tools

        class _EmptyExpertStore:
            """Read-only empty roster; no filesystem or network side effects."""

            def list_all(self) -> list[Any]:
                return []

        registry = create_default_registry()
        _register_new_tools(registry)
        payload = build_capabilities(_EmptyExpertStore(), registry, version=version)
    except Exception as exc:
        return _failed("capabilities_map", f"{type(exc).__name__}: {exc}", expected=expected)
    if payload.get("schema_version") != CAPABILITIES_SCHEMA_VERSION:
        return _failed(
            "capabilities_map",
            f"schema_version={payload.get('schema_version')!r}",
            expected=expected,
        )
    zero_cost = payload.get("zero_cost_synthesis") if isinstance(payload, dict) else None
    if not isinstance(zero_cost, dict) or zero_cost.get("owned") != "local":
        return _failed(
            "capabilities_map",
            f"zero_cost_synthesis={zero_cost!r}",
            expected=expected,
        )
    plans = zero_cost.get("prepaid_plans")
    if not isinstance(plans, list) or "claude" not in plans:
        return _failed(
            "capabilities_map",
            f"prepaid_plans={plans!r} must include claude",
            expected=expected,
        )
    tools = payload.get("tools") if isinstance(payload, dict) else []
    tool_count = len(tools) if isinstance(tools, list) else 0
    return _passed(
        "capabilities_map",
        f"{CAPABILITIES_SCHEMA_VERSION} with {tool_count} key tool(s); local+claude zero-cost paths",
        expected=expected,
    )


def run_offline_mcp_conformance(*, server_version: str | None = None) -> MCPConformanceReport:
    """Run the offline MCP conformance suite. No network, no model, $0."""
    version = server_version
    if not version:
        try:
            from deepr import __version__ as package_version

            version = str(package_version)
        except Exception:
            version = "unknown"

    checks = (
        _check_dual_era_protocol(),
        _check_offline_consult(),
        _check_remote_smoke_fail_closed(),
        _check_managed_conversation_fail_closed(),
        _check_registration_manifest(),
        _check_capabilities_map(version=version),
    )
    return MCPConformanceReport(
        checks=checks,
        generated_at=datetime.now(UTC),
        server_version=version,
    )


__all__ = [
    "CONFORMANCE_KIND",
    "CONFORMANCE_SCHEMA_VERSION",
    "ConformanceCheck",
    "MCPConformanceReport",
    "run_offline_mcp_conformance",
]
