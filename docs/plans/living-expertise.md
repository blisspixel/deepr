# Delivery plan: current, cumulative expertise

Status: in progress; execution plan reviewed 2026-10-22. Step 1 of the
[currency order](../design/expert-currency-order.md) is a read-only inspection
and an explicit world-time admission. v2.50.29 makes consult say whether a
citation reaches the loaded study and a retained passage, and it sends local
synthesis through the native context window study already uses. v2.50.31
repairs readable evidence, perspective attribution, terminal consultation and
failed-build reporting. It does not run S0. S0 through S4
remain open. The
[active roadmap](../../ROADMAP.md#order-of-operations)
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

Strong expertise includes confident, well-supported answers to established
questions. Candour about missing knowledge is necessary, but does not count as
knowing the subject. Qualification needs both an absolute bar for useful
answers within the declared scope and evidence of improvement over a baseline.
Being better than an inadequate baseline is insufficient.

**Expertise is open-book.** A high-quality source library, excellent notes, fast
retrieval and appropriate tools are core expert capabilities. The system should
inspect authoritative details when available rather than depend on model recall
or a compressed summary. Preserve original source text, source identity,
applicable editions/versions, rights and access limits, and useful links from
concepts and guidance into the reference library. Notes explain connections and
tradeoffs; the original source supplies details they may omit.

Source count is not source quality. Review coverage of the expert's practical
questions, primary authority, independent analysis, worked examples and known
failure cases. A large corpus can still miss the relevant manual section.
Current external access complements retained editions and versioned notes.
Verify quotations and interpretations, and show which material actually reached
the answering model. Search failure must not turn into confident recall.

### Dependability acceptance cases

Accumulated expertise carries an obligation to prepare, explain, and revise.
These planned acceptance cases apply across S0-S4, using the existing source
worlds, consultation traces, canonical history, and blinded review. They add no
execution or write authority and do not assert that the current surface passes.
Freeze new development fixtures separately from the existing S0 pilot; do not
change its cases or rubric after seeing answers.

| Case | Required behavior and retained evidence | Stage |
| --- | --- | --- |
| Consequential advice | Inspect the decision, relevant retained passages, dates and applicability, known disagreements, and gaps. Explain whether further research could materially change the answer and why; identify checks prevented by limits. Retain the preparation rationale, exact delivered context, omissions, and answer. | S1 |
| Contrary evidence | Advise on a bounded topic, then supply credible evidence that changes one assumption while leaving another conclusion supported. Explain what changes and why, what remains valid and why, and what is still uncertain. Retain both answers and source observations. After reviewed admission, link prior and revised positions to the prompting evidence, dates, rationale, and related conclusions needing reconsideration. Rebuild history without erasing the earlier view. | S1 temporary advice; S2-S3 durable revision |
| Misleading premise | Supply a question that invites a conclusion contradicted by the available evidence. Correct the premise respectfully, explain the evidential conflict, and give a supported reframing or state the limit. Do not build an elaborate answer on the false premise. Include a control with a sound premise to detect unwarranted dissent. | S1 and S3 |
| Attribution and situated disagreement | Supply sources with meaningful qualifications and different cultural or disciplinary perspectives. Distinguish observations, interpretations, hypotheses, and recommendations; attribute ideas accurately and preserve scope. Do not manufacture universal consensus, or give unsupported views equal weight merely because they disagree. Bind review to the actual passages delivered. | S1 and S3 |
| Continuity versus fresh preparation | Compare a maintained expert with a fresh baseline given sources relevant to the question and the preparation access promised by its frozen policy. Use matched models and answer limits, isolated inputs, and blinded review; report total resources separately. Test revision quality, premise correction, retained valid understanding, and uncertainty alongside decision usefulness. | S0 baseline; S4 held-out proof |

Review reasons and evidence, not required phrases or section headings. A change
of view is not automatically a success: the contrary evidence must warrant it.
Include weak or inapplicable contrary material as a control against reflexive
reversal. Calibrated uncertainty explains which claims are supported, which
depend on interpretation or assumptions, and which missing evidence matters.
Generic disclaimers, excessive abstention, and confident tone earn no credit.

An accountable human or calibrated model judges relevance, source meaning,
revision, dissent, and usefulness. Deterministic checks bind identities, hashes,
dates, snapshots, and admission boundaries; they cannot decide semantic quality.
Preserve failures and unreviewed cases. A passing fixture or a coherent change
summary does not establish longitudinal benefit. Report negative or inconclusive
comparisons with a fresh baseline without promoting a confidence or autonomy claim.

## Connected expert workflow, 2026-10-29

The expert is a persistent domain agent with identity, knowledge, temporal
history, a readable wiki, episodic experience, reusable methods, and an agent
loop. These components serve explanation, investigation, practical work,
revision, and later reuse. [Persistent expert agents](../design/persistent-expert-agent.md)
defines the contracts; [ROADMAP](../../ROADMAP.md#persistent-expert-agent-delivery)
contains the only active implementation checklist.

The release sequence below remains intact. Development should connect one
supervised workflow across its seams rather than perfect isolated fact-checking
steps before making an expert useful. S1 can expose read-only inquiry and
candidate methods; S2 supplies durable reconciliation; S3 supplies reviewed
method reuse and richer inquiry. A prototype spanning these concerns does not
promote any stage early. Frozen S0 cases, old failed trials, and S4 held-out
histories remain distinct. The existing offline-fixture exception still limits
what can run before live collection is admitted.

[ADR 0008](../decisions/0008-persistent-domain-agent-boundary.md) allows domain
episodes to persist across bounded invocations. Continuity is not additional
spend, tool, canonical-write, or external-action authority. General workflow
scheduling and arbitrary actions stay in a host. Personality expresses style
and working habits; it cannot overrule evidence or become a quality score.

An additional development comparison separates stored/pipeline behavior,
adaptive evidence use, and a fresh source-supplied model. Match model and
admitted tools, freeze resource ceilings and review before collection, and
report construction/maintenance overhead. This diagnoses a mechanism, not a
replacement S0 protocol or proof of S4 benefit. Use new cases to avoid tuning
only to the exposed local retry failure.

## Dependency order

The immediate creation repair connects the existing research, study, brief and
provenance primitives into a bounded default build, and generates a linked
Markdown view. The [formation design](../design/expert-formation.md) defines its
limits and recovery. It repairs an incomplete user flow without asserting that
graph connectivity qualifies an expert or that S0-S4 have passed.

`S0 baseline -> S1 prepared consultation -> S2 durable temporal learning ->
S3 perspective and inquiry -> S4 repeated-use proof -> S5 wider autonomy`

Baseline results may be negative. Recording them completes measurement, not
proof of value. Subject to the dated offline exception below, S1 prototypes
and fixtures proceed after the S0 protocol is frozen; the baseline must be
preserved before comparative claims. A poor
baseline does not block repairs to preparation. Failed stage acceptance keeps
that capability experimental. Wider autonomy requires positive held-out
evidence, rather than completion of every planned module.

The [2026-10-25 offline fixture amendment](../design/prepared-consultation-offline-fixtures.md)
permits isolated S1 support components and synthetic fixtures while capacity
qualification continues. This explicitly changes only that preparatory
sequencing. It does not satisfy S0, admit held-out collection, expose the
preparation entrypoint or permit live S1 calls before the original gate.

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
read-only source-copy verifier now checks exact independent files against a
selected world. Its [synthetic CLI validation](../validation/source-world-copies-2026-09-21.md)
does not replace archived run inputs, process confinement or reviewer bindings.
The four-arm, three-world pilot has 12 cases and 48 terminal cells, including
failures. The original missing inputs and the already collected replacement
diagnostic remain historical evidence. A new replacement baseline needs new
held-out inputs and prospective review; neither relabel the old answers nor
silently replace the historical protocol. Preserve development cases separately
from held-out cases; reviewers do not see arm identities until labels freeze.

**Exit evidence:** replayable inputs and outputs, failure denominators, binding
checks, reviewed per-case results, and explicit measured/unmeasured dimensions.
The workbook is an aggregator, not an arm executor or an automatic winner
selector. Human review may be unavailable; record that limit and keep the
value gate open. Do not manufacture attestations to finish a stage.

#### Next execution contract, reviewed 2026-10-22

This refines S0-S1 delivery, not the frozen historical experiments. The
[roadmap](../../ROADMAP.md#next-bounded-sequence-reviewed-2026-10-22)
owns order and active work. The
[research reassessment](../research/s0-s1-practice-2026-09-24.md#reassessment-2026-10-22)
explains the evidence behind these choices. No model run or GitHub setting
change is authorized by a planning status alone.

**Offline integrity increment, implemented in v2.50.45.** Existing summary,
assignment and label binding suffice for the mixed-outcome regression; no new
projection or evaluator was needed. New execution identities and typed drift
failures close the source/resume/worker boundary below. The following remains
the acceptance contract; replacement protocol and S1 work are still planned.
The rehearsal already retains answered, failed and blocked terminal cells,
maintenance fallback and unknown usage. Its strict workbook v1 cannot
represent a cell without an answer and semantic attestation. Keep that refusal;
do not fill missing answers with zero scores or weaken its schema. First
exercise the existing operational report and bound-review artifacts together
on a small mixed-outcome fixture. Add only the missing read-only projection
needed to show the scheduled denominator, reviewable subset, missing labels,
phase failures and usage unknowns in one dated report. Do not build a second
evaluator or count answered-only quality as end-to-end success.

The rehearsal's nine-file source identity omits current dependencies imported
by briefing, including selection, attribution, contracts and corpus support.
Extend the owning generation identity after tracing its actual callers;
include prompt/rendering dependencies and lock/runtime identity. Pin the
installed artifact used for collection as well. A changed dependency must
refuse resume before runtime probes, ledger writes or worker dispatch.
Historical runs retain their original recipe and an explicit compatibility
status, never a rewritten current pin. Regression evidence must mutate a
previously omitted dependency in an isolated fixture and prove refusal.

**Capacity development precedes the final freeze.** Use only new development
sources, never held-out cases or the old answer corpus, to measure realistic
study, briefing, maintenance and answer phases on the owned laptop. Run
sequentially without competing generation/test/archive loads. Record RAM,
context occupancy, model and daemon identity, output stop reason, elapsed time,
tokens and missing counters. A short warm-up measures startup capacity, not
maintenance feasibility. Preserve a failed phase rather than increasing its
limit inside a run. Freeze per-phase call/output/time limits and a total
attempt/time ceiling from this evidence before held-out collection. If a
shared policy limit suffices, keep it; introduce phase-specific fields only
when the measurements require them. The development trial also gets a finite
prospective manifest and stop rule; unlimited free retries are not an evaluation.

**Freeze a reviewable replacement baseline.** Before any held-out answer,
publish a timestamped protocol identity binding these items:

- Three new source worlds, 12 cases and four existing arm policies; original
  bytes, observation times, versions and permitted per-arm source inventories.
  Construction/maintenance receive no questions, rubric or later sources.
- Exact installed code/lock/model digest, generation settings, phase and total
  limits, no metered fallback and append-only attempt accounting. A model tag
  is not an identity. Failure, cancellation and ambiguous dispatch consume
  allowances; any resume follows the prospectively declared retry policy.
- Whole-answer usefulness and support, attribution, stale reuse, warranted
  correction, retention of still-valid guidance, premise handling, appropriate
  abstention and requested form as separate review dimensions. An obligation
  hit or a shorter answer cannot establish overall quality.
- A separate human-labeled reviewer calibration set, presentation-order checks,
  conflict/exposure disclosure, numeric agreement and escalation criteria, and
  a fixed policy for unresolved judgments. Independent model reviews are
  supplementary evidence, not evidence of human authorship or independent
  model-family errors. Reusing the answering model as judge is not an adequate
  independence claim. If only one usable local model exists, use human review
  for semantic acceptance rather than silently substituting that model.
- All 48 terminal outcomes in the report. Compare arms within the same case;
  report world/case-class strata, effect uncertainty, failed construction and
  maintenance overhead separately. Twelve cases are a pilot, not 48 independent
  examples or a broad expertise qualification. Do not choose thresholds after
  seeing which arm wins. Keep any wrong-memory diagnostic separate and bounded.

**2026-10-25 operator review amendment:** the operator explicitly selected
independent agent review instead of waiting for a human. For this replacement
pilot, freeze independent reviewers' labels before revealing the arm key.
Retain reviewer identity and exposure, presentation order, calibration inputs,
exact agreement, disagreements and unresolved judgments. Model-authored
calibration references are not human labels; interval agreement is not exact
agreement, and separate agents do not establish independent model-family
errors. Report model-reviewed pilot results with those limitations. Do not
record a human attestation, claim human-calibrated semantic acceptance or use
this amendment to qualify improved expertise or expand autonomous authority.
The earlier human-review and human-labeled calibration requirements above
remain the stronger acceptance lane, not a blocker on the operator-selected
pilot collection and model review.

Do not claim an anonymized packet makes an arm uninferable; record suspected
arm and reviewer exposure. Final protocol review is a concrete checkpoint after
the rubric, fixtures and bounds exist, not approval of an unspecified run. This
amendment does not freeze capacity limits or admit held-out collection; those
prospective gates remain. The existing private diagnostic key remains unopened.

**Next product increment: one opt-in S1 path.** Subject to the offline fixture
exception above, once the S0 protocol is frozen,
prototype one caller-scoped preparation packet through
`execute_consult_transaction`, using one explicit Python environment and one
official structured source class. Start with release-specific PyPI metadata
and index data for versions/yanks. Add OSV advisory evidence and interpreter
support data as separate increments; version metadata cannot certify advisory
coverage. Keep the acquired evidence temporary and retain the exact context
and source bytes supplied to the answer. Trace/lifecycle and operation receipts
are permitted writes; canonical profile, beliefs, corpus, graph and revision
history are unchanged. Do not run `sync --fresh-context` as a consult prelude.

Use one acquisition deadline and cumulative request/decoded-byte allowances,
including redirects, retries and DNS address attempts. No undeclared archive,
browser or general-search fallback. Public queries receive only admitted
package/version coordinates, never private task prose or a full lockfile.
Caller ownership, packet permissions, retention/cleanup and cross-caller reuse
must be defined before caching private context. See the
[preparation contract](../design/prepared-consultation.md).

S1 acceptance requires paired preparation-on/off review from the same expert
revision and matched question, model and answer limits. Acquisition and extra
reasoning are the treatment and are reported separately. Include advisory,
version/yank, conflicting-source and misleading/sound-premise cases, plus
unavailable sources, offline operation, cancellation, duplicate requests,
slow streaming, redirect/address exhaustion and denied cross-caller reuse.
Use synthetic transport and a small approved local semantic budget first;
only then perform a bounded public-source smoke. A live response or a sanitizer
canary pass does not prove safe, useful advice. Default-on promotion waits
for S1's own reviewed evidence; S0 need not show memory winning first.

**Stop and disposition.** Identity drift, unavailable mandatory evidence,
integrity failure, disclosed-key contamination, exhausted limits, unknown
dispatch state or material unresolved advice tradeoffs stop the affected run
or promotion. Retain the failed attempt and its dependent terminal outcomes.
Protocol or code repairs start a new bound trial; do not relabel old evidence.
S0 measurement may close with a negative result. S1 may remain opt-in. S4 alone
can establish the later repeated-use benefit claim. No paid-model key is needed
for the next work; local inference is $0 provider API cost, while hardware and
independent review resources remain separately reported.

### S1: prepare before consultation, with bounded temporary evidence

**Depends on:** a frozen S0 comparison contract, current capacity checks, and
the existing acquisition and consultation seams. Complete historical memory,
prediction resolution, new host integrations, and new providers are not
prerequisites.

Normal CLI and MCP query/consult should follow one shared service flow:

1. Establish the question, target environment, information date, and limits.
2. Inspect the stored perspective and identify assumptions needing a check.
   Consider decision stakes, relevant knowledge, source freshness, known
   disagreements, and gaps. Record whether further research could materially
   change the answer and why, rather than treating every question as requiring
   the same amount of retrieval.
   Retrieve the applicable original reference passages as well as the notes;
   allow a bounded follow-up lookup when a needed detail is absent. Use permitted
   computation or execution tools when the question warrants an empirical check,
   retaining inputs, environment, outputs and limits. Tool results are evidence
   to interpret, not a general correctness certificate.
3. Reuse a matching preparation packet or acquire permitted current sources.
4. Study relevant changes, unresolved conflicts, and implications for advice.
5. Freeze the expert revision plus admitted temporary evidence, then answer.
   Distinguish sourced observations, interpretations, hypotheses, and
   recommendations; preserve attribution and qualifications. Correct a
   misleading premise respectfully or explain why the requested conclusion
   is unsupported. Identify uncertainty that matters to the decision.

Reuse source packs, consult context, traces, and lifecycle records. Before
implementation, define the additive preparation contract: operation identity,
caller and authorization scope, expert revision, question scope,
environment/version constraints, source hashes
and observation times, checked and unchecked assumptions, reuse policy, limits,
attempts, stop reason, and context snapshot identity. Proposed field names and
commands are not a supported interface until they land.
The proposed contract is in [prepared consultation](../design/prepared-consultation.md).

The model chooses research direction and interprets relevance. Code enforces
the [source acquisition contract](../design/source-library-and-rendered-acquisition.md),
including a bounded rendered fallback only after its network and cleanup gates.
Code also enforces
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

**Show the check, not just a readiness label.** Every preparation result needs
a dated Markdown review and a machine-readable evidence projection bound to
the same operation and answer. Record source URLs and content hashes, actual
observation times, publication/revision dates where known, applicable versions,
checked assumptions, unchecked items, and material implications for guidance.
Link each material insight to its source observation and the relevant retained
finding or position. Include the exact delivered context and its omissions.
A current release number alone does not establish advisory coverage; a fixed
commit alone does not establish that an installed release contains the fix.

The review and graph projection must agree and be rebuildable from the frozen
packet. A changed recommendation needs a dated reason; an unchanged one needs
the evidence actually reviewed. No-change, failed check, and unexamined are
different results. This is a temporary evidence projection in S1, not a claim
that canonical temporal learning is complete. S2 admits reviewed changes and
preserves their history. A new Markdown timestamp or graph build time cannot
stand in for a substantive review.

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
Acceptance also checks that the Markdown, graph, source hashes, applicable
versions, and delivered answer context resolve to the same frozen evidence.
Deliberately mismatched dates, stale sources, missing links, and unsupported
"up to date" claims must fail the check.
Include details omitted from notes but present in full references, similar APIs
with different version behavior, unavailable source access and contradictory
references. In a separate controlled diagnostic, compare the same model with
recall only, notes only, full-reference retrieval and prepared source/tool access.
Keep the frozen S0 arms intact. Measure useful correct answers, citation
entailment, detail retrieval, omissions, elapsed time and total resources; do not
award success merely for searching or invoking a tool.

#### Python exemplar and profile acceptance

The current README example was a narrow repository code-quality expert. Its
claims about local test commands do not establish broad Python expertise.
Qualify a Python exemplar using retained research and reviewed consultations;
do not rename a narrow expert or inflate a score to imply broader coverage.

Use the existing retain, study, brief, and consult loop for this foundation
now. Basic understanding and reasoned positions must not wait for S3; S3
extends their cumulative synthesis and inquiry. A weak exemplar is a product
quality defect to investigate, not a screenshot selection problem. First build
and examine useful expertise, then capture it. The
[profile implementation design](../design/expert-perspective-profile.md)
exposes this existing understanding without claiming new preparation behavior.

The initial coverage map should include language/data-model semantics,
standard-library and runtime behavior, algorithms and complexity, concurrency,
typing/testing/packaging, performance and deployment, and security. Name limits
where research is missing. Retain applicable official documentation, release
notes, advisories, and independent technical analyses. Separate language
guarantees, empirical findings, community conventions, and reasoned opinions.
Explain when a recommendation applies, alternatives, and what could change it.
No fixed source count certifies that every best practice has been learned.

The knowledge graph and readable wiki should organize this understanding:
concepts, mechanisms, relationships, research, practical experience, and insights.
Temporal records preserve how that understanding changed and which versions it
applies to. They support the expert's judgment; neither a graph nor a wiki alone
demonstrates expertise. Connect positions back to this knowledge and let useful
questions lead to further investigation and learning.

Present guidance in a form suited to the specialty and the task. A Python expert
may need runnable examples, version constraints, design alternatives, complexity,
and a way to test the recommendation. Other specialties need different forms.
Preserve a common evidence and preparation record without forcing every expert
into the same answer template or substituting a confidence score for explanation.

Use held-out questions about choosing asynchronous I/O versus threads or
processes, algorithmic versus runtime bottlenecks, testing and packaging
tradeoffs, and where Python is or is not a good fit. Include version-specific
behavior and a relevant newly introduced security update. A source link alone
does not pass: the answer must explain the mechanism, constraints, and impact
on the caller's situation. Preparation must check relevant changes before
guidance, even when the underlying concept is familiar.

Freeze mandatory cases and unacceptable errors before examination. A critical
misconception, unsafe recommendation, fabricated current check, or inability to
answer a required foundational question leaves the affected scope unqualified.
Repair the underlying acquisition, study, retrieval, or reasoning failure and
use fresh questions to check transfer. Rephrasing the same examined answer is
development feedback, not another held-out success. Preserve every attempt.

The profile's primary view exposes existing perspective, useful questions
it can address, reasoned positions, research coverage and sources, unresolved
questions, and what changed. Deeper evidence and claim inspection remain
accessible. Missing perspective or coverage is shown explicitly; presentation
must not synthesize undocumented expertise merely to populate a screen.

Keep three signals separate: depth demonstrated by work and reviewed answers;
support and uncertainty of a particular position; and currency for a topic or
question. An age-decayed, trust-capped claim estimate is not a calibrated truth
probability or an overall expert grade. Expose its basis in claim inspection
instead of making an unexplained percentage the main expertise signal.
Last activity, last substantive study, and sources checked for this consultation
are distinct. Never show planned automatic preparation as already running.

**Screenshot gate:** use the actual built profile and retained expert state
after these checks, with code version and capture date in its validation record.
Show a substantive position and why it holds, useful coverage, and an honest
currency state. Do not use generated mock expertise, polished unreviewed answers,
or cosmetic score changes as evidence. A synthetic UI fixture is for behavior
testing and must not be published as a validated expert. Keep a real expert
example in the README once that qualification has been recorded; removing the
example alone does not satisfy this requirement.

### S2: preserve learning and select the applicable historical state

**Depends on:** S1 evidence and snapshot contracts. Reuse record identities,
position history, temporal primitives, and the existing admission boundary.
Close the [position-justification fidelity gap](../design/position-justification-and-explanation.md)
within this stage: reasoning, uncertainty, assumptions, counterevidence, and
revision signals must survive serialization and participate in version identity.
Historical position reads cannot claim complete perspective reconstruction
while those fields are lost.
An admitted revision must link prior and revised conclusions to the actual
evidence and observation dates prompting change, explain its rationale, and
identify earlier related guidance for reconsideration. Preserve what remains
valid and unresolved; a revision need not invalidate every earlier conclusion.
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

Separate evidential support, applicability, review priority, and demonstrated
competence. Elapsed time can make a version-specific recommendation due for
review without turning an established concept into a coin-flip claim. Changing
an applicability boundary or finding contrary evidence can justify revision;
refreshing a timestamp cannot. Replace the overloaded legacy estimate only
through a versioned migration and evaluation, preserving original values and
their interpretation. Do not fix it by raising floors or removing uncertainty.

Distinguish descriptive knowledge, conditional advice, preferences, hypotheses,
and resolvable predictions. A language definition is not a forecast with a
deadline, and an engineering tradeoff need not have an invented probability.
Use support and scope appropriate to the kind of judgment. Keep calibrated
forecasting measures for genuinely resolvable predictions.

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

Procedural candidates also require durable version identity, exact episode and
observation references, target-state checks, and rollback before admission.
This does not add skill execution authority. The temporal graph must distinguish
known-at reads from retrospective world-time reads and carry eligibility through
all dependencies and derived context; see the
[temporal query contract](../design/persistent-expert-agent.md#temporal-knowledge-graph-contract).

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

Review reusable methods alongside perspective: applicability, inputs, steps,
expected observations, counterexamples, known failures, and originating episode
references. Scoped reuse should improve the expert's actual investigation or
work product. A method can be read as guidance without executing arbitrary
code. Preserve method versions and retired variants through the owning
research-practice/skill seam; exported instructions remain derived. See
[procedural memory](../design/skills-as-learning-systems.md).

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
