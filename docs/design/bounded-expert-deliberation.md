# Bounded expert deliberation

Status: proposed design, 2026-07-11.

Cross-cuts expert consult, consult traces, local and plan capacity, verified
expert loops, and the graph-commit boundary. Read
[AGENTIC_BALANCE.md](../plans/AGENTIC_BALANCE.md) and
[multi-backend-patterns.md](multi-backend-patterns.md) first.

## Problem

One-shot consult is useful, but it does not let an expert ask another expert a
targeted follow-up, revisit a disagreement, or expose a missing assumption.
Unstructured multi-agent debate is not the answer. It adds correlated output,
rewards persuasive confidence, consumes capacity without an independent
verifier, and can turn conversation text into false consensus.

The useful goal is a bounded deliberation lab. Experts develop a better
question, perspective, or test plan together while Deepr preserves independent
positions, exact lineage, and a hard stop. Conversation can propose learning,
but it cannot directly become canonical memory.

## Proposed contract

A deliberation is one versioned run with:

- a question and explicit expert roster;
- an immutable expert-state snapshot for each participant;
- a selected local or explicit non-metered plan backend;
- a total turn, token, elapsed-time, and capacity ceiling;
- a maximum of three rounds by default and five by explicit override;
- one durable trace linking every prompt, response, source reference, capacity
  event, cancellation, and verifier result;
- typed terminal states: completed, waiting_capacity, cancelled,
  verifier_failed, budget_exhausted, or failed;
- no metered fallback in the local-first pilot.

The host remains the orchestrator. Experts receive bounded questions and return
structured perspective artifacts. They do not gain tools, spend authority, or
write authority by participating.

## Round protocol

### Round 1: independent positions

Each expert answers from the same question and its own frozen state without
seeing other answers. The packet includes claims used, confidence,
grounding-assurance labels, uncertainties, and one question it would ask a
different expert. This prevents early anchoring.

### Round 2: targeted cross-examination

The deterministic coordinator routes at most one question to each expert. A
question must name the proposition or assumption it challenges. The responder
can agree, dissent, abstain, or request evidence. No vote is taken.

### Round 3: evidence-seeking skeptic

One different-family checker receives the disputed claims and cited evidence,
not the speakers' private reasoning. It tries to identify unsupported parts,
missing conditions, or a falsifying observation. When no different-family
capacity is available, the run records weaker same-family assurance instead of
pretending independence.

### Optional rounds 4 and 5: revision and synthesis

Only explicit deep mode enables these rounds. Each expert may revise its
position while preserving the original. The final synthesizer reports
agreements, unresolved dissent, confidence changes, proposed tests, and source
gaps. It does not adjudicate truth by majority.

## Learning boundary

Deliberation outputs are trace and proposal artifacts, not beliefs. A proposed
knowledge change follows this path:

1. create a labeled gap, hypothesis, stance, or claim candidate;
2. retrieve or attach replayable source evidence;
3. run calibrated extraction and verification;
4. build a graph-commit envelope;
5. apply only an accepted, idempotent commit;
6. compare held-out acceptance cases before and after the change.

Conversation alone can improve perspective by revealing assumptions and tests,
but repeated assertion, agreement, eloquence, or self-report is never evidence.
Original ideas remain usable as labeled perspective state with assumptions,
uncertainty, expected observations, and disconfirming signals.

## Capacity and busy handling

The pilot uses local capacity by default. Before each round, scheduled runs use
the shared local-capacity observation. Confirmed contention writes a durable
waiting record with retry guidance and exits without sleeping or falling
through to a paid provider. The next attempt resumes from the last completed
round using the same run id and remaining ceilings.

Explicit plan capacity is allowed only through the existing auth-mode and
no-surprise-bills gate. One backend failure cannot silently switch vendors.
Metered API deliberation is deferred until every possible call has a
request-level upper bound, durable reservation, canonical settlement, and a
session-wide ceiling.

## Verification and acceptance

The prototype stays a manual local lab until a held-out set demonstrates:

- better reviewer-scored use of expert state than one-shot consult;
- equal or better uncertainty and dissent preservation;
- no increase in unsupported factual claims;
- useful new test or gap proposals per unit of capacity;
- stable answers on prior cases and no harmful belief reuse;
- replayable cancellation, resume, and capacity-wait behavior;
- bounded wall time and zero untracked cost events.

Run one-shot consult as the baseline. Use human or calibrated-model review for
meaning; deterministic checks validate only schema, lineage, bounds, writes,
and side effects.

## Rejected alternatives

- Free-form debate until consensus: persuasion is not verification.
- Round-robin polishing: later wording can amplify the first error.
- Majority voting: correlated model errors make agreement a weak truth signal.
- Direct learning from transcript: it creates self-reinforcing synthetic
  evidence and bypasses provenance.
- Unbounded autonomous discussion: it has no defensible stop or cost contract.

## Smallest reversible slice

Add a local-only `deliberation` evaluator over frozen fixture experts before a
new public command. Reuse the consult perspective packet and trace schema, add
round lineage plus typed stop state, and compare it against the existing
one-shot consult acceptance set. Only after cancellation, replay, capacity
waiting, and semantic review are measured should the surface graduate to an
explicit experimental CLI command, then MCP or A2A sessions.

## Initial dogfood evidence

A four-expert local one-shot baseline on 2026-07-11 completed provider work in
373 seconds at `$0`, using 32 stored beliefs across consciousness evaluation,
game systems, harness reliability, and durable loops. It supported the core
direction, but also exposed why the evaluator must come first: the provider hit
its output limit, Deepr initially mislabeled the partial result as completed,
the late agreement and disagreement sections were absent, and a mandatory math
section elicited formulas without numeric evidence. The completion contract,
dissent-first response shape, and evidence-conditional quantitative prompt were
fixed before an adversarial follow-up.

The follow-up then exposed a distinct local reasoning-model failure. Ollama
enables thinking by default for supported models, so the model used the entire
1,200-token bound for a separate reasoning field and emitted no visible answer.
Local council synthesis now sends the OpenAI-compatible
`reasoning_effort: none` control documented by
[Ollama's compatibility contract](https://docs.ollama.com/api/openai-compatibility).
The control is local-only and never changes plan-quota or metered requests. If a
backend still returns reasoning without visible content, Deepr does not promote
the reasoning trace or retry through another backend. It returns a visible
diagnostic with the original typed `truncated` or `failed` status.

The remaining baseline weakness is not only latency. A post-fix one-expert
qwen3.6 probe exceeded a five-minute host guard. The host timeout left the
Windows child process tree alive until its exact command lines and PIDs were
verified and stopped, while Deepr left no consult trace because trace creation
currently happens only after `run_consult` returns. The evaluator therefore
must open a durable running record before generation, emit phase heartbeats,
preserve a typed interrupted state, and prove cancellation propagation. The
calling harness owns process-tree termination; Deepr owns durable evidence and
resumable round state. Multi-round UX should not ship before both sides of that
contract are tested.
