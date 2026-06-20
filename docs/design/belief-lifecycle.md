# Design: Belief Lifecycle and Salience (memory governance)

Target: substrate in v2.14.x (while the event schema is young), the rest
lands with v2.15 (the evidence release). Roadmap: Phase 4 "Belief
lifecycle and salience".
Status: design + first increments shipped 2026-06-12.

## Problem

The temporal knowledge graph (v2.14) gave experts an inspectable,
append-only epistemic record: beliefs with trust-capped confidence, typed
edges, an event log, and $0 temporal queries. What it did not give them is
a *lifecycle*. Today:

- **Growth is monotonic.** Nothing leaves the active store except manual
  `archive_belief` calls that nobody issues. Decay lowers confidence, but
  a decayed belief still occupies prompt space, digest space, and
  retrieval candidacy forever.
- **Archival is lossy.** The archived event records only the claim text
  and confidence; the belief object (evidence refs, trust class, history)
  is deleted. "Reversible" is aspirational, not executable.
- **No salience signal.** A belief the expert actually leans on in
  answers and a belief absorbed once and never touched are
  indistinguishable. Decay treats them identically.
- **Record time and world time are conflated.** The event log knows when
  the *store* learned or retired a belief, but not when the underlying
  fact stopped being true. "What did we believe on date X" and "what was
  true on date X" are different questions; only the first is answerable.

The memory-systems literature (below) identifies exactly these gaps as
the root failure modes of agent memory, and deepr currently shares them
with 17 of the 20 systems surveyed in the kilo-agent-memory corpus.

## Literature grounding (distillr corpora, reviewed 2026-06-12)

Nine corpora from the operator's distillr library: `deepr-tkg` and
`deepr-calibration` (already grounding the TKG and calibration designs),
plus `kilo-tkg` (~40 papers), `kilo-agent-memory` (~20), 
`kilo-episodic-memory` (~15), `kilo-memory` (~20), `agentic-memory`,
`memory` (mixed-source), and `claim-verification` (~8). Findings mapped
to deepr, strongest first:

1. **Monotonic accumulation is the documented root failure mode**
   (When to Forget arXiv 2604.12007; GEM 2605.26252; importance-modulated
   decay 2601.18642; compression-spectrum survey 2604.15877). Seventeen of
   twenty systems in the kilo-agent-memory corpus use append-only or
   CRUD-style storage with no state governance, and inherit four named
   failure modes: redundancy, coexisting outdated facts, age-only
   eviction, and retrieval that never modifies memory state. The corpus
   consensus is that selective forgetting and consolidation are
   load-bearing, not hygiene.
2. **Outcome- and usage-driven forgetting converges to true usefulness**
   (When to Forget): two deterministic hit counters per memory, updated
   from retrieval sets and outcomes, provably converge to the conditional
   probability that the memory helps. No LLM, no embeddings - exactly
   deepr's $0 discipline. Caveat the paper itself records: the signal is
   association, not causation, and "hitchhiker" memories (retrieved
   alongside useful ones) need independent retrievals to wash out.
3. **Hierarchical decoupling of transient vs stable memory is the
   repeated empirical winner** (GAM 2604.12285; "Memory in the LLM Era"
   2604.01707; dual-process agents 2605.17625). Deepr's session ->
   verification-gated absorb -> belief store pipeline already is this
   shape. Validated; no action beyond keeping the absorb gate strict.
4. **Construction cost dominates lifecycle cost** (systems
   characterization 2606.06448: LLM-mediated construction phases dominate
   energy and tokens; retrieval is comparatively free). This validates
   the $0-read-side rule and makes Phase 6 (route construction-side work
   to plan-quota/local capacity) the right cost lever for always-on
   experts. It also says: when buying quality, spend on absorb/extraction,
   not on query surfaces.
5. **Conflicting perspectives are irreducible** (Rashomon Memory, via
   kilo-memory): forcing a single coherent encoding loses the signal.
   Deepr's contested-as-first-class design is this position; contested
   beliefs must therefore be exempt from any garbage collection.
6. **Memory benchmarks measure at most 2 of 7 continuity properties**
   (ATANT 2604.10981 audit of LoCoMo, LongMemEval, etc.). Chasing those
   scores would be measurement theater - the same trap the saturated-eval
   incident proved live on 2026-06-11. Instead, eval methodology v2
   should measure deepr's own continuity properties from stored state at
   $0: staleness honesty, abstention correctness, contradiction
   surfacing, what-changed exactness.
7. **Memory is an attack surface** (ADAM 2604.09747: adaptive extraction
   attacks reach up to 100% success; Poison Once 2604.02623; Opal
   2604.02522). The trust floors are the poisoning backstop; they now
   need adversarial verification. Extraction probing via MCP read tools
   and floor-bypass attempts belong in the Phase 5 red-team suite.
8. **Entailment beats lexical overlap for grounding and contradiction**
   (claim-verification corpus: ROUGE/lexical metrics show near-zero
   correlation with human support judgments; NLI-style checks are
   uniformly superior). Deepr's contradiction heuristic is lexical
   (word-similarity + negation), and its known phrasing-level false
   flags are exactly this failure. The planned same-meaning screen must
   be entailment-shaped, run on the uncertain band only (the selective
   recalibration pattern already adopted in the calibration design).
9. **Claim decomposition raises retrieval/verification accuracy by 20+
   points** (2205.06938, 2506.04583, 2310.03951): atomic,
   decontextualized claims verify and retrieve far better than compound
   ones. Absorb's extraction prompt should enforce atomicity; the
   calibration harness should measure it.
10. **Lightweight verifiers close most of the gap to flagship judges at
    10-20x lower cost** (2410.03461, 2604.06277). Keeps the validator and
    future calibrator on the cheap-model allowlist by evidence, not just
    thrift; Phase 6 eval-gated local admission extends the same logic to
    $0 models.
11. **Bi-temporal semantics** (Graphiti 2501.13956, already adopted in
    the TKG design): separate record time from world-valid time. The
    event schema is young - add it now or migrate forever.
12. **Streaming updates are the literature's white space** (kilo-tkg:
    no paper evaluates repeated incremental updates; kilo-agent-memory:
    nothing tested past ~35 sessions). Deepr's append-only event stream
    operates exactly there. Keep the read side $0, and add simple query
    timing to observability once stores grow past a few thousand
    beliefs - deepr can have the number the literature lacks.

## Design

### 1. Bi-temporal valid time (ship now)

`BeliefChange` gains an optional `invalidated_at` (world time: when the
fact stopped being true), distinct from `timestamp` (record time: when
the store learned it). Archive and revise operations accept it.
Additive JSONL - old events parse unchanged. This unlocks, later and for
$0, the two distinct queries: "what did we believe on X" (record-time
scan, already possible) and "what was true on X" (world-time filter).

### 2. Lossless archival (ship now)

Archival events carry a full belief snapshot (`snapshot` field: the
belief's `to_dict()`); `BeliefStore.restore_belief(belief_id)` rebuilds
the belief from the latest archived snapshot in the event log. The
regeneration invariant extended to deletion: reversibility is executable,
not aspirational. Edges touching archived beliefs are kept (the contested
view already renders dangling edges honestly).

### 3. Usage salience substrate (ship now; protective-only)

`Belief` gains `retrieval_count` and `last_retrieved_at`;
`BeliefStore.record_retrieval(ids, context)` bumps them (state, not
events - retrieval tallies would bloat an append-only log).

The hard constraint is deepr's own read-side discipline: validate, why,
digest, contested, and what-changed are documented as pure, $0,
state-free - and the MCP READ_ONLY mode depends on that. So usage may be
recorded only by surfaces that already mutate the expert. Today that
means the substrate ships without a production producer: absorb-merge
re-confirmation already protects through `updated_at` movement (no
counter needed - conflating re-confirmation with answer-time usage
would muddy the semantics), chat knowledge assembly records usage when
the worldview-to-BeliefStore bridge lands, and the hosted endpoint's
tool-call audit log can batch read-side usage server-side in v2.17.

Consequence, and the safety property: **usage only ever protects a
belief from archival; absence of usage never condemns one.** Many
experts are consumed exclusively through read-only surfaces and will
have no usage signal - that must not make their beliefs garbage.

### 4. Consolidation pass (ship now)

`expert health-check` gains an archive-candidates finding and an
`--archive-stale` action flag (the same propose-then-execute pattern as
the absorb-time contradiction flags). A belief is a candidate only if
ALL of:

- current (decayed, trust-capped) confidence below a floor (default 0.2)
- not updated or re-evidenced in N days (default 90)
- no recorded retrieval in N days (protective check)
- not a side of any open contradiction (contested beliefs are signal,
  never garbage - the Rashomon rule)

Dry-run by default; `-y` applies; every archival is event-logged with
snapshot, reason, and the thresholds used. $0, no LLM.

### 5. Entailment-shaped contradiction screen (v2.15)

The known phrasing-level false flags in absorb-time contradiction
detection get one cheap entailment-shaped call per flagged pair, in the
uncertain band only - merged with the selective-recalibration mechanism
from the calibration design (one budget, one injection point, injectable
research_fn for $0 tests). Lexical heuristics stay as the free first
pass; entailment is the screen, per finding 8. The deterministic-vs-agentic
boundary this rests on (lexical as a high-recall router, never a verdict;
decomposition and entailment are model-based) is set out, with cited
June-2026 grounding, in
[checks-deterministic-vs-agentic.md](checks-deterministic-vs-agentic.md).

### 6. Atomic claim decomposition at absorb (v2.15)

Extraction prompt enforces atomic, decontextualized claims (one
assertion per claim, no dangling pronouns); a deterministic compound
check (conjunction/clause heuristics) reports an atomicity rate. No
extra paid pass by default - the calibration harness measures whether
prompt-level enforcement suffices before any money is spent on a split
pass.

### 7. Continuity-property metrics (v2.15, eval methodology v2)

Per finding 6, expert-quality metrics measured from stored state at $0:
staleness honesty (are stale beliefs reported stale), abstention
correctness (insufficient-grounding bucket vs gold), contradiction
surfacing (recorded contested pairs vs planted ones), what-changed
exactness (event-log replay vs known mutations). These join the
calibration harness as the v2 metric set - measured on deepr's own
surface, not a borrowed benchmark.

### 8. Memory red-team additions (Phase 5)

First local probes now ship through `deepr eval red-team`: high-confidence
single-report, ungrounded, duplicate-source, and two-tertiary-source cases are
measured as memory trust-floor bypass attempts at `$0`. ADAM-style adaptive
extraction probing through the MCP read tools remains planned, with attack
success rate tracked per release.

## Order of operations

1. [x] Substrate (this increment, $0): bi-temporal `invalidated_at`,
   snapshot archival + `restore_belief`, salience fields +
   `record_retrieval`, absorb-merge usage recording, health-check
   archive candidates + `--archive-stale`.
2. Entailment screen, designed and budgeted with selective recalibration
   (one mechanism, two consumers).
3. Atomicity enforcement in the extraction prompt + atomicity rate in
   the calibration harness.
4. [x] Continuity metrics (2026-06-13): `src/deepr/experts/continuity_metrics.py`
   + `deepr eval continuity NAME` - the four properties of finding 6 scored
   from stored state at $0, each against ground truth derived independently
   of the surface it scores, methodology-versioned for run comparability.
5. Red-team additions land with the Phase 5 suite.

## Invariants

- Read-side queries stay $0 and state-free; usage recording happens only
  on already-mutating paths.
- Contested beliefs are never auto-archived.
- Archival is reversible from the event log alone (snapshot carried in
  the event).
- Usage signals protect; they never condemn.
- Nothing is ever deleted; the event log stays append-only.

## Open questions

- Outcome attribution (the second When-to-Forget counter - did the
  answer that used this belief succeed?) needs an outcome signal deepr
  does not capture yet; revisit when reflection verdicts or host-agent
  feedback can stand in for task success.
- Whether digest should de-emphasize (not hide) never-used decayed
  beliefs once salience data exists - lean yes, as a rendering choice,
  never a store mutation.

## Exit criteria

Archive-candidates appear in health-check on a live expert with the
gates above; `--archive-stale` archives with snapshots and
`restore_belief` round-trips one; an event written before this change
still parses; usage recording demonstrably never fires from validate,
why, digest, contested, or what-changed (regression-tested).
