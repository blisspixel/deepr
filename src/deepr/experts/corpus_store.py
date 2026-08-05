"""Retained source corpus for an expert (pure, $0, no model, no network).

An expert that does not keep the material it learned from cannot be studied
again. It cannot be re-read through a second lens, cannot show the passage
behind a claim, and cannot be re-derived when understanding of the field
changes - the only recourse is to re-acquire everything from scratch.

Deepr v1 kept none of it: `absorb --file` extracted atomic claims, recorded the
token ``report:file:<basename>``, and discarded the text. Measured on the live
fleet, ``documents/`` and ``knowledge/`` were empty on every expert.

This module is the fix. Sources are stored content-addressed under the expert's
canonical directory, with a sidecar index carrying origin identity and trust.

Design notes:

- **Content-addressed.** Re-absorbing unchanged material is a no-op, so a
  refresh cadence does not duplicate storage or inflate origin counts.
- **Origin key is not the file.** Many files routinely come from one publisher.
  Origin identity collapses to the publisher so corroboration counts stay
  honest; see :func:`deepr.experts.beliefs.Belief._independent_source_count`.
- **Containment.** Every write resolves under the expert directory. Corpus text
  is untrusted input and a path in its metadata must never escape.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deepr.experts.paths import canonical_expert_dir
from deepr.utils.atomic_io import atomic_write_text

CORPUS_SCHEMA_VERSION = "deepr-expert-corpus-v1"

_TRUST_CLASSES = ("primary", "secondary", "tertiary")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class CorpusEntry:
    """One retained source. Metadata only; text lives beside it by hash."""

    sha256: str
    origin_key: str
    title: str = ""
    url: str = ""
    publisher: str = ""
    kind: str = ""
    trust_class: str = "secondary"
    byte_len: int = 0
    fetched_at: str = ""
    added_at: str = ""
    superseded_by: str = ""
    """sha256 of a later revision of the same source, when one arrives."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorpusEntry:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    @property
    def is_active(self) -> bool:
        return not self.superseded_by


@dataclass
class CorpusStats:
    """Structural counts. Says nothing about whether the corpus is any good."""

    entry_count: int = 0
    active_count: int = 0
    distinct_origins: int = 0
    total_bytes: int = 0
    trust_mix: dict[str, int] = field(default_factory=dict)
    publishers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def content_hash(text: str) -> str:
    """Stable identity for source text.

    Newlines are normalized first so the same document fetched on Windows and
    Linux is one entry rather than two, which would otherwise read as two
    independent origins.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class CorpusStore:
    """Content-addressed source retention for one expert."""

    def __init__(self, expert_name: str, *, storage_dir: Path | None = None) -> None:
        self.expert_name = expert_name
        base = Path(storage_dir) if storage_dir else canonical_expert_dir(expert_name) / "corpus"
        self.root = base
        self.sources_dir = self.root / "sources"
        self.index_path = self.root / "index.jsonl"
        self.entries: dict[str, CorpusEntry] = {}
        self._load()

    # -- persistence ----------------------------------------------------- #

    def _load(self) -> None:
        if not self.index_path.exists():
            return
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                # A torn line must not make the whole corpus unreadable.
                continue
            if payload.get("schema_version") == CORPUS_SCHEMA_VERSION:
                continue
            entry = CorpusEntry.from_dict(payload)
            if entry.sha256:
                self.entries[entry.sha256] = entry

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        header = json.dumps({"schema_version": CORPUS_SCHEMA_VERSION, "expert": self.expert_name})
        lines = [header]
        lines.extend(json.dumps(entry.to_dict(), sort_keys=True) for _, entry in sorted(self.entries.items()))
        atomic_write_text(self.index_path, "\n".join(lines) + "\n")

    def _source_path(self, sha: str) -> Path:
        # Two-level fan-out keeps directory listings usable at fleet scale.
        return self.sources_dir / sha[:2] / f"{sha}.md"

    # -- writes ---------------------------------------------------------- #

    def add(
        self,
        text: str,
        *,
        origin_key: str,
        title: str = "",
        url: str = "",
        publisher: str = "",
        kind: str = "",
        trust_class: str = "secondary",
        fetched_at: str = "",
    ) -> tuple[CorpusEntry, bool]:
        """Retain one source. Returns (entry, was_new).

        Idempotent by content: re-adding identical text returns the existing
        entry and writes nothing, so a refresh cadence is cheap and does not
        inflate origin counts.
        """
        if not text or not text.strip():
            raise ValueError("refusing to retain empty source text")
        resolved_trust = str(trust_class or "secondary").strip().lower()
        if resolved_trust not in _TRUST_CLASSES:
            raise ValueError(f"trust_class must be one of {_TRUST_CLASSES}, got {trust_class!r}")
        if not origin_key or not origin_key.strip():
            raise ValueError("origin_key is required: it is what keeps corroboration honest")

        sha = content_hash(text)
        existing = self.entries.get(sha)
        if existing is not None:
            return existing, False

        path = self._source_path(sha)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, text)

        entry = CorpusEntry(
            sha256=sha,
            origin_key=origin_key.strip(),
            title=title.strip(),
            url=url.strip(),
            publisher=publisher.strip(),
            kind=kind.strip(),
            trust_class=resolved_trust,
            byte_len=len(text.encode("utf-8")),
            fetched_at=fetched_at or "",
            added_at=_utc_now_iso(),
        )
        self.entries[sha] = entry
        self._save()
        return entry, True

    def supersede(self, old_sha: str, new_sha: str) -> bool:
        """Mark one entry as replaced by a later revision.

        The old text is never deleted. Knowing what a source used to say is how
        an expert can show that its understanding changed rather than silently
        presenting the new version as if it had always been so.
        """
        old = self.entries.get(old_sha)
        if old is None or new_sha not in self.entries:
            return False
        old.superseded_by = new_sha
        self._save()
        return True

    # -- reads ----------------------------------------------------------- #

    def read(self, sha: str) -> str | None:
        path = self._source_path(sha)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def active_entries(self) -> list[CorpusEntry]:
        return [e for e in self.entries.values() if e.is_active]

    def entries_for_origin(self, origin_key: str) -> list[CorpusEntry]:
        return [e for e in self.entries.values() if e.origin_key == origin_key]

    def distinct_origins(self) -> set[str]:
        return {e.origin_key for e in self.entries.values() if e.is_active}

    def stats(self) -> CorpusStats:
        active = self.active_entries()
        trust_mix: dict[str, int] = {}
        for entry in active:
            trust_mix[entry.trust_class] = trust_mix.get(entry.trust_class, 0) + 1
        publishers = sorted({e.publisher for e in active if e.publisher})
        return CorpusStats(
            entry_count=len(self.entries),
            active_count=len(active),
            distinct_origins=len(self.distinct_origins()),
            total_bytes=sum(e.byte_len for e in active),
            trust_mix=trust_mix,
            publishers=publishers,
        )

    def load_study_material(self, *, max_chars: int = 0) -> list[tuple[CorpusEntry, str]]:
        """Active sources with their text, ordered deterministically.

        Ordering is by (origin_key, sha) so two study runs over an unchanged
        corpus see identical material and stay comparable. When ``max_chars`` is
        set, whole sources are included until the budget is reached; a source is
        never truncated mid-way, because a lens reading half a document reports
        absences that are artifacts of the cut.
        """
        ordered = sorted(self.active_entries(), key=lambda e: (e.origin_key, e.sha256))
        out: list[tuple[CorpusEntry, str]] = []
        used = 0
        for entry in ordered:
            text = self.read(entry.sha256)
            if text is None:
                continue
            if max_chars and used + len(text) > max_chars and out:
                break
            out.append((entry, text))
            used += len(text)
        return out
