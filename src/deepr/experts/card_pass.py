"""Build and keep one card per retained source.

The pass is deliberately per-source and idempotent by content hash. A corpus
that gains one document costs one model call, not a re-read of everything,
which is what makes an expert something you grow rather than something you
rebuild. Cards for sources that have not changed are loaded from disk and not
re-derived, so a run over an unchanged corpus costs nothing at all.

Failure is per-source too. A source that fails to read leaves an error card
and the other forty-nine still get read, because a partial set of cards is
worth having and an aborted run is not.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deepr.experts.corpus_store import CorpusEntry, CorpusStore
from deepr.experts.source_card import (
    _MAX_CLAIMS,
    _MAX_FIELD_CHARS,
    _MAX_LIST_ITEMS,
    CardClaim,
    SourceCard,
    build_card_prompt,
)

CardCompletion = Callable[[str], Awaitable[str]]
ProgressCallback = Callable[[str], None]

_DEFAULT_SOURCE_BUDGET = 60_000


@dataclass
class CardPassResult:
    """What one pass produced, including what it did not have to do."""

    expert_name: str
    cards: list[SourceCard] = field(default_factory=list)
    reused: int = 0
    """Cards loaded from disk because the source had not changed."""
    built: int = 0
    failed: int = 0

    @property
    def exit_code(self) -> int:
        if not self.cards:
            return 2
        return 1 if self.failed else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert": self.expert_name,
            "totals": {
                "cards": len(self.cards),
                "built": self.built,
                "reused": self.reused,
                "failed": self.failed,
            },
            "cards": [card.to_dict() for card in self.cards],
        }


def cards_dir(expert_dir: Path) -> Path:
    return expert_dir / "cards"


def card_path(expert_dir: Path, sha: str) -> Path:
    return cards_dir(expert_dir) / f"{sha}.json"


def load_card(expert_dir: Path, sha: str) -> SourceCard | None:
    """A card already built for this exact content, or None."""
    path = card_path(expert_dir, sha)
    if not path.exists():
        return None
    try:
        return SourceCard.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def save_card(expert_dir: Path, card: SourceCard) -> Path:
    path = card_path(expert_dir, card.sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())[:_MAX_FIELD_CHARS]


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(v) for v in value if _text(v)][:_MAX_LIST_ITEMS]
    return [_text(value)] if _text(value) else []


def _claims_from(raw: Any, haystack: str) -> list[CardClaim]:
    """Build claims, checking each anchor against the retained text.

    Grounding is form, not merit: whether the phrase is really there. A claim
    whose anchor is absent stays on the card and is labeled, because deciding
    it is wrong is a judgment this layer does not get to make.
    """
    import re

    normalized = re.sub(r"\s+", " ", haystack).strip().lower()
    claims: list[CardClaim] = []
    for item in (raw or [])[:_MAX_CLAIMS]:
        if not isinstance(item, dict):
            continue
        statement = _text(item.get("statement"))
        if not statement:
            continue
        anchor = _text(item.get("anchor"))
        probe = re.sub(r"\s+", " ", anchor).strip().lower()
        claims.append(
            CardClaim(
                statement=statement,
                anchor=anchor,
                hedged=bool(item.get("hedged")),
                is_grounded=bool(probe) and len(probe) >= 12 and probe[:400] in normalized,
            )
        )
    return claims


def assemble_card(parsed: dict[str, Any], entry: CorpusEntry, text: str, truncated: int) -> SourceCard:
    """Turn one parsed response into a card anchored to its source."""
    return SourceCard(
        sha256=entry.sha256,
        origin_key=entry.origin_key,
        title=entry.title,
        what_it_is=_text(parsed.get("what_it_is")),
        summary=_text(parsed.get("summary")),
        establishes=_as_list(parsed.get("establishes")),
        notable=_as_list(parsed.get("notable")),
        stops_at=_text(parsed.get("stops_at")),
        claims=_claims_from(parsed.get("claims"), text),
        leans_on=_as_list(parsed.get("leans_on")),
        truncated_chars=truncated,
    )


async def build_one_card(
    entry: CorpusEntry,
    text: str,
    completion: CardCompletion,
    *,
    source_budget: int = _DEFAULT_SOURCE_BUDGET,
) -> SourceCard:
    """Read one source. Never raises: a failed read is a card with an error."""
    from deepr.experts.study import extract_json_object

    shown = text[:source_budget] if source_budget else text
    truncated = max(0, len(text) - len(shown))
    prompt = build_card_prompt(sha=entry.sha256, origin=entry.origin_key, title=entry.title, text=shown)

    try:
        raw = await completion(prompt)
    except Exception as exc:
        return SourceCard(
            sha256=entry.sha256,
            origin_key=entry.origin_key,
            title=entry.title,
            error=str(exc)[:200],
        )

    parsed, error = extract_json_object(raw)
    if parsed is None:
        snippet = " ".join((raw or "").split())[:160]
        return SourceCard(
            sha256=entry.sha256,
            origin_key=entry.origin_key,
            title=entry.title,
            error=f"{error}. Began: {snippet!r}" if snippet else error,
        )
    return assemble_card(parsed, entry, shown, truncated)


async def run_card_pass(
    *,
    expert_name: str,
    corpus: CorpusStore,
    expert_dir: Path,
    completion: CardCompletion,
    source_budget: int = _DEFAULT_SOURCE_BUDGET,
    rebuild: bool = False,
    on_progress: ProgressCallback | None = None,
) -> CardPassResult:
    """One card per active source, reusing cards whose source has not changed."""
    result = CardPassResult(expert_name=expert_name)
    material = corpus.load_study_material()

    for index, (entry, text) in enumerate(material, 1):
        if not rebuild and (existing := load_card(expert_dir, entry.sha256)) is not None:
            result.cards.append(existing)
            result.reused += 1
            continue

        if on_progress:
            on_progress(f"reading source {index}/{len(material)} ({entry.origin_key})")
        card = await build_one_card(entry, text, completion, source_budget=source_budget)
        save_card(expert_dir, card)
        result.cards.append(card)
        if card.error or not card.is_read:
            result.failed += 1
        else:
            result.built += 1

    return result
