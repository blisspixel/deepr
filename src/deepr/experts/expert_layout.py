"""Where the parts of an expert live, named from the expert's point of view.

The old layout was named after the commands that wrote it - `study.json`,
`brief.json`, `viva.json` - which is the fact-list frame leaking into the
filesystem. A directory listing said which processes had run, not what the
expert was. That shapes what gets built next: a file called `positions.json`
invites features about positions.

Two things in it were actively confusing rather than merely process-named.
`brief.json` and `positions.json` were the same subject stored twice under
names that did not say which was the current view and which the history. And
`profile.json` and `profile_card.json` were two different things both called
profile, one a v1 config record and the other the expert's own account of
itself.

The layout now reads as an answer to "what is this expert":

    self.json      who I am - the name I chose, how I read this subject,
                   my voice, what I refuse to do
    corpus/        what I have read
    noticed/       what I found in it
    hold/          what I think, and what I used to think
      history.jsonl  every view I have held, with what moved it
      current.json   what I hold now, which is what a consult reads
    became/        the chain of what changed me
    attend/        what I am chasing, and where I look
    met/           what has been put to me - consults, examinations

**`corpus/` deliberately does not move.** It is already named from the expert's
side rather than after a verb, "corpus" is the accurate word for a body of
retained text, and it is a content-addressed store with an index - the highest
risk rename available for the least conceptual gain.

**Reads fall back to the old path; writes always use the new one.** That is
what makes the migration safe to run gradually: an expert that has not been
migrated is fully readable, and one that has been is written correctly, with no
window where a reader finds nothing. The fallback is not permanent - it exists
so the fleet can move without a flag day, and can be removed once no old-layout
expert remains.
"""

from __future__ import annotations

from pathlib import Path

from deepr.experts import paths as _paths


def canonical_expert_dir(expert_name: str) -> Path:
    """Look the root up through the module, not through a bound name.

    `from ... import canonical_expert_dir` would capture the function at import
    time, and tests redirect the expert root by patching the attribute on
    `deepr.experts.paths`. A bound name ignores that and every path helper here
    would silently resolve against the real fleet directory during tests.
    """
    return _paths.canonical_expert_dir(expert_name)


EXPERT_LAYOUT_SCHEMA_VERSION = "deepr-expert-layout-v2"

DEAD_V1_DIRS = ("conversations", "documents")
"""Directories the v1 path created and never filled. Empty across the fleet.

`beliefs/` and `knowledge/` were on this list until a dry run over the real
fleet showed 38 and 35 experts with content in them - belief ledgers, event
logs, mutation audits, digests and subscriptions, about 4MB in total. They are
live v1 storage, not leftovers, and they keep both their names and their
contents here. Renaming storage that something still writes is a separate piece
of work from renaming the artifacts of the study loop.

Removed on migration only when empty, so an operator with real data in one of
these does not lose it to a cosmetic change."""


#: Logical part -> (new relative path, old relative path).
#: One table so a reader, a writer and the migration cannot disagree about
#: where something lives.
_PARTS: dict[str, tuple[str, str]] = {
    "self": ("self.json", "profile_card.json"),
    "noticed": ("noticed/current.json", "study.json"),
    "noticed_rendered": ("noticed/current.md", "study.md"),
    "hold_current": ("hold/current.json", "brief.json"),
    "hold_rendered": ("hold/current.md", "brief.md"),
    "hold_history": ("hold/history.json", "positions.json"),
    "became": ("became/perspective.json", "graph/perspective.json"),
    "attend": ("attend/practice.json", "practice.json"),
    "attend_rendered": ("attend/practice.md", "practice.md"),
    "met_examination": ("met/examination.json", "viva.json"),
    "met_examination_rendered": ("met/examination.md", "viva.md"),
}


def part_in(expert_dir: Path, part: str) -> Path:
    """Resolve a logical part inside an expert directory.

    Returns the new path unless only the old one exists, so reads work both
    before and after migration and writes always land in the new layout
    because the old path is never created again.
    """
    try:
        new, old = _PARTS[part]
    except KeyError:
        raise KeyError(f"unknown expert layout part: {part!r}") from None
    candidate = expert_dir / new
    if candidate.exists():
        return candidate
    legacy = expert_dir / old
    return legacy if legacy.exists() else candidate


#: New relative path -> old relative path, for callers that hold a path
#: rather than a part name (the stage contract names its artifacts by path).
_BY_NEW_PATH: dict[str, str] = {new: old for new, old in _PARTS.values()}


def resolve_relative(expert_dir: Path, relative: str) -> Path:
    """Resolve a new-layout relative path, falling back to its old location.

    A path with no old counterpart - `corpus/index.jsonl`, `graph/evidence.json` -
    resolves to itself, so callers can pass every artifact they care about
    through one function rather than branching on which ones moved.
    """
    old = _BY_NEW_PATH.get(relative)
    if old is None:
        return expert_dir / relative
    candidate = expert_dir / relative
    if candidate.exists():
        return candidate
    legacy = expert_dir / old
    return legacy if legacy.exists() else candidate


def part(expert_name: str, name: str) -> Path:
    """Resolve a logical part by expert name."""
    return part_in(canonical_expert_dir(expert_name), name)


def self_path(expert_name: str) -> Path:
    """Who this expert is, in its own account. Was `profile_card.json`."""
    return part(expert_name, "self")


def corpus_dir(expert_name: str) -> Path:
    """What it has read. Unchanged, and deliberately."""
    return canonical_expert_dir(expert_name) / "corpus"


def noticed_path(expert_name: str) -> Path:
    """What it found in what it read. Was `study.json`."""
    return part(expert_name, "noticed")


def hold_current_path(expert_name: str) -> Path:
    """What it holds now. Was `brief.json`, and is what a consult reads."""
    return part(expert_name, "hold_current")


def hold_history_path(expert_name: str) -> Path:
    """Every view it has held, with what moved it. Was `positions.json`."""
    return part(expert_name, "hold_history")


def hold_rendered_path(expert_name: str) -> Path:
    """The readable form of what it holds. Was `brief.md`."""
    return part(expert_name, "hold_rendered")


def became_path(expert_name: str) -> Path:
    """The chain of what changed it. Was `graph/perspective.json`."""
    return part(expert_name, "became")


def attend_path(expert_name: str) -> Path:
    """What it is chasing and where it looks. Was `practice.json`."""
    return part(expert_name, "attend")


def met_examination_path(expert_name: str) -> Path:
    """The last examination put to it. Was `viva.json`."""
    return part(expert_name, "met_examination")


def evidence_graph_path(expert_name: str) -> Path:
    """What rests on what. Stays under `graph/`; it is a derived structure."""
    return canonical_expert_dir(expert_name) / "graph" / "evidence.json"


def portrait_path(expert_name: str, *, suffix: str = ".png") -> Path:
    """The face it chose for itself, beside the rest of its identity."""
    return canonical_expert_dir(expert_name) / f"self{suffix}"


#: Old name -> new name, derived from the same table the readers use so the
#: migration cannot move a file somewhere a reader will not look for it.
MOVES: tuple[tuple[str, str], ...] = tuple((old, new) for new, old in _PARTS.values())


def is_migrated(expert_name: str) -> bool:
    """Whether this expert already uses the new layout.

    Keyed on `hold/`, because that is the rename that carries meaning: an
    expert whose views live there has been through the migration, and one
    whose views are still in `brief.json` has not.
    """
    return (canonical_expert_dir(expert_name) / "hold").is_dir()
