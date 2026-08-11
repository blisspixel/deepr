"""Positions that survive a re-brief, and a record of what changed them.

The defect this removes is the largest destruction of judgement in the system.
`build_brief` takes a study and a corpus and no prior brief, then overwrites
`brief.json` wholesale. Every run discards the previous positions - their
likelihood bands, their falsifiers, and the dissent they carried - and derives
new ones from scratch. An expert that has existed six months has read more than
a new one and has concluded nothing that outlived its last run.

Three things become possible once a position has an identity and a history, and
none of them is possible without both:

- **A falsifier becomes a prediction.** "What would change my mind" is only a
  registered expectation if the thing it is attached to still exists when the
  evidence arrives. Against a positional id it is worthless: a re-brief makes
  `position-3` a different question.
- **Survival becomes evidence.** A position that has been re-derived across
  four corpus states is a different claim from one written once, and the
  difference is exactly what elapsed time is supposed to buy.
- **A revision becomes distinguishable from a replacement.** Which is the
  reversibility property that keeps `brief` out of unattended operation.

**The ledger is the record; `brief.json` stays the current view.** Every reader
in the system - consult, health, the graph, the profile, the stage contract -
loads `brief.json`, and changing its shape to a version log would break all of
them to serve one new reader. So versions append here, and the brief is derived
from the live ones. That is also the shape the belief store already uses, which
is the one part of Deepr that has always kept its history.

**Only the record axis is stored.** `recorded_at` and `superseded_at`, closed-
open, sentinel-terminated, never rewritten. Valid time and belief time are
sparse and cannot back a snapshot; a position carries an optional `held` block
for the case where a viva names the moment a view was abandoned, and it is an
annotation rather than a queryable axis. The reasoning is in
``expert-v2-identity-and-time.md``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from deepr.experts.record_identity import normalize_text, position_thread_id, version_id
from deepr.experts.record_time import END_OF_TIME, contains, is_open, utc_now

POSITION_LEDGER_SCHEMA_VERSION = "deepr-position-ledger-v1"

REASON_REVISED = "revised"
"""The expert restated this position differently. The common case."""

REASON_NOT_RESTATED = "not_restated"
"""A re-brief over the same subject did not produce this position at all.

Deliberately not called "retired". The expert did not decide to drop it; a
later pass simply did not arrive at it, which is weaker evidence and should
read as weaker. A position that vanishes quietly across several rebuilds is
worth looking at, and calling it retired would hide that."""

REASON_OPERATOR_RETIRED = "operator_retired"
REASON_SOURCE_RETRACTED = "retracted_by_source"

_REASONS = (REASON_REVISED, REASON_NOT_RESTATED, REASON_OPERATOR_RETIRED, REASON_SOURCE_RETRACTED)


@dataclass
class PositionVersion:
    """One statement of one position, and when the store held it."""

    thread_id: str
    """Which question this is about. Stable across every revision."""
    version_id: str
    """Which statement of it this is. Changes whenever the content does."""
    question: str
    stance: str = ""
    likelihood: str = ""
    confidence: str = ""
    would_change_my_mind: str = ""
    unresolved_dissent: str = ""
    supported_by: list[str] = field(default_factory=list)

    recorded_at: str = ""
    superseded_at: str = END_OF_TIME
    superseded_by: str = ""
    supersession_reason: str = ""
    corpus_fingerprint: str = ""
    """The corpus this statement was first formed over."""
    corroborated_over: list[str] = field(default_factory=list)
    """Later corpus states this same statement was reached again from.

    Separate from ``corpus_fingerprint`` because they answer different
    questions: where the view came from, and how many times it has been
    re-derived from material it had not already seen. Overwriting the first
    with the second loses both."""
    seq: int = 0
    """Tie-break within one instant.

    Two versions can share a timestamp at this resolution, and ordering has to
    be total or `as_of` at that instant is ambiguous. Keeping a real timestamp
    plus a counter beats the alternative already in this codebase, which nudges
    the timestamp forward a microsecond and makes it a lie."""

    @property
    def is_live(self) -> bool:
        return is_open(self.superseded_at)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_live"] = self.is_live
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PositionVersion:
        return cls(
            thread_id=str(data.get("thread_id") or ""),
            version_id=str(data.get("version_id") or ""),
            question=str(data.get("question") or ""),
            stance=str(data.get("stance") or ""),
            likelihood=str(data.get("likelihood") or ""),
            confidence=str(data.get("confidence") or ""),
            would_change_my_mind=str(data.get("would_change_my_mind") or ""),
            unresolved_dissent=str(data.get("unresolved_dissent") or ""),
            supported_by=list(data.get("supported_by") or []),
            recorded_at=str(data.get("recorded_at") or ""),
            superseded_at=str(data.get("superseded_at") or END_OF_TIME),
            superseded_by=str(data.get("superseded_by") or ""),
            supersession_reason=str(data.get("supersession_reason") or ""),
            corpus_fingerprint=str(data.get("corpus_fingerprint") or ""),
            corroborated_over=[str(f) for f in (data.get("corroborated_over") or [])],
            seq=int(data.get("seq", 0) or 0),
        )


def _content_of(position: Any) -> str:
    """What makes one statement different from another.

    The question is excluded on purpose - it is the thread identity, and
    including it would make every version differ from every other only because
    they share a subject.
    """
    parts = [
        str(getattr(position, "stance", "") or ""),
        str(getattr(position, "likelihood", "") or ""),
        str(getattr(position, "confidence", "") or ""),
        str(getattr(position, "would_change_my_mind", "") or ""),
        str(getattr(position, "unresolved_dissent", "") or ""),
        ",".join(sorted(str(f) for f in (getattr(position, "supported_by", None) or []))),
    ]
    return "\n\x00".join(parts)


def version_from_position(position: Any, *, at: str, corpus_fingerprint: str = "", seq: int = 0) -> PositionVersion:
    """Turn a freshly briefed position into a recordable version."""
    question = str(getattr(position, "question", "") or "")
    return PositionVersion(
        thread_id=position_thread_id(question),
        version_id=version_id(_content_of(position)),
        question=question,
        stance=str(getattr(position, "stance", "") or ""),
        likelihood=str(getattr(position, "likelihood", "") or ""),
        confidence=str(getattr(position, "confidence", "") or ""),
        would_change_my_mind=str(getattr(position, "would_change_my_mind", "") or ""),
        unresolved_dissent=str(getattr(position, "unresolved_dissent", "") or ""),
        supported_by=[str(f) for f in (getattr(position, "supported_by", None) or [])],
        recorded_at=at,
        corpus_fingerprint=corpus_fingerprint,
        seq=seq,
    )


@dataclass
class PositionLedger:
    """Every version of every position this expert has held."""

    expert_name: str
    schema_version: str = POSITION_LEDGER_SCHEMA_VERSION
    versions: list[PositionVersion] = field(default_factory=list)

    @property
    def live(self) -> list[PositionVersion]:
        """What the expert holds now. The default read."""
        return [v for v in self.versions if v.is_live]

    def history_of(self, thread_id: str) -> list[PositionVersion]:
        """Every statement of one position, oldest first."""
        return sorted(
            (v for v in self.versions if v.thread_id == thread_id),
            key=lambda v: (v.recorded_at, v.seq),
        )

    def as_of(self, at: str) -> list[PositionVersion]:
        """What the expert held at a moment, by record time.

        One axis, because it is the only total one. A version with no
        `recorded_at` - written before this ledger existed - is treated as
        having always applied rather than never, so a migrated store reads as
        live instead of silently empty.
        """
        return [v for v in self.versions if contains(v.recorded_at, v.superseded_at, at)]

    def survived(self, thread_id: str) -> int:
        """How many distinct corpus states this position has been re-derived over.

        The number that makes elapsed time into evidence. A position restated
        across four corpus fingerprints has been reached again from material it
        had not seen, which is different from one written once and copied.
        """
        seen: set[str] = set()
        for version in self.history_of(thread_id):
            if version.corpus_fingerprint:
                seen.add(version.corpus_fingerprint)
            seen.update(f for f in version.corroborated_over if f)
        return len(seen)

    def stats(self) -> dict[str, Any]:
        live = self.live
        return {
            "threads": len({v.thread_id for v in self.versions}),
            "versions": len(self.versions),
            "live": len(live),
            "revised": sum(1 for v in self.versions if v.supersession_reason == REASON_REVISED),
            "not_restated": sum(1 for v in self.versions if v.supersession_reason == REASON_NOT_RESTATED),
            "max_survived": max((self.survived(v.thread_id) for v in live), default=0),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "expert": self.expert_name,
            "stats": self.stats(),
            "versions": [v.to_dict() for v in self.versions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PositionLedger:
        ledger = cls(expert_name=str(data.get("expert") or ""))
        for raw in data.get("versions") or []:
            if isinstance(raw, dict) and raw.get("thread_id"):
                ledger.versions.append(PositionVersion.from_dict(raw))
        return ledger


def record_brief(
    ledger: PositionLedger,
    positions: list[Any],
    *,
    at: str = "",
    corpus_fingerprint: str = "",
) -> dict[str, int]:
    """Fold a fresh brief into the ledger. Returns what changed.

    Three outcomes per thread, and the distinctions are the point:

    - **unchanged**: the expert restated the same position identically. No new
      version, because a version that differs in nothing is noise, and the
      ledger's job is to make real change visible.
    - **revised**: same question, different statement. The prior version closes
      and a new one opens, so the pair is a recorded change of mind rather than
      a replacement.
    - **not restated**: a live position this brief did not produce. Closed with
      a reason that says only that, because the expert did not decide to drop
      it - a later pass simply did not arrive at it, and that is weaker
      evidence than a retirement.

    New threads are appended. Nothing is ever deleted.
    """
    stamp = at or utc_now()
    changed = {"new": 0, "revised": 0, "unchanged": 0, "not_restated": 0}

    live_by_thread = {v.thread_id: v for v in ledger.live}
    seen_threads: set[str] = set()
    seq = max((v.seq for v in ledger.versions), default=0)

    for position in positions:
        if not str(getattr(position, "question", "") or "").strip():
            continue
        seq += 1
        fresh = version_from_position(position, at=stamp, corpus_fingerprint=corpus_fingerprint, seq=seq)
        seen_threads.add(fresh.thread_id)
        prior = live_by_thread.get(fresh.thread_id)

        if prior is None:
            ledger.versions.append(fresh)
            changed["new"] += 1
            continue

        if prior.version_id == fresh.version_id:
            # Identical restatement. Record that it survived this corpus state
            # without adding a version: survival is counted by fingerprint, so
            # the evidence is kept and the noise is not.
            if (
                corpus_fingerprint
                and corpus_fingerprint != prior.corpus_fingerprint
                and corpus_fingerprint not in prior.corroborated_over
            ):
                prior.corroborated_over.append(corpus_fingerprint)
            changed["unchanged"] += 1
            continue

        prior.superseded_at = stamp
        prior.superseded_by = fresh.version_id
        prior.supersession_reason = REASON_REVISED
        ledger.versions.append(fresh)
        changed["revised"] += 1

    for thread_id, prior in live_by_thread.items():
        if thread_id in seen_threads:
            continue
        prior.superseded_at = stamp
        prior.supersession_reason = REASON_NOT_RESTATED
        changed["not_restated"] += 1

    return changed


def load_ledger(path: Path, *, expert_name: str = "") -> PositionLedger:
    """Read the ledger, or an empty one when there is none yet."""
    try:
        return PositionLedger.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return PositionLedger(expert_name=expert_name)


def find_thread(ledger: PositionLedger, question: str) -> str:
    """The thread id for a question, whether or not it is already held."""
    return position_thread_id(normalize_text(question))
