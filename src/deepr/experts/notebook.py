"""Render an expert's study findings as a notebook (pure, $0, no model).

`expert digest` sorts claims by confidence and prints bullets. That is a ledger,
and it is what made consults read as inventory rather than understanding.

This renders the other thing: what breaks, where sources disagree, how the
subject works, what a practitioner would expect and does not find. Sections are
ordered the way a person reads to learn, not the way a database sorts.

Three rules, each from a specific finding:

- **Confidence leaves the headline.** Subjective confidence tracks the internal
  consistency of evidence rather than its quality, so a bare number invites
  exactly the over-reading it cannot support. Where a value is shown it is
  accompanied by what produced it.
- **Numeric bands render inline, never behind a link.** Presenting a probability
  lexicon inline roughly doubled reader accuracy against words alone, and
  optional access (tooltip, linked table) performed no better than nothing,
  because about half of readers never opened it.
- **Coverage is reported, not just output.** An expert that read a third of its
  corpus and produced confident findings is reproducing a documented failure;
  what was skipped belongs in the document.

Derived view: the corpus and the study result are canonical. Regenerating over
unchanged inputs produces identical bytes.
"""

from __future__ import annotations

from typing import Any

from deepr.experts.study_contracts import StudyFinding, StudyResult
from deepr.experts.study_lenses import LENSES

NOTEBOOK_MARKER = "<!-- deepr:expert-notebook-v1 -->"

# Reading order: orientation, then mechanism, then the things that bite, then
# what is unsettled. Claims come last because they are the index, not the point.
_SECTION_ORDER: tuple[tuple[str, str, str], ...] = (
    ("mechanism", "How this works", "The underlying model, beneath the vocabulary."),
    ("failure", "What breaks", "Trigger, symptom, correction, and how to detect it early."),
    ("contention", "Where sources disagree", "Both sides quoted, and what would settle it."),
    ("change", "What changed", "And which earlier conclusions it invalidates."),
    ("absence", "What is missing", "What a practitioner would expect here and does not find."),
    ("operational", "Running it in practice", "The routine, and what goes wrong under pressure."),
    ("adversarial", "How it gets abused", "Assumptions that hurt most when violated deliberately."),
    ("economic", "Incentives and cost", "Who pays, who benefits, what is treated as free."),
    ("human_cultural", "How people actually behave", "What will be done, rather than what should be."),
    ("institutional", "Rules and obligations", "What to verify, and against which authority."),
)

# Fields rendered as labeled lines, in this order, when a finding carries them.
_DETAIL_ORDER: tuple[str, ...] = (
    "trigger",
    "symptom",
    "mechanism",
    "correction",
    "detection",
    "scope",
    "implies",
    "about",
    "what_would_settle_it",
    "practical_consequence",
    "expected",
    "why_expected",
    "what_is_there_instead",
    "how_to_close_it",
    "routine_burden",
    "failure_under_pressure",
    "assumption_violated",
    "attack",
    "damage",
    "who_bears_cost",
    "who_benefits",
    "behavior_predicted",
    "why_it_persists",
    "obligation_or_standard",
    "varies_by",
    "what_to_verify",
    "authority_to_check",
    "reasoning",
    "what_it_changes",
)

_LABELS = {
    "what_would_settle_it": "What would settle it",
    "practical_consequence": "Consequence",
    "what_is_there_instead": "What is there instead",
    "how_to_close_it": "How to close it",
    "routine_burden": "Routine burden",
    "failure_under_pressure": "Under pressure",
    "assumption_violated": "Assumption violated",
    "who_bears_cost": "Who bears the cost",
    "who_benefits": "Who benefits",
    "behavior_predicted": "Predicted behavior",
    "why_it_persists": "Why it persists",
    "obligation_or_standard": "Obligation or standard",
    "varies_by": "Varies by",
    "what_to_verify": "What to verify",
    "authority_to_check": "Authority to check",
    "why_expected": "Why expected",
    "what_it_changes": "What this changes",
}


def _label(key: str) -> str:
    return _LABELS.get(key, key.replace("_", " ").capitalize())


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def _render_finding(finding: StudyFinding, index: int) -> list[str]:
    lines = [f"{index}. **{finding.title}**"]
    for key in _DETAIL_ORDER:
        value = finding.payload.get(key)
        if value is None:
            continue
        text = _as_text(value)
        if text:
            lines.append(f"   - {_label(key)}: {text}")

    if finding.is_grounded:
        sources = ", ".join(sha[:12] for sha in finding.corpus_shas)
        lines.append(f"   - Sources: {sources}")
    else:
        # Labeled, not hidden. Deciding a finding is wrong is meaning; this
        # layer only reports that the quoted support could not be located.
        lines.append(
            "   - **Unverified**: no quoted phrase from this item was found in the "
            "retained corpus. Check before relying on it."
        )
    lines.append("")
    return lines


def _findings_by_lens(result: StudyResult) -> dict[str, list[StudyFinding]]:
    grouped: dict[str, list[StudyFinding]] = {}
    for finding in result.findings:
        grouped.setdefault(finding.lens, []).append(finding)
    return grouped


def _render_sources(result: StudyResult, corpus_entries: list[Any]) -> list[str]:
    lines = ["## Sources", ""]
    if not corpus_entries:
        lines.extend(["_No sources retained._", ""])
        return lines
    lines.append("| Origin | Publisher | Trust | Title |")
    lines.append("|---|---|---|---|")
    for entry in sorted(corpus_entries, key=lambda e: (e.origin_key, e.sha256)):
        title = (entry.title or entry.url or entry.sha256[:12])[:70]
        lines.append(f"| {entry.origin_key} | {entry.publisher or '-'} | {entry.trust_class} | {title} |")
    lines.append("")
    return lines


def _render_coverage(result: StudyResult) -> list[str]:
    coverage = result.coverage
    if coverage is None:
        return []
    lines = ["## What this study read", ""]
    lines.append(
        f"- Studied {coverage.studied_sources} of {coverage.corpus_sources} retained source(s), "
        f"spanning {coverage.cited_origins} of {coverage.corpus_origins} distinct origin(s)."
    )
    lines.append(
        f"- source_coverage={coverage.source_coverage:.2f} "
        f"(share of studied sources any finding cited); "
        f"origin_coverage={coverage.origin_coverage:.2f}."
    )
    for note in coverage.concerns():
        lines.append(f"- {note}")
    lines.append("")
    return lines


def _render_sections(result: StudyResult, grouped: dict[str, list[StudyFinding]]) -> tuple[list[str], list[str]]:
    """Render findings in reading order. Returns (lines, headings that were empty)."""
    ran = {outcome.lens for outcome in result.outcomes}
    lines: list[str] = []
    empty: list[str] = []
    for lens_key, heading, blurb in _SECTION_ORDER:
        findings = grouped.get(lens_key)
        if not findings:
            if lens_key in ran:
                empty.append(heading)
            continue
        lines.extend([f"## {heading}", "", f"_{blurb}_", ""])
        for index, finding in enumerate(findings, 1):
            lines.extend(_render_finding(finding, index))
    return lines, empty


def _render_empty_sections(empty_sections: list[str]) -> list[str]:
    """A lens that ran and found nothing is a result, not something to hide."""
    if not empty_sections:
        return []
    lines = [
        "## Read but empty",
        "",
        "These lenses ran and returned nothing. That is a result: either the "
        "corpus does not carry the material, or it was not asked well.",
        "",
    ]
    lines.extend(f"- {heading}" for heading in empty_sections)
    lines.append("")
    return lines


def _render_failures(result: StudyResult) -> list[str]:
    if not result.failed_lenses:
        return []
    lines = ["## Lenses that failed", ""]
    lines.extend(
        f"- {outcome.lens}: {outcome.status} - {outcome.detail}"
        for outcome in result.outcomes
        if outcome.status != "ok"
    )
    lines.append("")
    return lines


def _render_limitations(result: StudyResult) -> list[str]:
    if not result.limitations:
        return []
    lines = ["## Limitations", ""]
    lines.extend(f"- {item}" for item in result.limitations)
    lines.append("")
    return lines


def build_notebook(
    result: StudyResult,
    *,
    expert_name: str = "",
    domain: str = "",
    purpose: str = "",
    corpus_entries: list[Any] | None = None,
) -> str:
    """Render a study result as a notebook a person would read.

    Pure and deterministic: identical inputs render identical bytes, so an
    unchanged corpus regenerates without churn.
    """
    name = expert_name or result.expert_name
    lines: list[str] = [NOTEBOOK_MARKER, "", f"# {name}", ""]
    if domain:
        lines.append(f"**Domain:** {domain}")
    if purpose:
        lines.append(f"**Purpose:** {purpose}")
    if domain or purpose:
        lines.append("")

    lines.extend(
        [
            "> Derived view. The retained corpus and the study record are canonical;",
            "> this file is regenerated and safe to delete.",
            "",
        ]
    )

    grouped = _findings_by_lens(result)
    grounded = len(result.grounded_findings)
    lines.extend(
        [
            f"{len(result.findings)} finding(s) from {len(result.outcomes)} lens(es); "
            f"{grounded} anchored in the retained corpus.",
            "",
        ]
    )

    body, empty_sections = _render_sections(result, grouped)
    lines.extend(body)
    lines.extend(_render_empty_sections(empty_sections))
    lines.extend(_render_coverage(result))
    lines.extend(_render_sources(result, corpus_entries or []))
    lines.extend(_render_failures(result))
    lines.extend(_render_limitations(result))

    lines.extend(
        [
            "---",
            "",
            "Findings are proposed from sources, not verified conclusions. Anchored "
            "means a quoted phrase was located in the retained corpus; it does not "
            "mean the reading is correct.",
            "",
            f"Lenses available: {', '.join(sorted(LENSES))}.",
            "",
        ]
    )
    return "\n".join(lines)
