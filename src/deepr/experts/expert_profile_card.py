"""Who this expert is: how it came to its subject, and how it reads it now.

Not a fact list, and not a persona. A brief holds positions on questions; this
holds the thing underneath them - what the expert takes the subject to be
about, where it thinks the interesting problems are, what it has changed its
mind on, and what it is still uncertain enough about to want to read more.

Three things this exists to carry that a brief cannot.

**A standpoint.** Two experts can read one corpus and legitimately differ,
because much of what an expert knows is perspective rather than fact. An
expert that reports only what is settled is a search index; the value is in
the reading, and a reading has to belong to someone. So the expert names its
own orientation and says which lens it finds most revealing on this subject.

**A history of its own mind.** "I used to read this as X, and the March
sources moved me" is the sentence that separates six months of experience from
six months of accumulation. Perspective shifts are appended, never rewritten,
so an old expert can show the shape of its own learning rather than only its
latest state.

**Open questions it holds itself.** Not gaps in the corpus - questions the
expert finds genuinely unresolved and wants to pursue. That is the difference
between a system that answers and a researcher who is still working.

The name is the expert's own. Given a corpus and a reading of it, an expert
picks what to be called and how to write, and that is not decoration: in a
multi-expert consult, positions that all sound identical cannot be attributed,
and the council output collapses into one undifferentiated voice. A distinct
standpoint is what makes disagreement between experts legible as disagreement
rather than noise.

Style never touches calibration. Voice lives in rendering; likelihood,
confidence and falsifiers live in the typed fields, and a confident register
must never move a band.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PROFILE_SCHEMA_VERSION = "deepr-expert-profile-v1"

_MAX_FIELD_CHARS = 900
_MAX_ITEMS = 8


@dataclass
class PerspectiveShift:
    """One recorded change of mind, with what caused it."""

    at: str
    """When the shift was recorded, ISO-8601."""
    was: str
    now: str
    because: str = ""
    """What moved it. A shift with no cause is drift, not learning."""
    corpus_fingerprint: str = ""
    """The corpus as it stood when this shift happened."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExpertProfile:
    """The expert's own account of itself. Derived, but never overwritten."""

    expert_name: str
    schema_version: str = PROFILE_SCHEMA_VERSION
    chosen_name: str = ""
    """What the expert calls itself. Empty until it has read enough to choose."""
    standpoint: str = ""
    """How it reads this subject, in its own terms."""
    what_the_subject_is_about: str = ""
    """What the expert takes the real question to be, which is often not the
    question a newcomer would ask."""
    preferred_lens: str = ""
    """Which way of reading it finds most revealing here, and why."""
    open_questions: list[str] = field(default_factory=list)
    """What it is still working on. A researcher has these; an index does not."""
    where_it_is_weak: list[str] = field(default_factory=list)
    """What it knows it does not know well. Stated by the expert, not inferred."""
    voice: str = ""
    """How it writes: register and habits, derived from what it read."""
    glad_to_be_asked_about: list[str] = field(default_factory=list)
    """Where it most wants the question, and would dig in rather than summarize.

    An expert is not only open to learning, it is glad to be used. Naming what
    it would enjoy being asked is how a person decides which of forty experts
    to bring a problem to, and it is a different thing from what the expert
    happens to know."""
    shifts: list[PerspectiveShift] = field(default_factory=list)
    corpus_fingerprint: str = ""
    sources_read: int = 0

    @property
    def has_standpoint(self) -> bool:
        return bool(self.standpoint.strip())

    @property
    def has_changed_its_mind(self) -> bool:
        """An expert that never revised anything has not been tested by time."""
        return bool(self.shifts)

    def record_shift(self, *, at: str, was: str, now: str, because: str, fingerprint: str = "") -> None:
        """Append a change of mind. Never rewrites an earlier one.

        Overwriting would leave only the latest reading, which is exactly the
        state a new expert is in. The history is the experience.
        """
        if not was.strip() or not now.strip() or was.strip() == now.strip():
            return
        self.shifts.append(
            PerspectiveShift(
                at=at, was=was.strip(), now=now.strip(), because=because.strip(), corpus_fingerprint=fingerprint
            )
        )

    def concerns(self) -> list[str]:
        """What a reader should know about this profile itself."""
        notes: list[str] = []
        if not self.has_standpoint:
            notes.append(
                "This expert has no standpoint yet, so it can report what its sources say but has "
                "no reading of its own to offer."
            )
        if self.has_standpoint and not self.open_questions:
            notes.append(
                "A standpoint with no open questions is a finished opinion. Either the subject is "
                "genuinely closed, or the expert has stopped looking."
            )
        if self.has_standpoint and not self.where_it_is_weak:
            notes.append(
                "The expert names nothing it is weak on. That is possible, and it is also what a "
                "profile looks like when nobody asked."
            )
        return notes

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["has_standpoint"] = self.has_standpoint
        data["has_changed_its_mind"] = self.has_changed_its_mind
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpertProfile:
        profile = cls(
            expert_name=data.get("expert_name", ""),
            schema_version=data.get("schema_version", PROFILE_SCHEMA_VERSION),
            chosen_name=data.get("chosen_name", ""),
            standpoint=data.get("standpoint", ""),
            what_the_subject_is_about=data.get("what_the_subject_is_about", ""),
            preferred_lens=data.get("preferred_lens", ""),
            open_questions=list(data.get("open_questions") or []),
            where_it_is_weak=list(data.get("where_it_is_weak") or []),
            voice=data.get("voice", ""),
            glad_to_be_asked_about=list(data.get("glad_to_be_asked_about") or []),
            corpus_fingerprint=data.get("corpus_fingerprint", ""),
            sources_read=int(data.get("sources_read", 0) or 0),
        )
        profile.shifts = [
            PerspectiveShift(
                at=s.get("at", ""),
                was=s.get("was", ""),
                now=s.get("now", ""),
                because=s.get("because", ""),
                corpus_fingerprint=s.get("corpus_fingerprint", ""),
            )
            for s in (data.get("shifts") or [])
            if isinstance(s, dict)
        ]
        return profile


PROFILE_PROMPT = """You have read a corpus on "{expert_name}". Write your own profile.

This is not a summary of the material and not a persona. It is your account of how you read this
subject after reading it: what you take the real question to be, where you think the interesting
problems are, and what you are still working on.

You are not required to be certain. Much of what an expert knows is perspective rather than fact,
and on many questions there is no single reading of the evidence to converge on. Say how you read
it and own that it is a reading.

- "chosen_name": what you want to be called. Pick something that fits the subject and how you
  approach it, not a job title. This is how someone tells your view apart from another expert's
  in the same conversation.
- "standpoint": how you read this subject. What you emphasise, what you are sceptical of, and
  what you think most people get wrong about it.
- "what_the_subject_is_about": the real question underneath, which is usually not the question a
  newcomer arrives with.
- "preferred_lens": which way of reading this material you find most revealing, and why. Options
  include mechanism, failure, contention, absence, change, and the economic, operational,
  human/cultural, adversarial and institutional perspectives.
- "open_questions": what you are genuinely still working on. Not gaps in the corpus - questions
  you find unresolved and want to pursue.
- "where_it_is_weak": what you know you do not know well here. Be specific.
- "voice": how you write, in one or two sentences. This should follow from what you read: a
  corpus of formal specifications and one of practitioner writing do not produce the same voice.
- "glad_to_be_asked_about": the questions you would most want to be brought, and would dig into
  rather than summarize. Not what you know most about - what you would find it interesting to be
  asked. Someone choosing between forty experts uses this to pick.
{prior}
House style, which applies to every field: plain ASCII punctuation, a regular hyphen and never an
en dash or em dash, straight quotes, no emoji.

Return JSON only, no prose outside it, no code fence:

{{
  "chosen_name": "", "standpoint": "", "what_the_subject_is_about": "",
  "preferred_lens": "", "open_questions": [""], "where_it_is_weak": [""], "voice": "",
  "glad_to_be_asked_about": [""],
  "shift_from_prior": "", "shift_because": ""
}}

If your reading has changed from the prior standpoint above, say what it was in
"shift_from_prior" and what moved you in "shift_because". If it has not changed, leave both empty
rather than inventing a change.

===== WHAT YOU HAVE READ =====
{material}
===== END =====
"""


def parse_profile(
    parsed: dict[str, Any],
    *,
    expert_name: str,
    at: str,
    prior: ExpertProfile | None = None,
    corpus_fingerprint: str = "",
    sources_read: int = 0,
) -> ExpertProfile:
    """Build a profile from what the model returned, carrying the history forward.

    The two halves of this are separate on purpose. ``from_dict`` reads a
    profile that was already persisted, so ``shifts`` are already in it. This
    reads a fresh model reply, where the shift is reported as a *pair of loose
    fields* (``shift_from_prior``, ``shift_because``) and the prior profile's
    accumulated shifts live somewhere else entirely - on the prior object.

    Without this step a re-profile silently drops every recorded change of
    mind, which would make the one artifact in this system that tracks a
    revision lossy on exactly the operation that produces revisions.
    """
    profile = ExpertProfile.from_dict({**parsed, "expert_name": expert_name})
    profile.corpus_fingerprint = corpus_fingerprint
    profile.sources_read = sources_read

    if prior is not None:
        profile.shifts = list(prior.shifts)

    was = " ".join(str(parsed.get("shift_from_prior") or "").split())
    because = " ".join(str(parsed.get("shift_because") or "").split())
    if was and because and prior is not None:
        profile.record_shift(
            at=at,
            was=was,
            now=profile.standpoint,
            because=because,
            fingerprint=corpus_fingerprint,
        )
    return profile


def build_profile_prompt(expert_name: str, *, material: str, prior: ExpertProfile | None = None) -> str:
    """Ask the expert to account for itself, showing it its own prior reading."""
    prior_block = ""
    if prior is not None and prior.has_standpoint:
        prior_block = (
            f"\nYour prior standpoint, from an earlier reading:\n"
            f'  "{prior.standpoint[:_MAX_FIELD_CHARS]}"\n'
            "Consider whether the material has moved it. Changing your mind is expected; "
            "pretending to have changed it is not.\n"
        )
    return PROFILE_PROMPT.format(expert_name=expert_name, prior=prior_block, material=material)
