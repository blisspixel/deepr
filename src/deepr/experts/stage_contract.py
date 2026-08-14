"""What each stage needs before it runs, and what counts as having worked.

Written after asking Deepr's own harness-design expert what is wrong with
Deepr's expert loop. Its answer:

    Loose JSON handoffs create hidden coupling. Schema drift, partial writes,
    stale files, incompatible versions and missing provenance can silently
    corrupt later stages. [...] Producing every JSON file does not prove the
    final result is correct.

Both halves had already happened, twice, in a single afternoon. A synthesis
call timed out; the brief was written holding zero positions with the failure
recorded only as a limitation; the command exited 0 and printed the path as
though it had worked. The profile stage then read that file, found it present
and parseable, and produced a standpoint about *the pipeline failing* rather
than about the subject.

Each was fixed where it bit. This is the class fix, and the distinction it
turns on:

**Presence is not validity.** Every guard in the loop asked "does the file
exist and parse". The empty brief passed both. What a stage actually needs is
that its input carries the *content* the stage consumes - positions, findings,
a standpoint - and that is a different question with a different answer.

**A stage's own success is not its exit code.** A stage that produced a file is
not a stage that produced a result. Terminal success has to be stated
separately from "the process returned", because the failure mode is precisely a
process that returns cleanly having produced nothing usable.

This module is declarative on purpose. It owns no IO and calls no model: it
says what each stage requires and what its output must contain, and the CLI
enforces it. Keeping the rules in one readable table is what stops the next
silent corruption from needing its own bespoke guard bolted on after it bites.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

STAGE_CONTRACT_SCHEMA_VERSION = "deepr-stage-contract-v1"

STAGE_ACQUIRE = "acquire"
STAGE_STUDY = "study"
STAGE_BRIEF = "brief"
STAGE_PROFILE = "profile"
STAGE_GRAPH = "graph"
STAGE_PRACTICE = "practice"
STAGE_VIVA = "viva"


@dataclass(frozen=True)
class Requirement:
    """One thing a stage needs, and how to tell whether it is really there."""

    artifact: str
    """Path relative to the expert directory."""
    holds: Callable[[dict[str, Any]], bool]
    """Whether the parsed artifact carries what the stage consumes.

    Deliberately not "does it parse". A brief with zero positions parses
    perfectly and is useless to every stage downstream of it."""
    describe: str
    """What is missing, in words a person can act on."""
    fix: str
    """The command that would supply it."""


@dataclass(frozen=True)
class Stage:
    """A step in the loop: what it needs, and what its own output must contain."""

    name: str
    requires: tuple[Requirement, ...] = ()
    produces: str = ""
    """The artifact this stage writes."""
    succeeds_when: Callable[[dict[str, Any]], bool] | None = None
    """Whether the output is a result rather than merely a file.

    Separate from the process exit code, because the failure mode being
    guarded against is a process that exits cleanly having produced nothing
    usable."""
    success_means: str = ""


def _has_findings(study: dict[str, Any]) -> bool:
    return int((study.get("totals") or {}).get("findings", 0) or 0) > 0


def _has_grounded_findings(study: dict[str, Any]) -> bool:
    """Grounded, not merely present.

    A study whose findings anchor in nothing is a study that read the corpus
    and cited none of it, and briefing from it produces positions resting on
    text nobody can open.
    """
    return int((study.get("totals") or {}).get("grounded_findings", 0) or 0) > 0


def _position_cites_a_finding(position: dict[str, Any]) -> bool:
    """A position without a cited finding cannot be checked from the record."""
    question = str(position.get("question") or "").strip()
    supported = position.get("supported_by") or []
    return bool(question) and isinstance(supported, list) and any(str(item).strip() for item in supported)


def _has_positions(brief: dict[str, Any]) -> bool:
    """At least one position that cites the findings it rests on.

    A stance with an empty ``supported_by`` parses and used to count as
    success, so status reported the brief done while 'why do you think that'
    could not be answered.
    """
    positions = [p for p in (brief.get("positions") or []) if isinstance(p, dict)]
    return bool(positions) and all(_position_cites_a_finding(p) for p in positions)


def _has_standpoint(profile: dict[str, Any]) -> bool:
    return bool(str(profile.get("standpoint") or "").strip())


def _graph_is_formed(graph: dict[str, Any]) -> bool:
    return bool((graph.get("stats") or {}).get("is_formed"))


def _has_corpus(index: dict[str, Any]) -> bool:
    return int(index.get("active_count", 0) or 0) > 0


_STUDY_NEEDS_CORPUS = Requirement(
    artifact="corpus/index.jsonl",
    holds=_has_corpus,
    describe="no retained corpus, so there is nothing to read",
    fix="expert source",
)

_BRIEF_NEEDS_STUDY = Requirement(
    artifact="noticed/current.json",
    holds=_has_grounded_findings,
    describe="the study produced no grounded findings, so a brief would rest on nothing checkable",
    fix="expert study",
)

_NEEDS_BRIEF = Requirement(
    artifact="hold/current.json",
    holds=_has_positions,
    describe="the brief holds no positions, so the expert has not landed anywhere",
    fix="expert brief",
)

_NEEDS_PROFILE = Requirement(
    artifact="self.json",
    holds=_has_standpoint,
    describe="no standpoint recorded, so the expert has no reading of its own",
    fix="expert profile",
)


STAGES: tuple[Stage, ...] = (
    Stage(
        name=STAGE_ACQUIRE,
        produces="corpus/index.jsonl",
        succeeds_when=_has_corpus,
        success_means="at least one source retained",
    ),
    Stage(
        name=STAGE_STUDY,
        requires=(_STUDY_NEEDS_CORPUS,),
        produces="noticed/current.json",
        succeeds_when=_has_grounded_findings,
        success_means="at least one finding anchored in the retained text",
    ),
    Stage(
        name=STAGE_BRIEF,
        requires=(_BRIEF_NEEDS_STUDY,),
        produces="hold/current.json",
        succeeds_when=_has_positions,
        success_means="at least one position, each citing the findings it rests on",
    ),
    Stage(
        name=STAGE_PROFILE,
        requires=(_NEEDS_BRIEF,),
        produces="self.json",
        succeeds_when=_has_standpoint,
        success_means="a standpoint in the expert's own terms",
    ),
    Stage(
        name=STAGE_GRAPH,
        requires=(_BRIEF_NEEDS_STUDY, _NEEDS_BRIEF),
        produces="graph/evidence.json",
        succeeds_when=_graph_is_formed,
        success_means="at least one position reaching a passage through a finding",
    ),
    Stage(
        name=STAGE_PRACTICE,
        requires=(_NEEDS_BRIEF,),
        produces="attend/practice.json",
        succeeds_when=lambda p: bool((p.get("stats") or {}).get("live_pursuits")),
        success_means="at least one live pursuit to chase",
    ),
    Stage(
        name=STAGE_VIVA,
        requires=(_NEEDS_BRIEF,),
        produces="met/examination.json",
        succeeds_when=lambda v: bool(v.get("exchanges")),
        success_means="at least one question was put to the expert",
    ),
)

_BY_NAME = {stage.name: stage for stage in STAGES}


def get_stage(name: str) -> Stage | None:
    return _BY_NAME.get(name)


@dataclass
class Blocker:
    """Why a stage cannot run, and what would unblock it."""

    artifact: str
    reason: str
    fix: str

    def to_dict(self) -> dict[str, Any]:
        return {"artifact": self.artifact, "reason": self.reason, "fix": self.fix}


@dataclass
class StageState:
    """Where one stage stands for one expert."""

    name: str
    blockers: list[Blocker] = field(default_factory=list)
    produced: bool = False
    succeeded: bool = False
    success_means: str = ""

    @property
    def can_run(self) -> bool:
        return not self.blockers

    @property
    def status(self) -> str:
        """blocked, ready, failed, or done.

        ``failed`` is the one worth having: the artifact exists and does not
        carry what it promised. Without it, a stage that produced an empty file
        is indistinguishable from one that worked.
        """
        if self.blockers:
            return "blocked"
        if not self.produced:
            return "ready"
        return "done" if self.succeeded else "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.name,
            "status": self.status,
            "success_means": self.success_means,
            "blockers": [b.to_dict() for b in self.blockers],
        }


def evaluate_stage(stage: Stage, artifacts: dict[str, dict[str, Any] | None]) -> StageState:
    """Decide whether this stage can run, and whether its output is a result.

    ``artifacts`` maps a relative path to its parsed contents, or None when the
    file is absent or unreadable. Both are treated the same on purpose: an
    unparseable input is no more usable than a missing one, and quietly
    treating a corrupt file as present is how the corruption travels.
    """
    state = StageState(name=stage.name, success_means=stage.success_means)

    for requirement in stage.requires:
        data = artifacts.get(requirement.artifact)
        if data is None or not requirement.holds(data):
            state.blockers.append(
                Blocker(artifact=requirement.artifact, reason=requirement.describe, fix=requirement.fix)
            )

    output = artifacts.get(stage.produces) if stage.produces else None
    state.produced = output is not None
    if state.produced and stage.succeeds_when is not None:
        state.succeeded = bool(stage.succeeds_when(output or {}))
    return state


def evaluate_all(artifacts: dict[str, dict[str, Any] | None]) -> list[StageState]:
    """Where this expert stands across the whole loop."""
    return [evaluate_stage(stage, artifacts) for stage in STAGES]


def next_stage(states: list[StageState]) -> StageState | None:
    """The one thing to do next.

    A failed stage outranks a ready one: rerunning the stage that produced
    nothing usable is more useful than building further on top of it, and
    building on top is how a timed-out brief became a standpoint about the
    pipeline failing.
    """
    for state in states:
        if state.status == "failed":
            return state
    for state in states:
        if state.status == "ready":
            return state
    return None
