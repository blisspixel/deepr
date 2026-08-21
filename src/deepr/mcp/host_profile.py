"""Deterministic, offline configuration profiles for external MCP hosts."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from deepr import __version__ as DEEPR_VERSION
from deepr.mcp.contained_env import build_contained_read_only_env
from deepr.mcp.runtime_registry import create_runtime_registry
from deepr.mcp.security.tool_allowlist import ResearchMode, ToolAllowlist
from deepr.mcp.tool_surface import effective_tool_names

HOST_PROFILE_SCHEMA_VERSION = "deepr-mcp-host-profile-v1"
HOST_PROFILE_KIND = "deepr.mcp.host_profile"
HOST_DATA_PLACEHOLDER = "${DEEPR_HOST_DATA}"
V1_READ_ONLY_TOOLS = (
    "deepr_capabilities",
    "deepr_check_status",
    "deepr_get_expert_info",
    "deepr_get_result",
    "deepr_get_task_progress",
    "deepr_list_experts",
    "deepr_list_recoverable_tasks",
    "deepr_list_skills",
    "deepr_status",
    "deepr_tool_search",
)
_MAX_EXTENSION_DEPTH = 16
_MAX_EXTENSION_NODES = 1024
_MAX_EXTENSION_STRING_LENGTH = 16 * 1024
_MAX_EXTENSION_INTEGER_BITS = 4096


@dataclass(frozen=True)
class HostEvidence:
    host: str
    version: str
    release_channel: str
    revision: str
    tag_object: str
    package_version: str
    release_url: str
    config_documentation_url: str
    config_document_revision: str
    config_document_sha256: str
    mcp_types_url: str
    mcp_types_revision: str
    mcp_types_sha256: str
    runtime_schema_url: str
    runtime_schema_revision: str
    runtime_schema_sha256: str
    checked_on: str


_OPENCLAW_STABLE = HostEvidence(
    host="openclaw",
    version="v2026.7.1-2",
    release_channel="stable",
    revision="0790d9f593ad30c940ed93b5872a8cf6d6f3cf8c",
    tag_object="be8b8a9e8838f832e4fa47cde8bea0a33aec71ba",
    package_version="2026.7.1",
    release_url="https://github.com/openclaw/openclaw/releases/tag/v2026.7.1-2",
    config_documentation_url=(
        "https://github.com/openclaw/openclaw/blob/0790d9f593ad30c940ed93b5872a8cf6d6f3cf8c/"
        "docs/gateway/configuration-reference.md"
    ),
    config_document_revision="2b41702024a76a89b1a6d0c15caff967fde8d93d",
    config_document_sha256="d33e9fcf8d48ca4084d32b40d243cb30a244e3c8c1bc98c733d39e81ea5f440e",
    mcp_types_url=(
        "https://github.com/openclaw/openclaw/blob/0790d9f593ad30c940ed93b5872a8cf6d6f3cf8c/src/config/types.mcp.ts"
    ),
    mcp_types_revision="89b0f5b68df0292ee80132c1aa0173cc58c15b74",
    mcp_types_sha256="bc3b1d818d50d67ee9121ea05fd4508008095f87b2a076eea3a45539e741e7e4",
    runtime_schema_url=(
        "https://github.com/openclaw/openclaw/blob/0790d9f593ad30c940ed93b5872a8cf6d6f3cf8c/src/config/zod-schema.ts"
    ),
    runtime_schema_revision="59d56fe50dc5782936b60a7dbe3f9d7d17b7e535",
    runtime_schema_sha256="e9fc8b4bd58d7e78a9409fe0fd032a9d3f0eb7325d517b03b576acce1f20bec1",
    checked_on="2026-08-21",
)
_SUPPORTED_HOSTS = {(_OPENCLAW_STABLE.host, _OPENCLAW_STABLE.version): _OPENCLAW_STABLE}
_DEFAULT_VERSIONS = {_OPENCLAW_STABLE.host: _OPENCLAW_STABLE.version}


@dataclass(frozen=True)
class HostProfileViolation:
    """One deterministic host-profile contract violation."""

    code: str
    detail: str


def read_only_tool_names() -> tuple[str, ...]:
    """Return the pinned v1 tools after asserting current runtime equality."""
    registry = create_runtime_registry()
    allowlist = ToolAllowlist(mode=ResearchMode.READ_ONLY)
    runtime_tools = tuple(sorted(effective_tool_names(registry, allowlist)))
    if runtime_tools != V1_READ_ONLY_TOOLS:
        raise RuntimeError("runtime read-only tool authority drift requires a new host-profile schema version")
    return V1_READ_ONLY_TOOLS


def supported_host_versions() -> dict[str, str]:
    """Return supported host ids and their default pinned reference versions."""
    return dict(_DEFAULT_VERSIONS)


def _openclaw_fragment(tools: tuple[str, ...]) -> dict[str, Any]:
    return {
        "mcp": {
            "servers": {
                "deepr": {
                    "enabled": True,
                    "transport": "stdio",
                    "command": "deepr-mcp",
                    "args": [],
                    "env": build_contained_read_only_env(
                        HOST_DATA_PLACEHOLDER,
                        advertise_full_tool_list=True,
                    ),
                    "connectionTimeoutMs": 10000,
                    "requestTimeoutMs": 30000,
                    "supportsParallelToolCalls": False,
                    "toolFilter": {"include": list(tools)},
                }
            }
        }
    }


def build_host_profile(host: str, version: str | None = None) -> dict[str, Any]:
    """Build one pinned, side-effect-free host configuration reference."""
    host_id = host.strip().lower()
    resolved_version = version or _DEFAULT_VERSIONS.get(host_id)
    evidence = _SUPPORTED_HOSTS.get((host_id, resolved_version or ""))
    if evidence is None:
        supported = ", ".join(f"{name} {value}" for name, value in sorted(_DEFAULT_VERSIONS.items()))
        raise ValueError(f"unsupported host or version; supported fixtures: {supported}")

    tools = read_only_tool_names()
    profile = {
        "schema_version": HOST_PROFILE_SCHEMA_VERSION,
        "kind": HOST_PROFILE_KIND,
        "deepr": {
            "version": DEEPR_VERSION,
            "source_revision": None,
            "source_revision_status": "not_collected",
            "server_command": "deepr-mcp",
            "installed_executable_required": True,
        },
        "host": {
            "id": evidence.host,
            "version": evidence.version,
            "release_channel": evidence.release_channel,
            "revision": evidence.revision,
            "tag_object": evidence.tag_object,
            "tag_signature_verified": True,
            "package_version": evidence.package_version,
            "native_agent_plugins_supported": False,
        },
        "transport": {
            "type": "stdio",
            "server_name": "deepr",
            "required_host_environment": ["DEEPR_HOST_DATA"],
        },
        "capabilities": {
            "research_mode": "read_only",
            "initial_advertised_tools": list(tools),
            "effective_read_only_tools": list(tools),
            "tool_count": len(tools),
            "tool_listing_mode": "full_read_only_catalog",
            "auto_approve": False,
            "caller_approval_can_widen": False,
            "parallel_tool_calls_hint": False,
        },
        "authority": {
            "generation_mode": "offline_config_only",
            "generation_cost_usd": 0,
            "network_opened": False,
            "host_config_mutated": False,
            "host_installed": False,
            "credentials_inspected": False,
            "host_version_inferred": False,
            "runtime_paid_dispatch_authorized": False,
            "runtime_state_writes_expected": True,
            "runtime_state_root": HOST_DATA_PLACEHOLDER,
            "external_side_effects_allowed": False,
        },
        "policy_posture": {
            "allowed_tool_classes": ["read", "compute"],
            "denied_tool_classes": ["write", "execute", "sensitive"],
            "scoped_key_mode": "not_applicable_local_stdio",
            "expert_scope": "all_experts_under_contained_root",
            "rate_limit": "not_configured",
            "budget_ceiling_usd": 0,
            "budget_basis": "primary_and_legacy_environment_ceilings",
        },
        "runtime_controls": {
            "connection_timeout_ms": 10000,
            "request_timeout_ms": 30000,
            "retry_policy": "host_default_not_validated",
            "parallel_tool_calls_hint": False,
            "server_serialization_guaranteed": False,
        },
        "host_posture": {
            "sandbox": "not_configured_by_profile",
            "filesystem": "runtime_state_under_operator_selected_host_data",
            "network": "not_configured_by_profile",
            "approval": "deepr_auto_approve_disabled",
        },
        "conformance": {
            "deepr_contract_validated": True,
            "openclaw_parser_validated": False,
            "mcp_handshake_validated": False,
            "tool_discovery_validated": False,
            "live_tool_call_validated": False,
        },
        "validation": {
            "status": "reference",
            "checked_on": evidence.checked_on,
            "host_config_fields_checked": True,
            "live_runtime_checked": False,
            "independent_validation_evidence": None,
        },
        "evidence": {
            "release_url": evidence.release_url,
            "config_documentation_url": evidence.config_documentation_url,
            "host_revision": evidence.revision,
            "tag_object": evidence.tag_object,
            "config_document_revision": evidence.config_document_revision,
            "config_document_sha256": evidence.config_document_sha256,
            "mcp_types_url": evidence.mcp_types_url,
            "mcp_types_revision": evidence.mcp_types_revision,
            "mcp_types_sha256": evidence.mcp_types_sha256,
            "runtime_schema_url": evidence.runtime_schema_url,
            "runtime_schema_revision": evidence.runtime_schema_revision,
            "runtime_schema_sha256": evidence.runtime_schema_sha256,
        },
        "config_fragment": _openclaw_fragment(tools),
        "extensions": {},
    }
    violations = validate_host_profile(profile)
    if violations:  # pragma: no cover - protects static producer drift
        detail = "; ".join(item.detail for item in violations)
        raise RuntimeError(f"generated host profile violated its contract: {detail}")
    return profile


@dataclass
class _ExtensionWalkState:
    active_containers: set[int]
    node_count: int = 0


def _extension_scalar_error(value: Any) -> tuple[bool, str | None]:
    if value is None or isinstance(value, bool):
        return True, None
    if isinstance(value, int):
        error = "extensions contain an oversized integer" if value.bit_length() > _MAX_EXTENSION_INTEGER_BITS else None
        return True, error
    if isinstance(value, float):
        error = None if math.isfinite(value) else "extensions contain a non-finite number"
        return True, error
    if isinstance(value, str):
        if len(value) > _MAX_EXTENSION_STRING_LENGTH:
            return True, "extensions contain an oversized string"
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return True, "extensions contain a string that is not valid UTF-8"
        return True, None
    return False, None


def _walk_extension_mapping(value: dict[Any, Any], depth: int, state: _ExtensionWalkState) -> str | None:
    for key, child in value.items():
        if not isinstance(key, str):
            return "extension object keys must be strings"
        error = _walk_extension_json(key, depth + 1, state) or _walk_extension_json(child, depth + 1, state)
        if error is not None:
            return error
    return None


def _walk_extension_sequence(value: list[Any], depth: int, state: _ExtensionWalkState) -> str | None:
    for child in value:
        error = _walk_extension_json(child, depth + 1, state)
        if error is not None:
            return error
    return None


def _walk_extension_json(value: Any, depth: int, state: _ExtensionWalkState) -> str | None:
    state.node_count += 1
    if state.node_count > _MAX_EXTENSION_NODES:
        return "extensions exceed the maximum JSON node count"
    if depth > _MAX_EXTENSION_DEPTH:
        return "extensions exceed the maximum JSON nesting depth"
    is_scalar, error = _extension_scalar_error(value)
    if is_scalar:
        return error
    if type(value) not in (dict, list):
        return "extensions contain a non-JSON value"

    identity = id(value)
    if identity in state.active_containers:
        return "extensions contain a cycle"
    state.active_containers.add(identity)
    try:
        if isinstance(value, dict):
            return _walk_extension_mapping(value, depth, state)
        return _walk_extension_sequence(value, depth, state)
    finally:
        state.active_containers.remove(identity)


def _extension_json_error(value: Any) -> str | None:
    return _walk_extension_json(value, 0, _ExtensionWalkState(active_containers=set()))


def validate_host_profile(profile: Any) -> tuple[HostProfileViolation, ...]:
    """Validate the authority-bearing v1 profile fields against runtime truth."""
    violations: list[HostProfileViolation] = []

    if type(profile) is not dict:
        return (HostProfileViolation("root_type", "host profile must be a JSON object"),)

    def require(condition: bool, code: str, detail: str) -> None:
        if not condition:
            violations.append(HostProfileViolation(code, detail))

    expected_root = {
        "schema_version",
        "kind",
        "deepr",
        "host",
        "transport",
        "capabilities",
        "authority",
        "policy_posture",
        "runtime_controls",
        "host_posture",
        "conformance",
        "validation",
        "evidence",
        "config_fragment",
        "extensions",
    }
    require(set(profile) == expected_root, "root_fields", "root fields must match the v1 contract")
    require(
        profile.get("schema_version") == HOST_PROFILE_SCHEMA_VERSION,
        "schema_version",
        "schema_version must identify the v1 host-profile contract",
    )
    require(profile.get("kind") == HOST_PROFILE_KIND, "kind", "kind must identify a Deepr MCP host profile")

    host = profile.get("host")
    evidence_record: HostEvidence | None = None
    if isinstance(host, dict):
        host_id = host.get("id")
        host_version = host.get("version")
        if isinstance(host_id, str) and isinstance(host_version, str):
            evidence_record = _SUPPORTED_HOSTS.get((host_id, host_version))
    require(evidence_record is not None, "host_pin", "host and version must match a supported immutable pin")

    try:
        tools = read_only_tool_names()
    except RuntimeError as exc:
        violations.append(HostProfileViolation("tool_authority_drift", str(exc)))
        tools = V1_READ_ONLY_TOOLS
    expected_capabilities = {
        "research_mode": "read_only",
        "initial_advertised_tools": list(tools),
        "effective_read_only_tools": list(tools),
        "tool_count": len(tools),
        "tool_listing_mode": "full_read_only_catalog",
        "auto_approve": False,
        "caller_approval_can_widen": False,
        "parallel_tool_calls_hint": False,
    }
    require(
        profile.get("capabilities") == expected_capabilities,
        "capabilities",
        "capabilities must equal the effective registered read-only tool surface",
    )
    expected_transport = {
        "type": "stdio",
        "server_name": "deepr",
        "required_host_environment": ["DEEPR_HOST_DATA"],
    }
    require(profile.get("transport") == expected_transport, "transport", "transport must be local stdio")
    expected_authority = {
        "generation_mode": "offline_config_only",
        "generation_cost_usd": 0,
        "network_opened": False,
        "host_config_mutated": False,
        "host_installed": False,
        "credentials_inspected": False,
        "host_version_inferred": False,
        "runtime_paid_dispatch_authorized": False,
        "runtime_state_writes_expected": True,
        "runtime_state_root": HOST_DATA_PLACEHOLDER,
        "external_side_effects_allowed": False,
    }
    require(profile.get("authority") == expected_authority, "authority", "authority fields must remain fail closed")
    expected_policy_posture = {
        "allowed_tool_classes": ["read", "compute"],
        "denied_tool_classes": ["write", "execute", "sensitive"],
        "scoped_key_mode": "not_applicable_local_stdio",
        "expert_scope": "all_experts_under_contained_root",
        "rate_limit": "not_configured",
        "budget_ceiling_usd": 0,
        "budget_basis": "primary_and_legacy_environment_ceilings",
    }
    require(
        profile.get("policy_posture") == expected_policy_posture,
        "policy_posture",
        "tool, key, expert, rate, and budget posture must remain exact",
    )
    expected_runtime_controls = {
        "connection_timeout_ms": 10000,
        "request_timeout_ms": 30000,
        "retry_policy": "host_default_not_validated",
        "parallel_tool_calls_hint": False,
        "server_serialization_guaranteed": False,
    }
    require(
        profile.get("runtime_controls") == expected_runtime_controls,
        "runtime_controls",
        "timeout, retry, and concurrency posture must remain exact",
    )
    expected_host_posture = {
        "sandbox": "not_configured_by_profile",
        "filesystem": "runtime_state_under_operator_selected_host_data",
        "network": "not_configured_by_profile",
        "approval": "deepr_auto_approve_disabled",
    }
    require(
        profile.get("host_posture") == expected_host_posture,
        "host_posture",
        "sandbox, filesystem, network, and approval posture must remain exact",
    )
    expected_conformance = {
        "deepr_contract_validated": True,
        "openclaw_parser_validated": False,
        "mcp_handshake_validated": False,
        "tool_discovery_validated": False,
        "live_tool_call_validated": False,
    }
    require(
        profile.get("conformance") == expected_conformance,
        "conformance",
        "reference profiles cannot claim host parser, handshake, discovery, or live-call validation",
    )

    validation = profile.get("validation")
    expected_validation = {
        "status": "reference",
        "checked_on": evidence_record.checked_on if evidence_record is not None else None,
        "host_config_fields_checked": True,
        "live_runtime_checked": False,
        "independent_validation_evidence": None,
    }
    require(
        validation == expected_validation,
        "validation_status",
        "ordinary profiles cannot claim fixture or live validation",
    )
    extensions = profile.get("extensions")
    require(isinstance(extensions, dict), "extensions", "extensions must be an ignored object")
    if isinstance(extensions, dict):
        extension_error = _extension_json_error(extensions)
        require(extension_error is None, "extensions_json", extension_error or "extensions must be finite JSON")

    if evidence_record is not None:
        expected_host = {
            "id": evidence_record.host,
            "version": evidence_record.version,
            "release_channel": evidence_record.release_channel,
            "revision": evidence_record.revision,
            "tag_object": evidence_record.tag_object,
            "tag_signature_verified": True,
            "package_version": evidence_record.package_version,
            "native_agent_plugins_supported": False,
        }
        expected_evidence = {
            "release_url": evidence_record.release_url,
            "config_documentation_url": evidence_record.config_documentation_url,
            "host_revision": evidence_record.revision,
            "tag_object": evidence_record.tag_object,
            "config_document_revision": evidence_record.config_document_revision,
            "config_document_sha256": evidence_record.config_document_sha256,
            "mcp_types_url": evidence_record.mcp_types_url,
            "mcp_types_revision": evidence_record.mcp_types_revision,
            "mcp_types_sha256": evidence_record.mcp_types_sha256,
            "runtime_schema_url": evidence_record.runtime_schema_url,
            "runtime_schema_revision": evidence_record.runtime_schema_revision,
            "runtime_schema_sha256": evidence_record.runtime_schema_sha256,
        }
        require(host == expected_host, "host_evidence", "host fields must match the immutable evidence record")
        require(
            profile.get("evidence") == expected_evidence,
            "source_evidence",
            "source evidence must match the immutable host pin",
        )
        require(
            profile.get("config_fragment") == _openclaw_fragment(tools),
            "config_fragment",
            "configuration must match the pinned OpenClaw reference fragment",
        )

    deepr = profile.get("deepr")
    require(
        isinstance(deepr, dict)
        and set(deepr)
        == {
            "version",
            "source_revision",
            "source_revision_status",
            "server_command",
            "installed_executable_required",
        }
        and isinstance(deepr.get("version"), str)
        and deepr.get("version") == DEEPR_VERSION
        and deepr.get("source_revision") is None
        and deepr.get("source_revision_status") == "not_collected"
        and deepr.get("server_command") == "deepr-mcp"
        and deepr.get("installed_executable_required") is True,
        "deepr_runtime",
        "profile must require the installed deepr-mcp executable",
    )
    return tuple(violations)


def serialize_host_profile(profile: dict[str, Any]) -> str:
    """Return deterministic UTF-8-ready JSON with one final newline."""
    violations = validate_host_profile(profile)
    if violations:
        detail = "; ".join(item.detail for item in violations)
        raise ValueError(f"invalid host profile: {detail}")
    return json.dumps(profile, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def host_profile_sha256(profile: dict[str, Any]) -> str:
    """Return the digest used to bind future independent validation evidence."""
    return hashlib.sha256(serialize_host_profile(profile).encode("utf-8")).hexdigest()


__all__ = [
    "HOST_DATA_PLACEHOLDER",
    "HOST_PROFILE_KIND",
    "HOST_PROFILE_SCHEMA_VERSION",
    "V1_READ_ONLY_TOOLS",
    "HostProfileViolation",
    "build_host_profile",
    "host_profile_sha256",
    "read_only_tool_names",
    "serialize_host_profile",
    "supported_host_versions",
    "validate_host_profile",
]
