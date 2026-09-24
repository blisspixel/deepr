"""Fleet-seat MCP profile: local consult for an external harness or router.

The host owns terminals, fan-out, and any cheap classifier. This module is the
specialist contract those systems call. It does not certify a host, spend, or
treat an external probability as permission.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from deepr import __version__ as DEEPR_VERSION
from deepr.experts.route_explanation import build_route_explanation
from deepr.mcp.contained_env import build_contained_seat_env
from deepr.mcp.host_profile import HOST_DATA_PLACEHOLDER
from deepr.mcp.security.tool_allowlist import SEAT_TOOL_NAMES

SEAT_PROFILE_SCHEMA_VERSION = "deepr-mcp-seat-profile-v1"
SEAT_PROFILE_KIND = "deepr.mcp.seat_profile"
SEAT_CONSUMERS = (
    {"id": "openrig", "class": "open_source", "role": "control_plane", "support": "unvalidated"},
    {"id": "herdr", "class": "open_source", "role": "terminal_runtime", "support": "unvalidated"},
    {"id": "openclaw", "class": "open_source", "role": "gateway", "support": "unvalidated"},
    {"id": "opencode", "class": "open_source", "role": "coding_harness", "support": "unvalidated"},
    {"id": "goose", "class": "open_source", "role": "coding_harness", "support": "unvalidated"},
    {"id": "pi", "class": "open_source", "role": "coding_harness", "support": "unvalidated"},
    {"id": "hermes", "class": "open_source", "role": "personal_agent", "support": "unvalidated"},
    {"id": "deepseek-harness", "class": "open_source", "role": "coding_harness", "support": "unvalidated"},
    {"id": "claude-code", "class": "commercial", "role": "coding_harness", "support": "unvalidated"},
    {"id": "codex", "class": "commercial", "role": "coding_harness", "support": "unvalidated"},
    {"id": "cursor", "class": "commercial", "role": "coding_harness", "support": "unvalidated"},
    {"id": "grok-build", "class": "commercial", "role": "coding_harness", "support": "unvalidated"},
)


def seat_mode_active() -> bool:
    """Return whether this process is confined to the fleet-seat profile."""
    return os.environ.get("DEEPR_RESEARCH_MODE") == "seat"


def seat_local_only_error(backend: str, *, field: str) -> dict[str, Any] | None:
    """Refuse a non-local backend before provider or transaction work."""
    if not seat_mode_active() or backend == "local":
        return None
    return {
        "error_code": "SEAT_LOCAL_ONLY",
        "category": "capacity",
        "retryable": False,
        "message": (
            "The fleet-seat profile accepts local synthesis only. "
            f"{field}={backend!r} was refused before a provider client or consult transaction was created."
        ),
    }


def _route_error(code: str, message: str) -> dict[str, Any]:
    return {"error_code": code, "category": "validation", "retryable": False, "message": message}


def _bounded_int(value: object, *, name: str, default: int, upper: int) -> tuple[int | None, dict[str, Any] | None]:
    if value is None:
        return default, None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
        return None, _route_error("INVALID_ROUTE_LIMIT", f"{name} must be an integer from 1 to {upper}")
    return value, None


async def explain_route_tool(
    *,
    query: str,
    max_experts: int = 3,
    top_n: int = 5,
    admissions_path: Path | None = None,
) -> dict[str, Any]:
    """Return the $0 route card. Overlap is a hint, not a verdict or a permission."""
    if not isinstance(query, str) or not query.strip():
        return _route_error("INVALID_QUERY", "query must be a non-empty string")
    parsed_max, error = _bounded_int(max_experts, name="max_experts", default=3, upper=10)
    if error is not None or parsed_max is None:
        return error or _route_error("INVALID_ROUTE_LIMIT", "max_experts must be an integer from 1 to 10")
    parsed_top, error = _bounded_int(top_n, name="top_n", default=5, upper=10)
    if error is not None or parsed_top is None:
        return error or _route_error("INVALID_ROUTE_LIMIT", "top_n must be an integer from 1 to 10")
    return build_route_explanation(
        query.strip(),
        max_experts=parsed_max,
        top_n=parsed_top,
        admissions_path=admissions_path,
    )


def seat_consumer_dispatch(server: Any) -> dict[str, Callable[[dict[str, Any]], Awaitable[Any]]]:
    """Dispatch seat tools without growing the grandfathered server module."""
    return {
        "deepr_consult_experts": lambda args: server.consult_experts(**args),
        "deepr_route_explain": lambda args: explain_route_tool(
            query=args.get("query", ""),
            max_experts=args.get("max_experts", 3),
            top_n=args.get("top_n", 5),
        ),
    }


def build_seat_profile() -> dict[str, Any]:
    """Return the reference seat profile. Support stays unvalidated for every host."""
    env = build_contained_seat_env(HOST_DATA_PLACEHOLDER)
    return {
        "schema_version": SEAT_PROFILE_SCHEMA_VERSION,
        "kind": SEAT_PROFILE_KIND,
        "deepr": {"version": DEEPR_VERSION},
        "authority": {
            "generation_mode": "offline_config_only",
            "generation_cost_usd": 0,
            "runtime_paid_dispatch_authorized": False,
            "local_synthesis_only": True,
            "external_probability_is_authority": False,
            "host_support_claimed": False,
        },
        "tools": list(SEAT_TOOL_NAMES),
        "denied_classes": [
            "research dispatch",
            "absorb",
            "skill install",
            "metered reflection",
            "plan or api synthesis",
        ],
        "env": env,
        "consumers": [dict(item) for item in SEAT_CONSUMERS],
        "config_fragment": {
            "mcpServers": {
                "deepr": {
                    "command": "deepr",
                    "args": ["mcp", "serve"],
                    "env": env,
                }
            }
        },
    }


def serialize_seat_profile(profile: dict[str, Any] | None = None) -> str:
    """Serialize the seat profile canonically."""
    payload = build_seat_profile() if profile is None else profile
    violations = validate_seat_profile(payload)
    if violations:
        raise ValueError("invalid seat profile: " + "; ".join(violations))
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _append_if_wrong(violations: list[str], code: str, *, ok: bool) -> None:
    if not ok:
        violations.append(code)


def _env_violations(env: object) -> list[str]:
    if not isinstance(env, dict) or env.get("DEEPR_RESEARCH_MODE") != "seat":
        return ["env"]
    costly = [key for key in env if key.endswith("_LIMIT") or key.startswith("DEEPR_MAX_COST")]
    if any(env.get(key) != "0" for key in costly):
        return ["spend_ceiling"]
    return []


def _authority_violations(authority: object) -> list[str]:
    if not isinstance(authority, dict):
        return ["authority", "probability"]
    violations: list[str] = []
    if authority.get("runtime_paid_dispatch_authorized") is not False:
        violations.append("authority")
    if authority.get("external_probability_is_authority") is not False:
        violations.append("probability")
    return violations


def _consumers_ok(consumers: object) -> list[str]:
    violations: list[str] = []
    if not isinstance(consumers, list):
        return ["consumers"]
    by_id = {item.get("id"): item for item in consumers if isinstance(item, dict)}
    for required in ("openrig", "herdr", "opencode", "claude-code", "grok-build"):
        item = by_id.get(required)
        if not isinstance(item, dict) or item.get("support") != "unvalidated":
            violations.append(f"consumer:{required}")
    if any(isinstance(item, dict) and item.get("support") == "live_validated" for item in consumers):
        violations.append("live_support")
    return violations


def validate_seat_profile(profile: dict[str, Any]) -> list[str]:
    """Return contract violations. An empty list means the reference profile is intact."""
    violations: list[str] = []
    _append_if_wrong(
        violations,
        "schema_version",
        ok=profile.get("schema_version") == SEAT_PROFILE_SCHEMA_VERSION,
    )
    _append_if_wrong(violations, "kind", ok=profile.get("kind") == SEAT_PROFILE_KIND)
    _append_if_wrong(violations, "tools", ok=profile.get("tools") == list(SEAT_TOOL_NAMES))
    violations.extend(_env_violations(profile.get("env")))
    violations.extend(_authority_violations(profile.get("authority")))
    violations.extend(_consumers_ok(profile.get("consumers")))
    return violations


__all__ = [
    "SEAT_CONSUMERS",
    "SEAT_PROFILE_KIND",
    "SEAT_PROFILE_SCHEMA_VERSION",
    "SEAT_TOOL_NAMES",
    "build_seat_profile",
    "explain_route_tool",
    "seat_consumer_dispatch",
    "seat_local_only_error",
    "seat_mode_active",
    "serialize_seat_profile",
    "validate_seat_profile",
]
