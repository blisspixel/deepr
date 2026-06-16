"""Regenerated expert digest - a browsable view over the structured store.

The Phase E regeneration invariant made executable (ROADMAP Phase 4, v2.14
step 4): the belief store (beliefs + typed edges + event log) is canonical;
this digest is a derived view, fully regenerable, never hand-edited as
authoritative. Synthesis happens at compile time over structured truth -
organizing, not generating: no LLM call, cost $0.

Byte-stable by design: ordering is deterministic (confidence desc, then
claim) and the "as of" timestamp derives from the latest belief event, not
the wall clock - regenerating from an unchanged store produces an identical
file. A reader sees open conflicts (contradiction flags), not a smoothed
narrative.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

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


def build_digest(store: BeliefStore, *, expert_name: str = "") -> str:
    """Compile the store into a browsable Markdown digest. Deterministic, $0."""
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

    lines: list[str] = [
        _BANNER,
        f"# Expert Digest: {name}",
        "",
        f"As of: {_as_of(store)}",
        "",
        f"**{len(beliefs)}** beliefs across **{len(by_domain)}** domain(s) - "
        f"**{edge_count}** graph edge(s) ({supports_count} supporting) - "
        f"**{conflicts['open_count']}** open contradiction(s)",
        "",
    ]

    if conflicts["open_count"]:
        lines += ["## Open Contradictions", ""]
        lines.append(
            "These conflicts are surfaced deliberately, not smoothed over. "
            f'Adjudicate with: `deepr expert resolve-conflicts "{name}"`'
        )
        lines.append("")
        for pair in conflicts["pairs"]:
            if pair["status"] != "open":
                continue
            lines.append(f"- **A** ({pair['a']['confidence']:.2f}): {pair['a']['claim']}")
            lines.append(f"  **B** ({pair['b']['confidence']:.2f}): {pair['b']['claim']}")
        lines.append("")

    for domain in sorted(by_domain):
        domain_beliefs = by_domain[domain]
        lines += [f"## {domain} ({len(domain_beliefs)})", ""]
        lines += [_belief_line(b) for b in domain_beliefs]
        lines.append("")

    if not beliefs:
        lines += ["*No beliefs recorded yet.*", ""]

    lines += [
        "---",
        "",
        "Queries over this knowledge (always fresher than this file): "
        f'`deepr expert why "{name}" <claim>` - '
        f'`deepr expert what-changed "{name}" --since 7d` - '
        f'`deepr expert contested "{name}"`',
        "",
    ]
    return "\n".join(lines)
