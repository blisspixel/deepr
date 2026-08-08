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

    def summary(self) -> str:
        """What happened, without a grade."""
        if not self.exchanges:
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
            "positions_that_moved": self.positions_that_moved,
        }


EXAMINER_PROMPT = """You are examining an expert on "{subject}". You are not an expert on it, and
you are not expected to be. You come from {examiner_frame}.

This is a viva, not a quiz. You do not have the answers and you are not marking a paper. Your job
is to find out whether the thinking underneath these positions is load-bearing, or whether it
stops one question past the summary. Both of you should come out of this knowing more.

Ask the questions your own subject has trained you to ask. Someone who has spent years on a
different problem notices what an insider has stopped seeing, and that is the reason you are in
the room rather than another specialist.

Good viva questions, in rough order of usefulness:

- Why this and not the obvious alternative? What made you land here?
- Which of your positions is weakest, and what is holding it up?
- You lean on this repeatedly and never mention that. Why not?
- What would someone who disagreed with you say, and what is wrong with it?
- You say this is settled. Settled by whom, and what would unsettle it?
- What does this rest on that you have not checked?

Ask {count} questions. For each, say what you are probing, because a question with no target is
small talk.

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

You do not know this subject and you are not marking correctness. You are judging whether each
answer engaged with what you were probing, or slid past it.

For each, choose one verdict:

- "answered": engaged with the probe and gave something substantive.
- "partial": engaged, but left the sharp part of the question untouched.
- "cannot_answer": the expert does not hold this, AND it is the kind of thing that could be
  learned from material that exists. Say what would resolve it.
- "genuinely_open": nobody knows this. Not a deficiency. Do not use this as a polite way of
  saying the expert was unprepared - reserve it for questions the field itself has not settled.

The distinction between the last two is the most useful thing you will produce. One is a reading
list; the other is the edge of what is known.

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
    return EXAMINER_PROMPT.format(
        subject=subject, examiner_frame=examiner_frame, brief=brief, count=count
    )


def build_candidate_prompt(*, subject: str, brief: str, questions: list[str]) -> str:
    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
    return CANDIDATE_PROMPT.format(subject=subject, brief=brief, questions=numbered)


def build_judge_prompt(*, subject: str, exchanges: list[VivaExchange]) -> str:
    transcript = "\n\n".join(
        f"Q: {e.question}\n(probing: {e.probes})\nA: {e.answer}" for e in exchanges
    )
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
