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

### Time: one axis, and two sparse fields that are not axes

```
recorded_at, superseded_at    # when the store learned it. THE ONLY AXIS.
valid_from, valid_to          # when it holds in the world. Sparse. A filter.
held: {from, to, basis}       # when the expert held it. Sparse. An overlay.
```

This went through three versions in a day. The third came from a research pass
that refuted the second with a better argument than the second had for itself:

> Snapshot semantics require a total axis; a partially populated axis can only
> support predicate semantics. [...] An axis you can retroactively rewrite is
> not an axis, it is content.

`recorded_at`/`superseded_at` is total - every record has it, and it is never
rewritten. `valid_*` is null on most research claims, which state no date.
`held_*` is worse than sparse: it is *retroactively* writable, because a viva
in October can establish that a position was abandoned in June. That is exactly
what an axis cannot be. Transaction time works as an axis precisely because it
is unrewritable, and SQL:2011 forbids assigning its columns for that reason.

So `as_of(t)` consults record time and nothing else, and the third-axis
question dissolves instead of being resolved.

The supporting evidence is one-sided. No shipped tri-temporal system was found.
SQL:2011 permits "at most one application-time period and at most one
system-time period per table" and lists multiple application-time periods under
future directions - seen in 2011, deferred, still unstandardised fifteen years
later. Storing a third period was always free; what nobody agreed is what a
three-way temporal join *means*. Every system that met "the thing happened
before we heard about it" answered with a boundary on the transaction axis -
MarkLogic's LSQT, streaming watermarks - never a new dimension.

**The expert's objection stands and is still honoured.** It was an argument
against *conflation*, not for an axis. `held` stays first-class, structurally
distinct, and never allowed to back a snapshot. Where a later record attests
that a view was abandoned earlier, `as_of` returns the store's state for that
moment *and* flags `contradicted_by_later_attestation`, which is strictly more
information than a held-time snapshot would have given. The cost is named: that
annotation is not deterministic across time, since a 2027 attestation changes
what is flagged for June 2026. Acceptable for an overlay, disqualifying for an
axis.

The original objection, which produced all of this:

> The proposed design treats `ingested_at` and `invalidated_at` as when the
> expert held a belief. The expert perspective only supports these as
> transaction or system-observation times. Those are not equivalent. An expert
> may form, revise, or abandon a belief before Deepr receives or processes the
> corresponding record.

The gap is not hypothetical. A viva moves a position *during* the examination
and the JSON lands afterwards, with a slow backend putting minutes between
them. What the objection rules out is *calling* transaction time belief time.
What it does not license is querying by belief time, because ~95% of records
would have nothing to answer with.

`held` is therefore populated only where a record names the moment, and left
null otherwise - never filled from `recorded_at`, because a fabricated belief
time is the same failure as a fabricated valid time.

**Point-in-time semantics are the actual work.** The same consult: "correctness
depends on point-in-time query semantics, not merely adding four timestamp
columns." Three decisions that had to be made before any column is written:

- **`as_of(t)` and `about(t)` are separate, keyword-only, and record time
  applies first.** `query(about=April, as_of=October)` selects the store state
  first and filters by valid time within it. Reversing that filters using facts
  the store did not yet have. Never positional: `salaryAt('2021-02-25',
  '2021-03-25')` is unreadable at the call site.
- **`about(t)` returns `{matching, undated}`, never a flat list.** Most records
  state no date. Including them silently asserts a claim they do not make;
  excluding them silently makes the query useless.
- **`current()` is the default read path**, with time travel opt-in. SQL:2011
  makes this the standard default and XTDB reports ~90% of usage is atemporal.
  If it is not the default, every caller hand-rolls the filter and some get it
  wrong.

Closed-open intervals, UTC. `recorded_at` is never mutated; a revision is a new
row that closes its predecessor's `superseded_at`.

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

Superseded records stay, with `superseded_at`, a `superseded_by` pointer, and a
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

0. **Wire `position_thread_id`.** It exists in `record_identity.py` and is
   called from nowhere - built this session and never connected, which is the
   same trap that left `cross_domain`, the profile card and `corpus_search`
   unreachable. Without it there is no `history_of` and no `as_of` for
   positions at all, so nothing else on this list can start.
1. **Content-derived, stable `finding_id`.** Done. Append-only
   `study/findings.jsonl` plus a derived `study/current.json` still to do.
2. **`position_id`, and `supported_by` verified against it.** Add `recorded_at`
   and `superseded_at` to both records, plus `held_from` where the record names
   the moment it changed. `evidence_graph` then reads `first_seen`
   from the record instead of the run, which is the bug it currently documents
   against itself.
3. **Sparse valid time.** Populated only where a source states a date.
4. **The reconciliation stage**, between study and brief. Lenses stay
   corpus-blind. Reconciliation takes prior positions plus fresh findings and
   emits, per prior position: unchanged, strengthened, weakened, superseded, or
   retired, each with a reason. This is where accumulation actually happens.
5. **Two primitives, not five.** `history_of(thread_id)` first - it needs no
   semantic decisions and is what humans actually ask. Then `as_of(t)`, with
   `current()` as the zero-argument default read path. `what_changed` already
   ships with CLI and MCP surfaces; reimplement it over `as_of` rather than
   adding a primitive. `why_superseded` is not a query, it is two fields, and
   `supersession_reason` should be required whenever a record is superseded -
   an unreasoned supersession is the commonest way these stores rot. Defer
   `about(t)` until there are enough dated records to write a test that fails
   informatively.
6. **A nogood ledger.** Every adjudicated contradiction persisted so it is never
   re-litigated. The cheapest good idea in the truth-maintenance tradition.

## What actually bites, at 1,975 records

At this scale the query is free: ~2 ms for the interval comparisons, ~20 ms to
deserialise the JSON. **Deserialisation is 100% of the cost, so no index of any
kind is justified** - break-even for an interval tree is 10^4 to 10^5 records
and this store is 2 x 10^3. Explicitly over-engineering here: temporal
indexes, time bucketing, separate current/history files, materialised
snapshots, compaction, and a stability watermark. LSQT exists because
uncoordinated clients write with their own clocks; there is one writer per
expert directory, so that whole problem class is absent.

What does bite, in order:

**1. A store that cannot replay itself.** `Belief.get_current_confidence`
decays against `datetime.now(UTC)`, so `as_of(June)` would return a June record
carrying *today's* decayed confidence. This must be settled before `as_of`
ships: either it returns stored confidence and never computes, or decay takes
an explicit `at`. Shipping the query first would bake a silent wrongness into
every historical answer.

**2. Timestamps that lie by one microsecond.** `_record_change` guarantees
monotonic ordering by bumping the timestamp, so the stored `recorded_at` is not
the time the thing happened. Keep the true timestamp and add a per-store
monotonic `seq`; order is `(recorded_at, seq)`. One field, and timestamps stop
being fiction.

**3. Whole-file overwrites are the actual history bug.** `study.json` and
`brief.json` are written with a bare whole-file write on every checkpoint. That
is what makes history unrecoverable - a correctness problem, not a performance
one. The belief store already does this correctly with an append-only
`events.jsonl`, atomic writes, fsync and a lock. Copy that pattern for
`findings.jsonl` and `positions.jsonl` with a derived `current.json`.

**4. One time module, one interval predicate.** There are 64 duplicated
`_utc_now()` definitions and at least four separate hand-rolled naive-to-UTC
coercions. Sentinels, parser and `contains(start, end, t)` must live in exactly
one place or closed-open gets implemented three ways. `_context_matches_
temporal_filters` currently uses closed intervals *and* excludes records with
missing endpoints - a silent under-return, and the exact bug NULL-instead-of-
sentinel produces.

**Closed-open everywhere, and a sentinel on the total axis only.**
`END_OF_TIME = "9999-12-31T23:59:59.999999+00:00"` matches SQL:2011's own
worked example, SQL Server and MarkLogic, so export is a no-op, and it is
`datetime.max` with UTC attached so it round-trips through `fromisoformat`
losslessly and sorts correctly as a string. Closed-open is not aesthetic: it is
the only convention where consecutive versions tile the line with no gap and no
overlap, so `predecessor.superseded_at == successor.recorded_at` exactly.

But `valid_*` and `held` keep NULL, because there the distinction between
"unknown" and "unbounded" is load-bearing - a claim true from March and still
true is not the same record as one that states no date at all.

**One naming hazard.** `_as_of()` already exists in `digest.py` and `okf.py` as
a *label* meaning "max event timestamp", not a query. Rename it before
introducing a real `as_of`.

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
