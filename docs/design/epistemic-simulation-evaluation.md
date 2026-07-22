# Epistemic Simulation Evaluation

Status: Stage 0 contracts and zero-call structural evaluator implemented
2026-07-22. No graph context compiler, arm execution, semantic judge, lens
catalog, runtime integration, or public command is shipped.

## Purpose

This document defines how Deepr can tell whether an exceptional reasoning lens
is a real cognitive instrument rather than a memorable prompt. It is the
evidence gate for
[epistemic-simulation-experts.md](epistemic-simulation-experts.md).

The evaluator must answer five questions:

1. Does the method still help when the famous or exotic identity label is
   removed?
2. Does structured memory and TKG context add value beyond the same method in a
   prompt?
3. Does the lens reason inside changed assumptions instead of falling back to
   familiar real-world patterns?
4. Does it revise beliefs, preserve alternatives, and avoid invalidated memory
   as evidence changes?
5. Does multi-lens consultation improve decisions without factual
   contamination, conformity, hidden cost, or loss of dissent?

Style, confidence, agreement, and the volume of generated ideas are not success
criteria by themselves.

## Evaluation hypotheses

Every run binds to predeclared hypotheses. Post-hoc stories do not promote a
capability.

| Id | Hypothesis | Falsifying result |
|---|---|---|
| H1 | A sourced method pack improves blind decision utility over a generic expert | Named or anonymous method variants do not beat the generic baseline |
| H2 | Lane-aware TKG compilation improves useful use of expert state over the current bounded memory packet | The compiled arm adds context or cost without a reviewed quality gain |
| H3 | Branch-scoped lenses adapt to changed rules and incentives | Answers remain anchored to default-world associations after a material assumption change |
| H4 | Belief-delta memory improves revision under partial observability | The lens collapses alternatives early, ignores new evidence, or reuses invalidated memory |
| H5 | Designed information diversity improves a multi-lens result | The panel herds, loses minority evidence, or performs no better than matched union-context synthesis |
| H6 | Prospective memory improves later retrieval and prediction discipline | Candidate implications are not retrieved when relevant or leak into answers as observed fact |
| H7 | Outcomes improve calibration without corrupting factual authority | Outcome records cause unsupported factual promotion, overfitting, or negative transfer |

## Unit of analysis: the insight record

Do not grade only the final prose. Each material recommendation, hypothesis,
forecast, or interpretation should be represented as a
`deepr-insight-record-v1` candidate containing:

- stable insight and run ids;
- insight type: factual conclusion, interpretation, hypothesis, forecast,
  counterfactual implication, recommendation, or proposed test;
- exact factual subclaims and evidence-unit refs;
- branch id and assumption refs;
- reasoning-method tags from the method pack;
- alternatives considered;
- expected observations and disconfirmers;
- evidence confidence, conditional confidence, and calibration scope;
- novelty status, default `unassessed`;
- decision implication;
- source perspective and anonymous adjudication id; and
- review and outcome refs.

The record is an evaluation artifact, not canonical memory. It makes insight
quality inspectable without storing private chain-of-thought.

## Frozen case bundle

Each `deepr-epistemic-simulation-case-v1` fixture freezes:

- case id, task class, domain, and risk class;
- question, requested decision or output, time horizon, and success criteria;
- shared factual evidence units;
- access-controlled evidence manifest and redaction policy when applicable;
- lens method pack and world-model branch;
- hidden outcome or reference answer when one exists;
- known alternatives, null hypothesis, and decision-relevant cruxes;
- paired-case relation and the one intended intervention;
- allowed context, output, calls, time, disk, and cost;
- model, prompt, compiler, schema, and expert snapshot versions; and
- reviewer rubric and predeclared promotion thresholds.

Cases must be content-addressed. A changed question, assumption, evidence unit,
method pack, hidden outcome, or rubric creates a new case hash.

The Stage 0 case hash commits to the complete linked case, lens, context,
five-arm declaration, review contract, and methodology version. Lens and
context manifests are separately hashed, and each report result names the
exact lens and context whose hashes it carries. This prevents a valid digest
from being reassigned to the wrong case result.

## Primary comparison

Use the same cases, backend class, total eligible expert state, and aggregate
resource ceiling across five arms:

1. `generic`: one generic domain expert with shared evidence.
2. `style_only`: an evocative identity and voice description without durable
   expert memory or graph context.
3. `current_memory`: the current bounded stored-belief and perspective packet.
4. `compiled_lens`: one method pack with lane-aware, branch-scoped graph
   context.
5. `blinded_multi_lens`: independent compiled lenses with designed information
   differences, anonymous evidence-contract exchange, and dissent-preserving
   synthesis.

Stage 0 freezes only these arm declarations and their matched resource
envelope. Every arm explicitly has `input_artifact_status=not_supplied`,
`execution_status=not_executed`, and `semantic_review_status=not_supplied`.
`declared_lens_count=3` describes the future multi-lens ablation shape; the
fixture does not contain three bound lens inputs, generated outputs, or a live
comparison. Any claim that Stage 0 compared answer quality would therefore be
false. Executed, hash-bound arm artifacts first enter at delivery step 5.

The primary analysis compares arms 1 through 5. Identity and method ablations
run as paired variants inside the relevant arms:

- named label plus method pack;
- anonymous method pack;
- named label with method operations removed; and
- anonymous generic control with matched length.

If the named variant improves while the anonymous method pack does not, report
an identity-cue effect. Do not claim a superior expert.

## Test batteries

### 1. Identity and recognition ablation

Use one familiar historical name, one invented but plausible name, and one
anonymous method id over the same method pack. Counterbalance label and answer
order. Grade method use, factual integrity, consistency, and utility.

This addresses evidence that famous character names can expose latent training
cues and inflate apparent role performance
([SIGDIAL 2026](https://aclanthology.org/2026.sigdial-1.15/)).

### 2. Counterfactual transfer

Construct paired cases that change one decision-relevant rule, payoff,
resource constraint, time scale, sensory capability, or causal relation while
holding surface wording as stable as possible. Record:

- the exact intervention;
- what should remain invariant;
- which conclusion should change if the intervention is understood; and
- which familiar default answer becomes wrong.

Measure conditional consistency and incentive sensitivity, not agreement with
the default-world answer. Current counterfactual studies show substantial
degradation when familiar labels or payoff structures are changed
([arXiv:2603.19167, 2026-03-19](https://arxiv.org/abs/2603.19167)).

Stage 0 enforces a narrower structural precursor: the two worlds form a direct
parent-child fork, each world has exactly one structured condition record, that
record is its only branch assumption, carries the declared value, and appears
in context; world manifests must cover every current branch assumption. Only
the condition record and direct counterfactual implications that depend on it
are normalized across the pair. Every other rendered record must have the same
canonical hash. The paired cases and contexts also match framing, record and
edge time, exact evidence identity and content hash, path topology, snapshots,
bounds, and arm resources. This prevents an unrelated branch or obvious
fixture confound from passing. It does not prove that the declared condition
is semantically sufficient or that generated answers adapt correctly. Blinded
reviewers own those later judgments.

### 3. Progressive information disclosure

Run the same problem at four frozen disclosure levels:

1. question and constraints only;
2. shared background evidence;
3. methods, observations, and competing hypotheses; and
4. outcome-bearing evidence with the final outcome still hidden.

Track whether early outputs are meaningfully diverse and testable, whether
later outputs become better grounded, and whether the model revises instead of
retroactively claiming it always knew the answer. Do not use similarity to the
hidden answer as a complete novelty metric. ProjectionBench provides current
evidence for progressive disclosure as a discovery-evaluation pattern
([arXiv:2605.30284, 2026-05-28](https://arxiv.org/abs/2605.30284)).

### 4. Alternative-hypothesis portfolio

Supply incomplete observations for which several explanations remain viable.
Require:

- at least one serious alternative to the leading hypothesis;
- a null or no-effect hypothesis when meaningful;
- evidence for and against each candidate;
- the next observation with highest discriminating value; and
- abstention when the evidence cannot distinguish candidates.

Grade the portfolio, not only the chosen winner. Recent controlled work finds
that models evaluate hypotheses better than they generate them and often favor
overly simple rules that fail outside observed examples
([arXiv:2605.05851, 2026-05-07](https://arxiv.org/abs/2605.05851)).

### 5. Belief revision and invalidated memory

Present observations in a controlled sequence. Freeze the prior candidate set,
then add supporting, conflicting, superseding, and irrelevant evidence. The
lens must preserve an auditable prior-to-posterior delta, explain which
evidence caused the change, and avoid retrieving superseded state as current.

Test both under-revision and over-revision. A coherent lens should not resist
decisive evidence, but it should not abandon a well-supported belief because a
single low-trust observation appeared.

### 6. Partial observability and calibrated alternatives

Hide a decision-relevant variable and vary observation reliability. Require
multiple candidate conclusions to remain visible. Numeric probabilities are
graded only when the candidate set is explicitly exhaustive and the model or
aggregation method has calibration evidence. Otherwise use ordered or interval
assessments with provenance.

BeliefMem and predictive-world-memory research support retaining alternative
beliefs and logging revisions, but both remain recent research rather than a
reason to treat raw model confidence as calibrated probability
([BeliefMem, 2026-05-07](https://arxiv.org/abs/2605.05583),
[Nous, revised 2026-07-16](https://arxiv.org/abs/2606.22030)).

### 7. Evidence contract and private evidence

Every factual subclaim must bind to an exact evidence unit. Deterministic
validation may confirm ids, hashes, access scope, quotation spans, and whether
the cited unit was available to the participant. For factual graph edges,
linked evidence must reciprocally name the edge and collectively bind both
record endpoints. Access validation compares the packet consumer with an
expected principal supplied by the authenticated caller boundary; the packet
cannot authenticate itself. Semantic support remains a reviewer or
calibrated-model judgment.

Include cases where:

- one source is private but reviewable by an authorized evaluator;
- the downstream synthesizer sees only a redacted evidence description;
- a source is withheld and cannot be independently audited;
- two sources repeat one upstream origin; and
- an internal lens transcript asserts the claim without external evidence.

The Stage 0 `access_controlled_evidence` witness must cite at least one unit
whose visibility is `access_controlled`; permanently withheld material cannot
satisfy that family merely because the fixture consumer cannot inspect it.

The answer must disclose auditability without leaking protected content.
GAVEL's evidence-contract results support atomic evidence binding and
mechanized citation scrutiny
([ACL Findings 2026](https://aclanthology.org/2026.findings-acl.1789/)). W3C
PROV supplies interoperable provenance concepts, not a truth verdict
([W3C PROV Overview](https://www.w3.org/TR/prov-overview/)).

### 8. Prospective memory

At time T1, store candidate situations, expected observations, and expiry
conditions derived from a belief or hypothesis. At T2, ask an indirectly
related question. Grade whether the relevant candidate is retrieved, whether
its assumptions survive, and whether the answer clearly distinguishes prior
prediction from later observation.

Adversarial cases should include a plausible prospective implication that did
not occur. Retrieval is useful; presenting it as history is a hard failure.

### 9. Designed diversity and consensus resistance

Give each lens shared evidence plus a distinct private evidence unit, method,
or assumption. Require independent answers before exchange. During exchange,
hide famous labels and bind factual challenges to evidence units.

Grade whether unique evidence reaches synthesis, whether confidence changes
track evidence rather than status, and whether a correct minority survives.
Homogeneous debate and uniform updates may not improve expected correctness,
while diversity and calibrated confidence can help
([ACL Findings 2026](https://aclanthology.org/2026.findings-acl.1694/)).
Consensus-free debate research also supports retaining dissent rather than
forcing majority agreement
([ACL Findings 2026](https://aclanthology.org/2026.findings-acl.1600/)).

### 10. Longitudinal outcome loop

For resolvable forecasts, record the event definition, horizon, probability or
interval, evidence-confidence assessment, and later outcome. Use a proper
score such as Brier score only when the event and probability were validly
specified before resolution.

For recommendations without a clean event outcome, use operator-attested
decision usefulness, observed side effects, and verification results. Outcome
records may update task-scoped calibration and method utility. They cannot
promote the original rationale into factual truth.

### 11. Negative transfer

Run ordinary factual consult cases before and after enabling the compiler or
learning policy. The lens must not become more verbose, speculative,
anthropomorphic, stale, or citation-poor on tasks that do not benefit from
simulation. A feature that improves imaginative cases while degrading normal
expert consultation does not become a default.

## Context compiler evaluation

Evaluate retrieval separately from answer quality. For reviewer-labeled graph
fixtures, report:

- evidence-root recall;
- useful-path recall;
- irrelevant-context rate;
- contradiction and disconfirmer inclusion;
- alternative-hypothesis inclusion;
- temporal-state accuracy;
- invalidated-memory leakage;
- branch and assumption leakage;
- access-policy violations;
- context bytes and position of each item; and
- stable output metadata for identical frozen inputs.

These are diagnostics. A path's presence does not prove that it is semantically
relevant, and absence from a small label set does not prove irrelevance.

## Semantic review

Reviewers score anonymized insight records and final outputs on:

- decision utility;
- factual integrity;
- conditional consistency;
- evidence and assumption separation;
- alternative quality;
- testability and disconfirmability;
- revision quality;
- dissent preservation;
- temporal integrity;
- calibration discipline;
- novelty contribution, explicitly not novelty certification; and
- safety, disclosure, and non-impersonation.

Reviewer identity, expertise claim, conflicts, rubric version, answer order,
and review time are recorded. Deepr records these as attestations and does not
prove reviewer identity.

Model judging remains provisional until it reaches a predeclared agreement
floor against human labels and passes answer-order, identity-label,
verbosity, and provider-family checks. A model judge never certifies novelty or
historical fidelity.

## Measures and promotion rules

### Hard invariants

The following require zero violations in the acceptance corpus:

- hidden simulation mode or dropped disclosure;
- historical, alien, interdimensional, or future-observer identity claim;
- invented memory or fabricated quotation;
- simulation-to-factual write operation;
- branch id or authority-lane loss;
- protected evidence disclosure outside its access policy;
- prospective implication presented as an observation;
- unledgered call or spend; and
- non-replayable frozen-input metadata.

### Comparative gates

Before running the acceptance set, declare:

- the minimum practically useful gain over the generic and current-memory
  baselines;
- the maximum permitted factual-integrity regression;
- context, call, latency, and cost ceilings;
- reviewer agreement requirements;
- case exclusions and missing-data policy; and
- the confidence interval or uncertainty reporting method.

Use pilot cases only to estimate variance and fix the rubric. Do not tune on the
held-out acceptance cases. Promotion requires:

1. the anonymous method pack retains a meaningful share of the named variant's
   utility;
2. the compiled lens improves expert-state use and decision utility over the
   current-memory arm;
3. factual integrity is non-inferior to the generic baseline;
4. paired counterfactual sensitivity improves without default-world
   regression;
5. invalidated-memory and branch-leakage rates do not regress;
6. multi-lens synthesis preserves unique and minority evidence; and
7. resource use remains within the predeclared envelope.

If only the named label helps, stop and report an identity-cue effect. If more
memory increases confident error, stop and repair authority or retrieval. If
multi-lens consultation adds cost without unique evidence or better decisions,
keep the single-lens path.

## Versioned report

The Stage 0 `deepr-epistemic-simulation-eval-v1` report includes frozen
fixture, case, lens, and context hashes; exact arm declarations; covered case
families; structural validation results; zero-authority metadata; and an
explicit `accountable_review_required` acceptance state with no winner. It
contains no fabricated arm input, output, comparison, or score. Its schema
revalidates exact arm shapes, one-to-one case-result hashes, lens and context
hash bindings, structural totals, semantic status, and a timezone-bearing
generation timestamp. The linked report validator additionally requires the
frozen source bundle and recomputes the complete report, so a syntactically
valid replacement fixture digest is rejected.

A later executed report must additionally include:

- corpus, case, arm, variant, and run hashes;
- frozen backend, model, prompt, compiler, lens, and expert snapshots;
- context, calls, tokens, time, disk, capacity source, and ledgered cost;
- structural invariant results;
- compiler diagnostics;
- anonymized insight records;
- human and provisional model reviews;
- paired-case deltas;
- outcome scores when available;
- uncertainty and missing data;
- acceptance decision supplied by an accountable reviewer; and
- explicit `changes_runtime_default=false` and `writes_expert_state=false`.

The evaluator aggregates supplied observations. It does not infer that a lens
is exceptional from a weighted score or mark a product default automatically.

## Delivery order

1. Completed 2026-07-22: freeze this protocol and the proposed
   memory-authority ADR.
2. Completed 2026-07-22: add synthetic lane, branch, evidence, and paired-case
   fixtures.
3. Completed 2026-07-22: add pure schema and structural validators with no
   model or network calls.
4. Add a read-only context compiler over synthetic fixtures.
5. Compare generic, style-only, current-memory, compiled-lens, and blinded
   multi-lens artifacts using reviewer-supplied outputs.
6. Admit explicit local runs only after replay and bounds pass.
7. Run the Leonardo-informed and five-years-forward pilots under blinded
   identity and counterfactual tests.
8. Stage perspective learning only after negative-transfer and outcome gates.
9. Wait for ExpertEventV2 replay equality before authoritative longitudinal
   branch memory.

## Implementation seams

The Stage 0 implementation uses these coherent seams:

- `src/deepr/experts/epistemic_simulation_contract.py`: pure schemas and
  linked authority invariants;
- `src/deepr/experts/epistemic_simulation_context.py`: linked context access,
  provenance, branch, connectivity, and canonical-byte validation;
- `src/deepr/evals/epistemic_simulation_pairing.py`: matched-world structural
  fingerprints and the narrow intervention normalization boundary;
- `src/deepr/evals/epistemic_simulation.py`: frozen declarations for five
  future arms and structural aggregation;
- fixture files under `tests/data/epistemic_simulation/`; and
- published contracts under `docs/schemas/` with focused contract, evaluator,
  schema, and contamination tests.

The proposed Phase 1 `consult_context_compiler.py` seam would construct
read-only graph packets. Stage 0 validates frozen context packets but does not
select paths from live expert state.

Do not add these merely to split a large file. Before source work, rebuild the
code graph and confirm each seam has independent invariants and tests. The
first change should contain contracts, validators, and fixtures only. It should
not add a public command, model call, lens catalog, or memory write.
