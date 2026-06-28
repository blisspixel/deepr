"""Read-only perspective-state packets for expert surfaces."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

PERSPECTIVE_STATE_SCHEMA_VERSION = "deepr-expert-perspective-state-v1"
PERSPECTIVE_STATE_KIND = "deepr.expert.perspective_state"
ORIGINAL_IDEA_AUTHORITY = "perspective_state"
ORIGINAL_IDEA_PROMOTION_POLICY = "Not a verified external fact; use as a conjectural planning input until reviewed."


def _iso(value: datetime | None) -> str:
    value = value if value is None or value.tzinfo else value.replace(tzinfo=UTC)
    return value.isoformat() if value else ""


def _compact_text(value: Any, *, fallback: str = "") -> str:
    text = " ".join(str(value or fallback).split())
    return text or fallback


def _bounded_strings(values: list[str], *, limit: int) -> list[str]:
    return [_compact_text(value) for value in values[:limit] if _compact_text(value)]


def _bound_limit(limit: int) -> int:
    return max(1, min(50, int(limit)))


def _original_idea_card(original_idea: Any) -> dict[str, Any]:
    return {
        "id": _compact_text(getattr(original_idea, "id", "")),
        "title": _compact_text(getattr(original_idea, "title", "")),
        "statement": _compact_text(getattr(original_idea, "statement", "")),
        "origin": _compact_text(getattr(original_idea, "origin", "")),
        "rationale": _compact_text(getattr(original_idea, "rationale", "")),
        "uncertainty": _compact_text(getattr(original_idea, "uncertainty", "")),
        "assumptions": _bounded_strings(list(getattr(original_idea, "assumptions", []) or []), limit=5),
        "implications": _bounded_strings(list(getattr(original_idea, "implications", []) or []), limit=5),
        "expected_observations": _bounded_strings(
            list(getattr(original_idea, "expected_observations", []) or []), limit=5
        ),
        "disconfirming_signals": _bounded_strings(
            list(getattr(original_idea, "disconfirming_signals", []) or []), limit=5
        ),
        "priority": int(getattr(original_idea, "priority", 3) or 3),
        "confidence": round(float(getattr(original_idea, "confidence", 0.0) or 0.0), 3),
        "created_at": _iso(getattr(original_idea, "created_at", None)),
        "status": _compact_text(getattr(original_idea, "status", "active"), fallback="active"),
        "authority": ORIGINAL_IDEA_AUTHORITY,
        "promotion_policy": ORIGINAL_IDEA_PROMOTION_POLICY,
    }


def load_original_idea_cards(expert_name: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Load bounded active original ideas without mutating expert state."""
    from deepr.experts.metacognition import MetaCognitionTracker
    from deepr.security.output_safety import sanitize_host_facing_payload

    ideas = sorted(
        MetaCognitionTracker(expert_name).get_original_ideas(),
        key=lambda item: (-int(getattr(item, "priority", 3) or 3), -float(getattr(item, "confidence", 0.0) or 0.0)),
    )
    return [
        sanitize_host_facing_payload(_original_idea_card(idea), source_label=f"original idea: {expert_name}")
        for idea in ideas[: _bound_limit(limit)]
    ]


def build_perspective_state_packet(expert_name: str, *, limit: int = 5) -> dict[str, Any]:
    """Build a read-only packet of non-factual perspective state."""
    original_ideas = load_original_idea_cards(expert_name, limit=limit)
    return {
        "schema_version": PERSPECTIVE_STATE_SCHEMA_VERSION,
        "kind": PERSPECTIVE_STATE_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "model_calls": 0,
            "semantic_verdict": False,
            "derived_view": True,
        },
        "expert": expert_name,
        "state_policy": {
            "factual_claims": "Use the belief graph and grounding assurance for verified external facts.",
            "original_ideas": ORIGINAL_IDEA_PROMOTION_POLICY,
            "absence_of_support": "Absence of external support is not refutation for original ideas.",
        },
        "counts": {
            "original_ideas": len(original_ideas),
        },
        "original_ideas": original_ideas,
    }


def render_original_ideas_for_council(original_ideas: list[dict[str, Any]]) -> list[str]:
    """Render original ideas as clearly labeled consult context lines."""
    if not original_ideas:
        return []

    lines = [
        "",
        "Original idea perspective state. These are planning inputs, not verified external facts.",
    ]
    for idea in original_ideas:
        lines.append(f"- ({float(idea['confidence']):.2f}) {idea['title']}: {idea['statement']}")
        if idea["rationale"]:
            lines.append(f"  Rationale: {idea['rationale']}")
        if idea["uncertainty"]:
            lines.append(f"  Uncertainty: {idea['uncertainty']}")
        if idea["expected_observations"]:
            lines.append(f"  Expected observations: {'; '.join(idea['expected_observations'][:3])}")
        if idea["disconfirming_signals"]:
            lines.append(f"  Disconfirming signals: {'; '.join(idea['disconfirming_signals'][:3])}")
    return lines


__all__ = [
    "ORIGINAL_IDEA_AUTHORITY",
    "ORIGINAL_IDEA_PROMOTION_POLICY",
    "PERSPECTIVE_STATE_KIND",
    "PERSPECTIVE_STATE_SCHEMA_VERSION",
    "build_perspective_state_packet",
    "load_original_idea_cards",
    "render_original_ideas_for_council",
]
