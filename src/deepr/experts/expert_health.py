"""Which experts are worth consulting, and what the rest need.

A fleet of forty is not inspectable by opening forty directories. The signals
that decide whether an expert is worth asking already exist - independent
origin count, cross-source findings, grounded ratio, whether a brief was ever
formed, how old the reading is - and nothing collects them.

**This is artifact hygiene, not quality, and the distinction is the whole
point.** It answers questions a directory listing can answer: is there a
retained corpus, did anything read it, did the reading land anywhere, is the
corpus one publisher wearing several hats, are the claims traceable to a
passage. It cannot tell anyone whether an expert is worth talking to. A corpus
of five mutually-agreeing bad sources scores exactly like five good ones,
because nothing here has an opinion about whether the material was any good.

So it is a maintenance queue, not a ranking of minds. With fifty experts,
"which three need work and what do they need" is a real question with a cheap
answer, and every grade ships with one next action for that reason. Whether an
expert actually knows anything is a different question, answered by a test
built for that subject from that subject's own corpus - holding a source back
and seeing if the expert predicts it, asking what the material genuinely does
not cover, asking about something that does not exist. Those produce evidence
about one expert on one subject. They do not produce a letter, and the letter
should not pretend to stand in for them.

Two deliberate choices about how it grades.

**Depth is breadth plus concentration, not entropy.** Thirty pages from one
publisher is one publisher's authority, so documents are the wrong unit. But
effective source count - exp of the share entropy - is the wrong gate, because
it rewards *uniformity*: five publishers with one document each scores 5.0,
while the same five publishers with twenty documents from the most
authoritative one scores 1.98 and is told to go find other sources. The second
corpus is strictly better and the metric says to delete fifteen documents.

So the gate is ``origin_count`` (monotone in acquisition, so reading more can
never hurt) together with ``dominant_share`` (which catches the one-publisher
case the entropy measure was reached for). Effective source count stays where
it belongs, in the warning text, describing concentration rather than gating
on it.

**A missing brief caps the grade regardless of everything else.** An expert
with a large corpus and no formed view is a search index. It may be a very
good search index, and the grade should not imply it is a consultable expert,
because the whole difference is whether it has landed anywhere.

**Dropping real disagreement lowers the grade; declared certainty does not.**
The full-cup instinct is sound and the obvious way to measure it is wrong.
Asking an expert to declare its open questions and weaknesses grades a
self-report against a rubric it can read, and a frozen specification has no
live dissent to declare - manufacturing some there would be worse than
reporting none. So the penalty attaches to one checkable comparison instead:
the contention lens found disagreement in the corpus and the brief carried
none of it into a position. That is disagreement being averaged away, and it
is a claim about two artifacts rather than about a personality.

**The ladder is a progression, not a lattice.** It reads in one direction and
each rung adds one thing:

| | |
|---|---|
| F | brand new. Nothing to go on. |
| D | claims, but no retained corpus, so nothing can be re-read or checked. |
| C | a corpus, and initial research done. Findings, no formed view yet. |
| B | briefed and consultable, and one of five things is wrong. |
| A | all five clear, and it holds a perspective. Not current, or not being used. |
| S | all of A, plus read in the last month, plus actually consulted in it. |

The five gates at B, and nothing else:

1. **A thin or captured corpus** - fewer than five publishers, or one supplying
   most of it.
2. **Findings that do not trace back** - and no path in the evidence graph from
   any position to a passage.
3. **A small or unrecorded model did the reading** - see ``model_tier``.
4. **No standpoint of its own** - positions without a reading is an index.
5. **Not current, or nobody uses it** - which separates A from S.

Deliberately dropped as gates, kept as warnings: cross-source findings,
contention carried forward, declared open questions, named weaknesses,
recorded mind changes, settled-claim counts. Each was an inference about
quality from a structural proxy, and every one of them can be satisfied by a
shallow reading as easily as a deep one. Which model did the reading predicts
more than all of them together, and is a fact rather than an inference.

The only difference between A and S is **liveness**. A is a good expert; S is a
good expert that is being used and is keeping up. That is deliberate, because
an expert nobody has asked anything in six months is not being maintained by
anything, and the grade should say so before somebody relies on it.

An earlier version of this ladder gated S on four independent properties at
once and every rung had its own escape hatches. It was harder to explain than
the thing it measured, which is the wrong trade for a triage letter.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.expert_layout import evidence_graph_in, part_in

HEALTH_SCHEMA_VERSION = "deepr-expert-health-v1"

_STALE_DAYS = 90
"""Beyond this a reading is old enough to mention. Deliberately not a cliff:
staleness rate varies by subject far more than any single number admits."""

_CURRENT_DAYS = 30
"""Read within a month. S claims to be up to date, so it has to have looked."""

_IN_USE_DAYS = 30
"""Consulted within a month. The A-to-S difference, and the only signal here
that records something happening outside the expert's own directory."""

_DOMINANT_SHARE = 0.6
"""One publisher above this share sets what the corpus can conclude."""

_GOOD_ORIGINS = 5
"""Distinct publishers for depth. Invented, and per-subject would be better:
for some fields three standards bodies are the entire universe."""

_EMPTY_ADMISSION = re.compile(
    r"^\W*(none|n/?a|not applicable|nothing|no\s+(?:unresolved\s+)?"
    r"(?:disagreement|dissent|weakness|conflict|contention)\w*)\b",
    re.IGNORECASE,
)
"""Text that admits nothing while occupying the field.

"None identified in the corpus." scored as recorded dissent, so the expert
that wrote a sentence saying there was none outranked the one that honestly
left it blank. The form of the confession was being graded, not its content,
and in the direction that made honesty the losing move."""


def admits_something(text: str) -> bool:
    """True when a field says something rather than filling itself."""
    cleaned = " ".join(str(text or "").split())
    return len(cleaned) > 12 and not _EMPTY_ADMISSION.match(cleaned)


@dataclass
class ExpertHealth:
    """What one expert holds, and the single most useful thing to do next."""

    name: str
    schema_version: str = HEALTH_SCHEMA_VERSION

    beliefs: int = 0
    sources: int = 0
    effective_origins: float = 0.0
    origin_count: int = 0
    """Distinct publishers. Monotone in acquisition, unlike effective origins."""
    dominant_share: float = 0.0
    """Share held by the largest publisher. This is what catches capture."""
    findings: int = 0
    grounded_findings: int = 0
    cross_source_findings: int = 0
    positions: int = 0
    falsifiable_positions: int = 0
    positions_with_dissent: int = 0
    """Positions that record something they did not resolve."""
    open_questions: int = 0
    """What the expert says it is still working on. Self-reported, so weak."""
    contention_findings: int = 0
    """Disagreement the contention lens actually found in the corpus.

    The behavioural half of the openness check. Compared against dissent the
    brief carried forward, it separates a subject with nothing to argue about
    from a brief that dropped what the lens found."""
    settled_claims: int = 0
    """How much the expert reports as closed. A genuinely settled subject
    produces a long settled list, which is the opposite of a short one with no
    live questions."""
    known_weaknesses: int = 0
    mind_changes: int = 0
    """Recorded shifts in standpoint. Never revised is never tested."""
    standpoint: str = ""
    """The expert's own reading of the subject, from its profile card."""
    cards: int = 0
    age_days: int = -1
    """Days since the study was last run. -1 when never."""
    graph_is_formed: bool = False
    """Whether a position reaches a source through a finding.

    Structural, and stronger than the ratio beside it. ``grounded_ratio``
    averages - a brief where half the findings anchor nowhere still scores 0.5
    and reads as middling. This asks whether the traversal exists at all:
    whether any claim connects to a passage someone can open. Read from the
    evidence graph, which is derived from artifacts already on disk, so it
    costs nothing and cannot disagree with them."""
    model_tier: str = "unknown"
    """The weakest model that read this corpus or wrote this standpoint.

    Weighted heavily, and deliberately so. A small local model and a frontier
    model reading the same corpus through the same lenses produce genuinely
    different experts, and no downstream statistic recovers the difference: a
    shallow finding is grounded, traceable and cross-source exactly as easily
    as a deep one, so every corroboration metric scores both alike.

    It is also the only signal on this record that is a fact rather than an
    inference. Everything else here infers quality from structure, and two of
    those inferences have already had to be withdrawn."""
    consulted_days_ago: int = -1
    """Days since anyone last asked this expert anything. -1 when never.

    The signal that separates A from S. Everything else on this record
    describes the artifact; this one is the only evidence that the artifact is
    load-bearing for somebody. An expert nobody has consulted in six months is
    not being maintained by anything, whatever its corpus looks like."""

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
    def subject_is_contested(self) -> bool:
        """Whether this corpus contains disagreement to be open about.

        Read from the contention lens rather than from the expert's own
        account of itself. A frozen specification legitimately produces none,
        and penalizing that penalizes correct calibration.
        """
        return self.contention_findings > 0

    @property
    def dropped_the_dissent(self) -> bool:
        """The lens found disagreement and the brief carried none forward.

        This is the closed *mind* as opposed to the closed *subject*, and it
        is a comparison between two artifacts rather than a self-report, which
        is why it carries more weight than anything the expert says about
        itself.
        """
        return self.subject_is_contested and self.positions > 0 and self.positions_with_dissent == 0

    @property
    def is_open(self) -> bool:
        """Whether the expert left itself room, judged against its subject.

        On a contested subject, carrying the disagreement forward is what
        counts, because it can be checked against the study. On an uncontested
        one a declared open question or named weakness is enough, and
        manufactured doubt is not required.
        """
        if self.dropped_the_dissent:
            return False
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
    def read_by_a_capable_model(self) -> bool:
        """Whether a mid-tier or better model did the reading.

        Unknown does not pass. An expert built before this was recorded, or by
        a model whose size cannot be read off its tag, has no evidence either
        way - and absence of evidence must not read as evidence of quality,
        which is the mistake that produced every withdrawn signal here.
        """
        from deepr.experts.model_provenance import TIER_MID, at_least

        return at_least(self.model_tier, TIER_MID)

    @property
    def is_in_use(self) -> bool:
        """Somebody has actually asked this expert something lately.

        Usage rather than quality, and that is the point: it is the one field
        here that no amount of careful artifact construction can fake, because
        it records something that happened outside the expert.
        """
        return 0 <= self.consulted_days_ago <= _IN_USE_DAYS

    @property
    def is_captured(self) -> bool:
        """One publisher supplies most of the corpus, or there is only one.

        Catches the case entropy was reached for without punishing an expert
        for reading a lot of the best source it has.
        """
        if self.origin_count <= 1:
            return bool(self.sources)
        return self.dominant_share >= _DOMINANT_SHARE

    @property
    def grade(self) -> str:
        """A triage letter. Always read with ``next_action``.

        One direction, one thing per rung. A missing brief caps at C however
        deep the corpus, because an expert that has not landed anywhere is a
        search index and should not grade as a consultable expert.
        """
        if not self.sources and not self.beliefs:
            return "F"
        if not self.sources:
            return "D"
        if not self.is_studied or not self.is_consultable:
            return "C"

        # Five gates, each wrong in a way more reading cannot fix.
        if self.is_captured or self.origin_count < _GOOD_ORIGINS:
            return "B"
        if self.grounded_ratio < 0.5 or not self.graph_is_formed:
            return "B"
        if not self.read_by_a_capable_model:
            return "B"
        if not self.has_perspective:
            return "B"

        if self.is_current and self.is_in_use:
            return "S"
        return "A"

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
                self.is_captured,
                f"{self.sources} source(s) across {self.origin_count} publisher(s), with "
                f"{self.dominant_share:.0%} from the largest. Agreement here is mostly one "
                "publisher agreeing with itself. Acquire from elsewhere.",
            ),
            (
                not self.graph_is_formed and self.positions > 0,
                "No position reaches a source through a finding, so no claim connects to a passage "
                "anyone can open. Run `expert graph` to see where the chain breaks.",
            ),
            (
                not self.read_by_a_capable_model,
                f"Read by a {self.model_tier} model. A small model and a frontier model reading the "
                "same corpus produce different experts, and no later statistic recovers the "
                "difference. Re-study on a plan backend.",
            ),
            (
                self.cross_source_findings == 0 and self.findings > 1,
                "No finding draws on more than one source, so nothing here compares sources. Re-study.",
            ),
            (
                self.dropped_the_dissent,
                f"The contention lens found {self.contention_findings} disagreement(s) in the "
                "corpus and the brief carried none of them into a position. That is the "
                "disagreement being averaged away, not a subject without any. Re-brief.",
            ),
            (
                not self.is_open,
                "Names no open question and no weakness, and the corpus shows no contention "
                "either. That may be a settled subject, in which case manufactured doubt would "
                "be worse. Run profile so the expert says which it is.",
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
            (
                not self.is_in_use,
                "Strong and current, but nobody has consulted it"
                + (" ever" if self.consulted_days_ago < 0 else f" in {self.consulted_days_ago} days")
                + ". Consult it, or retire it - an expert nothing asks is not being kept honest "
                "by anything.",
            ),
        ]

    @property
    def next_action(self) -> str:
        """The one thing most worth doing. A grade without this is not usable."""
        for failing, message in self._next_action_checks():
            if failing:
                return message
        return "S tier. Well researched, current, holds a perspective, and in use."

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
            is_in_use=self.is_in_use,
            read_by_a_capable_model=self.read_by_a_capable_model,
            is_captured=self.is_captured,
            subject_is_contested=self.subject_is_contested,
            dropped_the_dissent=self.dropped_the_dissent,
        )
        return data


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def _weakest_model_tier(study: dict[str, Any] | None, profile: dict[str, Any] | None) -> str:
    """The weakest model in this expert's chain, across the artifacts that stamp one.

    Study and profile only. The brief is written from findings the study
    produced, so it cannot be better than them; stamping it as well would add a
    third read of the same constraint without adding information.
    """
    from deepr.experts.model_provenance import ModelProvenance, record, weakest

    stamps: list[ModelProvenance] = []
    for source in (study, profile):
        data = source or {}
        if stamp := data.get("model_provenance"):
            stamps.append(ModelProvenance.from_dict(stamp))
            continue
        # Fall back to the older ``capacity_source`` field. Every study written
        # before the stamp existed still recorded which backend ran, and the
        # tier is derived from exactly that - so the whole existing fleet is
        # rankable without re-studying anything, which would have burned hours
        # of quota to recover information already sitting on disk.
        if legacy := data.get("capacity_source"):
            stamps.append(record(str(legacy), str(data.get("model") or "")))
    return weakest(stamps).tier


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


def last_consulted_days(*, now: datetime | None = None, limit: int = 500) -> dict[str, int]:
    """Days since each expert was last consulted, from the local trace store.

    One scan for a whole fleet rather than one per expert: the traces are a
    single append-only log, so assessing fifty experts individually would read
    the same file fifty times.

    An unreadable or missing trace store yields an empty mapping, which grades
    every expert as never-consulted. That is the right way to be wrong here -
    it says "no evidence anyone uses this", which is exactly what a missing
    log means.
    """
    try:
        from deepr.experts.consult_traces import load_consult_traces

        traces = load_consult_traces(limit=limit)
    except Exception:
        return {}

    seen: dict[str, int] = {}
    for trace in traces:
        days = _age_days(str(trace.get("recorded_at") or ""), now=now)
        if days < 0:
            continue
        # Both sides of the record, because they answer different questions.
        # `output.experts_consulted` is who actually spoke; `input.requested_
        # experts` is who was asked for. A consult that failed still means
        # somebody wanted this expert's view, which is the thing being
        # measured - "is anyone using it", not "did it succeed".
        names = list((trace.get("output") or {}).get("experts_consulted") or [])
        names += list((trace.get("input") or {}).get("requested_experts") or [])
        for expert_name in names:
            key = str(expert_name)
            if key not in seen or days < seen[key]:
                seen[key] = days
    return seen


def assess_expert(
    name: str,
    expert_dir: Path,
    *,
    beliefs: int = 0,
    now: datetime | None = None,
    consulted_days_ago: int = -1,
) -> ExpertHealth:
    """Read what is on disk for one expert. No model call, no network.

    ``consulted_days_ago`` is passed in rather than read here, because it lives
    in a fleet-wide log rather than this expert's directory. Callers grading a
    fleet should call ``last_consulted_days`` once and index into it.
    """
    health = ExpertHealth(name=name, beliefs=beliefs, consulted_days_ago=consulted_days_ago)

    study = _load_json(part_in(expert_dir, "noticed"))
    if study:
        totals = study.get("totals") or {}
        health.findings = int(totals.get("findings", 0) or 0)
        health.grounded_findings = int(totals.get("grounded_findings", 0) or 0)
        health.cross_source_findings = int(totals.get("cross_source_findings", 0) or 0)
        health.age_days = _age_days(study.get("started_at", ""), now=now)
        health.contention_findings = sum(
            int(o.get("finding_count", 0) or 0) for o in (study.get("outcomes") or []) if o.get("lens") == "contention"
        )
        independence = study.get("independence") or {}
        health.sources = int(independence.get("source_count", 0) or 0)
        health.effective_origins = float(independence.get("effective_source_count", 0.0) or 0.0)
        health.origin_count = int(independence.get("origin_count", 0) or 0)
        health.dominant_share = float(independence.get("dominant_share", 0.0) or 0.0)

    if not health.sources:
        index = expert_dir / "corpus" / "index.jsonl"
        if index.exists():
            try:
                lines = [line for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
                health.sources = len(lines)
            except OSError:
                pass

    brief = _load_json(part_in(expert_dir, "hold_current"))
    if brief:
        positions = brief.get("positions") or []
        health.positions = len(positions)
        health.falsifiable_positions = sum(1 for p in positions if p.get("is_falsifiable"))
        health.positions_with_dissent = sum(1 for p in positions if admits_something(p.get("unresolved_dissent")))
        health.integrity_warnings = list(brief.get("integrity_warnings") or [])
        state = brief.get("state") or {}
        health.settled_claims = len(state.get("settled") or [])
        health.open_questions = sum(
            1 for item in (state.get("unknown") or []) + (state.get("live") or []) if admits_something(item)
        )

    health.model_tier = _weakest_model_tier(study, _load_json(part_in(expert_dir, "self")))
    graph = _load_json(evidence_graph_in(expert_dir))
    health.graph_is_formed = bool(((graph or {}).get("stats") or {}).get("is_formed"))

    profile = _load_json(part_in(expert_dir, "self"))
    if profile:
        health.standpoint = profile.get("standpoint", "")
        health.open_questions += sum(1 for q in (profile.get("open_questions") or []) if admits_something(q))
        health.known_weaknesses = sum(1 for w in (profile.get("where_it_is_weak") or []) if admits_something(w))
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
        "dropped_dissent": sum(1 for e in fleet if e.dropped_the_dissent),
        "unused": sum(1 for e in fleet if e.is_consultable and not e.is_in_use),
        "s_tier": sum(1 for e in fleet if e.grade == "S"),
    }
