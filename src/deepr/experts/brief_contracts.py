"""Typed shape of a consultable expert brief.

The notebook is what you read to learn a subject. The brief is what makes a
two-minute conversation with an expert worth having: where the field stands,
which part of your question is already settled, what the expert thinks and why,
and what would change their mind.

A brief is derived from study findings and the retained corpus. It is not a
summary of them. Summarizing is the low-utility operation; what makes an expert
useful is that they have *landed somewhere* and can say why, and can tell you
what they are not sure about without embarrassment.

Two rules the types enforce structurally rather than by convention:

1. **A position carries its own falsifier.** A stance without a stated
   observation that would overturn it is not a judgment, it is an assertion.
   ``Position`` cannot be constructed usefully without ``would_change_my_mind``.
2. **Dissent survives.** Disagreement between lenses is recorded as unresolved
   rather than averaged into a confident-sounding middle. Every intelligence
   post-mortem examined found the correct answer had been present and was
   smoothed away; a brief that reads confident because it dropped the
   disagreement reproduces exactly that.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

BRIEF_SCHEMA_VERSION = "deepr-expert-brief-v1"


@dataclass
class Position:
    """Where the expert lands on one question, and what would move it."""

    question: str
    stance: str
    reasoning: str
    would_change_my_mind: str
    """The observation that would overturn this. Empty makes the position invalid."""
    supported_by: list[str] = field(default_factory=list)
    """Finding titles this rests on, so 'why do you think that' is answerable."""
    unresolved_dissent: str = ""
    """Disagreement this position does not settle, stated rather than smoothed."""
    confidence_basis: str = ""
    """What the confidence rests on: source count, independence, agreement."""

    @property
    def is_falsifiable(self) -> bool:
        return bool(self.would_change_my_mind.strip())

    @property
    def is_grounded(self) -> bool:
        return bool(self.supported_by)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_falsifiable"] = self.is_falsifiable
        data["is_grounded"] = self.is_grounded
        return data


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

    def integrity_warnings(self) -> list[str]:
        """Structural problems a reader must see. Never a verdict on correctness."""
        warnings: list[str] = []
        if self.unfalsifiable_positions:
            warnings.append(
                f"{len(self.unfalsifiable_positions)} position(s) state no observation that would "
                "overturn them. An unfalsifiable position is an assertion, not a judgment."
            )
        if self.ungrounded_positions:
            warnings.append(
                f"{len(self.ungrounded_positions)} position(s) cite no supporting finding, so "
                "'why do you think that' cannot be answered from the record."
            )
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
        return warnings

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "expert": self.expert_name,
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
