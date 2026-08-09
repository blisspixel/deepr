# Expert V2: identity and a clock, not a new subsystem

Status: proposed, 2026-08-09. Completes prerequisites #2 and #4 of
[expert-v2-architecture.md](expert-v2-architecture.md), which are the two of
seven that were never built.

## The finding that reframes the work

Two research passes and two code audits ran independently on the question "how
should the TKG work". All four converged on the same answer, and it is not the
one the question implies.

**The problem is not a missing graph. It is missing identity and a missing
clock.** Every layer above the corpus is a pure function of the most recent
run, so a second study *replaces* the first instead of being a delta against
it. That is the entire mechanism by which a six-month expert has read more
without having learned more.

Three lines of code carry most of it:

```python
finding_id = f"{lens.key}-{start_index + len(findings)}"   # study.py:299
position_id = f"position-{index}"                          # evidence_graph.py:306
```

Both positional. Insert one finding and every id after it renumbers. `Position`
has no id field at all; the graph invents one at build time. `build_brief()`
takes a `StudyResult` and a `CorpusStore` and **no prior brief**, so every
`expert brief` run discards ten positions, their likelihood bands, their
falsifiers and their recorded dissent, and re-derives them from scratch.

`ExpertBrief` carries no timestamp of any kind. Neither does `VivaResult`. So
"what did this expert believe in June" is unanswerable not because the query is
missing but because the data was never recorded.

## What is already right, and must not be lost

Stated plainly because it cuts against building more:

- **The corpus accumulates correctly.** Content-addressed, deduped by sha256,
  never deletes. This layer already compounds.
- **Anchoring is machine-verified.** `_anchor_matches` checks that a quoted
  phrase actually appears in retained text. Measured elsewhere: LLMs asked for
  citations produced 0% relevant identifiers unprompted and 15.3% at best. Every
  graph-RAG system surveyed is weaker here - GraphRAG's own report prompt caps
  citations at five with `+more` and validates none of them.
- **Lenses are corpus-blind.** `study.py` already refuses to let a pass reason
  over the expert's own prior conclusions: "an echo chamber with extra steps".
  This invariant is the best anti-entrenchment mechanism in the system and
  survives V2 unchanged.

Those are the two hardest parts and they are done. What is missing is a schema
change and a delta pass.

## The design

### Identity: two keys, not one

A revisable record needs both a **thread id** (this question, across versions)
and a **version id** (this particular statement of it). One key cannot do both:
`ExpertStance.create` hashes `title|statement`, so a revised stance silently
becomes an unrelated record.

- **Finding thread id**: hash of `lens`, normalized title, and the sorted anchor
  set. Stable across runs because it is derived from content rather than from
  position in a list.
- **Position thread id**: hash of the normalized question. A position is *about*
  a question; revising it must not change what it is about.
- **Version id**: hash of the full record. Changes on every revision.

Findings get a signal nothing else has: **the anchor set**. Two findings citing
overlapping corpus spans are far more likely to be the same finding than two
similar sentences, and the check is deterministic and free.

### Time: four fields, on assertions only

```
valid_from, valid_to          # when it is true of the world. Usually unknown.
ingested_at, invalidated_at   # when this expert held it. Never null on ingest.
```

Closed-open intervals, UTC. `ingested_at` is never mutated; a revision is a new
row that closes its predecessor's `invalidated_at`.

Three decisions worth stating because the obvious choice is wrong in each:

**Time goes on the assertion, never on the entity.** The one production system
with genuine bitemporality puts it on edges and still leaves mutable state on
nodes - and has an open data-loss bug where a node attribute is destructively
overwritten and the old value is unrecoverable. Nodes stay derived.

**`valid_from` stays null unless the source states a date.** The same system
runs an LLM call per edge to extract timestamps and produces eight edges in one
ingest sharing an identical timestamp to the second, because it silently
defaults to the ingesting episode's time. A fabricated valid-time is worse than
a null one, because the invalidation rule then fires on it. "No valid time" is a
first-class state that suppresses temporal invalidation.

**Open-ended intervals use a sentinel, not NULL.** One implementation uses null
and pays for it in `IS NULL` branches everywhere; another picked `2038-01-19`
and shipped a live Y2038 bug where "open" sorts before genuinely future dates.

### Revision: stamp, never delete

Superseded records stay, with `invalidated_at`, a `superseded_by` pointer, and a
reason from a closed set: `retracted_by_source`, `superseded_by_newer`,
`source_discredited`, `operator_retired`, `merge_loser`.

Retired records leave the *default read set* and remain reachable by `as_of`
query. Growth is not the problem; an unbounded **active** set is. Compaction is
a separate, logged, reversible operation and the only thing permitted to delete.

**Bitemporal soft retraction strictly dominates AGM contraction here.** AGM
throws beliefs away; this keeps them and stays able to answer what was believed
in June. Take belief *bases* (finite, not closed under consequence - the store
already is one) and epistemic entrenchment as a concrete priority order, which
already exists as trust class, independent origin count, corroboration, recency.
Skip partial-meet contraction, skip Recovery, skip the postulates.

### Contradiction: the model proposes, deterministic logic decides

The single best design choice available, and the cheapest to get wrong.

An LLM answers only "do these conflict?". Timestamp and subject logic decides
what happens. Roughly forty lines, unit-testable, and it is the difference
between a working system and the documented failure case: a production graph
where **1,616 of 3,950 facts (41%) carry an invalidation**, and a hand audit of
four found three were collateral damage - "person administers company's source
control org" retiring "person holds job title at company".

The guard that would have prevented it is free and structural: **two findings
can only contradict if they are about the same question.** Requiring a shared
subject before permitting retirement needs no model call.

The judge is also fragile exactly where it matters. Measured on a small model,
contradiction detection scored 7/15 and got 1/3 on clear two-fact
contradictions; adding a `reasoning` field before the output arrays raised it to
14/15. Duplicate detection was unaffected. The invalidation half is the half
that degrades, and cost pressure pushes everyone onto the model that breaks it.

### Retraction: derivation counting, not a TMS

`position --rests_on--> finding --anchored_in--> source` is already a JTMS
dependency graph. Store a support count per position; retraction decrements; at
zero the position is marked **unsupported**, not false.

Skip ATMS (2^n environments, NP-complete label updating), skip DRed and
backward rederivation - measured as "a considerable source of overhead even on
very small updates" - and skip differential dataflow, which costs 2-3x memory
minimum.

The scale argument is decisive and comes from this repo, not a benchmark: **the
largest expert has 105 findings over 30 sources; the fleet holds 1,975
beliefs.** At 10^3-10^4 items every graph operation is sub-millisecond. The
entire cost is LLM adjudication, so optimise candidate fan-out - anchor-overlap
blocking, then MinHash, then embeddings as a recall filter, then the model only
on the residue, framed as *select from a list* rather than pairwise match.

### What V2 deliberately does not build

- **No communities.** Leiden is provably non-reproducible on sparse graphs of
  the kind LLM extraction produces: two runs on identical input give different
  hierarchies. `source_card.py` is a bounded, incremental, reproducible unit for
  the same job.
- **No multi-agent debate.** It decreases accuracy over rounds even when
  stronger models outnumber weaker ones, and amplifies position and bandwagon
  bias. What works instead is information asymmetry between critics - which
  `expert viva` already does by giving each examiner a different standpoint.
- **No entity resolution as a spine.** Every system surveyed bleeds here; the
  most cited one does no entity resolution at all and merges on an uppercased
  title string, first wins, rest silently dropped. Our spine is finding and
  position. If two concept nodes fragment, recall dips slightly. If two
  positions fragment, the expert holds a duplicated stance.
- **No parametric editing.** Sequential model edits show gradual then
  catastrophic forgetting. With an external claim store, edit the store.

## Order of work

Each step is independently useful and none requires the next.

1. **Content-derived, stable `finding_id`.** Blocks everything else. Append-only
   `study/findings.jsonl` plus a derived `study/current.json`.
2. **`position_id`, and `supported_by` verified against it.** Add `ingested_at`
   and `invalidated_at` to both records. `evidence_graph` then reads `first_seen`
   from the record instead of the run, which is the bug it currently documents
   against itself.
3. **Sparse valid time.** Populated only where a source states a date.
4. **The reconciliation stage**, between study and brief. Lenses stay
   corpus-blind. Reconciliation takes prior positions plus fresh findings and
   emits, per prior position: unchanged, strengthened, weakened, superseded, or
   retired, each with a reason. This is where accumulation actually happens.
5. **`as_of(t)`, `about(t)`, and the support sweep.** All deterministic, all $0.
6. **A nogood ledger.** Every adjudicated contradiction persisted so it is never
   re-litigated. The cheapest good idea in the truth-maintenance tradition.

## Two live bugs this work must fix on the way past

**A stance can never be revised.** `metacognition.py:468` keys stances by title
and returns the existing one on collision, silently. The first stance an expert
takes on a topic is permanent.

**The revision machinery has never run.** `BeliefChange` already implements the
record-time/world-time split and `to_expression()` literally emits "I used to
think X, but now I believe Y because Z". Measured across the fleet: 1,975
beliefs, 2,008 events, **1.02 events per belief.** Every belief was written once
and never revised.

## The honest expectation

The one system built entirely around belief revision gained **+6.5%** on the
benchmark category that actually tests it - its smallest improvement of any
category, against +184% on preference retrieval, while one category regressed
17.7%. Its real result was latency and context, not accuracy.

So the expectation here is that six months of accumulation shows up as better
calibration, better abstention and better contradiction resolution long before
it shows up as better factual correctness. The existing eval pilot already found
exactly that shape: the only nonzero delta across four arms was
`uncertainty_calibration`.

Keep a null baseline. If a six-month expert does not beat "the most recently
ingested finding wins", the temporal machinery is not earning its keep.

## Related

- [expert-v2-architecture.md](expert-v2-architecture.md) - the seven prerequisites
- [what-an-expert-is.md](what-an-expert-is.md) - why a standpoint is the product
- [skills-as-learning-systems.md](skills-as-learning-systems.md) - what would make elapsed time matter
