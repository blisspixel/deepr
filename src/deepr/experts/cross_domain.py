"""Ask an expert about something outside its subject, on purpose.

A furniture designer consulting an expert on Chinese writing gets nothing
useful if the question is "what do your sources say about chairs." They get
something worth having if the question is "you have spent a long time on a
system where meaning is carried by stroke order, radical composition and the
negative space inside a character - what does that make you notice about
this."

The expert knows nothing about furniture. That is the point. What transfers
is not its facts but its **frame**: the distinctions it has learned to make,
the failure modes it has learned to look for, the thing it has learned is
usually the real problem. A frame built somewhere else notices different
things, and noticing differently is most of what an outside perspective is
for.

Deepr's normal consult path forbids exactly this, correctly. Positions are
ranked against the question and dropped when they do not match, coverage
reports `uncovered`, and the expert says it holds nothing rather than
answering from adjacent material. That rule exists because answering outside
your evidence while sounding evidenced is the failure this whole system is
built against.

So this is a different mode, not a loosening of that one. Two rules keep it
honest:

**Nothing here is offered as evidence about the asked subject.** The expert's
findings are about *its* corpus. Carried across, they are analogy, and every
rendering says so. An analogy that presents as evidence is fabrication with a
citation attached, which is worse than a guess.

**The transfer is stated, not implied.** A useful cross-domain observation
names what maps to what and where the mapping breaks. "Both involve
composition" is a word, not an insight. Analogies are load-bearing exactly
where they are specific and fail exactly where nobody checked whether they
hold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CROSS_DOMAIN_SCHEMA_VERSION = "deepr-cross-domain-v1"

_MAX_PATTERNS = 10


@dataclass
class CrossDomainReading:
    """One expert's outside view, kept separate from its evidence."""

    expert_name: str
    asked_about: str
    standpoint: str = ""
    """The frame being lent. Empty when the expert has no reading of its own."""
    preferred_lens: str = ""
    observations: list[str] = field(default_factory=list)
    """What this frame notices, each naming the mapping it rests on."""
    where_it_breaks: list[str] = field(default_factory=list)
    """Where the analogy stops holding. Without this it is decoration."""
    schema_version: str = CROSS_DOMAIN_SCHEMA_VERSION

    @property
    def is_usable(self) -> bool:
        """An analogy with no stated limit is not offered as one."""
        return bool(self.observations and self.where_it_breaks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "expert": self.expert_name,
            "asked_about": self.asked_about,
            "kind": "analogy",
            "is_evidence": False,
            "standpoint": self.standpoint,
            "preferred_lens": self.preferred_lens,
            "observations": self.observations,
            "where_it_breaks": self.where_it_breaks,
            "is_usable": self.is_usable,
        }


CROSS_DOMAIN_PROMPT = """You are an expert on "{expert_name}". You are being asked about something
else entirely: {question}

You do not know this subject and you are not being asked to pretend otherwise. Nobody wants your
guess about it. What is wanted is what your subject has trained you to notice.

You have spent a long time on {expert_name}. That has given you distinctions other people do not
make, failure modes you look for first, and a sense of what is usually the real problem underneath
what people ask about. Those travel. Your facts do not.

So: read the question through your subject. What does your frame make visible here that someone
inside this subject would probably not think to look at?

Rules that keep this useful rather than decorative:

- Every observation must name the specific mapping it rests on. "Both involve composition" is a
  word, not an insight. "In my subject, the meaning lives in the order of construction, not the
  finished form - so I would ask whether the order of assembly here carries information nobody is
  reading" is an insight, because someone can check whether the mapping holds.
- Say where the analogy breaks. An analogy with no stated limit is being offered as a fact. The
  places it fails are usually where it would have misled someone.
- Do not claim your sources say anything about this subject. They do not. You are lending a way of
  seeing, not evidence.
- If your frame genuinely offers nothing here, say so. A forced analogy is worse than none, and
  admitting the reach failed is a real answer.

{standpoint_block}
House style: plain ASCII punctuation, a regular hyphen and never an en dash or em dash, straight
quotes, no emoji.

Return JSON only, no prose outside it, no code fence:

{{
  "observations": ["what your frame notices, each naming the mapping it rests on"],
  "where_it_breaks": ["where the analogy stops holding, and why"]
}}

===== WHAT YOUR SUBJECT HAS TAUGHT YOU =====
{material}
===== END =====
"""


def build_cross_domain_prompt(
    *,
    expert_name: str,
    question: str,
    material: str,
    standpoint: str = "",
    preferred_lens: str = "",
) -> str:
    """Ask for the frame, and refuse the facts."""
    block = ""
    if standpoint:
        block = f"How you read your own subject:\n  {standpoint}\n"
    if preferred_lens:
        block += f"The way of reading you find most revealing:\n  {preferred_lens}\n"
    return CROSS_DOMAIN_PROMPT.format(
        expert_name=expert_name,
        question=question,
        material=material,
        standpoint_block=block,
    )


def frame_material(context: Any, *, limit: int = _MAX_PATTERNS) -> str:
    """What to lend: the expert's patterns, not its question-matched evidence.

    Deliberately ignores the question. Ranking findings against a question from
    another subject would surface whatever shares vocabulary with it, which is
    the least interesting thing an outside frame has to offer and the most
    likely to look like false relevance.
    """
    lines: list[str] = []
    if getattr(context, "orientation", ""):
        lines += ["How this subject stands:", context.orientation, ""]

    findings = list(getattr(context, "findings", []) or [])
    if findings:
        lines.append("Patterns this subject has taught me to see:")
        lines += [f"- {f.title}" for f in findings[:limit]]
        lines.append("")

    settled = list(getattr(context, "settled", []) or [])
    if settled:
        lines.append("What is settled here, which may be where the useful contrast is:")
        lines += [f"- {item}" for item in settled[:4]]
        lines.append("")

    live = list(getattr(context, "live", []) or [])
    if live:
        lines.append("What is still contested here:")
        lines += [f"- {item}" for item in live[:4]]
    return "\n".join(lines).strip()


def assemble_reading(parsed: dict[str, Any], *, expert_name: str, question: str, **frame: str) -> CrossDomainReading:
    """Build the reading, dropping observations that name no mapping."""

    def _clean(items: Any) -> list[str]:
        if not isinstance(items, list):
            return []
        return [" ".join(str(v).split()) for v in items if str(v).strip()][:_MAX_PATTERNS]

    return CrossDomainReading(
        expert_name=expert_name,
        asked_about=question,
        standpoint=frame.get("standpoint", ""),
        preferred_lens=frame.get("preferred_lens", ""),
        observations=_clean(parsed.get("observations")),
        where_it_breaks=_clean(parsed.get("where_it_breaks")),
    )


def render_reading(reading: CrossDomainReading) -> str:
    """Render an outside view, labeled as one in the first line."""
    lines = [
        f"## {reading.expert_name}, reading this from outside",
        "",
        "This is analogy, not evidence. My sources say nothing about your subject; what I am "
        "lending is a way of looking at it, and you should check whether the mapping holds "
        "before you rely on any of it.",
        "",
    ]
    if reading.standpoint:
        lines += [f"_How I read my own subject: {reading.standpoint}_", ""]

    if not reading.observations:
        lines.append("My frame does not reach this. A forced analogy would be worse than none.")
        return "\n".join(lines)

    lines.append("**What my frame notices here**")
    lines += [f"- {item}" for item in reading.observations]
    lines.append("")

    if reading.where_it_breaks:
        lines.append("**Where the analogy stops holding**")
        lines += [f"- {item}" for item in reading.where_it_breaks]
    else:
        lines.append(
            "**No limits stated.** An analogy that names nowhere it breaks is being offered as a "
            "fact; treat every line above as less certain than it reads."
        )
    return "\n".join(lines)
