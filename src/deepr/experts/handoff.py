"""Versioned expert handoff payloads for downstream agents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from deepr.experts.dashboard_telemetry import build_expert_dashboard_telemetry
from deepr.experts.loop_status_rollup import build_loop_status_rollup
from deepr.experts.okf import OKF_PROFILE_SCHEMA_VERSION, OKF_SCHEMA_VERSION
from deepr.experts.perspective_state import build_perspective_state_packet
from deepr.security.output_safety import sanitize_host_facing_payload

HANDOFF_SCHEMA_VERSION = "deepr-expert-handoff-v1"
HANDOFF_KIND = "deepr.expert.handoff"
GROUNDING_ASSURANCE_LEVELS = ("cross_vendor", "same_vendor_fresh_context", "unverified")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.isoformat() if value else None


def _clamp(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _claim_sort_key(claim: Any) -> tuple[float, datetime, str]:
    return (
        float(getattr(claim, "confidence", 0.0) or 0.0),
        _aware(getattr(claim, "updated_at", None)) or datetime.min.replace(tzinfo=UTC),
        str(getattr(claim, "id", "")),
    )


def _decision_sort_key(decision: Any) -> tuple[datetime, str]:
    return (
        _aware(getattr(decision, "timestamp", None)) or datetime.min.replace(tzinfo=UTC),
        str(getattr(decision, "id", "")),
    )


def _grounding_assurance_counts(claims: list[Any]) -> dict[str, int]:
    counts = dict.fromkeys(GROUNDING_ASSURANCE_LEVELS, 0)
    for claim in claims:
        assurance = str(getattr(claim, "grounding_assurance", "unverified") or "unverified")
        counts[assurance] = counts.get(assurance, 0) + 1
    return counts


def _profile_summary(profile: Any) -> dict[str, Any]:
    return {
        "name": str(getattr(profile, "name", "")),
        "domain": str(getattr(profile, "domain", "") or ""),
        "description": getattr(profile, "description", None),
        "created_at": _iso(getattr(profile, "created_at", None)),
        "updated_at": _iso(getattr(profile, "updated_at", None)),
        "knowledge_cutoff": _iso(getattr(profile, "knowledge_cutoff_date", None)),
        "last_knowledge_refresh": _iso(getattr(profile, "last_knowledge_refresh", None)),
        "refresh_frequency_days": int(getattr(profile, "refresh_frequency_days", 0) or 0),
        "domain_velocity": str(getattr(profile, "domain_velocity", "") or ""),
        "source_file_count": len(getattr(profile, "source_files", []) or []),
        "research_job_count": len(getattr(profile, "research_jobs", []) or []),
        "total_documents": int(getattr(profile, "total_documents", 0) or 0),
    }


def _contract() -> dict[str, Any]:
    return {
        "read_only": True,
        "cost_usd": 0.0,
        "stability": "experimental",
        "compatibility": {
            "additive_fields": True,
            "breaking_changes_require_new_schema_version": True,
            "deprecation_policy": "Fields in this v1 payload are additive within v1; removals use a new schema.",
        },
        "canonical_state": [
            "expert profile",
            "belief store",
            "gap manifest",
            "durable loop-run records",
        ],
        "derived_views": [
            "OKF bundles",
            "expert digests",
            "SKILL.md exports",
        ],
    }


def build_expert_handoff(
    profile: Any,
    *,
    max_claims: int = 10,
    max_gaps: int = 10,
    loop_limit: int = 5,
    include_claims: bool = True,
    include_gaps: bool = True,
    include_decisions: bool = False,
    manifest: Any | None = None,
    telemetry: dict[str, Any] | None = None,
    loop_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable read-only expert handoff payload."""
    resolved_manifest = manifest if manifest is not None else profile.get_manifest()
    resolved_telemetry = telemetry if telemetry is not None else build_expert_dashboard_telemetry(profile)
    resolved_name = str(getattr(profile, "name", "") or getattr(resolved_manifest, "expert_name", ""))
    resolved_loop_status = (
        loop_status
        if loop_status is not None
        else build_loop_status_rollup(resolved_name, limit=_clamp(loop_limit, minimum=1, maximum=50))
    )
    perspective_state = build_perspective_state_packet(resolved_name, limit=max_claims)

    claim_limit = _clamp(max_claims, minimum=0, maximum=100)
    gap_limit = _clamp(max_gaps, minimum=0, maximum=50)
    claims = sorted(list(getattr(resolved_manifest, "claims", []) or []), key=_claim_sort_key, reverse=True)
    gaps = resolved_manifest.top_gaps(gap_limit) if hasattr(resolved_manifest, "top_gaps") else []
    decisions = sorted(
        list(getattr(resolved_manifest, "decisions", []) or []),
        key=_decision_sort_key,
        reverse=True,
    )
    grounding_assurance = _grounding_assurance_counts(claims)
    verified_claim_count = grounding_assurance.get("cross_vendor", 0) + grounding_assurance.get(
        "same_vendor_fresh_context", 0
    )

    payload: dict[str, Any] = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "kind": HANDOFF_KIND,
        "generated_at": datetime.now(UTC).isoformat(),
        "contract": _contract(),
        "expert": _profile_summary(profile),
        "summary": {
            "claim_count": int(getattr(resolved_manifest, "claim_count", len(claims)) or 0),
            "open_gap_count": int(getattr(resolved_manifest, "open_gap_count", len(gaps)) or 0),
            "decision_count": len(decisions),
            "avg_confidence": float(getattr(resolved_manifest, "avg_confidence", 0.0) or 0.0),
            "contested_open_count": int(resolved_telemetry.get("contested_claims", {}).get("open_count", 0) or 0),
            "loop_run_count": int(resolved_loop_status.get("count", 0) or 0),
            "verified_claim_count": verified_claim_count,
            "cross_vendor_verified_claim_count": grounding_assurance.get("cross_vendor", 0),
            "grounding_assurance": grounding_assurance,
            "original_idea_count": int(perspective_state["counts"]["original_ideas"]),
        },
        "limits": {
            "max_claims": claim_limit if include_claims else 0,
            "max_gaps": gap_limit if include_gaps else 0,
            "loop_limit": _clamp(loop_limit, minimum=1, maximum=50),
            "include_decisions": include_decisions,
        },
        "manifest": {
            "generated_at": _iso(getattr(resolved_manifest, "generated_at", None)),
            "policies": dict(getattr(resolved_manifest, "policies", {}) or {}),
            "claim_count": int(getattr(resolved_manifest, "claim_count", len(claims)) or 0),
            "open_gap_count": int(getattr(resolved_manifest, "open_gap_count", len(gaps)) or 0),
            "avg_confidence": float(getattr(resolved_manifest, "avg_confidence", 0.0) or 0.0),
        },
        "expert_state": resolved_telemetry,
        "perspective_state": perspective_state,
        "loop_status": resolved_loop_status,
        "okf": {
            "schema_version": OKF_SCHEMA_VERSION,
            "profile_schema_version": OKF_PROFILE_SCHEMA_VERSION,
            "profile_schema_url": "docs/schemas/okf-profile-v1.json",
            "canonical": False,
            "export_command": f"deepr expert export-okf {resolved_name!r} ./okf/{resolved_name}",
            "absorb_command": f"deepr expert absorb-okf {resolved_name!r} ./okf/{resolved_name} --dry-run",
        },
        "recommended_mcp_tools": [
            "deepr_query_expert",
            "deepr_what_changed",
            "deepr_contested",
            "deepr_explain_belief",
            "deepr_expert_loop_status",
            "deepr_expert_handoff",
        ],
    }

    if include_claims:
        payload["claims"] = [claim.to_dict() for claim in claims[:claim_limit]]
    if include_gaps:
        payload["gaps"] = [gap.to_dict() for gap in gaps[:gap_limit]]
    if include_decisions:
        payload["decisions"] = [decision.to_dict() for decision in decisions[:10]]

    return sanitize_host_facing_payload(payload, source_label=f"expert handoff: {resolved_name}")
