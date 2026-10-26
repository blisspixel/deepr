"""Trusted caller namespaces and content-free prepared-operation projections."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from deepr.experts.preparation_contracts import CallerScope

_STDIO_PROCESS_NONCE = secrets.token_hex(32)
_TRACE_ID = re.compile(r"^consult_[0-9a-f]{12}$")
_OPERATION_ID = re.compile(r"^op_[0-9a-f]{32}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_BACKENDS = frozenset({"local", "plan", "api"})
_ADMISSIONS = frozenset({"unknown", "admitted", "waiting", "unavailable"})
_SYNTHESIS_STATES = frozenset({"completed", "failed", "truncated", "cancelled", "skipped_no_valid_perspectives"})


class PreparationIdentityError(ValueError):
    """Prepared ownership admission failed without disclosing caller content."""


def _digest(value: Any) -> str:
    encoded = (
        value.encode("utf-8")
        if isinstance(value, str)
        else json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    )
    return hashlib.sha256(encoded).hexdigest()


def _capacity_identity(value: object) -> str:
    if not value:
        return ""
    if isinstance(value, str) and value.startswith("sha256:") and _DIGEST.fullmatch(value[7:]):
        return value
    return "sha256:" + _digest(value)


def current_os_principal() -> str:
    """Use the effective OS identity, never a username environment variable."""
    if sys.platform == "win32":
        from deepr.experts.preparation_permissions import PreparationPermissions

        return "windows-token-user:" + str(PreparationPermissions().sid)
    return "posix-uid:" + str(os.getuid())


def preparation_cli_scope() -> CallerScope:
    return CallerScope(namespace_sha256=_digest(["deepr-preparation-owner-v1", "cli", current_os_principal()]))


def preparation_stdio_scope() -> CallerScope:
    return CallerScope(
        namespace_sha256=_digest(
            ["deepr-preparation-owner-v1", "stdio", current_os_principal(), os.getpid(), _STDIO_PROCESS_NONCE]
        )
    )


def preparation_scoped_key_scope(owner_id: str) -> CallerScope:
    """Accept only a server-derived identity after scoped-key admission."""
    return CallerScope(namespace_sha256=_digest(["deepr-preparation-owner-v1", "http-scoped-key", owner_id]))


def safe_prepared_capacity(capacity: Mapping[str, object]) -> dict[str, object]:
    """Keep the existing lifecycle shape, with only fixed codes and hashes."""
    source = capacity.get("source", capacity.get("backend", capacity.get("synthesis_backend", "local")))
    backend = capacity.get("backend", capacity.get("synthesis_backend", source))
    if (
        not isinstance(source, str)
        or source not in _BACKENDS
        or not isinstance(backend, str)
        or backend not in _BACKENDS
    ):
        raise ValueError("Invalid prepared capacity code")
    admission = capacity.get("admission", "unknown")
    if not isinstance(admission, str) or admission not in _ADMISSIONS:
        raise ValueError("Invalid prepared capacity admission")
    fallback = capacity.get("live_metered_fallback", False)
    if not isinstance(fallback, bool):
        raise ValueError("Invalid prepared capacity fallback")
    return {
        "source": source,
        "backend": backend,
        "provider": _capacity_identity(capacity.get("provider")),
        "model": _capacity_identity(capacity.get("model")),
        "admission": admission,
        "live_metered_fallback": fallback,
    }


def safe_preparation_reference(reference: Mapping[str, object] | None) -> dict[str, str]:
    """Construct a new allowlist; never copy nested caller/source payloads."""
    result: dict[str, str] = {}
    for key in (
        "owner_sha256",
        "packet_sha256",
        "manifest_sha256",
        "capture_sha256",
        "captured_context_sha256",
        "delivery_sha256",
        "answer_sha256",
    ):
        value = (reference or {}).get(key)
        if isinstance(value, str) and _DIGEST.fullmatch(value):
            result[key] = value
    operation = (reference or {}).get("operation_id")
    if "owner_sha256" in result and isinstance(operation, str) and _OPERATION_ID.fullmatch(operation):
        result["operation_id"] = operation
    return result


def prepared_audit_trace_id(value: str | None) -> str:
    """Only a separately supplied service trace id can be retained."""
    if value is None or value == "":
        return ""
    if _TRACE_ID.fullmatch(value) is None:
        raise ValueError("Invalid prepared service trace identity")
    return value


def prepared_trace_kwargs(protected: bool, reference: Mapping[str, object] | None) -> dict[str, Any]:
    """Preserve legacy writer calls while selecting prepared privacy explicitly."""
    return {"protected_preparation": True, "preparation_reference": reference} if protected else {}


def admit_preparation_capacity(
    preparation: object | None,
    *,
    backend_mode: str,
    budget: float,
    requested_experts: list[str],
    trace_id: str,
    requested_capacity: Mapping[str, object],
) -> Mapping[str, object]:
    """Admit the additive local slice before lifecycle or backend side effects."""
    if preparation is None:
        return requested_capacity
    from deepr.experts.preparation_service import PreparationAdmission

    if (
        not isinstance(preparation, PreparationAdmission)
        or backend_mode != "local"
        or budget != 0
        or len(requested_experts) != 1
    ):
        raise ValueError("Prepared consultation requires one explicit expert, owned local synthesis and zero budget")
    prepared_audit_trace_id(trace_id)
    return safe_prepared_capacity(requested_capacity)


def is_protected_preparation(trace: Mapping[str, Any]) -> bool:
    return trace.get("protected_preparation") is True


def build_prepared_consult_trace(
    *,
    question: str,
    requested_experts: list[str],
    max_experts: int,
    budget: float,
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    capacity: dict[str, Any] | None = None,
    failure: dict[str, Any] | None = None,
    routing: dict[str, Any] | None = None,
    trace_id: str | None = None,
    recorded_at: datetime | None = None,
    preparation_reference: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Build from scratch before legacy trace assembly can copy private text."""
    del routing
    resolved_id = prepared_audit_trace_id(trace_id) or "consult_" + secrets.token_hex(6)
    synthesis = (result or {}).get("synthesis_status", "failed" if failure else "completed")
    synthesis = synthesis if isinstance(synthesis, str) and synthesis in _SYNTHESIS_STATES else "failed"
    resources: dict[str, int | float] = {}
    for key, value in {
        "max_experts": max_experts,
        "budget_usd": budget,
        "cost_usd": (payload or {}).get("cost_usd"),
    }.items():
        if not isinstance(value, bool) and isinstance(value, int | float) and math.isfinite(value) and value >= 0:
            resources[key] = value
    reference = safe_preparation_reference(preparation_reference)
    availability = "protected" if "operation_id" in reference else "unavailable"
    return {
        "schema_version": "deepr-consult-trace-v1",
        "kind": "deepr.expert.consult_trace",
        "trace_id": resolved_id,
        "recorded_at": (recorded_at or datetime.now(UTC)).isoformat(),
        "status": "completed" if not failure and synthesis == "completed" else "failed",
        "protected_preparation": True,
        "content_availability": availability,
        "input": {"question_hash": _digest(question), "roster_hash": _digest(requested_experts)},
        "capacity": safe_prepared_capacity(capacity or {}),
        "preparation": reference,
        "resources": resources,
        "context_packet": {"content_availability": availability},
        "output": {"content_availability": availability, "payload_sha256": _digest(payload or {})},
        "checks": [{"name": "private_content_protected", "status": "passed"}],
        "events": [],
        "failure": {"code": "consult_failed", "details_sha256": _digest(failure)} if failure else {},
        "synthesis_status": synthesis,
        "contract": {"private_bodies_in_global_trace": False, "semantic_quality_assessed": False},
    }
