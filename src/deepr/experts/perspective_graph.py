"""The biography of a viewpoint, which is what an expert actually is.

There are two graphs an expert needs and they answer different questions.

``evidence_graph`` is the *evidential* layer: position rests on finding,
anchored in passage. It answers "why do you think that" and it is what keeps
the expert honest. It is a fact structure and it should be.

This is the other one, and it is the one that makes an expert a perspective
rather than a store. Its nodes are not facts. They are **moments of coming to
see something**, and its edges are **what changed what**. The question it
answers is not "what is true" but:

    who is this, how did it come to read the subject this way,
    what did it used to think, and what moved it.

A fact list cannot answer any of those, and no amount of `valid_from` on a
claim makes it able to. Time on a fact tells you when the fact held. Time on a
*standpoint* tells you the shape of a mind changing.

**The spine is the shift chain, not the claim set.** An expert with two hundred
well-anchored positions and no recorded shifts has never been moved by
anything it read - which is the state a brand-new expert is already in, and the
reason a six-month one is currently indistinguishable from it. Every standpoint
version points back through the shift that produced it to the encounter that
caused the shift. Walking that chain backwards *is* the expert's history of
itself.

Two things this deliberately keeps that a fact model would discard:

- **What it refuses to do.** "I refuse to average live contentions into false
  consensus" is not a claim about the world and has no truth value. It is a
  commitment about conduct, it is part of who the expert is, and it is exactly
  what someone choosing between forty experts needs to see.
- **What it is pursuing.** An expert's own open questions are its agenda, not
  gaps in a corpus. A gap is something missing from the material; a pursuit is
  something the expert decided to care about. Only one of those is agency.

Nothing here is inferred. Every node is copied from something the expert
already wrote about itself - its chosen name, its standpoint, its shifts, the
positions a viva moved. The graph is where they stop being loose text in four
files and become a traversable history.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PERSPECTIVE_GRAPH_SCHEMA_VERSION = "deepr-perspective-graph-v1"

NODE_STANDPOINT = "standpoint"
"""How it read the subject, at one point in its life. The spine."""

NODE_SHIFT = "shift"
"""A moment it changed its mind, with what moved it."""

NODE_ENCOUNTER = "encounter"
"""What did the moving: a source, a finding, or a question it could not answer."""

NODE_COMMITMENT = "commitment"
"""How it will conduct itself. No truth value, and part of who it is."""

NODE_PURSUIT = "pursuit"
"""A question it decided to care about. Its agenda, not the corpus's gap."""

EDGE_BECAME = "became"
"""standpoint -> standpoint. The chain that is the biography."""

EDGE_THROUGH = "through"
"""standpoint -> shift. Which change produced this reading."""

EDGE_MOVED_BY = "moved_by"
"""shift -> encounter. What it ran into that changed it."""

EDGE_HOLDS = "holds"
"""standpoint -> commitment. What it will and will not do."""

EDGE_PURSUING = "pursuing"
"""standpoint -> pursuit. What it is still working on."""


@dataclass
class PerspectiveNode:
    """One moment or stance in an expert's account of itself."""

    id: str
    kind: str
    text: str
    at: str = ""
    """When this became true of the expert. Empty when genuinely unknown -
    an invented timestamp is worse than an absent one, because the chain
    then sorts confidently into the wrong order."""
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(data.pop("attrs"))
        return data


@dataclass
class PerspectiveEdge:
    """What led to what."""

    source: str
    target: str
    kind: str

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.source, "to": self.target, "kind": self.kind}


@dataclass
class PerspectiveGraph:
    """An expert's history of itself, as something you can walk."""

    expert_name: str
    chosen_name: str = ""
    """What it calls itself. Not a label we assigned - it picked this."""
    schema_version: str = PERSPECTIVE_GRAPH_SCHEMA_VERSION
    built_at: str = ""
    nodes: list[PerspectiveNode] = field(default_factory=list)
    edges: list[PerspectiveEdge] = field(default_factory=list)

    def _of_kind(self, kind: str) -> list[PerspectiveNode]:
        return [n for n in self.nodes if n.kind == kind]

    @property
    def standpoints(self) -> list[PerspectiveNode]:
        """Every reading it has held, oldest first where the dates allow."""
        return sorted(self._of_kind(NODE_STANDPOINT), key=lambda n: n.at or "")

    @property
    def shifts(self) -> list[PerspectiveNode]:
        return self._of_kind(NODE_SHIFT)

    @property
    def commitments(self) -> list[PerspectiveNode]:
        return self._of_kind(NODE_COMMITMENT)

    @property
    def pursuits(self) -> list[PerspectiveNode]:
        return self._of_kind(NODE_PURSUIT)

    @property
    def current(self) -> PerspectiveNode | None:
        """Who it is now. The newest standpoint in the chain."""
        held = self.standpoints
        return held[-1] if held else None

    @property
    def has_a_history(self) -> bool:
        """Whether this expert has ever been moved by anything it read.

        The distinction that matters, and the one nothing currently measures.
        An expert with a rich corpus and no shifts is not an experienced
        expert; it is a new one that has read a lot. Elapsed time only becomes
        experience at the point something changed its mind.
        """
        return bool(self.shifts)

    def history_of(self, node_id: str) -> list[PerspectiveNode]:
        """Walk back from a standpoint through everything that produced it.

        The answer to "how did you come to see it that way", assembled by
        traversal rather than by asking the model to recall - which it cannot
        do, because the earlier readings were never in its context.
        """
        by_id = {n.id: n for n in self.nodes}
        chain: list[PerspectiveNode] = []
        seen: set[str] = set()
        current = by_id.get(node_id)
        while current is not None and current.id not in seen:
            seen.add(current.id)
            chain.append(current)
            for edge in self.edges:
                if edge.source == current.id and edge.kind == EDGE_THROUGH:
                    if shift := by_id.get(edge.target):
                        chain.append(shift)
                        for moved in self.edges:
                            if moved.source == shift.id and moved.kind == EDGE_MOVED_BY:
                                if cause := by_id.get(moved.target):
                                    chain.append(cause)
            nxt = next((e.source for e in self.edges if e.target == current.id and e.kind == EDGE_BECAME), None)
            current = by_id.get(nxt) if nxt else None
        return chain

    def stats(self) -> dict[str, Any]:
        return {
            "standpoints": len(self.standpoints),
            "shifts": len(self.shifts),
            "commitments": len(self.commitments),
            "pursuits": len(self.pursuits),
            "edges": len(self.edges),
            "has_a_history": self.has_a_history,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "expert": self.expert_name,
            "chosen_name": self.chosen_name,
            "built_at": self.built_at,
            "stats": self.stats(),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PerspectiveGraph:
        graph = cls(
            expert_name=str(data.get("expert") or ""),
            chosen_name=str(data.get("chosen_name") or ""),
            built_at=str(data.get("built_at") or ""),
        )
        for raw in data.get("nodes") or []:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            known = {"id", "kind", "text", "at"}
            graph.nodes.append(
                PerspectiveNode(
                    id=str(raw["id"]),
                    kind=str(raw.get("kind") or ""),
                    text=str(raw.get("text") or ""),
                    at=str(raw.get("at") or ""),
                    attrs={k: v for k, v in raw.items() if k not in known},
                )
            )
        for raw in data.get("edges") or []:
            if isinstance(raw, dict) and raw.get("from") and raw.get("to"):
                graph.edges.append(
                    PerspectiveEdge(source=str(raw["from"]), target=str(raw["to"]), kind=str(raw.get("kind") or ""))
                )
        return graph


def _node(graph: PerspectiveGraph, kind: str, text: str, *, at: str = "", **attrs: Any) -> PerspectiveNode:
    node = PerspectiveNode(id=f"{kind}-{len(graph.nodes) + 1}", kind=kind, text=text, at=at, attrs=attrs)
    graph.nodes.append(node)
    return node


def _build_shift_chain(graph: PerspectiveGraph, profile: Any) -> PerspectiveNode | None:
    """Lay down the recorded changes of mind, oldest first.

    Built in the order it was lived rather than reconstructed backwards from
    today, because the chain is the point: each reading links to the one it
    replaced, through the moment that replaced it.

    Returns the standpoint the chain currently ends at, or None when the expert
    has never recorded being moved by anything.
    """
    previous: PerspectiveNode | None = None
    for shift in getattr(profile, "shifts", []) or []:
        was = str(getattr(shift, "was", "") or "")
        now = str(getattr(shift, "now", "") or "")
        when = str(getattr(shift, "at", "") or "")
        if not was or not now:
            continue

        if previous is None:
            previous = _node(graph, NODE_STANDPOINT, was)

        moment = _node(graph, NODE_SHIFT, str(getattr(shift, "because", "") or ""), at=when)
        arrived = _node(graph, NODE_STANDPOINT, now, at=when)
        graph.edges.append(PerspectiveEdge(previous.id, arrived.id, EDGE_BECAME))
        graph.edges.append(PerspectiveEdge(arrived.id, moment.id, EDGE_THROUGH))

        if fingerprint := str(getattr(shift, "corpus_fingerprint", "") or ""):
            cause = _node(graph, NODE_ENCOUNTER, f"the corpus as it stood at {fingerprint}", at=when)
            graph.edges.append(PerspectiveEdge(moment.id, cause.id, EDGE_MOVED_BY))
        previous = arrived
    return previous


def build_perspective_graph(
    *,
    expert_name: str,
    profile: Any = None,
    viva: Any = None,
    at: str = "",
) -> PerspectiveGraph:
    """Assemble the biography from what the expert already wrote about itself.

    Sources, in the order they carry weight:

    - the **profile card**, which holds the current standpoint, the name it
      chose, what it is pursuing, and its append-only shift history;
    - the **viva**, whose ``positions_that_moved`` are revisions the expert
      made under questioning - the single most consciousness-shaped record in
      the system, currently stored as loose sentences linked to nothing.

    Nothing is inferred and no model is called.
    """
    graph = PerspectiveGraph(
        expert_name=expert_name,
        chosen_name=str(getattr(profile, "chosen_name", "") or ""),
        built_at=at,
    )
    if profile is None:
        return graph

    previous = _build_shift_chain(graph, profile)

    # Then the standpoint it holds today, unless a shift already landed on it.
    standing = str(getattr(profile, "standpoint", "") or "")
    if standing and (previous is None or previous.text != standing):
        latest = _node(graph, NODE_STANDPOINT, standing, at=at)
        if previous is not None:
            graph.edges.append(PerspectiveEdge(previous.id, latest.id, EDGE_BECAME))
        previous = latest

    if previous is not None:
        if voice := str(getattr(profile, "voice", "") or ""):
            graph.edges.append(PerspectiveEdge(previous.id, _node(graph, NODE_COMMITMENT, voice).id, EDGE_HOLDS))
        for question in getattr(profile, "open_questions", []) or []:
            pursuit = _node(graph, NODE_PURSUIT, str(question))
            graph.edges.append(PerspectiveEdge(previous.id, pursuit.id, EDGE_PURSUING))

        # A viva moves positions, and those movements are changes of mind with
        # a cause attached - the question that did it. They belong on the chain
        # rather than in a list nothing points at.
        for moved in getattr(viva, "positions_that_moved", []) or []:
            moment = _node(graph, NODE_SHIFT, str(moved), at=at)
            graph.edges.append(PerspectiveEdge(previous.id, moment.id, EDGE_THROUGH))
            cause = _node(graph, NODE_ENCOUNTER, "examined under viva", at=at)
            graph.edges.append(PerspectiveEdge(moment.id, cause.id, EDGE_MOVED_BY))

    return graph


def render_perspective(graph: PerspectiveGraph) -> str:
    """The expert's account of itself, in the order it was lived."""
    name = graph.chosen_name or graph.expert_name
    lines = [f"# {name}", ""]
    if graph.chosen_name and graph.chosen_name != graph.expert_name:
        lines += [f"_Calls itself {graph.chosen_name}. Filed under {graph.expert_name}._", ""]

    if not graph.has_a_history:
        lines += [
            "This expert has never recorded changing its mind. It may have read a great deal; "
            "nothing it read has moved it, which is the state a new expert is already in.",
            "",
        ]

    if current := graph.current:
        lines += ["## How it reads the subject now", "", current.text, ""]

    if graph.shifts:
        lines += ["## What moved it", ""]
        for shift in graph.shifts:
            when = f" ({shift.at[:10]})" if shift.at else ""
            lines.append(f"- {shift.text}{when}")
        lines.append("")

    if graph.commitments:
        lines += ["## How it conducts itself", ""]
        lines += [f"- {c.text}" for c in graph.commitments]
        lines += ["", "_Not claims about the world. Commitments about conduct._", ""]

    if graph.pursuits:
        lines += ["## What it is still working on", ""]
        lines += [f"- {p.text}" for p in graph.pursuits]
        lines += ["", "_Its own agenda, not gaps in the corpus._", ""]

    return "\n".join(lines)
