"""Generated EXPERT.md memory cards for durable experts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepr.experts.paths import canonical_expert_dir
from deepr.experts.self_model import build_expert_self_model
from deepr.utils.atomic_io import atomic_write_text

if TYPE_CHECKING:
    from deepr.core.contracts import Claim, ExpertManifest, Gap
    from deepr.experts.profile import ExpertProfile

EXPERT_MEMORY_CARD_SCHEMA_VERSION = "deepr-expert-memory-card-v1"
EXPERT_MEMORY_CARD_KIND = "deepr.expert.memory_card"
DEFAULT_MEMORY_CARD_FILENAME = "EXPERT.md"


@dataclass(frozen=True)
class ExpertMemoryCardArtifact:
    """A rendered memory-card artifact and its structured payload."""

    payload: dict[str, Any]
    markdown: str
    path: Path | None = None


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _compact_text(value: Any, *, fallback: str = "") -> str:
    text = " ".join(str(value or fallback).split())
    return text or fallback


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _frontmatter_value(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def _bound_limit(limit: int) -> int:
    return max(1, min(50, int(limit)))


def memory_card_path(expert_name: str, *, base_path: Path | None = None) -> Path:
    """Return the canonical EXPERT.md path for an expert."""
    return canonical_expert_dir(expert_name, base_path) / DEFAULT_MEMORY_CARD_FILENAME


def _source_summary(source: Any) -> dict[str, Any]:
    return {
        "id": _compact_text(getattr(source, "id", "")),
        "title": _compact_text(getattr(source, "title", "")),
        "url": _compact_text(getattr(source, "url", "")),
        "trust_class": _enum_value(getattr(source, "trust_class", "")),
        "support_class": _enum_value(getattr(source, "support_class", "")),
        "retrieved_at": _iso(getattr(source, "retrieved_at", None)),
    }


def _claim_card(claim: Claim) -> dict[str, Any]:
    sources = [_source_summary(source) for source in claim.sources]
    return {
        "id": claim.id,
        "statement": _compact_text(claim.statement),
        "domain": _compact_text(claim.domain),
        "confidence": round(float(claim.confidence), 3),
        "grounding_assurance": _compact_text(claim.grounding_assurance, fallback="unverified"),
        "source_count": len(claim.sources),
        "sources": sources[:5],
        "contradicts": list(claim.contradicts),
        "tags": list(claim.tags),
        "created_at": _iso(claim.created_at),
        "updated_at": _iso(claim.updated_at),
    }


def _belief_cards(manifest: ExpertManifest, *, limit: int) -> list[dict[str, Any]]:
    claims = sorted(manifest.claims, key=lambda claim: (-float(claim.confidence), claim.id))
    return [_claim_card(claim) for claim in claims[:limit]]


def _gap_card(gap: Gap) -> dict[str, Any]:
    return {
        "id": gap.id,
        "topic": _compact_text(gap.topic),
        "priority": int(gap.priority),
        "ev_cost_ratio": round(float(gap.ev_cost_ratio), 3),
        "questions": [_compact_text(question) for question in gap.questions[:5]],
        "times_asked": int(gap.times_asked),
        "estimated_cost": round(float(gap.estimated_cost), 4),
        "filled": bool(gap.filled),
    }


def _gap_cards(manifest: ExpertManifest, *, limit: int) -> list[dict[str, Any]]:
    return [_gap_card(gap) for gap in manifest.top_gaps(limit)]


def _perspective_state_tags(claim: Claim) -> list[str]:
    tags: list[str] = []
    for tag in claim.tags:
        normalized = str(tag).strip().lower().replace("-", "_")
        if normalized in {"hypothesis", "stance", "proposal", "original_idea", "theory", "insight", "inferred"}:
            tags.append(normalized)
    return tags


def _working_theories(manifest: ExpertManifest, *, limit: int) -> list[dict[str, Any]]:
    theories: list[dict[str, Any]] = []
    for claim in sorted(manifest.claims, key=lambda item: (-float(item.confidence), item.id)):
        state_tags = _perspective_state_tags(claim)
        if not state_tags:
            continue
        card = _claim_card(claim)
        card["state_tags"] = state_tags
        card["authority"] = "perspective_state"
        card["promotion_policy"] = "Needs review before being presented as a verified external fact."
        theories.append(card)
        if len(theories) >= limit:
            break
    return theories


def _active_contradictions(manifest: ExpertManifest, *, limit: int) -> list[dict[str, Any]]:
    by_id = {claim.id: claim for claim in manifest.claims}
    contradictions: list[dict[str, Any]] = []
    for claim in manifest.claims:
        if not claim.contradicts:
            continue
        contradictions.append(
            {
                "claim_id": claim.id,
                "statement": _compact_text(claim.statement),
                "contradicts": [
                    {
                        "claim_id": other_id,
                        "statement": _compact_text(by_id[other_id].statement) if other_id in by_id else "",
                    }
                    for other_id in claim.contradicts
                ],
            }
        )
        if len(contradictions) >= limit:
            break
    return contradictions


def _recent_belief_events(expert_name: str, *, limit: int, event_log_path: Path | None = None) -> list[dict[str, Any]]:
    path = event_log_path or (canonical_expert_dir(expert_name) / "beliefs" / "events.jsonl")
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append(
                {
                    "timestamp": _compact_text(event.get("timestamp")),
                    "belief_id": _compact_text(event.get("belief_id")),
                    "change_type": _compact_text(event.get("change_type")),
                    "reason": _compact_text(event.get("reason")),
                    "new_claim": _compact_text(event.get("new_claim")),
                    "old_claim": _compact_text(event.get("old_claim")),
                }
            )
    except OSError:
        return []
    return events[-limit:]


def _current_stance(self_model: dict[str, Any], manifest: ExpertManifest) -> dict[str, Any]:
    focus = self_model["current_focus_packet"]
    beliefs = list(focus["selected_beliefs"])
    gaps = list(focus["selected_gaps"])
    stance_summary = "No current claims are available yet."
    if beliefs:
        top = beliefs[0]
        stance_summary = f"Current strongest position: {top['statement']} (confidence {float(top['confidence']):.3f})."
    return {
        "summary": stance_summary,
        "belief_count": manifest.claim_count,
        "open_gap_count": manifest.open_gap_count,
        "top_focus_beliefs": beliefs,
        "top_focus_gaps": gaps,
        "interpretation_policy": (
            "Treat beliefs as calibrated positions with provenance, not as a complete fact book."
        ),
    }


def _self_research_agenda(
    self_model: dict[str, Any],
    gaps: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    agenda: list[dict[str, Any]] = []
    freshness = self_model["calibration"]["freshness_status"]
    if freshness in {"aging", "stale", "incomplete"}:
        agenda.append(
            {
                "topic": "refresh current domain state",
                "reason": f"freshness status is {freshness}",
                "capacity_order": list(self_model["learning_strategy"]["capacity_order"]),
                "budget_policy": "owned or prepaid capacity first; metered only behind an explicit budget gate",
            }
        )
    for gap in gaps:
        agenda.append(
            {
                "topic": gap["topic"],
                "reason": "open high-value knowledge gap",
                "priority": gap["priority"],
                "ev_cost_ratio": gap["ev_cost_ratio"],
                "capacity_order": list(self_model["learning_strategy"]["capacity_order"]),
                "budget_policy": "owned or prepaid capacity first; metered only behind an explicit budget gate",
            }
        )
        if len(agenda) >= limit:
            break
    if not agenda:
        agenda.append(
            {
                "topic": "maintain calibrated perspective",
                "reason": "no higher-priority gap is currently recorded",
                "capacity_order": list(self_model["learning_strategy"]["capacity_order"]),
                "budget_policy": "no refresh spend unless new evidence, staleness, or user demand justifies it",
            }
        )
    return agenda[:limit]


def _what_would_change_my_mind(
    *,
    beliefs: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    limit: int,
) -> list[str]:
    signals: list[str] = []
    for item in contradictions:
        signals.append(f"Resolve active contradiction around: {item['statement']}")
        if len(signals) >= limit:
            return signals
    for gap in gaps:
        signals.append(f"New evidence or analysis that closes gap: {gap['topic']}")
        if len(signals) >= limit:
            return signals
    if beliefs:
        signals.append("High-trust contradictory evidence against the strongest current beliefs.")
        signals.append("A fresher source pack showing the domain has materially changed.")
    else:
        signals.append("A reviewed source pack that establishes an initial domain model.")
    return signals[:limit]


def _perspective_packet(
    self_model: dict[str, Any],
    manifest: ExpertManifest,
    *,
    beliefs: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    theories = _working_theories(manifest, limit=limit)
    return {
        "position": "expertise is a developing perspective, not a fact list",
        "working_theories": theories,
        "insight_candidates": [
            theory for theory in theories if {"insight", "original_idea", "proposal"} & set(theory["state_tags"])
        ],
        "self_research_agenda": _self_research_agenda(self_model, gaps, limit=limit),
        "what_would_change_my_mind": _what_would_change_my_mind(
            beliefs=beliefs,
            gaps=gaps,
            contradictions=contradictions,
            limit=limit,
        ),
        "agency_scope": {
            "can_do_without_metered_spend": [
                "read structured expert state",
                "regenerate derived memory cards",
                "use local capacity when configured",
                "use explicit plan-quota capacity when the operator selects it",
            ],
            "requires_explicit_gate": [
                "metered API calls",
                "profile identity changes",
                "learning-policy effects",
                "graph writes from new semantic claims",
                "tool or permission expansion",
            ],
            "autonomy_boundary": (
                "The expert may propose research, theories, and self-model changes, but workflow gates own spend, "
                "capacity, writes, schemas, and review."
            ),
        },
    }


def build_expert_memory_card(
    profile: ExpertProfile,
    manifest: ExpertManifest | None = None,
    *,
    focus_limit: int = 8,
    generated_at: datetime | None = None,
    event_log_path: Path | None = None,
) -> dict[str, Any]:
    """Build a read-only memory-card payload from canonical expert state."""
    focus_limit = _bound_limit(focus_limit)
    manifest = manifest or profile.get_manifest()
    generated_at = generated_at or _utc_now()
    self_model = build_expert_self_model(profile, manifest, focus_limit=focus_limit)
    domain = _compact_text(profile.domain or manifest.domain or profile.description, fallback="general")
    card_path = memory_card_path(profile.name)
    beliefs = _belief_cards(manifest, limit=focus_limit)
    gaps = _gap_cards(manifest, limit=focus_limit)
    contradictions = _active_contradictions(manifest, limit=focus_limit)
    return {
        "schema_version": EXPERT_MEMORY_CARD_SCHEMA_VERSION,
        "kind": EXPERT_MEMORY_CARD_KIND,
        "contract": {
            "read_only": True,
            "cost_usd": 0.0,
            "derived_view": True,
            "authoritative": False,
            "stability": "experimental",
            "model_calls": 0,
            "writes": "none",
            "regeneration_command": f"deepr expert memory-card {json.dumps(profile.name)} --write",
        },
        "artifact": {
            "filename": DEFAULT_MEMORY_CARD_FILENAME,
            "path": str(card_path),
            "generated_at": generated_at.isoformat(),
            "canonical_state": "expert profile, manifest, belief event log, and self-model records",
            "frontmatter_marker": EXPERT_MEMORY_CARD_KIND,
        },
        "expert": {
            "name": profile.name,
            "preferred_name": profile.name,
            "domain": domain,
            "description": _compact_text(profile.description or profile.domain, fallback=domain),
            "identity_policy": (
                "The profile name is authoritative. Proposed identity or naming changes must pass self-model review."
            ),
        },
        "memory_layers": {
            "profile": {
                "role": "stable identity and configuration",
                "authority": "canonical",
                "path": "profile.json",
            },
            "belief_graph": {
                "role": "claims, confidence, provenance, contradictions, and typed edges",
                "authority": "canonical",
                "path": "beliefs/",
            },
            "event_log": {
                "role": "append-only memory of belief changes",
                "authority": "canonical",
                "path": "beliefs/events.jsonl",
            },
            "self_model": {
                "role": "read-only capabilities, limits, current goals, learning strategy, and focus packet",
                "authority": "derived",
                "schema_version": self_model["schema_version"],
            },
            "wiki_card": {
                "role": "compact wiki-style handoff for humans and host agents",
                "authority": "derived",
                "path": DEFAULT_MEMORY_CARD_FILENAME,
            },
        },
        "continuity": self_model["continuity_summary"],
        "calibration": self_model["calibration"],
        "current_goals": list(self_model["current_goals"]),
        "learning_strategy": dict(self_model["learning_strategy"]),
        "current_stance": _current_stance(self_model, manifest),
        "perspective": _perspective_packet(
            self_model,
            manifest,
            beliefs=beliefs,
            gaps=gaps,
            contradictions=contradictions,
            limit=focus_limit,
        ),
        "beliefs": beliefs,
        "gaps": gaps,
        "active_contradictions": contradictions,
        "recent_belief_events": _recent_belief_events(profile.name, limit=focus_limit, event_log_path=event_log_path),
        "collaboration": {
            "best_used_for": [
                "asking current domain questions",
                "surfacing uncertainty and dissent",
                "planning what to learn next",
                "handing structured expert state to another agent",
            ],
            "host_agent_guidance": [
                "Use this card as orientation, then inspect handoff, loop status, and belief explanations when needed.",
                "Ask for fresh research when the freshness status or domain velocity says the topic may have moved.",
                "Do not treat absence of web support as refutation of a hypothesis or original idea.",
            ],
            "next_commands": [
                "deepr expert self-model NAME --json",
                "deepr expert consult NAME --json",
                "deepr expert why NAME BELIEF_ID",
                "deepr expert sync NAME --local",
            ],
        },
        "update_policy": {
            "manual_edit_authority": "none",
            "canonical_update_paths": [
                "deepr expert absorb",
                "deepr expert sync",
                "deepr expert propose-self-model",
                "deepr expert accept-self-model",
            ],
            "review_required_for": [
                "identity changes",
                "goal changes",
                "learning-policy effects",
                "claim promotion from hypothesis or stance to factual belief",
            ],
            "regeneration": "Regenerate this file after canonical state changes. Do not hand-edit it as memory.",
        },
    }


def _append_bullet_lines(lines: list[str], items: list[str]) -> None:
    if not items:
        lines.append("- None recorded.")
        return
    for item in items:
        lines.append(f"- {_compact_text(item)}")


def _memory_card_header_lines(payload: dict[str, Any]) -> list[str]:
    expert = payload["expert"]
    contract = payload["contract"]
    artifact = payload["artifact"]
    return [
        "---",
        f"schema_version: {_frontmatter_value(payload['schema_version'])}",
        f"kind: {_frontmatter_value(payload['kind'])}",
        f"expert: {_frontmatter_value(expert['name'])}",
        f"generated_at: {_frontmatter_value(artifact['generated_at'])}",
        "derived_view: true",
        "authoritative: false",
        "---",
        "",
        f"# {_compact_text(expert['preferred_name'])}",
        "",
        "This is a generated expert memory card. Canonical memory lives in structured Deepr state.",
        "",
        "## Identity",
        f"- Name: {_compact_text(expert['name'])}",
        f"- Domain: {_compact_text(expert['domain'])}",
        f"- Description: {_compact_text(expert['description'])}",
        f"- Identity policy: {_compact_text(expert['identity_policy'])}",
        "",
        "## Contract",
        f"- Cost: ${float(contract['cost_usd']):.4f}",
        f"- Read only: {str(bool(contract['read_only'])).lower()}",
        f"- Derived view: {str(bool(contract['derived_view'])).lower()}",
        f"- Authoritative memory: {str(bool(contract['authoritative'])).lower()}",
        f"- Regenerate: `{_compact_text(contract['regeneration_command'])}`",
        "",
        "## Current Stance",
        f"- Summary: {_compact_text(payload['current_stance']['summary'])}",
        f"- Interpretation policy: {_compact_text(payload['current_stance']['interpretation_policy'])}",
        f"- Claim count: {int(payload['current_stance']['belief_count'])}",
        f"- Open gaps: {int(payload['current_stance']['open_gap_count'])}",
        "",
        "## Perspective And Agency",
        f"- Position: {_compact_text(payload['perspective']['position'])}",
        f"- Autonomy boundary: {_compact_text(payload['perspective']['agency_scope']['autonomy_boundary'])}",
        "- Can do without metered spend:",
    ]


def _append_perspective_section(lines: list[str], payload: dict[str, Any]) -> None:
    _append_bullet_lines(lines, list(payload["perspective"]["agency_scope"]["can_do_without_metered_spend"]))
    lines.append("- Requires explicit gate:")
    _append_bullet_lines(lines, list(payload["perspective"]["agency_scope"]["requires_explicit_gate"]))
    lines.extend(
        [
            "",
            "## Working Theories And Insights",
        ]
    )


def _append_theories_section(lines: list[str], payload: dict[str, Any]) -> None:
    theories = list(payload["perspective"]["working_theories"])
    if not theories:
        lines.append("- No explicitly labeled theories, stances, proposals, original ideas, or insights recorded yet.")
    for theory in theories:
        tags = ", ".join(theory["state_tags"])
        lines.append(
            f"- [{theory['id']}] {_compact_text(theory['statement'])} "
            f"(tags: {tags}, confidence {float(theory['confidence']):.3f})"
        )
        lines.append(f"  - {_compact_text(theory['promotion_policy'])}")
    lines.extend(
        [
            "",
            "## Self Research Agenda",
        ]
    )


def _append_self_research_section(lines: list[str], payload: dict[str, Any]) -> None:
    for item in payload["perspective"]["self_research_agenda"]:
        lines.append(f"- {_compact_text(item['topic'])}: {_compact_text(item['reason'])}")
        lines.append(f"  - capacity order: {', '.join(item['capacity_order'])}")
        lines.append(f"  - budget policy: {_compact_text(item['budget_policy'])}")
    lines.extend(
        [
            "",
            "## What Would Change My Mind",
        ]
    )
    _append_bullet_lines(lines, list(payload["perspective"]["what_would_change_my_mind"]))


def _append_calibration_section(lines: list[str], payload: dict[str, Any]) -> None:
    calibration = payload["calibration"]
    continuity = payload["continuity"]
    lines.extend(
        [
            "",
            "## Calibration And Freshness",
            f"- Average confidence: {float(calibration['avg_confidence']):.3f}",
            f"- Freshness status: {_compact_text(calibration['freshness_status'])}",
            f"- Freshness score: {_compact_text(calibration.get('freshness_score'), fallback='unknown')}",
            f"- Knowledge cutoff: {_compact_text(continuity.get('knowledge_cutoff'), fallback='unknown')}",
            f"- Last refresh: {_compact_text(continuity.get('last_knowledge_refresh'), fallback='unknown')}",
            "",
            "## Current Goals",
        ]
    )
    _append_bullet_lines(lines, list(payload["current_goals"]))
    lines.extend(["", "## Memory Layers"])
    for name, layer in payload["memory_layers"].items():
        lines.append(
            f"- {name}: {_compact_text(layer['role'])} "
            f"(authority: {_compact_text(layer['authority'])}, path: {_compact_text(layer.get('path'), fallback='n/a')})"
        )
    lines.extend(["", "## Beliefs"])


def _append_beliefs_section(lines: list[str], payload: dict[str, Any]) -> None:
    beliefs = list(payload["beliefs"])
    if not beliefs:
        lines.append("- No current beliefs recorded.")
    for belief in beliefs:
        lines.append(
            f"- [{belief['id']}] {_compact_text(belief['statement'])} "
            f"(confidence {float(belief['confidence']):.3f}, "
            f"assurance {_compact_text(belief['grounding_assurance'])}, "
            f"sources {int(belief['source_count'])})"
        )
    lines.extend(["", "## Open Gaps"])


def _append_gaps_section(lines: list[str], payload: dict[str, Any]) -> None:
    gaps = list(payload["gaps"])
    if not gaps:
        lines.append("- No open gaps recorded.")
    for gap in gaps:
        lines.append(
            f"- [{gap['id']}] {_compact_text(gap['topic'])} "
            f"(priority {int(gap['priority'])}, EV/cost {float(gap['ev_cost_ratio']):.3f})"
        )
        for question in gap["questions"][:3]:
            lines.append(f"  - {_compact_text(question)}")
    lines.extend(["", "## Active Contradictions"])


def _append_contradictions_section(lines: list[str], payload: dict[str, Any]) -> None:
    contradictions = list(payload["active_contradictions"])
    if not contradictions:
        lines.append("- None recorded.")
    for item in contradictions:
        lines.append(f"- [{item['claim_id']}] {_compact_text(item['statement'])}")
        for other in item["contradicts"]:
            label = _compact_text(other.get("statement"), fallback=other["claim_id"])
            lines.append(f"  - contradicts {other['claim_id']}: {label}")
    lines.extend(["", "## Recent Belief Events"])


def _append_recent_events_section(lines: list[str], payload: dict[str, Any]) -> None:
    events = list(payload["recent_belief_events"])
    if not events:
        lines.append("- No recent belief events recorded.")
    for event in events:
        label = _compact_text(event.get("new_claim") or event.get("old_claim"), fallback=event["belief_id"])
        lines.append(f"- {event['timestamp']} {event['change_type']} {event['belief_id']}: {label}")
    lines.extend(["", "## Collaboration"])
    _append_bullet_lines(lines, list(payload["collaboration"]["host_agent_guidance"]))
    lines.extend(["", "## Update Policy"])


def _append_update_policy_section(lines: list[str], payload: dict[str, Any]) -> None:
    policy = payload["update_policy"]
    lines.append(f"- Manual edit authority: {_compact_text(policy['manual_edit_authority'])}")
    lines.append(f"- Regeneration: {_compact_text(policy['regeneration'])}")
    lines.append("- Canonical update paths:")
    _append_bullet_lines(lines, list(policy["canonical_update_paths"]))
    lines.append("- Review required for:")
    _append_bullet_lines(lines, list(policy["review_required_for"]))


def render_expert_memory_card(payload: dict[str, Any]) -> str:
    """Render a memory-card payload as Markdown."""
    lines = _memory_card_header_lines(payload)
    _append_perspective_section(lines, payload)
    _append_theories_section(lines, payload)
    _append_self_research_section(lines, payload)
    _append_calibration_section(lines, payload)
    _append_beliefs_section(lines, payload)
    _append_gaps_section(lines, payload)
    _append_contradictions_section(lines, payload)
    _append_recent_events_section(lines, payload)
    _append_update_policy_section(lines, payload)
    return "\n".join(lines) + "\n"


def write_expert_memory_card(
    profile: ExpertProfile,
    manifest: ExpertManifest | None = None,
    *,
    focus_limit: int = 8,
    output_path: Path | None = None,
    generated_at: datetime | None = None,
) -> ExpertMemoryCardArtifact:
    """Build and atomically write an EXPERT.md memory card."""
    payload = build_expert_memory_card(
        profile,
        manifest=manifest,
        focus_limit=focus_limit,
        generated_at=generated_at,
    )
    markdown = render_expert_memory_card(payload)
    path = output_path or memory_card_path(profile.name)
    atomic_write_text(path, markdown, encoding="utf-8")
    return ExpertMemoryCardArtifact(payload=payload, markdown=markdown, path=path)


__all__ = [
    "DEFAULT_MEMORY_CARD_FILENAME",
    "EXPERT_MEMORY_CARD_KIND",
    "EXPERT_MEMORY_CARD_SCHEMA_VERSION",
    "ExpertMemoryCardArtifact",
    "build_expert_memory_card",
    "memory_card_path",
    "render_expert_memory_card",
    "write_expert_memory_card",
]
