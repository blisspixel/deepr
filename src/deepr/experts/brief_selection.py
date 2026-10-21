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
  in turn, keeping each lens's own order. Each lens gets a candidate considered
  before any lens gets a second; a complete unit may not fit. This is a structural rule
  about coverage, not a judgment about which disagreement matters; that
  judgment stays with the synthesis model and later review.
- **Complete delivery within a declared prompt bound.** A finding's fields
  travel together or not at all. Historical marked-shortening receipts remain
  readable; new syntheses never receive a misleading prefix.
- **The selection is a receipt.** Presented and omitted finding ids, every
  shortened field, and the exact prompt hash travel with the brief, so nobody
  can later claim the whole study reached synthesis when it did not.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from typing import Any

from deepr.experts.study_contracts import StudyFinding, StudyResult

SELECTION_POLICY = "lens-balanced-complete-findings-v2"
MAX_FINDINGS_IN_PROMPT = 120
MAX_FIELD_CHARS = 600
MAX_BRIEF_PROMPT_CHARS = 60000

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
    max_prompt_chars: int = 0
    omission_reasons: dict[str, str] = field(default_factory=dict)
    finding_content_sha256: dict[str, str] = field(default_factory=dict)
    admission_status: str = "admitted"

    @property
    def complete(self) -> bool:
        """True only when every finding reached synthesis unshortened."""
        return self.admission_status == "admitted" and not self.omitted_ids and not self.shortened

    def resolve_finding(self, result: StudyResult, finding_id: str) -> StudyFinding:
        """Resolve a retained unit only against its original study and content.

        Older receipts without content bindings cannot establish this identity.
        This does not retrieve evidence or grant synthesis another model call.
        """
        from deepr.experts.consult_support import study_fingerprint

        matches = [finding for finding in result.findings if finding.finding_id == finding_id]
        if study_fingerprint(result) != self.study_fingerprint or len(matches) != 1:
            raise ValueError("Finding does not resolve to the recorded study identity")
        finding = matches[0]
        if self.finding_content_sha256.get(finding_id) != finding_content_hash(finding):
            raise ValueError("Finding content does not match the recorded receipt")
        return finding

    def bind_study_content(self, result: StudyResult) -> None:
        """Require unambiguous study handles before binding their complete units."""
        identities = [finding.finding_id for finding in result.findings]
        if not all(identities) or len(identities) != len(set(identities)):
            self.admission_status = "refused_finding_identity"
            self.omission_reasons = dict.fromkeys(identities, "finding_identity")
            raise BriefPromptAdmissionError(self)
        self.finding_content_sha256 = {finding.finding_id: finding_content_hash(finding) for finding in result.findings}

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
            max_prompt_chars=int(data.get("max_prompt_chars", 0) or 0),
            omission_reasons=dict(data.get("omission_reasons") or {}),
            finding_content_sha256=dict(data.get("finding_content_sha256") or {}),
            admission_status=str(data.get("admission_status", "admitted")),
        )


def select_findings(result: StudyResult, limit: int = MAX_FINDINGS_IN_PROMPT) -> list[StudyFinding]:
    """Take whole findings one lens at a time, in study order within each lens.

    Returned in study order, so the prompt still reads lens by lens. Only the
    choice of which findings make the cut is balanced.
    """
    chosen = {id(finding) for _, finding in zip(range(limit), balanced_findings(result))}
    return [finding for finding in result.findings if id(finding) in chosen]


def balanced_findings(result: StudyResult) -> Iterator[StudyFinding]:
    """Candidate admission order; final presentation retains study order."""
    queues = [deque(outcome.findings) for outcome in result.outcomes if outcome.findings]
    while any(queues):
        for queue in queues:
            if queue:
                yield queue.popleft()


def finding_content_hash(finding: StudyFinding) -> str:
    """Bind payload, qualifications, anchors and source identities together."""
    raw = json.dumps(finding.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class BriefPromptAdmissionError(ValueError):
    """Prompt admission refused; carries a receipt without dispatch."""

    def __init__(self, selection: BriefSelection) -> None:
        details = {
            "refused_prompt_envelope": "Brief prompt framing exceeds its character allowance",
            "refused_no_complete_findings": "No complete study finding fits the brief prompt allowance",
            "refused_finding_identity": "Brief findings require nonempty unique identities",
        }
        super().__init__(details[selection.admission_status] + "; refused before dispatch.")
        self.selection = selection


def admit_complete_findings(
    result: StudyResult,
    fingerprint: str,
    render_prompt: Callable[[list[StudyFinding], BriefSelection], str],
    max_prompt_chars: int = MAX_BRIEF_PROMPT_CHARS,
) -> tuple[str, BriefSelection]:
    """Fit complete units against the exact envelope, never their prefixes."""
    if type(max_prompt_chars) is not int or not 0 < max_prompt_chars <= MAX_BRIEF_PROMPT_CHARS:
        raise ValueError(f"Brief prompt allowance must be between 1 and {MAX_BRIEF_PROMPT_CHARS} characters")
    selected: list[StudyFinding] = []
    reasons: dict[str, str] = {}
    identity_receipt = start_selection(result, [], fingerprint)
    identity_receipt.max_prompt_chars = max_prompt_chars
    identity_receipt.bind_study_content(result)
    content_hashes = identity_receipt.finding_content_sha256

    def candidate(findings: list[StudyFinding]) -> tuple[str, BriefSelection]:
        receipt = start_selection(result, findings, fingerprint)
        receipt.max_prompt_chars = max_prompt_chars
        receipt.finding_content_sha256 = content_hashes
        return render_prompt(findings, receipt), receipt

    capped = select_findings(result)
    prompt, selection = candidate(capped)
    if len(prompt) <= max_prompt_chars:
        selection.omission_reasons = dict.fromkeys(selection.omitted_ids, "finding_cap")
        return prompt, seal_selection(selection, prompt)
    prompt, selection = candidate(selected)
    pending = list(balanced_findings(result))
    while pending:
        before = len(selected)
        deferred: list[StudyFinding] = []
        for finding in pending:
            if len(selected) >= MAX_FINDINGS_IN_PROMPT:
                reasons[finding.finding_id] = "finding_cap"
                continue
            proposed_ids = {id(item) for item in [*selected, finding]}
            proposed = [item for item in result.findings if id(item) in proposed_ids]
            proposed_prompt, proposed_selection = candidate(proposed)
            if len(proposed_prompt) <= max_prompt_chars:
                selected, prompt, selection = proposed, proposed_prompt, proposed_selection
                reasons.pop(finding.finding_id, None)
            else:
                deferred.append(finding)
                reasons[finding.finding_id] = "prompt_chars"
        if len(selected) == before:
            break
        # Notices can shrink after admission. Revisit rejected complete units;
        # each continuing pass admits at least one of at most 120 findings.
        pending = deferred
    selection.omission_reasons = reasons
    if not selected and result.findings:
        selection.admission_status = (
            "refused_prompt_envelope" if len(prompt) > max_prompt_chars else "refused_no_complete_findings"
        )
        raise BriefPromptAdmissionError(seal_selection(selection, prompt))
    return prompt, seal_selection(selection, prompt)


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
    """The finding's eligible fields, complete; admission owns the bound.

    ``selection`` remains accepted for callers of the former rendering API.
    Historical shortening helpers remain available for receipt compatibility.
    """
    parts: list[str] = []
    for key, value in finding.payload.items():
        if key in {"anchors", "name", "title", "thread"}:
            continue
        text = "; ".join(str(v) for v in value) if isinstance(value, list) else str(value)
        text = " ".join(text.split())
        if not text:
            continue
        parts.append(f"  {key}: {text}")
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
