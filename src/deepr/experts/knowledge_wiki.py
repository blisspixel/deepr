"""Linked, reproducible Markdown over retained understanding, never its authority."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from deepr.experts.brief_attribution import ORIGIN_LABELS, orientation_statements
from deepr.experts.brief_contracts import ExpertBrief
from deepr.experts.consult_support import bind_study, recorded_statement
from deepr.experts.corpus_store import CorpusEntry, content_hash
from deepr.experts.evidence_graph import build_graph
from deepr.experts.record_identity import position_thread_id
from deepr.experts.study_contracts import StudyResult
from deepr.utils.atomic_io import atomic_write_text

MARKER = "<!-- deepr:knowledge-view-v1 -->"
RENDERER_VERSION = "deepr-knowledge-reader-v3"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + "\n"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return html.escape(str(value)).replace("[", "\\[").replace("]", "\\]")


def _page(kind: str, identity: str) -> str:
    return f"{kind}/{_hash(identity)[:16]}.md"


def _document(title: str, lines: list[str]) -> str:
    return "\n".join([MARKER, f"# {_text(title)}", "", *lines, ""])


def _recorded_limits(study: StudyResult, brief: ExpertBrief, binding: str) -> list[str]:
    """Keep run provenance and remove exact duplicates, without judging resolution."""
    notes = list(dict.fromkeys(study.limitations))
    brief_notes = list(dict.fromkeys(brief.limitations + brief.integrity_warnings()))
    lines = [
        "## Recorded limitations and run history",
        "",
        "These notes describe the recorded runs, not a new check of current failures. "
        "Checkpoint and retry notes record what happened during that run.",
        "",
        f"Brief study binding: {binding}.",
        "",
    ]
    if binding == "matched":
        lines += [f"- {_text(note)}" for note in dict.fromkeys(notes + brief_notes)]
    else:
        lines += ["### Loaded study", "", *[f"- {_text(note)}" for note in notes], ""]
        lines += [
            "### Brief from a different or unverified study",
            "",
            "These brief notes are not attributed to the loaded study. Retained history is preserved.",
            "",
            *[f"- {_text(note)}" for note in brief_notes],
        ]
    return lines


def _source_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        return ""
    return url.replace("<", "%3C").replace(">", "%3E").replace("\n", "").replace("\r", "")


def _finding_details(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in payload.items():
        if key in {"anchors", "title", "name", "concept"} or value is None:
            continue
        lines += [f"## {_text(key.replace('_', ' ').capitalize())}", ""]
        if isinstance(value, dict):
            lines += ["```json", _json(value).rstrip(), "```", ""]
        elif isinstance(value, list):
            lines += [f"- {_text(item)}" for item in value] + [""]
        else:
            lines += [_text(value), ""]
    return lines


def _position_page(position: Any, findings: dict[str, Any], binding: str = "unbound") -> str:
    pid = position_thread_id(position.question)
    cited = [findings[fid] for fid in dict.fromkeys(position.supported_by) if fid in findings]
    lines = [
        "[Knowledge index](../index.md)",
        "",
        f"Position identity: `{pid}`",
        "",
        _text(position.stance),
        "",
        f"Recorded support label: {_text(position.confidence or 'none recorded')} (uncalibrated, not a probability).",
        f"Basis: {_text(position.confidence_basis or 'none recorded')}.",
        f"Study binding: {binding}.",
        f"Cites {len(set(position.supported_by))} findings; {len(cited)} present in this study, "
        f"with {sum(f.grounded_anchor_count for f in cited)} recorded matched excerpts.",
        "Counts describe the loaded study; they support this position's links only when the study binding matches.",
        "",
        "## Reasoning",
        "",
        _text(position.reasoning),
        "",
        "## Conditions for revision",
        "",
        _text(recorded_statement(position.would_change_my_mind) or "Not recorded."),
        "",
        "## Unresolved dissent",
        "",
        _text(recorded_statement(position.unresolved_dissent) or "None recorded; this is not proof of consensus."),
        "",
        "## Supporting research",
        "",
    ]
    for fid in position.supported_by:
        lines.append(
            f"- [{_text(findings[fid].title)}](../{_page('findings', fid)})"
            if fid in findings and binding == "matched"
            else f"- Unresolved finding citation: `{_text(fid)}` (study binding: {binding})"
        )
    return _document(position.question, lines)


def _anchor_lines(finding: Any, source_texts: dict[str, str]) -> list[str]:
    lines = ["## Recorded excerpts", "", "Literal matches locate text; they do not verify the interpretation.", ""]
    if not finding.anchors:
        return [*lines, "No excerpt text recorded.", ""]
    available = {sha: source_texts[sha] for sha in finding.corpus_shas if sha in source_texts}
    for anchor in finding.anchors:
        probe = " ".join(anchor.split()).lower()
        matches = [sha for sha, body in available.items() if probe and probe in " ".join(body.split()).lower()]
        if matches:
            label = "Matched in retained text: " + ", ".join(
                f"[source {sha[:12]}](../{_page('sources', sha)})" for sha in matches
            )
        elif available and len(available) == len(finding.corpus_shas):
            label = "Unmatched in the linked retained text."
        else:
            label = "Match unverified: linked retained text unavailable."
        lines += [label, "", *[f"> {_text(line)}" for line in anchor.splitlines()], ""]
    return lines


def _finding_page(
    finding: Any, brief: ExpertBrief, sources: dict[str, CorpusEntry], source_texts: dict[str, str], binding: str
) -> str:
    fid = finding.finding_id
    lines = [
        "[Knowledge index](../index.md)",
        "",
        f"Finding identity: `{_text(fid)}`",
        "",
        "Recorded interpretation, not a verified truth label.",
        "",
        *_finding_details(finding.payload),
        f"Matched excerpts: {finding.grounded_anchor_count}; unmatched excerpts: {finding.ungrounded_anchor_count}.",
        "",
        *_anchor_lines(finding, source_texts),
        "## Sources",
        "",
    ]
    for sha in finding.corpus_shas:
        lines.append(
            f"- [{_text(sources[sha].title or sha)}](../{_page('sources', sha)})"
            if sha in sources
            else f"- Missing retained source: `{_text(sha)}`"
        )
    lines += ["", "## Used in guidance", ""]
    if binding != "matched":
        lines.append(f"Guidance links unresolved: brief study binding is {binding}.")
        return _document(finding.title, lines)
    lines += [
        f"- [{_text(p.question)}](../{_page('positions', position_thread_id(p.question))})"
        for p in brief.positions
        if fid in p.supported_by
    ]
    return _document(finding.title, lines)


def _source_page(entry: CorpusEntry, findings: dict[str, Any]) -> str:
    sha = entry.sha256
    lines = [
        "[Knowledge index](../index.md)",
        "",
        f"Content SHA256: `{sha}`",
        "",
        f"Observed: {_text(entry.fetched_at or 'unknown')}",
        "",
        "Publication date and version applicability: inspect the source; not inferred from observation time.",
        "",
        f"Publisher identity: {_text(entry.origin_key)}",
        "",
    ]
    if url := _source_url(entry.url):
        lines += [f"[Original source](<{url}>)", ""]
    lines += [
        f"[Retained text](../../../../corpus/sources/{sha[:2]}/{sha}.md)",
        "",
        "## Research linked to this source",
        "",
    ]
    lines += [
        f"- [{_text(f.title)}](../{_page('findings', fid)})" for fid, f in findings.items() if sha in f.corpus_shas
    ]
    return _document(entry.title or sha, lines)


def build_knowledge_view(
    *,
    study: StudyResult,
    brief: ExpertBrief,
    entries: list[CorpusEntry],
    history: dict[str, Any] | None = None,
    source_texts: dict[str, str] | None = None,
) -> tuple[str, dict[str, str]]:
    """Project recorded links and content; infer no new relationships or verdicts."""
    entries = sorted(entries, key=lambda entry: entry.sha256)
    if any(len(entry.sha256) != 64 or any(c not in "0123456789abcdef" for c in entry.sha256) for entry in entries):
        raise ValueError("Knowledge source identity must be a lowercase SHA256")
    known_sources = {entry.sha256 for entry in entries}
    source_texts = {
        sha: body for sha, body in (source_texts or {}).items() if sha in known_sources and content_hash(body) == sha
    }
    inputs = {
        "renderer": RENDERER_VERSION,
        "available_source_hashes": sorted(source_texts),
        "study": study.to_dict(),
        "brief": brief.to_dict(),
        "corpus": [e.to_dict() for e in entries],
        "history": history,
    }
    hashes = {name: _hash(_json(value)) for name, value in inputs.items()}
    identity = _hash(_json(hashes))
    graph = build_graph(
        expert_name=study.expert_name, study=study, brief=brief, corpus_entries=entries, at=study.started_at
    )
    pages: dict[str, str] = {"evidence.json": _json(graph.to_dict())}
    findings = {finding.finding_id: finding for finding in study.findings if finding.finding_id}
    sources = {entry.sha256: entry for entry in entries}
    binding = bind_study(brief, study)
    index = [
        "Derived from retained research. Source links are inspectable; interpretations and advice require review.",
        "",
        f"Study observed: {_text(study.started_at or 'unknown')}",
        "",
        "[Currentness and limits](currentness.md) | [Evidence graph](evidence.json) | [Input bindings](manifest.json)",
        "",
        "## Perspective",
        "",
        f"Findings anchored {len(study.grounded_findings)} of {len(study.findings)} (recorded literal-match signal).",
        f"Brief study binding: {binding}. Attribution labels are recorded model judgments, not verified truth.",
        "",
    ]
    for statement in orientation_statements(brief.orientation, brief.orientation_statements):
        index += [f"**{ORIGIN_LABELS.get(statement.origin, 'Origin not recorded')}:** {_text(statement.text)}", ""]
        for fid in statement.supported_by:
            index.append(
                f"- [{_text(findings[fid].title)}]({_page('findings', fid)})"
                if binding == "matched" and fid in findings
                else f"- Unresolved finding citation: `{_text(fid)}` (study binding: {binding})"
            )
        if statement.origin == "studied" and not statement.supported_by:
            index.append("No supporting finding recorded; attribution is unresolved.")
        index.append("")
    index += ["## Guidance and reasoning", ""]
    for position in brief.positions:
        pid = position_thread_id(position.question)
        target = _page("positions", pid)
        index.append(f"- [{_text(position.question)}]({target})")
        pages[target] = _position_page(position, findings, binding)
    index += ["", "## Concepts, mechanisms, and research notes", ""]
    for fid, finding in findings.items():
        target = _page("findings", fid)
        index.append(f"- {_text(finding.lens)}: [{_text(finding.title)}]({target})")
        pages[target] = _finding_page(finding, brief, sources, source_texts, binding)
    index += ["", "## Source library", ""]
    for sha, entry in sources.items():
        target = _page("sources", sha)
        index.append(f"- [{_text(entry.title or sha)}]({target})")
        pages[target] = _source_page(entry, findings)
    index += ["", "## Open questions", ""]
    index += [f"- {_text(question)}" for question in brief.state.live + brief.state.unknown]
    index += [
        "",
        "## History and experience",
        "",
        "[Recorded position history](history.json). No investigations, outcomes, or practical experience are invented by this view.",
    ]
    pages["index.md"] = _document(study.expert_name, index)
    pages["history.json"] = _json(history)
    pages["currentness.md"] = _document(
        "Currentness and review limits",
        [
            "[Knowledge index](index.md)",
            "",
            f"Study observation: {_text(study.started_at or 'unknown')}",
            "",
            "This view regenerates retained understanding. It performs no new search or substantive review.",
            "",
            "Source observation, publication, version applicability, and advice quality are separate checks.",
            "",
            "No live preparation or qualification is implied. Position dates not recorded in the evidence graph remain unknown.",
            "",
            *_recorded_limits(study, brief, binding),
        ],
    )
    pages["manifest.json"] = _json(
        {
            "schema_version": "deepr-knowledge-view-v1",
            "identity": identity,
            "input_hashes": hashes,
            "files": {name: _hash(text) for name, text in sorted(pages.items())},
        }
    )
    return identity, pages


def _retained_source_texts(directory: Path, entries: list[CorpusEntry]) -> dict[str, str]:
    """Read available local bytes without following an escaping source link."""
    source_texts = {}
    for entry in entries:
        path = directory / "corpus" / "sources" / entry.sha256[:2] / f"{entry.sha256}.md"
        if path.resolve().is_relative_to(directory.resolve()) and path.is_file():
            try:
                source_texts[entry.sha256] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
    return source_texts


def write_knowledge_view(
    directory: Path,
    *,
    study: StudyResult,
    brief: ExpertBrief,
    entries: list[CorpusEntry],
    history: dict[str, Any] | None = None,
) -> Path:
    """Keep immutable views and an index pointer, preserving authored content."""
    source_texts = _retained_source_texts(directory, entries)
    identity, pages = build_knowledge_view(
        study=study, brief=brief, entries=entries, history=history, source_texts=source_texts
    )
    root = directory / "knowledge"
    pointer = root / "INDEX.md"
    if not pointer.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Knowledge index escapes the expert directory")
    if pointer.exists() and not pointer.read_text(encoding="utf-8").startswith(MARKER):
        raise ValueError(f"Refusing to replace authored knowledge index: {pointer}")
    target = root / "views" / identity[:16]
    for relative, text in pages.items():
        path = target / relative
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Knowledge output escapes the expert directory")
        if path.exists() and path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Knowledge view changed or has conflicting content: {path}")
    for relative, text in pages.items():
        path = target / relative
        if not path.exists():
            atomic_write_text(path, text)
    atomic_write_text(
        pointer,
        _document(
            study.expert_name,
            [
                f"[Open linked knowledge](views/{identity[:16]}/index.md)",
                "",
                "Generated from retained research. Qualification and currentness require the linked evidence and review.",
            ],
        ),
    )
    return target / "index.md"
