# Design: Temporal Knowledge Graph (graph-structured expert memory)

Target: v2.14. Roadmap: Phase 4 "Graph-structured expert memory".
Status: design. The query contracts shipped first (`what_changed`,
`contested` in v2.13.1) deliberately, to fix the external surface before the
internal model changes.

## Problem

An expert today stores beliefs as a flat dict (`BeliefStore.beliefs`) with
some graph-like fields bolted on (`contradictions_with` edge list,
`evidence_refs` strings, a 100-record `changes` window). That supports
"what do you believe" and the two shipped temporal queries, but not:

- **"Why do you believe X"** - no typed support edges, so there is no
  inference chain to walk (`explain_belief` is blocked on this).
- **Belief trajectories** - confidence history exists per belief, but there
  is no first-class record of *why* each shift happened (absorbed report,
  sync delta, adjudication, decay).
- **Truncation honesty** - the 100-record change window already reports
  `window_truncated`; a real event log removes the limitation.

## Design

Evolve, do not rewrite. `BeliefStore` stays the API; the storage gains two
structures alongside the existing belief dict:

1. **Typed edges** - `Edge(src_id, dst_id, type, created_at, provenance)`
   with types `supports | contradicts | enables | derived_from`. The
   existing `contradictions_with` lists migrate to `contradicts` edges
   (bidirectional pairs, as `add_contested_belief` already writes them).
   New edges are written at absorb time: extraction already knows which
   evidence backs each claim; a claim absorbed from a report that cites an
   existing belief gets a `supports`/`derived_from` edge.

2. **Append-only event log** - `BeliefEvent(belief_id, kind, timestamp,
   reason, snapshot)` replacing the bounded `changes` list, persisted as
   JSONL next to the belief store (same pattern as the cost ledger: the
   ledger is canonical, views regenerate). `what_changed` becomes a query
   over this log and loses its truncation caveat.

Node types stay implicit (every node is a Belief; `source_type` already
distinguishes fact/signal/inference) until a concrete query needs more -
typed *edges* are the unlock, typed *nodes* are speculative.

## Components and order of operations

1. **Event log first.** Introduce the JSONL belief-event log; dual-write
   with the legacy `changes` list for one release; switch `what_changed`
   to read the log; drop the window caveat. (Smallest risk, immediate
   honesty win, no schema migration of beliefs themselves.)
2. **Edge store.** Add the edge list to the belief store file with a
   schema version bump; migrate `contradictions_with` on first load
   (idempotent, reversible - the legacy field is kept in sync for one
   release).
3. **Write paths.** absorb/sync/adjudication write `supports`/
   `derived_from` edges with report provenance; `add_contested_belief`
   switches to the edge store internally (API unchanged).
4. **`explain_belief`.** CLI `deepr expert why NAME BELIEF` + MCP
   `deepr_explain_belief`: walk `supports`/`derived_from` edges to
   evidence roots, attach the confidence trajectory from the event log,
   and list open `contradicts` edges. Depth-bounded, cycle-safe.
5. **Regenerated digest.** A compile pass over beliefs + edges + events
   emits the browsable digest (topic summaries, cross-references, open
   conflicts) as a derived view (Phase E regeneration invariant: the
   structured store is canonical, the digest is disposable).

## Invariants

- Event log is append-only; belief snapshots inside events are immutable.
- Every edge carries provenance (report id, sync id, or adjudication id).
- A migration must round-trip: legacy store -> graph store -> legacy view
  loses nothing.
- All reads stay cost-$0 (no LLM calls in the query surface).

## Open questions

- Edge dedup policy when the same support relationship is re-absorbed from
  multiple reports (current lean: one edge, provenance list grows).
- Whether decay events are materialized in the log (noisy) or computed at
  query time from `last_updated` + decay rate (current lean: computed).

## Exit criteria

`deepr expert why` answers with a real inference chain on a live expert;
`what_changed` has no truncation caveat; digest regenerates byte-stable
from the store; all migrations covered by round-trip tests.
