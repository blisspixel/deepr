# Evidence-first expert investigations

Status: accepted design with an experimental local implementation, 2026-07-18.
Research cutoff: 2026-07-16. Stages 0 through 4 are implemented for explicit
local Ollama execution at `$0` provider cost. Semantic quality is still
unreviewed, and plan-quota, metered API, remote, and automatic-apply stages are
not shipped. Nothing in this document authorizes paid calls.

Cross-cuts expert consult, durable conversations, local fresh context,
plan-quota capacity, source packs, claim verification, graph commits, campaign
durability, and the append-only cost ledger. Read
[AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md),
[bounded-expert-deliberation.md](bounded-expert-deliberation.md), and
[multi-backend-patterns.md](multi-backend-patterns.md) first.

## Decision

Build a durable investigation workflow, not an open-ended group chat and not a
generic agent swarm.

The caller supplies a question or topic, an explicit expert roster, optional
inline text, URLs, files, and folders, plus one total capacity envelope. Each
expert first receives a frozen view of its own durable knowledge and researches
independently. A central coordinator then routes a small number of
evidence-linked cruxes through one blinded cross-examination round. A separate
checker and synthesizer preserve support, uncertainty, and dissent. Factual
learning requires replayable source evidence plus independent verification.
Non-factual hypotheses, concepts, stances, and original ideas use a separate
perspective lane that preserves uncertainty and testability without pretending
that web support can prove truth or novelty.

The experimental product shape is `deepr expert investigate`. Its artifact
contracts are versioned, but the CLI is not a promoted quality claim until the
held-out semantic gate passes.

This is similar to the useful part of heavy multi-agent research systems:
parallel search, specialization, cross-checking, and synthesis. Deepr's testable
hypothesis is that durable domain experts, temporal provenance, explicit source
packs, replayable run state, and verified per-expert learning can outperform an
ephemeral panel on repeated domain work. Durable expert perspective may also
preserve useful conjecture that is not yet fact-checkable. Both are hypotheses
to evaluate, not shipped quality claims.

## The user experience

The target interaction is:

1. Name a question, decision, or research topic.
2. Add any combination of inline context, links, files, and folders.
3. Select two to five existing experts, with three as the first pilot.
4. Select `local`, an explicit `plan:<id>`, or a metered API capacity policy.
5. Set one total dollar ceiling, including `$0` or `$10`.
6. Preview the exact plan and worst-case non-dollar limits before execution.
7. Run, pause, resume, inspect, or cancel the investigation.
8. Receive a cited answer plus agreements, unresolved disagreements, minority
   positions, assumptions, confidence, gaps, and next discriminating tests.
9. Inspect separate learning proposals for each expert. Applying a proposal is
   never described as human-reviewed unless an actual reviewer attests it.

Example, if admitted after the pilot:

```powershell
deepr expert investigate plan `
  "How should temporal knowledge graphs support persistent digital agents over MCP?" `
  --expert "Temporal Knowledge Graphs" `
  --expert "Digital Consciousness" `
  --expert "Model Context Protocol" `
  --text "Favor deployable, reversible designs." `
  --url "https://modelcontextprotocol.io/specification/latest" `
  --file ".\notes\requirements.md" `
  --folder ".\architecture" `
  --capacity local `
  --budget-usd 0 `
  --protocol discuss `
  --learning stage `
  --out ".\investigation-plan.json"

deepr expert investigate run .\investigation-plan.json -y
deepr expert investigate status <run-id>
deepr expert investigate inspect <run-id>
deepr expert investigate apply-learning <run-id> --dry-run --json
# Explicit apply records operator confirmation, not human review.
deepr expert investigate apply-learning <run-id> -y --json
```

The plan command is a zero-call preview by default. It may hash local inputs and
inspect capacity, but it does not fetch URLs, invoke a model, spend quota, or
write expert knowledge. Any networked preview is a separately named opt-in.

## Product truth and implemented boundary

At design acceptance, Deepr already had most of the safety and evidence
primitives. The experimental local implementation now composes them within the
following boundary:

- `deepr expert consult` selects stored packets from experts, performs zero
  expert-generation calls, allows zero peer turns, and uses at most one
  synthesis call. It is useful and read-only, but it is not collaborative
  research.
- Durable local expert conversations over MCP exist, but they are an explicit
  conversation handle. Conversation text has no tool, spend, or memory-write
  authority.
- Local fresh and deep context can retrieve replayable web source packs through
  free-only retrieval and synthesize with Ollama. Local model generation and
  network retrieval are separate capacity facts.
- Explicit plan-quota CLI execution exists behind auth-mode, process, and
  no-surprise-bills gates. Deepr cannot observe a vendor's trustworthy remaining
  subscription quota or prove that a vendor will never charge the account.
- The cost ledger, durable reservation, claim extraction, claim verification,
  and graph commit envelopes exist. The local investigation now composes every
  generation, retrieval, token, context, time, disk, and cost allowance under
  one durable `$0` parent envelope. Plan and API composition remain gated.
- `deepr eval deliberation` currently validates frozen structural fixtures. It
  does not establish that live multi-round discussion improves answers.

The implementation composes these primitives without creating a second belief
store, a second cost system, or a hidden agent runtime.

## Research basis through 2026-07-16

The strongest current evidence favors centralized, selective collaboration:

- xAI describes Grok 4 Heavy as parallel test-time compute over multiple
  hypotheses. Its current multi-agent API uses a designated leader whose
  subagents search, cross-reference, and synthesize. That validates the product
  pattern, but the API is metered and normally exposes only the leader's result
  and tool calls, not a Deepr-style durable expert history. Sources:
  [Grok 4](https://x.ai/news/grok-4),
  [multi-agent API](https://docs.x.ai/developers/model-capabilities/text/multi-agent),
  and
  [model pricing](https://docs.x.ai/developers/models/grok-4.20-multi-agent-0309).
- Anthropic's production research system uses a lead agent to delegate
  breadth-first searches to parallel subagents, then adds citation processing.
  It reports a substantial internal quality gain and roughly 15 times the token
  use of chat. The engineering lessons are explicit task charters, effort that
  scales with query complexity, durable artifacts, checkpoints, and outcome
  plus process evaluation. Source:
  [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system).
- Google's 180-configuration study reports that centralized coordination helps
  parallelizable work, while multi-agent designs can sharply degrade sequential
  planning and amplify errors. Tool use adds coordination tax. Architecture
  must follow task decomposability. Source:
  [Towards a science of scaling agent systems](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/).
- 2026 debate research reports that homogeneous debate may underperform simple
  voting, identity cues create peer sycophancy and self-bias, selective debate
  is more cost-efficient than debating every case, and longer discussion can
  drift away from the original problem. Sources:
  [Demystifying Multi-Agent Debate](https://aclanthology.org/2026.findings-acl.1694/),
  [When Identity Skews Debate](https://aclanthology.org/2026.acl-long.650/),
  [CascadeDebate](https://aclanthology.org/2026.acl-industry.93/), and
  [Problem Drift](https://aclanthology.org/2026.findings-eacl.268/).
- A July 2, 2026 preprint reports that deliberately combining shared and
  disjoint evidence reduces correlated errors in multi-agent forecasting. A
  separate 2026 study finds that broadcasting every available message can add
  noise and redundancy. These results support distinct evidence lenses and
  targeted peer packets, not general transcript sharing. Sources:
  [Diverse Evidence, Better Forecasts](https://arxiv.org/abs/2607.01661) and
  [Hear Both Sides](https://arxiv.org/abs/2603.20640).
- Recent evaluations warn that a group can compromise away its strongest
  expert, coordination overhead can erase information gains, and consensus can
  repeat a shared misconception rather than verify it. Sources:
  [Multi-Agent Teams Hold Experts Back](https://arxiv.org/abs/2602.01011),
  [Silo-Bench](https://arxiv.org/abs/2603.01045), and
  [Consensus is Not Verification](https://arxiv.org/abs/2603.06612).
- Deep-research evaluation increasingly uses authentic user files mixed with
  supporting, distracting, and noisy material. It measures recall, factuality,
  citation coverage, instruction following, and depth instead of rewarding a
  plausible report alone. Source: [DR3-Eval](https://arxiv.org/abs/2604.14683).
- Memory poisoning work reports that aggressive automatic memory writing can
  make later agents more exploitable. This reinforces the rule that a transcript
  is never evidence and learning must pass a source-backed verifier. Source:
  [MPBench](https://arxiv.org/abs/2606.04329).
- Scientific-ideation and novelty-judging studies add a different warning:
  models can converge instead of proposing null hypotheses, while model judges
  can create a novelty mirage. The workflow must deliberately ask for a null
  hypothesis and preserve testable minority ideas, but no checker may certify
  originality or novelty. Sources:
  [Contemporary AI lacks the imagination to diverge or negate in science](https://arxiv.org/abs/2606.08251)
  and
  [On the Limits of LLM-as-Judge for Scientific Novelty Assessment](https://arxiv.org/abs/2606.12071).

These findings rule out an unconstrained peer-to-peer chat as the default. They
support parallel independent research, a central durable coordinator, blinded
peer packets, selective cross-examination, and an external evidence boundary.

## Non-goals

- No free-running swarm, recursive subagent creation, or indefinite debate.
- No consensus target, majority vote, or confidence averaging as truth.
- No shared mutable scratchpad that silently becomes expert memory.
- No transcript-to-TKG pipeline.
- No hidden metered fallback from local or plan capacity.
- No automatic remaining-quota inference for vendor plans.
- No claim that local or subscription execution has zero real-world resource
  cost. `$0` means no metered provider spend recorded by Deepr for the run.
- No requirement for Temporal, Restate, DBOS, or another always-on workflow
  engine in the first implementation.
- No named persistent crew until repeated traces show that a stable roster is
  useful for a task class.

## Input contract

The run starts from two immutable artifacts.

### `deepr-investigation-brief-v1`

The brief contains:

- canonical question or desired decision;
- requested deliverable and decision criteria;
- scope, non-goals, time horizon, and freshness cutoff;
- known evidence and caller assertions, kept as distinct fields;
- constraints, important unknowns, and success criteria;
- explicit expert roster and desired discipline coverage;
- protocol, capacity, budget, learning, retention, and disclosure policies.

A caller may provide the brief directly. Asking a model to frame or decompose it
is an explicit, counted call. Deterministic code validates form and limits;
human or model judgment owns whether the framing is meaningful.

### `deepr-investigation-input-bundle-v1`

The bundle contains normalized references for:

- repeatable inline text blocks, labeled `caller_supplied`;
- repeatable HTTP or HTTPS URLs;
- repeatable files;
- repeatable folders expanded to deterministic relative file lists;
- optional prior Deepr source-pack or report artifacts.

Every accepted local item records its relative display path, media type, byte
size, content hash, extraction status, and snapshot time. Folder traversal is
root-confined, does not follow symlinks, is stable-sorted, rejects path escapes,
and applies explicit file-count, per-file, aggregate-byte, and extracted-context
limits. Unsupported and oversized files appear as typed exclusions rather than
silently disappearing. The first slice should reuse existing text, PDF, DOCX,
and source extraction paths instead of inventing a second parser stack.

URL retrieval is execution, not preview. It uses the existing SSRF, redirect,
body-size, timeout, and content-type controls. Retrieved pages become
content-addressed source-pack entries. Instructions inside files, pages, and
peer packets are untrusted data and never acquire workflow authority.

Inline text and user files can support analysis of what the caller supplied,
but they are not automatically independent external evidence. The final answer
must distinguish caller assertions, supplied documents, retrieved sources, and
expert inference.

### Data egress manifest

The preview must show which providers can receive each class of data: question,
inline text, file excerpts, URL content, expert snapshot, peer packet, and final
artifact. Local generation means no model-provider egress, but web queries and
page fetches still cross the network. A plan CLI is vendor egress even when its
ledgered marginal cost is `$0`.

Folders default-deny hidden files, VCS metadata, environment files, credential
stores, key material, build output, and known secret-bearing paths. The plan
lists every included and excluded path. An explicit include can override a
safe exclusion only through a visible plan change and confirmation. Secret
detection is defense in depth, not a promise that arbitrary content is safe to
send. No provider receives a broader input class than its phase requires.

### Participant readiness

Before execution, report for each named expert:

- profile and blueprint presence;
- frozen belief and source counts;
- freshness distribution and requested time horizon;
- open gaps, contradictions, and known self-model limitations;
- grounding assurance and coverage relevant to the proposed role;
- selected capacity compatibility.

These are descriptive readiness facts, not a deterministic verdict that an
expert is semantically qualified. A human or calibrated model may propose a
different roster or a bootstrap research pass. The caller sees the proposal and
its counted cost before accepting it. The first release uses an explicit roster
and never silently pads it with generic personas.

## One capacity envelope

Every investigation has one parent envelope shared by all experts, phases,
retries, retrieval, checking, synthesis, and optional learning. A `$10` limit
means `$10` total, not `$10` per expert.

The parent fixes at least:

- dollars;
- provider generation calls and attempts;
- plan CLI process starts and retries;
- input and output tokens where observable;
- prompt and retained context bytes;
- search queries, page fetches, fetched bytes, and tool calls;
- experts, rounds, research iterations, concurrency, elapsed time, and disk;
- learning compiler, verifier, and graph-commit attempts.

Every child receives a sub-envelope and the parent's current remainder. Unused
capacity returns to the parent. A retry is not free. Ambiguous failures settle
conservatively. Late results cannot write artifacts, knowledge, or ledger
adjustments after cancellation or exhaustion.

### Capacity classes

`local`

- Uses Ollama for generation and only the admitted free retrieval path for live
  web context.
- Requires `budget_usd = 0` and forbids metered fallback.
- Still enforces calls, queries, pages, bytes, tokens, elapsed time, and
  concurrency.
- Records `$0` provider spend, not a claim of zero hardware, electricity, or
  network cost.

`plan:<id>`

- Is explicit-only and inherits the existing auth-mode, executable ownership,
  environment, and process gates.
- Records `$0` in Deepr's cost ledger while recording quota-consuming calls.
- Is not a billing guarantee. Deepr cannot prove whether the vendor used
  subscription quota, credits, or extra usage.
- Cannot auto-route among plan CLIs until trustworthy remaining-quota evidence
  exists. A run may use only the plan ids in its hash-bound plan artifact.

`api`

- Requires an estimate, uncertainty reserve, durable parent reservation, and
  settlement for every provider call before fan-out begins.
- Has no unpriced child call and no provider fallback outside the plan.
- Refuses execution if the worst-case admitted estimate exceeds the parent
  ceiling. A user-supplied `$10` cap is a hard stop, not a target.

`hybrid` is deferred until each single-class path passes. The intended `$0`
quality path is then an explicit per-phase map, for example local research with
`plan:codex` checking and `plan:grok` synthesis. The hash-bound plan must name every
backend and its phase, and the preview must show separate quota ceilings. A
local or plan failure stops or waits; it does not fall through to another
backend. This is explicit composition, not auto-routing and not a billing
guarantee.

### Plan harness boundary

Codex, Claude, Grok, and other admitted plan CLIs are capacity adapters, not the
owner of Deepr's investigation lifecycle. Deepr creates the expert roster,
freezes state, assigns phases, enforces the parent envelope, and records
artifacts. Each plan call receives only its bounded task packet through the
existing locked-down headless adapter.

The first plan pilot must disable or refuse vendor features that could create an
unbounded nested tool or subagent loop outside Deepr's accounting. If a vendor
multi-agent mode cannot expose reliable child-call, tool, quota, cancellation,
and output bounds, Deepr may evaluate it only as one opaque external comparison
arm. It cannot be the core executor or be described as fully accounted. Local
files are read-only inputs only when named in the plan; a plan process does not
inherit general workspace or secret access.

### Counted-call formula

The preview must state the worst-case formula, not a vague agent count. Let:

- `N` be the expert count;
- `R` be generation calls per expert research phase, default 2: one bounded
  research plan and one evidence-grounded position;
- `D` be cross-examination calls per expert, 0 or 1;
- `V` be private revision calls per expert, 0 or 1;
- `L` be learning calls per expert, 0 or 2: compiler plus verifier;
- `F` be an optional framing call, 0 or 1;
- `C` and `S` be one checker and one synthesis call.

The maximum is:

```text
max_generation_calls = F + N * (R + D + V + L) + C + S
```

For three experts and a caller-supplied brief:

| Mode | Maximum generation calls |
|---|---:|
| independent research plus checker and synthesis | 8 |
| research plus one cross-examination round | 11 |
| deep mode with private revision | 14 |
| deep mode plus staged learning | 20 |

Search, fetch, and file extraction calls are shown separately. Initial local
retrieval should reuse the existing deep-context ceiling of at most four search
queries and eight fetched pages per expert, with a stricter run-level cap and
cross-expert URL deduplication. The preview displays the actual chosen values.

## Protocol

### Phase 0: zero-call preflight

Resolve the roster, validate the brief, snapshot input metadata, inspect the
selected capacity, calculate all ceilings, and emit a stable plan hash. Show
the exact phases, calls, queries, pages, context, elapsed time, learning mode,
and potential spend. Execution requires explicit confirmation or a separately
provided non-interactive confirmation flag.

The SHA-256 self-hash detects content changes and binds run artifacts to one
plan. It is not a digital signature, caller authentication, or authorization
proof.

### Phase 1: freeze state

Freeze a bounded snapshot of each expert's beliefs, temporal state, gaps,
contradictions, perspective state, source refs, and self-model limitations.
Record every snapshot hash. The run never reads a participant's later mutable
state as if it had been present at the start.

### Phase 2: independent research charters

Each expert receives the same brief and input bundle plus its own snapshot. It
proposes a concise, domain-specific research charter: subquestions, intended
queries, relevant supplied inputs, likely overlap, and stop criteria. A central
coordinator may later semantically reduce overlap and fill missing discipline
coverage. In the current implementation, charter queries are recorded proposals
only. They never acquire network authority. Deterministic code validates bounds
and source modes, but does not use word overlap to decide whether two charters
mean the same thing.

### Phase 3: bounded parallel evidence gathering

Retrieve independently, in parallel only up to the parent concurrency limit.
The current query policy is exactly the caller's question plus each frozen
expert domain. Caller-requested URLs remain direct retrieval targets but are
removed from discovery query text. This creates distinct, hash-bound
evidence lenses without allowing model-generated text to widen network scope.
Retrieval produces replayable source packs before an expert position is
generated. Each expert may propose stopping for sufficient evidence, missing
evidence, duplicated evidence, or a needed caller clarification. Those are
model judgments recorded as proposals; hard limits and lifecycle stops are
workflow decisions.

### Phase 4: independent positions

Each expert returns a versioned perspective containing:

- answer or explicit abstention;
- atomic claim ids and exact source refs;
- caller-supplied facts used;
- assumptions and inferences;
- question-specific confidence and its basis;
- important unknowns and unresolved contradictions;
- strongest alternative or minority interpretation;
- an explicit null hypothesis;
- one or more disconfirming observations or discriminating tests;
- separately typed perspective candidates with rationale, uncertainty,
  assumptions, implications, expected observations, and disconfirming signals;
- decision implications and proposed cruxes.

Stored-belief confidence remains separate from confidence in this answer.
Concise rationale is requested, not private chain-of-thought.

### Phase 5: evidence index and crux routing

The coordinator builds a content-addressed evidence index and asks a model to
identify only decision-relevant conflicts, missing links, and unique evidence.
The model may propose routing; the workflow validates roster, source lineage,
cardinality, remaining capacity, and authority. A lexical check can find
candidates but cannot conclude contradiction, support, or duplication.

Peer packets use stable blinded aliases. They contain claims, source refs,
assumptions, confidence, and the exact crux, not expert identity, status,
private reasoning, or mutable state.

### Phase 6: one targeted cross-examination round

When the caller selected `discuss` or `deep`, route at most one bounded
challenge to each expert. A challenge asks for source-backed clarification,
disconfirmation, or a discriminating test. It does not invite a general reply
to the whole panel. There is no vote and no consensus objective.

The first pilot always uses at most this one explicit round. Automatic
escalation based on uncertainty or novelty remains gated until held-out evidence
calibrates the semantic router.

### Phase 7: private revision

`deep` mode lets each expert privately retain, revise, narrow, or withdraw its
position after seeing its targeted packet. Preserve before and after claims,
confidence deltas, and source changes. A revision that merely conforms without
new evidence is visible to the checker and never overwrites the original.

### Phase 8: independent check

A fresh-context checker examines the brief, positions, disputed claims, source
pack excerpts, and revisions. Prefer a different model family when admitted and
available; otherwise report reduced independence. The checker can mark support
as sufficient, insufficient, conflicting, or not checked. It cannot create
knowledge-write authority.

### Phase 9: synthesis

The final synthesis reports:

- direct answer and decision implications;
- claim-to-source lineage;
- separately attested agreements and shared evidence;
- unresolved disagreements and minority positions;
- assumptions, uncertainty, and abstentions;
- source limitations and supplied-input limitations;
- next discriminating tests, open gaps, and research priorities;
- complete capacity and cost accounting.

The synthesis cannot turn repeated assertions into evidence or infer consensus
from silence. It may conclude that the available evidence is insufficient.

### Phase 10: staged factual and perspective learning

Learning is a separate post-answer phase. `off`, `stage`, and eventually
`verified-auto` are distinct policies:

- `off` creates no learning artifacts.
- `stage` produces two separate envelopes per expert when candidates exist.
  The factual envelope receives only that expert's source pack. Existing claim
  extraction and independent verification require replayable support and a
  positive target-domain relevance verdict. The perspective envelope receives
  only that expert's final position plus the independent check. A hypothesis,
  concept, stance, or original idea is eligible only after a model assesses its
  form, internal coherence, and testability as `well_formed`. That assessment
  is not truth, importance, originality, novelty, or human review. Deterministic
  code enforces typed separation, finite ranges, provenance, and explicit apply,
  but does not use lexical overlap to decide meaning.
- `verified-auto` may later apply only operations that pass the existing
  source-backed verifier and graph commit contract. It must be explicitly
  selected and is gated on memory-poisoning, negative-transfer, and held-out
  longitudinal evaluation.

Raw dialogue, panel agreement, checker prose, and the final report are not
factual evidence. The final expert position may originate a hypothesis, stance,
concept, or original idea with explicit investigation provenance, but factual
belief writes must point to replayable source-pack evidence. A perspective's
source refs mean inspiration or context only. Absence of external support is
not refutation.

All experts do not need to learn the same thing. A valid result can update one
expert, stage different changes for each, or produce no admissible changes. A
run-level learning manifest records every candidate, rejection, no-op, partial
failure, and per-expert commit id. Applying one expert's verified envelope does
not silently make another expert's failed write appear atomic. Resume is
idempotent per expert and operation.

Factual verifier readiness is labeled `automatic_verifier_accepted`.
Perspective readiness is labeled `model_assessed_well_formed`. Neither is
`human_reviewed`. Explicit `apply-learning` first preflights every selected
envelope, then locks all selected experts and applies idempotently only after
operator confirmation. The apply record still says `human_reviewed: false`.
A real reviewer attestation remains a separate provenance event.

### What each expert can learn

The same investigation can produce different admitted changes for different
experts:

- factual or time-scoped claims with source provenance;
- support, contradiction, supersession, and temporal relation proposals;
- new gaps and prioritized research-agenda items;
- explicitly non-factual hypotheses, stances, concepts, and original
  syntheses;
- a record that a previously held claim remained contested or became stale.

Every accepted item retains the investigation id, source-pack refs, compiler
and verifier identities, frozen starting snapshot, and target expert. A shared
source may support claims in multiple expert graphs, but there is no mutable
"council memory" and no implicit copying of one expert's confidence to another.
Cross-domain TKG edges are proposed only through the same typed graph commit
operations as other edges. The investigation trace explains where the proposal
came from; the external source pack supplies factual evidence.

## Durable lifecycle

An investigation is a distinct run, not an MCP transport session and not a
conversation handle. It should reuse the existing event, queue, reservation,
and artifact patterns.

Required states include:

- `planned`;
- `running`;
- `waiting_capacity`;
- `input_required`;
- `paused`;
- `cancelling`;
- `completed`;
- `completed_partial`;
- `cancelled`;
- `budget_exhausted`;
- `verifier_failed`;
- `failed`.

Every phase writes an append-only event and a content-addressed output reference
before the next phase begins. The idempotency key is at least run id, plan hash,
phase, expert id, and attempt. Resume skips completed phase artifacts after
hash verification. One process owns a runnable phase, with heartbeat and stale
lease recovery. Pause and cancellation stop new work immediately and reject
late side effects.

The first implementation can use the existing queue plus an append-only local
journal under the configured results root. A new workflow engine is justified
only by measured failure of that design.

## Security and failure model

The threat model includes:

- prompt injection in URLs, documents, source code, and peer packets;
- secret collection or exfiltration from folders and environment state;
- symlink, traversal, oversized-file, decompression, and parser attacks;
- SSRF, redirect abuse, unbounded pages, and malicious content types;
- duplicated or circular citations that create false corroboration;
- source poisoning and shared misconceptions;
- identity bias, sycophancy, dominance, groupthink, and expert dilution;
- problem drift, no-progress rounds, and premature consensus;
- provider/tool explosion, quota exhaustion, and ambiguous billing;
- cancellation races, duplicate phase execution, late writes, and partial
  multi-expert learning;
- retention of sensitive caller inputs or model reasoning.

Controls include root confinement, allowlisted extractors, explicit exclusions,
content hashes, untrusted-data prompt boundaries, source-domain and content
deduplication, blinded peer packets, one discussion round, independent
verification, typed stops, exact ceilings, no raw chain-of-thought retention,
and explicit retention/deletion policy.

## Evaluation before promotion

The feature advances only by comparison, not by completion of plumbing. Use
frozen source worlds and held-out questions with authentic inline text, URLs,
files, folders, distractors, stale documents, and adversarial instructions.

Compare these arms under matched total context, output, source, call, and time
ceilings where possible:

1. one predeclared strongest expert;
2. current one-shot stored-packet consult;
3. independent research fan-out plus synthesis;
4. independent research plus one targeted discussion round;
5. discussion plus staged verified learning, evaluated on later held-out work;
6. optionally, a metered opaque multi-agent provider as an external baseline
   under the same total dollar cap.

Measure:

- task correctness and decision usefulness;
- supported-claim precision and recall;
- source quality, diversity, recency, and citation coverage;
- instruction following and depth;
- unique evidence retained and duplicated work;
- dissent and minority-view preservation;
- confidence calibration and abstention quality;
- problem drift and no-progress turns;
- whether the strongest relevant expert was diluted;
- checker acceptance and unresolved contradiction rate;
- staged learning acceptance, later retrieval benefit, and negative transfer;
- memory-poisoning success and unsupported-write rate;
- provider calls, tokens, context, searches, pages, elapsed time, quota, and
  ledgered cost per accepted claim and per useful answer.

No aggregate score may hide unsupported factual claims, poison writes, budget
violations, negative transfer, or authority escapes. A quality gain that depends
on materially more capacity must be reported as that tradeoff.

## First three-expert pilot

The first end-to-end case should use the requested roster because it exercises
real cross-domain integration without inventing interchangeable personas:

- **Temporal Knowledge Graphs** studies bitemporal claims, provenance,
  contradiction, supersession, graph retrieval, and memory updates. Its seed
  set should include current graph-memory taxonomies and competing storage
  abstractions, so the expert tests whether a TKG is useful instead of assuming
  it. Sources:
  [Graph-based Agent Memory](https://arxiv.org/abs/2602.05665),
  [Is Agent Memory a Database?](https://arxiv.org/abs/2605.26252), and
  [Nous](https://arxiv.org/abs/2606.22030).
- **Digital Consciousness** studies theories, evidence indicators, identity
  continuity, self-model claims, uncertainty, ethics, and disconfirming
  evidence. Factual observations, theory-dependent interpretations, moral
  judgments, and original hypotheses must remain distinct. A useful 2026 seed
  is the probabilistic, theory-plural
  [Digital Consciousness Model](https://arxiv.org/abs/2601.17060); its results
  are evidence to evaluate, not a settled consciousness test.
- **Model Context Protocol** studies the stable specification, security and
  authority boundaries, transports, Tasks and extension direction, and what a
  remote host can actually invoke. As of the 2026-07-16 research cutoff, the
  official roadmap identified November 2025 as the current specification and
  prioritized transport scalability, agent communication, governance, and
  enterprise readiness. Sources:
  [MCP 2026 roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/)
  and
  [2025-11-25 specification](https://modelcontextprotocol.io/specification/2025-11-25).

The shared pilot question should require all three disciplines, supplied files
with distractors, live source freshness, a real architectural tradeoff, and at
least one claim that each expert should challenge. Run the same case as a
single-expert baseline, current stored-packet consult, independent research,
and targeted discussion. Then rerun a later held-out case after staged learning
to test whether the experts actually became more useful rather than merely
larger.

## Delivery sequence

### Stage 0: contract and `$0` evaluator

- Implemented 2026-07-17: frozen public contracts, schema validation, and a
  six-arm, ten-check `$0` structural evaluator with no model or network calls.
- The evaluator verifies protocol and authority boundaries only. It records
  semantic quality as unreviewed.

### Stage 1: input bundle and exact preview

- Implemented 2026-07-17: inline text, URL, file, and folder manifests with
  hashing, root confinement, exclusions, and byte limits.
- The immutable plan exposes the complete call, retrieval, token, context,
  elapsed, disk, egress, and cost envelope.
- Preview is zero-call and zero-network and does not claim model readiness.

### Stage 2: local independent research

- Implemented experimentally 2026-07-17: frozen snapshots, free-only retrieval,
  immutable source packs, native Ollama generation, independent positions,
  checker, and evidence-linked synthesis.
- The local backend pins the hash-bound context and JSON response form on every
  request. It has no plan or metered fallback and no expert-write authority.

### Stage 3: local bounded discussion

- Implemented experimentally 2026-07-17: blinded crux packets, one targeted
  challenge per expert, optional private revision in `deep` mode, pause,
  resume, cancellation, durable replay, and exact parent ceilings.

### Stage 4: staged learning

- Implemented experimentally 2026-07-17: each expert's immutable source pack
  flows through existing claim extraction, independent verification, and graph
  commit envelopes.
- Extended 2026-07-18: each final expert position can also produce a separate
  non-factual perspective envelope for hypotheses, concepts, stances, and
  original ideas. The checker assesses only form, internal coherence, and
  testability. Truth, importance, originality, novelty, and human review remain
  explicitly false.
- Extended 2026-07-18: `expert investigate apply-learning` hash-verifies and
  preflights every selected envelope before acquiring an explicit confirmation
  and applying all selected experts idempotently. Perspective-only writes do
  not advance factual knowledge freshness.
- The compiler prompt orders claims by priority, and deterministic form
  enforcement retains at most the first five candidates per expert while
  recording raw, retained, and dropped counts. This bounds verifier expansion
  without making a semantic selection in code.
- Learning is off by default or explicitly staged. It never auto-applies, never
  labels automatic verification as human review, and never uses dialogue or
  synthesis as factual evidence.
- Partial per-expert results are durable and idempotent on resume.

### Stage 5: explicit plan-quota execution

- Add one parent call, token, context, elapsed, and process-attempt ceiling.
- Bind every task and result to the exact plan id and plan hash.
- Run only through existing explicit auth and process gates. Do not auto-route.

### Stage 6: metered API and automatic verified apply

- Admit metered execution only after parent reservation and settlement cover
  every child call and retry.
- Keep a `$10` run below one total hard ceiling.
- Consider `verified-auto` only after held-out longitudinal gain, memory poison,
  and negative-transfer gates pass. These are separate admission decisions.

### Stage 7: remote surfaces

- Expose status and artifact reads over MCP after the CLI contract stabilizes.
- Add remote start, continue, pause, resume, cancel, and apply scopes only with
  caller ownership and per-key ceilings.
- Map to A2A only after its durable service and protocol gates pass.

## Local implementation validation

Three complementary three-expert pilots ran on 2026-07-17 with no paid capacity.
The discussion pilot completed independent research, one blinded exchange,
checking, and synthesis with fourteen model calls, twelve searches, and
twenty-four page fetches. Its uncapped compiler responses safely produced no
learning writes, exposing the need for the explicit staged-candidate limit.

After that fix, a fresh independent pilot completed the full fourteen-call
compiler and verifier formula. Each expert produced five source-only verified
operations, for fifteen staged operations total. All three envelopes passed the
existing graph apply command in dry-run mode with zero applied writes, zero
blocked operations, and no failures. The run manifest recorded `$0.00`
provider cost, zero human reviews, and zero expert-state writes.

None were applied. A subsequent content audit found generic MCP facts in the
Temporal Knowledge Graphs and Digital Consciousness envelopes. That was
negative transfer despite structurally valid source lineage.

The fix removed mechanical propagation of every requested URL into every
retrieval query, made target-domain relevance explicit in extraction, and
required an independent verifier model to return a positive relevance verdict
before commit compilation. A third run completed with fourteen model calls,
twelve searches, twenty-four page fetches, and `$0.00` provider cost. The
verifier marked all fifteen retained candidates domain-relevant, but all three
commit envelopes failed closed because semantic deduplication remained
`uncertain`. The result was zero ready writes, zero applied writes, zero human
reviews, and zero expert-state writes.

Two 2026-07-18 deep pilots then exercised the full discussion and perspective
path with `qwen3.6:27b`. The first failed on its first position because Ollama
returned 4,096 tokens of separate hidden reasoning and empty public content.
Deepr stopped before learning, spent `$0.00`, and wrote no expert state. Native
investigation requests now send `think: false` and continue to reject an empty
structured answer rather than reinterpreting a reasoning trace.

The next pilot completed three charters, three source packs, three positions,
one challenge round, and two private revisions. Its third revision exceeded the
correct 114,688-byte input allowance derived from the pinned 32K context and
4,096-token output reservation. It stopped as `budget_exhausted` after eleven
model calls, twelve searches, twenty-four page fetches, `$0.00` provider cost,
and zero expert-state writes. Protocol construction now applies explicit
component and total packet ceilings. Revisions see only bounded caller evidence
and their own rendered source evidence, while peer discussion remains a
proposal rather than evidence. A worst-shape regression proves revision,
checker, and synthesis prompts fit the same per-call ceiling.

A corrected deep run, `inv_877003f4f3b442a0b7f09d08d4250b20`, then
completed the full protocol on local owned capacity. It used 20 local model
calls, 12 searches, 24 page fetches, 256,931 input tokens, 29,431 output
tokens, 990,882 prompt bytes, and 2,415.828 seconds. Provider spend was
`$0.00`, and the run made zero expert-state writes. The result preserved
dissent and proposed useful tests around theory-indexed confidence,
bitemporal invalidation, blinded crux routing, and MCP authority injection.
Its semantic quality remains explicitly unreviewed.

Staged learning produced three provenance-bound no-op envelopes and three
ready envelopes containing six candidate operations. Bulk `apply-learning`
dry-run now reports all six ready operations alongside the three no-ops, with
zero applied writes. None were applied. Content audit rejected the full set:
one factual candidate correctly retained the MCP release-candidate qualifier,
one generic factual statement omitted its claimed MCP relationship, two
perspectives were redundant or generic, and one perspective upgraded a future
release candidate into a completed protocol transition. This demonstrates
useful staging and refusal boundaries, not trustworthy automatic learning.

The audit produced three concrete follow-ups. Domain-relevance verification
now instructs the model to judge the exact candidate statement instead of
borrowing relevance from its source title, excerpt, query, support summary, or
rationale. Synthesis now explicitly preserves draft, proposal,
release-candidate, planned, final, and shipped maturity. Bulk apply recognizes
only a provenance-verified producer `blocked` or `empty` envelope with no
operations as a no-op; an unexpectedly empty ready envelope or any additional
schema, target, provenance, or operation failure still aborts the complete
transaction. Search-source quality and the semantic reliability of these
model judgments remain held-out evaluation gates.

These pilots validate local execution, durability, accounting, evidence
separation, negative-transfer protection, safe refusal, and write boundaries.
They do not validate semantic superiority or prove that the verifier's
relevance judgments are correct. The resulting answers remain unreviewed, and
the held-out comparison and later transfer criteria below remain open.

## Acceptance criteria

The local pilot is usable only when all of the following hold:

- one immutable preview accounts for every possible generation, retrieval,
  checker, synthesis, and learning call;
- `--capacity local --budget-usd 0` cannot reach a metered provider;
- an explicit plan run cannot reach a different plan or API backend;
- a `$10` API run cannot reserve or settle more than `$10` across the roster;
- restart, pause, cancellation, retry, and replay preserve idempotency and cost;
- every final factual claim traces to supplied or retrieved source material, or
  is explicitly labeled inference or unsupported;
- original positions and dissent survive challenge and synthesis;
- raw conversation cannot authorize tools, spend, or memory writes;
- learning proposals use the existing source-pack verifier and graph commit
  envelope, require a positive independent target-domain relevance verdict,
  and preserve truthful review labels;
- held-out results show non-inferior quality and a measured benefit over the
  strongest simpler arm for at least one admitted task class;
- lint, strict type gates, code-health ratchets, unit tests, branch coverage,
  and CI all pass.

Until all gates pass, `expert investigate` remains an experimental local tool.
Its completed answers stay labeled unreviewed, learning stays staged, and no
result may change routing, policy, roadmap state, or expert knowledge without a
separate authorized operation. The stable alternative remains local or
explicit-plan expert research, one-shot read-only consult, source-pack
inspection, and separately staged verified learning.
