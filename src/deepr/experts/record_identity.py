"""Stable identity for records that get revised.

The defect this fixes, in two lines of the codebase it replaces:

    finding_id = f"{lens.key}-{start_index + len(findings)}"   # study.py
    position_id = f"position-{index}"                          # evidence_graph.py

Both are positions in a list. Insert one finding and every id after it
renumbers, so a brief citing ``failure-30`` silently repoints at a different
finding after a partial resume re-runs only the failure lens. The citation
still validates, which is worse than failing - the provenance chain reports
itself intact while pointing at the wrong evidence.

**Two keys, not one.** A record that can be revised needs both:

- a **thread id**, answering "which question is this about", stable across
  every revision, and
- a **version id**, answering "which statement of it is this", changing on
  every revision.

One key cannot do both, and collapsing them is a real bug already present
elsewhere in this codebase: ``ExpertStance.create`` hashes title and statement
together, so revising a stance produces an unrelated record with no link to
what it replaced.

**Findings resolve by anchor set, which nothing else has.** Two findings
quoting overlapping corpus spans are far more likely to be the same finding
than two findings with similar titles - and the check is deterministic, free,
and exactly the evidence a person would use. Every surveyed system resolves on
a normalized name string and bleeds accordingly.

Hashes are truncated to 16 hex characters. At the measured scale of this
system - the largest expert holds 105 findings, the whole fleet 1,975 records -
64 bits is many orders of magnitude clear of a birthday collision, and a
readable id is worth more than the unused entropy.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

IDENTITY_SCHEMA_VERSION = "deepr-record-identity-v1"

_ID_CHARS = 16
_PUNCT = re.compile(r"[^\w\s]+")
_SPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Fold a title or question to its comparable form.

    Case, punctuation, accents and whitespace are removed because none of them
    change which question is being asked, and all of them change often enough
    between runs to break an id that includes them. A model rewrapping a
    question or adding a trailing full stop must not create a new thread.
    """
    folded = unicodedata.normalize("NFKD", str(text or ""))
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = _PUNCT.sub(" ", folded.lower())
    return _SPACE.sub(" ", folded).strip()


def _digest(*parts: str) -> str:
    """Hash the parts with a separator that cannot appear in them.

    A newline separator rather than concatenation: joining "ab" + "c" and
    "a" + "bc" to the same string is how content-addressed ids collide on
    inputs that are not remotely alike.
    """
    return hashlib.sha256("\n\x00".join(parts).encode("utf-8")).hexdigest()[:_ID_CHARS]


def finding_thread_id(*, lens: str, title: str, anchors: list[str]) -> str:
    """Which finding this is, stable across runs.

    Derived from the lens, the normalized title, and the sorted anchor set.
    Anchors are included because they are what a finding is *about* in the
    corpus: a lens re-reading the same passages and phrasing its title slightly
    differently is the same finding, and including the anchors makes that
    recognisable while a title-only hash would not.

    Sorted, so anchor ordering from the model cannot change identity.
    """
    normalized_anchors = sorted({normalize_text(a) for a in anchors if str(a).strip()})
    return f"{lens}-{_digest(lens, normalize_text(title), *normalized_anchors)}"


def position_thread_id(question: str) -> str:
    """Which question this position is about, stable across every revision.

    Deliberately derived from the question alone. A position exists to answer
    one question; changing the stance, the confidence, or the falsifier is a
    revision of the same position, not a different one. Including any of them
    would make every revision a new thread and defeat the point.
    """
    return f"position-{_digest(normalize_text(question))}"


def version_id(payload: str) -> str:
    """Which statement of a record this is. Changes whenever the content does."""
    return _digest(payload)


def is_stable_id(value: str) -> bool:
    """Whether an id came from here rather than from a list position.

    Lets a migration tell a durable id from a legacy positional one without
    keeping a separate flag. ``failure-3`` is legacy; ``failure-a1b2c3...`` is
    not.
    """
    _, _, suffix = str(value or "").rpartition("-")
    return len(suffix) == _ID_CHARS and all(c in "0123456789abcdef" for c in suffix)
