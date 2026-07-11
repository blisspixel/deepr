"""Derived self-model records for experts."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepr.core.contracts import Claim, ExpertManifest, Gap
    from deepr.experts.profile import ExpertProfile

EXPERT_SELF_MODEL_SCHEMA_VERSION = "deepr-expert-self-model-v1"
EXPERT_SELF_MODEL_KIND = "deepr.expert.self_model"
logger = logging.getLogger(__name__)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _claim_summary(claim: Claim) -> dict[str, Any]:
    return {
        "id": claim.id,
        "statement": claim.statement,
        "confidence": round(float(claim.confidence), 3),
        "source_count": len(claim.sources),
        "contradicts": list(claim.contradicts),
    }


def _gap_summary(gap: Gap) -> dict[str, Any]:
    return {
        "id": gap.id,
        "topic": gap.topic,
        "priority": int(gap.priority),
        "ev_cost_ratio": round(float(gap.ev_cost_ratio), 3),
        "questions": list(gap.questions[:3]),
    }


def _top_claims(manifest: ExpertManifest, *, limit: int) -> list[dict[str, Any]]:
    claims = sorted(manifest.claims, key=lambda claim: float(claim.confidence), reverse=True)
    return [_claim_summary(claim) for claim in claims[:limit]]


def _top_gaps(manifest: ExpertManifest, *, limit: int) -> list[dict[str, Any]]:
    return [_gap_summary(gap) for gap in manifest.top_gaps(limit)]


def _active_contradictions(manifest: ExpertManifest, *, limit: int) -> list[dict[str, Any]]:
    contradictions: list[dict[str, Any]] = []
    for claim in manifest.claims:
        if claim.contradicts:
            contradictions.append(
                {
                    "claim_id": claim.id,
                    "statement": claim.statement,
                    "contradicts": list(claim.contradicts),
                }
            )
        if len(contradictions) >= limit:
            break
    return contradictions


def _limitations(profile: ExpertProfile, manifest: ExpertManifest, freshness: dict[str, Any]) -> list[str]:
    items: list[str] = []
    if manifest.claim_count == 0:
        items.append("No current claims in manifest.")
    if manifest.open_gap_count:
        items.append(f"{manifest.open_gap_count} open knowledge gap(s).")
    if freshness.get("status") in {"stale", "incomplete"}:
        items.append(str(freshness.get("message") or "Knowledge freshness requires attention."))
    if not profile.installed_skills:
        items.append("No expert-specific skills installed.")
    return items


def _blocked_capabilities(profile: ExpertProfile, manifest: ExpertManifest) -> list[dict[str, str]]:
    blocked: list[dict[str, str]] = []
    if manifest.claim_count == 0:
        blocked.append(
            {
                "code": "no_manifest_claims",
                "reason": "No canonical claims are available for grounded answers.",
                "next_action": "Run local or approved expert learning before relying on this expert.",
            }
        )
    if not profile.vector_store_id and profile.provider != "local":
        blocked.append(
            {
                "code": "no_vector_store",
                "reason": "The profile has no vector store id.",
                "next_action": "Create or import an expert profile with a knowledge store.",
            }
        )
    if manifest.open_gap_count:
        blocked.append(
            {
                "code": "open_gaps",
                "reason": "Open gaps limit coverage for repeated questions.",
                "next_action": "Route or fill the highest-value gaps under budget.",
            }
        )
    return blocked


def _unresolved_risks(profile: ExpertProfile, manifest: ExpertManifest, freshness: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    if freshness.get("status") in {"aging", "stale", "incomplete"}:
        risks.append(f"Freshness status is {freshness.get('status')}.")
    if manifest.avg_confidence < 0.5 and manifest.claim_count:
        risks.append("Average claim confidence is below 0.5.")
    if profile.monthly_spending > profile.monthly_learning_budget:
        risks.append("Monthly learning spend is above the configured budget.")
    if not risks:
        risks.append("No unresolved self-model risks detected by deterministic checks.")
    return risks


def build_expert_self_model(
    profile: ExpertProfile,
    manifest: ExpertManifest,
    *,
    focus_limit: int = 5,
) -> dict[str, Any]:
    """Build a read-only self-model record from current expert state."""
    focus_limit = max(1, focus_limit)
    freshness = profile.get_freshness_status()
    top_gaps = _top_gaps(manifest, limit=focus_limit)
    return {
        "schema_version": EXPERT_SELF_MODEL_SCHEMA_VERSION,
        "kind": EXPERT_SELF_MODEL_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "stability": "experimental",
            "derived_view": True,
            "goal_changes_require_review": True,
        },
        "expert": {
            "name": profile.name,
            "domain": profile.domain or manifest.domain,
            "provider": profile.provider,
            "model": profile.model,
        },
        "capabilities": {
            "domain": profile.domain or manifest.domain,
            "documents": int(profile.total_documents),
            "claim_count": manifest.claim_count,
            "open_gap_count": manifest.open_gap_count,
            "installed_skills": list(profile.installed_skills),
            "velocity": profile.domain_velocity,
        },
        "limitations": _limitations(profile, manifest, freshness),
        "calibration": {
            "avg_confidence": round(float(manifest.avg_confidence), 3),
            "claim_count": manifest.claim_count,
            "open_gap_count": manifest.open_gap_count,
            "freshness_status": str(freshness.get("status", "")),
            "freshness_score": freshness.get("freshness_score"),
        },
        "current_goals": _current_goals(profile, top_gaps, freshness),
        "learning_strategy": {
            "capacity_order": ["local", "explicit_plan", "metered_with_budget"],
            "domain_velocity": profile.domain_velocity,
            "refresh_frequency_days": int(profile.refresh_frequency_days),
            "preferred_actions": ["reuse beliefs", "route gaps", "refresh stale sources", "verify before promotion"],
        },
        "continuity_summary": {
            "created_at": _iso(profile.created_at),
            "updated_at": _iso(profile.updated_at),
            "knowledge_cutoff": _iso(profile.knowledge_cutoff_date),
            "last_knowledge_refresh": _iso(profile.last_knowledge_refresh),
            "research_jobs": len(profile.research_jobs),
            "conversations": int(profile.conversations),
            "research_triggered": int(profile.research_triggered),
        },
        "blocked_capabilities": _blocked_capabilities(profile, manifest),
        "unresolved_risks": _unresolved_risks(profile, manifest, freshness),
        "current_focus_packet": {
            "selected_beliefs": _top_claims(manifest, limit=focus_limit),
            "selected_gaps": top_gaps,
            "active_contradictions": _active_contradictions(manifest, limit=focus_limit),
            "goal": "improve or answer within current evidence, budget, and review boundaries",
            "allowed_tools": [
                "deepr expert consult",
                "deepr expert route-gaps",
                "deepr expert sync --local",
                "deepr expert why",
            ],
            "expected_stop_condition": "stop when evidence is sufficient, budget is exhausted, or review is required",
        },
    }


def build_expert_self_model_context_from_profile(
    profile: ExpertProfile,
    *,
    focus_limit: int = 3,
) -> dict[str, Any]:
    """Return bounded read-only self-model metadata for trace and loop context."""
    try:
        payload = build_expert_self_model(profile, profile.get_manifest(), focus_limit=focus_limit)
    except Exception as exc:
        logger.debug("Self-model context unavailable for %s", getattr(profile, "name", "unknown"), exc_info=True)
        return _unavailable_context(exc)
    return _compact_context(payload)


def build_expert_self_model_context(
    expert_name: str,
    *,
    focus_limit: int = 3,
) -> dict[str, Any]:
    """Load an expert and return bounded read-only self-model metadata."""
    from deepr.experts.profile import ExpertStore

    try:
        profile = ExpertStore().load(expert_name)
        if profile is None:
            return {}
    except Exception as exc:
        logger.debug("Self-model profile load failed for %s", expert_name, exc_info=True)
        return _unavailable_context(exc)
    return build_expert_self_model_context_from_profile(profile, focus_limit=focus_limit)


def _unavailable_context(exc: Exception) -> dict[str, Any]:
    return {
        "schema_version": EXPERT_SELF_MODEL_SCHEMA_VERSION,
        "kind": EXPERT_SELF_MODEL_KIND,
        "status": "unavailable",
        "error_type": type(exc).__name__,
    }


def _compact_context(payload: dict[str, Any]) -> dict[str, Any]:
    focus = payload["current_focus_packet"]
    contract = payload["contract"]
    return {
        "schema_version": payload["schema_version"],
        "kind": payload["kind"],
        "status": "available",
        "contract": {
            "read_only": contract["read_only"],
            "cost_usd": contract["cost_usd"],
            "derived_view": contract["derived_view"],
            "goal_changes_require_review": contract["goal_changes_require_review"],
        },
        "current_goals": list(payload["current_goals"]),
        "calibration": dict(payload["calibration"]),
        "blocked_capability_count": len(payload["blocked_capabilities"]),
        "unresolved_risk_count": len(payload["unresolved_risks"]),
        "current_focus_packet": {
            "selected_beliefs": list(focus["selected_beliefs"]),
            "selected_gaps": list(focus["selected_gaps"]),
            "active_contradictions": list(focus["active_contradictions"]),
            "goal": focus["goal"],
            "allowed_tools": list(focus["allowed_tools"]),
            "expected_stop_condition": focus["expected_stop_condition"],
        },
    }


def _current_goals(profile: ExpertProfile, top_gaps: list[dict[str, Any]], freshness: dict[str, Any]) -> list[str]:
    goals: list[str] = []
    if freshness.get("status") in {"stale", "incomplete"}:
        goals.append("refresh stale or incomplete knowledge")
    if top_gaps:
        goals.append(f"close highest-value gap: {top_gaps[0]['topic']}")
    if not goals:
        goals.append(f"maintain calibrated coverage for {profile.domain or profile.name}")
    return goals
