"""One card per source: what this document is, and what it establishes.

The study pass reads chunks and merges findings. Findings are fragments, and
fragments do not compose - nothing in the pipeline ever said "here is what
this source is, taken whole." That leaves two problems. Cross-document work
has no unit to reason over, and the corpus cannot grow, because the cost of
understanding it scales with total text rather than with the number of
documents.

A card fixes both by making the *document* the unit:

- **Bounded.** One call per source, one compact record out, however long the
  source was. Fifty sources produce fifty cards that still fit in a prompt
  when fifty sources of raw text never would.
- **Incremental.** A new source adds a card and recomputes nothing else. An
  expert grows a document at a time instead of being rebuilt.
- **Readable.** The cards are the layer a person can actually read to learn
  the subject, and cross-linked they are the wiki.

A card is not a summary. Summarizing is the low-value operation: it compresses
and loses the specifics that made the source worth keeping. A card records
what the source *is*, what it establishes, what it leans on, and where it
stops - the things you need to decide whether to go read it, and what it can
be used to support.

Every claim carries a verbatim anchor, checked against the retained text the
same way study findings are. Decontextualisation is the known weak point in
this shape of extraction - roughly one claim in five comes out mis-scoped
regardless of technique - so the anchor is what lets a reader put a claim back
in its setting rather than trusting the extraction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

CARD_SCHEMA_VERSION = "deepr-source-card-v1"

_MAX_CLAIMS = 12
_MAX_LIST_ITEMS = 8
_MAX_FIELD_CHARS = 800


@dataclass
class CardClaim:
    """One thing this source states, with the passage that states it."""

    statement: str
    anchor: str = ""
    hedged: bool = False
    """True when the source itself qualifies this rather than asserting it."""
    is_grounded: bool = False
    """Whether the anchor was found verbatim in the retained text."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceCard:
    """A complete read of one document."""

    sha256: str
    origin_key: str
    title: str = ""
    schema_version: str = CARD_SCHEMA_VERSION
    what_it_is: str = ""
    """Kind of document, who produced it, and when, in the source's own terms."""
    summary: str = ""
    """What it says, for someone deciding whether to read it."""
    establishes: list[str] = field(default_factory=list)
    """What this source can actually be used to support."""
    notable: list[str] = field(default_factory=list)
    """What is surprising or load-bearing here, as opposed to merely present."""
    stops_at: str = ""
    """Scope and limits, including what the source says it does not cover."""
    claims: list[CardClaim] = field(default_factory=list)
    leans_on: list[str] = field(default_factory=list)
    """Named upstream work this document rests on. The reuse graph starts here."""
    truncated_chars: int = 0
    """Source text not shown to the reader, when it exceeded the call budget."""
    error: str = ""

    @property
    def is_read(self) -> bool:
        """A card that carries nothing is a failed read, not a thin source."""
        return bool(self.summary or self.establishes or self.claims)

    @property
    def grounded_claims(self) -> list[CardClaim]:
        return [c for c in self.claims if c.is_grounded]

    def concerns(self) -> list[str]:
        """What a reader must know before leaning on this card."""
        notes: list[str] = []
        if self.error:
            notes.append(f"This source was not read: {self.error}")
            return notes
        if self.claims and not self.grounded_claims:
            notes.append(
                "No claim on this card could be located in the retained text, so nothing here is "
                "checkable against the source it came from."
            )
        if self.truncated_chars:
            notes.append(
                f"{self.truncated_chars:,} chars of this source were not read. The card describes the part that was."
            )
        return notes

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_read"] = self.is_read
        data["grounded_claim_count"] = len(self.grounded_claims)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceCard:
        card = cls(
            sha256=data.get("sha256", ""),
            origin_key=data.get("origin_key", ""),
            title=data.get("title", ""),
            schema_version=data.get("schema_version", CARD_SCHEMA_VERSION),
            what_it_is=data.get("what_it_is", ""),
            summary=data.get("summary", ""),
            establishes=list(data.get("establishes") or []),
            notable=list(data.get("notable") or []),
            stops_at=data.get("stops_at", ""),
            leans_on=list(data.get("leans_on") or []),
            truncated_chars=int(data.get("truncated_chars", 0) or 0),
            error=data.get("error", ""),
        )
        card.claims = [
            CardClaim(
                statement=c.get("statement", ""),
                anchor=c.get("anchor", ""),
                hedged=bool(c.get("hedged")),
                is_grounded=bool(c.get("is_grounded")),
            )
            for c in (data.get("claims") or [])
            if isinstance(c, dict)
        ]
        return card


CARD_PROMPT = """Read this source and write the card an expert would keep on it.

Not a summary. A card records what the source *is*, what it can be used to support, what is
notable in it, and where it stops - the things someone needs to decide whether to go and read
it, and what it may be cited for.

- Write for a reader who has not seen this document and may never read it.
- Preserve the specifics that make it usable later: named things, quantities, conditions,
  dates, defined terms. A card that drops the numbers is a card nobody can use.
- Separate what the source asserts from what it hedges. If it says "may" or "suggests", the
  claim is hedged; record it as such rather than promoting it.
- "establishes" is what this source can actually support, which is usually narrower than what
  it discusses.
- "notable" is what is surprising, load-bearing, or contrary to what a reader would expect.
  Not everything present is notable.
- "stops_at" is scope: what this source does not cover, and any limits it states about itself.
- "leans_on" names the upstream work this document rests on, when it names any.

Every claim needs an `anchor`: a phrase copied verbatim from the source. Do not paraphrase an
anchor. A claim you cannot anchor should not be reported.

Report only what this source contains. Do not add what you know from elsewhere.

House style, which applies to every field you return: write plain ASCII punctuation. Use a
regular hyphen, never an en dash or em dash. Use straight quotes, never curly ones. No emoji.
Prose, not decoration.

Return JSON only, no prose outside it, no code fence:

{{
  "what_it_is": "kind of document, who produced it, when",
  "summary": "what it says, for someone deciding whether to read it",
  "establishes": ["what this source can be used to support"],
  "notable": ["what is surprising or load-bearing here"],
  "stops_at": "scope and limits, including what it does not cover",
  "claims": [{{"statement": "", "anchor": "verbatim phrase", "hedged": false}}],
  "leans_on": ["named upstream work this rests on"]
}}

===== SOURCE {sha} | origin={origin}{title_part} =====
{text}
===== SOURCE ENDS =====
"""


def build_card_prompt(*, sha: str, origin: str, title: str, text: str) -> str:
    """One source, one prompt. Bounded by the source, not by the corpus."""
    return CARD_PROMPT.format(
        sha=sha[:12],
        origin=origin,
        title_part=f" | title={title}" if title else "",
        text=text,
    )
