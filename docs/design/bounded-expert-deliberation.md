# Bounded expert deliberation

Status: accepted prototype contract, 2026-07-12. Live multi-round surfaces remain
gated by the acceptance criteria below.

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

## Accepted prototype contract

A deliberation is one versioned run with:

- a question and explicit expert roster;
- an immutable expert-state snapshot for each participant;
- a selected local or explicit non-metered plan backend;
- a total turn, token, elapsed-time, and capacity ceiling;
- a maximum of three rounds by default and five by explicit override;
- one durable trace linking every prompt, response, source reference, capacity
  event, cancellation, and verifier result;
- resumable states: waiting_capacity and interrupted;
- terminal states: completed, cancelled, verifier_failed, budget_exhausted, or
  failed;
- no metered fallback in the local-first pilot.

The host remains the orchestrator. Experts receive bounded questions and return
structured perspective artifacts. They do not gain tools, spend authority, or
write authority by participating.

### Artifact contracts

The prototype uses three independently versioned artifact families:

- `deepr-consult-lifecycle-event-v1` is an append-only run journal shared with
  one-shot consult. It is created before backend construction or dispatch and
  carries bounded metadata, including maximum, observed, and remaining spend,
  never answer text or private reasoning.
- `deepr-deliberation-round-v1` is the future immutable round artifact. It binds
  every turn to one run, round, participant, frozen snapshot hash, parent turn,
  prompt hash, response hash, backend, model, and typed completion state.
- `deepr-deliberation-eval-v1` is the `$0` held-out comparison report. Structural
  checks are deterministic; semantic dimensions remain unreviewed until a human
  or calibrated, bias-checked judge records a separate review.

The lifecycle journal does not replace `deepr-consult-trace-v1`. The existing
trace remains the final one-shot transaction artifact and keeps its current
completed/failed compatibility contract. Both artifacts use the same
preallocated `consult_*` trace id.

### State machine and ownership

Every attempt appends `running` before backend construction or provider
dispatch. A running attempt may append more running heartbeats, enter resumable
`waiting_capacity` or `interrupted`, or enter exactly one terminal state. Only
waiting_capacity and interrupted may resume, using the same run id, a new
attempt id, and the next sequence number. Completed work is idempotent and is
not dispatched again. No transition is allowed out of a terminal state.

The process that opens an attempt owns its heartbeat, deadline, cancellation,
and child-process cleanup until it records a resumable or terminal state. A
stale running attempt is not silently treated as failed. Recovery first records
interrupted with the observed stale heartbeat and process metadata, then an
explicit resume may continue it. Heartbeats contain hashes, phase, bounded
counts, elapsed time, remaining ceilings, and process ownership only.

Preflight may begin with a blank provider or model when local discovery has not
completed. A heartbeat may enrich each blank once. Source, backend, and fallback
posture never change, and a resolved provider or model cannot be switched or
cleared. Admission observations may move between unknown, waiting, unavailable,
and admitted without pretending that capacity identity changed.

Cancellation is propagated to cancellable awaitable provider work before a
cancelled event is recorded. The elapsed ceiling includes durable lifecycle
start time, bounds awaitable setup and generation, and is checked at lifecycle
boundaries before a typed `elapsed_limit` terminal event is recorded. Built-in
synchronous backend construction, reporting hooks, lifecycle writes, and final
trace writes run off the event loop. An active durable call is awaited through
cancellation, so it cannot become a hidden late writer. A settled metered
cancellation estimate enters lifecycle progress only after canonical settlement
and only when it is finite, non-negative, and within the run bound. Critical
lifecycle callback errors propagate and cancel sibling council work; ordinary
display callback failures remain best effort.
Provider-specific cleanup must finish before another attempt can resume.
Cancellation or timeout never routes to another backend.

Lifecycle and final-trace serialization share a bounded wait across the
process-local mutex and OS file lock. Every lock acquisition is capped at five
seconds. After durable attempt start, active lifecycle writes and final-trace
finalization also use the smaller remaining elapsed allowance. Standalone load
and resume use the five-second cap outside active-attempt accounting. Contention
before provider work begins is retryable. Elapsed stops use the same boundary.
Contention after provider work may have run, any corrupt journal, and any
possibly partial append are explicitly non-retryable until finalization-only
resume exists. Lock and I/O errors are typed separately and expose no local path.

### Bounds and idempotency

A turn is one provider dispatch. For a roster of `N` participants, the default
three-round protocol permits at most `2N + 1` dispatches: `N` independent
positions, at most `N` cross-examinations, and one skeptic. Explicit deep mode
permits at most `3N + 2`: the default bound plus at most `N` revisions and one
synthesis. Deliberation records `dispatch_scope: provider_call`. The current
one-shot lifecycle separately records a maximum of `N + 1` logical council work
items with `dispatch_scope: council_work_item`; it does not mislabel internal
agentic fallback calls as a proven provider-call bound. Those existing API calls
remain governed by their own per-session spend and ledger gates, while the
local-first deliberation pilot disables live fallback entirely. The current
one-shot wrapper enforces logical-work, elapsed-time, and spend ceilings. It
does not aggregate provider output tokens or context bytes across internal
council calls, so its lifecycle events omit those optional bounds,
observations, and remaining counters. Live deliberation remains gated until
provider-call token and context totals are measured and enforced. Bounds that
are present are pure functions used before dispatch, not estimates after the
fact.

Each dispatch key is `(run_id, round, participant, role)`. Resume loads the
immutable round journal and skips a key whose completed response hash is
already present. Roster order and canonical participant identity are fixed
before coroutine construction. Duplicate names, case aliases, and slug aliases
fail closed. Token, context-byte, elapsed-time, capacity, and spend ceilings
must all be finite and non-negative. Hitting any ceiling produces a typed stop;
it never weakens a gate or falls through to metered capacity.

### Frozen state and untrusted content

Each participant snapshot records the canonical expert identity, exact source
paths, content hashes, and snapshot time. Resume and replay fail closed if any
snapshot hash changes. Round 1 receives no peer output. Later peer output is
delimited and treated as untrusted source data, so embedded tool calls, shell
commands, graph commits, or instructions remain inert text. Deliberation has no
tool executor and no write path into beliefs, graphs, expert state, routing
state, roadmap state, or project files. Only trace and evaluation artifact
roots may change.

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

The held-out rubric separately scores expert-state use, response to peer
challenge, uncertainty calibration, dissent preservation, unsupported factual
claims, useful test or gap proposals, and harmful belief reuse. Structural
completion never implies semantic acceptance. A deliberation result remains
`review_required: true` and `accepted: false` until the review artifact passes
published thresholds. Model judging is admitted only after agreement and
position-order calibration against human labels; provider-family difference is
recorded assurance metadata, not proof of independence.

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
verified and stopped. That finding is now covered by the one-shot transaction
wrapper: Deepr preallocates the final trace id and opens the lifecycle journal
before backend construction or provider dispatch, emits phase heartbeats, and
records typed cancellation or failure even when final trace construction cannot
complete. Durable lifecycle and final-trace writes run off the event loop and
are awaited through cancellation, while the calling harness still owns any
external process tree it launched. Live multi-round UX remains gated on replay,
resume, capacity-wait, and provider-call token and context enforcement tests.
