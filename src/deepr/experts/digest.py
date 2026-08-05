"""Regenerated expert digest - a browsable view over the structured store.

The Phase E regeneration invariant made executable (ROADMAP Phase 4, v2.14
step 4): the belief store (beliefs + typed edges + event log) is canonical;
this digest is a derived view, fully regenerable, never hand-edited as
authoritative. Synthesis happens at compile time over structured truth -
organizing, not generating: no LLM call, cost $0.

Byte-stable by design: ordering is deterministic (confidence desc, then
claim) and the "as of" timestamp derives from the latest belief event, not
the wall clock - regenerating from an unchanged store produces an identical
file. A reader sees recorded contradiction candidates and their verification
assurance, not a smoothed narrative or a lexical candidate mislabeled as fact.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from deepr.experts.belief_edges import Edge
from deepr.experts.beliefs import Belief, BeliefStore
from deepr.experts.perspective import contested as contested_query

# Marker the CLI checks before overwriting: a digest missing this line may
# have been hand-edited, which violates the regeneration invariant.
DIGEST_MARKER = "<!-- deepr:digest derived-view regenerable -->"

_BANNER = (
    f"{DIGEST_MARKER}\n"
    "<!-- DERIVED VIEW - do not hand-edit. The belief store is canonical; "
    "regenerate with: deepr expert digest NAME -->\n"
)


def _as_of(store: BeliefStore) -> str:
    """Latest knowledge timestamp - from events when available, else beliefs.

    Using the store's own latest change (not the wall clock) keeps the
    digest byte-stable across regenerations of an unchanged store.
    """
    timestamps: list[datetime] = []
    if store.has_event_log:
        events = store.iter_events()
        timestamps = [e.timestamp for e in events]
    if not timestamps:
        timestamps = [b.updated_at for b in store.beliefs.values()]
    if not timestamps:
        return "never"
    latest = max(t if t.tzinfo else t.replace(tzinfo=UTC) for t in timestamps)
    return latest.isoformat()


def _belief_line(belief: Belief) -> str:
    conf = belief.get_current_confidence()
    flags = ""
    if belief.contradictions_with:
        flags = f"  **[contested x{len(belief.contradictions_with)}]**"
    evidence = f", {len(belief.evidence_refs)} source(s)" if belief.evidence_refs else ", no sources"
    return f"- ({conf:.2f}) {belief.claim}{flags}  `{belief.source_type}{evidence}`"


def _endpoint_label(store: BeliefStore, belief_id: str) -> str:
    belief = store.beliefs.get(belief_id)
    if belief is None:
        return f"[{belief_id}] missing belief"
    return f"[{belief_id}] {belief.claim}"


def _temporal_edges(store: BeliefStore) -> list[Edge]:
    return sorted(
        (edge for edge in store.edges.values() if edge.temporal_contexts),
        key=lambda edge: (edge.edge_type, edge.src_id, edge.dst_id),
    )


def _temporal_context_line(context: dict[str, str]) -> str:
    valid_from = context.get("valid_from", "")
    valid_until = context.get("valid_until", "")
    observed_at = context.get("observed_at", "")
    temporal_scope = context.get("temporal_scope", "")
    parts: list[str] = []
    if valid_from or valid_until:
        parts.append(f"valid {valid_from or 'unknown'} to {valid_until or 'unknown'}")
    if observed_at:
        parts.append(f"observed {observed_at}")
    if temporal_scope:
        parts.append(f"scope {temporal_scope}")
    return "; ".join(parts) or "temporal context recorded"


def _append_temporal_edge_section(lines: list[str], store: BeliefStore) -> None:
    temporal_edges = _temporal_edges(store)
    if not temporal_edges:
        return
    lines += [
        "## Temporal Edge Qualifiers",
        "",
        "These time-scoped relationships are derived from stored edge metadata; the belief graph remains canonical.",
        "",
    ]
    for edge in temporal_edges:
        provenance = ", ".join(edge.provenance) if edge.provenance else "none"
        lines.append(
            f"- `{edge.edge_type}` {_endpoint_label(store, edge.src_id)} -> "
            f"{_endpoint_label(store, edge.dst_id)} (provenance: {provenance})"
        )
        for context in edge.temporal_contexts:
            lines.append(f"  - {_temporal_context_line(context)}")
    lines.append("")


def _sorted_beliefs(beliefs: list[Belief]) -> list[Belief]:
    return sorted(beliefs, key=lambda b: (-b.get_current_confidence(), b.claim))


def _section(lines: list[str], title: str, beliefs: list[Belief], *, empty_note: str = "") -> None:
    lines += [f"## {title}", ""]
    if not beliefs:
        if empty_note:
            lines += [f"*{empty_note}*", ""]
        else:
            lines += ["*None.*", ""]
        return
    lines += [_belief_line(b) for b in _sorted_beliefs(beliefs)]
    lines.append("")


def _partition_wiki_sections(beliefs: list[Belief]) -> dict[str, list[Belief]]:
    """Structural wiki partitions (trust/provenance only; no semantic scoring)."""
    stance: list[Belief] = []
    multi: list[Belief] = []
    secondary: list[Belief] = []
    tertiary: list[Belief] = []
    contested: list[Belief] = []
    for b in beliefs:
        if b.contradictions_with:
            contested.append(b)
        trust = (b.trust_class or "tertiary").lower()
        if trust == "primary":
            stance.append(b)
        elif b._independent_source_count() >= 2:
            multi.append(b)
        elif trust == "secondary":
            secondary.append(b)
        else:
            tertiary.append(b)
    return {
        "stance": stance,
        "multi_source": multi,
        "secondary": secondary,
        "tertiary": tertiary,
        "contested": contested,
    }


def _source_inventory(beliefs: list[Belief]) -> list[str]:
    """Compact non-quote evidence origins, sorted for byte stability."""
    keys: set[str] = set()
    for b in beliefs:
        for ref in b.evidence_refs:
            token = str(ref).strip()
            if not token or any(ch.isspace() for ch in token):
                continue
            if token.lower().startswith("conflicting:"):
                continue
            keys.add(token)
    return sorted(keys)


def build_digest(store: BeliefStore, *, expert_name: str = "") -> str:
    """Compile the store into a browsable Markdown digest. Deterministic, $0.

    Wiki-shaped sections (stance, multi-source, secondary, tertiary, contested,
    sources) are structural partitions over trust class and provenance. Full
    domain inventory remains for complete browsing. Not a semantic maturity
    narrative.
    """
    name = expert_name or store.expert_name
    beliefs = list(store.beliefs.values())

    by_domain: dict[str, list[Belief]] = defaultdict(list)
    for b in beliefs:
        by_domain[b.domain or "general"].append(b)
    for domain_beliefs in by_domain.values():
        domain_beliefs.sort(key=lambda b: (-b.get_current_confidence(), b.claim))

    conflicts = contested_query(store, expert_name=name)
    edge_count = len(store.edges)
    supports_count = sum(1 for e in store.edges.values() if e.edge_type == "supports")
    parts = _partition_wiki_sections(beliefs)
    sources = _source_inventory(beliefs)

    lines: list[str] = [
        _BANNER,
        f"# Expert Digest: {name}",
        "",
        f"As of: {_as_of(store)}",
        "",
        f"**{len(beliefs)}** beliefs across **{len(by_domain)}** domain(s) - "
        f"**{edge_count}** graph edge(s) ({supports_count} supporting) - "
        f"**{conflicts['open_count']}** open contradiction candidate(s) "
        f"({conflicts['model_confirmed_count']} model-confirmed, {conflicts['unverified_count']} unverified) - "
        f"**{len(sources)}** compact source origin(s)",
        "",
        "Wiki-shaped sections below are **derived partitions** (trust class and "
        "provenance). The belief store remains canonical. Regenerate after absorb/sync.",
        "",
        "## Wiki index",
        "",
        "- Stance (primary trust)",
        "- Multi-source corroborated",
        "- Domain knowledge (secondary)",
        "- Research / tertiary",
        "- Contested",
        "- Source inventory",
        "- Full inventory by domain",
        "",
    ]

    _section(
        lines,
        "Stance (operator / primary)",
        parts["stance"],
        empty_note="No primary-trust beliefs. Project stance may be absorbed with --trust-class primary.",
    )
    _section(
        lines,
        "Multi-source corroborated",
        parts["multi_source"],
        empty_note="No multi-origin claims yet. Absorb a second independent source to corroborate.",
    )
    _section(
        lines,
        "Domain knowledge (secondary)",
        parts["secondary"],
        empty_note="No secondary-trust beliefs. Prefer official docs via absorb --trust-class secondary.",
    )
    _section(
        lines,
        "Research / tertiary",
        parts["tertiary"],
        empty_note="No tertiary research claims.",
    )

    if conflicts["open_count"]:
        lines += ["## Recorded Contradiction Candidates", ""]
        lines.append(
            "These candidates are surfaced deliberately, not smoothed over. "
            "Verification labels describe process assurance, not independent semantic truth. "
            f'Adjudicate with: `deepr expert resolve-conflicts "{name}"`'
        )
        lines.append("")
        for pair in conflicts["pairs"]:
            if pair["status"] != "open":
                continue
            lines.append(
                f"- **A** ({pair['a']['confidence']:.2f}, {pair.get('verification', 'unverified')}): "
                f"{pair['a']['claim']}"
            )
            lines.append(f"  **B** ({pair['b']['confidence']:.2f}): {pair['b']['claim']}")
        lines.append("")

    _section(
        lines,
        "Contested beliefs",
        parts["contested"],
        empty_note="No beliefs currently marked with contradiction links.",
    )

    lines += ["## Source inventory", ""]
    if sources:
        lines += [f"- `{s}`" for s in sources]
        lines.append("")
    else:
        lines += ["*No compact source origins recorded.*", ""]

    _append_temporal_edge_section(lines, store)

    lines += ["## Full inventory by domain", ""]
    for domain in sorted(by_domain):
        domain_beliefs = by_domain[domain]
        lines += [f"### {domain} ({len(domain_beliefs)})", ""]
        lines += [_belief_line(b) for b in domain_beliefs]
        lines.append("")

    if not beliefs:
        lines += ["*No beliefs recorded yet.*", ""]

    lines += [
        "---",
        "",
        "Deepen research corpus (Distill) then absorb: "
        f'`deepr expert deepen-plan "{name}"` - '
        "Queries over this knowledge (always fresher than this file): "
        f'`deepr expert why "{name}" <claim>` - '
        f'`deepr expert what-changed "{name}" --since 7d` - '
        f'`deepr expert contested "{name}"` - '
        f'`deepr expert quality "{name}"`',
        "",
    ]
    return "\n".join(lines)
