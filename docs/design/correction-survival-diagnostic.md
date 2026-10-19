# Correction survival diagnostic

Status: first increment implemented 2026-10-19 (mock answers, no inference).
Issue: #259. Builds on the receipts from
[evidence selection and delivery](evidence-selection-and-delivery.md) (#258).

## Question

After an expert receives a credible correction, does its later advice use the
correction while keeping what stayed valid? If not, where was the evidence
lost: in the source world, the study, the brief synthesis input, consult
retrieval, the final prompt boundary, or the answer?

A larger history, a changed statement or a higher retrieval score does not
answer this. This diagnostic is separate from the frozen S0 pilot in
[living expertise](../plans/living-expertise.md) and does not change it.

## Shape

- **Frozen case set** (`evals/correction_survival_cases.py`,
  `correction-survival-v1`). Three chronological worlds about an invented job
  scheduler, so no model has prior knowledge: a v2 manual, then a release note
  that changes one default on one platform (plus an unsourced contrary forum
  post), then a genuine exception and an unresolved disagreement. Eleven cases
  cover warranted correction, inapplicable contrary evidence, unresolved
  disagreement, a historical question, a false premise with a sound-premise
  control, missing evidence with an answerable control, a near-match version,
  a low-overlap synonymous correction, and repeated compression. Each case's
  obligations and the review rubric are frozen before any answer exists, and
  the whole set is hashed.
- **Three arms, one allowance.** `production` runs the shipped path: fixture
  findings grounded against the retained sources, `build_brief` with the
  world's frozen synthesis, `build_consult_context`, `build_synthesis_packet`.
  `oracle_packet` hands the obligation evidence to the same packer, separating
  retrieval and packing from reading. `fresh_sources` supplies the world's
  library without memory, measuring what continuity adds. All use the same
  completion and prompt bound.
- **Stage receipts per obligation.** Mechanical states only: source present,
  finding represented and anchored, presented/omitted/shortened at briefing
  (from `synthesis_input`), selected or missed by retrieval, delivered,
  omitted by the limit or never assembled (from the delivery manifest). The
  answer stage stays `unreviewed` until a reviewer label is bound.
- **Isolation and repetition.** A historical case lists forbidden later
  sources; the run reports `isolated` or `leaked` per arm by checking the
  world, the delivered passage hashes and every sentence of each forbidden
  source against the prompt. For the frozen worlds isolation holds by
  construction; the check exists to catch a world or arm change that admits a
  later source. A repeated case
  re-briefs unchanged evidence and records study identity and per-position
  provenance per cycle, so repetition cannot be counted as new evidence.
- **Distractors.** Small worlds fit every bound, so retrieval and packing
  cannot fail there. `--distractors N` adds deterministic on-topic filler
  sources and findings per world and records the count.
- **Accounting and reuse.** Every scheduled case, arm and cycle is recorded,
  including failed answers. Prompt and answer files are hashed; `run.json`
  binds the hash of exactly the cases scheduled (a subset never shares the
  full set's hash and is labelled as a subset) and a recipe hash over the
  brief, attribution, selection, support-resolution, study, packing and
  diagnostic modules. `COMPLETE.json` is written last after every file is
  re-verified. `load_run` refuses a run without it, with altered files, or
  produced from another case set or recipe; an answer file alone is never a
  completed run. It also refuses a run whose recorded attempts differ from
  the scheduled count.
- **Blinded review.** `blinded_review_packet` lists answers under salted
  opaque ids with no arm names. `bind_review_labels` accepts a label only for
  a known item, obligation and exact answer hash, from the closed label set,
  with a named reviewer, once, including across calls when earlier bindings
  are passed in. Freezing labels before opening the key is a review procedure
  the caller owns; the code cannot enforce it.

`deepr eval correction-survival [--distractors N] [--output-dir DIR]` runs the
mock diagnostic at `$0` and writes the run with `report.json` and `report.md`.

## Decisions and alternatives rejected

- **No lexical answer scoring.** Whether an answer used a correction is
  semantic. Required phrases or word overlap would be a verdict encoded as a
  rule ([AGENTIC_BALANCE](../plans/AGENTIC_BALANCE.md)).
- **No new memory backend or orchestration framework.** The production
  builders, brief receipt and delivery manifest already exist.
- **Not the rehearsal worker's common prompt.** That prompt suits the S0
  comparison but bypasses production selection and packing, which is what
  this diagnostic must exercise.
- **Harness2-style recipe contrasts** (the issue's optional reference) are
  not built. The four-arm recipe matrix would add machinery before any
  semantic budget is approved; the parameterized fixture covers the mechanical
  part with less.
- **No procedural-lesson loop.** A repeated failure becomes a scoped,
  versioned proposal with traces, not an automatic behaviour change.

## Limits

Mock answers prove transport and accounting only. The worlds are tiny and
synthetic; transfer to real domains is unknown. The brief synthesis is frozen
fixture output, so briefing-stage loss in a real model run is not measured
here. The fresh arm receives sources in corpus order, which can favour it when
real sources sort before filler. A local semantic run needs separately
approved limits, an attested model digest and blinded reviewer labels before
any claim about answers. A fresh baseline matching or beating maintained
memory would be a valid negative result.
