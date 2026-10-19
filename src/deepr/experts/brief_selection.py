"""Choose which study findings a brief synthesis is shown, and say so.

The synthesis prompt cannot carry every finding of a large study. It used to
take the first 120 in outcome order and clip every field to 600 characters
without a trace. Outcome order is lens order, so the cap was really a lens
policy: a study whose synopsis lens produced 120 notes showed the synthesis
no contention finding at all, while the brief still counted every one of
them. A clipped field could lose the trailing condition that made a sentence
true and present the surviving prefix as complete.

This module makes the choice explicit and recorded:

- **Whole findings, balanced across lenses.** Findings are taken one per lens
  in turn, keeping each lens's own order. Every lens that produced anything is
  represented before any lens gets a second slot. This is a structural rule
  about coverage, not a judgment about which disagreement matters; that
  judgment stays with the synthesis model and later review.
- **Shortening is marked, never silent.** A field over the limit is cut at a
  sentence or word boundary and labelled with how much was kept and where the
  full text lives. The full study stays the drill-down.
- **The selection is a receipt.** Presented and omitted finding ids, every
  shortened field, and the exact prompt hash travel with the brief, so nobody
  can later claim the whole study reached synthesis when it did not.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from deepr.experts.study_contracts import StudyFinding, StudyResult

SELECTION_POLICY = "lens-balanced-whole-findings-v1"
MAX_FINDINGS_IN_PROMPT = 120
MAX_FIELD_CHARS = 600

_SENTENCE_END_RE = re.compile(r"[.;!?](?=\s)")


@dataclass
class ShortenedField:
    finding_id: str
    field: str
    original_chars: int
    kept_chars: int


@dataclass
class BriefSelection:
    """What the brief synthesis was actually shown from one study."""

    policy: str = SELECTION_POLICY
    study_fingerprint: str = ""
    total_findings: int = 0
    presented_ids: list[str] = field(default_factory=list)
    omitted_ids: list[str] = field(default_factory=list)
    shortened: list[ShortenedField] = field(default_factory=list)
    contention_total: int = 0
    contention_presented: int = 0
    prompt_sha256: str = ""
    prompt_chars: int = 0

    @property
    def complete(self) -> bool:
        """True only when every finding reached synthesis unshortened."""
        return not self.omitted_ids and not self.shortened

    def limitations(self) -> list[str]:
        """Plain statements of what the synthesis did not see in full."""
        notes: list[str] = []
        if self.omitted_ids:
            notes.append(
                f"Synthesis was shown {len(self.presented_ids)} of {self.total_findings} study findings "
                f"({self.policy}). Positions cannot rest on the {len(self.omitted_ids)} omitted finding(s); "
                "the full study remains the record."
            )
        if self.contention_total > self.contention_presented:
            notes.append(
                f"{self.contention_total - self.contention_presented} of {self.contention_total} contention "
                "finding(s) were not shown to synthesis, so disagreement in them cannot have been carried forward."
            )
        if self.shortened:
            notes.append(
                f"{len(self.shortened)} finding field(s) were shortened for synthesis and marked as shortened; "
                "the full text remains in the study."
            )
        return notes

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["complete"] = self.complete
        return data

    @classmethod
    def from_dict(cls, data: Any) -> BriefSelection | None:
        """Read a persisted receipt; None for legacy briefs that never recorded one."""
        if not isinstance(data, dict) or not data:
            return None
        shortened = [
            ShortenedField(
                finding_id=str(item.get("finding_id", "")),
                field=str(item.get("field", "")),
                original_chars=int(item.get("original_chars", 0) or 0),
                kept_chars=int(item.get("kept_chars", 0) or 0),
            )
            for item in data.get("shortened") or []
            if isinstance(item, dict)
        ]
        return cls(
            policy=str(data.get("policy", "")),
            study_fingerprint=str(data.get("study_fingerprint", "")),
            total_findings=int(data.get("total_findings", 0) or 0),
            presented_ids=[str(item) for item in data.get("presented_ids") or []],
            omitted_ids=[str(item) for item in data.get("omitted_ids") or []],
            shortened=shortened,
            contention_total=int(data.get("contention_total", 0) or 0),
            contention_presented=int(data.get("contention_presented", 0) or 0),
            prompt_sha256=str(data.get("prompt_sha256", "")),
            prompt_chars=int(data.get("prompt_chars", 0) or 0),
        )


def select_findings(result: StudyResult, limit: int = MAX_FINDINGS_IN_PROMPT) -> list[StudyFinding]:
    """Take whole findings one lens at a time, in study order within each lens.

    Returned in study order, so the prompt still reads lens by lens. Only the
    choice of which findings make the cut is balanced.
    """
    queues = [list(outcome.findings) for outcome in result.outcomes if outcome.findings]
    chosen: set[int] = set()
    while len(chosen) < limit and any(queues):
        for queue in queues:
            if queue and len(chosen) < limit:
                chosen.add(id(queue.pop(0)))
    return [finding for finding in result.findings if id(finding) in chosen]


def shorten_field(text: str, limit: int = MAX_FIELD_CHARS) -> str:
    """Keep a field whole when it fits; otherwise cut at a boundary and say so.

    A sentence boundary in the second half of the allowance is preferred,
    then a word boundary. The marker is not part of the allowance, so a short
    field is never mistaken for a shortened one.
    """
    if len(text) <= limit:
        return text
    head = text[:limit]
    ends = [match.end() for match in _SENTENCE_END_RE.finditer(head + " ")]
    cut = ends[-1] if ends and ends[-1] >= limit // 2 else len(head.rsplit(" ", 1)[0]) or limit
    kept = text[:cut].rstrip()
    return f"{kept} [shortened: {len(kept)} of {len(text)} characters; full text in the study]"


def render_payload_fields(finding: StudyFinding, selection: BriefSelection | None = None) -> list[str]:
    """The finding's own fields, each whole or visibly shortened."""
    parts: list[str] = []
    for key, value in finding.payload.items():
        if key in {"anchors", "name", "title", "thread"}:
            continue
        text = "; ".join(str(v) for v in value) if isinstance(value, list) else str(value)
        text = " ".join(text.split())
        if not text:
            continue
        shown = shorten_field(text)
        if shown != text and selection is not None:
            kept = shown.rsplit(" [shortened:", 1)[0]
            selection.shortened.append(
                ShortenedField(
                    finding_id=finding.finding_id,
                    field=key,
                    original_chars=len(text),
                    kept_chars=len(kept),
                )
            )
        parts.append(f"  {key}: {shown}")
    return parts


def start_selection(result: StudyResult, presented: list[StudyFinding], fingerprint: str) -> BriefSelection:
    presented_ids = {id(finding) for finding in presented}
    contested = [finding for finding in result.findings if finding.lens == "contention"]
    return BriefSelection(
        study_fingerprint=fingerprint,
        total_findings=len(result.findings),
        presented_ids=[finding.finding_id for finding in presented],
        omitted_ids=[finding.finding_id for finding in result.findings if id(finding) not in presented_ids],
        contention_total=len(contested),
        contention_presented=sum(1 for finding in contested if id(finding) in presented_ids),
    )


def seal_selection(selection: BriefSelection, prompt: str) -> BriefSelection:
    """Bind the receipt to the exact prompt bytes the synthesis received."""
    selection.prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    selection.prompt_chars = len(prompt)
    return selection
