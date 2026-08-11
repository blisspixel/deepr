"""Examination by questioning, where nobody has the answer key.

The problem this solves: how do you find out whether an expert understands its
subject when there is no ground truth, and no one available who already knows?

A doctoral viva answers it. The examiners frequently do not know the answer to
what they are asking. That is not a defect of the format, it is the format.
They probe - why this and not the alternative, which part is weakest, you lean
on X and never mention Y, what would change your mind - and what the candidate
demonstrates is whether the thinking is load-bearing or whether it stops one
question past the summary. Both sides come out knowing more than they went in
with, which a graded exam cannot do.

Three things follow that make this the right shape here.

**The examiners can be other experts, and should be.** They do not need the
subject; they need a frame to probe from. An expert on provenance asks
different questions than one on evaluation, and neither is asking as a subject
expert. This is the same property that makes cross-domain consulting work:
a frame built elsewhere notices what an insider stops seeing.

**An unanswerable question is the output, not the failure.** Some are genuine
open questions in the field and the right answer is that nobody knows. Others
are answerable from material that exists and the expert simply has not read
it. The second kind is a reading list somebody else wrote for free, and
telling them apart is most of the value here.

**There is no score.** A viva produces a judgement, a list of things to go and
address, and occasionally the discovery that a position does not survive
contact with a good question. Compressing that into a letter would throw away
the part worth having, and this module deliberately does not.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

VIVA_SCHEMA_VERSION = "deepr-viva-v1"

_MAX_QUESTIONS = 8
_MAX_FIELD_CHARS = 1200

VERDICT_ANSWERED = "answered"
VERDICT_PARTIAL = "partial"
VERDICT_CANNOT = "cannot_answer"
VERDICT_OPEN = "genuinely_open"

_VERDICTS = (VERDICT_ANSWERED, VERDICT_PARTIAL, VERDICT_CANNOT, VERDICT_OPEN)


@dataclass
class VivaExchange:
    """One question, the answer, and what the examiner made of it."""

    question: str
    asked_by: str
    probes: str = ""
    """What the examiner was testing. Without this a question is small talk."""
    answer: str = ""
    verdict: str = VERDICT_ANSWERED
    examiner_note: str = ""
    """Why the examiner judged it that way, so the judgement can be argued with."""
    would_resolve_it: str = ""
    """What material would answer this. The reading-list entry, when there is one."""

    @property
    def is_gap(self) -> bool:
        """Answerable from material that exists, and the expert has not read it."""
        return self.verdict == VERDICT_CANNOT and bool(self.would_resolve_it.strip())

    @property
    def is_frontier(self) -> bool:
        """Nobody knows. Worth recording, and not a deficiency."""
        return self.verdict == VERDICT_OPEN

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_gap"] = self.is_gap
        data["is_frontier"] = self.is_frontier
        return data


@dataclass
class VivaResult:
    """What an examination found. Not a score."""

    expert_name: str
    schema_version: str = VIVA_SCHEMA_VERSION
    examiners: list[str] = field(default_factory=list)
    exchanges: list[VivaExchange] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    """Why calls failed, deduplicated.

    An examiner is allowed to fail without ending the examination, but a
    swallowed failure is worse than a loud one: a capacity refusal - plan
    quota exhausted, spend guard tripped - affects every call, and without
    this the run looks like a panel that had nothing to ask. Measured: the
    paid-overage guard refused mid-session and produced an empty viva with no
    stated reason."""

    positions_that_moved: list[str] = field(default_factory=list)
    """Positions the expert revised or withdrew under questioning.

    The most valuable outcome available and the one a graded exam cannot
    produce: a view that did not survive a good question, found before someone
    relied on it."""

    @property
    def gaps(self) -> list[VivaExchange]:
        """Answerable questions the expert could not answer. The reading queue."""
        return [e for e in self.exchanges if e.is_gap]

    @property
    def frontier(self) -> list[VivaExchange]:
        return [e for e in self.exchanges if e.is_frontier]

    @property
    def handled(self) -> list[VivaExchange]:
        return [e for e in self.exchanges if e.verdict in {VERDICT_ANSWERED, VERDICT_PARTIAL}]

    def reading_queue(self) -> list[str]:
        """What to go and read next, in the examiners' words."""
        return [e.would_resolve_it for e in self.gaps if e.would_resolve_it]

    def as_gaps(self) -> list[dict[str, Any]]:
        """The reading queue, shaped so acquisition can act on it.

        Without this the queue is a list nobody reads. Consult already routes
        its gaps into acquisition; a viva produces the same kind of thing on
        purpose rather than by accident, so it should land in the same place.

        Priority 4 rather than the default 3: these gaps were found by someone
        deliberately looking for them and were named specifically enough to
        search for, which is a better lead than a gap inferred from a consult
        that happened to go badly.
        """
        return [
            {
                "topic": f"Viva gap ({self.expert_name}): {exchange.would_resolve_it}",
                "questions": [exchange.question],
                "priority": 4,
            }
            for exchange in self.gaps
        ]

    def summary(self) -> str:
        """What happened, without a grade."""
        if not self.exchanges:
            if self.failures:
                return f"No questions were put to this expert. Every call failed: {self.failures[0]}"
            return "No questions were put to this expert."
        parts = [
            f"{len(self.exchanges)} question(s) from {len(self.examiners)} examiner(s)",
            f"{len(self.handled)} handled",
        ]
        if self.gaps:
            parts.append(f"{len(self.gaps)} answerable and unanswered")
        if self.frontier:
            parts.append(f"{len(self.frontier)} genuinely open")
        if self.positions_that_moved:
            parts.append(f"{len(self.positions_that_moved)} position(s) moved")
        return "; ".join(parts) + "."

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "expert": self.expert_name,
            "examiners": self.examiners,
            "summary": self.summary(),
            "exchanges": [e.to_dict() for e in self.exchanges],
            "reading_queue": self.reading_queue(),
            "gaps": self.as_gaps(),
            "positions_that_moved": self.positions_that_moved,
            "failures": self.failures,
        }


EXAMINER_PROMPT = """You are examining an expert on "{subject}". You are not an expert on it, and
you are not expected to be. You come from {examiner_frame}.

This is a viva, not a quiz. You do not have the answers and you are not marking a paper. Your job
is to find out whether the thinking underneath these positions is load-bearing, or whether it
stops one question past the summary. Both of you should come out of this knowing more.

Ask the questions your own subject has trained you to ask. Someone who has spent years on a
different problem notices what an insider has stopped seeing, and that is the reason you are in
the room rather than another specialist.

Ask {count} questions, and they must not all be the same kind. Two kinds are needed, because
they find different things.

**Reasoning questions** ask how a position was reached:

- Why this and not the obvious alternative? What made you land here?
- Which of your positions is weakest, and what is holding it up?
- You lean on this repeatedly and never mention that. Why not?
- What would someone who disagreed with you say, and what is wrong with it?
- You say this is settled. Settled by whom, and what would unsettle it?

**Coverage questions** ask about the subject itself, aimed at what this brief does not
mention. Name a specific thing - a technique, a case, a body of work, a competing account, a
population, a time period - that someone working seriously in this area would expect to come
up, and that is absent here. Then ask about it directly.

At least a third of your questions must be coverage questions, and this is not optional. A
panel that only asks reasoning questions gets a clean examination every time, because the
expert can always answer a question about its own thinking by introspecting. "I did not run
that check" is an honest answer and it is not a gap. Only a coverage question can find the
thing the expert has not read.

Your own subject is what makes you good at this: you know what serious work in *your* area
takes account of, and you can ask whether the equivalent exists here.

For each question, say what you are probing, because a question with no target is small talk.

House style: plain ASCII punctuation, a regular hyphen and never an en dash or em dash, straight
quotes, no emoji.

Return JSON only, no prose outside it, no code fence:

{{"questions": [{{"question": "", "probes": "what this is testing"}}]}}

===== WHAT THE EXPERT HOLDS =====
{brief}
===== END =====
"""


CANDIDATE_PROMPT = """You are being examined on "{subject}". Answer as yourself.

These questions come from someone outside your subject. Some will miss. Some will land on
something you have not thought about, and that is what the examination is for.

Answer from what you actually hold. Where your material does not reach, say so plainly - that is
a real answer and a useful one, not a failure. Do not manufacture an answer to look prepared.

If a question changes your mind, say that too. A position that does not survive a good question
was worth losing, and losing it here is much better than losing it after someone relied on it.

House style: plain ASCII punctuation, a regular hyphen and never an en dash or em dash, straight
quotes, no emoji.

Return JSON only, no prose outside it, no code fence:

{{"answers": [{{"question": "the question, copied", "answer": "",
  "changed_my_mind": "what moved, or empty if nothing did"}}]}}

===== WHAT YOU HOLD =====
{brief}
===== END =====

===== QUESTIONS =====
{questions}
===== END =====
"""


JUDGE_PROMPT = """You put these questions to an expert on "{subject}". Judge the answers.

You do not know this subject and you are not marking correctness.

Before choosing a verdict, answer one mechanical question about each reply: **does it contain
the substance the question asked for, or does it explain the absence of that substance?** Those
are different, and how gracefully the second is written does not turn it into the first.

If the question named a body of work, a technique, a case or a population, and the reply says it
was not consulted, was not covered, or is not held - then the substance is absent. That is
"cannot_answer", and the honesty of the admission is not a reason to mark it otherwise. Honesty
determines whether you can trust the answer, not whether the answer is there.

Worked example, because this is the mistake to avoid. Question: "this is the alarm-fatigue
problem that aviation human-factors research has studied for decades - did you consult it?"
Reply: "No, that literature was not consulted; here is what I used instead and why it is
weaker." That is a model answer and it is **cannot_answer**, resolved by the aviation
human-factors literature on alarm fatigue. Marking it "answered" because it was candid and
well-reasoned throws away the single most useful thing this examination produces.

Then choose one verdict:

- "answered": the substance is present. The expert holds this and said it. A candid concession
  about its own reasoning counts here - that is the substance a reasoning question asks for.
- "partial": some of the substance is present and the sharp part of the question is untouched.
- "cannot_answer": the expert does not hold this, AND it could be learned from material that
  exists outside the expert. In "would_resolve_it", name that material - a literature, a
  dataset, a study, a body of practice - specifically enough that someone could go and find it.

  This verdict is only for things the expert must go and *read*. If what is missing is the
  expert's own account of its own reasoning, that is not this verdict, because no amount of
  reading fills it: the expert already has everything it needs and simply did not say. Mark
  those "partial". A reading queue entry beginning "the expert explaining..." or "an account
  from the expert of..." is the mistake this paragraph exists to prevent.
- "genuinely_open": nobody knows this. Not a deficiency. Do not use this as a polite way of
  saying the expert was unprepared - reserve it for questions the field itself has not settled.

The distinction between the last two is the most useful thing you will produce. One is a reading
list; the other is the edge of what is known.

Do not mark cannot_answer for something the expert genuinely addressed just because the answer
was short. Brevity is not absence.

A run where every verdict is "answered" is much more likely to be a judging failure than a
perfect expert. If that is what you are about to return, re-read the coverage questions and
check each one against the substance test above.

House style: plain ASCII punctuation, a regular hyphen and never an en dash or em dash, straight
quotes, no emoji.

Return JSON only, no prose outside it, no code fence:

{{"judgements": [{{"question": "copied", "verdict": "answered|partial|cannot_answer|genuinely_open",
  "note": "why", "would_resolve_it": "what material would answer this, when cannot_answer"}}]}}

===== QUESTIONS AND ANSWERS =====
{transcript}
===== END =====
"""


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())[:_MAX_FIELD_CHARS]


def build_examiner_prompt(*, subject: str, examiner_frame: str, brief: str, count: int = 4) -> str:
    """Ask an outsider to probe, from wherever they actually stand."""
    return EXAMINER_PROMPT.format(subject=subject, examiner_frame=examiner_frame, brief=brief, count=count)


def build_candidate_prompt(*, subject: str, brief: str, questions: list[str]) -> str:
    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
    return CANDIDATE_PROMPT.format(subject=subject, brief=brief, questions=numbered)


def build_judge_prompt(*, subject: str, exchanges: list[VivaExchange]) -> str:
    transcript = "\n\n".join(f"Q: {e.question}\n(probing: {e.probes})\nA: {e.answer}" for e in exchanges)
    return JUDGE_PROMPT.format(subject=subject, transcript=transcript)


def parse_questions(parsed: dict[str, Any], *, asked_by: str) -> list[VivaExchange]:
    """Questions that name what they probe. The rest are small talk."""
    out: list[VivaExchange] = []
    for raw in (parsed.get("questions") or [])[:_MAX_QUESTIONS]:
        if not isinstance(raw, dict):
            continue
        question = _text(raw.get("question"))
        if not question:
            continue
        out.append(VivaExchange(question=question, asked_by=asked_by, probes=_text(raw.get("probes"))))
    return out


def attach_answers(exchanges: list[VivaExchange], parsed: dict[str, Any]) -> list[str]:
    """Fill in answers, returning anything the expert said changed its mind."""
    by_question = {e.question.lower(): e for e in exchanges}
    moved: list[str] = []
    for raw in parsed.get("answers") or []:
        if not isinstance(raw, dict):
            continue
        exchange = by_question.get(_text(raw.get("question")).lower())
        if exchange is None:
            continue
        exchange.answer = _text(raw.get("answer"))
        if changed := _text(raw.get("changed_my_mind")):
            moved.append(changed)
    return moved


def attach_judgements(exchanges: list[VivaExchange], parsed: dict[str, Any]) -> None:
    """Record each verdict, defaulting to partial rather than to a pass."""
    by_question = {e.question.lower(): e for e in exchanges}
    for raw in parsed.get("judgements") or []:
        if not isinstance(raw, dict):
            continue
        exchange = by_question.get(_text(raw.get("question")).lower())
        if exchange is None:
            continue
        verdict = _text(raw.get("verdict")).lower()
        exchange.verdict = verdict if verdict in _VERDICTS else VERDICT_PARTIAL
        exchange.examiner_note = _text(raw.get("note"))
        exchange.would_resolve_it = _text(raw.get("would_resolve_it"))


def render_viva(result: VivaResult) -> str:
    """The transcript, with what to do about it at the end."""
    lines = [f"# {result.expert_name}: examination", "", result.summary(), ""]

    if result.positions_that_moved:
        lines += ["## What moved under questioning", ""]
        lines += [f"- {item}" for item in result.positions_that_moved]
        lines += [
            "",
            "_A position that does not survive a good question was worth losing, and losing it "
            "here is better than losing it after someone relied on it._",
            "",
        ]

    for exchange in result.exchanges:
        lines.append(f"**{exchange.question}**  \n_asked by {exchange.asked_by}, probing {exchange.probes}_")
        lines.append("")
        lines.append(exchange.answer or "_no answer recorded_")
        if exchange.examiner_note:
            lines.append(f"\n> {exchange.verdict}: {exchange.examiner_note}")
        lines.append("")

    if result.gaps:
        lines += ["## What to go and read", ""]
        lines += [f"- {item}" for item in result.reading_queue()]
        lines += ["", "_Answerable, and unanswered. Somebody else wrote this list for free._", ""]

    if result.frontier:
        lines += ["## Where the field itself has not settled", ""]
        lines += [f"- {e.question}" for e in result.frontier]
        lines += ["", "_Not deficiencies. Worth knowing, and worth saying out loud when asked._", ""]

    return "\n".join(lines)
