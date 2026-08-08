"""Which experts are worth consulting, and what the rest need.

A fleet of forty is not inspectable by opening forty directories. The signals
that decide whether an expert is worth asking already exist - independent
origin count, cross-source findings, grounded ratio, whether a brief was ever
formed, how old the reading is - and nothing collects them.

A grade is a triage device, not a verdict. It exists so a person with forty
experts can find the three that need work, and it is paired with the specific
next action every time, because "grade C" tells you nothing you can act on and
"no corpus; run acquire" does.

Two deliberate choices about how it grades.

**Depth is counted by origin, not by document.** Thirty pages from one
publisher is one publisher's authority. An expert can look substantial by
document count and be a single source wearing thirty hats, which is the
measurement error every corroboration number downstream inherits.

**A missing brief caps the grade regardless of everything else.** An expert
with a large corpus and no formed view is a search index. It may be a very
good search index, and the grade should not imply it is a consultable expert,
because the whole difference is whether it has landed anywhere.

**Certainty lowers the grade rather than raising it.** An expert holding no
unresolved dissent, naming no open questions and having never changed its mind
is not a finished expert; it is a closed one. A full cup has no room, and an
expert that believes it has the subject has stopped being able to learn it -
which is the moment it stops being worth consulting, whatever its corpus looks
like.

**S is all four at once, and deliberately hard to reach.** Deep and
independently sourced, current, holding a perspective of its own rather than a
pile of facts, and still actively wanting to know more. Anything short of all
four is not S. Most experts should sit below it, including good ones: a grade
most things reach measures nothing, and the top of this ladder exists to
describe something worth aiming at rather than to hand out praise.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HEALTH_SCHEMA_VERSION = "deepr-expert-health-v1"

_STALE_DAYS = 90
"""Beyond this a reading is old enough to mention. Deliberately not a cliff:
staleness rate varies by subject far more than any single number admits."""

_CURRENT_DAYS = 30
"""Read within a month. S claims to be up to date, so it has to have looked."""

_THIN_ORIGINS = 2.0
_GOOD_ORIGINS = 5.0


@dataclass
class ExpertHealth:
    """What one expert holds, and the single most useful thing to do next."""

    name: str
    schema_version: str = HEALTH_SCHEMA_VERSION

    beliefs: int = 0
    sources: int = 0
    effective_origins: float = 0.0
    findings: int = 0
    grounded_findings: int = 0
    cross_source_findings: int = 0
    positions: int = 0
    falsifiable_positions: int = 0
    positions_with_dissent: int = 0
    """Positions that record something they did not resolve."""
    open_questions: int = 0
    """What the expert says it is still working on, from its own profile."""
    known_weaknesses: int = 0
    mind_changes: int = 0
    """Recorded shifts in standpoint. Never revised is never tested."""
    standpoint: str = ""
    """The expert's own reading of the subject, from its profile card."""
    cards: int = 0
    age_days: int = -1
    """Days since the study was last run. -1 when never."""

    integrity_warnings: list[str] = field(default_factory=list)

    @property
    def is_studied(self) -> bool:
        return self.findings > 0

    @property
    def is_consultable(self) -> bool:
        """A formed view, resting on something that can be checked."""
        return self.positions > 0 and self.grounded_findings > 0

    @property
    def grounded_ratio(self) -> float:
        return round(self.grounded_findings / self.findings, 2) if self.findings else 0.0

    @property
    def is_stale(self) -> bool:
        return self.age_days > _STALE_DAYS

    @property
    def is_open(self) -> bool:
        """Whether the expert has left itself any room.

        Any one of: something it could not resolve, a question it is still
        working on, or a weakness it names. An expert with none of the three
        is closed, and a closed expert cannot learn the thing it claims to
        know.
        """
        return bool(self.positions_with_dissent or self.open_questions or self.known_weaknesses)

    @property
    def is_hungry(self) -> bool:
        """Not merely open, but actively wanting more.

        Stronger than ``is_open``: the expert names questions it is pursuing
        *and* admits where it is weak. Leaving a gap unstated is not the same
        as going after it.
        """
        return bool(self.open_questions and self.known_weaknesses)

    @property
    def has_perspective(self) -> bool:
        """Holds a reading of the subject, not only findings about it.

        The difference between an expert and an index. Comes from the profile
        card, which is the expert's own account of how it reads the subject.
        """
        return bool(self.standpoint.strip())

    @property
    def is_current(self) -> bool:
        return 0 <= self.age_days <= _CURRENT_DAYS

    @property
    def grade(self) -> str:
        """A triage letter. Always read with ``next_action``.

        A missing brief caps at C however deep the corpus, because an expert
        that has not landed anywhere is a search index and should not grade as
        a consultable expert.
        """
        if not self.sources and not self.beliefs:
            return "F"
        if not self.sources:
            return "D"
        if not self.is_studied:
            return "C"
        if not self.is_consultable:
            return "C"
        if self.effective_origins < _THIN_ORIGINS or self.grounded_ratio < 0.5:
            return "B"
        if not self.is_open:
            # A closed expert cannot climb however good its corpus. Certainty
            # across the board is not mastery of a subject; it is the point at
            # which one stops learning it.
            return "B"

        deep = self.effective_origins >= _GOOD_ORIGINS and self.cross_source_findings > 0
        if deep and self.is_current and self.has_perspective and self.is_hungry:
            return "S"
        if deep and not self.is_stale:
            return "A"
        return "B"

    def _next_action_checks(self) -> list[tuple[bool, str]]:
        """Every reason an expert might need work, worst first.

        A list rather than a chain so the priority order is visible and can be
        argued with. The first true one wins, because handing someone five
        things to do is the same as handing them none.
        """
        unfalsifiable = self.positions - self.falsifiable_positions
        missing = "no open questions" if not self.open_questions else "nothing it is weak on"
        return [
            (not self.sources and not self.beliefs, "Empty. Give it a subject and run acquire."),
            (
                not self.sources,
                f"{self.beliefs} claim(s) but no retained corpus, so nothing can be re-read or checked. Run acquire.",
            ),
            (not self.is_studied, f"{self.sources} source(s) retained and never read. Run study."),
            (
                not self.positions,
                "Studied but never briefed, so it reports findings and holds no view. Run brief.",
            ),
            (
                self.grounded_ratio < 0.5,
                f"Only {self.grounded_ratio:.0%} of findings are verifiable against the corpus. "
                "Re-study before trusting it.",
            ),
            (
                self.effective_origins < _THIN_ORIGINS,
                f"{self.sources} source(s) collapse to {self.effective_origins:.1f} independent "
                "origin(s), so agreement here is one publisher agreeing with itself. Acquire "
                "from elsewhere.",
            ),
            (
                self.cross_source_findings == 0 and self.findings > 1,
                "No finding draws on more than one source, so nothing here compares sources. Re-study.",
            ),
            (
                not self.is_open,
                "Holds no unresolved dissent, no open questions and names no weakness. That is "
                "possible, and it is also what an expert looks like once it has stopped looking. "
                "Check the contention findings the brief did not carry forward.",
            ),
            (
                unfalsifiable > 0,
                f"{unfalsifiable} position(s) state nothing that would overturn them. Re-brief.",
            ),
            (
                not self.has_perspective,
                "Holds positions but no reading of its own, so it reports what its sources say "
                "without a standpoint. Run profile.",
            ),
            (
                not self.is_hungry,
                f"Consultable, but names {missing}. An expert still learning knows both. Run profile.",
            ),
            (
                not self.is_current,
                f"Strong, but last read {self.age_days} days ago. Re-acquire to reach S.",
            ),
        ]

    @property
    def next_action(self) -> str:
        """The one thing most worth doing. A grade without this is not usable."""
        for failing, message in self._next_action_checks():
            if failing:
                return message
        return "S tier. Deep, current, holds a perspective, and still looking."

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            grade=self.grade,
            next_action=self.next_action,
            is_consultable=self.is_consultable,
            grounded_ratio=self.grounded_ratio,
            is_stale=self.is_stale,
            is_open=self.is_open,
            is_hungry=self.is_hungry,
            has_perspective=self.has_perspective,
            is_current=self.is_current,
        )
        return data


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def _age_days(started_at: str, *, now: datetime | None = None) -> int:
    if not started_at:
        return -1
    try:
        when = datetime.fromisoformat(started_at)
    except ValueError:
        return -1
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0, ((now or datetime.now(UTC)) - when).days)


def assess_expert(name: str, expert_dir: Path, *, beliefs: int = 0, now: datetime | None = None) -> ExpertHealth:
    """Read what is on disk for one expert. No model call, no network."""
    health = ExpertHealth(name=name, beliefs=beliefs)

    study = _load_json(expert_dir / "study.json")
    if study:
        totals = study.get("totals") or {}
        health.findings = int(totals.get("findings", 0) or 0)
        health.grounded_findings = int(totals.get("grounded_findings", 0) or 0)
        health.cross_source_findings = int(totals.get("cross_source_findings", 0) or 0)
        health.age_days = _age_days(study.get("started_at", ""), now=now)
        independence = study.get("independence") or {}
        health.sources = int(independence.get("source_count", 0) or 0)
        health.effective_origins = float(independence.get("effective_source_count", 0.0) or 0.0)

    if not health.sources:
        index = expert_dir / "corpus" / "index.jsonl"
        if index.exists():
            try:
                lines = [line for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
                health.sources = len(lines)
            except OSError:
                pass

    brief = _load_json(expert_dir / "brief.json")
    if brief:
        positions = brief.get("positions") or []
        health.positions = len(positions)
        health.falsifiable_positions = sum(1 for p in positions if p.get("is_falsifiable"))
        health.positions_with_dissent = sum(1 for p in positions if (p.get("unresolved_dissent") or "").strip())
        health.integrity_warnings = list(brief.get("integrity_warnings") or [])
        state = brief.get("state") or {}
        health.open_questions = len(state.get("unknown") or []) + len(state.get("live") or [])

    profile = _load_json(expert_dir / "profile_card.json")
    if profile:
        health.standpoint = profile.get("standpoint", "")
        health.open_questions += len(profile.get("open_questions") or [])
        health.known_weaknesses = len(profile.get("where_it_is_weak") or [])
        health.mind_changes = len(profile.get("shifts") or [])

    cards = expert_dir / "cards"
    if cards.is_dir():
        health.cards = len(list(cards.glob("*.json")))

    return health


def fleet_summary(fleet: list[ExpertHealth]) -> dict[str, Any]:
    """Counts by grade, and how much of the fleet is actually consultable."""
    grades: dict[str, int] = {}
    for expert in fleet:
        grades[expert.grade] = grades.get(expert.grade, 0) + 1
    consultable = [e for e in fleet if e.is_consultable]
    return {
        "experts": len(fleet),
        "consultable": len(consultable),
        "by_grade": dict(sorted(grades.items())),
        "stale": sum(1 for e in fleet if e.is_stale),
        "never_studied": sum(1 for e in fleet if not e.is_studied),
        "closed": sum(1 for e in fleet if e.is_studied and not e.is_open),
        "s_tier": sum(1 for e in fleet if e.grade == "S"),
    }
