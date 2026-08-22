"""A model writes the queries; the arm structure still has to hold.

Templating query text was a mistake, and the runs showed it before I admitted
it: four of six arms returned nothing on two separate topics, and the queries
that did run looked like ``criticism of anti-slop practices for AI agent
generated code and analysis``. That is not a search anybody would type. I
reported the empty arms as signal about the subject when they were signal
about the queries.

The evidence I was leaning on says something narrower than I made it say. It
found that *people* do not spontaneously broaden their own searching, and that
changing what the algorithm returns works where prompting the searcher does
not. That argues the *coverage guarantee* must be structural. It does not
argue the query text should be string concatenation.

So the split is:

    structural   the arms. A model told to "search thoroughly" reliably omits
                 the adversarial and primary arms, so their presence is a
                 requirement checked after the fact, not a request.
    model        what actually goes in them. Which critics this field has, what
                 it calls its own controversies, where its landmark work was
                 published, and the other community's word for the subject.
                 Templates know none of that and cannot learn it.

Falls back to templates when there is no model, when the call fails, or when a
required arm comes back empty, and says so on the plan. Templates are a poor
researcher and a dependable one; keeping them is what lets acquisition run at
$0 with no model at all.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from deepr.experts.acquisition_plan import (
    ARM_ADVERSARIAL,
    ARM_DESCRIPTIVE,
    ARM_GENRE,
    ARM_PRIMARY,
    ARM_RECENCY,
    ARM_TERMINOLOGY,
    ARMS,
    AcquisitionPlan,
    AcquisitionQuery,
    plan_queries,
)

QueryCompletion = Callable[[str], Awaitable[str]]

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.-]*")
_STOPWORDS = frozenset("a an and are as at be by for from how in is of on or the to what when with".split())

_PER_ARM = 4
_MAX_QUERY_CHARS = 120

_ARM_BRIEFS: dict[str, str] = {
    ARM_DESCRIPTIVE: "what the subject is and how it works, in the terms its own field uses",
    ARM_ADVERSARIAL: (
        "who says this is wrong, and why. Name the actual critics, the specific objections, the "
        "known failure cases. Not 'criticism of X' - the search a skeptic in this field would run"
    ),
    ARM_GENRE: (
        "documents that enumerate disagreement by form: reviews, surveys, comments, replies, "
        "rebuttals, retractions, errata. Use the words this field uses for those"
    ),
    ARM_PRIMARY: (
        "where the claim is made rather than repeated: specs, standards, original papers, "
        "datasets, reference implementations, named landmark work"
    ),
    ARM_RECENCY: "what changed recently, and what supersedes older material",
    ARM_TERMINOLOGY: (
        "the same subject as named by a different community. Different words, not a rephrasing - "
        "queries here that share the topic's own vocabulary are useless"
    ),
}

_REQUIRED_ARMS = (ARM_ADVERSARIAL, ARM_PRIMARY, ARM_TERMINOLOGY)
"""The arms a model skips unprompted, which are the ones that matter most."""


def build_proposal_prompt(topic: str, known_terms: tuple[str, ...] = ()) -> str:
    """Ask for real queries, arm by arm, with each arm's job stated."""
    arms = "\n".join(f'  "{arm}": {brief}' for arm, brief in _ARM_BRIEFS.items())
    seen = ""
    if known_terms:
        seen = "\nAlready in the corpus, so do not simply re-find it: " + "; ".join(known_terms) + "\n"

    return (
        f"Plan the searches for building an expert on: {topic}\n\n"
        "Write the queries a researcher who knows this field would actually type. Real terminology, "
        "real names, real venues where they help. A query that is the topic with a word bolted on "
        "the front is worse than useless: it looks like coverage and finds nothing.\n\n"
        "Each arm has a different job:\n\n"
        f"{arms}\n{seen}\n"
        "Rules:\n"
        f"- {_PER_ARM} queries per arm.\n"
        "- Every arm must be filled. The adversarial and primary arms are the ones most often "
        "skipped and the ones that matter most; a corpus without them reproduces whatever is "
        "already popular.\n"
        "- Queries must be searchable: short and specific, not sentences.\n"
        "- Do not repeat the topic verbatim as a query.\n\n"
        "Return JSON only, no prose, no code fence:\n\n"
        '{"queries": {' + ", ".join(f'"{arm}": [""]' for arm in ARMS) + "}}\n"
    )


def echoes_topic(text: str, topic: str) -> bool:
    """True when a query is the topic wearing a hat.

    ``criticism of X`` reaches nothing a search for ``X`` did not already
    reach. This is the exact failure templating made unavoidable, and a model
    can still produce it, so it is checked rather than assumed away.
    """
    words = {w.lower() for w in _WORD_RE.findall(text)}
    topic_words = {w.lower() for w in _WORD_RE.findall(topic)}
    return len(words - topic_words - _STOPWORDS) <= 1


def assemble_proposed_plan(parsed: dict[str, Any], topic: str) -> AcquisitionPlan:
    """Turn a proposal into a plan, keeping only queries that add something."""
    plan = AcquisitionPlan(topic=" ".join(topic.split()))
    plan.search_key = plan.topic
    raw = parsed.get("queries") if isinstance(parsed.get("queries"), dict) else parsed
    seen_queries: set[str] = set()

    for arm in ARMS:
        items = (raw or {}).get(arm) or []
        if not isinstance(items, list):
            continue
        accepted = 0
        for item in items[: _PER_ARM * 2]:
            if not isinstance(item, str):
                continue
            text = " ".join(item.split())
            if not text or len(text) > _MAX_QUERY_CHARS:
                continue
            if arm != ARM_DESCRIPTIVE and echoes_topic(text, topic):
                continue
            query_key = text.casefold()
            if query_key in seen_queries:
                continue
            plan.queries.append(AcquisitionQuery(text=text, arm=arm, rationale=_ARM_BRIEFS[arm]))
            seen_queries.add(query_key)
            accepted += 1
            if accepted == _PER_ARM:
                break
    return plan


def templated_fallback(topic: str, why: str) -> AcquisitionPlan:
    """The deterministic plan, labeled with why it was reached for."""
    plan = plan_queries(topic)
    plan.fallback_reason = why
    return plan


async def propose_plan(
    topic: str,
    *,
    completion: QueryCompletion,
    known_terms: tuple[str, ...] = (),
) -> AcquisitionPlan:
    """Ask a model to write the plan, then check the structure held."""
    from deepr.experts.study import extract_json_object

    clean_topic = " ".join(topic.split())
    if not clean_topic:
        return templated_fallback("", "the topic was empty")

    try:
        raw = await completion(build_proposal_prompt(clean_topic, known_terms))
    except Exception as exc:
        return templated_fallback(clean_topic, f"the query proposal call failed ({type(exc).__name__})")

    parsed, error = extract_json_object(raw)
    if parsed is None:
        return templated_fallback(clean_topic, f"the query proposal did not return usable JSON ({error})")

    plan = assemble_proposed_plan(parsed, clean_topic)
    if missing := [arm for arm in _REQUIRED_ARMS if not plan.by_arm(arm)]:
        return templated_fallback(clean_topic, f"the proposal left {', '.join(missing)} empty")
    return plan
