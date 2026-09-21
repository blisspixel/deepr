"""Linked, reproducible Markdown over retained understanding, never its authority."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from deepr.experts.brief_contracts import ExpertBrief
from deepr.experts.corpus_store import CorpusEntry
from deepr.experts.evidence_graph import build_graph
from deepr.experts.record_identity import position_thread_id
from deepr.experts.study_contracts import StudyResult
from deepr.utils.atomic_io import atomic_write_text

MARKER = "<!-- deepr:knowledge-view-v1 -->"


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


def _position_page(position: Any, findings: dict[str, Any]) -> str:
    pid = position_thread_id(position.question)
    lines = [
        "[Knowledge index](../index.md)",
        "",
        f"Position identity: `{pid}`",
        "",
        _text(position.stance),
        "",
        "## Reasoning",
        "",
        _text(position.reasoning),
        "",
        "## Conditions for revision",
        "",
        _text(position.would_change_my_mind or "Not recorded."),
        "",
        "## Unresolved dissent",
        "",
        _text(position.unresolved_dissent or "None recorded; this is not proof of consensus."),
        "",
        "## Supporting research",
        "",
    ]
    for fid in position.supported_by:
        lines.append(
            f"- [{_text(findings[fid].title)}](../{_page('findings', fid)})"
            if fid in findings
            else f"- Missing finding: `{_text(fid)}`"
        )
    return _document(position.question, lines)


def _finding_page(finding: Any, brief: ExpertBrief, sources: dict[str, CorpusEntry]) -> str:
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
    *, study: StudyResult, brief: ExpertBrief, entries: list[CorpusEntry], history: dict[str, Any] | None = None
) -> tuple[str, dict[str, str]]:
    """Project recorded links and content; infer no new relationships or verdicts."""
    entries = sorted(entries, key=lambda entry: entry.sha256)
    if any(len(entry.sha256) != 64 or any(c not in "0123456789abcdef" for c in entry.sha256) for entry in entries):
        raise ValueError("Knowledge source identity must be a lowercase SHA256")
    inputs = {
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
    index = [
        "Derived from retained research. Source links are inspectable; interpretations and advice require review.",
        "",
        f"Study observed: {_text(study.started_at or 'unknown')}",
        "",
        "[Currentness and limits](currentness.md) | [Evidence graph](evidence.json) | [Input bindings](manifest.json)",
        "",
        "## Perspective",
        "",
        _text(brief.orientation),
        "",
        "## Guidance and reasoning",
        "",
    ]
    for position in brief.positions:
        pid = position_thread_id(position.question)
        target = _page("positions", pid)
        index.append(f"- [{_text(position.question)}]({target})")
        pages[target] = _position_page(position, findings)
    index += ["", "## Concepts, mechanisms, and research notes", ""]
    for fid, finding in findings.items():
        target = _page("findings", fid)
        index.append(f"- {_text(finding.lens)}: [{_text(finding.title)}]({target})")
        pages[target] = _finding_page(finding, brief, sources)
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
            "## Recorded limitations",
            "",
            *[f"- {_text(note)}" for note in study.limitations + brief.limitations + brief.integrity_warnings()],
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


def write_knowledge_view(
    directory: Path,
    *,
    study: StudyResult,
    brief: ExpertBrief,
    entries: list[CorpusEntry],
    history: dict[str, Any] | None = None,
) -> Path:
    """Keep immutable views and an index pointer, preserving authored content."""
    identity, pages = build_knowledge_view(study=study, brief=brief, entries=entries, history=history)
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
