# The expert insight layer (corpus to perspective, not corpus to facts)

Status: design, 2026-08-05.
Parent: [exceptional-expert-quality.md](exceptional-expert-quality.md).
Siblings: [living-expert-research-stack.md](living-expert-research-stack.md),
[diverse-expert-council.md](diverse-expert-council.md).
Plan: [../plans/living-expert-research-stack.md](../plans/living-expert-research-stack.md).

## Operator ask (compressed)

An expert is a Distill-style process that gets the latest on a topic from many
independent sources, then a Learny-style pass that reasons across all of that
content and comes back with **insights**. Think about the material several
ways in order to understand it better. The product is grounded perspective and
currency, not a fact dump, and not raw content.

## The finding that reorders the plan

Deepr has an acquisition story and a storage story. It has **no insight
generation step at all**, and the one ingestion path it has actively destroys
the structure insight lives in.

`expert absorb` is a fact shredder by construction. Its extraction prompt asks
for "atomic, verifiable factual claims" and instructs that a sentence joining
two facts be split (`src/deepr/experts/report_absorber.py:930-955`). Its only
output constructor is `Belief(...)` (`report_absorber.py:522-537`). So every
document that enters an expert through absorb, including every Distill corpus
and every Learny export, is flattened to single-sentence claims each carrying a
confidence number.

That is why a consult reads as a confidence ledger. Not because the store lacks
depth, but because the only shape the ingestion path can write is a fact.

Three separate findings confirm this is the binding constraint:

1. **The typed perspective state already exists and is inert.** `ExpertStance`,
   `ExpertConcept`, `ExpertHypothesis`, `ExplorationAgenda`, and
   `ExpertOriginalIdea` are defined in `src/deepr/core/contracts.py:202-606`,
   with a model-owned `claim_kind` taxonomy in
   `src/deepr/experts/claim_extraction.py:266-272`, per-kind write policies in
   `src/deepr/experts/source_pack_policies.py:9-111`, verifier gates in
   `src/deepr/experts/source_pack_compiler.py:388-430`, and commit operations in
   `src/deepr/experts/graph_commit_apply.py:37-86`. The readers
   (`get_stances`, `get_concepts`, `get_hypotheses`, `get_exploration_agendas`
   at `src/deepr/experts/metacognition.py:592-608`) have **zero production
   callers**. `digest.py` never imports the tracker at all. Across the live
   fleet, **zero of 39 experts** have any of these populated.
2. **They can only be written by `expert sync` / `apply-graph-commit`,** never
   by absorb. So the corpora that would fill them cannot reach them.
3. **The retrieval path then re-biases toward stance.** Consult packet
   selection sorts by query overlap then effective confidence
   (`src/deepr/experts/council.py:268-271`), while trust ceilings cap tertiary
   domain claims at 0.60 single-source and 0.80 corroborated
   (`src/deepr/experts/beliefs.py:118-137`) and leave operator-attested stance
   uncapped at 1.00. Absorbed project intent therefore **structurally outranks
   corroborated domain evidence** for the eight available packet slots. Even a
   well-deepened expert can produce a stance-dominated packet.

The echo chamber is not only a corpus problem. It is a corpus problem, an
ingestion-shape problem, and a retrieval-ordering problem, stacked.

## What an expert actually is on disk today

Measured against the live NephMesh expert, 2026-08-05:

| Path | Contents |
|---|---|
| `beliefs/beliefs.json` | 92 beliefs, 20 edges, change log |
| `beliefs/events.jsonl`, `mutation_audit.jsonl` | Append-only history |
| `blueprints/blueprints.jsonl` | Operator-attested purpose |
| `profile.json` | Identity, budget, activity |
| `documents/` | **empty** |
| `knowledge/` | **empty** |
| `conversations/` | **empty** |

A belief carries: `claim`, `confidence`, `decay_rate`, `trust_class`,
`evidence_refs`, `grounding_assurance`, `domain`, `contradictions_with`,
`history`. All 20 edges are `supports`. So the temporal knowledge graph exists
structurally and is, in practice, a thin same-polarity similarity graph with no
temporal qualifiers in use.

**The expert retains no corpus.** `absorb --file` reads a document, extracts
atomic claims, records the token `report:file:<basename>`, and the source text
is not kept. `documents/` and `knowledge/` are empty on a 92-claim expert. The
`evidence_refs` list mixes compact origin tokens with raw prose excerpts, so the
only trace of a source is a filename and a few quoted lines.

Three capabilities follow directly from that, and Deepr has none of them:

1. **It cannot re-read its own sources.** So it cannot re-analyze the same
   material through a different lens, which is precisely the "think about it in
   multiple ways" move.
2. **It cannot show you a passage.** Provenance resolves to a filename, not to
   the text that justified the claim.
3. **It cannot re-derive when the frame changes.** When understanding of a
   domain shifts, the only recourse is to re-acquire and re-absorb from scratch,
   because the evidence was consumed rather than kept.

Corpus ownership is therefore not a storage nicety. It is the precondition for
insight being *revisable* rather than one-shot, and for the temporal graph to
record how understanding of the same material changed over time rather than only
that new claims arrived.

## The target: an excellent student's notebook

The useful mental model is a strong student working through a field, not a
database accumulating rows. A good student's notebook has layers, and the
valuable layers are the derived ones:

| Layer | Student analogue | Deepr today |
|---|---|---|
| Sources kept and re-readable | The papers and docs, annotated | **Absent** - consumed and discarded |
| Notes per source | What this one says, in their own words | Absent - shredded to atomic claims |
| Cross-source analysis | "These three disagree about X, and here is why" | Absent |
| Summary | The distilled understanding worth re-reading | `digest` is a confidence-sorted bullet list |
| Stance | What they now think, and on what grounds | Type exists, zero populated |
| Open questions | What they still do not understand | `Gap` exists and is used |
| Revision history | What they used to think and why they changed | Belief events exist; typed state has none |

Facts and confidence are the bottom of that stack, and Deepr currently has only
the bottom. The operator's "second brain" framing and the notebook framing are
the same request: the product is the derived layers, kept current, with the
sources still there to check.

Note the two directions this runs, and that they are different:

- **Learn** - the corpus produces claims, stance, fail patterns, and edges that
  change what the expert believes.
- **Accumulate** - the corpus itself is retained and grows, so later passes can
  reason over more material, and any earlier conclusion can be traced back to
  text and re-examined.

Deepr does the first, weakly, and does not do the second at all.

## What the layer is

Four stages, of which Deepr today has the first and a broken third.

| Stage | Owner | State today |
|---|---|---|
| **Acquire** - find and fetch multi-origin current sources | Distill (`--cost-mode no-metered`, $0 API) | Works; not wired to Deepr at scale (no batch absorb) |
| **Retain** - the expert keeps the corpus it learned from | Deepr | **Missing.** `documents/` and `knowledge/` are empty on every expert; absorb discards source text |
| **Ingest** - claims and provenance from the corpus | Deepr `absorb-dir` (Step 4.1) | Not built; and absorb only emits facts |
| **Reason** - read across the whole corpus through several lenses and produce insight | **Missing** | This document |
| **Hold** - store insight as typed, sourced, revisable perspective | Deepr typed state | Defined, inert, write-once, provenance dropped |
| **Render** - notes a human would study | Deepr `digest` | Confidence-sorted bullet partitions |

The Learny-shaped move is stage three: a bounded pass that reads the corpus as
a body rather than as N independent documents, and returns the things a
sentence-level extractor structurally cannot produce.

### What a reasoning pass returns that extraction cannot

Extraction answers "what does this sentence assert?" A corpus-level pass
answers questions that only exist across documents:

| Output | Why extraction cannot produce it |
|---|---|
| **Fail patterns** - trigger, symptom, mechanism, correction, detection | A conditional structure. Split into atomic claims it becomes four unrelated 0.6-confidence bullets. |
| **Stance** - position, tradeoffs, decision criteria, what the expert would reject | A judgment over competing sources, not an assertion in any one of them. |
| **Tensions** - where independent good sources disagree, and on what | Requires holding two documents at once. |
| **Consensus vs frontier** - what is settled, what is actively contested | Requires the distribution across origins, not any single origin. |
| **What changed** - and what that invalidates | Requires the time axis across releases and revisions. |
| **Open questions** - what the corpus does not answer | Requires knowing the shape of the whole, i.e. absence. |
| **Elite bar** - what good looks like here | A synthesis of stance, fail patterns, and operator-attested acceptance cases. |

"Think about it in multiple ways" is not a prompt flourish. It is the mechanism.
A single synthesis pass over a corpus produces the same generic best-practice
mush the live NephMesh validation surfaced. Several passes with **distinct
lenses** produce material that disagrees with itself, and the disagreements are
the insight. This is the same argument that `diverse-expert-council.md` already
makes about council composition, applied one level down: diversity of lens is
what prevents restating the narrative.

### Candidate lenses over a corpus

These are the analogue of the council axes, aimed at material rather than at a
project. A pass runs each lens independently and never forces agreement.

| Lens | Asks |
|---|---|
| Mechanism | How does this actually work, beneath the vocabulary? |
| Failure | What breaks, under what conditions, and how is it detected? |
| Contention | Where do independent sources disagree, and what would settle it? |
| Change | What is different from the prior understanding, and what does that invalidate? |
| Practice | What survives production, and what is documentation-only? |
| Absence | What would a practitioner expect to find here that is not here? |

## Boundaries this must not cross

The STOP contract (`ROADMAP.md:5-31`) and `AGENTIC_BALANCE.md` apply with full
force, and an insight layer is exactly the kind of feature that erodes them.

1. **Insight is model-owned; admission is deterministic.** No lexical scoring
   of whether something is an insight, a fail pattern, or a stance. Code checks
   that a record has a trigger, a correction, source refs, and an uncertainty
   statement. Code never checks that it is *good*.
2. **Every insight traces to source windows in the corpus.** A pass that reads
   the belief store and writes conclusions back is the echo chamber with extra
   steps. Insight is derived from evidence, never from the expert's own prior
   output.
3. **Absorb stays the only write boundary.** Distill and Learny artifacts are
   evidence packs. A reasoning pass proposes; the existing verifier and commit
   gates admit.
4. **Insight is labeled, not promoted to fact.** A stance carries rationale and
   uncertainty. A fail pattern carries scope and disconfirming signals. Neither
   renders as a verified claim, and neither inherits belief confidence
   arithmetic.
5. **Insight must be revisable.** Today `promote_stance_candidate` silently
   refuses a duplicate title (`metacognition.py:468-470`) and there is no
   revise or retire operation. Writing insight onto a write-once substrate makes
   the first wrong reading permanent. This is a prerequisite, not a follow-up.
6. **No new capacity claims.** The reasoning pass runs on local Ollama or proven
   plan quota. It is more model calls than absorb, which is a time cost at $0,
   not a money cost.

## Prerequisites, in dependency order

Each is a finding from the research pass, not a guess.

0. **Corpus retention. Decided 2026-08-05: retain, content-addressed.** The
   expert copies absorbed source text to `corpus/sources/<sha256>.md` under the
   existing `validate_path` containment, with a `corpus/index.jsonl` carrying
   origin key, url, publisher, fetched_at, hash, and trust class. Deduped across
   the fleet by hash. Accepted cost: tens of MB per expert. Pointers into an
   operator-owned Distill library were rejected because they break on move,
   prune, or rename and leave the expert unable to re-read itself, which makes
   "think about it in multiple ways" a single shot.
1. **`absorb-dir` with publisher-collapsed origin identity.** Without batch
   ingestion there is no corpus to reason over. With naive per-file provenance,
   a 40-page crawl of one site reports 40 independent origins and lifts tertiary
   claims to the 0.80 corroborated ceiling on one publisher's authority, making
   `expert quality` lie. Origin keys must collapse to publisher through the
   existing `_canonical_url_source_key` (`beliefs.py:27-48`).
2. **`absorb-okf --trust-class`.** A directory absorb path already exists
   (`src/deepr/cli/commands/semantic/expert_okf.py:185-274`) and passes no trust
   class, so every Distill corpus that goes through it is capped at 0.60. Small
   fix, large effect on whether depth registers at all.
3. **Typed-state revision and provenance.** `evidence_refs` are accepted by
   `promote_stance_candidate` and written into `uncertainty_log` rather than
   onto the record (`metacognition.py:473-483`); `ExpertStance` has no
   `evidence_refs` field. Insight without citations cannot render in a wiki.
   Revise and retire operations must exist before the first insight is written.
4. **A path from absorb to typed shapes.** Either route `absorb` through the
   source-pack pipeline (recommended: one extra verification call, $0 with
   `--local`, reuses the existing verifier contract) or accept that typed state
   stays empty. Widening the absorber's own prompt is the cheaper-looking option
   and the wrong one: its gates are a `min_confidence` float and two lexical
   routers, none of which can enforce `requires_external_support` or
   `requires_disconfirming_signals`.
5. **Packet assembly that separates stance from evidence.** Otherwise insight
   lands in the store and never reaches an answer.

## What this replaces in the current plan

The plan's gap 6 reads "stance / fail-pattern / elite-bar not typed memory ->
later / 6+" (`living-expert-research-stack.md:163`). That is mis-scoped in two
directions: most of the typed machinery already exists, and the missing piece is
not storage but the reasoning pass that produces something worth storing.

It also changes Step 4.1's acceptance. If `absorb-dir` ships as a beliefs-only
batch loop, every corpus it ingests is permanently flattened to atomic claims,
and the insight layer later has to re-read all of it. The absorb-to-typed-shapes
decision (prerequisite 4) should be made **before** 4.1 is built, not after.

## Success criteria

1. A digest section a practitioner would actually read: fail patterns with
   triggers and corrections, stance with decision criteria, named tensions
   between sources, open questions. Not a confidence-sorted bullet list.
2. Every insight cites the corpus windows it came from, and a reader can follow
   them.
3. A consult on a deepened expert returns at least one thing the operator had
   not written into project intent, traceable to a domain source.
4. Re-running acquisition after the field moves produces a visible delta: what
   changed, what it invalidated, what is newly contested.
5. An insight the operator judges wrong can be retired, with the reason and a
   snapshot preserved.

## Non-goals

- A "insight score", maturity level, or depth percentage.
- Reimplementing Distill or Learny inside Deepr.
- Generating insight from the belief store instead of from sources.
- Insight that renders as verified fact.
- Any of this on metered capacity while paid dispatch is frozen.
