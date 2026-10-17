"""Resolve whether a position's citations reach this study and its passages.

A finding id is positional inside one study. A later study can reuse the id
for different content. Citation presence is not support. Resolution requires
the brief's study fingerprint, the finding, an anchored excerpt, and a
retained passage that was read. Word overlap is not a verdict.
"""

from __future__ import annotations

import hashlib
from typing import Any

from deepr.experts.brief_contracts import ExpertBrief, Position
from deepr.experts.study_contracts import StudyFinding, StudyResult

_UNRECORDED = frozenset({"false", "no", "none", "n/a", "na", "null", "nil"})


def recorded_statement(value: object) -> str:
    """Return text that was actually recorded.

    Exact placeholder tokens are empty form values. This does not judge
    whether a longer sentence is dissent.
    """
    text = str(value or "").strip()
    if text.casefold() in _UNRECORDED:
        return ""
    return text


def study_fingerprint(result: StudyResult) -> str:
    """Identity of the findings a brief is allowed to cite."""
    lines: list[str] = []
    for outcome in result.outcomes:
        lines.append(f"outcome:{outcome.lens}:{outcome.corpus_fingerprint}")
        for finding in outcome.findings:
            anchors = "\n".join(finding.anchors)
            shas = ",".join(finding.corpus_shas)
            lines.append(
                f"finding:{finding.finding_id}:{finding.title}:{shas}:{finding.grounded_anchor_count}:{anchors}"
            )
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def bind_study(brief: ExpertBrief | None, result: StudyResult | None) -> str:
    """Return matched, unbound, mismatch, or no_study."""
    if result is None:
        return "no_study"
    if brief is None or not brief.study_fingerprint:
        return "unbound"
    if brief.study_fingerprint != study_fingerprint(result):
        return "mismatch"
    return "matched"


def resolve_position_support(
    position: Position,
    *,
    findings: dict[str, StudyFinding],
    passages: dict[str, tuple[str, str, str]],
    binding: str,
) -> dict[str, Any]:
    """One position's cited ids, and which of them reached a retained passage."""
    cited = list(position.supported_by)
    resolved: list[str] = []
    missing: list[str] = []
    unanchored: list[str] = []
    missing_passage: list[str] = []
    if binding == "matched":
        for finding_id in cited:
            finding = findings.get(finding_id)
            if finding is None:
                missing.append(finding_id)
                continue
            if not finding.is_grounded:
                unanchored.append(finding_id)
                continue
            window = passages.get(finding_id)
            if window is None or not str(window[2]).strip():
                missing_passage.append(finding_id)
                continue
            resolved.append(finding_id)
    fully_resolved = bool(cited) and binding == "matched" and resolved == cited
    return {
        "question": position.question,
        "cited_ids": cited,
        "resolved_finding_ids": resolved,
        "missing_finding_ids": missing,
        "unanchored_finding_ids": unanchored,
        "missing_passage_ids": missing_passage,
        "study_binding": binding,
        "resolved": fully_resolved,
    }


def support_for_positions(
    positions: list[Position],
    *,
    brief: ExpertBrief | None,
    result: StudyResult | None,
    passages: dict[str, tuple[str, str, str]],
) -> list[dict[str, Any]]:
    binding = bind_study(brief, result)
    findings = {finding.finding_id: finding for finding in (result.findings if result is not None else [])}
    return [
        resolve_position_support(position, findings=findings, passages=passages, binding=binding)
        for position in positions
    ]
