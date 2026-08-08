"""Decide what to go and read, mechanically.

An expert is capped by what it read. Deepr's acquisition took a list of URLs
from a person, which is the weakest of the three channels real researchers
use: an audit of how 495 sources in a complex review were actually found put
protocol-driven search at 30%, citation chasing at 51%, and personal knowledge
at 24%. Deepr had only the third, and no judgment about coverage at all.

The load-bearing decision in this module is that query diversification is
**generated, not requested**. Across 21 studies and about 9,900 participants,
prompting a searcher to consider broader terms had limited effect while
changing what the algorithm returned worked; searchers did not spontaneously
broaden, and running more searches did not help. A prompt that says "also look
for criticism" is the version that fails. So the adversarial and genre arms
are emitted by template whether or not any model thinks they are needed.

Six arms, each answering a different failure:

    descriptive   what the topic is. What a naive search would find alone.
    adversarial   who says it is wrong. Nobody searches for this unprompted.
    genre         reviews, comments, replies, retractions - the document
                  classes that enumerate disagreement as a matter of form.
    primary       specs, standards, registries, datasets. Where a claim is
                  made rather than repeated.
    recency       what changed. A corpus of durable material misses the news.
    terminology   the other community's word for the same thing. The
                  documented miss is a paper that said "cross-continent"
                  where the rest of the field said "global".

Nothing here calls a model or the network. A plan is a list of strings and a
reason for each, so it is inspectable before anything is spent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ARM_DESCRIPTIVE = "descriptive"
ARM_ADVERSARIAL = "adversarial"
ARM_GENRE = "genre"
ARM_PRIMARY = "primary"
ARM_RECENCY = "recency"
ARM_TERMINOLOGY = "terminology"

ARMS: tuple[str, ...] = (
    ARM_DESCRIPTIVE,
    ARM_ADVERSARIAL,
    ARM_GENRE,
    ARM_PRIMARY,
    ARM_RECENCY,
    ARM_TERMINOLOGY,
)

_DESCRIPTIVE_TEMPLATES = (
    "{topic}",
    "{topic} overview",
    "how {topic} works",
    "{topic} explained in depth",
)

_ADVERSARIAL_TEMPLATES = (
    "criticism of {topic}",
    "{topic} limitations",
    "problems with {topic}",
    "case against {topic}",
    "{topic} does not work",
    "failure to replicate {topic}",
    "{topic} overstated",
)
"""Deliberately blunt. These are the searches nobody runs on their own.

The evidence that people do not spontaneously seek disconfirmation is
uniform: the positive test strategy is the default, and searching to verify a
claim has been measured to *increase* belief in false ones, because thin
topics return a manipulated tail. Running these by construction is the only
version that survives that finding.
"""

_GENRE_TEMPLATES = (
    "{topic} systematic review",
    "{topic} controversy",
    "comment on {topic}",
    "reply to {topic}",
    "{topic} retraction",
    "{topic} correction",
)
"""Document classes where disagreement is required by form, not by luck.

A review enumerates the disputes in its field as a matter of genre. A comment
or reply exists only because somebody objected. Retractions and corrections
are the highest-precision signal available and are structurally absent from a
corpus assembled by relevance ranking.
"""

_PRIMARY_TEMPLATES = (
    "{topic} specification",
    "{topic} standard",
    "{topic} original paper",
    "{topic} dataset",
    "{topic} reference implementation",
)

_RECENCY_TEMPLATES = (
    "{topic} recent developments",
    "{topic} what changed",
    "{topic} state of the art",
)

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.-]*")


@dataclass(frozen=True)
class AcquisitionQuery:
    """One search to run, and why it is in the plan."""

    text: str
    arm: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "arm": self.arm, "rationale": self.rationale}


@dataclass
class AcquisitionPlan:
    """The full search, inspectable before anything is spent."""

    topic: str
    queries: list[AcquisitionQuery] = field(default_factory=list)
    excluded_publishers: list[str] = field(default_factory=list)
    search_key: str = ""
    """The shortened noun phrase actually templated, when the topic was long."""

    def by_arm(self, arm: str) -> list[AcquisitionQuery]:
        return [q for q in self.queries if q.arm == arm]

    @property
    def arms_covered(self) -> set[str]:
        return {q.arm for q in self.queries}

    def concerns(self) -> list[str]:
        """Arms a plan is missing, named before it runs rather than after."""
        notes: list[str] = []
        if not self.by_arm(ARM_ADVERSARIAL):
            notes.append(
                "No adversarial queries. A corpus assembled without them reproduces whatever the "
                "ranker considers popular, and dissent is exactly what ranking buries."
            )
        if not self.by_arm(ARM_TERMINOLOGY):
            notes.append(
                "No alternate terminology. A community that names this differently will not appear, "
                "and a citation-based expansion cannot reach it either."
            )
        if not self.by_arm(ARM_PRIMARY):
            notes.append("No primary-source queries, so the corpus may be entirely secondary retelling.")
        if self.search_key and self.search_key != self.topic:
            notes.append(
                f"Queries were built from {self.search_key!r} rather than the full topic, which is too "
                "long to template into a usable search. Check that the shortened form still names the "
                "subject; if it does not, pass a shorter topic."
            )
        return notes

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "search_key": self.search_key,
            "excluded_publishers": self.excluded_publishers,
            "arms_covered": sorted(self.arms_covered),
            "query_count": len(self.queries),
            "queries": [q.to_dict() for q in self.queries],
            "concerns": self.concerns(),
        }


_MAX_TOPIC_WORDS = 6
"""Above this, a templated query stops being a query.

Found by using it: a topic given as a sentence produced
"criticism of anti-slop practices for AI agent generated code and analysis",
which no search engine handles. Templates need a noun phrase, so a long topic
is shortened for templating and the shortening is reported rather than done
quietly."""


def _clean_topic(topic: str) -> str:
    return " ".join(str(topic or "").split())


def search_key(topic: str) -> str:
    """The short noun phrase the templates wrap.

    Content words only, head-first, because a search engine weights the head of
    a phrase and the tail of a description is usually qualifiers.
    """
    words = [w for w in _clean_topic(topic).split() if w.lower() not in _TOPIC_STOPWORDS]
    return " ".join(words[:_MAX_TOPIC_WORDS])


_TOPIC_STOPWORDS = frozenset("a an and are as at be by for from how in is of on or the to what when with".split())


def _emit(templates: tuple[str, ...], topic: str, arm: str, rationale: str) -> list[AcquisitionQuery]:
    return [AcquisitionQuery(text=t.format(topic=topic), arm=arm, rationale=rationale) for t in templates]


def _terminology_queries(alternates: tuple[str, ...]) -> list[AcquisitionQuery]:
    """Re-ask using the other community's word for the same thing."""
    return [
        AcquisitionQuery(
            text=term,
            arm=ARM_TERMINOLOGY,
            rationale="an alternate name for this subject; communities that use it are otherwise unreachable",
        )
        for term in alternates
        if term.strip()
    ]


def _exclusion_queries(topic: str, excluded: tuple[str, ...]) -> list[AcquisitionQuery]:
    """Re-run the topic with the dominant publisher removed.

    A corpus that has collapsed onto one publisher will keep collapsing,
    because the same query returns the same site. Excluding it is the cheapest
    way to find out whether anyone else has written about this at all.
    """
    return [
        AcquisitionQuery(
            text=f"{topic} -site:{publisher}",
            arm=ARM_DESCRIPTIVE,
            rationale=f"{publisher} already dominates this corpus; this asks who else covers the subject",
        )
        for publisher in excluded
        if publisher.strip()
    ]


def plan_queries(
    topic: str,
    *,
    alternates: tuple[str, ...] = (),
    exclude_publishers: tuple[str, ...] = (),
) -> AcquisitionPlan:
    """Build the search plan for one subject.

    ``alternates`` are other names for the same thing, ideally harvested from
    a corpus already read rather than guessed. ``exclude_publishers`` comes
    from the independence measurement: once one origin dominates, the plan
    asks the same questions with that origin removed.
    """
    clean = _clean_topic(topic)
    plan = AcquisitionPlan(topic=clean, excluded_publishers=[p for p in exclude_publishers if p.strip()])
    if not clean:
        return plan
    key = search_key(clean)
    plan.search_key = key
    clean = key or clean

    plan.queries = [
        *_emit(_DESCRIPTIVE_TEMPLATES, clean, ARM_DESCRIPTIVE, "what the subject is, in its own terms"),
        *_emit(
            _ADVERSARIAL_TEMPLATES,
            clean,
            ARM_ADVERSARIAL,
            "who says this is wrong; emitted by construction because nobody searches for it unprompted",
        ),
        *_emit(
            _GENRE_TEMPLATES,
            clean,
            ARM_GENRE,
            "document classes where disagreement appears as a matter of form",
        ),
        *_emit(_PRIMARY_TEMPLATES, clean, ARM_PRIMARY, "where the claim is made rather than repeated"),
        *_emit(_RECENCY_TEMPLATES, clean, ARM_RECENCY, "what changed, which durable material misses"),
        *_terminology_queries(alternates),
        *_exclusion_queries(clean, tuple(plan.excluded_publishers)),
    ]
    return plan


def harvest_alternates(texts: list[str], topic: str, *, limit: int = 6) -> tuple[str, ...]:
    """Pull candidate alternate names for the subject out of what was read.

    Deliberately crude: multi-word capitalized phrases and parenthesized
    expansions, which is where a field's other name for something usually
    sits. Harvesting from the corpus beats guessing, because the whole point
    is to find the vocabulary the expert does not already have.
    """
    known = {w.lower() for w in _WORD_RE.findall(topic)}
    seen: dict[str, int] = {}
    for text in texts:
        for phrase in re.findall(r"\(([^()]{3,60})\)", text or ""):
            candidate = " ".join(phrase.split())
            if not candidate or candidate.lower() in known:
                continue
            words = _WORD_RE.findall(candidate)
            if not words or len(words) > 5:
                continue
            if all(w.lower() in known for w in words):
                continue
            seen[candidate] = seen.get(candidate, 0) + 1
    ranked = sorted(seen.items(), key=lambda item: (-item[1], item[0]))
    return tuple(name for name, _ in ranked[:limit])
