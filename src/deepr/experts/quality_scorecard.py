"""Structural quality scorecard for domain experts ($0, no model).

Measures provenance depth, circularity risk, multi-source share, and learning
loop evidence. Does **not** claim semantic excellence (AGENTIC_BALANCE).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

QUALITY_SCHEMA = "deepr-expert-quality-v1"
QUALITY_KIND = "deepr.expert.quality"

# Filename tokens that mark project-stance corpus (echo risk when dominant).
_DEFAULT_CIRCULAR_TOKENS = (
    "intent.md",
    "readme.md",
    "roadmap.md",
    "nephmesh-intent",
    "project-intent",
    "agents.md",
)


@dataclass
class ExpertQualityScorecard:
    """Structural quality snapshot for one expert."""

    schema_version: str = QUALITY_SCHEMA
    kind: str = QUALITY_KIND
    expert_name: str = ""
    domain: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    claim_count: int = 0
    trust_mix: dict[str, int] = field(default_factory=dict)
    effective_confidence: dict[str, float] = field(default_factory=dict)
    multi_source_share: float = 0.0
    multi_source_count: int = 0
    distinct_origin_count: int = 0
    circularity_risk: float = 0.0
    circular_claim_count: int = 0
    secondary_or_better_share: float = 0.0
    open_gap_count: int = 0
    verified_learning_loops: int = 0
    stage_hint: str = "unknown"
    grade: str = "F"
    blockers: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    next_actions: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(
        default_factory=lambda: [
            "Structural provenance scorecard only - not a semantic maturity verdict.",
            "Human or calibrated eval must judge whether answers are actually exceptional.",
            "cost_usd=0; no model calls.",
        ]
    )
    cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_circular_ref(ref: str, tokens: tuple[str, ...]) -> bool:
    lowered = str(ref).lower()
    return any(token in lowered for token in tokens)


def _grade_findings(
    *,
    claim_count: int,
    secondary_or_better_share: float,
    multi_source_share: float,
    circularity_risk: float,
    verified_learning_loops: int,
) -> tuple[list[str], list[str]]:
    """Structural blockers and strengths. No semantic verdict."""
    blockers: list[str] = []
    strengths: list[str] = []

    if claim_count < 15:
        blockers.append("thin inventory: fewer than 15 claims")
    else:
        strengths.append(f"inventory size {claim_count}")

    if secondary_or_better_share < 0.5:
        blockers.append(
            f"secondary_or_better_share={secondary_or_better_share:.2f} < 0.50 (too much tertiary/web-capped knowledge)"
        )
    else:
        strengths.append(f"secondary_or_better_share={secondary_or_better_share:.2f}")

    if circularity_risk > 0.35:
        blockers.append(
            f"circularity_risk={circularity_risk:.2f} > 0.35 "
            "(project-intent/README provenance dominates - echo chamber)"
        )
    elif circularity_risk <= 0.15:
        strengths.append(f"low circularity_risk={circularity_risk:.2f}")

    if multi_source_share < 0.15 and claim_count >= 15:
        blockers.append(
            f"multi_source_share={multi_source_share:.2f} < 0.15 (few claims corroborated across independent origins)"
        )
    elif multi_source_share >= 0.25:
        strengths.append(f"multi_source_share={multi_source_share:.2f}")

    if verified_learning_loops == 0 and claim_count >= 10:
        blockers.append("no verified learning-loop improvements recorded yet")

    return blockers, strengths


def _grade_letter(
    *,
    claim_count: int,
    secondary_or_better_share: float,
    multi_source_share: float,
    circularity_risk: float,
    verified_learning_loops: int,
    blocker_count: int,
) -> str:
    """Letter grade is structural only."""
    score = 0
    score += 2 if claim_count >= 30 else 1 if claim_count >= 15 else 0
    score += 3 if secondary_or_better_share >= 0.7 else 2 if secondary_or_better_share >= 0.5 else 0
    score += 2 if circularity_risk <= 0.15 else 1 if circularity_risk <= 0.35 else 0
    score += 2 if multi_source_share >= 0.25 else 1 if multi_source_share >= 0.15 else 0
    score += 1 if verified_learning_loops > 0 else 0

    if score >= 9 and blocker_count == 0:
        return "A"
    if score >= 7 and blocker_count <= 1:
        return "B"
    if score >= 5:
        return "C"
    if score >= 3:
        return "D"
    return "F"


def _grade(
    *,
    claim_count: int,
    secondary_or_better_share: float,
    multi_source_share: float,
    circularity_risk: float,
    verified_learning_loops: int,
) -> tuple[str, list[str], list[str]]:
    blockers, strengths = _grade_findings(
        claim_count=claim_count,
        secondary_or_better_share=secondary_or_better_share,
        multi_source_share=multi_source_share,
        circularity_risk=circularity_risk,
        verified_learning_loops=verified_learning_loops,
    )
    grade = _grade_letter(
        claim_count=claim_count,
        secondary_or_better_share=secondary_or_better_share,
        multi_source_share=multi_source_share,
        circularity_risk=circularity_risk,
        verified_learning_loops=verified_learning_loops,
        blocker_count=len(blockers),
    )
    return grade, blockers, strengths


def _belief_trust_class(belief: Any) -> str:
    return str(getattr(belief, "trust_class", "tertiary") or "tertiary").lower()


def _belief_effective_confidence(belief: Any) -> float:
    get_conf = getattr(belief, "get_current_confidence", None)
    if callable(get_conf):
        return float(get_conf())
    return float(getattr(belief, "confidence", 0.0) or 0.0)


def _belief_refs(belief: Any) -> list[str]:
    return [str(r) for r in (getattr(belief, "evidence_refs", []) or [])]


def _belief_independent_source_count(belief: Any, refs: list[str]) -> int:
    indep = getattr(belief, "_independent_source_count", None)
    if callable(indep):
        return int(indep())
    return len({r.lower() for r in refs if r.strip() and " " not in r})


def _compact_refs(refs: list[str]) -> list[str]:
    """Origin tokens: whitespace-free refs that are not rejected-candidate markers."""
    return [
        r.strip()
        for r in refs
        if r.strip() and " " not in r.strip() and not r.strip().lower().startswith("conflicting:")
    ]


def _is_circular_belief(refs: list[str], circular_tokens: tuple[str, ...]) -> bool:
    """A belief is circular when every one of its origins is a project-intent ref."""
    if not refs:
        return False
    if all(_is_circular_ref(r, circular_tokens) for r in refs if r.strip()):
        return True
    if not any(_is_circular_ref(r, circular_tokens) for r in refs):
        return False
    # Prose refs aside, all compact origins are circular.
    compact = [r for r in refs if r.strip() and " " not in r]
    return bool(compact) and all(_is_circular_ref(r, circular_tokens) for r in compact)


def build_quality_scorecard(
    *,
    expert_name: str,
    domain: str,
    beliefs: list[Any],
    open_gap_count: int = 0,
    verified_learning_loops: int = 0,
    circular_tokens: tuple[str, ...] = _DEFAULT_CIRCULAR_TOKENS,
) -> ExpertQualityScorecard:
    """Build a scorecard from belief objects (Belief or duck-typed)."""
    trust_mix: Counter[str] = Counter()
    eff_scores: list[float] = []
    multi = 0
    circular = 0
    secondary_or_better = 0
    global_origins: set[str] = set()

    for belief in beliefs:
        trust = _belief_trust_class(belief)
        trust_mix[trust] += 1
        if trust in {"primary", "secondary"}:
            secondary_or_better += 1

        eff_scores.append(_belief_effective_confidence(belief))

        refs = _belief_refs(belief)
        if _belief_independent_source_count(belief, refs) >= 2:
            multi += 1

        global_origins.update(token.lower() for token in _compact_refs(refs))
        if _is_circular_belief(refs, circular_tokens):
            circular += 1

    n = len(beliefs)
    multi_share = (multi / n) if n else 0.0
    circ_risk = (circular / n) if n else 1.0
    sob_share = (secondary_or_better / n) if n else 0.0
    origin_count = len(global_origins)

    eff_summary = {
        "min": round(min(eff_scores), 3) if eff_scores else 0.0,
        "avg": round(sum(eff_scores) / len(eff_scores), 3) if eff_scores else 0.0,
        "max": round(max(eff_scores), 3) if eff_scores else 0.0,
    }

    grade, blockers, strengths = _grade(
        claim_count=n,
        secondary_or_better_share=sob_share,
        multi_source_share=multi_share,
        circularity_risk=circ_risk,
        verified_learning_loops=verified_learning_loops,
    )

    stage = _stage_hint(
        claim_count=n,
        has_blockers=bool(blockers),
        verified_learning_loops=verified_learning_loops,
    )
    actions = _next_actions(
        expert_name=expert_name,
        claim_count=n,
        circularity_risk=circ_risk,
        secondary_or_better_share=sob_share,
        multi_source_share=multi_share,
        open_gap_count=int(open_gap_count),
        verified_learning_loops=int(verified_learning_loops),
    )

    return ExpertQualityScorecard(
        expert_name=expert_name,
        domain=domain,
        claim_count=n,
        trust_mix=dict(trust_mix),
        effective_confidence=eff_summary,
        multi_source_share=round(multi_share, 3),
        multi_source_count=multi,
        distinct_origin_count=origin_count,
        circularity_risk=round(circ_risk, 3),
        circular_claim_count=circular,
        secondary_or_better_share=round(sob_share, 3),
        open_gap_count=int(open_gap_count),
        verified_learning_loops=int(verified_learning_loops),
        stage_hint=stage,
        grade=grade,
        blockers=blockers,
        strengths=strengths,
        next_actions=actions,
    )


def _stage_hint(*, claim_count: int, has_blockers: bool, verified_learning_loops: int) -> str:
    if claim_count == 0:
        return "foundation"
    if has_blockers:
        return "improve"
    if verified_learning_loops == 0:
        return "learning"
    return "exceptional_path"


def _next_actions(
    *,
    expert_name: str,
    claim_count: int,
    circularity_risk: float,
    secondary_or_better_share: float,
    multi_source_share: float,
    open_gap_count: int,
    verified_learning_loops: int,
) -> list[dict[str, Any]]:
    """Ordered structural next steps. Never a semantic verdict on the expert."""
    n = claim_count
    circ_risk = circularity_risk
    sob_share = secondary_or_better_share
    multi_share = multi_source_share

    actions: list[dict[str, Any]] = []
    if circ_risk > 0.35 or sob_share < 0.5:
        actions.append(
            {
                "id": "absorb_primary_secondary",
                "title": "Absorb independent official docs as secondary",
                "reason": "Reduce circularity and tertiary-only caps with real domain sources.",
                "command_argv": [
                    [
                        "deepr",
                        "expert",
                        "absorb",
                        expert_name,
                        "--file",
                        "<official-or-primary-doc.md>",
                        "--local",
                        "--trust-class",
                        "secondary",
                        "-y",
                    ]
                ],
            }
        )
    if multi_share < 0.15 and n >= 10:
        actions.append(
            {
                "id": "deepen_plan_distill",
                "title": "Run Distill deepen plan then absorb secondary insights",
                "reason": "Multi-source provenance needs independent corpus origins (Distill library).",
                "command_argv": [
                    ["deepr", "expert", "deepen-plan", expert_name],
                    [
                        "deepr",
                        "expert",
                        "absorb",
                        expert_name,
                        "--file",
                        "<distill-library-insight.md>",
                        "--local",
                        "--trust-class",
                        "secondary",
                        "-y",
                    ],
                ],
            }
        )
    if open_gap_count == 0 and n >= 10:
        actions.append(
            {
                "id": "discover_gaps",
                "title": "Discover gaps (false-healthy inventory)",
                "reason": "Zero open gaps with a thin or circular store often means discovery never ran.",
                "command_argv": [["deepr", "expert", "discover-gaps", expert_name]],
            }
        )
    if verified_learning_loops == 0:
        actions.append(
            {
                "id": "close_learning_loop",
                "title": "Run a measured improve cycle",
                "reason": "No verifier-passed learning loop yet - expert has inventory but no improvement proof.",
                "command_argv": [
                    ["deepr", "expert", "route-gaps", expert_name, "--execute", "--local", "--dry-run"],
                    ["deepr", "expert", "sync", expert_name, "--local", "--dry-run"],
                ],
            }
        )

    return actions
