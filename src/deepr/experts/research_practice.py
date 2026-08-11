"""What an expert does to stay expert, rather than what it knows.

A professor does not maintain expertise by holding facts. They maintain a
practice: a handful of questions they are actively chasing, a set of sources
they follow because those sources have repeatedly been worth reading, and areas
they are deepening as against areas they are merely keeping an eye on. The
practice is what makes next month's reading different from last month's, and it
is the thing that turns elapsed time into expertise.

Deepr has every input for this and has never assembled it:

- the **agenda** exists as ``open_questions`` on the profile card, regenerated
  from scratch each time and driving nothing;
- **which sources have earned attention** is computable exactly, from the
  evidence graph's ``load_bearing_sources`` - the publishers the expert's own
  claims actually trace back to, as opposed to the ones that happened to be
  acquired;
- **new questions** arrive every time a viva finds something answerable that
  the expert could not answer;
- and nothing feeds any of it into the next acquisition, so every acquisition
  starts from the topic string again as though the expert had learned nothing
  about where to look.

The practice closes that loop. It is the difference between an expert that is
re-researched and one that is *keeping up*.

**Three record types, and the distinctions between them are the design.**

A **pursuit** is a question the expert decided to chase. It is not a gap. A gap
is something missing from the corpus - a property of the material. A pursuit is
something the expert chose to care about, which is why it carries a reason and
a resolution rather than just a description. Pursuits open, get answered, or get
abandoned, and all three are recorded because abandoning a line of enquiry is
itself a finding about the subject.

A **watch** is a source worth following, and it must be *earned*. Promoting
whatever was acquired first would just re-rank the accident of acquisition
order. A watch is promoted from evidence: this publisher's material is what the
expert's positions actually rest on. Demotion is equally evidential - a watch
that stops producing anything load-bearing is dropped, which is how a field
moving on becomes visible rather than being silently carried forever.

An **interest** is an area with a stated depth. The distinction between
deepening and maintaining is what stops an expert either sprawling across
everything shallowly or over-focusing on one corner. A human keeps two or three
things deep and a dozen shallow, deliberately.

Nothing here calls a model. Every update is derived from artifacts already on
disk, which is what makes it cheap enough to run after every study.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PRACTICE_SCHEMA_VERSION = "deepr-research-practice-v1"

PURSUIT_OPEN = "open"
PURSUIT_ANSWERED = "answered"
PURSUIT_ABANDONED = "abandoned"

DEPTH_DEEPENING = "deepening"
DEPTH_MAINTAINING = "maintaining"
DEPTH_PERIPHERAL = "peripheral"

_MAX_DEEPENING = 3
"""How many areas an expert may be actively deepening at once.

A human keeps two or three things deep and a dozen shallow. An expert
"deepening" everything is one that has not prioritised, and the whole value of
a stated depth is that it forces the choice."""

_MAX_WATCHES = 12
"""A reading list nobody can get through is not a reading list."""

_STALE_WATCH_ROUNDS = 3
"""Rounds a watch may produce nothing load-bearing before it is dropped.

Three rather than one, because a publisher that had a quiet quarter is not a
publisher that has stopped mattering."""


@dataclass
class Pursuit:
    """A question the expert decided to chase.

    Not a gap. A gap is missing material; a pursuit is a choice, which is why
    it carries why it matters and how it ended.
    """

    question: str
    why_it_matters: str = ""
    opened_at: str = ""
    status: str = PURSUIT_OPEN
    resolution: str = ""
    """What answered it, or why it was abandoned. Empty while open."""
    resolved_at: str = ""
    origin: str = ""
    """Where it came from: profile, viva, consult. Lets a reader judge it."""

    @property
    def is_live(self) -> bool:
        return self.status == PURSUIT_OPEN

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_live"] = self.is_live
        return data


@dataclass
class Watch:
    """A source followed because its material has proved load-bearing."""

    origin: str
    """Publisher or origin key. What to go and check."""
    why: str = ""
    added_at: str = ""
    positions_resting_on_it: int = 0
    """Earned attention, measured. Not how much was acquired from it."""
    quiet_rounds: int = 0
    """Consecutive updates in which it carried nothing. Demotion counter."""

    @property
    def is_stale(self) -> bool:
        return self.quiet_rounds >= _STALE_WATCH_ROUNDS

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_stale"] = self.is_stale
        return data


@dataclass
class Interest:
    """An area, and how much attention the expert is giving it."""

    area: str
    depth: str = DEPTH_MAINTAINING
    why: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchPractice:
    """How this expert keeps up. Append-only where it matters."""

    expert_name: str
    schema_version: str = PRACTICE_SCHEMA_VERSION
    updated_at: str = ""
    pursuits: list[Pursuit] = field(default_factory=list)
    watches: list[Watch] = field(default_factory=list)
    interests: list[Interest] = field(default_factory=list)
    dropped_watches: list[dict[str, Any]] = field(default_factory=list)
    """Sources that were being watched and no longer are, with why.

    Both ways a watch can leave are decisions worth seeing: three quiet rounds
    means the expert judged a publisher to have stopped mattering, and falling
    past the cap means it lost to twelve others. Dropping either silently
    leaves a practice that looks deliberately chosen when part of it was
    truncated, and "append-only where it matters" has to include the removals
    or it is only a description of the happy path."""

    @property
    def live_pursuits(self) -> list[Pursuit]:
        return [p for p in self.pursuits if p.is_live]

    @property
    def deepening(self) -> list[Interest]:
        return [i for i in self.interests if i.depth == DEPTH_DEEPENING]

    @property
    def is_practising(self) -> bool:
        """Whether this expert has a practice at all.

        A live question and somewhere to look. An expert with neither is not
        keeping up with anything; it is waiting to be re-researched, which is
        what every expert in the fleet does today.
        """
        return bool(self.live_pursuits and self.watches)

    def next_reading(self, limit: int = 5) -> list[str]:
        """What to go and read, in the expert's own words.

        Live pursuits first, because a question is a better search than a
        topic, then the sources that have earned a look. This is the ordering
        an acquisition pass should follow rather than starting from the topic
        string again.
        """
        out = [p.question for p in self.live_pursuits[:limit]]
        remaining = limit - len(out)
        if remaining > 0:
            out += [f"new material from {w.origin}" for w in self.watches[:remaining]]
        return out

    def stats(self) -> dict[str, Any]:
        return {
            "live_pursuits": len(self.live_pursuits),
            "answered_pursuits": sum(1 for p in self.pursuits if p.status == PURSUIT_ANSWERED),
            "abandoned_pursuits": sum(1 for p in self.pursuits if p.status == PURSUIT_ABANDONED),
            "watches": len(self.watches),
            "stale_watches": sum(1 for w in self.watches if w.is_stale),
            "deepening": len(self.deepening),
            "is_practising": self.is_practising,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "expert": self.expert_name,
            "updated_at": self.updated_at,
            "stats": self.stats(),
            "next_reading": self.next_reading(),
            "pursuits": [p.to_dict() for p in self.pursuits],
            "watches": [w.to_dict() for w in self.watches],
            "interests": [i.to_dict() for i in self.interests],
            "dropped_watches": list(self.dropped_watches),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchPractice:
        practice = cls(
            expert_name=str(data.get("expert") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )
        for raw in data.get("pursuits") or []:
            if isinstance(raw, dict) and raw.get("question"):
                practice.pursuits.append(
                    Pursuit(
                        question=str(raw["question"]),
                        why_it_matters=str(raw.get("why_it_matters") or ""),
                        opened_at=str(raw.get("opened_at") or ""),
                        status=str(raw.get("status") or PURSUIT_OPEN),
                        resolution=str(raw.get("resolution") or ""),
                        resolved_at=str(raw.get("resolved_at") or ""),
                        origin=str(raw.get("origin") or ""),
                    )
                )
        for raw in data.get("watches") or []:
            if isinstance(raw, dict) and raw.get("origin"):
                practice.watches.append(
                    Watch(
                        origin=str(raw["origin"]),
                        why=str(raw.get("why") or ""),
                        added_at=str(raw.get("added_at") or ""),
                        positions_resting_on_it=int(raw.get("positions_resting_on_it", 0) or 0),
                        quiet_rounds=int(raw.get("quiet_rounds", 0) or 0),
                    )
                )
        for raw in data.get("interests") or []:
            if isinstance(raw, dict) and raw.get("area"):
                practice.interests.append(
                    Interest(
                        area=str(raw["area"]),
                        depth=str(raw.get("depth") or DEPTH_MAINTAINING),
                        why=str(raw.get("why") or ""),
                    )
                )
        practice.dropped_watches = [d for d in (data.get("dropped_watches") or []) if isinstance(d, dict)]
        return practice


def _normalized(question: str) -> str:
    from deepr.experts.record_identity import normalize_text

    return normalize_text(question)


def open_pursuits(
    practice: ResearchPractice,
    questions: list[str],
    *,
    origin: str,
    at: str,
    why: str = "",
) -> int:
    """Add questions the expert has decided to chase. Returns how many are new.

    Deduplicated against every pursuit ever held, not just the live ones. A
    question that was asked and abandoned must not silently reopen on the next
    pass - re-opening it should be a decision, and reappearing is not one.
    """
    known = {_normalized(p.question) for p in practice.pursuits}
    added = 0
    for question in questions:
        text = " ".join(str(question or "").split())
        if not text or _normalized(text) in known:
            continue
        practice.pursuits.append(Pursuit(question=text, why_it_matters=why, opened_at=at, origin=origin))
        known.add(_normalized(text))
        added += 1
    return added


def resolve_pursuit(practice: ResearchPractice, question: str, *, resolution: str, at: str) -> bool:
    """Close a pursuit as answered. Returns whether one matched."""
    target = _normalized(question)
    for pursuit in practice.pursuits:
        if pursuit.is_live and _normalized(pursuit.question) == target:
            pursuit.status = PURSUIT_ANSWERED
            pursuit.resolution = resolution
            pursuit.resolved_at = at
            return True
    return False


def update_watches(practice: ResearchPractice, load_bearing: list[tuple[str, int]], *, at: str) -> None:
    """Promote sources the expert's claims actually rest on, drop the quiet ones.

    ``load_bearing`` is ``(origin, positions_resting_on_it)`` from the evidence
    graph. Attention is earned by carrying claims, not by having been acquired:
    promoting whatever arrived first would only re-rank the accident of
    acquisition order.

    A watch that carries nothing this round has its quiet counter advanced
    rather than being dropped immediately, because a publisher with a quiet
    quarter has not stopped mattering. Three quiet rounds and it goes, which is
    how a field moving on becomes visible instead of being carried forever.

    Every departure is recorded in ``dropped_watches`` with its reason. A
    practice that silently truncated to its cap reads as twelve deliberately
    chosen sources whether or not it was ever asked to choose.
    """
    counts = {origin: n for origin, n in load_bearing if origin}
    existing = {w.origin: w for w in practice.watches}

    for origin, count in counts.items():
        watch = existing.get(origin)
        if watch is None:
            watch = Watch(origin=origin, added_at=at, why="its material is what my positions rest on")
            practice.watches.append(watch)
            existing[origin] = watch
        watch.positions_resting_on_it = count
        watch.quiet_rounds = 0

    for watch in practice.watches:
        if watch.origin not in counts:
            watch.quiet_rounds += 1

    kept = [w for w in practice.watches if not w.is_stale]
    for watch in practice.watches:
        if watch.is_stale:
            practice.dropped_watches.append(
                {"origin": watch.origin, "why": f"carried nothing for {watch.quiet_rounds} rounds", "at": at}
            )

    kept.sort(key=lambda w: w.positions_resting_on_it, reverse=True)
    for watch in kept[_MAX_WATCHES:]:
        practice.dropped_watches.append(
            {"origin": watch.origin, "why": f"outranked; only {_MAX_WATCHES} watches are kept", "at": at}
        )
    practice.watches = kept[:_MAX_WATCHES]


def set_interests(practice: ResearchPractice, interests: list[Interest]) -> None:
    """Replace the interest set, holding the deepening budget.

    Excess deepening areas are demoted to maintaining rather than dropped: the
    expert still cares about them, it just cannot be going deep on eight things
    at once, and silently discarding an area it named would be worse than
    saying it is on the back burner.
    """
    ordered = list(interests)
    deepening = [i for i in ordered if i.depth == DEPTH_DEEPENING]
    for surplus in deepening[_MAX_DEEPENING:]:
        surplus.depth = DEPTH_MAINTAINING
        surplus.why = (surplus.why + " (demoted: deepening budget is full)").strip()
    practice.interests = ordered


PRACTICE_PROMPT = """You are "{expert_name}". Decide what you are working on next.

This is not a summary of what you know. It is your research practice: the questions you have
chosen to chase, and where your attention should go. A specialist stays a specialist by
maintaining one of these, not by having read a lot once.

What is decided for you, and what is yours:

- **Which sources you follow is already settled** and is not your call. It is measured from
  which publishers your own positions actually rest on, so you cannot promote a source you
  like the look of. That is deliberate.
- **What you are chasing, and where your attention goes, is entirely yours.**

Three jobs.

**1. Review your live pursuits.** For each one below, say whether what you have read since
answers it. Be strict: a question is answered when you could now give a supported answer, not
when you have read around it. If a line of enquiry turned out to be the wrong question, abandon
it and say why - abandoning is a real finding about the subject and is not a failure.

**2. Open new pursuits.** What do you now want to know that you did not before? Good ones come
from a tension you could not resolve, a claim you could not check, or a question your reading
kept circling without landing on. Each needs a reason it matters to *this* subject. Do not open
a pursuit you have no way to make progress on.

**3. Set your attention.** Name the areas you work in and how deep you are going on each:
"deepening" (actively going after it), "maintaining" (keeping current, not digging), or
"peripheral" (aware, not investing). At most {max_deepening} may be deepening. A specialist
keeps two or three things deep and a dozen shallow, and choosing is the point.

House style: plain ASCII punctuation, a regular hyphen and never an en dash or em dash, straight
quotes, no emoji.

Return JSON only, no prose outside it, no code fence:

{{
  "reviewed": [{{"question": "copied exactly", "verdict": "still_open|answered|abandon",
                "resolution": "what answered it, or why you are abandoning it"}}],
  "new_pursuits": [{{"question": "", "why_it_matters": ""}}],
  "interests": [{{"area": "", "depth": "deepening|maintaining|peripheral", "why": ""}}]
}}

===== HOW YOU READ THIS SUBJECT =====
{standpoint}
===== END =====

===== WHAT YOU ARE CURRENTLY CHASING =====
{live}
===== END =====

===== WHAT YOU HAVE READ SINCE =====
{material}
===== END =====
"""


def build_practice_prompt(
    *,
    expert_name: str,
    standpoint: str,
    practice: ResearchPractice,
    material: str,
) -> str:
    """Ask the expert to update its own agenda.

    Deliberately does not ask about watches. Those are measured from the
    evidence graph, and letting a model rank them would reintroduce exactly the
    guessing that the measurement replaced - an expert would follow the sources
    it finds appealing rather than the ones carrying its claims.
    """
    live = "\n".join(f"- {p.question}" for p in practice.live_pursuits) or "(nothing yet)"
    return PRACTICE_PROMPT.format(
        expert_name=expert_name,
        standpoint=standpoint or "(no standpoint recorded yet)",
        live=live,
        material=material,
        max_deepening=_MAX_DEEPENING,
    )


def apply_practice_update(practice: ResearchPractice, parsed: dict[str, Any], *, at: str) -> dict[str, int]:
    """Fold the expert's own decisions into its practice. Returns what changed.

    Resolutions are applied before new pursuits open, so a question the expert
    answered and immediately re-asked in different words is deduplicated
    against the closed one rather than reopening as new.
    """
    changed = {"answered": 0, "abandoned": 0, "opened": 0}

    for raw in parsed.get("reviewed") or []:
        if not isinstance(raw, dict):
            continue
        verdict = str(raw.get("verdict") or "").strip().lower()
        resolution = " ".join(str(raw.get("resolution") or "").split())
        question = str(raw.get("question") or "")
        if verdict == "answered" and resolve_pursuit(practice, question, resolution=resolution, at=at):
            changed["answered"] += 1
        elif verdict == "abandon":
            target = _normalized(question)
            for pursuit in practice.pursuits:
                if pursuit.is_live and _normalized(pursuit.question) == target:
                    pursuit.status = PURSUIT_ABANDONED
                    pursuit.resolution = resolution or "abandoned without a stated reason"
                    pursuit.resolved_at = at
                    changed["abandoned"] += 1
                    break

    for raw in parsed.get("new_pursuits") or []:
        if not isinstance(raw, dict) or not str(raw.get("question") or "").strip():
            continue
        changed["opened"] += open_pursuits(
            practice,
            [str(raw["question"])],
            origin="self",
            at=at,
            why=" ".join(str(raw.get("why_it_matters") or "").split()),
        )

    if interests := [
        Interest(
            area=" ".join(str(raw.get("area") or "").split()),
            depth=str(raw.get("depth") or DEPTH_MAINTAINING).strip().lower(),
            why=" ".join(str(raw.get("why") or "").split()),
        )
        for raw in (parsed.get("interests") or [])
        if isinstance(raw, dict) and str(raw.get("area") or "").strip()
    ]:
        set_interests(practice, interests)

    practice.updated_at = at
    return changed


def render_practice(practice: ResearchPractice) -> str:
    """What this expert is doing to stay expert."""
    lines = [f"# {practice.expert_name}: research practice", ""]

    if not practice.is_practising:
        lines += [
            "This expert has no live questions, or nowhere it is following. It is not keeping up "
            "with anything - it is waiting to be re-researched.",
            "",
        ]

    if live := practice.live_pursuits:
        lines += ["## What it is chasing", ""]
        for pursuit in live:
            origin = f" _(from {pursuit.origin})_" if pursuit.origin else ""
            lines.append(f"- {pursuit.question}{origin}")
        lines.append("")

    if answered := [p for p in practice.pursuits if p.status == PURSUIT_ANSWERED]:
        lines += ["## What it has settled", ""]
        lines += [f"- {p.question}\n  - {p.resolution}" for p in answered[-5:]]
        lines.append("")

    if practice.watches:
        lines += ["## What it follows", ""]
        for watch in practice.watches:
            quiet = f", quiet for {watch.quiet_rounds}" if watch.quiet_rounds else ""
            lines.append(f"- {watch.origin} ({watch.positions_resting_on_it} position(s) rest on it{quiet})")
        lines += ["", "_Earned by carrying claims, not by having been acquired._", ""]

    if practice.interests:
        lines += ["## Where its attention is", ""]
        for interest in practice.interests:
            lines.append(f"- **{interest.depth}**: {interest.area}")
        lines.append("")

    if reading := practice.next_reading():
        lines += ["## What it would read next", ""]
        lines += [f"- {item}" for item in reading]
        lines.append("")

    return "\n".join(lines)
