# Expert v2: from fact ledger to research organism

Status: proposed architecture, 2026-08-05.
Supersedes the implicit v1 model in which an expert *is* its belief store.
Companion: [expert-insight-layer.md](expert-insight-layer.md) (why the reasoning
stage is missing). Plan: [../plans/living-expert-research-stack.md](../plans/living-expert-research-stack.md).

## The verdict on v1

Measured on the live NephMesh expert, 2026-08-05: 92 beliefs, 20 edges (all
`supports`), and empty `documents/`, `knowledge/`, and `conversations/`
directories. Across the 39-expert fleet, 77.4 percent of displayed confidence
values are the single constant 0.60, and zero experts have any typed
perspective state populated.

That is a sentence database with a decay curve. Calling it a domain expert is
not a stretch of terminology, it is a category error, and every downstream
complaint (flat confidence, circular sources, generic synthesis, no dissent)
follows from it mechanically.

**The root cause is architectural, not a missing feature.** v1 makes `Belief`
the center of gravity: absorb's only output type, the store's only first-class
record, the consult packet's only content, the digest's only input. Anything
that is not expressible as one atomic sentence plus a float has nowhere to live.
Expertise is mostly not expressible that way.

## The v1 pipeline, and where it destroys value

```
document -> extract atomic claims -> confidence gate -> dedup -> Belief rows
             ^                                                      |
             |                                                      v
        source text discarded                            digest: sort by confidence
```

Three lossy steps, each irreversible:

1. **Shred.** The extraction prompt requires atomic single-fact claims and
   instructs that a sentence joining two facts be split
   (`report_absorber.py:930-955`). Any conditional, comparative, or causal
   structure is destroyed at ingestion.
2. **Discard.** The source text is not retained. Only `report:file:<basename>`
   survives. The expert can never re-read what it learned from.
3. **Flatten.** The only rendering is confidence-sorted bullets
   (`digest.py:114,186`), so even the structure that survives is presented as a
   ledger.

Nothing downstream can recover what these steps remove.

## The v2 model

An expert is **a maintained corpus, a body of study notes derived from it, a set
of positions the expert will defend, and a record of how all three changed** -
with atomic claims as a retrieval index over that, not as the thing itself.

```
acquire (Distill, $0 local)
    |
    v
CORPUS  ......... owned, content-addressed, re-readable, growing
    |
    +--> study pass (multi-lens, bounded, $0 local) ......... THE MISSING STAGE
    |         |
    |         +--> per-source NOTES        what this source actually says
    |         +--> cross-source ANALYSIS   tensions, consensus, evolution
    |         +--> typed PERSPECTIVE       stance, fail patterns, concepts, hypotheses
    |         +--> GAPS                    what the corpus does not answer
    |
    +--> extraction ......... atomic claims as a *retrieval index* over the corpus
              |
              v
          TKG edges: what supports, contradicts, supersedes, and *when*
              |
              v
    NOTEBOOK (rendered) + CONSULT PACKET (assembled) + HANDOFF (compiled)
```

The inversion: in v1 beliefs are the product and everything else is decoration.
In v2 the corpus and the derived study are the product, and beliefs are the
index that makes them retrievable.

## On-disk shape

```
<expert>/
  profile.json
  blueprints/blueprints.jsonl        # operator-attested purpose (exists)

  corpus/                            # NEW - the expert owns what it learned from
    index.jsonl                      # origin_key, url, publisher, fetched_at,
                                     # sha256, trust_class, kind, superseded_by
    sources/<sha256>.md              # retained text, content-addressed

  notes/                             # NEW - per-source study
    <source_sha>.md                  # what it says, mechanisms, scope, caveats
                                     # every line anchored to a corpus offset

  analysis/                          # NEW - cross-source, the Learny-shaped output
    tensions.jsonl                   # who disagrees, about what, what would settle it
    consensus.jsonl                  # settled across N independent origins
    evolution.jsonl                  # what changed, when, what it invalidated

  perspective/                       # types exist in code, zero populated today
    stances.jsonl  fail_patterns.jsonl  concepts.jsonl  hypotheses.jsonl
    meta_events.jsonl                # NEW - created/revised/retired + snapshots

  beliefs/                           # exists - now an index, not the product
    beliefs.json  events.jsonl  mutation_audit.jsonl

  graph/                             # TKG - real edge types, not 20 supports
  notebook.md                        # NEW - the rendered study document
```

Every layer above `beliefs/` is regenerable from `corpus/` plus the study
passes. That is the point: **when understanding of a field changes, you re-study
the corpus rather than re-acquiring it.** In v1 that is impossible because the
corpus is gone.

## The study pass

One bounded, local, $0 operation with a fixed shape. Not an agent loop.

```
deepr expert study NAME [--lens ...] [--since <date>] [--local] [--dry-run]
```

For each lens, read the corpus (or the delta since last study) and emit typed
candidates. Lenses are independent and are never asked to agree.

| Lens | Question | Primary output |
|---|---|---|
| Mechanism | How does this work beneath the vocabulary? | concepts |
| Failure | What breaks, when, how is it detected, what is the fix? | fail patterns |
| Contention | Where do independent sources disagree, and on what? | tensions |
| Change | What is different now, and what does that invalidate? | evolution, superseded edges |
| Practice | What survives production vs what is documentation-only? | stance |
| Absence | What would a practitioner expect here that is missing? | gaps |

**Multiple lenses is the mechanism, not decoration.** A single synthesis pass
over a corpus produces exactly the generic best-practice mush the live NephMesh
validation surfaced. Independent lenses produce material that disagrees with
itself, and the disagreements are the insight. This is the same argument
`diverse-expert-council.md` makes about council composition, applied one level
down to material rather than to a project.

Cost: N lenses x corpus chunks, all local. Hours, not dollars. Delta studies
after the first are small.

### Admission stays deterministic

The study pass proposes; the existing verifier and commit gates admit. Code
checks that a fail pattern has a trigger, a symptom, a correction, source
anchors, and a disconfirming signal. Code never checks that it is *good*. Model
judgment owns meaning; form and side effects stay deterministic
(`ROADMAP.md:5-31`, `AGENTIC_BALANCE.md`).

Two hard rules, both load-bearing:

1. **Every note, tension, and stance anchors to corpus offsets.** Not to a
   filename. A reader follows the anchor to the text. Unanchored output is
   rejected, which is a form check.
2. **The study pass reads the corpus, never the belief store.** A pass that
   reasons over the expert's own prior conclusions is the echo chamber with
   extra steps.

## The notebook

`expert digest` today sorts claims by confidence. The v2 render is a study
document, and the confidence number leaves the headline entirely:

```
# <Expert>
## Scope and non-goals            <- blueprint, operator-attested
## What I currently think         <- stance, with decision criteria
## How this works                 <- concepts, mechanism-first
## What breaks                    <- fail patterns: trigger -> symptom -> correction
## Where sources disagree         <- tensions, both sides quoted and cited
## What changed recently          <- evolution, with what it invalidated
## What I do not know             <- gaps and open questions
## Sources                        <- corpus index: publisher, currency, trust
## Claim index                    <- the atomic layer, last, as an index
```

A confidence value renders only where it is informative. Where it equals its
trust ceiling (77 percent of the fleet) it renders the reason - `capped: single
tertiary source` - not two decimals of false precision.

## What has to be true for this to work

Ordered by dependency. Each is a finding from the code, not a guess.

| # | Prerequisite | Why |
|---|---|---|
| 0 | **Corpus retention** | Without it there is no second lens, no re-study, no passage to show. Everything else is downstream |
| 1 | **`absorb-dir` with publisher-collapsed origins** | Corpus at scale, without letting a 40-page crawl of one site report 40 independent origins and inflate trust ceilings |
| 2 | **Typed-state revision + `evidence_refs` on the record** | `promote_*` silently refuses duplicate titles and drops evidence refs into `uncertainty_log`. Writing insight onto a write-once substrate makes the first wrong reading permanent |
| 3 | **The study pass** | The missing stage |
| 4 | **Real TKG edge types** | 20 `supports` edges is not a temporal graph. `supersedes`, `contradicts`, `refines`, `bounded_by` with `valid_from` / `valid_until` |
| 5 | **Notebook render** | Otherwise the study lands in the store and nobody reads it |
| 6 | **Packet assembly that separates stance from evidence** | Otherwise the study lands in the store and never reaches an answer |

## Sequencing

Each phase is independently useful and independently shippable. No phase
requires the next to justify itself.

**Phase 1 - the expert can keep and re-read what it learned.**
Corpus retention, `absorb-dir` with correct origin identity,
`absorb-okf --trust-class`. Ends with: experts hold real multi-origin corpora
and `expert quality` reports honest origin counts.

**Phase 2 - the substrate can hold a changed mind.**
`evidence_refs` on typed records, `revise_*` / `retire_*` with snapshots,
`meta_events.jsonl`, the `MetaCognitionTracker` canonical-path fix. Ends with:
nothing written in Phase 3 is permanent by accident.

**Phase 3 - the expert studies its corpus.**
`expert study` with the six lenses, `ExpertFailPattern` end to end, tensions and
evolution records, anchored citations. Ends with: an expert holds material a
sentence-level extractor structurally cannot produce.

**Phase 4 - a human and an agent can use it.**
Notebook render, packet assembly with stance/evidence separation and
contradiction counterparts, handoff blocks for fail patterns and elite bar,
challenge consult mode. Ends with: consults argue instead of agreeing.

**Phase 5 - it stays current and honest.**
Subscriptions seeded from study gaps, delta studies on refresh, evolution
records, calibration honesty fixes. Ends with: re-running acquisition after the
field moves produces a visible, reviewable delta.

## What v2 does not change

- Absorb remains the write boundary. Distill and Learny artifacts are evidence.
- Capacity honesty: local `$0` default, plan quota only when proven, metered
  dispatch stays frozen.
- Deterministic gates own form, spend, writes, and provenance. Model judgment
  owns meaning, and is labeled rather than promoted to fact.
- No lexical scoring of quality, depth, maturity, or insight.
- One-shot consult stays one-shot. Better input, not unbounded debate.

## Migration

Additive. Existing belief stores keep working and keep their events; they simply
have no corpus, no notes, and no analysis until an operator re-absorbs with
retention on. `expert notebook` on a v1 expert renders the claim index plus
empty-state notes pointing at `deepen-plan` and `study`. No forced regeneration,
no store rewrite.

The honest statement for a v1 expert is that it holds an index without the
material - which is exactly what it is.
