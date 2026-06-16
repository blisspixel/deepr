"""Gap-to-tool routing: map a knowledge gap to the best instrument to fill it.

ROADMAP Phase 4 "dynamic tool selection via gap analysis". Each instrument owns
a cognitive niche:

- recon (infrastructure / email-security / tech-stack) - free, passive
- distillr (academic / literature / corpus synthesis) - paid ingestion
- primr (strategic company deep-dives) - paid, long-running
- general deep research - the default when no specialist fits

``GapRouter`` is read-side and cost-$0: it classifies each gap by keyword
signal, picks the highest-scoring available instrument (falling back to general
research when the specialist is not installed), and returns a route with a
rationale and a cost estimate. It advises; it does not execute the fill. The
output feeds both a human preview and the future autonomous fill loop.

Instrument availability mirrors deepr.mcp.client.config_loader.discover_*: the
binary names (recon / distill-mcp / primr-mcp) are the source of truth there.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deepr.core.contracts import Gap

# Instrument identifiers.
RECON = "recon"
DISTILLR = "distillr"
PRIMR = "primr"
RESEARCH = "research"  # general deep research; always available, the default

# Binary that signals each specialist instrument is installed (see
# config_loader.discover_*). RESEARCH has no binary - it is always available.
_INSTRUMENT_BINARY = {RECON: "recon", DISTILLR: "distill-mcp", PRIMR: "primr-mcp"}

# Characteristic cost when a gap carries no estimate of its own.
_INSTRUMENT_DEFAULT_COST = {RECON: 0.0, DISTILLR: 2.0, PRIMR: 5.0, RESEARCH: 0.5}

# Keyword signals per specialist instrument (lowercased, substring match).
_INSTRUMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    RECON: (
        "infrastructure",
        "tech stack",
        "tech-stack",
        "dns",
        "email security",
        "dmarc",
        "spf",
        "dkim",
        "tenant",
        "saas",
        "hosting",
        "posture",
        "exposure",
        "domain",
        "subdomain",
        "certificate",
    ),
    DISTILLR: (
        "paper",
        "papers",
        "academic",
        "literature",
        "arxiv",
        "study",
        "studies",
        "journal",
        "peer-review",
        "citation",
        "corpus",
        "documentation",
        "spec",
        "whitepaper",
    ),
    PRIMR: (
        "company",
        "competitor",
        "competitive",
        "hiring",
        "headcount",
        "strategy",
        "strategic",
        "positioning",
        "go-to-market",
        "gtm",
        "funding",
        "revenue",
        "initiative",
        "leadership",
        "org chart",
        "market share",
    ),
}


@dataclass
class GapRoute:
    """A routing decision for one gap."""

    topic: str
    instrument: str
    available: bool
    estimated_cost: float
    rationale: str
    suggestion: str
    priority: int = 3
    ev_cost_ratio: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "instrument": self.instrument,
            "available": self.available,
            "estimated_cost": round(self.estimated_cost, 2),
            "rationale": self.rationale,
            "suggestion": self.suggestion,
            "priority": self.priority,
            "ev_cost_ratio": round(self.ev_cost_ratio, 3),
            "matched_keywords": self.matched_keywords,
        }


class GapRouter:
    """Route knowledge gaps to the instrument best suited to fill each."""

    def __init__(self, available: dict[str, bool] | None = None) -> None:
        """Create a router.

        Args:
            available: Optional override of instrument availability (tests pass
                this). When omitted, availability is detected via ``shutil.which``
                on each specialist's binary; general research is always available.
        """
        if available is None:
            available = {inst: shutil.which(binary) is not None for inst, binary in _INSTRUMENT_BINARY.items()}
        self.available = {**available, RESEARCH: True}

    @staticmethod
    def classify(topic: str, questions: list[str] | None = None) -> tuple[str, list[str]]:
        """Pick the best-fit specialist by keyword signal.

        Returns (instrument, matched_keywords). Falls back to RESEARCH when no
        specialist keyword matches. On a tie, the higher-signal (more matches)
        instrument wins; ties beyond that resolve recon < distillr < primr by
        iteration order, which is acceptable for an advisory router.
        """
        text = " ".join([topic, *(questions or [])]).lower()
        best_instrument = RESEARCH
        best_matches: list[str] = []
        for instrument, keywords in _INSTRUMENT_KEYWORDS.items():
            matches = [kw for kw in keywords if kw in text]
            if len(matches) > len(best_matches):
                best_instrument = instrument
                best_matches = matches
        return best_instrument, best_matches

    def route_gap(self, gap: Gap) -> GapRoute:
        """Route a single gap to an instrument."""
        instrument, matched = self.classify(gap.topic, gap.questions)
        available = self.available.get(instrument, False)

        # Specialist chosen but not installed -> fall back to general research,
        # and say how to unlock the specialist.
        if instrument != RESEARCH and not available:
            binary = _INSTRUMENT_BINARY[instrument]
            pip_name = {"distill-mcp": "distillr", "primr-mcp": "primr", "recon": "recon-tool"}[binary]
            rationale = (
                f"Best fit is {instrument} (matched: {', '.join(matched)}), but it is not installed. "
                f"Install with `pip install {pip_name}` to route here; using general research meanwhile."
            )
            cost = gap.estimated_cost or _INSTRUMENT_DEFAULT_COST[RESEARCH]
            return GapRoute(
                topic=gap.topic,
                instrument=RESEARCH,
                available=True,
                estimated_cost=cost,
                rationale=rationale,
                suggestion=f'deepr research "{gap.topic}" --auto --budget {cost:.2f}',
                priority=gap.priority,
                ev_cost_ratio=gap.ev_cost_ratio,
                matched_keywords=matched,
            )

        cost = gap.estimated_cost or _INSTRUMENT_DEFAULT_COST[instrument]
        rationale = (
            f"Matched {instrument} signals: {', '.join(matched)}."
            if matched
            else "No specialist signal; general deep research is the safe default."
        )
        return GapRoute(
            topic=gap.topic,
            instrument=instrument,
            available=True,
            estimated_cost=cost,
            rationale=rationale,
            suggestion=self._suggestion(instrument, gap.topic, cost),
            priority=gap.priority,
            ev_cost_ratio=gap.ev_cost_ratio,
            matched_keywords=matched,
        )

    def route(self, gaps: list[Gap]) -> list[GapRoute]:
        """Route a list of gaps, highest expected-value-per-cost first."""
        ordered = sorted(gaps, key=lambda g: g.ev_cost_ratio, reverse=True)
        return [self.route_gap(g) for g in ordered]

    @staticmethod
    def _suggestion(instrument: str, topic: str, cost: float) -> str:
        """An actionable next step for the chosen instrument."""
        if instrument == RESEARCH:
            return f'deepr research "{topic}" --auto --budget {cost:.2f}'
        if instrument == RECON:
            return "Consult recon (free): mention the company domain in `deepr expert chat`, or call the recon skill."
        if instrument == DISTILLR:
            return f"Ingest sources via the distillr skill (`ingest_*` / `discover`), budget ~${cost:.2f}."
        if instrument == PRIMR:
            return f"Run a primr company deep-dive via the primr skill (`research_company`), budget ~${cost:.2f}."
        return f'deepr research "{topic}" --auto'
