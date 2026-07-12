"""OKF bundle export for Deepr experts.

OKF is an interchange view, not authoritative expert state. This module
regenerates a portable Markdown/YAML bundle from the structured belief store
and manifest snapshot at $0, with no model or network calls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from deepr.experts.belief_edges import Edge
from deepr.experts.beliefs import Belief, BeliefChange, BeliefStore
from deepr.experts.perspective import contested as contested_query

OKF_SCHEMA_VERSION = "deepr-okf-v1"
OKF_PROFILE_SCHEMA_VERSION = "deepr-okf-profile-v1"
OKF_MARKER = "deepr:okf derived-view regenerable"

_HTML_BANNER = f"<!-- {OKF_MARKER} -->\n<!-- DERIVED VIEW - do not hand-edit. The belief store is canonical. -->\n"
_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class OKFBundle:
    """In-memory OKF export files keyed by bundle-relative path."""

    files: dict[str, str]
    concept_count: int
    gap_count: int
    event_count: int
    contested_count: int
    as_of: str


@dataclass(frozen=True)
class OKFWriteResult:
    """Result of writing an OKF bundle."""

    output_dir: Path
    files: list[str]
    concept_count: int
    gap_count: int
    event_count: int
    contested_count: int
    as_of: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": str(self.output_dir),
            "files": list(self.files),
            "concept_count": self.concept_count,
            "gap_count": self.gap_count,
            "event_count": self.event_count,
            "contested_count": self.contested_count,
            "as_of": self.as_of,
            "schema_version": OKF_SCHEMA_VERSION,
        }


@dataclass(frozen=True)
class OKFIngestionCorpus:
    """Parsed OKF concept documents prepared for verified absorption."""

    source_path: Path
    report_id: str
    report_text: str
    files: list[str]
    concept_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "report_id": self.report_id,
            "files": list(self.files),
            "concept_count": self.concept_count,
        }


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _as_of(store: BeliefStore, events: list[BeliefChange]) -> str:
    timestamps: list[datetime] = []
    for event in events:
        if (timestamp := _aware(event.timestamp)) is not None:
            timestamps.append(timestamp)
    for belief in store.beliefs.values():
        if (timestamp := _aware(belief.updated_at)) is not None:
            timestamps.append(timestamp)
    if not timestamps:
        return "never"
    return max(timestamps).isoformat()


def _slug(value: str, *, fallback: str) -> str:
    slug = _SLUG_CHARS.sub("-", value.lower()).strip("-")
    return slug[:80].strip("-") or fallback


def _concept_path(belief: Belief) -> str:
    prefix = _slug(belief.domain or "general", fallback="general")
    return f"concepts/{prefix}-{belief.id}.md"


def _yaml_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines)


def _parse_frontmatter_value(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value.strip("\"'")


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    start = 0
    while start < len(lines):
        stripped = lines[start].strip()
        if not stripped or stripped.startswith("<!--"):
            start += 1
            continue
        break
    if start >= len(lines) or lines[start].strip() != "---":
        return {}, text

    end = start + 1
    while end < len(lines) and lines[end].strip() != "---":
        end += 1
    if end >= len(lines):
        return {}, text

    fields: dict[str, Any] = {}
    for line in lines[start + 1 : end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = _parse_frontmatter_value(value)
    return fields, "\n".join(lines[end + 1 :]).strip()


def _doc(fields: dict[str, Any], body: list[str]) -> str:
    return "\n".join([_HTML_BANNER + _frontmatter(fields), "", *body, ""])


def _md_escape(value: str) -> str:
    return value.replace("[", "\\[").replace("]", "\\]")


def _fmt_num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _sorted_beliefs(store: BeliefStore) -> list[Belief]:
    return sorted(
        store.beliefs.values(),
        key=lambda belief: (
            belief.domain or "",
            -belief.get_current_confidence(),
            belief.claim,
            belief.id,
        ),
    )


def _edge_target(edge: Edge, source_id: str) -> str:
    return edge.dst_id if edge.src_id == source_id else edge.src_id


def _edge_line(edge: Edge, source_id: str, paths_by_id: dict[str, str], beliefs_by_id: dict[str, Belief]) -> str:
    target_id = _edge_target(edge, source_id)
    target = beliefs_by_id.get(target_id)
    label = _md_escape(target.claim if target else target_id)
    path = paths_by_id.get(target_id)
    provenance = ", ".join(edge.provenance) if edge.provenance else "unspecified provenance"
    if path:
        link = f"./{Path(path).name}"
        return f"- {edge.edge_type}: [{label}]({link})  `{provenance}`"
    return f"- {edge.edge_type}: {label}  `{provenance}`"


def _contradiction_provenance(store: BeliefStore, a_id: str, b_id: str) -> list[str]:
    provenance: list[str] = []
    for edge in store.edges.values():
        if edge.edge_type != "contradicts":
            continue
        if {edge.src_id, edge.dst_id} != {a_id, b_id}:
            continue
        for item in edge.provenance:
            if item not in provenance:
                provenance.append(item)
    return provenance


def _build_index(
    profile: Any,
    store: BeliefStore,
    manifest: Any,
    paths_by_id: dict[str, str],
    as_of: str,
    events: list[BeliefChange],
) -> str:
    beliefs = _sorted_beliefs(store)
    gaps = list(getattr(manifest, "gaps", []) or [])
    contested = contested_query(store, expert_name=str(profile.name))
    fields = {
        "type": "deepr.okf.index",
        "title": str(profile.name),
        "description": str(getattr(profile, "description", "") or ""),
        "tags": [str(getattr(profile, "domain", "") or "general")],
        "timestamp": as_of,
        "deepr": {
            "schema_version": OKF_SCHEMA_VERSION,
            "source_expert": str(profile.name),
            "belief_count": len(beliefs),
            "edge_count": len(store.edges),
            "gap_count": len(gaps),
            "event_count": len(events),
            "contested_count": int(contested.get("open_count", 0) or 0),
        },
    }
    body = [
        f"# {profile.name}",
        "",
        "This OKF bundle is a regenerated Deepr derived view. The structured belief store remains canonical.",
        "",
        "## Profile",
        "",
        f"- Domain: {getattr(profile, 'domain', None) or 'general'}",
        f"- Description: {getattr(profile, 'description', None) or ''}",
        f"- As of: {as_of}",
        f"- Concepts: {len(beliefs)}",
        f"- Gaps: {len(gaps)}",
        f"- Open contested claims: {int(contested.get('open_count', 0) or 0)}",
        "",
        "## Concepts",
        "",
    ]
    if beliefs:
        for belief in beliefs:
            path = paths_by_id[belief.id]
            body.append(
                f"- [{_md_escape(belief.claim)}]({path}) "
                f"`{belief.domain or 'general'}, confidence {_fmt_num(belief.get_current_confidence())}`"
            )
    else:
        body.append("- No beliefs recorded yet.")
    body.extend(
        [
            "",
            "## Bundle Views",
            "",
            "- [Knowledge gaps](gaps.md)",
            "- [Contested claims](contested.md)",
            "- [Change log](log.md)",
            "",
            "## Live Queries",
            "",
            f'- `deepr expert why "{profile.name}" <claim>`',
            f'- `deepr expert what-changed "{profile.name}" --since 7d`',
            f'- `deepr expert contested "{profile.name}"`',
        ]
    )
    return _doc(fields, body)


def _build_concept(
    profile: Any,
    belief: Belief,
    store: BeliefStore,
    paths_by_id: dict[str, str],
    as_of: str,
) -> str:
    updated_at = _aware(belief.updated_at)
    created_at = _aware(belief.created_at)
    fields = {
        "type": "deepr.okf.concept",
        "title": belief.claim,
        "description": belief.claim,
        "tags": [belief.domain or "general", belief.source_type, belief.trust_class],
        "timestamp": updated_at.isoformat() if updated_at else as_of,
        "deepr": {
            "schema_version": OKF_SCHEMA_VERSION,
            "source_expert": str(profile.name),
            "belief_id": belief.id,
            "confidence": round(belief.confidence, 6),
            "current_confidence": round(belief.get_current_confidence(), 6),
            "trust_class": belief.trust_class,
            "source_type": belief.source_type,
            "evidence_refs": list(belief.evidence_refs),
            "contradictions_with": list(belief.contradictions_with),
        },
    }
    body = [
        f"# {belief.claim}",
        "",
        "## Claim",
        "",
        belief.claim,
        "",
        "## State",
        "",
        f"- Belief id: `{belief.id}`",
        f"- Domain: {belief.domain or 'general'}",
        f"- Confidence: {_fmt_num(belief.get_current_confidence())}",
        f"- Source type: {belief.source_type}",
        f"- Trust class: {belief.trust_class}",
        f"- Created: {created_at.isoformat() if created_at else ''}",
        f"- Updated: {updated_at.isoformat() if updated_at else ''}",
        "",
        "## Citations",
        "",
    ]
    if belief.evidence_refs:
        body.extend(f"- `{ref}`" for ref in belief.evidence_refs)
    else:
        body.append("- No citation references recorded.")

    edges = sorted(
        store.edges_for(belief.id),
        key=lambda edge: (edge.edge_type, _edge_target(edge, belief.id), ",".join(edge.provenance)),
    )
    body.extend(["", "## Relations", ""])
    if edges:
        beliefs_by_id = store.beliefs
        body.extend(_edge_line(edge, belief.id, paths_by_id, beliefs_by_id) for edge in edges)
    else:
        body.append("- No typed edges recorded.")
    body.extend(["", "[Back to index](../index.md)"])
    return _doc(fields, body)


def _build_gaps(profile: Any, manifest: Any, as_of: str) -> str:
    gaps = sorted(
        list(getattr(manifest, "gaps", []) or []),
        key=lambda gap: (
            bool(getattr(gap, "filled", False)),
            -float(getattr(gap, "ev_cost_ratio", 0.0) or 0.0),
            -int(getattr(gap, "priority", 0) or 0),
            str(getattr(gap, "topic", "")),
        ),
    )
    fields = {
        "type": "deepr.okf.gaps",
        "title": f"{profile.name} knowledge gaps",
        "description": "Open and filled knowledge gaps exported from the Deepr expert manifest.",
        "tags": [str(getattr(profile, "domain", "") or "general"), "gaps"],
        "timestamp": as_of,
        "deepr": {
            "schema_version": OKF_SCHEMA_VERSION,
            "source_expert": str(profile.name),
            "gap_count": len(gaps),
            "open_gap_count": sum(1 for gap in gaps if not bool(getattr(gap, "filled", False))),
        },
    }
    body = ["# Knowledge Gaps", ""]
    if not gaps:
        body.append("No knowledge gaps recorded.")
        return _doc(fields, body)

    for gap in gaps:
        status = "filled" if bool(getattr(gap, "filled", False)) else "open"
        body.extend(
            [
                f"## {getattr(gap, 'topic', '')}",
                "",
                f"- Gap id: `{getattr(gap, 'id', '')}`",
                f"- Status: {status}",
                f"- Priority: {getattr(gap, 'priority', 0)}",
                f"- Estimated cost: ${float(getattr(gap, 'estimated_cost', 0.0) or 0.0):.3f}",
                f"- Expected value: {_fmt_num(float(getattr(gap, 'expected_value', 0.0) or 0.0))}",
                f"- EV/cost ratio: {_fmt_num(float(getattr(gap, 'ev_cost_ratio', 0.0) or 0.0))}",
                "",
            ]
        )
        questions = list(getattr(gap, "questions", []) or [])
        if questions:
            body.append("Questions:")
            body.extend(f"- {question}" for question in questions)
            body.append("")
    return _doc(fields, body)


def _build_contested(profile: Any, store: BeliefStore, as_of: str) -> str:
    contested = contested_query(store, expert_name=str(profile.name))
    fields = {
        "type": "deepr.okf.contested",
        "title": f"{profile.name} contested claims",
        "description": "Recorded contradiction candidates exported with verification provenance.",
        "tags": [str(getattr(profile, "domain", "") or "general"), "contested"],
        "timestamp": as_of,
        "deepr": {
            "schema_version": OKF_SCHEMA_VERSION,
            "source_expert": str(profile.name),
            "open_count": int(contested.get("open_count", 0) or 0),
        },
    }
    body = ["# Contested Claims", ""]
    pairs = list(contested.get("pairs", []) or [])
    open_pairs = [pair for pair in pairs if pair.get("status") == "open"]
    if not open_pairs:
        body.append("No open contested claims recorded.")
        return _doc(fields, body)

    for index, pair in enumerate(open_pairs, 1):
        a = pair.get("a", {})
        b = pair.get("b", {})
        provenance = _contradiction_provenance(store, str(a.get("belief_id", "")), str(b.get("belief_id", "")))
        body.extend(
            [
                f"## Pair {index}",
                "",
                f"- A `{a.get('belief_id', '')}`: {a.get('claim', '')}",
                f"- B `{b.get('belief_id', '')}`: {b.get('claim', '')}",
                f"- Verification: {pair.get('verification', 'unverified')}",
                f"- Provenance: {', '.join(provenance) or 'unspecified'}",
                "",
            ]
        )
    return _doc(fields, body)


def _build_log(profile: Any, events: list[BeliefChange], as_of: str, paths_by_id: dict[str, str]) -> str:
    fields = {
        "type": "deepr.okf.log",
        "title": f"{profile.name} belief change log",
        "description": "Append-only belief event log exported as a portable Markdown view.",
        "tags": [str(getattr(profile, "domain", "") or "general"), "log"],
        "timestamp": as_of,
        "deepr": {
            "schema_version": OKF_SCHEMA_VERSION,
            "source_expert": str(profile.name),
            "event_count": len(events),
        },
    }
    body = ["# Change Log", ""]
    if not events:
        body.append("No belief events recorded.")
        return _doc(fields, body)

    for event in sorted(events, key=lambda change: _aware(change.timestamp) or datetime.min.replace(tzinfo=UTC)):
        event_time = _aware(event.timestamp)
        timestamp = event_time.isoformat() if event_time else ""
        concept_path = paths_by_id.get(event.belief_id)
        belief_ref = f"[`{event.belief_id}`]({concept_path})" if concept_path else f"`{event.belief_id}`"
        body.append(f"- {timestamp} `{event.change_type}` {belief_ref}: {event.new_claim or event.old_claim}")
        if event.reason:
            body.append(f"  - Reason: {event.reason}")
        if event.evidence:
            body.append(f"  - Evidence: `{event.evidence}`")
    return _doc(fields, body)


def _build_llms(profile: Any, bundle_name: str) -> str:
    return "\n".join(
        [
            f"# {OKF_MARKER}",
            f"# {bundle_name}",
            "",
            "This directory is a regenerated Deepr OKF bundle. The structured belief store is canonical.",
            "",
            "- Start at ./index.md",
            "- Concept pages live in ./concepts/",
            "- Open gaps are in ./gaps.md",
            "- Contested claims are in ./contested.md",
            "- Belief history is in ./log.md",
            "",
            f'For live state, prefer Deepr MCP tools for "{profile.name}" when available.',
            "",
        ]
    )


def _iter_markdown_files(path: Path) -> tuple[Path, list[Path]]:
    root = path.resolve()
    if root.is_file():
        return root.parent, [root]
    if root.is_dir():
        return root, sorted(root.rglob("*.md"))
    raise ValueError(f"OKF path not found: {path}")


def _is_concept_doc(relative_path: str, fields: dict[str, Any]) -> bool:
    doc_type = str(fields.get("type", ""))
    return doc_type.endswith(".concept") or relative_path.startswith("concepts/")


def build_okf_ingestion_corpus(path: Path) -> OKFIngestionCorpus:
    """Parse OKF concept Markdown into source text for ReportAbsorber."""
    base, markdown_files = _iter_markdown_files(path)
    concepts: list[tuple[str, dict[str, Any], str]] = []
    digest = sha256()

    for file_path in markdown_files:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        relative_path = file_path.resolve().relative_to(base).as_posix()
        fields, body = _split_frontmatter(text)
        if not _is_concept_doc(relative_path, fields):
            continue
        concepts.append((relative_path, fields, body))
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8", errors="replace"))
        digest.update(b"\0")

    if not concepts:
        raise ValueError(f"No OKF concept documents found in {path}")

    report_id = f"okf:{base.name}:{digest.hexdigest()[:12]}"
    lines = [
        "# OKF Import Corpus",
        "",
        f"Source path: {base}",
        f"Concept documents: {len(concepts)}",
        "",
        "These OKF concept documents are source text for Deepr's verified absorb gate.",
        "Only claims grounded in the concept body or frontmatter citations should be absorbed.",
        "",
    ]
    for relative_path, fields, body in concepts:
        title = str(fields.get("title") or fields.get("description") or Path(relative_path).stem)
        lines.extend(
            [
                f"## OKF concept: {title}",
                "",
                f"Source file: {relative_path}",
                "",
                "Frontmatter:",
                "```json",
                json.dumps(fields, indent=2, sort_keys=True),
                "```",
                "",
                "Body:",
                body or "(empty)",
                "",
            ]
        )

    return OKFIngestionCorpus(
        source_path=base,
        report_id=report_id,
        report_text="\n".join(lines),
        files=[relative_path for relative_path, _, _ in concepts],
        concept_count=len(concepts),
    )


def build_okf_bundle(
    profile: Any,
    store: BeliefStore,
    *,
    manifest: Any | None = None,
    include_llms: bool = True,
) -> OKFBundle:
    """Build a deterministic OKF bundle from structured expert state."""
    resolved_manifest = manifest if manifest is not None else profile.get_manifest()
    events = store.iter_events() if store.has_event_log else list(store.changes)
    as_of = _as_of(store, events)
    beliefs = _sorted_beliefs(store)
    paths_by_id = {belief.id: _concept_path(belief) for belief in beliefs}
    contested = contested_query(store, expert_name=str(profile.name))

    files: dict[str, str] = {
        "index.md": _build_index(profile, store, resolved_manifest, paths_by_id, as_of, events),
        "gaps.md": _build_gaps(profile, resolved_manifest, as_of),
        "contested.md": _build_contested(profile, store, as_of),
        "log.md": _build_log(profile, events, as_of, paths_by_id),
    }
    for belief in beliefs:
        files[paths_by_id[belief.id]] = _build_concept(profile, belief, store, paths_by_id, as_of)
    if include_llms:
        files["llms.txt"] = _build_llms(profile, str(profile.name))

    return OKFBundle(
        files=dict(sorted(files.items())),
        concept_count=len(beliefs),
        gap_count=len(list(getattr(resolved_manifest, "gaps", []) or [])),
        event_count=len(events),
        contested_count=int(contested.get("open_count", 0) or 0),
        as_of=as_of,
    )


def write_okf_bundle(bundle: OKFBundle, output_dir: Path, *, force: bool = False) -> OKFWriteResult:
    """Write an OKF bundle, refusing to overwrite hand-edited files."""
    root = output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[str, Path, str]] = []
    for relative_path, content in bundle.files.items():
        target = (root / relative_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Invalid bundle path: {relative_path}") from exc
        if target.exists() and OKF_MARKER not in target.read_text(encoding="utf-8", errors="replace") and not force:
            raise ValueError(
                f"{target} exists without the OKF derived-view marker. "
                "Use --force only when you intend to replace a hand-edited file."
            )
        targets.append((relative_path, target, content))

    for _, target, content in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    return OKFWriteResult(
        output_dir=root,
        files=[relative_path for relative_path, _, _ in targets],
        concept_count=bundle.concept_count,
        gap_count=bundle.gap_count,
        event_count=bundle.event_count,
        contested_count=bundle.contested_count,
        as_of=bundle.as_of,
    )
