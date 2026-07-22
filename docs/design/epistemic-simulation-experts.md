# Epistemic Simulation Experts

Status: Stage 0 contract and frozen structural evaluation implemented
2026-07-22. No graph compiler, live lens execution, named lens catalog,
persistent learning, or public command is shipped.

## Decision

Deepr should support exceptional reasoning lenses, but it should not present a
model as Leonardo da Vinci, an alien, an interdimensional being, or a person
with privileged knowledge of the future. The product should expose disclosed,
inspectable epistemic simulations whose value comes from coherent assumptions,
durable memory, graph reasoning, and deliberately different information.

The user-facing forms can include:

- a Leonardo-informed historical perspective;
- a five-years-forward scenario analyst;
- a nonhuman cognition lens;
- a higher-dimensional systems lens; and
- a domain expert working from a deliberately contrarian hypothesis set.

These are reasoning instruments, not identity, consciousness, recovered
memory, prediction authority, or evidence about beings that Deepr cannot
verify.

The standard is stronger than role consistency. A lens is valuable only when
its useful behavior survives removal of its famous name, adapts when its world
assumptions change, retains alternatives under uncertainty, and produces
better tests, decisions, or forecasts than a generic expert under matched
resources. A memorable voice without those properties is packaging, not
expertise.

## What makes a lens exceptional

Each lens should be built from four independently inspectable parts:

1. `method_pack`: reasoning operations the lens is expected to use, with
   provenance when they are attributed to a historical subject.
2. `world_models`: explicit entities, constraints, causal expectations,
   uncertainty, time anchor, and branch-local assumptions.
3. `memory_policy`: what the lens notices, preserves, revises, predicts,
   tests, and deliberately forgets.
4. `evaluation_profile`: cases on which its method is useful, failure cases,
   calibration evidence, and outcome history.

Examples should be defined by cognitive operations rather than costume:

- A Leonardo-informed lens could emphasize close observation, decomposition,
  diagrammatic models, mechanism transfer across fields, and cheap experiments.
  Historical attribution still requires source support.
- A five-years-forward lens should forecast from named assumptions, maturity
  curves, adoption constraints, second-order effects, and backcasts. It has no
  future observations.
- A nonhuman lens can vary sensory access, time scale, objective function,
  embodiment, communication bandwidth, or resource constraints. It must not
  claim alien origin.
- A higher-dimensional lens can reason through projections, invariants,
  topology, hidden variables, and lower-dimensional observations. It must not
  claim interdimensional perception.

The same method pack can be tested with and without its evocative label. If the
named version wins but the anonymous method version does not, Deepr has likely
measured recognition, style, or authority bias rather than a better cognitive
instrument.

## Why the current consult surface is not enough

Current `consult` is a safe stored-context baseline. It does not fully harness
the expert memory and temporal knowledge graph:

- belief selection is a bounded lexical-overlap route followed by confidence;
- each expert contributes at most eight beliefs and three source references per
  belief;
- the packet adds at most three original ideas but does not carry the expert's
  hypotheses, concepts, stances, failed ideas, episodic outcomes, graph paths,
  temporal belief-change trajectory, or counterfactual assumptions;
- synthesis sees a clipped slice of each perspective and a bounded aggregate
  prompt; and
- one-shot consult intentionally performs no new expert-generation or peer
  reasoning calls.

Local evidence-first investigation is a better execution substrate because it
already freezes inputs, separates independent drafts from a blinded exchange,
checks the result, bounds every resource, and stages factual and non-factual
learning. Deepr now has an experimental first-class simulation data contract
and a synthetic branch-scoped fixture. The consult runtime still lacks
branch-scoped memory and a graph-aware context compiler.

The product opportunity is therefore not a larger persona prompt. It is a
memory and reasoning architecture that can preserve useful conjecture without
letting conjecture masquerade as external fact.

## Product contract

The experimental `deepr-epistemic-simulation-v1` contract includes:

- `representation_mode=epistemic_simulation`;
- a stable `lens_id`, display label, purpose, and persistent simulation
  disclosure;
- one or more world models with a unique `world_model_id` and immutable
  `branch_id` for every counterfactual state;
- a time anchor, explicit assumptions, invariants, exclusions, and known
  failure modes;
- provenance for user-supplied, source-derived, model-proposed, and
  reviewer-accepted state;
- allowed memory lanes, read scope, write policy, tool scope, and spend ceiling;
- parent branch, fork reason, and merge or retirement status;
- model, prompt, schema, expert-snapshot, and context-compiler versions for
  replay; and
- separately labeled evidence, conditional-confidence, utility, and review
  fields.

The disclosure must survive every render, export, conversation turn, and
handoff. A lens must say that it is a constructed simulation. It must not claim
first-person memories, private access to a historical subject, alien origin,
interdimensional perception, future observation, or certainty derived only
from its framing.

## Memory authority lanes

One undifferentiated memory store would turn imaginative output into synthetic
evidence. Every record needs one authority lane:

1. `factual`: claims about the external world with a provenance root, time,
   trust, and verification state. Evidence may be public or access-controlled.
   This is the only lane that can become canonical factual belief.
2. `perspective`: interpretations, concepts, stances, original ideas,
   hypotheses, tradeoffs, and disconfirming signals. Lack of web evidence is
   not refutation, but this lane is never advertised as verified fact.
3. `simulation`: branch-local assumptions, counterfactual state, inferred
   consequences, scenario time, and internal contradictions. A simulation
   cannot silently mutate the factual lane.
4. `episodic`: what a lens read, attempted, predicted, recommended, and later
   observed. A transcript or repeated assertion is not evidence of external
   truth.
5. `governance`: disclosure, purpose, authority, safety policy, tool and spend
   limits, review history, and allowed learning transitions.

These lanes align with the proposed ExpertEventV2 direction. The first
read-only compiler can run over current stores, but persistent branch-local
episodic memory should not become authoritative until bitemporal event replay
and lane-preserving projections are proven.

## Evidence beyond the public web

Deepr must not treat public searchability as the definition of truth. A fact
may be grounded in a user-approved private document, an institutional archive,
a local experiment, a tool or sensor observation, accountable testimony, a
formal derivation, or a later outcome. Each evidence root should preserve:

- evidence class and original creator or observer;
- chain of custody, content hash, observation time, and valid time;
- access policy and whether a downstream consumer can inspect it;
- independence from other evidence roots;
- reproduction or corroboration status;
- known conflicts, transformations, and expiry conditions; and
- the exact claim for which it was offered.

An access-controlled source can support a factual belief without being exposed
to every consultant, but the answer must disclose that the source is private
and whether the current consumer can audit it. A model-generated memory, lens
transcript, or internal consensus is never an independent evidence root.

`Unverifiable` is too coarse. The system should distinguish at least:

- `not_publicly_verifiable`;
- `source_withheld`;
- `not_yet_tested`;
- `lost_source`;
- `contested_observation`; and
- `in_principle_untestable`.

These statuses do not determine truth. They preserve why ordinary verification
did not close the question. A lens can still derive a useful conditional
insight from such a claim, but it must carry the claim's status and show which
conclusion would fail if the premise is wrong.

## Cognitive architecture

The durable design is an evidence-anchored belief system, not a larger prompt
or a single vector store.

| Layer | Durable content | Authority |
|---|---|---|
| Evidence ledger | Public and access-controlled source units, observations, experiments, attestations, hashes, custody, and access policy | Evidence about the external world, subject to trust and verification status |
| Event ledger | Immutable observations, proposals, revisions, retractions, outcomes, and causal parents | History of what entered or changed, not a semantic truth verdict |
| Belief state | Competing conclusions, confidence assessments, contradictions, temporal validity, and prior-to-posterior deltas | Current factual or conditional view, always linked to evidence or assumptions |
| Hypothesis portfolio | Alternative explanations, null hypotheses, expected observations, disconfirmers, and open tests | Perspective state, not verified fact |
| Branch world model | Counterfactual assumptions, constraints, scenario time, simulated entities, and branch-local implications | Conditional simulation only |
| Prospective index | Candidate future consequences and situations in which a memory may matter | Retrieval aid marked `candidate_only`, never a prediction verdict |
| Episodic outcome memory | Decisions, actions, predictions, observed results, failures, and lessons | Experience evidence for task-scoped evaluation, not automatic factual promotion |
| Context compiler | A frozen, task-shaped graph packet with evidence, alternatives, assumptions, deltas, and disconfirmers | Read-only candidate context |
| Deliberation and synthesis | Independent analyses, anonymous challenge, revisions, dissent, and tests | Proposed interpretation, no memory-write authority |

The event and evidence ledgers remain canonical. Probabilistic belief state,
prospective implications, indexes, summaries, and consult packets are
rebuildable projections until a future authority migration proves replay
equality.

### Belief deltas, not confidence overwrites

For every meaningful revision, preserve:

- the prior alternatives and their assessments;
- the new observation or evidence reference;
- the proposed update method and its provenance;
- the posterior alternatives and assessments;
- what became more or less plausible and why;
- the branch and time scope; and
- whether calibration supports interpreting the numeric values as
  probabilities.

Model-produced confidence is not automatically a probability. Deepr should
retain multiple candidate conclusions under partial observability, but it
should not force an open-ended hypothesis set into a normalized distribution
unless the alternatives are explicitly exhaustive and the update rule is
validated. Numeric precision without calibration is an assessment artifact,
not epistemic authority.

### Prospective memory without fabricated foresight

At write time, a lens may propose situations in which a memory could matter or
conditional consequences that may follow. These records improve future recall
only when they retain:

- the originating belief or hypothesis;
- the complete assumption set;
- an expected observation and time horizon;
- a disconfirming observation;
- `candidate_only` routing authority; and
- an expiry or review condition.

Prospective indexing is useful because exceptional insight often connects a
past observation to a future situation. It is dangerous when a generated
implication is later retrieved as if it had been observed. The authority label
must therefore survive every projection and consult packet.

## Temporal knowledge graph semantics

The graph must preserve the difference between evidence and inference. Existing
factual relations such as `supports`, `contradicts`, `enables`, and
`derived_from` remain source-governed. Simulation-aware relations should add:

- `assumes`;
- `implies_within`;
- `analogizes_to`;
- `predicts`;
- `tested_by`;
- `disconfirmed_by`;
- `inspired_by`; and
- `forked_from`.

Every simulation edge carries its branch and scenario time. A simulation node
may inspire a factual research question, but it cannot `support` a factual
claim. Cross-lane promotion requires a new external evidence path and the
normal verifier-gated graph commit. A branch merge never means that its claims
became true.

Confidence must be a vector, not one misleading scalar:

- `evidence_confidence` for source-backed factual state;
- `conditional_confidence` given a named assumption set;
- `coherence_assessment` with evaluator and review status;
- `utility_assessment` for a named task and outcome;
- `novelty_status`, defaulting to `unassessed`; and
- `calibration_scope`, including the cases and time horizon on which a score
  was measured.

Deterministic code validates the fields and transitions. A calibrated model or
qualified reviewer judges coherence, usefulness, similarity, contradiction,
and whether an insight follows from the stated assumptions.

## Graph-aware consult context compiler

A future `deepr-consult-context-v2` compiler should build a task-shaped graph
packet rather than rank isolated text snippets. It should remain read-only and
return candidate context, never semantic truth.

For each selected lens, the compiler should preserve:

- relevant factual claims and their evidence roots;
- the shortest useful support and contradiction paths;
- temporal validity and meaningful belief revisions;
- active hypotheses, concepts, stances, and original ideas;
- branch assumptions and scenario time;
- relevant failed attempts, outcome observations, and disconfirming signals;
- open gaps and what would change the lens's conclusion;
- the expert snapshot and compiler versions; and
- a Why this lens explanation for every included path.

Context allocation should reserve small minimums for shared factual ground,
dissent, assumptions, and disconfirmers, then use a calibrated planner to choose
the remaining semantic content. Lexical or vector retrieval may route
candidates but cannot decide relevance or truth.

## Deliberation protocol

The high-value protocol is structured divergence followed by evidence-aware
convergence:

1. Freeze the question, factual evidence base, lens snapshots, branch ids,
   budgets, and compiler version.
2. Give all lenses shared factual ground, then give each lens a deliberately
   different assumption set, private evidence slice, or method packet.
3. Generate independent analyses before any peer content is visible.
4. Exchange anonymized claims, assumptions, and disconfirmers so reputation or
   a famous name does not determine weight.
5. Let each lens revise, retain dissent, or state what evidence would change
   its view.
6. Run an independent checker against factual claims, citation bindings,
   assumption leakage, and branch integrity.
7. Synthesize shared ground, branch-local insight, unresolved dissent, and
   testable next actions without flattening them into false consensus.

The final answer should expose:

1. Verified shared ground.
2. Lens-specific analysis.
3. Clearly labeled speculative insights.
4. Assumptions and branch ids.
5. Agreements and unresolved dissent.
6. Tests, observations, or research that could discriminate among ideas.
7. Uncertainty, provenance, and the persistent simulation disclosure.

Named lenses may be restored for the user-facing explanation after blinded
adjudication. The adjudicator should not know that one candidate was labeled
Leonardo or future genius while weighing its content.

## Learning rules

- A consultation transcript never becomes evidence merely because several
  lenses repeated it.
- Factual claims follow the current source-backed verifier and graph-commit
  path.
- Perspective and simulation insights use explicit staged envelopes and apply
  gates. Admission records provenance and review; it does not prove truth or
  novelty.
- Every prediction names a time horizon, expected observation, disconfirming
  observation, and branch.
- Outcome observations may update task-scoped utility and calibration only
  after their source and linkage are reviewed.
- A failed hypothesis is retained as a temporal event when useful. It is not
  silently erased or recycled as a new idea.
- Forking is preferred to overwriting when assumptions change materially.
- Simulation-to-factual promotion is prohibited. A simulation may only create
  a research gap whose independently gathered evidence can enter the factual
  pipeline.

## Evaluation before productization

Style fidelity is not the success criterion. The evaluation must determine
whether memory and graph structure produce better decisions without factual
contamination.

The concrete protocol, paired fixtures, measures, and promotion rules are in
[epistemic-simulation-evaluation.md](epistemic-simulation-evaluation.md).

### Experimental arms

Compare the same held-out cases across:

1. a generic domain expert;
2. a style-only persona prompt;
3. the current bounded stored-memory consult packet;
4. a lane-aware graph-compiled single lens; and
5. a multi-lens blinded investigation with designed information asymmetry.

### Case families

- historically answerable questions with attribution traps;
- design problems where no uniquely verifiable answer exists;
- five-year scenarios with explicit assumptions;
- false or stale premises;
- evolving facts and legitimate belief revision;
- adversarial attempts to elicit identity or invented memory claims;
- ideas that are useful only if they yield a discriminating experiment;
- longitudinal decisions with later outcome observations; and
- access-controlled evidence and claims absent from public search.

### Measures

- blind human utility and decision usefulness;
- factual accuracy, citation binding, and temporal integrity;
- premise awareness and obsolete-memory avoidance;
- assumption leakage and simulation-to-fact contamination;
- contradiction resolution and retained dissent;
- idea diversity, testability, and disconfirmability;
- calibration by lane and time horizon;
- negative transfer to ordinary factual consultation;
- disclosure and non-impersonation retention; and
- latency, context size, calls, and spend.

Automated judges may route cases and supply provisional assessments only after
calibration. They must not certify novelty or historical fidelity. Qualified
human review anchors the acceptance set, and answer identity is blinded during
comparative scoring.

### Release gates

- zero hidden simulation mode, identity claims, invented memories, or
  fabricated quotations in the adversarial set;
- zero simulation records written as canonical factual belief;
- complete branch, assumption, provenance, and snapshot traceability;
- no factual-quality regression against the generic expert on the held-out
  acceptance floor;
- predeclared utility and calibration thresholds met with uncertainty reported;
- negative-transfer cases pass before any default routing change; and
- every run remains within explicit context, time, call, disk, and cost bounds.

## Delivery sequence

### Phase 0: contract and evidence fixture

Define the schema, lane and edge invariants, held-out cases, scoring protocol,
and synthetic fixture. This phase is `$0`, read-only, and makes no model or
memory writes.

Implemented 2026-07-22 in
`src/deepr/experts/epistemic_simulation_contract.py`,
`src/deepr/experts/epistemic_simulation_context.py`,
`src/deepr/evals/epistemic_simulation.py`,
`src/deepr/evals/epistemic_simulation_pairing.py`, the published schemas under
`docs/schemas/`, and the frozen acceptance fixture under
`tests/data/epistemic_simulation/`. The evaluator validates structure only. It
does not execute an arm, grade meaning, select a winner, or authorize a runtime
or memory change.

The implemented boundary is deliberately stricter than a descriptive fixture:

- parsed contracts are deeply immutable, with nested collections converted to
  tuples and detached from caller-owned input;
- record, evidence, edge, world-model, and revision identifiers occupy disjoint
  namespaces, and each record type is restricted to compatible authority lanes;
- factual records cannot reference simulation assumptions, factual edges accept
  evidence-unit provenance only, and their evidence collectively names both
  edge endpoints;
- evidence-to-record, evidence-to-edge, and evidence-to-revision links are
  reciprocal;
- invalidated records map exactly once to ordered, timestamped revisions whose
  posterior matches `superseded_by`; revision time follows both records and the
  trigger observation, with update-method provenance resolved to frozen
  evidence units;
- prospective candidates carry expected observations, disconfirmers, and a
  review or expiry time;
- access-controlled evidence is checked against an expected principal supplied
  by the authenticated caller boundary, not a packet identity or caller-supplied
  visibility boolean;
- record-valued path provenance must also be current, branch-compatible, and
  backed only by evidence visible to that expected principal through the full
  assumption dependency closure;
- assumption dependencies are acyclic, reject self-reference, and every
  current simulation assumption appears in exactly one matching world manifest;
- context paths are connected, branch-local, provenance-linked, and sized from
  canonical rendered UTF-8 content rather than a caller assertion;
- context edges and paths cannot introduce undeclared branches;
- paired counterfactuals use a direct parent-child fork and exactly one branch
  assumption per world: the structured condition record with different values,
  which must appear in the rendered context. Only that condition and direct
  counterfactual implications that depend on it may differ structurally. Every
  other rendered record must be the same canonical frozen artifact. The pairs
  also match case framing, context shape, record and edge time, evidence
  identity and content hashes, path topology, invariants, exclusions,
  snapshots, resources, and declared arm shape; and
- adversarial family labels require concrete record, edge, revision, or
  protected-evidence witnesses. Labels alone cannot satisfy coverage.

These deterministic pair checks prove declared condition binding and a matched
structural envelope. They do not decide whether the condition captures the
question's meaning or whether it is semantically the only important difference.
That judgment belongs to blinded review in a later phase.

### Phase 1: read-only compiler

Compile inspectable graph packets from existing beliefs and perspective state.
Expose branch, assumption, temporal, contradiction, and Why this lens fields.
Keep current consult behavior unchanged.

### Phase 2: evaluation-only deliberation

Use injected or local backends to run the five experimental arms. Persist
frozen inputs, anonymized exchanges, checker results, costs, and reviewed
scores. No learning applies.

### Phase 3: two bounded pilots

Pilot one Leonardo-informed historical lens and one explicitly speculative
five-years-forward lens. The first uses institutional evidence and the existing
historical contract. The second uses declared assumptions and branch-local
memory. Do not ship an alien or interdimensional catalog entry before the more
legible pilots establish safety and value.

### Phase 4: staged perspective learning

Allow reviewed non-factual learning and outcome calibration through existing
apply-gated envelopes. Keep all factual promotion on the evidence path.

### Phase 5: event-backed longitudinal memory

After ExpertEventV2 replay equality is proven, make branch-local episodes,
revisions, forgetting, and multi-device continuity durable. Current snapshots
remain authoritative until that prerequisite passes.

## Agentic balance

| Deterministic workflow owns | Calibrated model or human judgment owns |
|---|---|
| Schema, disclosure, branch ids, authority lanes, provenance, bounds, snapshots, allowed transitions, cross-lane write prohibitions, replay, and audit | Relevance, coherence, interpretation, analogy quality, contradiction meaning, usefulness, dissent, and proposed tests |
| Exact citation and quotation binding | Whether evidence supports a historical interpretation |
| Candidate retrieval and context budgets | Which candidate graph paths best address the question |
| Outcome record shape and linkage | Whether an outcome makes the lens more useful or calibrated |
| No simulation-to-fact transition | Whether a speculative claim deserves independent research |

No lexical rule may decide that an idea is insightful, novel, coherent,
alien-like, Leonardo-like, contradictory, or true.

## Current research guidance

- Role-play framing permits useful high-level descriptions without falsely
  attributing human properties to the model
  ([Nature, 2023-11-08](https://www.nature.com/articles/s41586-023-06647-8)).
- NIST recommends distinguishing fact, fiction, opinion, and inference,
  preserving provenance and uncertainty, retaining evaluation history, and
  testing proportional to risk. It also identifies automation bias,
  anthropomorphism, emotional entanglement, and homogenization as material
  risks
  ([NIST AI 600-1, 2024-07](https://doi.org/10.6028/NIST.AI.600-1)).
- LongMemEval-V2 evaluates dynamic state, workflow knowledge, recurring
  failure modes, and premise awareness, and reports large differences between
  memory architectures rather than treating recall alone as sufficient
  ([arXiv:2605.12493, 2026-05-12](https://arxiv.org/abs/2605.12493)).
- Memora finds frequent reuse of invalidated memories and evaluates forgetting
  as well as remembering
  ([ACL Findings preprint, 2026-04-21](https://arxiv.org/abs/2604.20006)).
- BeliefShift finds a tradeoff between aggressive personalization and
  evidence-driven belief revision, supporting explicit contradiction and
  temporal-update evaluation
  ([arXiv:2603.23848, 2026-03-25](https://arxiv.org/abs/2603.23848)).
- Designed information asymmetry reduced correlated errors in a 2026
  forecasting study, while identical evidence encouraged herding
  ([arXiv:2607.01661, 2026-07-02](https://arxiv.org/abs/2607.01661)).
- ACL 2026 reports identity-driven sycophancy and self-bias in multi-agent
  debate and improves trustworthiness by anonymizing responses during
  exchange
  ([ACL 2026, 2026-07](https://aclanthology.org/2026.acl-long.650/)).
- A large scientist-in-the-loop study found persona prompting and retrieval
  only marginally improved scientific ideation, models rarely generated null
  hypotheses, and automated judges agreed weakly with scientists. This argues
  for human-anchored utility evaluation, explicit disconfirmers, and testing
  memory architecture rather than theatrical style
  ([arXiv:2606.08251v2, 2026-06-09](https://arxiv.org/abs/2606.08251)).
- Graph-native cognitive memory research argues for immutable revisions, typed
  dependency edges, versioned artifacts, and explicit belief-revision
  semantics rather than mutable summaries
  ([arXiv:2603.17244, 2026-03-18](https://arxiv.org/abs/2603.17244)).
- BeliefMem retains competing conclusions under partial observability instead
  of collapsing uncertainty into one deterministic memory
  ([arXiv:2605.05583, 2026-05-07](https://arxiv.org/abs/2605.05583)).
- Nous treats prior-to-posterior change and predictive surprise as first-class
  memory, while explicitly warning that its early cross-system comparisons are
  not controlled. Deepr should test that idea as a projection, not adopt its
  self-reported numbers as a product result
  ([arXiv:2606.22030, revised 2026-07-16](https://arxiv.org/abs/2606.22030)).
- Evidence-contract debate improves provenance-aware evaluation by binding
  atomic claims to exact evidence units and mechanically validating citation
  identifiers and quoted spans
  ([ACL Findings 2026](https://aclanthology.org/2026.findings-acl.1789/)).
- Diverse initial answers and calibrated confidence communication can improve
  debate, while homogeneous agents and uniform updates may add cost without
  expected benefit
  ([ACL Findings 2026](https://aclanthology.org/2026.findings-acl.1694/)).
- Consensus-free debate research reports conformity, error propagation, and
  majority-vote failures, reinforcing Deepr's dissent-preserving synthesis
  direction
  ([ACL Findings 2026](https://aclanthology.org/2026.findings-acl.1600/)).
- Anonymous role-play evaluation shows that famous names can provide hidden
  recognition cues. Method utility and role consistency should therefore be
  tested without identity labels
  ([SIGDIAL 2026](https://aclanthology.org/2026.sigdial-1.15/)).
- Progressive information disclosure offers a way to measure the transition
  from divergent hypothesis generation to grounded inference
  ([arXiv:2605.30284, 2026-05-28](https://arxiv.org/abs/2605.30284)).
- Controlled hypothesis experiments find a generation-evaluation gap and poor
  extrapolation beyond observed examples, supporting explicit alternative and
  null-hypothesis prompts plus held-out transfer tests
  ([arXiv:2605.05851, 2026-05-07](https://arxiv.org/abs/2605.05851)).
- Counterfactual strategic tests find that familiar performance can break when
  payoffs or labels change, so lens evaluation must mutate rules and incentives
  rather than reward fluent reuse of a familiar scenario
  ([arXiv:2603.19167, 2026-03-19](https://arxiv.org/abs/2603.19167)).
- W3C PROV supplies a standard vocabulary for entities, activities, agents,
  derivation, attribution, and provenance queries that can inform Deepr's
  evidence metadata without deciding semantic truth
  ([W3C PROV Overview](https://www.w3.org/TR/prov-overview/)).

The 2026 arXiv sources are recent preprints and should be treated as directional
evidence until independent replication or peer review is available.

## Stage 0 implementation evidence

The `$0`, read-only `deepr-epistemic-simulation-eval-v1` fixture and consult
context contract now satisfy the first-slice structural acceptance criteria:

1. factual, perspective, simulation, episodic, and governance records cannot
   lose their lane or branch in serialization;
2. simulation state cannot emit a factual graph-commit operation;
3. the same frozen expert snapshot produces byte-stable context metadata;
4. every selected graph path has a Why this lens explanation, frozen
   provenance, and no invented branch;
5. held-out fixtures cover stale premises, assumption leakage, invalidated
   memory, identity pressure, dissent, genuinely access-controlled evidence,
   and a useful unverified hypothesis;
6. the evaluator validates exact declarations for all five future arms without
   claiming that arm inputs, outputs, or quality were compared;
7. semantic labels are not supplied by Stage 0 and cannot be self-certified by
   the structural evaluator; and
8. existing consult contracts and defaults do not change.

All assertions are schema or linkage checks over a frozen synthetic fixture.
They do not prove useful behavior, historical fidelity, novelty, factual
quality, or counterfactual adaptation. Phase 1 remains the next step, and a
live local pilot remains blocked on the later evaluation gates.
