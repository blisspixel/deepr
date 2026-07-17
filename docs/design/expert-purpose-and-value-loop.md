# Expert Purpose And Value Loop

Status: accepted; first local contract increment implemented, 2026-07-16.

## Goal

Make the purpose of an expert and the result of using it explicit, durable, and
reviewable.

The product loop is:

1. define what the expert is for;
2. define cases that would demonstrate useful behavior;
3. compile changing evidence into expert state;
4. consult that state for a real question or decision;
5. record the later observed outcome;
6. use held-out evidence to decide whether a future change helped.

Research is an input to this loop. Expert state is the reusable product. Better
repeated decisions are the desired outcome.

## Problem

Deepr already records beliefs, gaps, contradictions, provenance, temporal
edges, consult traces, loop runs, cost, and reviewed self-model proposals. It
does not yet give an expert one operator-accepted charter that says why the expert
exists and how usefulness will be tested. It also does not have a first-class,
append-only record for the result of a decision that used expert state.

Without those two ends of the loop, Deepr can prove that knowledge changed but
cannot prove that the change helped. More beliefs, newer sources, higher recall,
or a completed consult are not user outcomes.

The 2026 evidence reinforces this distinction:

- deep-research systems still fail many expert-consulting tasks even when their
  reports look complete;
- forgetting-aware memory evaluation penalizes reuse of obsolete state;
- experience-memory systems improve some agent tasks by learning from both
  success and failure;
- full-history persistence can introduce stale or irrelevant context;
- persistent memory creates a delayed poisoning surface.

Relevant sources include
[the expert-consulting benchmark](https://arxiv.org/abs/2605.17554),
[DR3-Eval](https://arxiv.org/abs/2604.14683),
[Memora](https://arxiv.org/abs/2604.20006),
[ReasoningBank](https://www.research.google/blog/reasoningbank-enabling-agents-to-learn-from-experience/),
and
[MPBench](https://arxiv.org/abs/2606.04329).

## Decision

Add an explicit preparation lane and two canonical artifact lanes:

1. `deepr-expert-blueprint-draft-v1` is explicitly unreviewed and
   non-authoritative.
2. `deepr-expert-blueprint-preflight-v1` proves only structural validity and
   packages a normalized hash, counts, and review questions at `$0`.
3. `deepr-expert-blueprint-v1` is a purpose and acceptance contract accepted
   through an operator attestation.
4. `deepr-expert-outcome-v1` is an operator-attested observation about a
   decision or consultation result.

The two canonical lanes are append-only JSONL under the expert directory. Every
record is a complete versioned snapshot or observation. A process crash cannot
replace a valid earlier record with a partial file.

The first increment is deliberately manual:

- blueprint templates are generated at `$0` with no model calls;
- a strict preflight normalizes and hashes a completed draft while stating that
  it is unreviewed, non-authoritative, and semantically unassessed;
- an operator may explicitly attest that scope and acceptance review occurred;
- outcome observations are recorded through the same operator-attestation
  boundary;
- Deepr does not verify reviewer identity or claim human authorship;
- no outcome changes beliefs, prompts, skills, routing, confidence, or policy;
- evaluation code may later summarize structural coverage, but it must not
  infer semantic success from labels or text.

## Blueprint Contract

A blueprint contains:

- expert name;
- mission;
- non-goals;
- decision use cases and their success criteria;
- source policy;
- domain volatility and update cadence;
- initial questions;
- held-out acceptance cases with success criteria and failure conditions;
- operator-attestation and revision metadata;
- an explicit authority contract.

The authority contract states that the blueprint is authoritative for scope and
evaluation intent, but cannot authorize spend, provider dispatch, knowledge
writes, external actions, or a semantic maturity verdict.

The operator flow is:

```text
deepr expert blueprint NAME --template --output blueprint.json
# edit blueprint.json
deepr expert blueprint NAME --from-file blueprint.json --output blueprint-preflight.json
# inspect the draft and preflight; only then attest that review is complete
deepr expert blueprint NAME --from-file blueprint.json --apply --attested-by OPERATOR
deepr expert make NAME --local
```

A blueprint may be prepared before the profile exists. `expert make` remains
backward compatible, but the README and next-step guidance place the blueprint
before research or synchronization.

### Storage

Canonical path:

```text
<expert>/blueprints/blueprints.jsonl
```

Each operator-attested revision includes a monotonically increasing revision number and
a SHA-256 hash over the semantic draft. Reapplying the same semantic draft is
idempotent and returns the existing latest revision. A changed charter appends a
new complete revision. Older revisions are never edited.

### Validation

Deterministic code owns only form:

- schema and kind;
- exact expert-name match;
- field types and bounded lengths;
- unique case identifiers;
- allowed volatility values;
- finite cadence range;
- attester presence and an explicit unverified-identity marker;
- canonical hashing, locking, and append behavior.

An accountable reviewer owns whether the mission, use cases, source policy,
and acceptance cases are good. Deepr records only an operator attestation and
does not verify that reviewer's identity or humanity. No lexical check or
structural preflight may conclude that the blueprint is meaningful, reviewed,
or complete.

## Outcome Contract

An outcome contains:

- stable outcome and decision identifiers;
- expert name and observation time;
- a concise decision summary;
- result label: `succeeded`, `mixed`, `failed`, or `unresolved`;
- operator-supplied observation text;
- optional consult trace, belief, and source references;
- outcome evidence references;
- attester label and attestation time;
- an explicit no-automatic-learning contract.

Canonical path:

```text
<expert>/outcomes/outcomes.jsonl
```

The result label is supplied through operator attestation. Deterministic code
validates the allowed value and artifact form but does not infer it from words,
metrics, or agreement, and it does not verify who supplied it. A repeated
explicit outcome id is idempotent only when the complete record matches;
conflicting reuse fails closed.

A correction must retain the same decision id and reference one earlier
observation. One observation can have only one direct correction, preventing an
ambiguous branch; a later correction references the latest observation in the
chain. Read-only summaries distinguish all observations from current outcomes
and count result labels for both without turning those counts into a quality
verdict.

## Longitudinal Evaluation Protocol

The blueprint and outcome lanes are prerequisites, not proof. The later
longitudinal harness should compare the same time-sliced tasks across:

1. fresh frontier deep research without persistent memory;
2. static retrieval or full-history context;
3. a compiled Deepr expert;
4. the same Deepr expert maintained with local or explicit plan capacity.

Use frozen source worlds with supportive evidence, distractors, and noise.
Report at least:

- decision or answer correctness;
- reuse of invalidated beliefs;
- source relevance and factual support as separate citation dimensions;
- appropriate abstention and uncertainty;
- update latency;
- retained correctness and negative transfer;
- reviewer minutes;
- construction, maintenance, retrieval, and generation cost;
- break-even consultation count;
- observed downstream outcome where one exists.

No single aggregate score may hide false-support rate, invalid-memory reuse, or
negative transfer. Model judges require human-anchored calibration before their
labels can affect defaults.

### First Harness Increment

The first harness is a `$0`, attestation-driven evaluator. It does not run any
of the four arms. Instead, it generates a blueprint-bound review workbook,
validates completed trials, and produces a descriptive report from
operator-attested labels and measured costs. This keeps provider execution and
semantic judgment outside the deterministic aggregation boundary.

The review workbook must bind to one exact blueprint revision and content hash.
It contains a linear sequence of at least two frozen source worlds, each with a
manifest reference and SHA-256 digest. Every blueprint acceptance case appears
exactly once and names its source world and evaluation role. Each case has
exactly one trial for each frozen arm:

1. `fresh_research`;
2. `static_history`;
3. `compiled_expert`;
4. `maintained_expert`.

Each trial binds the run and answer artifacts by reference and hash, records
retrieval and generation cost, response latency, and reviewer time, and carries
operator-attested scores for correctness, source relevance, factual support,
and uncertainty calibration. The semantic attestation also covers abstention,
invalidated-belief reuse, retained correctness, forward transfer, and negative
transfer where applicable. It explicitly records
`identity_verified: false` and `human_authorship_claimed: false`. An update
trial separately records whether the update completed, so a system that never
incorporated a change is not forced to invent a latency. The workbook binds the
randomized or non-randomized review-assignment manifest by reference and hash,
and has a protocol attestation that the same cases were used, source worlds
were frozen, arms were isolated, and artifact hashes were checked. Trial
execution, semantic attestation, and protocol attestation timestamps must occur
in that order.

The evaluator owns only structural checks and arithmetic. It rejects a stale
blueprint binding, missing or duplicate arm cells, a broken source-world chain,
non-finite measurements, or role-specific fields in the wrong case type. In
the default operator-attested mode it does not open artifact references. With
an explicit `--artifact-root`, it root-confines every relative file reference
and recomputes every declared SHA-256 digest before aggregation. Neither mode
calls a provider, inspects answer text, infers a score from language, or
verifies an attester identity or semantic label.

The report keeps the dimensions separate. For each arm it reports means and
counts, invalidated-belief reuse, negative transfer, expected-abstention match,
retention and forward-transfer labels, update latency, reviewer effort, fixed
cost, marginal consultation cost, and total observed cost. Pairwise deltas and
deterministic 95 percent paired-bootstrap intervals show case-level uncertainty
without emitting a superiority flag. Cost-only break-even estimates are also
descriptive. The report does not rank arms, select a winner, claim statistical
sufficiency, attribute an observed outcome causally, or change a default.

Rates use only applicable trials. Invalidated-belief reuse excludes source
worlds with no operator-attested invalidation, and negative transfer excludes
the initial world. Update reporting separates completion rate from latency
among completed updates so missing updates cannot disappear from the
denominator.

An intentionally incomplete template is valid scaffolding, not evidence. A
completed workbook must pass the published strict schema and runtime
cross-record validation before aggregation. Report writes require an explicit
output path; previews and aggregation are otherwise read-only.

## Agentic Boundary

This feature is a workflow envelope around externally supplied meaning.

Deterministic code owns schema, paths, bounds, revision numbers, hashes,
idempotency, locking, explicit artifact-verification mode, and writes. An
accountable reviewer owns purpose, success criteria, outcome interpretation,
and whether a future change improved the expert. The current artifact records
an operator attestation without proving who or what performed that review.
Models may later propose draft cases or lessons, but proposed content remains
unreviewed and cannot apply itself.

This adds no loop by itself. Automatic learning from outcomes remains gated
until a held-out evaluator, negative-transfer check, budget/capacity envelope,
durable run record, and typed stop condition all exist.

## Security And Authority

Blueprint and outcome text is untrusted when inserted into a model prompt. The
canonical artifacts are trusted only as operator-attested statements of intent
or observation, not as proof of human authorship, factual evidence, or
instructions with tool authority. Drafts and preflight artifacts have no scope
authority.

This increment does not solve origin laundering in persistent memory. A
separate architecture decision must define immutable write-time origin,
non-malleable authority, and source or claim-level entitlement propagation
before Deepr claims safe multi-user organizational memory.

Independent artifact verification accepts only caller-selected local files
beneath one resolved root. Absolute references, URIs, query or fragment syntax,
missing files, root or symlink escape, conflicting declared hashes, content
changes during hashing, and digest mismatches fail closed. Verification streams
files, performs no network request, and writes nothing. A generated report must
be outside that evidence root and cannot overwrite the input workbook. Byte
identity proves only the workbook binding, not that an artifact is truthful,
that an operator-attested score is correct, or that a human supplied it.

## Failure And Recovery

- External JSON is parsed completely before a canonical write starts.
- Cross-process file locks serialize revision and outcome appends.
- Records are appended durably with `fsync`.
- A malformed canonical record fails closed at the first invalid line without
  treating later records as trustworthy.
- Blueprint revisions are replayable complete snapshots.
- Outcomes are immutable observations. Corrections append a new outcome with a
  new id and `supersedes_outcome_id` referencing an earlier observation.

## Rollout

1. Prototype, implemented: local draft and preflight preparation, explicit
   operator attestation, no model calls, no identity-verification claim, and no
   automatic learning.
2. Shadow: attach blueprint and outcome references to evaluation reports without
   changing expert behavior.
3. Pilot: run one flagship expert through frozen longitudinal cases.
4. Limited production: permit measured outcome evidence to propose, but not
   apply, learning-policy changes.
5. Broader use: only after origin authority, entitlements, judge calibration,
   and negative-transfer gates pass.

## Alternatives Rejected

- Store the blueprint in `ExpertProfile`: rejected because purpose and
  acceptance cases have their own revision lifecycle and should not force a
  profile-schema migration.
- Generate the mission automatically from a domain name: rejected because
  semantic purpose belongs to the accountable operator and a generic template
  would create false precision.
- Treat consult-quality scores as outcomes: rejected because answer appearance
  and downstream usefulness are different measurements.
- Let outcomes directly update confidence or routing: rejected because one
  operator-attested observation is evidence for an eval case, not an
  authorization to change policy.
- Store only the latest blueprint JSON: rejected because silent replacement
  would erase why acceptance criteria changed.

## Verification

- Strict parsing rejects extra fields, empty required collections, invalid
  identifiers, and expert-name mismatches.
- Template and preflight generation perform no model or provider construction.
- Draft and preflight schemas explicitly deny review and scope authority.
- Same-content blueprint application is idempotent.
- Concurrent or successive changed applications produce ordered revisions.
- Outcome ids are append-only and conflicting reuse fails closed.
- All paths resolve under the configured canonical expert root.
- CLI preflight is read-only, cannot overwrite its draft, and writes only to an
  explicit separate output; `--apply` and `--attested-by` are explicit.
- Default expert-value aggregation labels artifact integrity as operator-attested
  and does not claim independent file reads.
- Explicit `--artifact-root` aggregation verifies every bound local artifact
  under a root-confined path policy before a report can be written, and report
  output cannot mutate the workbook or evidence root.
- Published schemas and the registry validate representative payloads.
- Unit tests run without API keys, `.env`, or outbound network access.
