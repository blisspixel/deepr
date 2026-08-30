"""Typed shape of a consultable expert brief.

The notebook is what you read to learn a subject. The brief is what makes a
two-minute conversation with an expert worth having: where the field stands,
which part of your question is already settled, what the expert thinks and why,
and what would change their mind.

A brief is derived from study findings and the retained corpus. It is not a
summary of them. Summarizing is the low-utility operation; what makes an expert
useful is that they have *landed somewhere* and can say why, and can tell you
what they are not sure about without embarrassment.

Four rules the types enforce structurally rather than by convention:

1. **A position carries its own falsifier.** A stance without a stated
   observation that would overturn it is not a judgment, it is an assertion.
   ``Position`` cannot be constructed usefully without ``would_change_my_mind``.
2. **Dissent survives.** Disagreement between lenses is recorded as unresolved
   rather than averaged into a confident-sounding middle. Every intelligence
   post-mortem examined found the correct answer had been present and was
   smoothed away; a brief that reads confident because it dropped the
   disagreement reproduces exactly that.
3. **Likelihood and confidence are different quantities and never share a
   field.** How likely a claim is to be true, and how sound the basis for that
   estimate is, move independently: a well-evidenced claim can be a coin flip,
   and a thinly-evidenced one can be near-certain. Analytic standards across
   intelligence, climate and clinical practice all require the split, and all
   three record harm from products that collapsed it.
4. **A position may decline to resolve.** ``resolution`` makes "these did not
   reconcile" a first-class answer, so the schema never forces a stance the
   evidence does not support. Without it, a required stance field guarantees
   invention whenever the findings genuinely conflict.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

BRIEF_SCHEMA_VERSION = "deepr-expert-brief-v2"

LIKELIHOOD_BANDS: dict[str, tuple[int, int]] = {
    "almost no chance": (1, 5),
    "very unlikely": (5, 20),
    "unlikely": (20, 45),
    "roughly even chance": (45, 55),
    "likely": (55, 80),
    "very likely": (80, 95),
    "almost certain": (95, 99),
}
"""Closed vocabulary for how likely a claim is. Rendered with its numbers.

Readers reconstruct these words wrong when the numbers live in a legend: given
a published glossary, they still read "very likely" as roughly 65-75% when the
author meant 90%+. So the band is printed inline, every time, not defined once.
"""

CONFIDENCE_LEVELS: tuple[str, ...] = ("high", "moderate", "low")
"""How sound the basis is: source quantity, independence, and agreement."""

RESOLUTIONS: tuple[str, ...] = ("single", "conditional", "irreducible")
"""single: one stance. conditional: stance depends on a stated assumption.
irreducible: the findings did not reconcile and the brief does not pretend."""

_VAGUE_FALSIFIER_RE = re.compile(
    r"\b(?:new (?:evidence|information|data|research|sources?)"
    r"|(?:the )?evidence (?:change|changes|changed|shift\w*|weaken\w*|improv\w*)"
    r"|further (?:study|studies|research|work|analysis)"
    r"|more (?:data|evidence|research|sources?)"
    r"|additional (?:data|evidence|research|sources?)"
    r"|better (?:data|evidence|understanding))\b",
    re.IGNORECASE,
)

_SPECIFICITY_RE = re.compile(
    r"\d"
    r"|\b(?:above|below|under|exceed\w*|fewer|greater|absent|missing|contradict\w*"
    r"|replicat\w*|measur\w*|publish\w*|reverse\w*|trial|dataset|benchmark|audit"
    r"|log|logs|incident|retract\w*|withdraw\w*)\b",
    re.IGNORECASE,
)


@dataclass
class Position:
    """Where the expert lands on one question, and what would move it."""

    question: str
    stance: str
    reasoning: str
    would_change_my_mind: str
    """The observation that would overturn this. Empty makes the position invalid."""
    supported_by: list[str] = field(default_factory=list)
    """Finding *ids* this rests on, so 'why do you think that' is answerable.

    Ids, not titles, and the distinction is load-bearing: titles collide,
    several lenses fall back to a constant when the model names nothing, and a
    title containing a newline can never be matched. This docstring said
    "titles" while the prompt and the citation filter both used ids - a stale
    comment stating the opposite of the code, which is how the next reader
    introduces a real bug.

    The ids are still positional (``{lens}-{ordinal}``), so they are stable
    within a run and not across runs. Making them content-derived is step one
    of the V2 work."""
    unresolved_dissent: str = ""
    """Disagreement this position does not settle, stated rather than smoothed."""
    confidence_basis: str = ""
    """What the confidence rests on: source count, independence, agreement."""
    likelihood: str = ""
    """How likely the stance is true. A term from LIKELIHOOD_BANDS, or empty."""
    confidence: str = ""
    """How sound the basis is. A term from CONFIDENCE_LEVELS, or empty."""
    resolution: str = "single"
    """single, conditional, or irreducible. See RESOLUTIONS."""
    supporting_documents: int = 0
    """Retained sources behind the cited findings."""
    distinct_roots: int = 0
    """Distinct publishers behind those sources. This is the number that counts."""
    falsifier_resolution_criterion: str = ""
    """The observable test used later to decide whether the falsifier fired."""
    falsifier_resolution_date: str = ""
    """The prospective ISO date on which the falsifier should next be checked."""

    @property
    def is_falsifiable(self) -> bool:
        return bool(self.would_change_my_mind.strip())

    @property
    def is_registered_prediction(self) -> bool:
        """Whether this position can be checked prospectively rather than in hindsight."""
        return bool(
            self.is_falsifiable
            and self.falsifier_resolution_criterion.strip()
            and self.falsifier_resolution_date.strip()
        )

    @property
    def is_grounded(self) -> bool:
        return bool(self.supported_by)

    @property
    def likelihood_band(self) -> tuple[int, int] | None:
        return LIKELIHOOD_BANDS.get(self.likelihood)

    @property
    def is_single_origin(self) -> bool:
        """Several sources, one publisher: apparent corroboration that is not.

        The documented shape behind more than one intelligence failure, where a
        judgment read as multiply-sourced and traced back to a single origin.
        """
        return self.distinct_roots == 1 and self.supporting_documents > 1

    @property
    def falsifier_is_decorative(self) -> bool:
        """True when the falsifier is a formula rather than an observation.

        Heuristic, and deliberately a warning rather than a rejection: it flags
        stated falsifiers that reach for "if new evidence emerges" without ever
        naming something that could be observed. A falsifier nobody could check
        cannot overturn anything, which makes it an immunisation strategy
        wearing the costume of rigour.
        """
        text = self.would_change_my_mind
        if not text.strip():
            return False
        return bool(_VAGUE_FALSIFIER_RE.search(text)) and not _SPECIFICITY_RE.search(text)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_falsifiable"] = self.is_falsifiable
        data["is_registered_prediction"] = self.is_registered_prediction
        data["is_grounded"] = self.is_grounded
        data["is_single_origin"] = self.is_single_origin
        data["likelihood_band"] = list(self.likelihood_band) if self.likelihood_band else None
        return data


def _position_from(data: dict[str, Any]) -> Position:
    """One position back from its persisted form, calibration intact."""
    return Position(
        question=data.get("question", ""),
        stance=data.get("stance", ""),
        reasoning=data.get("reasoning", ""),
        would_change_my_mind=data.get("would_change_my_mind", ""),
        falsifier_resolution_criterion=data.get("falsifier_resolution_criterion", ""),
        falsifier_resolution_date=data.get("falsifier_resolution_date", ""),
        supported_by=list(data.get("supported_by") or []),
        unresolved_dissent=data.get("unresolved_dissent", ""),
        confidence_basis=data.get("confidence_basis", ""),
        likelihood=data.get("likelihood", ""),
        confidence=data.get("confidence", ""),
        resolution=data.get("resolution", "single"),
        supporting_documents=int(data.get("supporting_documents", 0) or 0),
        distinct_roots=int(data.get("distinct_roots", 0) or 0),
    )


@dataclass
class AnticipatedQuestion:
    """A question the expert expects, with the answer already prepared.

    The highest-value thing a briefer carries: the naive version of the question
    has been asked a hundred times and has a crisp reply, so the conversation
    starts past it.
    """

    question: str
    answer: str
    why_asked: str = ""
    """What makes people ask this - often a common misconception worth naming."""
    supported_by: list[str] = field(default_factory=list)
    weakens_thesis: bool = False
    """True when the honest answer costs the brief something.

    A question set is only preparation if at least one entry attacks. Questions
    generated by turning the brief's own assertions interrogative are always
    answerable, always on-thesis, and worthless.
    """

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SettledState:
    """What is resolved, what is live, and what is genuinely unknown.

    Separating these is most of an expert's value in the first minute: it stops
    the conversation spending time on questions the field closed years ago.
    """

    settled: list[str] = field(default_factory=list)
    live: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceCredibility:
    """How much independent weight the corpus actually carries.

    Citation count is not evidential depth. Intelligence post-mortems found
    products that left readers with "an impression of many corroborating reports
    where in fact there were very few sources", and a corpus of secondary
    coverage reproduces that by default.
    """

    origin: str
    source_count: int = 0
    trust_class: str = ""
    note: str = ""
    """What this origin is reliable for, or what interest it may have."""
    is_sole_root: bool = False
    """True when several sources here trace to one publisher."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExpertBrief:
    """The consultable artifact. Derived, regenerable, and citation-bearing."""

    expert_name: str
    schema_version: str = BRIEF_SCHEMA_VERSION
    orientation: str = ""
    """The sixty-second version. What a newcomer needs before asking anything."""
    positions: list[Position] = field(default_factory=list)
    state: SettledState = field(default_factory=SettledState)
    key_quantities: list[str] = field(default_factory=list)
    anticipated_questions: list[AnticipatedQuestion] = field(default_factory=list)
    common_failures: list[str] = field(default_factory=list)
    """What people try first that does not work."""
    credibility: list[SourceCredibility] = field(default_factory=list)
    finding_titles: dict[str, str] = field(default_factory=dict)
    """Cited finding id to its title, so the render can show words not handles."""
    limitations: list[str] = field(default_factory=list)
    generated_from_findings: int = 0
    cost_usd: float = 0.0

    @property
    def unfalsifiable_positions(self) -> list[Position]:
        """Positions with no stated falsifier. These are assertions, not judgments."""
        return [p for p in self.positions if not p.is_falsifiable]

    @property
    def ungrounded_positions(self) -> list[Position]:
        return [p for p in self.positions if not p.is_grounded]

    def _position_warnings(self) -> list[str]:
        """Problems with individual positions, counted rather than enumerated."""
        checks = (
            (
                self.unfalsifiable_positions,
                "state no observation that would overturn them. An unfalsifiable position is an "
                "assertion, not a judgment.",
            ),
            (
                self.ungrounded_positions,
                "cite no supporting finding, so 'why do you think that' cannot be answered from the record.",
            ),
            (
                [p for p in self.positions if p.falsifier_is_decorative],
                "state a falsifier that names nothing observable. 'If new evidence emerges' cannot "
                "be checked, so it cannot overturn anything.",
            ),
            (
                [p for p in self.positions if p.is_single_origin],
                "rest on several sources that trace to a single publisher. That reads as corroboration and is not.",
            ),
            (
                [p for p in self.positions if p.stance and not p.likelihood],
                "state a stance with no likelihood. A stance with no stated likelihood cannot be "
                "scored later, and so was never a judgment.",
            ),
            (
                [p for p in self.positions if p.resolution == "irreducible" and not p.unresolved_dissent],
                "are marked irreducible but record no disagreement, which is a contradiction: "
                "something must have failed to reconcile.",
            ),
        )
        return [f"{len(group)} position(s) {message}" for group, message in checks if group]

    def integrity_warnings(self) -> list[str]:
        """Structural problems a reader must see. Never a verdict on correctness."""
        warnings = self._position_warnings()
        sole_roots = [c for c in self.credibility if c.is_sole_root]
        if sole_roots:
            warnings.append(
                f"{len(sole_roots)} origin(s) supply several sources each. Repetition within one "
                "publisher is not independent corroboration."
            )
        if self.positions and not any(p.unresolved_dissent for p in self.positions):
            warnings.append(
                "No position records unresolved dissent. That is possible, and it is also what a "
                "brief looks like when disagreement has been averaged away; check the study "
                "findings for contention the brief did not carry forward."
            )
        if self.anticipated_questions and not any(q.weakens_thesis for q in self.anticipated_questions):
            warnings.append(
                "No anticipated question weakens the brief's own position. A question set where "
                "every answer reinforces the thesis is marketing, not preparation."
            )
        return warnings

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpertBrief:
        """Rebuild a brief from its persisted form, so it can be consulted."""
        state = data.get("state") or {}
        brief = cls(
            expert_name=data.get("expert", ""),
            schema_version=data.get("schema_version", BRIEF_SCHEMA_VERSION),
            orientation=data.get("orientation", ""),
            state=SettledState(
                settled=list(state.get("settled") or []),
                live=list(state.get("live") or []),
                unknown=list(state.get("unknown") or []),
            ),
            key_quantities=list(data.get("key_quantities") or []),
            common_failures=list(data.get("common_failures") or []),
            finding_titles=dict(data.get("finding_titles") or {}),
            limitations=list(data.get("limitations") or []),
            generated_from_findings=int(data.get("generated_from_findings", 0) or 0),
        )
        brief.positions = [_position_from(p) for p in (data.get("positions") or []) if isinstance(p, dict)]
        brief.anticipated_questions = [
            AnticipatedQuestion(
                question=q.get("question", ""),
                answer=q.get("answer", ""),
                why_asked=q.get("why_asked", ""),
                supported_by=list(q.get("supported_by") or []),
                weakens_thesis=bool(q.get("weakens_thesis")),
            )
            for q in (data.get("anticipated_questions") or [])
            if isinstance(q, dict)
        ]
        brief.credibility = [
            SourceCredibility(
                origin=c.get("origin", ""),
                source_count=int(c.get("source_count", 0) or 0),
                trust_class=c.get("trust_class", ""),
                note=c.get("note", ""),
                is_sole_root=bool(c.get("is_sole_root")),
            )
            for c in (data.get("credibility") or [])
            if isinstance(c, dict)
        ]
        return brief

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "expert": self.expert_name,
            "finding_titles": self.finding_titles,
            "orientation": self.orientation,
            "positions": [p.to_dict() for p in self.positions],
            "state": self.state.to_dict(),
            "key_quantities": self.key_quantities,
            "anticipated_questions": [q.to_dict() for q in self.anticipated_questions],
            "common_failures": self.common_failures,
            "credibility": [c.to_dict() for c in self.credibility],
            "generated_from_findings": self.generated_from_findings,
            "cost_usd": self.cost_usd,
            "integrity_warnings": self.integrity_warnings(),
            "limitations": self.limitations,
        }
