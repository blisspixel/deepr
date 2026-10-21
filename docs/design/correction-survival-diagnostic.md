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
  `correction-survival-v2`, with v1 retained separately). Three chronological worlds about an invented job
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
  targeted selection from packing. It is not a complete-world upper bound:
  related qualifications can be absent even when the target source is delivered.
  Inspect actual prompts before attributing a failure to reading. `fresh_sources`
  supplies the world's library without memory as a descriptive comparison. All use the same
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
  the scheduled count. JSON artifacts use explicit UTF-8 and LF newlines, so
  their hashes match the actual bytes on Windows as well as other platforms.
  Ambient text newline translation must not invalidate a newly collected run.
  Historical read-only inspection can instead require an
  explicit recorded recipe pin, as described below; the default current-code
  guard remains unchanged.
- **Blinded review.** `blinded_review_packet` lists answers under salted
  opaque ids with no arm names. `bind_review_labels` accepts a label only for
  a known item, obligation and exact answer hash, from the closed label set,
  with a named reviewer, once, including across calls when earlier bindings
  are passed in. Freezing labels before opening the key is a review procedure
  the caller owns; the code cannot enforce it.

`deepr eval correction-survival [--distractors N] [--output-dir DIR]` runs the
mock diagnostic at `$0` and writes the run with `report.json` and `report.md`.
`--local-model MODEL [--model-digest DIGEST]` answers instead through the
production consult system prompt and native local dispatch
(`evals/correction_survival_local.py`): the digest is attested before the
first call and on every call, a mismatch refuses or fails the attempt, and
each attempt records its dispatch (stop reason, tokens, elapsed time, `$0`).

### Routing identity and latency (v2.50.43 repair, #259)

`--embedding-model MODEL` keeps one attested embedding digest, resolved profile
and vector dimension across query/document calls and later attempts. An identity
change takes the disclosed lexical fallback. Each attempt's `finding_routing`
records configured and effective routes, success/fallback/unused state, identity,
reason and content-free call summaries referencing the canonical local attempt
ledger. Failed/refused calls remain visible; missing usage is null, not known
zero. Unavailable durable accounting cannot produce a successful ranking.

`elapsed_ms` retains its original answer-only meaning, also named
`answer_elapsed_ms`. `routing_elapsed_ms` includes embedding work and refusal;
`total_elapsed_ms` measures routing plus packet assembly through answer
completion. Shared fixture materialization and artifact writes are outside that
attempt measure. The report aggregates timings and effective-route/state counts,
embedding calls, known input tokens, unknown usage and unsettled accounting.
Legacy records have unknown routing/total times, never fabricated zeros. Recipe
identity now includes the embedding backend/profile and native attempt recorder;
retained old runs are not rewritten. See
[the design decision](consult-embedding-routing.md#identity-and-diagnostic-accounting-repair-2026-10-20-259).

## Historical review after a code update (2026-10-20, #275)

At the time of this repair, the retained 36-answer run still had the frozen case-set identity, but the
routing/accounting repair changed the recipe hash. The default `load_run`
correctly refuses it as a current-code result. Review must nevertheless remain
possible without regenerating answers or reading raw JSON around the verifier.

Add an optional, explicit `expected_recipe_sha256` to the existing loader.
Omitting it still requires the current recipe. Supplying it requires exactly
64 lowercase hexadecimal characters and an exact match with the recorded
recipe. This is artifact inspection, not execution or cache admission. All
existing completion-marker, current case-set, scheduled-count and prompt/answer
file-hash checks remain mandatory. A changed case set still requires the
original implementation; this increment does not invent an archived schema
interpreter or reconstruct missing inputs.

Expose `deepr eval correction-survival-report --run-dir DIR --recipe-sha256 SHA`
as a read-only command. It cannot construct a completion or router, create a
run, write a report, alter a ledger or bind labels. The operator obtains the pin
from the retained experiment's known record, rather than inferring that an
arbitrary changed run is current. Reports retain recorded code/recipe identity
and separately show the current recipe and its exact equality comparison.
Identity equality is not a verdict on answers, code compatibility or quality.
Reports remain operator artifacts; reviewers continue using the existing
blinded packet with its assignment key withheld.

The later v2 fixture correction changes the case-set identity as well. Inspect
v1 with the retained compatible v2.50.43 implementation and its original recipe
pin; the current implementation correctly refuses that old case set.

Reject a `skip_checks` switch: it would also lose artifact and case binding.
Reject changing the historical recipe or rewriting the old run to resemble
current execution. Do not relax the default guard or rerun inference merely to
produce reviewable artifacts. Reproduce changed-code loading with synthetic
completion output, then exercise the actual retained run by its original pin,
without viewing answer text, opening an assignment key or adding labels.

## Retained-answer review completion (2026-10-20, #259)

Review the existing 36-answer, 60-obligation packet using its original frozen
sources, obligations, rubric and recipe pin. Do not regenerate its answers or
alter original files. Independent model reviewers must first pass predeclared
semantic controls. Preserve unsuccessful local and independent calibration, malformed
outputs and any later review failure. Clarifying mutually exclusive label
precedence before review is distinct from changing the original obligations or
adding a retrospective success threshold; retain both the clarification and its
failed predecessor.

Keep the assignment key closed while model labels and their semantic reasons
are frozen and inspected. Then use the existing label-binding and report
functions to join exact answer hashes and stage receipts. Report all scheduled
attempts, per-case scope errors, appropriate deferrals, nonanswers, original
resource observations and unknown review costs. A useful negative measurement
can complete this diagnostic. It cannot establish expertise, approve S0, promote
embedding routing by default, or validate model judgments outside these cases.

### Prospective fixture and review-handoff correction

Independent source-backed review found a v1 fixture defect: the manual promises
enabled keys on every platform, while the macOS case says its default is
unknown. Keep the original sources, answers and resulting ambiguity intact.
Freeze a v2 case set before collecting replacement answers, explicitly limiting
the manual, derived findings and initial position to the documented Linux,
Windows and container platforms, and stating the macOS question's version.
Audit the other fixture interpretations against their sources as well.
Preserve the vendor's measurement and the maintainer's suggestion as distinct
evidence, separate local worker duplicate suppression from external-provider
windows, retain the provider-specific duration and modal risk, and keep the
new payment qualification out of earlier source worlds. A fresh v2 measurement
is separate from the reviewed, defective v1 trial.

The blinded packet must carry its frozen source world and detailed obligations,
not merely point a reviewer at mutable source code. Move the existing review
binding and packet functions together into a named read-only review seam,
preserving their public imports. Bind source bytes and metadata to the scheduled
case-set identity before producing a packet, and test historical-world isolation
and stale-case refusal. Include the runtime's deterministic distractor sources
when configured, with the same source bytes, observation cutoff, origin and
trust metadata. A note that establishes no recommendation within its own
planning scope can still affect interpretation; excluding it from review
would misrepresent what the generator could read. Reuse the fixture generator
through the owning case module rather than reconstructing a second version.
Each new run records a fingerprint of its full materialized source inventory,
including runtime notes and metadata. Packet generation verifies that fingerprint
before exporting sources. A historical run with auxiliary sources but no bound
inventory requires its compatible producer; do not reconstruct those bytes from
a later fixture generator. Legacy zero-distractor runs remain case-bound because
the case-set digest already includes every base source byte and its metadata.
Do not add a bypass to the historical case guard: v1
inspection still uses its retained compatible implementation and explicit recipe
pin. Its old answers must not become v2 results.

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

### Owned generation recipe binding, 2026-10-20

The recipe also binds the local answerer, council system prompt/output-budget
owner and synthesis request dispatcher. Omitting those files let output limits,
context settings or the forwarded prompt change without invalidating the recipe.
A temporary source-byte overlay reproduces all three gaps without changing the
repository or calling a model. Default loading must reject that changed recipe;
an explicit original pin still permits read-only historical reporting with
`recipe_matches_current: false` and unchanged artifacts.

This is a bounded identity repair for those owned generation seams, not complete
runtime reproducibility. Injected completions, caller arguments, other imported
dependencies, model/daemon behavior and external state remain separate inputs.
The new guard never rewrites a recorded recipe, resets a model budget or admits
execution reuse from a historical inspection pin.
