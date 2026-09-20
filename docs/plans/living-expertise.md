# Delivery plan: current, cumulative expertise

Status: planned, 2026-09-20. The [active roadmap](../../ROADMAP.md#active-release-plan)
owns priorities and release targets. This document defines dependencies,
contracts, and acceptance evidence for that sequence. The
[September research assessment](../design/living-expertise-research-2026-09.md)
explains the research; [Supported Surface](../SUPPORTED_SURFACE.md) says what
runs. Stage identifiers below are stable even if release targets change.

## Product contract

An expert develops understanding through study, investigation, reflection,
and experience. It retains concepts, explanations, positions, hypotheses,
tradeoffs, dissent, research history, and what might change its mind. It uses
that understanding to orient a caller, share insights, and guide a decision.
Currentness is part of expertise: preparing for the immediate question is the
default product behavior to deliver, including relevant developments and the
caller's environment. Periodic maintenance does not establish readiness for
every question.

The temporal graph records evidence relationships and changing perspectives.
The wiki is a navigable, derived account of that understanding. Neither a
larger fact inventory nor regenerated prose proves learning. The release gate
is useful, supported guidance that survives correction and repeated use.

## Dependency order

`S0 baseline -> S1 prepared consultation -> S2 durable temporal learning ->
S3 perspective and inquiry -> S4 repeated-use proof -> S5 wider autonomy`

Baseline results may be negative. Recording them completes measurement, not
proof of value. S1 prototypes and fixtures can proceed after the S0 protocol
is frozen; the baseline must be preserved before comparative claims. A poor
baseline does not block repairs to preparation. Failed stage acceptance keeps
that capability experimental. Wider autonomy requires positive held-out
evidence, rather than completion of every planned module.

### S0: preserve the baseline and freeze what improvement means

Reuse the existing blueprint, source-world preflight, four-arm workbook,
[local rehearsal](../design/local-four-arm-rehearsal.md), and
[v2.51 protocol](../design/expert-purpose-and-value-loop.md#v251-pilot-protocol).
Source integrity, an operational rehearsal, blinded review, and demonstrated
benefit are separate statuses. Do not repeat completed runs without a changed
input or a documented evidence gap.

Freeze one expert's mission, decisions, source access, exact model identity,
resource ceilings, arm policies, and reviewer rubric. Finish isolated input
materialization and answer-to-review binding where evidence is missing. The
existing 12 cases across four arms and three chronological worlds produce
48 terminal cells, including failures. Preserve development cases separately
from held-out cases; reviewers do not see arm identities until labels freeze.

**Exit evidence:** replayable inputs and outputs, failure denominators, binding
checks, reviewed per-case results, and explicit measured/unmeasured dimensions.
The workbook is an aggregator, not an arm executor or an automatic winner
selector. Human review may be unavailable; record that limit and keep the
value gate open. Do not manufacture attestations to finish a stage.

### S1: prepare before consultation, with bounded temporary evidence

**Depends on:** a frozen S0 comparison contract, current capacity checks, and
the existing acquisition and consultation seams. Complete historical memory,
prediction resolution, new host integrations, and new providers are not
prerequisites.

Normal CLI and MCP query/consult should follow one shared service flow:

1. Establish the question, target environment, information date, and limits.
2. Inspect the stored perspective and identify assumptions needing a check.
3. Reuse a matching preparation packet or acquire permitted current sources.
4. Study relevant changes, unresolved conflicts, and implications for advice.
5. Freeze the expert revision plus admitted temporary evidence, then answer.

Reuse source packs, consult context, traces, and lifecycle records. Before
implementation, define the additive preparation contract: operation identity,
caller and authorization scope, expert revision, question scope,
environment/version constraints, source hashes
and observation times, checked and unchecked assumptions, reuse policy, limits,
attempts, stop reason, and context snapshot identity. Proposed field names and
commands are not a supported interface until they land.

The model chooses research direction and interprets relevance. Code enforces
finite source, byte, context, call, elapsed-time, and capacity limits. Every
attempt, including a failed or cancelled one, consumes its applicable allowance.
Repeated identical requests reuse an operation result; retries cannot create
duplicate learning or fresh allowances. An ambiguous dispatched attempt stays
visible and is not automatically retried through another backend.

Consultation retains source material and staged learning proposals but does not
mutate canonical findings, positions, confidence, or learning policy. Therefore
useful prepared advice can ship before S2's finding history. Read-only handoff,
inspection, and packet assembly remain free of research side effects.

A Python expert checks relevant runtime/library releases and advisories against
the caller's pinned environment. Enduring conceptual questions may need little
new evidence, with that judgment recorded. Reuse requires matching scope,
versions, observations, and freshness coverage. Empty search results, recent
file timestamps, or unchanged page hashes cannot certify currentness.
Packets containing private task context stay bound to their caller and source
permissions. A matching expert or question cannot authorize cross-caller reuse.

Make offline/frozen operation explicit and dated. Expose partial, failed,
cancelled, and completed preparation separately. If checking fails, identify
the affected guidance and qualify or defer it. New conversations freeze after
preparation. Existing frozen conversations require explicit refresh or fork
for later evidence; the prior snapshot stays reproducible.

**Exit evidence:** CLI/MCP parity, visible preparation, applicable release and
correction cases, scoped reuse, denied cross-caller reuse, unavailable retrieval, timeout/cancellation,
duplicate requests, and unchanged canonical expert state. Run preparation
enabled/disabled from the same revision in a separate paired experiment;
freeze its sources and account for all extra work. Add a small dated live-source
smoke after frozen tests to establish real acquisition. A smoke test does not
prove longitudinal benefit. Default-on release requires these checks and
reviewed advice; it does not require a successful forecast or self-improving
harness.

### S2: preserve learning and select the applicable historical state

**Depends on:** S1 evidence and snapshot contracts. Reuse record identities,
position history, temporal primitives, and the existing admission boundary.
Close the [position-justification fidelity gap](../design/position-justification-and-explanation.md)
within this stage: reasoning, uncertainty, assumptions, counterevidence, and
revision signals must survive serialization and participate in version identity.
Historical position reads cannot claim complete perspective reconstruction
while those fields are lost.
Add finding revision history with a rebuildable current projection. Source-only
study remains independent of prior conclusions; reconciliation happens after
that study. Exact replay is mechanical. Semantic equivalence, contradiction,
supersession, and withdrawal require reviewed judgment. Not revisited does not
mean retracted, and a rephrased title does not establish a new identity.

Use record time for what the expert knew at a cutoff; known validity and version
constraints describe applicability. Unknown dates stay unknown. Carry the
selected revision through positions, findings, and supporting passages before
truncation or ranking can lose the eligible evidence. Strict historical reads
cannot include later observations. Present-day retrospective annotations are
separate, explicitly dated views. Newest alone does not establish authority.

Write the additive migration and recovery design before code: retain old
records, make repeat applies idempotent, recover interrupted projections, and
check source links after rebuild. Do not require a new database or fleet-wide
event-store migration. Preserve registered expectations and their original
criteria across revisions; registration and the read-only experience join
already exist and must not be rebuilt as new features.

**Exit evidence:** replay, interruption, changed wording, partial study,
late-arriving evidence, unknown validity, pinned environments, and obsolete
near-matches. Rebuilding the current view and wiki preserves history and
citations. A rejected admission leaves the previously committed state usable.

### S3: develop a perspective and choose useful inquiry

**Depends on:** S2 lineage and source-only study. Add a distinct synthesis step
over admitted findings, earlier positions, perspective graph, research
practice, and recorded investigations/outcomes. Preserve concepts, reasoning,
insights, tradeoffs, dissent, and the reason to revise or retain a view.
Factual premises need support; interpretations need rationale and uncertainty;
hypotheses need possible tests. Novel phrasing earns no credit by itself.

Link competing explanations to the observation that could distinguish them.
Use existing pursuits, watches, and falsifiers to choose a bounded next inquiry.
Similarity does not establish causality. Resolve registered predictions only
against independent later evidence, with reviewed observed, contradicted,
inconclusive, or unchecked outcomes. Missing evidence is not disproof.
Predictions cover only part of expertise; explanatory and decision usefulness
need their own review.

Expose the resulting orientation, reasoning, and source links through bounded
consult context and the derived wiki. Extend the existing change summary to
show proposed, accepted, unresolved, and unexamined changes. No-op, partial,
and failed runs remain distinct. Extend existing experience/outcome links with
exact answer and context revisions where needed. Delivery does not prove use,
and an outcome record does not establish that advice caused the result.

**Exit evidence:** a new connection survives the next study; a material change
propagates to applicable guidance; sound older understanding remains; a caller
can trace why a perspective changed and what remains unresolved. Resolving a
prediction cannot itself change confidence, prompts, routing, or policy.

### S4: demonstrate repeated use and supervised renewal

**Depends on:** S1-S3 and the preserved S0 baseline. Maintain one expert through
initial evidence, a correction, then incomplete/distracting later material.
Track last substantive review by topic and follow effects into related
positions and advice. Supervised maintenance is enough for this stage.

Repeat the four-arm protocol on a new held-out history. Keep S1's preparation
ablation separate so freshness and accumulated understanding are not confused.
All arms receive the evidence their frozen policy promises. Match the model
and declared answer limits, and report construction, preparation, maintenance,
review, and consultation resources separately. Equal final-answer budgets do
not establish equal total compute. Report an equal-total-resource sensitivity
comparison if feasible; otherwise limit efficiency claims explicitly.

Report correctness, explanatory/decision usefulness, warranted insight,
transfer, false support, stale reuse, retained understanding, abstention,
coverage, latency, context, reviewer effort, and cost separately. Calibrate
model review against human labels. Keep unfavorable and missing results.

**Exit evidence:** independently reviewed benefit on held-out cases, with
predeclared harm tolerances and no hidden regressions or omitted failures.
Freeze numerical tolerances before collection; do not select them after seeing
results. Negative or inconclusive evidence triggers a named repair and a fresh
comparison, not an automatic expansion. Live prospective outcomes are labeled
separately from frozen-world replay. One expert establishes a bounded result,
not universal superiority.

### S5: expand only the mechanism that earned it

**Depends on:** S4 benefit, recovery evidence, and current capacity admission.
Promote bounded currency maintenance before research-strategy modification.
Each topic needs coverage and substantive-review evidence; scheduled fetching
alone does not establish readiness. Consultation keeps its own preparation.

Research-strategy and harness changes begin as shadow proposals with failure
traces, a predicted effect, exact model/harness versions, independent evaluation,
retained-capability checks, context-growth limits, and rollback. Record null
results and negative transfer. A model change requires revalidation. Accepted
self-model guidance and telemetry cannot silently change default policy.

New hosts, remote control, larger councils, additional providers, concurrent
multi-device mutation, and storage migrations have separate necessity and
authority gates. They are not prerequisites for S1-S4. The internal Level 5/6
labels are descriptions of demonstrated gates, not autonomy or intelligence
scores.

## Validation budget and execution record

The operator's ceiling for this validation campaign is **$10 total**, shared
across all stages, live checks, model/judge/tool use, retries, failed attempts,
and release validation. It does not reset per run, backend, day, or release.
The planned path is **$0 incremental external spend**: local deterministic
checks, owned-local inference, public retrieval, and standard public-repository
CI. Record local runtime, tokens, and reviewer effort separately.

No paid validation is needed for the documentation change or the initial local
pilot. All production plan adapters currently remain blocked. The attended
one-shot paid research path does not authorize paid consultation, learning,
judging, or an external instrument. Existing account controls, wallet holds,
per-job ceilings, and any tighter calendar limit remain binding; this plan
does not raise them or create a new funding balance.

For any later charged validation, bind the campaign to saved baseline ledger
positions and count settled charges plus outstanding worst-case holds across
every instrument before dispatch. Effective remaining authority is the smallest
of campaign headroom and all existing limits. Unknown costs or unbounded
external billing block that path. Report actual spend and unresolved holds in
the validation record; never infer zero cost from a missing usage receipt.

Retain configured report roots, immutable inputs, exact code/model versions,
commands, terminal outcomes, and review bindings. Reuse valid evidence and run
the smallest experiment that resolves the next uncertainty. Do not spend the
remaining allowance merely because it exists.

## Delivery discipline

Use small reviewed changes on short-lived branches, merge only after required
checks, verify CI on the resulting `main` commit, and remove the merged task
branch. Keep `main` as the sole long-lived branch. Documentation-only planning
updates go in `Unreleased`; they do not require a package version bump.
Publish a release when a coherent fix or capability and its validation are
ready, following the roadmap's package, tag, artifact, and installer checks.
Do not label an unreviewed experiment as a completed value milestone.
