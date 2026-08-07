"""Domain-agnostic study lenses for reading a corpus.

An expert is not a fact ledger. The material that makes one useful - how a thing
actually works, what breaks and how it presents, where good sources disagree,
what a practitioner would expect to find and does not - is structurally absent
from atomic claim extraction, which asks only "what does this sentence assert?".

Lenses vary along two axes:

**Interrogation** - how the material is read. Mechanism, failure, contention,
change, absence. Each asks a different question of the same text.

**Perspective** - who is doing the reading. A think tank is valuable because the
economist, the field operator, and the security researcher notice different
things in one document. Perspective lenses encode standing viewpoints that
generalize across every subject.

INVARIANT: a lens prompt must never name a subject matter. A lens that mentions
networks, medicine, software, or markets is tuned to one topic and will not
generalize, which defeats the purpose of a general expert substrate. This is
enforced mechanically by :func:`domain_hint_leaks` and pinned by a unit test.

Lenses propose; they never write. Admission stays with the existing verifier and
commit gates, which check form and provenance, not whether an insight is good.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

LensAxis = Literal["interrogation", "perspective"]


@dataclass(frozen=True)
class StudyLens:
    """One way of reading a corpus. Carries no subject matter."""

    key: str
    axis: LensAxis
    summary: str
    prompt: str
    output_field: str
    """Top-level JSON array the lens is contracted to return."""


_INTERROGATION: tuple[StudyLens, ...] = (
    StudyLens(
        key="synopsis",
        axis="interrogation",
        summary="What this source actually says, in its own terms",
        output_field="notes",
        prompt="""Read this material and write the notes a serious student would take on it.

Not a compression of the text and not a verdict on it: an account of what it says, what it is
for, what it establishes, and where it stops. Preserve the specifics that make it usable later -
named things, quantities, conditions, dates, defined terms. Note what the source treats as
settled versus what it hedges, and note its own stated scope or limits.

Someone should be able to read your notes and know whether this source is worth returning to,
and for what.

Report only what this material contains.""",
    ),
    StudyLens(
        key="orientation",
        axis="interrogation",
        summary="The shape of the subject: threads, landmarks, state of play",
        output_field="orientation",
        prompt="""Read this material as someone building a map of an unfamiliar subject.

Produce orientation, not summary: what are the main threads and how do they relate; what are the
landmark works, findings, or positions that everything else references; what vocabulary must be
understood before the rest makes sense; what appears settled and what is visibly still moving;
who or what the recurring reference points are.

Also state what a newcomer would most usefully read or resolve next, and why that specifically.

This is the overview a student writes before they can reason about the subject at all.""",
    ),
    StudyLens(
        key="mechanism",
        axis="interrogation",
        summary="How it actually works beneath the vocabulary",
        output_field="concepts",
        prompt="""Read the corpus to understand HOW THE SUBJECT ACTUALLY WORKS beneath its vocabulary.

Do not summarize the documents. Do not restate what each says. Produce the underlying model:
what the real moving parts are, what constrains what, and which stated rules are consequences
of a deeper mechanism rather than independent facts.

Report only what the corpus supports.""",
    ),
    StudyLens(
        key="failure",
        axis="interrogation",
        summary="What breaks, how it presents, what to do instead",
        output_field="fail_patterns",
        prompt="""Read the corpus to find FAILURE MODES: what goes wrong, under what conditions, how it
presents, and what to do instead.

A failure mode is a conditional structure: trigger -> symptom -> mechanism -> correction -> detection.
Report only failure modes this corpus gives you evidence for. Do not report generic best practice.
Silent failures, false reassurance, and results that look like success are the highest value.""",
    ),
    StudyLens(
        key="contention",
        axis="interrogation",
        summary="Where independent sources disagree",
        output_field="tensions",
        prompt="""Read the corpus to find TENSIONS: places where independent sources disagree, where one
source's guidance is undermined by another's evidence, or where a single source contradicts itself.

A tension needs both sides quoted. Do not manufacture disagreement. If the corpus is genuinely
consistent on a point, do not invent a tension for it.""",
    ),
    StudyLens(
        key="change",
        axis="interrogation",
        summary="What changed and what it invalidated",
        output_field="changes",
        prompt="""Read the corpus for WHAT HAS CHANGED over time and what that change invalidates.

Report shifts in understanding, practice, versions, standards, or consensus. For each, state what
was believed or done before, what is the case now, what evidence marks the change, and which
previously reasonable conclusions no longer hold.

Only report change the corpus dates or sequences. Do not infer recency from tone.""",
    ),
    StudyLens(
        key="absence",
        axis="interrogation",
        summary="What a practitioner would expect here and does not find",
        output_field="absences",
        prompt="""Read the corpus and identify what a knowledgeable practitioner would EXPECT TO FIND HERE
AND DOES NOT.

Absence is not "topics not covered". It is: a claim asserted without the evidence that would
normally accompany it, a recommendation with no stated failure case, a measurement with no stated
limits, a decision with no stated alternative considered.""",
    ),
)


_PERSPECTIVE: tuple[StudyLens, ...] = (
    StudyLens(
        key="economic",
        axis="perspective",
        summary="Incentives, costs, and who pays",
        output_field="observations",
        prompt="""Read the corpus as someone who thinks in incentives, costs, and who-pays.

Ask: who bears the cost and who captures the benefit? What is being sold, funded, or defended?
Whose interests shape which claims get made loudly and which get made quietly? What is expensive
that the corpus treats as free, or free that it treats as expensive?

Report only what the corpus supports. Do not invent motives.""",
    ),
    StudyLens(
        key="operational",
        axis="perspective",
        summary="Running it on an ordinary day, and at 3am",
        output_field="observations",
        prompt="""Read the corpus as the person who has to run this in practice, on an ordinary day, and at
3am when it goes wrong.

Ask: what does the routine actually look like? What has to be done repeatedly, by whom, with what
skill? What is easy to get wrong under time pressure or fatigue? What does handover, maintenance,
and recovery look like? What does the corpus describe as one-time setup that is really an ongoing
burden?""",
    ),
    StudyLens(
        key="human_cultural",
        axis="perspective",
        summary="What people will actually do, and why beliefs persist",
        output_field="observations",
        prompt="""Read the corpus as someone who studies how people actually behave, what they believe, and
why beliefs persist past the evidence.

Ask: what will people do rather than what should they do? Which claims will be ignored, resisted,
or over-adopted, and why? What social, status, identity, or trust dynamics surround this subject?
Where does the corpus assume a rational actor who will not exist?""",
    ),
    StudyLens(
        key="adversarial",
        axis="perspective",
        summary="How to make it fail or be misused",
        output_field="observations",
        prompt="""Read the corpus as someone whose goal is to make this fail, be misused, or be turned against
its users. Assume capability and patience.

Ask: what is the abuse case? What assumption, if violated deliberately rather than by accident,
causes the most damage? What does the corpus treat as a safeguard that is really a convention?
Where does trust get extended without being verified?

Report only what the corpus gives you grounds for. Do not speculate beyond the material.""",
    ),
    StudyLens(
        key="institutional",
        axis="perspective",
        summary="Rules, standards, liability, and the bodies that set them",
        output_field="observations",
        prompt="""Read the corpus as someone who works with rules, standards, liability, and the bodies that
set them.

Ask: what obligations attach here, and to whom? What varies by jurisdiction, body, or governing
standard? What is asserted as settled that is actually a policy choice? Where would a reviewer,
regulator, auditor, or ethics board object, and on what grounds?

Never state a legal, regulatory, or compliance conclusion as settled fact. Frame every such point
as what would need checking and against which authority.""",
    ),
)


LENSES: dict[str, StudyLens] = {lens.key: lens for lens in (*_INTERROGATION, *_PERSPECTIVE)}

DEFAULT_LENS_KEYS: tuple[str, ...] = (
    "synopsis",
    "orientation",
    "mechanism",
    "failure",
    "contention",
    "absence",
    "operational",
    "adversarial",
)
"""What a person does when they set out to know a subject, in order.

Read and take notes (synopsis). Build a map of the territory (orientation). Then
interrogate it: how it works, what breaks, where the sources disagree, what is
missing. Then read it as the people who have to live with it (operational,
adversarial).

The analytical lenses came first in development and were, on their own, a
mistake: they produce sharp observations about material the reader has no
orientation in. Notes and a map are what make the rest legible, and they are the
first thing a student writes."""


# Subject-matter words. A lens naming any of these is tuned to one topic.
# Matched as whole words, so stems are spelled out rather than truncated: a
# prefix rule fires on "generic" for "gene" and on "coder" for "code", which
# makes the guard noisy enough that someone eventually deletes it.
_DOMAIN_WORDS: tuple[str, ...] = (
    # technical
    "network",
    "networks",
    "radio",
    "radios",
    "kubernetes",
    "software",
    "code",
    "codebase",
    "protocol",
    "protocols",
    "device",
    "devices",
    "server",
    "servers",
    "packet",
    "packets",
    "frequency",
    "api",
    "apis",
    "database",
    "databases",
    "cluster",
    "clusters",
    "firmware",
    # life sciences and medicine
    "medical",
    "clinical",
    "patient",
    "patients",
    "dose",
    "doses",
    "dosage",
    "supplement",
    "supplements",
    "muscle",
    "biology",
    "biological",
    "gene",
    "genes",
    "genetic",
    "drug",
    "drugs",
    "therapy",
    "diagnosis",
    # commerce and finance
    "market",
    "markets",
    "stock",
    "stocks",
    "portfolio",
    "revenue",
    "customer",
    "customers",
    "pricing",
    # law and policy
    "statute",
    "statutes",
    "litigation",
    "plaintiff",
    "defendant",
    # humanities
    "archaeology",
    "archaeological",
    "artifact",
    "artifacts",
    "manuscript",
)


def domain_hint_leaks() -> list[str]:
    """Lens keys whose prompt leaks a subject matter. Must always be empty.

    Form check only: it asserts that a lens is topic-free, never that a lens is
    a good lens.

    Matching is on word boundaries, not substrings: "gene" inside "generic" and
    "api" inside "rapidly" are not domain leaks, and a substring rule would make
    the guard fire on ordinary prose until someone deleted it.
    """
    leaks: list[str] = []
    for key, lens in LENSES.items():
        lowered = lens.prompt.lower()
        for word in _DOMAIN_WORDS:
            if re.search(rf"\b{re.escape(word)}\b", lowered):
                leaks.append(f"{key}: leaks '{word}'")
    return leaks


def resolve_lenses(keys: list[str] | tuple[str, ...] | None) -> list[StudyLens]:
    """Resolve lens keys to lenses, preserving caller order.

    Raises:
        ValueError: on an unknown key, listing what is available. A silent skip
            would let a typo quietly reduce a study pass to fewer lenses.
    """
    if not keys:
        keys = DEFAULT_LENS_KEYS
    resolved: list[StudyLens] = []
    seen: set[str] = set()
    for key in keys:
        normalized = str(key).strip().lower().replace("-", "_")
        if normalized not in LENSES:
            available = ", ".join(sorted(LENSES))
            raise ValueError(f"unknown lens '{key}'. Available: {available}")
        if normalized not in seen:
            seen.add(normalized)
            resolved.append(LENSES[normalized])
    return resolved


def axis_coverage(lenses: list[StudyLens]) -> dict[str, int]:
    """Count lenses per axis. A study pass with only one axis is thin by design."""
    counts = {"interrogation": 0, "perspective": 0}
    for lens in lenses:
        counts[lens.axis] += 1
    return counts
