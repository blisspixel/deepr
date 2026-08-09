"""The graph an expert already is, written down as one.

Deepr has held this structure since the study pass existed and has never
stored it. A finding carries ``corpus_shas`` - the retained sources its anchors
were actually found in. A position carries ``supported_by`` - the findings it
rests on. That is a two-hop provenance chain from a claim to a passage, kept as
three flat lists in two files, so the one question it exists to answer has to
be recomputed by hand every time anyone asks it.

**This is not the concept graph.** ``lazy_graph_rag`` holds a real
``KnowledgeGraph`` of concepts joined by co-occurrence, definition and
dependency, useful for retrieval and built for the chat path. Its nodes are
phrases with frequencies; its edges are all variants of "appeared near". It
cannot express "this position rests on that finding which was anchored in that
passage" without distorting both, so this is a separate artifact stored beside
it rather than a rewrite of it.

What having it as a graph makes cheap, none of which is cheap across two files:

- **A position whose chain does not reach a source.** The strongest integrity
  check available, and structural rather than statistical: it is not "few
  anchors matched", it is "this claim connects to no passage at all". A
  grounded ratio can average that away; a broken path cannot hide.
- **Evidence nobody used.** A grounded finding no position rests on is either a
  brief that missed something or a corpus that was read for nothing.
- **A source carrying more weight than its share.** Which passage the most
  claims trace back to, which is the concentration question asked where it can
  actually be answered - per claim, rather than per document.

It is temporal because every node records when it entered. An expert that has
existed six months should be able to answer "what did you think in June, and
what moved", and a graph whose nodes have no time cannot.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

EVIDENCE_GRAPH_SCHEMA_VERSION = "deepr-evidence-graph-v1"

NODE_SOURCE = "source"
NODE_FINDING = "finding"
NODE_POSITION = "position"

EDGE_ANCHORED_IN = "anchored_in"
"""finding -> source. An anchor from this finding was found in that passage."""

EDGE_RESTS_ON = "rests_on"
"""position -> finding. This claim is built on that reading."""


@dataclass
class GraphNode:
    """One thing an expert holds, with when it arrived."""

    id: str
    kind: str
    label: str
    first_seen: str = ""
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "first_seen": self.first_seen,
            **self.attrs,
        }


@dataclass
class GraphEdge:
    """A claim of support, pointing from the dependent thing to what it needs."""

    source: str
    target: str
    kind: str

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.source, "to": self.target, "kind": self.kind}


@dataclass
class EvidenceGraph:
    """Sources, findings and positions, and what rests on what."""

    expert_name: str
    schema_version: str = EVIDENCE_GRAPH_SCHEMA_VERSION
    built_at: str = ""
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def _by_kind(self, kind: str) -> list[GraphNode]:
        return [n for n in self.nodes if n.kind == kind]

    @property
    def sources(self) -> list[GraphNode]:
        return self._by_kind(NODE_SOURCE)

    @property
    def findings(self) -> list[GraphNode]:
        return self._by_kind(NODE_FINDING)

    @property
    def positions(self) -> list[GraphNode]:
        return self._by_kind(NODE_POSITION)

    def _outgoing(self, node_id: str, kind: str) -> list[str]:
        return [e.target for e in self.edges if e.source == node_id and e.kind == kind]

    def reaches_a_source(self, position_id: str) -> bool:
        """Whether this position's support chain arrives at a retained passage.

        Two hops, both required. A position resting on findings that are
        themselves anchored in nothing is not partially grounded - it is a
        claim with a bibliography that cites empty pages.
        """
        for finding_id in self._outgoing(position_id, EDGE_RESTS_ON):
            if self._outgoing(finding_id, EDGE_ANCHORED_IN):
                return True
        return False

    @property
    def unsupported_positions(self) -> list[GraphNode]:
        """Positions whose chain never reaches a source. The integrity check."""
        return [p for p in self.positions if not self.reaches_a_source(p.id)]

    @property
    def unused_findings(self) -> list[GraphNode]:
        """Grounded readings no position rests on.

        Either the brief missed something or the corpus was read for nothing.
        Both are worth knowing and neither is visible without the edges.
        """
        used = {e.target for e in self.edges if e.kind == EDGE_RESTS_ON}
        return [f for f in self.findings if f.id not in used and f.attrs.get("grounded")]

    def load_bearing_sources(self, limit: int = 5) -> list[tuple[str, int]]:
        """Which passages the most claims trace back to.

        Concentration asked where it can be answered: per claim rather than per
        document. A corpus of thirty sources where every position routes
        through two of them is two sources wearing thirty hats, and no
        document-level count shows that.
        """
        counts: Counter[str] = Counter()
        for position in self.positions:
            reached: set[str] = set()
            for finding_id in self._outgoing(position.id, EDGE_RESTS_ON):
                reached.update(self._outgoing(finding_id, EDGE_ANCHORED_IN))
            counts.update(reached)
        labels = {n.id: n.label for n in self.sources}
        return [(labels.get(sha, sha), n) for sha, n in counts.most_common(limit)]

    @property
    def is_formed(self) -> bool:
        """Whether this is a graph rather than a pile of nodes.

        Requires an actual traversal to exist: at least one position that
        reaches a source through a finding. Counting nodes would let a study
        with no brief - findings and sources, no path between claims and
        passages - report a formed graph.
        """
        return any(self.reaches_a_source(p.id) for p in self.positions)

    def stats(self) -> dict[str, Any]:
        return {
            "sources": len(self.sources),
            "findings": len(self.findings),
            "positions": len(self.positions),
            "edges": len(self.edges),
            "unsupported_positions": len(self.unsupported_positions),
            "unused_findings": len(self.unused_findings),
            "is_formed": self.is_formed,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "expert": self.expert_name,
            "built_at": self.built_at,
            "stats": self.stats(),
            "load_bearing_sources": [{"source": s, "positions": n} for s, n in self.load_bearing_sources()],
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceGraph:
        graph = cls(
            expert_name=str(data.get("expert") or ""),
            schema_version=str(data.get("schema_version") or EVIDENCE_GRAPH_SCHEMA_VERSION),
            built_at=str(data.get("built_at") or ""),
        )
        for raw in data.get("nodes") or []:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            known = {"id", "kind", "label", "first_seen"}
            graph.nodes.append(
                GraphNode(
                    id=str(raw["id"]),
                    kind=str(raw.get("kind") or ""),
                    label=str(raw.get("label") or ""),
                    first_seen=str(raw.get("first_seen") or ""),
                    attrs={k: v for k, v in raw.items() if k not in known},
                )
            )
        for raw in data.get("edges") or []:
            if not isinstance(raw, dict):
                continue
            if raw.get("from") and raw.get("to"):
                graph.edges.append(
                    GraphEdge(source=str(raw["from"]), target=str(raw["to"]), kind=str(raw.get("kind") or ""))
                )
        return graph


def _entry_sha(entry: Any) -> str:
    """The retained source's hash, whatever the store calls it.

    ``CorpusStore`` entries name it ``sha256`` while findings record the same
    value under ``corpus_shas``. Reading the wrong attribute silently produced
    source nodes with empty ids, which dropped every anchored_in edge as
    dangling and reported a fully-supported expert as having no position that
    reaches a source. A wrong attribute name is indistinguishable from real
    corruption in the output, so both names are accepted here.
    """
    for attribute in ("sha256", "sha"):
        value = str(getattr(entry, attribute, "") or "")
        if value:
            return value
    return ""


def _source_nodes(corpus_entries: list[Any], at: str) -> list[GraphNode]:
    nodes: list[GraphNode] = []
    for entry in corpus_entries:
        sha = _entry_sha(entry)
        if not sha:
            continue
        nodes.append(
            GraphNode(
                id=sha,
                kind=NODE_SOURCE,
                label=str(getattr(entry, "title", "") or getattr(entry, "origin_key", "") or sha[:12]),
                first_seen=str(getattr(entry, "added_at", "") or getattr(entry, "fetched_at", "") or at),
                attrs={
                    "origin_key": str(getattr(entry, "origin_key", "") or ""),
                    "publisher": str(getattr(entry, "publisher", "") or ""),
                },
            )
        )
    return nodes


def build_graph(
    *,
    expert_name: str,
    study: Any,
    brief: Any,
    corpus_entries: list[Any] | None = None,
    at: str = "",
) -> EvidenceGraph:
    """Materialise the chain that already exists across study.json and brief.json.

    Nothing here is inferred. Every edge is copied from a field that was
    already recorded: ``corpus_shas`` on a finding, ``supported_by`` on a
    position. The graph is a change of storage, not a new claim, which is why
    it can be rebuilt from scratch at any time without a model call.
    """
    graph = EvidenceGraph(expert_name=expert_name, built_at=at)
    graph.nodes.extend(_source_nodes(corpus_entries or [], at))
    known_sources = {n.id for n in graph.nodes}

    findings = list(getattr(study, "findings", []) or []) if study is not None else []
    for finding in findings:
        finding_id = str(getattr(finding, "finding_id", "") or "")
        if not finding_id:
            continue
        graph.nodes.append(
            GraphNode(
                id=finding_id,
                kind=NODE_FINDING,
                label=str(getattr(finding, "title", "") or finding_id),
                first_seen=str(getattr(study, "started_at", "") or at),
                attrs={
                    "lens": str(getattr(finding, "lens", "") or ""),
                    "grounded": bool(getattr(finding, "is_grounded", False)),
                },
            )
        )
        for sha in set(getattr(finding, "corpus_shas", []) or []):
            # Only to sources actually retained. An anchor naming a document
            # that is no longer in the corpus is a dangling edge, and a
            # dangling edge would let a position claim support from a passage
            # nobody can open.
            if str(sha) in known_sources:
                graph.edges.append(GraphEdge(source=finding_id, target=str(sha), kind=EDGE_ANCHORED_IN))

    known_findings = {n.id for n in graph.findings}
    positions = list(getattr(brief, "positions", []) or []) if brief is not None else []
    for index, position in enumerate(positions, start=1):
        position_id = f"position-{index}"
        graph.nodes.append(
            GraphNode(
                id=position_id,
                kind=NODE_POSITION,
                label=str(getattr(position, "question", "") or position_id),
                # Left empty rather than stamped with the build time. A
                # position's real first_seen is when the brief was written,
                # and a brief carries no timestamp - so filling it from `at`
                # produced a field that equalled built_at and reset on every
                # rebuild. An honestly empty field beats a confidently wrong
                # one, and this is the first thing V2 has to fix.
                first_seen="",
                attrs={
                    "stance": str(getattr(position, "stance", "") or ""),
                    "likelihood": str(getattr(position, "likelihood", "") or ""),
                    "confidence": str(getattr(position, "confidence", "") or ""),
                },
            )
        )
        for finding_id in getattr(position, "supported_by", []) or []:
            if str(finding_id) in known_findings:
                graph.edges.append(GraphEdge(source=position_id, target=str(finding_id), kind=EDGE_RESTS_ON))

    return graph


def render_graph(graph: EvidenceGraph) -> str:
    """What the graph shows that the flat files could not."""
    stats = graph.stats()
    lines = [
        f"# {graph.expert_name}: evidence graph",
        "",
        f"{stats['sources']} source(s), {stats['findings']} finding(s), "
        f"{stats['positions']} position(s), {stats['edges']} edge(s).",
        "",
    ]

    if not stats["is_formed"]:
        lines += [
            "No position reaches a source through a finding, so this is a pile of nodes "
            "rather than a graph. Run study and brief before reading anything into it.",
            "",
        ]

    if graph.unsupported_positions:
        lines += ["## Positions that reach no source", ""]
        lines += [f"- {p.label}" for p in graph.unsupported_positions]
        lines += ["", "_A claim with a bibliography citing empty pages. Re-brief or re-study._", ""]

    if graph.unused_findings:
        lines += [
            "## Evidence nothing rests on",
            "",
            f"{len(graph.unused_findings)} grounded finding(s) support no position. Either the "
            "brief missed something or this part of the corpus was read for nothing.",
            "",
        ]

    if load_bearing := graph.load_bearing_sources():
        lines += ["## What the claims actually rest on", ""]
        lines += [f"- {label}: {count} position(s)" for label, count in load_bearing]
        lines += [
            "",
            "_Concentration per claim rather than per document. Thirty sources where every "
            "position routes through two of them is two sources wearing thirty hats._",
            "",
        ]

    return "\n".join(lines)
