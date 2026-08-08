"""Running an examination: examiners in, transcript and reading list out.

Three passes, in the order a viva actually happens.

1. Each examiner reads the candidate's brief and puts questions to it, from
   its own standpoint rather than as a second specialist.
2. The candidate answers all of them in one pass. One pass rather than one per
   question is deliberate: a viva is a conversation the candidate can see the
   whole of, and answering question six differently because question two
   already covered it is a real part of what is being examined.
3. Each examiner judges the answers to its own questions, and only its own.
   An examiner marking another's questions has no idea what was being probed.

Every model call goes through the same ``StudyCompletion`` the study pass uses,
so this inherits its capacity story unchanged: local or prepaid plan, $0 at the
margin, and no route to a metered API from here.

The failure posture is that an examiner is allowed to fail. A viva with three
examiners where one returns nothing is a viva with two examiners, which is
worth having; taking the whole examination down because one panel member
timed out would be the wrong trade.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from deepr.experts.viva import (
    VivaExchange,
    VivaResult,
    attach_answers,
    attach_judgements,
    build_candidate_prompt,
    build_examiner_prompt,
    build_judge_prompt,
    parse_questions,
)

VivaCompletion = Callable[[str], str]

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class Examiner:
    """Who is asking, and from where.

    ``frame`` is the whole point. "You come from evaluation design" produces
    different questions than "you come from provenance", and an examiner given
    no frame reverts to asking the subject's own obvious questions - which the
    candidate has already answered in its brief.
    """

    name: str
    frame: str
    questions: int = 4


def _parse_json(text: str) -> dict[str, Any]:
    """Recover the object from a model that would not stay out of prose.

    Returns an empty dict rather than raising. A malformed examiner reply
    should cost its questions, not the examination.
    """
    if not text:
        return {}
    candidate = text.strip()
    if fenced := _FENCE_RE.search(candidate):
        candidate = fenced.group(1).strip()
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end > start:
            candidate = candidate[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _ask(completion: VivaCompletion, prompt: str) -> dict[str, Any]:
    """One call, where a failure is an empty result rather than an exception."""
    try:
        return _parse_json(completion(prompt))
    except Exception:
        return {}


def run_viva(
    *,
    expert_name: str,
    subject: str,
    brief: str,
    examiners: list[Examiner],
    completion: VivaCompletion,
) -> VivaResult:
    """Examine one expert, and return what was found rather than a score."""
    result = VivaResult(expert_name=expert_name, examiners=[e.name for e in examiners])

    questions: list[VivaExchange] = []
    for examiner in examiners:
        parsed = _ask(
            completion,
            build_examiner_prompt(
                subject=subject, examiner_frame=examiner.frame, brief=brief, count=examiner.questions
            ),
        )
        questions.extend(parse_questions(parsed, asked_by=examiner.name))

    if not questions:
        return result
    result.exchanges = questions

    answers = _ask(
        completion,
        build_candidate_prompt(subject=subject, brief=brief, questions=[q.question for q in questions]),
    )
    result.positions_that_moved = attach_answers(questions, answers)

    # Each examiner judges only what it asked. It is the only one that knows
    # what the question was probing, so it is the only one able to say whether
    # the answer went there or slid past it.
    for examiner in examiners:
        mine = [q for q in questions if q.asked_by == examiner.name]
        if not mine:
            continue
        attach_judgements(mine, _ask(completion, build_judge_prompt(subject=subject, exchanges=mine)))

    return result


DEFAULT_PANEL: tuple[Examiner, ...] = (
    Examiner(
        name="method",
        frame="research method and evidence - you care how a claim was arrived at, "
        "what would have shown it false, and whether the person checked",
    ),
    Examiner(
        name="practice",
        frame="applied practice - you care what someone would actually do differently "
        "on Monday, and you are impatient with claims that change nothing",
    ),
    Examiner(
        name="dissent",
        frame="the strongest opposing case - you care what a serious, informed "
        "opponent would say, and whether it has been engaged with or waved past",
    ),
)
"""A panel that works with no other experts on hand.

Three standpoints rather than three specialists, because the whole argument for
examination-by-outsider is that the standpoint is what generates the question.
Real experts from other subjects are better - they bring a frame that was built
against real material rather than described in a sentence - and this exists so
a viva is available before there are three other experts worth borrowing.
"""
